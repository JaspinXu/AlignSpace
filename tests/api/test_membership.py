import concurrent.futures
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select, update

from alignspace.auth.config import AuthConfig
from alignspace.auth.models import JoinCodeRow
from alignspace.auth.service import digest
from alignspace.persistence.repository import ProjectRepository
from alignspace.persistence.tables import ProjectMemberRow, ProjectRow

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "a sufficiently long password"
SECRET = "membership-test-secret-that-is-long-enough"


@pytest.fixture
def api(tmp_path):
    from alignspace.main import create_app

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'membership.db'}",
        checkpoint_path=str(tmp_path / "checkpoints.db"),
        auth_config=AuthConfig(secret=SECRET, secure_cookie=False),
    )
    with TestClient(app, headers=ORIGIN) as client:
        yield client


def register(api, email):
    response = api.post("/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def auth(user):
    return {"Authorization": f"Bearer {user['accessToken']}"}


def create_project(api, owner, **overrides):
    body = {"roomType": "living_room", "budgetBand": "15k_to_30k_sgd", "consent": True}
    body.update(overrides)
    return api.post("/v1/projects", headers=auth(owner), json=body)


def join_code(api, owner, project_id):
    response = api.post(f"/v1/projects/{project_id}/join-code", headers=auth(owner))
    assert response.status_code == 200, response.text
    return response.json()


def test_create_project_returns_homeowner_without_a_designer(api):
    owner = register(api, "owner@example.com")
    created = create_project(api, owner)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["role"] == "homeowner"
    assert body["designerJoined"] is False
    assert body["status"] == "draft"
    assert {
        "id", "roomType", "budgetBand", "consent", "status",
        "stateVersion", "assets", "role", "designerJoined",
    } <= set(body)


def test_public_designer_id_in_payload_is_not_trusted(api):
    owner = register(api, "owner@example.com")
    created = create_project(api, owner, designerId="another-real-user-id")
    assert created.status_code == 201
    assert created.json()["designerJoined"] is False


def test_my_projects_lists_only_projects_i_belong_to(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    stranger = register(api, "stranger@example.com")
    assert api.get("/v1/projects", headers=auth(owner)).json() == [project]
    assert api.get("/v1/projects", headers=auth(stranger)).json() == []


def test_join_code_lets_a_designer_join_once_and_is_idempotent(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    issued = join_code(api, owner, project["id"])
    assert len(issued["code"]) == 12
    assert isinstance(issued["expiresAt"], int)

    designer = register(api, "designer@example.com")
    joined = api.post("/v1/projects/join", headers=auth(designer), json={"code": issued["code"]})
    assert joined.status_code == 200, joined.text
    assert joined.json()["role"] == "designer"
    assert joined.json()["designerJoined"] is True
    assert api.get(f"/v1/projects/{project['id']}", headers=auth(owner)).json()["designerJoined"] is True
    assert [item["id"] for item in api.get("/v1/projects", headers=auth(designer)).json()] == [project["id"]]

    again = api.post("/v1/projects/join", headers=auth(designer), json={"code": issued["code"]})
    assert again.status_code == 200
    assert again.json()["id"] == project["id"]


def test_regenerating_a_code_revokes_the_previous_one(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    first = join_code(api, owner, project["id"])
    second = join_code(api, owner, project["id"])
    assert first["code"] != second["code"]

    designer = register(api, "designer@example.com")
    revoked = api.post("/v1/projects/join", headers=auth(designer), json={"code": first["code"]})
    assert revoked.status_code == 409
    assert revoked.json()["error"]["code"] == "JOIN_CODE_INVALID"
    accepted = api.post("/v1/projects/join", headers=auth(designer), json={"code": second["code"]})
    assert accepted.status_code == 200


def test_expired_join_code_is_rejected(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    issued = join_code(api, owner, project["id"])
    with api.app.state.container.session_factory() as session:
        row = session.get(JoinCodeRow, digest(issued["code"]))
        row.expires_at = 1
        session.commit()

    designer = register(api, "designer@example.com")
    response = api.post("/v1/projects/join", headers=auth(designer), json={"code": issued["code"]})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOIN_CODE_INVALID"


def test_owner_cannot_join_their_own_project(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    issued = join_code(api, owner, project["id"])
    response = api.post("/v1/projects/join", headers=auth(owner), json={"code": issued["code"]})
    assert response.status_code == 409


def test_a_second_designer_cannot_take_an_occupied_slot(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    issued = join_code(api, owner, project["id"])
    first = register(api, "first@example.com")
    second = register(api, "second@example.com")
    assert api.post("/v1/projects/join", headers=auth(first), json={"code": issued["code"]}).status_code == 200
    later = join_code(api, owner, project["id"])
    blocked = api.post("/v1/projects/join", headers=auth(second), json={"code": later["code"]})
    assert blocked.status_code == 409


def test_non_member_cannot_read_project_or_full_state(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    outsider = register(api, "outsider@example.com")
    assert api.get(f"/v1/projects/{project['id']}", headers=auth(outsider)).status_code == 403
    assert api.get(f"/v1/projects/{project['id']}/state", headers=auth(outsider)).status_code == 403


def test_full_state_snapshot_returns_project_state_and_pending_question(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    response = api.get(f"/v1/projects/{project['id']}/state", headers=auth(owner))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"]["id"] == project["id"]
    assert body["projectState"]["projectId"] == project["id"]
    assert body["projectState"]["stateVersion"] == 0
    assert body["pendingQuestion"] is None


def test_full_state_exposes_the_pending_homeowner_question_after_analysis(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    headers = auth(owner)
    version = 0
    for index in range(3):
        buffer = BytesIO()
        Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
        asset = api.post(
            f"/v1/projects/{project['id']}/assets",
            headers=headers,
            data={"expectedStateVersion": str(version), "idempotencyKey": f"asset-{index}"},
            files={"file": (f"room-{index}.png", buffer.getvalue(), "image/png")},
        )
        assert asset.status_code == 201, asset.text
        version = asset.json()["stateVersion"]
    started = api.post(
        f"/v1/projects/{project['id']}/analysis-runs",
        headers=headers,
        json={"idempotencyKey": "run-1", "expectedStateVersion": version, "data": {}},
    )
    assert started.status_code == 202, started.text

    snapshot = api.get(f"/v1/projects/{project['id']}/state", headers=headers)
    assert snapshot.status_code == 200, snapshot.text
    body = snapshot.json()
    assert body["pendingQuestion"]["targetRole"] == "homeowner"
    assert body["projectState"]["waitReason"] == "homeowner"
    assert body["project"]["role"] == "homeowner"


def test_join_attempts_are_rate_limited(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    join_code(api, owner, project["id"])
    designer = register(api, "designer@example.com")
    headers = auth(designer)

    statuses = [
        api.post("/v1/projects/join", headers=headers, json={"code": f"WRONG{i}"}).status_code
        for i in range(12)
    ]

    assert statuses[:10] == [409] * 10
    assert statuses[-1] == 429
    limited = api.post("/v1/projects/join", headers=headers, json={"code": "WRONG-again"})
    assert limited.status_code == 429
    assert "Retry-After" in limited.headers


def test_full_state_reads_a_single_consistent_snapshot(api, monkeypatch):
    with api.app.state.container.engine.connect() as connection:
        assert connection.exec_driver_sql("PRAGMA journal_mode=WAL").scalar() == "wal"
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    container = api.app.state.container
    original_load = ProjectRepository.load

    def load_with_competing_write(session_self, project_id):
        # Another request commits a state write after the project row has been
        # read but before the shared state is read.
        with container.session_factory() as competing:
            competing.execute(
                update(ProjectRow)
                .where(ProjectRow.id == project_id)
                .values(state_version=1, status="analysing")
            )
            competing.commit()
        session_self._session.expire_all()
        return original_load(session_self, project_id)

    monkeypatch.setattr(ProjectRepository, "load", load_with_competing_write)

    response = api.get(f"/v1/projects/{project['id']}/state", headers=auth(owner))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"]["stateVersion"] == body["projectState"]["stateVersion"]


def test_concurrent_redemption_grants_at_most_one_designer(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner).json()
    issued = join_code(api, owner, project["id"])
    first = register(api, "first@example.com")
    second = register(api, "second@example.com")

    def redeem(user):
        return api.post("/v1/projects/join", headers=auth(user), json={"code": issued["code"]})

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(redeem, [first, second]))

    assert sorted(result.status_code for result in results) == [200, 409]
    with api.app.state.container.session_factory() as session:
        designers = session.scalars(
            select(ProjectMemberRow).where(ProjectMemberRow.role == "designer")
        ).all()
    assert len(designers) == 1
