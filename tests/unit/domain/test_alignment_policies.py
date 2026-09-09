from uuid import uuid4

import pytest
from pydantic import ValidationError

from alignspace.domain.enums import (
    ActorKind,
    AttributeStatus,
    ConflictStatus,
    ConflictType,
    ConstraintSeverity,
    EvidenceSource,
    Role,
)
from alignspace.domain.models import Attribute, Conflict, Evidence, ProjectState, Question
from alignspace.domain.policies import (
    DomainRuleError,
    add_question,
    calculate_completeness,
    can_draft_brief,
    record_conflict_attempt,
)


def test_eleventh_homeowner_question_is_rejected() -> None:
    state = ProjectState(
        project_id="project-1",
        questions=[
            Question(id=f"q-{index}", target_role=Role.HOMEOWNER, text=f"Question {index}")
            for index in range(10)
        ],
    )

    with pytest.raises(DomainRuleError, match="homeowner question budget exhausted"):
        add_question(
            state,
            Question(id="q-10", target_role=Role.HOMEOWNER, text="Question 10"),
        )


def test_brief_requires_canonical_state_completeness_threshold() -> None:
    state = ProjectState(project_id="project-1", completeness=0.84)

    assert can_draft_brief(state) is False


def test_completeness_uses_required_dimensions_without_materialising_missing_rows() -> None:
    attributes = [
        Attribute(
            id=str(uuid4()),
            target_element="room",
            dimension=dimension,
            value=f"decided {dimension}",
            status=AttributeStatus.CONFIRMED,
            confidence=1,
            evidence=[
                Evidence(
                    source_type=EvidenceSource.HOMEOWNER_ANSWER,
                    source_id=f"answer-{dimension}",
                    description="Explicit decision",
                )
            ],
            actor=ActorKind.HOMEOWNER,
        )
        for dimension in ["style", "colour", "material", "lighting"]
    ]
    state = ProjectState(project_id="project-1", attributes=attributes)

    assert calculate_completeness(state) == 0.5
    assert len(state.attributes) == 4


def test_second_unsuccessful_conflict_attempt_escalates_immutably() -> None:
    conflict = Conflict(
        id="c-1",
        type=ConflictType.PREFERENCE_VS_CONSTRAINT,
        summary="Material exceeds budget",
        impact="A lower-cost alternative is required",
        status=ConflictStatus.OPEN,
        severity=ConstraintSeverity.IMPORTANT,
        resolution_attempts=1,
    )

    updated = record_conflict_attempt(conflict)

    assert conflict.resolution_attempts == 1
    assert updated.resolution_attempts == 2
    assert updated.status == ConflictStatus.ESCALATED


def test_third_conflict_resolution_attempt_is_rejected() -> None:
    conflict = Conflict(
        id="c-1",
        type=ConflictType.PREFERENCE_VS_CONSTRAINT,
        summary="Material exceeds budget",
        impact="A lower-cost alternative is required",
        status=ConflictStatus.ESCALATED,
        severity=ConstraintSeverity.IMPORTANT,
        resolution_attempts=2,
    )

    with pytest.raises(DomainRuleError, match="conflict resolution budget exhausted"):
        record_conflict_attempt(conflict)


def test_conflict_model_rejects_more_than_two_resolution_attempts() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 2"):
        Conflict(
            id="c-1",
            type=ConflictType.PREFERENCE_VS_CONSTRAINT,
            summary="Material exceeds budget",
            impact="A lower-cost alternative is required",
            status=ConflictStatus.OPEN,
            severity=ConstraintSeverity.IMPORTANT,
            resolution_attempts=3,
        )


def test_conflict_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        Conflict(
            id="c-1",
            type="unknown_conflict",
            summary="Unrecognised conflict",
            impact="Cannot route resolution",
            status=ConflictStatus.OPEN,
            severity=ConstraintSeverity.IMPORTANT,
        )
