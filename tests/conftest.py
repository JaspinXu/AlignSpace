import json
from io import BytesIO
from pathlib import Path
from typing import Annotated

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from PIL import Image

from alignspace.api.dependencies import get_actor
from alignspace.application.commands import ActorContext
from alignspace.application.service import WorkflowService
from alignspace.auth.config import AuthConfig
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
from alignspace.persistence.tables import ImageAssetRow, ProjectMemberRow
from alignspace.persistence.uow import SqlAlchemyUnitOfWork
from alignspace.providers.mock import build_mock_agents
from alignspace.workflow.runtime import memory_graph


@pytest.fixture(autouse=True)
def isolated_asset_storage(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIGNSPACE_ASSET_DIR", str(tmp_path / "assets"))


def image_bytes(fmt: str = "PNG", color: str = "red") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format=fmt)
    return buffer.getvalue()


def upload_asset(
    client: TestClient,
    project_id: str,
    *,
    headers: dict[str, str],
    key: str,
    version: int,
    fmt: str = "PNG",
) -> dict:
    response = client.post(
        f"/v1/projects/{project_id}/assets",
        headers=headers,
        data={"expectedStateVersion": str(version), "idempotencyKey": key},
        files={"file": (f"room.{fmt.lower()}", image_bytes(fmt), f"image/{fmt.lower()}")},
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
def upload_image(client: TestClient):
    def _upload(
        project_id: str,
        *,
        headers: dict[str, str],
        key: str,
        version: int,
        fmt: str = "PNG",
        color: str = "red",
    ):
        return client.post(
            f"/v1/projects/{project_id}/assets",
            headers=headers,
            data={"expectedStateVersion": str(version), "idempotencyKey": key},
            files={
                "file": (f"room.{fmt.lower()}", image_bytes(fmt, color), f"image/{fmt.lower()}")
            },
        )

    return _upload


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
        uow.session.add(
            ImageAssetRow(
                project_id="project-1",
                id="asset-1",
                payload={"media_type": "image/png", "sha256": "abc123"},
                deleted_at=None,
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


TEST_AUTH_SECRET = "test-only-auth-secret-that-is-long-enough"


def test_actor(
    x_actor_id: Annotated[str, Header()],
    x_actor_role: Annotated[str, Header()],
) -> ActorContext:
    """Test-only identity injection. Production never trusts these headers."""
    return ActorContext(actor_id=x_actor_id, role=Role(x_actor_role))


@pytest.fixture
def client(tmp_path):
    from alignspace.main import create_app

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'api.db'}",
        checkpoint_path=str(tmp_path / "checkpoints.db"),
        auth_config=AuthConfig(secret=TEST_AUTH_SECRET, secure_cookie=False),
    )
    # Override only inside tests: the real get_actor keeps validating Bearer tokens.
    app.dependency_overrides[get_actor] = test_actor
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
        },
    )
    assert response.status_code == 201
    project_id = response.json()["id"]
    # The public API no longer accepts a designerId, so tests seed the second
    # member directly instead of inventing a production shortcut.
    _add_member(client, project_id, "designer-1", Role.DESIGNER)
    return project_id


def _add_member(client: TestClient, project_id: str, member_id: str, role: Role) -> None:
    container = client.app.state.container
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        uow.session.add(
            ProjectMemberRow(
                project_id=project_id,
                member_id=member_id,
                role=role.value,
                payload={},
            )
        )
        uow.commit()


@pytest.fixture
def add_member(client: TestClient):
    def _add(
        project_id: str,
        member_id: str = "designer-1",
        role: Role = Role.DESIGNER,
    ) -> None:
        _add_member(client, project_id, member_id, role)

    return _add


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
    version = 0
    for index in range(3):
        asset = upload_asset(
            client, project_id, headers=headers, key=f"ready-asset-{index}", version=version
        )
        version = asset["stateVersion"]
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


