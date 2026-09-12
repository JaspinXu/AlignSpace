import secrets
import time
from collections.abc import Callable

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from alignspace.application.commands import ActorContext
from alignspace.application.resources import ProjectResourceService, ProjectView
from alignspace.application.service import AuthorizationError
from alignspace.auth.models import JoinCodeRow
from alignspace.auth.service import digest, write_transaction
from alignspace.domain.enums import Role
from alignspace.domain.models import DomainModel, NonBlankString
from alignspace.persistence.tables import ProjectMemberRow

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 12
CODE_TTL_SECONDS = 24 * 60 * 60


class JoinCodeError(ValueError):
    """Raised when a project code cannot be redeemed."""


class JoinRequest(DomainModel):
    code: NonBlankString


class JoinCodeView(DomainModel):
    code: str
    expires_at: int


class MembershipService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        resources: ProjectResourceService,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._sessions = session_factory
        self._resources = resources
        self.clock = clock

    def generate_code(self, project_id: str, actor: ActorContext) -> JoinCodeView:
        with write_transaction(self._sessions) as db:
            member = db.scalar(
                select(ProjectMemberRow).where(
                    ProjectMemberRow.project_id == project_id,
                    ProjectMemberRow.member_id == actor.actor_id,
                    ProjectMemberRow.role == Role.HOMEOWNER.value,
                )
            )
            if member is None:
                raise AuthorizationError("only the homeowner can issue a project code")
            db.execute(
                update(JoinCodeRow)
                .where(JoinCodeRow.project_id == project_id, JoinCodeRow.revoked.is_(False))
                .values(revoked=True)
            )
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            expires_at = int(self.clock()) + CODE_TTL_SECONDS
            db.add(
                JoinCodeRow(
                    digest=digest(code),
                    project_id=project_id,
                    expires_at=expires_at,
                    revoked=False,
                    used_by=None,
                )
            )
        return JoinCodeView(code=code, expires_at=expires_at)

    def join(self, actor: ActorContext, request: JoinRequest) -> ProjectView:
        project_id = self._consume(request.code.strip(), actor)
        return self._resources.get(
            project_id,
            ActorContext(actor_id=actor.actor_id, role=Role.DESIGNER),
        )

    def _consume(self, code: str, actor: ActorContext) -> str:
        try:
            with write_transaction(self._sessions) as db:
                row = db.get(JoinCodeRow, digest(code))
                if row is None:
                    raise JoinCodeError()
                if row.used_by == actor.actor_id:
                    return row.project_id
                if row.revoked or row.expires_at <= int(self.clock()):
                    raise JoinCodeError()
                existing = db.scalar(
                    select(ProjectMemberRow).where(
                        ProjectMemberRow.project_id == row.project_id,
                        ProjectMemberRow.member_id == actor.actor_id,
                    )
                )
                if existing is not None:
                    if existing.role == Role.DESIGNER.value:
                        return row.project_id
                    raise JoinCodeError("屋主不能作为设计师加入自己的项目。")
                occupied = db.scalar(
                    select(ProjectMemberRow).where(
                        ProjectMemberRow.project_id == row.project_id,
                        ProjectMemberRow.role == Role.DESIGNER.value,
                    )
                )
                if occupied is not None:
                    raise JoinCodeError()
                db.add(
                    ProjectMemberRow(
                        project_id=row.project_id,
                        member_id=actor.actor_id,
                        role=Role.DESIGNER.value,
                        payload={},
                    )
                )
                row.used_by = actor.actor_id
                row.revoked = True
                return row.project_id
        except IntegrityError as exc:
            # The unique (project, role) index is the last line of defence if two
            # requests ever pass the membership check before either commits.
            raise JoinCodeError() from exc
