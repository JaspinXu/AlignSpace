import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alignspace.application.service import WorkflowService
from alignspace.domain.enums import (
    ActorKind,
    AttributeStatus,
    ConflictStatus,
    ConflictType,
    ConstraintSeverity,
    EvidenceSource,
    ProjectStatus,
    Role,
)
from alignspace.domain.models import (
    Attribute,
    BriefVersion,
    Conflict,
    Evidence,
    ProjectState,
    calculate_brief_content_hash,
)
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


@pytest.fixture
def analysis_ready_project(client: TestClient) -> str:
    project_id = _create_project(client, consent=True)
    headers = {"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"}
    for index in range(3):
        response = client.post(
            f"/v1/projects/{project_id}/assets",
            headers=headers,
            json={
                "idempotencyKey": f"ready-asset-{index}",
                "expectedStateVersion": index,
                "data": {
                    "fixtureId": f"living-room-{index}",
                    "mediaType": "image/jpeg",
                    "sizeBytes": 1024,
                },
            },
        )
        assert response.status_code == 201
    return project_id


@pytest.fixture
def brief_ready_project(client: TestClient) -> str:
    project_id = _create_project(client, consent=True)
    dimensions = ["style", "colour", "material", "lighting", "layout", "furniture", "mood"]
    attributes = [
        Attribute(
            id=f"confirmed-{dimension}",
            target_element="living_room",
            dimension=dimension,
            value=f"confirmed {dimension}",
            status=AttributeStatus.CONFIRMED,
            confidence=1,
            evidence=[
                Evidence(
                    source_type=EvidenceSource.HOMEOWNER_ANSWER,
                    source_id=f"answer-{dimension}",
                    description=f"Confirmed {dimension} preference.",
                )
            ],
            actor=ActorKind.HOMEOWNER,
        )
        for dimension in dimensions
    ]
    payload = json.loads(
        (Path(__file__).resolve().parents[1] / "examples/project-haven.design-brief.json").read_text()
    )
    payload["project"]["id"] = project_id
    payload["project"]["status"] = ProjectStatus.AWAITING_APPROVAL.value
    payload["completeness"] = 0.875
    payload["version"] = 1
    brief = BriefVersion(
        version=1,
        content_hash=calculate_brief_content_hash(payload),
        payload=payload,
        completeness=0.875,
    )
    container = client.app.state.container
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        state = uow.projects.load(project_id)
        updated = state.model_copy(
            update={
                "state_version": 1,
                "status": ProjectStatus.AWAITING_APPROVAL,
                "attributes": attributes,
                "conflicts": [
                    Conflict(
                        id="finish-budget-conflict",
                        type=ConflictType.PREFERENCE_VS_CONSTRAINT,
                        summary="Natural stone exceeds the budget fixture.",
                        impact="Choose a lower-cost finish.",
                        status=ConflictStatus.OPEN,
                        severity=ConstraintSeverity.IMPORTANT,
                    )
                ],
                "brief_versions": [brief],
                "completeness": 0.875,
            }
        )
        uow.projects.save(updated, expected_version=0)
        uow.commit()
    return project_id
