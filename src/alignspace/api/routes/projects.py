from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from alignspace.api.dependencies import get_actor, get_container
from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.resources import (
    AssetDeleteView,
    AssetInput,
    AssetWriteView,
    CreateProjectCommand,
    ProjectView,
)
from alignspace.application.service import WorkflowResponse

router = APIRouter(prefix="/v1/projects", tags=["projects"])
Actor = Annotated[ActorContext, Depends(get_actor)]
Container = Annotated[object, Depends(get_container)]


@router.post("", response_model=ProjectView, status_code=status.HTTP_201_CREATED)
def create_project(
    command: CreateProjectCommand,
    actor: Actor,
    container: Container,
) -> ProjectView:
    return container.resources.create(actor, command)


@router.get("/{project_id}", response_model=ProjectView)
def get_project(project_id: str, actor: Actor, container: Container) -> ProjectView:
    return container.resources.get(project_id, actor)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: str, actor: Actor, container: Container) -> Response:
    container.resources.delete(project_id, actor)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{project_id}/assets",
    response_model=AssetWriteView,
    status_code=status.HTTP_201_CREATED,
)
def register_asset(
    project_id: str,
    envelope: WriteEnvelope[AssetInput],
    actor: Actor,
    container: Container,
) -> AssetWriteView:
    return container.resources.register_asset(project_id, actor, envelope)


@router.delete("/{project_id}/assets/{asset_id}", response_model=AssetDeleteView)
def delete_asset(
    project_id: str,
    asset_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> AssetDeleteView:
    return container.resources.delete_asset(project_id, asset_id, actor, envelope)


@router.patch(
    "/{project_id}/attributes/{attribute_id}",
    response_model=WorkflowResponse,
)
def edit_attribute(
    project_id: str,
    attribute_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> WorkflowResponse:
    return container.workflow.edit_attribute(project_id, attribute_id, actor, envelope)
