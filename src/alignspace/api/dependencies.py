from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import select

from alignspace.application.commands import ActorContext
from alignspace.application.service import AuthorizationError
from alignspace.auth.routes import current_user
from alignspace.domain.enums import Role
from alignspace.persistence.tables import ProjectMemberRow


def get_container(request: Request) -> Any:
    return request.app.state.container


def get_actor(
    request: Request,
    user: Annotated[object, Depends(current_user)],
) -> ActorContext:
    project_id = request.path_params.get("project_id")
    if project_id is None:
        return ActorContext(actor_id=user.id, role=Role.HOMEOWNER)
    with request.app.state.container.session_factory() as db:
        member = db.scalar(select(ProjectMemberRow).where(
            ProjectMemberRow.project_id == project_id,
            ProjectMemberRow.member_id == user.id,
        ))
        if member is None:
            raise AuthorizationError("You are not a member of this project.")
        return ActorContext(actor_id=user.id, role=Role(member.role))
