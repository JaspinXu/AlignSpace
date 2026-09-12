from typing import TypedDict


class WorkflowState(TypedDict, total=False):
    project_id: str
    project_state: dict[str, object]
    assets: list[dict[str, object]]
    next_action: str
    pending_question: dict[str, object]
    review_decision: str
