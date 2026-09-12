import time
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.service import AuthorizationError
from alignspace.domain.enums import Role
from alignspace.domain.models import DomainModel, NonBlankString, ProjectState, Question
from alignspace.domain.policies import StaleStateError
from alignspace.persistence.database import read_transaction
from alignspace.persistence.repository import ProjectRepository, canonical_request_hash
from alignspace.persistence.tables import ImageAssetRow, ProjectMemberRow, ProjectRow
from alignspace.persistence.uow import SqlAlchemyUnitOfWork
from alignspace.storage.base import Storage
from alignspace.storage.images import prepare_image


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


class AssetView(DomainModel):
    id: str
    original_filename: str
    media_type: str
    size_bytes: int
    sha256: str
    deleted: bool
    deleted_at: int | None = None


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
    role: Role
    designer_joined: bool


class ProjectSnapshot(DomainModel):
    project: ProjectView
    project_state: ProjectState
    pending_question: Question | None = None


CheckpointDelete = Callable[[str], Any]


class ProjectResourceService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        checkpoint_delete: CheckpointDelete,
        storage: Storage,
    ) -> None:
        self._session_factory = session_factory
        self._checkpoint_delete = checkpoint_delete
        self._storage = storage

    def create(self, actor: ActorContext, command: CreateProjectCommand) -> ProjectView:
        if actor.role != Role.HOMEOWNER:
            raise AuthorizationError("only a homeowner can create a project")
        project_id = str(uuid4())
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            state = ProjectState(project_id=project_id)
            uow.projects.create(
                state,
                room_type=command.room_type,
                budget_band=command.budget_band,
                consent=command.consent,
            )
            uow.session.add(
                ProjectMemberRow(
                    project_id=project_id,
                    member_id=actor.actor_id,
                    role=Role.HOMEOWNER.value,
                    payload={},
                )
            )
            uow.commit()
        return self.get(project_id, actor)

    def get(self, project_id: str, actor: ActorContext) -> ProjectView:
        with self._session_factory() as session:
            project = self._project(session, project_id)
            self._authorize_in_session(session, project_id, actor)
            return self._project_view(session, project, actor.role)

    def list_for_member(self, actor: ActorContext) -> list[ProjectView]:
        with self._session_factory() as session:
            memberships = session.execute(
                select(ProjectRow, ProjectMemberRow.role)
                .join(ProjectMemberRow, ProjectMemberRow.project_id == ProjectRow.id)
                .where(ProjectMemberRow.member_id == actor.actor_id)
                .order_by(ProjectRow.id)
            ).all()
            return [
                self._project_view(session, project, Role(role))
                for project, role in memberships
            ]

    def snapshot(self, project_id: str, actor: ActorContext) -> ProjectSnapshot:
        with read_transaction(self._session_factory) as session:
            project = self._project(session, project_id)
            self._authorize_in_session(session, project_id, actor)
            state = ProjectRepository(session).load(project_id)
            view = self._project_view(session, project, actor.role)
            pending = next((item for item in state.questions if item.answer is None), None)
            return ProjectSnapshot(project=view, project_state=state, pending_question=pending)

    def delete(self, project_id: str, actor: ActorContext) -> None:
        with self._session_factory() as session:
            project = self._project(session, project_id)
            self._authorize_in_session(session, project_id, actor)
            if actor.role != Role.HOMEOWNER:
                raise AuthorizationError("only the homeowner can delete a project")
            storage_keys = [
                key
                for asset in session.scalars(
                    select(ImageAssetRow).where(ImageAssetRow.project_id == project_id)
                )
                if (key := asset.payload.get("storage_key")) is not None
            ]
            session.delete(project)
            session.commit()
        for storage_key in storage_keys:
            self._gc_storage_key(storage_key)
        self._checkpoint_delete(project_id)

    def register_asset(
        self,
        project_id: str,
        actor: ActorContext,
        *,
        expected_state_version: int,
        idempotency_key: str,
        filename: str,
        raw: bytes,
        declared_type: str | None = None,
    ) -> AssetWriteView:
        self._authorize_homeowner(project_id, actor)
        prepared = prepare_image(raw, declared_type=declared_type, filename=filename)
        request_hash = canonical_request_hash(
            {
                "action": "upload_asset",
                "projectId": project_id,
                "actor": actor.model_dump(mode="json", by_alias=True),
                "expectedStateVersion": expected_state_version,
                "idempotencyKey": idempotency_key,
                "sha256": prepared.sha256,
                "mediaType": prepared.media_type,
                "sizeBytes": len(prepared.data),
            }
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            self._authorize_in_session(uow.session, project_id, actor)
            if actor.role != Role.HOMEOWNER:
                raise AuthorizationError("only the homeowner can manage reference assets")
            replay = uow.idempotency.lookup(project_id, idempotency_key, request_hash)
            if replay is not None:
                return AssetWriteView.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, expected_state_version)
            project = self._project(uow.session, project_id)
            if not project.consent:
                raise ConsentRequiredError("image consent is required before registering an asset")
            active = uow.session.scalar(
                select(func.count()).select_from(ImageAssetRow).where(
                    ImageAssetRow.project_id == project_id,
                    ImageAssetRow.deleted_at.is_(None),
                )
            )
            if active >= 10:
                raise AssetLimitError("a project can contain at most ten reference assets")
            storage_key = self._storage.save(prepared.data, prepared.extension)
            asset = AssetWriteView(
                id=str(uuid4()),
                original_filename=filename,
                media_type=prepared.media_type,
                size_bytes=len(prepared.data),
                sha256=prepared.sha256,
                deleted=False,
                deleted_at=None,
                state_version=state.state_version + 1,
            )
            uow.session.add(
                ImageAssetRow(
                    project_id=project_id,
                    id=asset.id,
                    payload={
                        "original_filename": filename,
                        "media_type": prepared.media_type,
                        "size_bytes": len(prepared.data),
                        "sha256": prepared.sha256,
                        "storage_key": storage_key,
                        "width": prepared.width,
                        "height": prepared.height,
                    },
                )
            )
            updated = state.model_copy(update={"state_version": state.state_version + 1})
            uow.projects.save(updated, expected_version=state.state_version)
            uow.idempotency.record(
                project_id=project_id,
                key=idempotency_key,
                request_hash=request_hash,
                response_payload=asset.model_dump(mode="json", by_alias=True),
                resulting_version=asset.state_version,
            )
            uow.commit()
            return asset

    def asset_content(self, project_id: str, asset_id: str, actor: ActorContext) -> tuple[bytes, str]:
        with read_transaction(self._session_factory) as session:
            self._project(session, project_id)
            self._authorize_in_session(session, project_id, actor)
            asset = session.get(ImageAssetRow, (project_id, asset_id))
            if asset is None or asset.deleted_at is not None:
                raise KeyError(f"asset {asset_id} not found")
            return self._storage.open(asset.payload["storage_key"]), asset.payload["media_type"]

    def _authorize_homeowner(self, project_id: str, actor: ActorContext) -> None:
        with self._session_factory() as session:
            self._project(session, project_id)
            self._authorize_in_session(session, project_id, actor)
            if actor.role != Role.HOMEOWNER:
                raise AuthorizationError("only the homeowner can manage reference assets")

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
            if actor.role != Role.HOMEOWNER:
                raise AuthorizationError("only the homeowner can manage reference assets")
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return AssetDeleteView.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            asset = uow.session.get(ImageAssetRow, (project_id, asset_id))
            if asset is None or asset.deleted_at is not None:
                raise KeyError(f"asset {asset_id} not found")
            storage_key = asset.payload["storage_key"]
            asset.payload = {**asset.payload, "storage_key": None}
            asset.deleted_at = int(time.time())
            updated = state.model_copy(update={"state_version": state.state_version + 1})
            uow.projects.save(updated, expected_version=state.state_version)
            response = AssetDeleteView(id=asset_id, state_version=updated.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
        self._gc_storage_key(storage_key)
        return response

    def _gc_storage_key(self, storage_key: str) -> None:
        with self._session_factory() as session:
            references = session.scalar(
                select(func.count()).select_from(ImageAssetRow).where(
                    ImageAssetRow.payload["storage_key"].as_string() == storage_key
                )
            )
        if references == 0:
            self._storage.delete(storage_key)

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
                    ImageAssetRow.project_id == project_id,
                    ImageAssetRow.deleted_at.is_(None),
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
    def _project_view(session: Session, project: ProjectRow, role: Role) -> ProjectView:
        assets = session.scalars(
            select(ImageAssetRow)
            .where(ImageAssetRow.project_id == project.id)
            .order_by(ImageAssetRow.id)
        ).all()
        designer_joined = session.scalar(
            select(func.count()).select_from(ProjectMemberRow).where(
                ProjectMemberRow.project_id == project.id,
                ProjectMemberRow.role == Role.DESIGNER.value,
            )
        ) > 0
        return ProjectView(
            id=project.id,
            room_type=project.room_type or "unknown",
            budget_band=project.budget_band or "unknown",
            consent=project.consent,
            status=project.status,
            state_version=project.state_version,
            assets=[
                AssetView(
                    id=item.id,
                    original_filename=item.payload.get("original_filename", "legacy-asset"),
                    media_type=item.payload.get("media_type", "image/unknown"),
                    size_bytes=item.payload.get("size_bytes", 0),
                    sha256=item.payload.get("sha256", ""),
                    deleted=item.deleted_at is not None,
                    deleted_at=item.deleted_at,
                )
                for item in assets
            ],
            role=role,
            designer_joined=designer_joined,
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
