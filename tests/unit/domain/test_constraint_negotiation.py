from alignspace.domain.constraints import (
    build_derived_conflict,
    constraint_needs_conflict,
    derived_conflict_id,
    invalidate_approvals,
    reconcile_constraint_conflict,
)
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
    Conflict,
    Constraint,
    Evidence,
    ProjectState,
)


def attribute(
    attribute_id: str = "manual-material",
    value: str = "natural stone",
    status: AttributeStatus = AttributeStatus.CONFIRMED,
) -> Attribute:
    return Attribute(
        id=attribute_id,
        target_element="worktop",
        dimension="material",
        value=value,
        status=status,
        confidence=1,
        actor=ActorKind.HOMEOWNER,
        evidence=[],
    )


def constraint(**overrides) -> Constraint:
    base = {
        "id": "c1",
        "category": ConstraintCategory.BUDGET,
        "statement": "天然石材超出当前预算档位",
        "rationale": "改用石材效果饰面",
        "severity": ConstraintSeverity.IMPORTANT,
        "verification_status": ConstraintVerificationStatus.DESIGNER_ASSERTED,
        "owner": ConstraintOwner.DESIGNER,
        "evidence": [
            Evidence(
                source_type=EvidenceSource.DESIGNER_NOTE,
                source_id="note-1",
                description="designer input",
            )
        ],
        "attribute_id": "manual-material",
        "proposed_by": "designer-1",
    }
    base.update(overrides)
    return Constraint(**base)


def project(**overrides) -> ProjectState:
    base = {"project_id": "p1", "attributes": [attribute()]}
    base.update(overrides)
    return ProjectState(**base)


def test_important_constraint_on_confirmed_preference_derives_a_conflict():
    state = project()
    item = constraint()
    assert constraint_needs_conflict(state, item) is True
    conflict = build_derived_conflict(item, "natural stone")
    assert conflict.id == derived_conflict_id("c1")
    assert conflict.constraint_id == "c1"
    assert conflict.status == ConflictStatus.OPEN
    assert conflict.severity == ConstraintSeverity.IMPORTANT


def test_unlinked_advisory_withdrawn_or_unconfirmed_do_not_derive():
    state = project()
    assert constraint_needs_conflict(state, constraint(severity=ConstraintSeverity.ADVISORY)) is False
    assert constraint_needs_conflict(state, constraint(attribute_id=None)) is False
    assert constraint_needs_conflict(state, constraint(withdrawn=True)) is False
    unresolved = project(attributes=[attribute(status=AttributeStatus.UNRESOLVED)])
    assert constraint_needs_conflict(unresolved, constraint()) is False
    assert constraint_needs_conflict(project(attributes=[]), constraint()) is False


def test_reconcile_adds_then_refreshes_an_open_derived_conflict():
    state = project()
    item = constraint()
    once = reconcile_constraint_conflict(state, item)
    assert [c.id for c in once] == [derived_conflict_id("c1")]

    refreshed = reconcile_constraint_conflict(
        state.model_copy(update={"conflicts": once}),
        constraint(statement="更新后的预算约束"),
    )
    assert len(refreshed) == 1
    assert refreshed[0].summary == "更新后的预算约束"


def test_reconcile_removes_open_derived_conflict_when_cause_goes_away():
    state = project()
    existing = [build_derived_conflict(constraint(), "natural stone")]
    with_conflict = state.model_copy(update={"conflicts": existing})
    assert reconcile_constraint_conflict(with_conflict, constraint(withdrawn=True)) == []
    assert reconcile_constraint_conflict(with_conflict, constraint(attribute_id=None)) == []


def test_reconcile_preserves_a_human_resolved_conflict():
    resolved = Conflict(
        id=derived_conflict_id("c1"),
        type="preference_vs_constraint",
        summary="已解决",
        impact="done",
        status=ConflictStatus.RESOLVED,
        severity=ConstraintSeverity.IMPORTANT,
        resolution_attempts=1,
        constraint_id="c1",
    )
    state = project(conflicts=[resolved])
    assert reconcile_constraint_conflict(state, constraint(withdrawn=True)) == [resolved]
    assert reconcile_constraint_conflict(state, constraint()) == [resolved]


def test_invalidate_approvals_clears_and_returns_to_alignment():
    approval = Approval(
        role=Role.HOMEOWNER,
        actor_id="homeowner-1",
        brief_version=1,
        content_hash="a" * 64,
    )
    approved = project(approvals=[approval], status=ProjectStatus.APPROVED)
    updated = invalidate_approvals(approved)
    assert updated.approvals == []
    assert updated.status == ProjectStatus.ALIGNMENT

    untouched = project(approvals=[])
    assert invalidate_approvals(untouched) is untouched
