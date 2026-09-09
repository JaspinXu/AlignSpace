import pytest
from fastapi.testclient import TestClient

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


@pytest.fixture
def client(tmp_path):
    from alignspace.main import create_app

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        checkpoint_path=str(tmp_path / "checkpoints.db"),
    )
    with TestClient(app) as test_client:
        yield test_client


def _create_project(client: TestClient, *, consent: bool) -> str:
    response = client.post(
        "/v1/projects",
        headers={"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"},
        json={
            "roomType": "living_room",
            "budgetBand": "15k_to_30k_sgd",
            "consent": consent,
            "designerId": "designer-1",
        },
    )
    assert response.status_code == 201
    return response.json()["id"]


@pytest.fixture
def ready_project(client: TestClient) -> str:
    return _create_project(client, consent=True)


@pytest.fixture
def project_without_consent(client: TestClient) -> str:
    return _create_project(client, consent=False)


@pytest.fixture
def project_with_attribute(client: TestClient) -> str:
    project_id = _create_project(client, consent=True)
    container = client.app.state.container
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        state = uow.projects.load(project_id)
        state = state.model_copy(
            update={
                "attributes": [
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
                                source_id="living-room-1",
                                description="Observed wall colour.",
                            )
                        ],
                        actor=ActorKind.VISION_AGENT,
                    )
                ]
            }
        )
        # Fixture setup preserves version zero because no API write has occurred.
        uow.projects._replace_entities(state)
        uow.commit()
    return project_id
