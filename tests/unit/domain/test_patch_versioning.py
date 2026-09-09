import pytest
from pydantic import TypeAdapter, ValidationError

from alignspace.domain.enums import ConflictStatus, ConflictType, ConstraintSeverity, Role
from alignspace.domain.models import (
    Approval,
    Conflict,
    ProjectState,
    Question,
    calculate_brief_content_hash,
)
from alignspace.domain.patches import (
    PatchOperation,
    StatePatch,
    UpsertConflict,
    UpsertQuestion,
    apply_patch,
)
from alignspace.domain.policies import DomainRuleError, StaleStateError


def test_stale_patch_is_rejected() -> None:
    state = ProjectState(project_id="project-1", state_version=4)
    patch = StatePatch(expected_state_version=3, operations=[])
    with pytest.raises(StaleStateError, match="expected version 3, current version 4"):
        apply_patch(state, patch)


def test_discriminated_conflict_operation_updates_state_immutably() -> None:
    conflict = Conflict(
        id="c-1",
        type=ConflictType.PREFERENCE_VS_CONSTRAINT,
        summary="Material exceeds budget",
        impact="A lower-cost alternative is required",
        status=ConflictStatus.OPEN,
        severity=ConstraintSeverity.IMPORTANT,
    )
    operation = TypeAdapter(PatchOperation).validate_python(
        {"op": "upsert_conflict", "conflict": conflict.model_dump()}
    )
    state = ProjectState(project_id="project-1")

    updated = apply_patch(
        state,
        StatePatch(expected_state_version=0, operations=[operation]),
    )

    assert isinstance(operation, UpsertConflict)
    assert state.conflicts == []
    assert updated.conflicts == [conflict]
    assert updated.state_version == 1


def test_question_patch_rejects_eleventh_distinct_homeowner_question() -> None:
    state = ProjectState(
        project_id="project-1",
        questions=[
            Question(id=f"q-{index}", target_role=Role.HOMEOWNER, text=f"Question {index}")
            for index in range(10)
        ],
    )
    patch = StatePatch(
        expected_state_version=0,
        operations=[
            UpsertQuestion(
                question=Question(id="q-10", target_role=Role.HOMEOWNER, text="Question 10")
            )
        ],
    )

    with pytest.raises(DomainRuleError, match="homeowner question budget exhausted"):
        apply_patch(state, patch)


def test_patch_rejects_conflict_with_more_than_two_resolution_attempts() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 2"):
        StatePatch(
            expected_state_version=0,
            operations=[
                {
                    "op": "upsert_conflict",
                    "conflict": {
                        "id": "c-1",
                        "type": "preference_vs_constraint",
                        "summary": "Material exceeds budget",
                        "impact": "A lower-cost alternative is required",
                        "status": "open",
                        "severity": "important",
                        "resolution_attempts": 3,
                    },
                }
            ],
        )


def test_conflict_patch_cannot_reset_exhausted_resolution_attempts() -> None:
    exhausted_conflict = Conflict(
        id="c-1",
        type=ConflictType.PREFERENCE_VS_CONSTRAINT,
        summary="Material exceeds budget",
        impact="A lower-cost alternative is required",
        status=ConflictStatus.ESCALATED,
        severity=ConstraintSeverity.IMPORTANT,
        resolution_attempts=2,
    )
    state = ProjectState(project_id="project-1", conflicts=[exhausted_conflict])
    reset_attempt = exhausted_conflict.model_copy(update={"resolution_attempts": 0})
    patch = StatePatch(
        expected_state_version=0,
        operations=[UpsertConflict(conflict=reset_attempt)],
    )

    with pytest.raises(
        DomainRuleError,
        match="conflict resolution attempts cannot decrease",
    ):
        apply_patch(state, patch)

    assert state.conflicts == [exhausted_conflict]
    assert state.state_version == 0


def test_patch_rejects_an_impossible_future_operation_explicitly() -> None:
    class FutureOperation:
        approval = Approval(
            role=Role.HOMEOWNER,
            actor_id="h-1",
            brief_version=2,
            content_hash=calculate_brief_content_hash({"style": "warm modern"}),
        )

    patch = StatePatch.model_construct(expected_state_version=0, operations=[FutureOperation()])

    with pytest.raises(TypeError, match="unsupported patch operation"):
        apply_patch(ProjectState(project_id="project-1"), patch)
