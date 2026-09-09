from collections.abc import Callable
from typing import Any
from uuid import uuid4

from pydantic import Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.service import AuthorizationError
from alignspace.domain.enums import Role
from alignspace.domain.models import DomainModel, NonBlankString, ProjectState
from alignspace.domain.policies import StaleStateError
from alignspace.persistence.repository import canonical_request_hash
from alignspace.persistence.tables import ImageAssetRow, ProjectMemberRow, ProjectRow
from alignspace.persistence.uow import SqlAlchemyUnitOfWork


class ConsentRequiredError(ValueError):
    """Raised when image processing consent has not been granted."""


class AssetLimitError(ValueError):
    """Raised when a project already has the maximum reference assets."""


class AssetCountError(ValueError):
    """Raised when analysis does not have three to ten reference assets."""


class CreateProjectCommand(DomainModel):
    room_type: NonBlankString
    budget_band: NonBlankString
    consent: bool
    designer_id: NonBlankString


class AssetInput(DomainModel):
    fixture_id: NonBlankString
    media_type: str = Field(pattern=r"^image/(jpeg|png|webp)$")
    size_bytes: int = Field(gt=0, le=10 * 1024 * 1024)


class AssetView(DomainModel):
    id: str
    fixture_id: str
    media_type: str
    size_bytes: int


class AssetWriteView(AssetView):
    state_version: int


class AssetDeleteView(DomainModel):
    id: str
    state_version: int


class ProjectView(DomainModel):
    id: str
    room_type: str
    budget_band: str
    consent: bool
    status: str
    state_version: int
    assets: list[AssetView]


CheckpointDelete = Callable[[str], Any]


