import pytest

from alignspace.domain.models import ProjectState
from alignspace.domain.patches import StatePatch, apply_patch
from alignspace.domain.policies import StaleStateError


def test_stale_patch_is_rejected() -> None:
    state = ProjectState(project_id="project-1", state_version=4)
    patch = StatePatch(expected_state_version=3, operations=[])
    with pytest.raises(StaleStateError, match="expected version 3, current version 4"):
        apply_patch(state, patch)
