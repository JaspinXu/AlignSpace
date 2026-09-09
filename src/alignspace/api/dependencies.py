from typing import Annotated, Any

from fastapi import Header, Request

from alignspace.application.commands import ActorContext
from alignspace.domain.enums import Role


def get_container(request: Request) -> Any:
    return request.app.state.container


def get_actor(
    actor_id: Annotated[str, Header(alias="X-Actor-Id")],
    actor_role: Annotated[Role, Header(alias="X-Actor-Role")],
) -> ActorContext:
    return ActorContext(actor_id=actor_id, role=actor_role)