class WorkflowDriver:
    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.homeowner_headers = {
            "X-Actor-Id": "homeowner-1",
            "X-Actor-Role": "homeowner",
        }
        self.designer_headers = {
            "X-Actor-Id": "designer-1",
            "X-Actor-Role": "designer",
        }

    def _project(self, project_id: str, headers: dict[str, str] | None = None) -> dict:
        response = self.client.get(
            f"/v1/projects/{project_id}",
            headers=headers or self.homeowner_headers,
        )
        assert response.status_code == 200, response.text
        return response.json()

    def _write(
        self,
        method: str,
        path: str,
        project_id: str,
        key: str,
        data: dict[str, object],
        *,
        headers: dict[str, str] | None = None,
        expected_status: int = 200,
    ) -> dict:
        current = self._project(project_id, headers)
        response = self.client.request(
            method,
            path,
            headers=headers or self.homeowner_headers,
            json={
                "idempotencyKey": key,
                "expectedStateVersion": current["stateVersion"],
                "data": data,
            },
        )
        assert response.status_code == expected_status, response.text
        return response.json()

    def complete(self) -> dict[str, object]:
        project_id = _create_project(self.client, consent=True)

        version = 0
        for index in range(3):
            asset = upload_asset(
                self.client,
                project_id,
                headers=self.homeowner_headers,
                key=f"asset-{index}",
                version=version,
            )
            version = asset["stateVersion"]

        started = self._write(
            "POST",
            f"/v1/projects/{project_id}/analysis-runs",
            project_id,
            "analysis-1",
            {},
            expected_status=202,
        )
        broad = self._write(
            "POST",
            (
                f"/v1/projects/{project_id}/questions/"
                f"{started['pendingQuestion']['id']}/answer"
            ),
            project_id,
            "answer-liked-elements",
            {
                "parts": [
                    {
                        "assetId": option["assetId"],
                        "targetElement": option["targetElement"],
                    }
                    for option in started["pendingQuestion"]["options"]
                ]
            },
            expected_status=202,
        )

        for _ in range(10):
            pending = broad.get("pendingQuestion")
            if not pending or pending.get("kind") != "detail":
                break
            broad = self._write(
                "POST",
                f"/v1/projects/{project_id}/questions/{pending['id']}/answer",
                project_id,
                f"detail-{pending['id']}",
                {
                    "selection": [
                        {
                            "attributeId": option["attributeId"],
                            "decision": "confirmed",
                            "value": option["value"],
                        }
                        for option in pending["options"]
                    ]
                },
                expected_status=202,
            )

        explicit_preferences = {
            "style": "warm modern",
            "material": "natural stone",
            "layout": "clear conversational seating layout",
            "furniture": "compact rounded furniture",
            "mood": "calm and welcoming",
            "function": "conversation and reading",
        }
        for dimension, value in explicit_preferences.items():
            self._write(
                "PATCH",
                f"/v1/projects/{project_id}/attributes/manual-{dimension}",
                project_id,
                f"manual-{dimension}",
                {
                    "targetElement": "living_room",
                    "dimension": dimension,
                    "value": value,
                    "status": "confirmed",
                },
            )

        assert broad["waitReason"] == "designer"

        constraint = self._write(
            "POST",
            f"/v1/projects/{project_id}/constraints",
            project_id,
            "constraint-stone-budget",
            {
                "category": "budget",
                "statement": "天然石材工作台超出当前预算档位",
                "rationale": "改用石材效果饰面可在预算内实现相近观感",
                "severity": "important",
                "appliesTo": "worktop",
                "attributeId": "manual-material",
                "incompatibleWith": ["natural stone"],
            },
            headers=self.designer_headers,
        )
        assert constraint["projectState"]["conflicts"][0]["constraintId"]

        resumed = self._write(
            "POST",
            f"/v1/projects/{project_id}/designer-reviews",
            project_id,
            "designer-review-1",
            {"note": "预算约束已录入。"},
            headers=self.designer_headers,
            expected_status=202,
        )
        assert resumed["pendingQuestion"]["id"].startswith("question-conflict-")

        drafted = self._write(
            "POST",
            (
                f"/v1/projects/{project_id}/questions/"
                f"{resumed['pendingQuestion']['id']}/answer"
            ),
            project_id,
            "resolve-stone-budget",
            {"answer": "Use the lower-cost stone-effect finish."},
        )
        assert drafted["status"] == "awaiting_approval"

        latest_response = self.client.get(
            f"/v1/projects/{project_id}/briefs/latest",
            headers=self.homeowner_headers,
        )
        assert latest_response.status_code == 200, latest_response.text
        latest = latest_response.json()

        homeowner_approval = self._write(
            "POST",
            f"/v1/projects/{project_id}/briefs/{latest['version']}/approvals",
            project_id,
            "approve-homeowner",
            {"contentHash": latest["contentHash"]},
        )
        assert homeowner_approval["status"] == "awaiting_approval"
        designer_approval = self._write(
            "POST",
            f"/v1/projects/{project_id}/briefs/{latest['version']}/approvals",
            project_id,
            "approve-designer",
            {"contentHash": latest["contentHash"]},
            headers=self.designer_headers,
        )

        final_brief_response = self.client.get(
            f"/v1/projects/{project_id}/briefs/latest",
            headers=self.homeowner_headers,
        )
        assert final_brief_response.status_code == 200, final_brief_response.text
        final_brief = final_brief_response.json()
        schema = json.loads(
            (Path(__file__).resolve().parents[1] / "schemas/design-brief.schema.json").read_text()
        )
        state = designer_approval["projectState"]
        return {
            "status": designer_approval["status"],
            "latestBrief": final_brief,
            "questions": state["questions"],
            "conflicts": state["conflicts"],
            "briefSchemaValid": Draft202012Validator(schema).is_valid(final_brief["payload"]),
        }


@pytest.fixture
def workflow_driver(client: TestClient) -> WorkflowDriver:
    return WorkflowDriver(client)
