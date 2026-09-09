from collections.abc import Callable
from typing import Any

from langgraph.types import Command
from pydantic import Field
from sqlalchemy.orm import Session, sessionmaker

from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.domain.enums import (
    ActorKind,
    AttributeStatus,
    EvidenceSource,
    ProjectStatus,
    Role,
)
from alignspace.domain.models import DomainModel, Evidence, ProjectState
from alignspace.domain.patches import StatePatch, UpsertAttribute, apply_patch
from alignspace.domain.policies import StaleStateError
from alignspace.persistence.repository import canonical_request_hash
from alignspace.persistence.uow import SqlAlchemyUnitOfWork


class AuthorizationError(PermissionError):
    """Raised when an actor is not permitted to perform a project action."""


class WorkflowResponse(DomainModel):
    project_id: str
    state_version: int = Field(ge=0)
    status: ProjectStatus
    wait_reason: str | None = None
    pending_question: dict[str, object] | None = None
    project_state: dict[str, object]


MembershipCheck = Callable[[str, ActorContext], bool]


class WorkflowService:
    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        graph: Any,
        membership_check: MembershipCheck,
    ) -> None:
        self._session_factory = session_factory
        self._graph = graph
        self._membership_check = membership_check

    def start_analysis(
        self,
        project_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        self._authorize(project_id, actor)
        return self._run_graph(project_id, actor, envelope, action="start_analysis")

    def resume(
        self,
        project_id: str,
        actor: ActorContext,
        wait_reason: str,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        self._authorize(project_id, actor)
        required_role = {
            "homeowner": Role.HOMEOWNER,
            "designer": Role.DESIGNER,
            "professional": Role.DESIGNER,
        }.get(wait_reason)
        if required_role is None or actor.role != required_role:
            raise AuthorizationError(f"actor cannot answer {wait_reason} task")
        return self._run_graph(
            project_id,
            actor,
            envelope,
            action=f"resume_{wait_reason}",
            resume=True,
        )

    def edit_attribute(
        self,
        project_id: str,
        attribute_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        self._authorize(project_id, actor)
        request_hash = self._hash_request(
            "edit_attribute",
            project_id,
            actor,
            envelope,
            extra={"attributeId": attribute_id},
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return WorkflowResponse.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            attribute = next(
                (item for item in state.attributes if item.id == attribute_id),
                None,
            )
            if attribute is None:
                raise KeyError(f"attribute {attribute_id} not found")
            status = AttributeStatus(envelope.data["status"])
            if status not in {
                AttributeStatus.CONFIRMED,
                AttributeStatus.REJECTED,
                AttributeStatus.UNRESOLVED,
                AttributeStatus.NOT_APPLICABLE,
            }:
                raise ValueError("human attribute status is not editable")
            source = (
                EvidenceSource.HOMEOWNER_ANSWER
                if actor.role == Role.HOMEOWNER
                else EvidenceSource.DESIGNER_NOTE
            )
            changed = attribute.model_copy(
                update={
                    "value": envelope.data.get("value", attribute.value),
                    "status": status,
                    "confidence": 1.0,
                    "actor": (
                        ActorKind.HOMEOWNER if actor.role == Role.HOMEOWNER else ActorKind.DESIGNER
                    ),
                    "evidence": [
                        *attribute.evidence,
                        Evidence(
                            source_type=source,
                            source_id=envelope.idempotency_key,
                            description="Explicit human attribute correction.",
                        ),
                    ],
                }
            )
            updated = apply_patch(
                state,
                StatePatch(
                    expected_state_version=state.state_version,
                    operations=[UpsertAttribute(attribute=changed)],
                ),
            )
            response = self._response(updated)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
            return response

    def _run_graph(
        self,
        project_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
        *,
        action: str,
        resume: bool = False,
    ) -> WorkflowResponse:
        request_hash = self._hash_request(action, project_id, actor, envelope)
        config = {"configurable": {"thread_id": project_id}}
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return WorkflowResponse.model_validate(replay.response_payload)
            current = uow.projects.load(project_id)
            self._check_version(current, envelope.expected_state_version)
            if resume:
                self._reconcile_checkpoint(config, current)
                graph_input: object = Command(resume=envelope.data)
            else:
                graph_input = {
                    "project_id": project_id,
                    "project_state": current.model_dump(mode="json", by_alias=True),
                }
            graph_result = self._graph.invoke(graph_input, config=config)
            returned = ProjectState.model_validate(graph_result["project_state"])
            wait_reason, pending_question = self._interrupt_details(graph_result)
            status = self._status_for(wait_reason, returned.status)
            accepted = returned.model_copy(
                update={
                    "state_version": current.state_version + 1,
                    "status": status,
                    "current_node": f"wait_{wait_reason}" if wait_reason else returned.current_node,
                    "wait_reason": wait_reason,
                }
            )
            response = self._response(accepted, pending_question)
            uow.projects.save(accepted, expected_version=current.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
            return response

    def _reconcile_checkpoint(self, config: dict[str, object], current: ProjectState) -> None:
        snapshot = self._graph.get_state(config)
        values = snapshot.values or {}
        checkpoint_state = values.get("project_state") if isinstance(values, dict) else None
        if not isinstance(checkpoint_state, dict):
            return
        checkpoint_version = checkpoint_state.get("stateVersion")
        if checkpoint_version != current.state_version:
            self._graph.update_state(
                config,
                {"project_state": current.model_dump(mode="json", by_alias=True)},
            )

    @staticmethod
    def _interrupt_details(
        graph_result: dict[str, object],
    ) -> tuple[str | None, dict[str, object] | None]:
        interrupts = graph_result.get("__interrupt__") or []
        if not interrupts:
            return None, None
        value = interrupts[0].value
        return value.get("waitReason"), value.get("pendingQuestion")

    @staticmethod
    def _status_for(wait_reason: str | None, fallback: ProjectStatus) -> ProjectStatus:
        return {
            "homeowner": ProjectStatus.HOMEOWNER_REVIEW,
            "designer": ProjectStatus.DESIGNER_REVIEW,
            "professional": ProjectStatus.ALIGNMENT,
        }.get(wait_reason, fallback)

    @staticmethod
    def _check_version(state: ProjectState, expected_version: int) -> None:
        if state.state_version != expected_version:
            raise StaleStateError(
                f"expected version {expected_version}, current version {state.state_version}"
            )

    def _authorize(self, project_id: str, actor: ActorContext) -> None:
        if not self._membership_check(project_id, actor):
            raise AuthorizationError("actor is not a project member with the requested role")

    @staticmethod
    def _hash_request(
        action: str,
        project_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
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
    def _response(
        state: ProjectState,
        pending_question: dict[str, object] | None = None,
    ) -> WorkflowResponse:
        return WorkflowResponse(
            project_id=state.project_id,
            state_version=state.state_version,
            status=state.status,
            wait_reason=state.wait_reason,
            pending_question=pending_question,
            project_state=state.model_dump(mode="json", by_alias=True),
        )

    @staticmethod
    def _record_replay(
        uow: SqlAlchemyUnitOfWork,
        project_id: str,
        envelope: WriteEnvelope[dict[str, object]],
        request_hash: str,
        response: WorkflowResponse,
    ) -> None:
        uow.idempotency.record(
            project_id=project_id,
            key=envelope.idempotency_key,
            request_hash=request_hash,
            response_payload=response.model_dump(mode="json", by_alias=True),
            resulting_version=response.state_version,
        )
