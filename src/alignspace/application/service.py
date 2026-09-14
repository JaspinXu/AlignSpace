import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator
from langgraph.types import Command
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from alignspace.application.briefing import build_brief_payload, build_brief_version
from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.domain.constraints import flag_brief_change, reconcile_constraints
from alignspace.domain.enums import (
    ActorKind,
    AttributeStatus,
    ConflictStatus,
    ConstraintCategory,
    ConstraintOwner,
    ConstraintSeverity,
    ConstraintVerificationStatus,
    EvidenceSource,
    ProjectStatus,
    Role,
)
from alignspace.domain.models import (
    Approval,
    Attribute,
    BriefVersion,
    Constraint,
    DomainModel,
    Evidence,
    ProjectState,
    Question,
    calculate_brief_content_hash,
)
from alignspace.domain.patches import (
    StatePatch,
    UpsertApproval,
    UpsertAttribute,
    UpsertBriefVersion,
    UpsertConflict,
    UpsertConstraint,
    apply_patch,
)
from alignspace.domain.policies import (
    DomainRuleError,
    StaleStateError,
    calculate_completeness,
    can_approve,
    can_draft_brief,
    record_conflict_attempt,
    validate_professional_claim,
)
from alignspace.persistence.repository import canonical_request_hash
from alignspace.persistence.tables import ImageAssetRow
from alignspace.persistence.uow import SqlAlchemyUnitOfWork


class AuthorizationError(PermissionError):
    """Raised when an actor is not permitted to perform a project action."""


class BriefHashMismatchError(ValueError):
    """Raised when approval targets content other than the stored brief."""


class BriefSchemaError(ValueError):
    """Raised when an edited brief does not match the public schema."""


class ApprovalNotAllowedError(ValueError):
    """Raised when completeness or conflicts prevent approval."""


class BriefReviewError(ValueError):
    """Raised when a valid brief still fails approval-readiness review."""


class WorkflowResponse(DomainModel):
    project_id: str
    state_version: int = Field(ge=0)
    status: ProjectStatus
    wait_reason: str | None = None
    pending_question: dict[str, object] | None = None
    project_state: dict[str, object]


