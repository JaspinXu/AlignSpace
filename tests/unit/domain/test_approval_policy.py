from alignspace.domain.enums import ConflictStatus, ConstraintSeverity, Role
from alignspace.domain.models import Approval, BriefVersion, Conflict, ProjectState
from alignspace.domain.policies import can_approve


def matching_approvals() -> list[Approval]:
    return [
        Approval(role=Role.HOMEOWNER, actor_id="h-1", brief_version=2, content_hash="abc"),
        Approval(role=Role.DESIGNER, actor_id="d-1", brief_version=2, content_hash="abc"),
    ]


def test_same_version_and_hash_from_both_roles_is_required() -> None:
    brief = BriefVersion(version=2, content_hash="abc", payload={}, completeness=0.9)
    state = ProjectState(
        project_id="project-1",
        completeness=0.9,
        approvals=matching_approvals(),
    )

    assert can_approve(state, brief) is True


def test_brief_completeness_below_threshold_blocks_approval() -> None:
    brief = BriefVersion(version=2, content_hash="abc", payload={}, completeness=0.84)
    state = ProjectState(
        project_id="project-1",
        completeness=0.9,
        approvals=matching_approvals(),
    )

    assert can_approve(state, brief) is False


def test_open_critical_conflict_blocks_approval() -> None:
    brief = BriefVersion(version=2, content_hash="abc", payload={}, completeness=0.9)
    state = ProjectState(
        project_id="project-1",
        completeness=0.9,
        approvals=matching_approvals(),
        conflicts=[
            Conflict(
                id="c-1",
                type="preference_vs_constraint",
                summary="Unsafe wall change",
                impact="Professional review required",
                status=ConflictStatus.OPEN,
                severity=ConstraintSeverity.CRITICAL,
            )
        ],
    )

    assert can_approve(state, brief) is False
