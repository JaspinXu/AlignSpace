from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from alignspace.api.dependencies import get_actor, get_container
from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.space_service import (
    MaterialCatalogue,
    SpaceSnapshot,
    SpaceVersionList,
)

router = APIRouter(prefix="/v1/projects", tags=["space"])
Actor = Annotated[ActorContext, Depends(get_actor)]
Container = Annotated[object, Depends(get_container)]


@router.get("/{project_id}/space", response_model=SpaceSnapshot)
def latest_space(project_id: str, actor: Actor, container: Container) -> SpaceSnapshot:
    return container.space.snapshot(project_id, actor)


@router.get("/{project_id}/space/versions", response_model=SpaceVersionList)
def space_versions(project_id: str, actor: Actor, container: Container) -> SpaceVersionList:
    return container.space.versions(project_id, actor)


@router.get("/{project_id}/materials", response_model=MaterialCatalogue)
def material_catalogue(
    project_id: str,
    actor: Actor,
    container: Container,
    target: Annotated[str | None, Query()] = None,
) -> MaterialCatalogue:
    return container.space.materials(project_id, actor, target)


@router.post("/{project_id}/space/rooms", response_model=SpaceSnapshot)
def create_room(
    project_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> SpaceSnapshot:
    return container.space.create_room(project_id, actor, envelope)


@router.patch("/{project_id}/space/rooms/{room_id}", response_model=SpaceSnapshot)
def update_room(
    project_id: str,
    room_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> SpaceSnapshot:
    return container.space.update_room(project_id, room_id, actor, envelope)


@router.delete("/{project_id}/space/rooms/{room_id}", response_model=SpaceSnapshot)
def delete_room(
    project_id: str,
    room_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    response: Response,
    actor: Actor,
    container: Container,
) -> SpaceSnapshot:
    response.status_code = status.HTTP_200_OK
    return container.space.delete_room(project_id, room_id, actor, envelope)


@router.post("/{project_id}/space/objects", response_model=SpaceSnapshot)
def create_object(
    project_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> SpaceSnapshot:
    return container.space.create_object(project_id, actor, envelope)


@router.patch("/{project_id}/space/objects/{object_id}", response_model=SpaceSnapshot)
def update_object(
    project_id: str,
    object_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    actor: Actor,
    container: Container,
) -> SpaceSnapshot:
    return container.space.update_object(project_id, object_id, actor, envelope)


@router.delete("/{project_id}/space/objects/{object_id}", response_model=SpaceSnapshot)
def delete_object(
    project_id: str,
    object_id: str,
    envelope: WriteEnvelope[dict[str, object]],
    response: Response,
    actor: Actor,
    container: Container,
) -> SpaceSnapshot:
    response.status_code = status.HTTP_200_OK
    return container.space.delete_object(project_id, object_id, actor, envelope)
