import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from alignspace.domain.models import (
    Approval,
    Attribute,
    BriefVersion,
    Conflict,
    Constraint,
    ProjectState,
    Question,
)
from alignspace.domain.policies import StaleStateError
from alignspace.persistence.tables import (
    ApprovalRow,
    AttributeRow,
    AuditEventRow,
    BriefVersionRow,
    ConflictRow,
    ConstraintRow,
    IdempotencyRecordRow,
    ProjectRow,
    QuestionRow,
)


class IdempotencyConflictError(ValueError):
    """Raised when an idempotency key is reused with different request content."""


@dataclass(frozen=True)
class IdempotencyResult:
    response_payload: dict[str, object]
    resulting_version: int


def canonical_request_hash(payload: object) -> str:
    canonical_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class IdempotencyRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lookup(
        self,
        project_id: str,
        key: str,
        request_hash: str,
    ) -> IdempotencyResult | None:
        row = self._session.get(IdempotencyRecordRow, (project_id, key))
        if row is None:
            return None
        if row.request_hash != request_hash:
            raise IdempotencyConflictError(
                f"idempotency key {key} was already used with different content"
            )
        return IdempotencyResult(
            response_payload=row.response_payload,
            resulting_version=row.resulting_version,
        )

    def record(
        self,
        *,
        project_id: str,
        key: str,
        request_hash: str,
        response_payload: dict[str, object],
        resulting_version: int,
    ) -> None:
        self._session.add(
            IdempotencyRecordRow(
                project_id=project_id,
                key=key,
                request_hash=request_hash,
                response_payload=response_payload,
                resulting_version=resulting_version,
            )
        )


class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        state: ProjectState,
        *,
        room_type: str | None = None,
        budget_band: str | None = None,
        consent: bool = False,
    ) -> None:
        if state.state_version != 0:
            raise ValueError("new projects must start at state_version 0")
        self._session.add(
            ProjectRow(
                id=state.project_id,
                state_version=state.state_version,
                status=state.status.value,
                completeness=state.completeness,
                current_node=state.current_node,
                wait_reason=state.wait_reason,
                room_type=room_type,
                budget_band=budget_band,
                consent=consent,
                brief_stale=state.brief_stale,
            )
        )
        self._replace_entities(state)
        self._append_audit_event(state, "project_created")

    def load(self, project_id: str) -> ProjectState:
        project = self._session.get(ProjectRow, project_id)
        if project is None:
            raise KeyError(f"project {project_id} not found")
        return ProjectState(
            project_id=project.id,
            state_version=project.state_version,
            status=project.status,
            attributes=self._load_models(AttributeRow, Attribute, project_id),
            constraints=self._load_models(ConstraintRow, Constraint, project_id),
            questions=self._load_models(QuestionRow, Question, project_id),
            conflicts=self._load_models(ConflictRow, Conflict, project_id),
            brief_versions=self._load_models(BriefVersionRow, BriefVersion, project_id),
            approvals=self._load_models(ApprovalRow, Approval, project_id),
            completeness=project.completeness,
            current_node=project.current_node,
            wait_reason=project.wait_reason,
            brief_stale=project.brief_stale,
        )

    def save(self, state: ProjectState, expected_version: int) -> None:
        if state.state_version != expected_version + 1:
            raise ValueError("state_version must increment expected_version by exactly one")
        result = self._session.execute(
            update(ProjectRow)
            .where(
                ProjectRow.id == state.project_id,
                ProjectRow.state_version == expected_version,
            )
            .values(
                state_version=state.state_version,
                status=state.status.value,
                completeness=state.completeness,
                current_node=state.current_node,
                wait_reason=state.wait_reason,
                brief_stale=state.brief_stale,
            )
        )
        if result.rowcount != 1:
            raise StaleStateError(f"project {state.project_id} changed concurrently")
        self._replace_entities(state)
        self._append_audit_event(state, "project_saved")

    def _replace_entities(self, state: ProjectState) -> None:
        specifications = (
            (AttributeRow, state.attributes, lambda item: {"id": item.id}),
            (ConstraintRow, state.constraints, lambda item: {"id": item.id}),
            (QuestionRow, state.questions, lambda item: {"id": item.id}),
            (ConflictRow, state.conflicts, lambda item: {"id": item.id}),
            (BriefVersionRow, state.brief_versions, lambda item: {"version": item.version}),
            (
                ApprovalRow,
                state.approvals,
                lambda item: {
                    "role": item.role.value,
                    "brief_version": item.brief_version,
                    "content_hash": item.content_hash,
                },
            ),
        )
        for row_type, items, identity in specifications:
            self._session.execute(delete(row_type).where(row_type.project_id == state.project_id))
            self._session.add_all(
                row_type(
                    project_id=state.project_id,
                    position=position,
                    payload=item.model_dump(mode="json"),
                    **identity(item),
                )
                for position, item in enumerate(items)
            )

    def _load_models(self, row_type: Any, model_type: Any, project_id: str) -> list[Any]:
        rows = self._session.scalars(
            select(row_type)
            .where(row_type.project_id == project_id)
            .order_by(row_type.position)
        ).all()
        return [model_type.model_validate(row.payload) for row in rows]

    def _append_audit_event(self, state: ProjectState, event_type: str) -> None:
        self._session.add(
            AuditEventRow(
                project_id=state.project_id,
                event_type=event_type,
                state_version=state.state_version,
                payload={
                    "status": state.status.value,
                    "currentNode": state.current_node,
                    "waitReason": state.wait_reason,
                },
            )
        )
