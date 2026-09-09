from alignspace.agents.contracts import AgentResult
from alignspace.domain.enums import NextAction
from alignspace.domain.models import Constraint, ProjectState
from alignspace.domain.patches import StatePatch, UpsertConstraint, apply_patch


class DesignerAgent:
    def __init__(self, fixture_constraints: list[Constraint] | None = None) -> None:
        self._fixture_constraints = list(fixture_constraints or [])

    def run(self, state: ProjectState) -> AgentResult:
        existing_ids = {constraint.id for constraint in state.constraints}
        operations = [
            UpsertConstraint(constraint=constraint)
            for constraint in self._fixture_constraints
            if constraint.id not in existing_ids
        ]
        if not operations:
            return AgentResult(state=state, next_action=NextAction.ASK_DESIGNER)
        updated = apply_patch(
            state,
            StatePatch(expected_state_version=state.state_version, operations=operations),
        )
        return AgentResult(state=updated, patches=operations)
