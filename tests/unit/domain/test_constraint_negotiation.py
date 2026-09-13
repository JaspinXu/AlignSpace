from alignspace.domain.constraints import (
    build_derived_conflict,
    conflicting_value,
    derived_conflict_id,
    flag_brief_change,
    invalidate_approvals,
    reconcile_constraints,
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
    BriefVersion,
    Conflict,
    Constraint,
    Evidence,
    ProjectState,
    calculate_brief_content_hash,
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
        "revision": 1,
        "incompatible_with": ["natural stone"],
    }
    base.update(overrides)
    return Constraint(**base)


def project(**overrides) -> ProjectState:
    base = {"project_id": "p1", "attributes": [attribute()]}
    base.update(overrides)
    return ProjectState(**base)


def test_linking_alone_is_not_a_conflict():
    assert conflicting_value(project(), constraint(incompatible_with=[])) is None
    assert conflicting_value(project(), constraint()) == "natural stone"
    assert conflicting_value(project(), constraint(withdrawn=True)) is None
    unresolved = project(attributes=[attribute(status=AttributeStatus.UNRESOLVED)])
    assert conflicting_value(unresolved, constraint()) is None
    assert conflicting_value(project(), constraint(attribute_id=None)) is None
    assert conflicting_value(project(), constraint(incompatible_with=["pale oak"])) is None


def test_derived_conflict_carries_revision_and_constraint():
    conflict = build_derived_conflict(constraint(), "natural stone")
    assert conflict.id == derived_conflict_id("c1", 1)
    assert conflict.constraint_id == "c1"
    assert conflict.status == ConflictStatus.OPEN
    assert conflict.severity == ConstraintSeverity.IMPORTANT


def test_reconcile_adds_one_open_conflict_per_revision():
    state = project(constraints=[constraint()])
    conflicts = reconcile_constraints(state)
    assert [c.id for c in conflicts] == [derived_conflict_id("c1", 1)]

    revised = state.model_copy(update={"constraints": [constraint(revision=2)]})
    refreshed = reconcile_constraints(revised)
    assert [c.id for c in refreshed] == [derived_conflict_id("c1", 2)]


def test_reconcile_keeps_resolved_history_and_opens_a_new_revision_conflict():
    resolved = Conflict(
        id=derived_conflict_id("c1", 1),
        type="preference_vs_constraint",
        summary="旧结论",
        impact="done",
        status=ConflictStatus.RESOLVED,
        severity=ConstraintSeverity.IMPORTANT,
        resolution_attempts=1,
        constraint_id="c1",
    )
    state = project(constraints=[constraint(revision=2)], conflicts=[resolved])
    conflicts = reconcile_constraints(state)
    ids = {c.id for c in conflicts}
    assert derived_conflict_id("c1", 1) in ids  # history kept
    assert derived_conflict_id("c1", 2) in ids  # new pending conflict
    assert next(c for c in conflicts if c.id == derived_conflict_id("c1", 2)).status == "open"


def test_reconcile_drops_open_conflict_when_cause_goes_away():
    existing = [build_derived_conflict(constraint(), "natural stone")]
    state = project(constraints=[constraint(withdrawn=True)], conflicts=existing)
    assert reconcile_constraints(state) == []
    rejected = project(
        attributes=[attribute(status=AttributeStatus.REJECTED)],
        constraints=[constraint()],
        conflicts=existing,
    )
    assert reconcile_constraints(rejected) == []


def test_flag_brief_change_clears_approvals_and_marks_brief_stale():
    approval = Approval(
        role=Role.HOMEOWNER, actor_id="homeowner-1", brief_version=1, content_hash="a" * 64
    )
    brief = BriefVersion(
        version=1,
        content_hash=calculate_brief_content_hash({}),
        payload={},
        completeness=0.875,
    )
    state = project(
        approvals=[approval],
        brief_versions=[brief],
        status=ProjectStatus.APPROVED,
    )
    updated = flag_brief_change(state)
    assert updated.approvals == []
    assert updated.brief_stale is True
    assert updated.status == ProjectStatus.ALIGNMENT

    untouched = project(approvals=[])
    assert flag_brief_change(untouched) is untouched
    assert invalidate_approvals(untouched) is untouched
