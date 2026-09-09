from alignspace.agents.contracts import AgentResult
from alignspace.domain.enums import (
    AttributeStatus,
    ConflictStatus,
    ConstraintSeverity,
    NextAction,
    Role,
)
from alignspace.domain.models import ProjectState
from alignspace.domain.policies import can_draft_brief


class AlignmentAgent:
    def run(self, state: ProjectState) -> AgentResult:
        if any(attribute.status == AttributeStatus.PROPOSED for attribute in state.attributes):
            action = NextAction.ASK_HOMEOWNER
        elif any(
            conflict.status == ConflictStatus.OPEN
            and conflict.severity == ConstraintSeverity.CRITICAL
            for conflict in state.conflicts
        ):
            action = NextAction.REQUEST_PROFESSIONAL_REVIEW
        elif not state.constraints:
            action = NextAction.ASK_DESIGNER
        elif can_draft_brief(state):
            action = NextAction.DRAFT_BRIEF
        elif sum(question.target_role == Role.HOMEOWNER for question in state.questions) < 10:
            action = NextAction.ASK_HOMEOWNER
        else:
            action = NextAction.STOP_UNRESOLVED
        return AgentResult(state=state, next_action=action)
