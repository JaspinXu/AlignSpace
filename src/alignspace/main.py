import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request

from alignspace.agents.contracts import AgentBundle
from alignspace.api.errors import install_error_handlers
from alignspace.api.routes.briefs import router as briefs_router
from alignspace.api.routes.constraints import router as constraints_router
from alignspace.api.routes.preferences import router as preferences_router
from alignspace.api.routes.projects import router as projects_router
from alignspace.api.routes.workflow import router as workflow_router
from alignspace.application.membership import MembershipService
from alignspace.application.preferences import PreferenceService
from alignspace.application.resources import ProjectResourceService
from alignspace.application.service import WorkflowService
from alignspace.auth.config import AuthConfig
from alignspace.auth.routes import router as auth_router
from alignspace.auth.service import AuthService
from alignspace.persistence.database import create_engine_and_session
from alignspace.providers.factory import build_preference_provider
from alignspace.providers.mock import build_mock_agents
from alignspace.storage.local import LocalStorage
from alignspace.workflow.runtime import sqlite_graph


@dataclass(frozen=True)
class Container:
    engine: Any
    session_factory: Any
    graph: Any
    resources: ProjectResourceService
    workflow: WorkflowService
    membership: MembershipService
    preferences: PreferenceService
    auth: AuthService


def create_app(
    database_url: str | None = None,
    checkpoint_path: str | None = None,
    *,
    agents: AgentBundle | None = None,
    auth_config: AuthConfig | None = None,
) -> FastAPI:
    database_url = database_url or os.getenv(
        "ALIGNSPACE_DATABASE_URL", "sqlite:///alignspace-accounts.db"
    )
    checkpoint_path = checkpoint_path or os.getenv(
        "ALIGNSPACE_CHECKPOINT_PATH", "alignspace-accounts-checkpoints.db"
    )
    engine, session_factory = create_engine_and_session(database_url)
    graph = sqlite_graph(agents or build_mock_agents(), checkpoint_path)
    storage = LocalStorage(os.getenv("ALIGNSPACE_ASSET_DIR", "var/assets"))
    resources = ProjectResourceService(
        session_factory=session_factory,
        checkpoint_delete=graph.checkpointer.delete_thread,
        storage=storage,
    )
    workflow = WorkflowService(
        session_factory=session_factory,
        graph=graph,
        membership_check=resources.is_member,
    )
    membership = MembershipService(
        session_factory=session_factory,
        resources=resources,
    )
    preferences = PreferenceService(
        session_factory=session_factory,
        provider=build_preference_provider(),
        storage=storage,
        membership_check=resources.is_member,
    )
    container = Container(
        engine=engine,
        session_factory=session_factory,
        graph=graph,
        resources=resources,
        workflow=workflow,
        membership=membership,
        preferences=preferences,
        auth=AuthService(session_factory, auth_config or AuthConfig.from_env()),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            container.auth.config.validate()
            yield
        finally:
            graph.checkpointer.conn.close()
            engine.dispose()

    app = FastAPI(title="AlignSpace API", version="0.1.0", lifespan=lifespan)
    app.state.container = container

    @app.middleware("http")
    async def correlation_id(request: Request, call_next):
        request.state.correlation_id = request.headers.get("X-Correlation-Id", str(uuid4()))
        response = await call_next(request)
        response.headers["X-Correlation-Id"] = request.state.correlation_id
        return response

    install_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(projects_router)
    app.include_router(constraints_router)
    app.include_router(preferences_router)
    app.include_router(workflow_router)
    app.include_router(briefs_router)
    return app


app = create_app()
