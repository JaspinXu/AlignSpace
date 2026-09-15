from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status

from alignspace.api.dependencies import get_actor, get_container
from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.membership import JoinCodeView, JoinRequest
from alignspace.application.resources import (
    AssetDeleteView,
    AssetWriteView,
    CreateProjectCommand,
    ProjectSnapshot,
    ProjectView,
)
from alignspace.application.service import WorkflowResponse
from alignspace.storage.images import MAX_BYTES

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


@router.get("", response_model=list[ProjectView])
def list_projects(actor: Actor, container: Container) -> list[ProjectView]:
    return container.resources.list_for_member(actor)


@router.post("/join", response_model=ProjectView)
def join_project(
    command: JoinRequest,
    request: Request,
    actor: Actor,
    container: Container,
) -> ProjectView:
    container.auth.throttle("join-user", actor.actor_id, limit=10, window=60)
    container.auth.throttle("join-ip", request.client.host, limit=30, window=60)
    return container.membership.join(actor, command)


@router.get("/{project_id}/state", response_model=ProjectSnapshot)
def get_project_state(
    project_id: str,
    actor: Actor,
    container: Container,
) -> ProjectSnapshot:
    return container.resources.snapshot(project_id, actor)


@router.post("/{project_id}/join-code", response_model=JoinCodeView)
def generate_join_code(
    project_id: str,
    actor: Actor,
    container: Container,
) -> JoinCodeView:
    return container.membership.generate_code(project_id, actor)


@router.get("/{project_id}/assets/{asset_id}/content")
def asset_content(project_id: str, asset_id: str, actor: Actor, container: Container) -> Response:
    data, media_type = container.resources.asset_content(project_id, asset_id, actor)
    return Response(
        content=data,
        media_type=media_type,
        headers={"Cache-Control": "private, max-age=0"},
    )


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
    file: Annotated[UploadFile, File()],
    expected_state_version: Annotated[int, Form(alias="expectedStateVersion")],
    idempotency_key: Annotated[str, Form(alias="idempotencyKey")],
    request: Request,
    actor: Actor,
    container: Container,
) -> AssetWriteView:
    container.auth.throttle("upload-user", actor.actor_id, limit=20, window=60)
    container.auth.throttle("upload-ip", request.client.host, limit=60, window=60)
    return container.resources.register_asset(
        project_id,
        actor,
        expected_state_version=expected_state_version,
        idempotency_key=idempotency_key,
        filename=file.filename or "upload",
        raw=file.file.read(MAX_BYTES + 1),
        declared_type=file.content_type,
    )


@router.delete("/{project_id}/assets/{asset_id}", response_model=AssetDeleteView)
def delete_asset(
    project_id: str,
    asset_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> AssetDeleteView:
    result = container.resources.delete_asset(project_id, asset_id, actor, envelope)
    advanced = container.workflow.advance_interview(project_id, actor)
    if advanced is not None:
        return AssetDeleteView(id=result.id, state_version=advanced.state_version)
    return result


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
