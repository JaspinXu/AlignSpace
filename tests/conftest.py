import pytest

from alignspace.application.service import WorkflowService
from alignspace.domain.enums import ActorKind, AttributeStatus, EvidenceSource, Role
from alignspace.domain.models import Attribute, Evidence, ProjectState
from alignspace.persistence.database import create_engine_and_session
from alignspace.persistence.uow import SqlAlchemyUnitOfWork
from alignspace.providers.mock import build_mock_agents
from alignspace.workflow.runtime import memory_graph


@pytest.fixture
def service(tmp_path):
    engine, session_factory = create_engine_and_session(f"sqlite:///{tmp_path / 'service.db'}")
    with SqlAlchemyUnitOfWork(session_factory) as uow:
        uow.projects.create(
            ProjectState(
                project_id="project-1",
                attributes=[
                    Attribute(
                        id="wall-colour",
                        target_element="wall",
                        dimension="colour",
                        value="warm beige",
                        status=AttributeStatus.PROPOSED,
                        confidence=0.8,
                        evidence=[
                            Evidence(
                                source_type=EvidenceSource.IMAGE,
                                source_id="asset-1",
                                description="Observed wall colour.",
                            )
                        ],
                        actor=ActorKind.VISION_AGENT,
                    )
                ],
            )
        )
        uow.commit()
    members = {
        ("project-1", "homeowner-1", Role.HOMEOWNER),
        ("project-1", "designer-1", Role.DESIGNER),
    }
    workflow_service = WorkflowService(
        session_factory=session_factory,
        graph=memory_graph(build_mock_agents()),
        membership_check=lambda project_id, actor: (
            project_id,
            actor.actor_id,
            actor.role,
        )
        in members,
    )
    yield workflow_service
    engine.dispose()
