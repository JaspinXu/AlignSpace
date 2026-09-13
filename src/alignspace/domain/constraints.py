"""Rule-based constraint conflict derivation, brief staleness and approval invalidation.

The conflict rule compares structure the system can actually see: a constraint links to a
preference AND the designer explicitly lists the preference value it rules out
(``incompatible_with``). Linking alone is never treated as a contradiction, and the system
never estimates cost or feasibility itself.
"""

from alignspace.domain.enums import (
    AttributeStatus,
    ConflictStatus,
    ConflictType,
    ProjectStatus,
)
from alignspace.domain.models import Attribute, Conflict, Constraint, ProjectState

DERIVED_CONFLICT_PREFIX = "constraint-conflict-"


def derived_conflict_id(constraint_id: str, revision: int) -> str:
    return f"{DERIVED_CONFLICT_PREFIX}{constraint_id}-r{revision}"


def _linked_attribute(state: ProjectState, constraint: Constraint) -> Attribute | None:
    if not constraint.attribute_id:
        return None
    return next((item for item in state.attributes if item.id == constraint.attribute_id), None)


def conflicting_value(state: ProjectState, constraint: Constraint) -> str | None:
    """Return the confirmed preference value this constraint explicitly rules out, if any."""
    if constraint.withdrawn:
        return None
    attribute = _linked_attribute(state, constraint)
    if attribute is None or attribute.status != AttributeStatus.CONFIRMED:
        return None
    excluded = {value.strip().casefold() for value in constraint.incompatible_with if value.strip()}
    if attribute.value.strip().casefold() in excluded:
        return attribute.value
    return None


def build_derived_conflict(constraint: Constraint, attribute_value: str) -> Conflict:
    return Conflict(
        id=derived_conflict_id(constraint.id, constraint.revision),
        type=ConflictType.PREFERENCE_VS_CONSTRAINT,
        summary=constraint.statement,
        impact=f"与已确认偏好「{attribute_value}」冲突，需要屋主或设计师决定。",
        status=ConflictStatus.OPEN,
        severity=constraint.severity,
        constraint_id=constraint.id,
    )


def reconcile_constraints(state: ProjectState) -> list[Conflict]:
    """Recompute every constraint-derived conflict from the current attributes and constraints.

    Human decisions (resolved / accepted_unresolved) are kept as history for every revision.
    Open derived conflicts are superseded: a constraint gets at most one open conflict, for its
    current revision, and only when it explicitly rules out a confirmed preference value.
    """
    kept = [
        conflict
        for conflict in state.conflicts
        if conflict.constraint_id is None or conflict.status != ConflictStatus.OPEN
    ]
    for constraint in state.constraints:
        current_id = derived_conflict_id(constraint.id, constraint.revision)
        if any(conflict.id == current_id for conflict in kept):
            continue
        value = conflicting_value(state, constraint)
        if value is not None:
            kept.append(build_derived_conflict(constraint, value))
    return kept


def invalidate_approvals(state: ProjectState) -> ProjectState:
    if not state.approvals:
        return state
    return state.model_copy(update={"approvals": [], "status": ProjectStatus.ALIGNMENT})


def flag_brief_change(state: ProjectState) -> ProjectState:
    """A change that affects the brief clears stale approvals and marks the brief outdated."""
    updates: dict[str, object] = {}
    if state.approvals:
        updates["approvals"] = []
    if state.brief_versions:
        updates["brief_stale"] = True
        updates["status"] = ProjectStatus.ALIGNMENT
    return state.model_copy(update=updates) if updates else state
