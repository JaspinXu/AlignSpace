from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from alignspace.api.dependencies import get_actor, get_container
from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.service import WorkflowResponse
from alignspace.domain.models import Question

router = APIRouter(prefix="/v1/projects", tags=["workflow"])
Actor = Annotated[ActorContext, Depends(get_actor)]
Container = Annotated[object, Depends(get_container)]


def _set_workflow_status(response: Response, result: WorkflowResponse) -> None:
    response.status_code = status.HTTP_202_ACCEPTED if result.wait_reason else status.HTTP_200_OK


@router.post("/{project_id}/analysis-runs", response_model=WorkflowResponse)
def start_analysis(
    project_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    response: Response,
    actor: Actor,
    container: Container,
) -> WorkflowResponse:
    container.resources.require_analysis_ready(project_id, actor)
    result = container.workflow.start_analysis(project_id, actor, envelope)
    _set_workflow_status(response, result)
    return result


@router.get("/{project_id}/questions/next", response_model=Question)
def next_question(project_id: str, actor: Actor, container: Container) -> Question:
    return container.workflow.next_question(project_id, actor)


@router.post("/{project_id}/questions/{question_id}/answer", response_model=WorkflowResponse)
def answer_question(
    project_id: str,
    question_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    response: Response,
    actor: Actor,
    container: Container,
) -> WorkflowResponse:
    result = container.workflow.answer_question(project_id, question_id, actor, envelope)
    _set_workflow_status(response, result)
    return result


@router.post("/{project_id}/designer-reviews", response_model=WorkflowResponse)
def submit_designer_review(
    project_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    response: Response,
    actor: Actor,
    container: Container,
) -> WorkflowResponse:
    result = container.workflow.resume(project_id, actor, "designer", envelope)
    _set_workflow_status(response, result)
    return result


@router.post("/{project_id}/conflicts/{conflict_id}/resolve", response_model=WorkflowResponse)
def resolve_conflict(
    project_id: str,
    conflict_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> WorkflowResponse:
    return container.workflow.resolve_conflict(project_id, conflict_id, actor, envelope)
