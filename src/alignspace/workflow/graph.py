import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from alignspace.agents.contracts import AgentBundle
from alignspace.domain.enums import NextAction, ProjectStatus, ReviewDecision
from alignspace.domain.models import BriefVersion, ProjectState, calculate_brief_content_hash
from alignspace.domain.patches import StatePatch, UpsertBriefVersion, UpsertQuestion, apply_patch
from alignspace.workflow.state import WorkflowState


def _project_state(workflow_state: WorkflowState) -> ProjectState:
    stored = workflow_state.get("project_state")
    if stored is not None:
        return ProjectState.model_validate(stored)
    return ProjectState(project_id=workflow_state["project_id"])


def _dump(state: ProjectState) -> dict[str, object]:
    return state.model_dump(mode="json", by_alias=True)


def build_graph(agents: AgentBundle, checkpointer: object):
    builder = StateGraph(WorkflowState)

    def vision_analysis(workflow_state: WorkflowState) -> WorkflowState:
        result = agents.vision.run(_project_state(workflow_state))
        return {"project_state": _dump(result.state)}

    def homeowner_interview(workflow_state: WorkflowState) -> WorkflowState:
        result = agents.homeowner.run(_project_state(workflow_state))
        update: WorkflowState = {
            "project_state": _dump(result.state),
            "next_action": (result.next_action or NextAction.ASK_HOMEOWNER).value,
        }
        if result.patches:
            update["pending_question"] = result.patches[-1].question.model_dump(
                mode="json", by_alias=True
            )
        return update

    def wait_homeowner(workflow_state: WorkflowState) -> WorkflowState:
        pending = workflow_state["pending_question"]
        response = interrupt(
            {
                "waitReason": "homeowner",
                "pendingQuestion": pending,
            }
        )
        answer = response.get("answer") if isinstance(response, dict) else str(response)
        if not isinstance(answer, str) or not answer.strip():
            return {"next_action": NextAction.ASK_HOMEOWNER.value}
        state = _project_state(workflow_state)
        question = next(item for item in state.questions if item.id == pending["id"])
        operation = UpsertQuestion(question=question.model_copy(update={"answer": answer.strip()}))
        updated = apply_patch(
            state,
            StatePatch(expected_state_version=state.state_version, operations=[operation]),
        )
        return {"project_state": _dump(updated), "pending_question": {}}

    def designer_review(workflow_state: WorkflowState) -> WorkflowState:
        result = agents.designer.run(_project_state(workflow_state))
        return {
            "project_state": _dump(result.state),
            "next_action": (
                NextAction.ASK_DESIGNER.value if not result.patches else "alignment"
            ),
        }

    def wait_designer(workflow_state: WorkflowState) -> WorkflowState:
        response = interrupt(
            {
                "waitReason": "designer",
                "projectId": workflow_state["project_id"],
            }
        )
        return {"next_action": "alignment", "pending_question": response or {}}

    def alignment(workflow_state: WorkflowState) -> WorkflowState:
        result = agents.alignment.run(_project_state(workflow_state))
        return {"next_action": result.next_action.value if result.next_action else "stop_unresolved"}

    def wait_professional(workflow_state: WorkflowState) -> WorkflowState:
        response = interrupt(
            {
                "waitReason": "professional",
                "projectId": workflow_state["project_id"],
            }
        )
        return {"next_action": "stop_unresolved", "pending_question": response or {}}

    def draft_brief(workflow_state: WorkflowState) -> WorkflowState:
        state = _project_state(workflow_state)
        root = Path(__file__).resolve().parents[3]
        payload = json.loads((root / "examples/project-haven.design-brief.json").read_text())
        payload["project"]["id"] = state.project_id
        payload["project"]["status"] = ProjectStatus.AWAITING_APPROVAL.value
        payload["completeness"] = state.completeness
        version = max((brief.version for brief in state.brief_versions), default=0) + 1
        payload["version"] = version
        brief = BriefVersion(
            version=version,
            content_hash=calculate_brief_content_hash(payload),
            payload=payload,
            completeness=state.completeness,
        )
        operation = UpsertBriefVersion(brief_version=brief)
        updated = apply_patch(
            state,
            StatePatch(expected_state_version=state.state_version, operations=[operation]),
        )
        return {"project_state": _dump(updated)}

    def review(workflow_state: WorkflowState) -> WorkflowState:
        result = agents.review.run(_project_state(workflow_state))
        return {"review_decision": result.review_decision.value}

    def awaiting_approval(workflow_state: WorkflowState) -> WorkflowState:
        state = _project_state(workflow_state)
        updated = state.model_copy(update={"status": ProjectStatus.AWAITING_APPROVAL})
        return {"project_state": _dump(updated)}

    def stop_unresolved(workflow_state: WorkflowState) -> WorkflowState:
        return {"next_action": NextAction.STOP_UNRESOLVED.value}

    builder.add_node("vision_analysis", vision_analysis)
    builder.add_node("homeowner_interview", homeowner_interview)
    builder.add_node("wait_homeowner", wait_homeowner)
    builder.add_node("designer_review", designer_review)
    builder.add_node("wait_designer", wait_designer)
    builder.add_node("alignment", alignment)
    builder.add_node("wait_professional", wait_professional)
    builder.add_node("draft_brief", draft_brief)
    builder.add_node("review", review)
    builder.add_node("awaiting_approval", awaiting_approval)
    builder.add_node("stop_unresolved", stop_unresolved)

    builder.add_edge(START, "vision_analysis")
    builder.add_edge("vision_analysis", "homeowner_interview")
    builder.add_conditional_edges(
        "homeowner_interview",
        lambda state: state["next_action"],
        {
            NextAction.ASK_HOMEOWNER.value: "wait_homeowner",
            NextAction.STOP_UNRESOLVED.value: "stop_unresolved",
        },
    )
    builder.add_edge("wait_homeowner", "alignment")
    builder.add_conditional_edges(
        "designer_review",
        lambda state: state["next_action"],
        {
            NextAction.ASK_DESIGNER.value: "wait_designer",
            "alignment": "alignment",
        },
    )
    builder.add_edge("wait_designer", "alignment")
    builder.add_conditional_edges(
        "alignment",
        lambda state: state["next_action"],
        {
            NextAction.ASK_HOMEOWNER.value: "homeowner_interview",
            NextAction.ASK_DESIGNER.value: "designer_review",
            NextAction.REQUEST_PROFESSIONAL_REVIEW.value: "wait_professional",
            NextAction.DRAFT_BRIEF.value: "draft_brief",
            NextAction.STOP_UNRESOLVED.value: "stop_unresolved",
        },
    )
    builder.add_edge("wait_professional", "stop_unresolved")
    builder.add_edge("draft_brief", "review")
    builder.add_conditional_edges(
        "review",
        lambda state: state["review_decision"],
        {
            ReviewDecision.REPAIR.value: "alignment",
            ReviewDecision.DOWNGRADE.value: "alignment",
            ReviewDecision.REDACT.value: "alignment",
            ReviewDecision.ESCALATE.value: "wait_professional",
            ReviewDecision.PASS.value: "awaiting_approval",
        },
    )
    builder.add_edge("awaiting_approval", END)
    builder.add_edge("stop_unresolved", END)
    return builder.compile(checkpointer=checkpointer)
