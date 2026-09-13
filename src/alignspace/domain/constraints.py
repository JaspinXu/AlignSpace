"""Rule-based constraint conflict derivation and approval invalidation.

The rules here only compare structure the system can actually see: whether a
constraint links to a preference that the homeowner has confirmed, and how
severe the designer states the constraint to be. They never estimate cost or
feasibility; that judgement comes from the designer's own input.
"""

from alignspace.domain.enums import (
    AttributeStatus,
    ConflictStatus,
    ConflictType,
    ConstraintSeverity,
    ProjectStatus,
)
from alignspace.domain.models import Attribute, Conflict, Constraint, ProjectState

DERIVED_CONFLICT_PREFIX = "constraint-conflict-"


def derived_conflict_id(constraint_id: str) -> str:
    return f"{DERIVED_CONFLICT_PREFIX}{constraint_id}"


def _linked_attribute(state: ProjectState, constraint: Constraint) -> Attribute | None:
    if not constraint.attribute_id:
        return None
    return next((item for item in state.attributes if item.id == constraint.attribute_id), None)


def constraint_needs_conflict(state: ProjectState, constraint: Constraint) -> bool:
    """A designer-asserted important/critical constraint that bears on a confirmed
    preference is an explicit, structured clash that needs a human decision."""
    if constraint.withdrawn or constraint.severity == ConstraintSeverity.ADVISORY:
        return False
    attribute = _linked_attribute(state, constraint)
    return attribute is not None and attribute.status == AttributeStatus.CONFIRMED


def build_derived_conflict(constraint: Constraint, attribute_value: str) -> Conflict:
    return Conflict(
        id=derived_conflict_id(constraint.id),
        type=ConflictType.PREFERENCE_VS_CONSTRAINT,
        summary=constraint.statement,
        impact=f"与已确认偏好「{attribute_value}」冲突，需要屋主或设计师决定。",
        status=ConflictStatus.OPEN,
        severity=constraint.severity,
        constraint_id=constraint.id,
    )


def reconcile_constraint_conflict(state: ProjectState, constraint: Constraint) -> list[Conflict]:
    """Return the project's conflicts after applying one constraint's derived conflict.

    A conflict that a human already resolved or accepted stays untouched. An open
    derived conflict is refreshed while the clash still holds and removed once the
    constraint no longer implies it (unlinked, downgraded or withdrawn) — removal of
    a derived artefact is not the same as marking an unresolved conflict resolved.
    """
    conflict_id = derived_conflict_id(constraint.id)
    existing = next((item for item in state.conflicts if item.id == conflict_id), None)
    if existing is not None and existing.status != ConflictStatus.OPEN:
        return list(state.conflicts)
    remaining = [item for item in state.conflicts if item.id != conflict_id]
    if constraint_needs_conflict(state, constraint):
        attribute = _linked_attribute(state, constraint)
        assert attribute is not None
        remaining.append(build_derived_conflict(constraint, attribute.value))
    return remaining


def invalidate_approvals(state: ProjectState) -> ProjectState:
    """Clear stale approvals after a change that affects the design brief."""
    if not state.approvals:
        return state
    return state.model_copy(update={"approvals": [], "status": ProjectStatus.ALIGNMENT})
