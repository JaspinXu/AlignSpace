import pytest
from pydantic import TypeAdapter

from alignspace.domain.enums import ConflictStatus, ConstraintSeverity
from alignspace.domain.models import Conflict, ProjectState
from alignspace.domain.patches import PatchOperation, StatePatch, UpsertConflict, apply_patch
from alignspace.domain.policies import StaleStateError


def test_stale_patch_is_rejected() -> None:
    state = ProjectState(project_id="project-1", state_version=4)
    patch = StatePatch(expected_state_version=3, operations=[])
    with pytest.raises(StaleStateError, match="expected version 3, current version 4"):
        apply_patch(state, patch)


def test_discriminated_conflict_operation_updates_state_immutably() -> None:
    conflict = Conflict(
        id="c-1",
        type="preference_vs_constraint",
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