class BriefView(DomainModel):
    version: int
    content_hash: str
    payload: dict[str, object]
    completeness: float
    approvals: list[Approval]
    state_version: int


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
        schema_path = Path(__file__).resolve().parents[3] / "schemas/design-brief.schema.json"
        self._brief_validator = Draft202012Validator(json.loads(schema_path.read_text()))

    def start_analysis(
        self,
        project_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        self._authorize(project_id, actor)
        if actor.role != Role.HOMEOWNER:
            raise AuthorizationError("only the homeowner can start analysis")
        return self._run_graph(project_id, actor, envelope, action="start_analysis")

    def resume(
        self,
        project_id: str,
        actor: ActorContext,
        wait_reason: str,
        envelope: WriteEnvelope[dict[str, object]],
        *,
        action: str | None = None,
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
            action=action or f"resume_{wait_reason}",
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
        raw_status = envelope.data.get("status")
        if not isinstance(raw_status, str):
            raise DomainRuleError("attribute correction requires a status")
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
            status = AttributeStatus(raw_status)
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
            default_value = attribute.value if attribute is not None else None
            changed_value = envelope.data.get("value", default_value)
            if not isinstance(changed_value, str):
                raise DomainRuleError("attribute value must be a string")
            validate_professional_claim(changed_value)
            evidence = Evidence(
                source_type=source,
                source_id=envelope.idempotency_key,
                description="Explicit human attribute correction.",
            )
            actor_kind = (
                ActorKind.HOMEOWNER if actor.role == Role.HOMEOWNER else ActorKind.DESIGNER
            )
            if attribute is None:
                target_element = envelope.data.get("targetElement")
                dimension = envelope.data.get("dimension")
                if not isinstance(target_element, str) or not target_element.strip():
                    raise DomainRuleError("new attribute requires targetElement")
                if not isinstance(dimension, str) or not dimension.strip():
                    raise DomainRuleError("new attribute requires dimension")
                changed = Attribute(
                    id=attribute_id,
                    target_element=target_element.strip(),
                    dimension=dimension.strip(),
                    value=changed_value,
                    status=status,
                    confidence=1.0,
                    actor=actor_kind,
                    evidence=[evidence],
                )
            else:
                changed = attribute.model_copy(
                    update={
                        "value": changed_value,
                        "status": status,
                        "confidence": 1.0,
                        "actor": actor_kind,
                        "evidence": [*attribute.evidence, evidence],
                    }
                )
            updated = apply_patch(
                state,
                StatePatch(
                    expected_state_version=state.state_version,
                    operations=[UpsertAttribute(attribute=changed)],
                ),
            )
            updated = updated.model_copy(
                update={
                    "completeness": calculate_completeness(updated),
                    "conflicts": reconcile_constraints(updated),
                }
            )
            updated = flag_brief_change(updated)
            response = self._response(updated)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
            return response

    def get_state(self, project_id: str, actor: ActorContext) -> ProjectState:
        self._authorize(project_id, actor)
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            return uow.projects.load(project_id)

    def next_question(self, project_id: str, actor: ActorContext) -> Question:
        state = self.get_state(project_id, actor)
        question = next(
            (
                item
                for item in state.questions
                if item.answer is None and not item.skipped and item.response is None
            ),
            None,
        )
        if question is None:
            raise KeyError("pending question not found")
        return question

    def answer_question(
        self,
        project_id: str,
        question_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        self._authorize(project_id, actor)
        if actor.role != Role.HOMEOWNER:
            raise AuthorizationError("actor cannot answer homeowner task")
        data = envelope.data
        has_note = isinstance(data.get("answer"), str) and bool(str(data["answer"]).strip())
        has_parts = isinstance(data.get("parts"), list) and bool(data["parts"])
        has_selection = isinstance(data.get("selection"), list) and bool(data["selection"])
        skipped = data.get("skipped") is True
        if not (has_note or has_parts or has_selection or skipped):
            raise ValueError("homeowner answer requires a note, parts, selection or skip")
        action = f"answer_question:{question_id}"
        request_hash = self._hash_request(
            action,
            project_id,
            actor,
            envelope,
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return WorkflowResponse.model_validate(replay.response_payload)
        pending = self.next_question(project_id, actor)
        if pending.id != question_id:
            raise KeyError(f"question {question_id} is not the pending question")
        return self.resume(
            project_id,
            actor,
            "homeowner",
            envelope,
            action=action,
        )

    def resolve_conflict(
        self,
        project_id: str,
        conflict_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        self._authorize(project_id, actor)
        request_hash = self._hash_request(
            "resolve_conflict",
            project_id,
            actor,
            envelope,
            extra={"conflictId": conflict_id},
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return WorkflowResponse.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            conflict = next((item for item in state.conflicts if item.id == conflict_id), None)
            if conflict is None:
                raise KeyError(f"conflict {conflict_id} not found")
            attempted = record_conflict_attempt(conflict)
            status = ConflictStatus(envelope.data.get("status", "resolved"))
            if status not in {ConflictStatus.RESOLVED, ConflictStatus.ACCEPTED_UNRESOLVED}:
                raise DomainRuleError("a human conflict resolution must close the conflict")
            resolution = envelope.data.get("resolution")
            if not isinstance(resolution, str) or not resolution.strip():
                raise DomainRuleError("conflict resolution text is required")
            validate_professional_claim(resolution)
            changed = attempted.model_copy(
                update={"status": status, "resolution": resolution.strip()}
            )
            updated = apply_patch(
                state,
                StatePatch(
                    expected_state_version=state.state_version,
                    operations=[UpsertConflict(conflict=changed)],
                ),
            )
            updated = flag_brief_change(updated)
            response = self._response(updated)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
            return response

    def create_constraint(
        self,
        project_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        self._authorize(project_id, actor)
        self._require_designer(actor)
        request_hash = self._hash_request("create_constraint", project_id, actor, envelope)
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return WorkflowResponse.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            constraint = self._compose_constraint(
                state, actor, envelope.data, constraint_id=str(uuid4()), existing=None
            )
            updated = self._apply_constraint_change(state, constraint)
            response = self._response(updated)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
            return response

    def update_constraint(
        self,
        project_id: str,
        constraint_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        self._authorize(project_id, actor)
        self._require_designer(actor)
        request_hash = self._hash_request(
            "update_constraint",
            project_id,
            actor,
            envelope,
            extra={"constraintId": constraint_id},
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return WorkflowResponse.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            existing = next((item for item in state.constraints if item.id == constraint_id), None)
            if existing is None:
                raise KeyError(f"constraint {constraint_id} not found")
            if existing.withdrawn:
                raise DomainRuleError("withdrawn constraints cannot be edited")
            constraint = self._compose_constraint(
                state, actor, envelope.data, constraint_id=constraint_id, existing=existing
            )
            updated = self._apply_constraint_change(state, constraint)
            response = self._response(updated)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
            return response

    def withdraw_constraint(
        self,
        project_id: str,
        constraint_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        self._authorize(project_id, actor)
        self._require_designer(actor)
        request_hash = self._hash_request(
            "withdraw_constraint",
            project_id,
            actor,
            envelope,
            extra={"constraintId": constraint_id},
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return WorkflowResponse.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            existing = next((item for item in state.constraints if item.id == constraint_id), None)
            if existing is None:
                raise KeyError(f"constraint {constraint_id} not found")
            updated = self._apply_constraint_change(
                state, existing.model_copy(update={"withdrawn": True})
            )
            response = self._response(updated)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
            return response

    def list_constraints(self, project_id: str, actor: ActorContext) -> list[Constraint]:
        return list(self.get_state(project_id, actor).constraints)

    def realign(
        self,
        project_id: str,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        """Regenerate the brief from the current state after a change invalidated it."""
        self._authorize(project_id, actor)
        request_hash = self._hash_request("realign", project_id, actor, envelope)
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return WorkflowResponse.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            if not can_draft_brief(state):
                updated = state.model_copy(
                    update={
                        "state_version": state.state_version + 1,
                        "status": ProjectStatus.ALIGNMENT,
                    }
                )
                response = self._response(updated)
                uow.projects.save(updated, expected_version=state.state_version)
                self._record_replay(uow, project_id, envelope, request_hash, response)
                uow.commit()
                return response
            brief = build_brief_version(state)
            self._validate_professional_content(brief.payload)
            self._validate_brief(brief.payload)
            updated = apply_patch(
                state,
                StatePatch(
                    expected_state_version=state.state_version,
                    operations=[UpsertBriefVersion(brief_version=brief)],
                ),
            ).model_copy(
                update={
                    "approvals": [],
                    "status": ProjectStatus.AWAITING_APPROVAL,
                    "brief_stale": False,
                }
            )
            response = self._response(updated)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
            return response

    @staticmethod
    def _require_designer(actor: ActorContext) -> None:
        if actor.role != Role.DESIGNER:
            raise AuthorizationError("only a designer can manage constraints")

    def _compose_constraint(
        self,
        state: ProjectState,
        actor: ActorContext,
        data: dict[str, object],
        *,
        constraint_id: str,
        existing: Constraint | None,
    ) -> Constraint:
        def value(key: str, fallback: object) -> object:
            return data.get(key, fallback)

        raw_category = value("category", existing.category.value if existing else None)
        if not isinstance(raw_category, str) or not raw_category.strip():
            raise DomainRuleError("constraint category is required")
        category = ConstraintCategory(raw_category.strip())

        raw_statement = value("statement", existing.statement if existing else "")
        if not isinstance(raw_statement, str) or not raw_statement.strip():
            raise DomainRuleError("constraint statement is required")
        statement = raw_statement.strip()
        validate_professional_claim(statement)

        raw_rationale = value("rationale", existing.rationale if existing else "")
        rationale = raw_rationale.strip() if isinstance(raw_rationale, str) else ""
        if rationale:
            validate_professional_claim(rationale)

        severity = ConstraintSeverity(
            str(value("severity", existing.severity.value if existing else "important"))
        )
        raw_applies_to = value("appliesTo", existing.applies_to if existing else "")
        applies_to = raw_applies_to.strip() if isinstance(raw_applies_to, str) else ""
        raw_attribute_id = value("attributeId", existing.attribute_id if existing else None)
        attribute_id = (
            raw_attribute_id.strip()
            if isinstance(raw_attribute_id, str) and raw_attribute_id.strip()
            else None
        )
        if attribute_id is not None and not any(
            item.id == attribute_id for item in state.attributes
        ):
            raise ValueError(f"linked preference attribute {attribute_id} not found")

        evidence = list(existing.evidence) if existing else []
        evidence.append(
            Evidence(
                source_type=EvidenceSource.DESIGNER_NOTE,
                source_id=constraint_id,
                description="Designer-entered constraint.",
            )
        )
        raw_incompatible = value(
            "incompatibleWith", existing.incompatible_with if existing else []
        )
        if isinstance(raw_incompatible, str):
            incompatible_with = [item.strip() for item in raw_incompatible.split(",") if item.strip()]
        elif isinstance(raw_incompatible, list):
            incompatible_with = [str(item).strip() for item in raw_incompatible if str(item).strip()]
        else:
            incompatible_with = []
        material_changed = existing is not None and any(
            (
                existing.statement != statement,
                existing.severity != severity,
                existing.applies_to != applies_to,
                existing.attribute_id != attribute_id,
                existing.incompatible_with != incompatible_with,
            )
        )
        revision = existing.revision + 1 if material_changed else (existing.revision if existing else 1)
        return Constraint(
            id=constraint_id,
            category=category,
            statement=statement,
            rationale=rationale,
            severity=severity,
            verification_status=(
                existing.verification_status
                if existing
                else ConstraintVerificationStatus.DESIGNER_ASSERTED
            ),
            owner=existing.owner if existing else ConstraintOwner.DESIGNER,
            evidence=evidence,
            verified_by=existing.verified_by if existing else None,
            applies_to=applies_to,
            attribute_id=attribute_id,
            proposed_by=existing.proposed_by if existing else actor.actor_id,
            withdrawn=False,
            revision=revision,
            incompatible_with=incompatible_with,
        )

    @staticmethod
    def _apply_constraint_change(state: ProjectState, constraint: Constraint) -> ProjectState:
        updated = apply_patch(
            state,
            StatePatch(
                expected_state_version=state.state_version,
                operations=[UpsertConstraint(constraint=constraint)],
            ),
        )
        updated = updated.model_copy(update={"conflicts": reconcile_constraints(updated)})
        return flag_brief_change(updated)

    def latest_brief(self, project_id: str, actor: ActorContext) -> BriefView:
        state = self.get_state(project_id, actor)
        if not state.brief_versions:
            raise KeyError("latest brief not found")
        latest = max(state.brief_versions, key=lambda item: item.version)
        return self._brief_view(state, latest)

    def edit_brief(
        self,
        project_id: str,
        version: int,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> BriefView:
        self._authorize(project_id, actor)
        request_hash = self._hash_request(
            "edit_brief",
            project_id,
            actor,
            envelope,
            extra={"version": version},
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return BriefView.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            latest = self._find_latest_brief(state)
            if latest.version != version:
                raise StaleStateError(
                    f"brief version {version} is stale; latest version is {latest.version}"
                )
            raw_payload = envelope.data.get("payload")
            if not isinstance(raw_payload, dict):
                raise BriefSchemaError("brief edit requires a payload object")
            client_payload = dict(raw_payload)
            project = client_payload.get("project")
            if isinstance(project, dict) and project.get("id") not in (None, project_id):
                raise BriefSchemaError("brief project id must match the route project")
            # System fields always come from authoritative state; only whitelisted
            # fields may be changed through the brief edit endpoint.
            payload = build_brief_payload(state)
            if "goals" in client_payload:
                goals = client_payload["goals"]
                if not isinstance(goals, list) or not all(
                    isinstance(item, str) for item in goals
                ):
                    raise BriefSchemaError("brief goals must be a list of strings")
                payload["goals"] = goals
            next_version = latest.version + 1
            payload["version"] = next_version
            payload["approvals"] = []
            payload.pop("contentHash", None)
            payload["project"] = {
                **payload["project"],
                "status": ProjectStatus.AWAITING_APPROVAL.value,
            }
            self._validate_professional_content(payload)
            self._validate_brief(payload)
            completeness = payload.get("completeness")
            if not isinstance(completeness, (int, float)):
                raise BriefSchemaError("brief completeness must be numeric")
            brief = BriefVersion(
                version=next_version,
                content_hash=calculate_brief_content_hash(payload),
                payload=payload,
                completeness=float(completeness),
            )
            if not can_draft_brief(state) or brief.completeness < 0.85:
                raise BriefReviewError(
                    "brief review requires at least 0.85 completeness and no critical conflict"
                )
            updated = apply_patch(
                state,
                StatePatch(
                    expected_state_version=state.state_version,
                    operations=[UpsertBriefVersion(brief_version=brief)],
                ),
            ).model_copy(
                update={
                    "approvals": [],
                    "status": ProjectStatus.AWAITING_APPROVAL,
                    "brief_stale": False,
                }
            )
            response = self._brief_view(updated, brief)
            uow.projects.save(updated, expected_version=state.state_version)
            self._record_replay(uow, project_id, envelope, request_hash, response)
            uow.commit()
            return response

    def approve_brief(
        self,
        project_id: str,
        version: int,
        actor: ActorContext,
        envelope: WriteEnvelope[dict[str, object]],
    ) -> WorkflowResponse:
        self._authorize(project_id, actor)
        request_hash = self._hash_request(
            "approve_brief",
            project_id,
            actor,
            envelope,
            extra={"version": version},
        )
        with SqlAlchemyUnitOfWork(self._session_factory) as uow:
            replay = uow.idempotency.lookup(project_id, envelope.idempotency_key, request_hash)
            if replay is not None:
                return WorkflowResponse.model_validate(replay.response_payload)
            state = uow.projects.load(project_id)
            self._check_version(state, envelope.expected_state_version)
            brief = self._find_latest_brief(state)
            if brief.version != version:
                raise StaleStateError(
                    f"brief version {version} is stale; latest version is {brief.version}"
                )
            if state.brief_stale:
                raise ApprovalNotAllowedError(
                    "brief is outdated; regenerate it before approving"
                )
            submitted_hash = envelope.data.get("contentHash")
            if submitted_hash != brief.content_hash:
                raise BriefHashMismatchError("submitted hash does not match the stored brief")
            if not can_draft_brief(state) or brief.completeness < 0.85:
                raise ApprovalNotAllowedError(
                    "brief approval requires complete state and no open critical conflict"
                )
            approval = Approval(
                role=actor.role,
                actor_id=actor.actor_id,
                brief_version=brief.version,
                content_hash=brief.content_hash,
            )
            state_without_actor_approval = state.model_copy(
                update={
                    "approvals": [item for item in state.approvals if item.role != actor.role]
                }
            )
            updated = apply_patch(
                state_without_actor_approval,
                StatePatch(
                    expected_state_version=state.state_version,
                    operations=[UpsertApproval(approval=approval)],
                ),
            )
            status = (
                ProjectStatus.APPROVED
                if can_approve(updated, brief)
                else ProjectStatus.AWAITING_APPROVAL
            )
            updated = updated.model_copy(update={"status": status})
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
                    "assets": self._active_assets(project_id),
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

    def _active_assets(self, project_id: str) -> list[dict[str, object]]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ImageAssetRow)
                .where(
                    ImageAssetRow.project_id == project_id,
                    ImageAssetRow.deleted_at.is_(None),
                )
                .order_by(ImageAssetRow.id)
            ).all()
            return [
                {
                    "id": row.id,
                    "media_type": row.payload.get("media_type", "image/unknown"),
                    "sha256": row.payload.get("sha256", ""),
                }
                for row in rows
            ]

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
    def _find_latest_brief(state: ProjectState) -> BriefVersion:
        if not state.brief_versions:
            raise KeyError("latest brief not found")
        return max(state.brief_versions, key=lambda item: item.version)

    @staticmethod
    def _brief_view(state: ProjectState, brief: BriefVersion) -> BriefView:
        approvals = [
            item
            for item in state.approvals
            if item.brief_version == brief.version and item.content_hash == brief.content_hash
        ]
        return BriefView(
            version=brief.version,
            content_hash=brief.content_hash,
            payload=brief.payload,
            completeness=brief.completeness,
            approvals=approvals,
            state_version=state.state_version,
        )

    def _validate_brief(self, payload: dict[str, object]) -> None:
        errors = sorted(self._brief_validator.iter_errors(payload), key=lambda item: list(item.path))
        if errors:
            first = errors[0]
            path = ".".join(str(item) for item in first.path) or "$"
            raise BriefSchemaError(f"brief schema error at {path}: {first.message}")

    @classmethod
    def _validate_professional_content(cls, value: object) -> None:
        if isinstance(value, str):
            validate_professional_claim(value)
        elif isinstance(value, dict):
            for item in value.values():
                cls._validate_professional_content(item)
        elif isinstance(value, list):
            for item in value:
                cls._validate_professional_content(item)

    @staticmethod
    def _record_replay(
        uow: SqlAlchemyUnitOfWork,
        project_id: str,
        envelope: WriteEnvelope[dict[str, object]],
        request_hash: str,
        response: DomainModel,
    ) -> None:
        uow.idempotency.record(
            project_id=project_id,
            key=envelope.idempotency_key,
            request_hash=request_hash,
            response_payload=response.model_dump(mode="json", by_alias=True),
            resulting_version=getattr(response, "state_version", envelope.expected_state_version + 1),
        )