class ProjectResourceService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        checkpoint_delete: CheckpointDelete,
    ) -> None:
        self._session_factory = session_factory
        self._checkpoint_delete = checkpoint_delete

    def create(self, actor: ActorContext, command: CreateProjectCommand) -> ProjectView:
        if actor.role != Role.HOMEOWNER:
            raise AuthorizationError("only a homeowner can create a project")
        if actor.actor_id == command.designer_id:
            raise ValueError("homeowner and designer must be distinct project members")
        project_id = str(uuid4())
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            state = ProjectState(project_id=project_id)
            uow.projects.create(
                state,
                room_type=command.room_type,
                budget_band=command.budget_band,
                consent=command.consent,
            )
            uow.session.add_all(
                [
                    ProjectMemberRow(
                        project_id=project_id,
                        member_id=actor.actor_id,
                        role=Role.HOMEOWNER.value,
                        payload={},
                    ),
                    ProjectMemberRow(
                        project_id=project_id,
                        member_id=command.designer_id,
                        role=Role.DESIGNER.value,
                        payload={},
                    ),
                ]
            )
            uow.commit()
        return self.get(project_id, actor)

    def get(self, project_id: str, actor: ActorContext) -> ProjectView:
        with self._session_factory() as session:
            project = self._project(session, project_id)
            self._authorize_in_session(session, project_id, actor)
            return self._project_view(session, project)

    def delete(self, project_id: str, actor: ActorContext) -> None:
        with self._session_factory() as session:
            project = self._project(session, project_id)
            self._authorize_in_session(session, project_id, actor)
            if actor.role != Role.HOMEOWNER:
                raise AuthorizationError("only the homeowner can delete a project")
            session.delete(project)
            session.commit()
        self._checkpoint_delete(project_id)

    def register_asset(
        self,
        project_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[AssetInput],
    ) -> AssetWriteView:
        request_hash = self._request_hash("register_asset", project_id, actor, envelope)
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            self._authorize_in_session(uow.session, project_id, actor)
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return AssetWriteView.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            project = self._project(uow.session, project_id)
            if not project.consent:
                raise ConsentRequiredError("image consent is required before registering an asset")
            asset_count = uow.session.scalar(
                select(func.count()).select_from(ImageAssetRow).where(
                    ImageAssetRow.project_id == project_id
                )
            )
            if asset_count >= 10:
                raise AssetLimitError("a project can contain at most ten reference assets")
            asset = AssetWriteView(
                id=str(uuid4()),
                fixture_id=envelope.data.fixture_id,
                media_type=envelope.data.media_type,
                size_bytes=envelope.data.size_bytes,
                state_version=state.state_version + 1,
            )
            uow.session.add(
                ImageAssetRow(
                    project_id=project_id,
                    id=asset.id,
                    payload=asset.model_dump(
                        mode="json",
                        by_alias=True,
                        exclude={"state_version"},
                    ),
                )
            )
            updated = state.model_copy(update={"state_version": state.state_version + 1})
            uow.projects.save(updated, expected_version=state.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, asset)
            uow.commit()
            return asset

    def delete_asset(
        self,
        project_id: str,
        asset_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> AssetDeleteView:
        request_hash = self._request_hash(
            "delete_asset",
            project_id,
            actor,
            envelope,
            extra={"assetId": asset_id},
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            self._authorize_in_session(uow.session, project_id, actor)
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return AssetDeleteView.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            asset = uow.session.get(ImageAssetRow, (project_id, asset_id))
            if asset is None:
                raise KeyError(f"asset {asset_id} not found")
            uow.session.delete(asset)
            updated = state.model_copy(update={"state_version": state.state_version + 1})
            uow.projects.save(updated, expected_version=state.state_version)
            response = AssetDeleteView(id=asset_id, state_version=updated.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
        self._checkpoint_delete(project_id)
        return response

    def is_member(self, project_id: str, actor: ActorContext) -> bool:
        with self._session_factory() as session:
            return self._membership(session, project_id, actor) is not None

    def require_analysis_ready(self, project_id: str, actor: ActorContext) -> None:
        with self._session_factory() as session:
            project = self._project(session, project_id)
            self._authorize_in_session(session, project_id, actor)
            if not project.consent:
                raise ConsentRequiredError("image consent is required before analysis")
            asset_count = session.scalar(
                select(func.count()).select_from(ImageAssetRow).where(
                    ImageAssetRow.project_id == project_id
                )
            )
            if not 3 <= asset_count <= 10:
                raise AssetCountError("analysis requires between three and ten reference assets")

    @staticmethod
    def _project(session: Session, project_id: str) -> ProjectRow:
        project = session.get(ProjectRow, project_id)
        if project is None:
            raise KeyError(f"project {project_id} not found")
        return project

    @classmethod
    def _authorize_in_session(
        cls,
        session: Session,
        project_id: str,
        actor: ActorContext,
    ) -> None:
        cls._project(session, project_id)
        if cls._membership(session, project_id, actor) is None:
            raise AuthorizationError("actor is not a project member with the requested role")

    @staticmethod
    def _membership(
        session: Session,
        project_id: str,
        actor: ActorContext,
    ) -> ProjectMemberRow | None:
        return session.scalar(
            select(ProjectMemberRow).where(
                ProjectMemberRow.project_id == project_id,
                ProjectMemberRow.member_id == actor.actor_id,
                ProjectMemberRow.role == actor.role.value,
            )
        )

    @staticmethod
    def _project_view(session: Session, project: ProjectRow) -> ProjectView:
        assets = session.scalars(
            select(ImageAssetRow)
            .where(ImageAssetRow.project_id == project.id)
            .order_by(ImageAssetRow.id)
        ).all()
        return ProjectView(
            id=project.id,
            room_type=project.room_type or "unknown",
            budget_band=project.budget_band or "unknown",
            consent=project.consent,
            status=project.status,
            state_version=project.state_version,
            assets=[AssetView.model_validate(item.payload | {"id": item.id}) for item in assets],
        )

    @staticmethod
    def _check_version(state: ProjectState, expected_version: int) -> None:
        if state.state_version != expected_version:
            raise StaleStateError(
                f"expected version {expected_version}, current version {state.state_version}"
            )

    @staticmethod
    def _request_hash(
        action: str,
        project_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[Any],
        *,
        extra: dict[str, object] | None = None,
    ) -> str:
        return canonical_request_hash(
            {
                "action": action,
                "projectId": project_id,
                "actor": actor.model_dump(mode="json", by_alias=True),
                "envelope": envelope.model_dump(mode="json", by_alias=True),
                **(extra or {}),
            }
        )

    @staticmethod
    def _record_replay(
        uow: SqlAlchemyUnitOfWork,
        project_id: str,
        envelope: WriteEnvelope[Any],
        request_hash: str,
        response: DomainModel,
    ) -> None:
        uow.idempotency.record(
            project_id=project_id,
            key=envelope.idempotency_key,
            request_hash=request_hash,
            response_payload=response.model_dump(mode="json", by_alias=True),
            resulting_version=response.state_version,
        )
