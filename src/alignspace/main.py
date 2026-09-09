from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request

from alignspace.agents.contracts import AgentBundle
from alignspace.api.errors import install_error_handlers
from alignspace.api.routes.projects import router as projects_router
from alignspace.application.resources import ProjectResourceService
from alignspace.application.service import WorkflowService
from alignspace.persistence.database import create_engine_and_session
from alignspace.providers.mock import build_mock_agents
from alignspace.workflow.runtime import sqlite_graph


@dataclass(frozen=True)
class Container:
    engine: Any
    session_factory: Any
    graph: Any
    resources: ProjectResourceService
    workflow: WorkflowService


def create_app(
    database_url: str = "sqlite:///alignspace.db",
    checkpoint_path: str = "alignspace-checkpoints.db",
    *,
    agents: AgentBundle | None = None,
) -> FastAPI:
    engine, session_factory = create_engine_and_session(database_url)
    graph = sqlite_graph(agents or build_mock_agents(), checkpoint_path)
    resources = ProjectResourceService(
        session_factory=session_factory,
        checkpoint_delete=graph.checkpointer.delete_thread,
    )
    workflow = WorkflowService(
        session_factory=session_factory,
        graph=graph,
        membership_check=resources.is_member,
    )
    container = Container(
        engine=engine,
        session_factory=session_factory,
        graph=graph,
        resources=resources,
        workflow=workflow,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
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
    app.include_router(projects_router)
    return app
