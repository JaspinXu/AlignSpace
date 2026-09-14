from typing import Annotated

from fastapi import APIRouter, Depends

from alignspace.api.dependencies import get_actor, get_container
from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.service import WorkflowResponse
from alignspace.domain.models import Constraint

router = APIRouter(prefix="/v1/projects", tags=["constraints"])
Actor = Annotated[ActorContext, Depends(get_actor)]
Container = Annotated[object, Depends(get_container)]


@router.get("/{project_id}/constraints", response_model=list[Constraint])
def list_constraints(project_id: str, actor: Actor, container: Container) -> list[Constraint]:
    return container.workflow.list_constraints(project_id, actor)


@router.post("/{project_id}/constraints", response_model=WorkflowResponse)
def create_constraint(
    project_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> WorkflowResponse:
    return container.workflow.create_constraint(project_id, actor, envelope)


@router.patch("/{project_id}/constraints/{constraint_id}", response_model=WorkflowResponse)
def update_constraint(
    project_id: str,
    constraint_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> WorkflowResponse:
    return container.workflow.update_constraint(project_id, constraint_id, actor, envelope)


@router.post("/{project_id}/constraints/{constraint_id}/withdraw", response_model=WorkflowResponse)
def withdraw_constraint(
    project_id: str,
    constraint_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> WorkflowResponse:
    return container.workflow.withdraw_constraint(project_id, constraint_id, actor, envelope)
