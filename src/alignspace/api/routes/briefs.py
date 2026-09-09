from typing import Annotated

from fastapi import APIRouter, Depends

from alignspace.api.dependencies import get_actor, get_container
from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.service import BriefView, WorkflowResponse

router = APIRouter(prefix="/v1/projects", tags=["briefs"])
Actor = Annotated[ActorContext, Depends(get_actor)]
Container = Annotated[object, Depends(get_container)]


@router.get("/{project_id}/briefs/latest", response_model=BriefView)
def latest_brief(project_id: str, actor: Actor, container: Container) -> BriefView:
    return container.workflow.latest_brief(project_id, actor)


@router.patch("/{project_id}/briefs/{version}", response_model=BriefView)
def edit_brief(
    project_id: str,
    version: int,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> BriefView:
    return container.workflow.edit_brief(project_id, version, actor, envelope)


@router.post("/{project_id}/briefs/{version}/approvals", response_model=WorkflowResponse)
def approve_brief(
    project_id: str,
    version: int,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> WorkflowResponse:
    return container.workflow.approve_brief(project_id, version, actor, envelope)
