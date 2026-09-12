from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from alignspace.auth.config import AuthConfig

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "a sufficiently long password"
SECRET = "asset-upload-test-secret-long-enough"


@pytest.fixture
def api(tmp_path):
    from alignspace.main import create_app

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'upload.db'}",
        checkpoint_path=str(tmp_path / "checkpoints.db"),
        auth_config=AuthConfig(secret=SECRET, secure_cookie=False),
    )
    with TestClient(app, headers=ORIGIN) as client:
        yield client


def image_bytes(fmt="PNG", color="red"):
    buffer = BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format=fmt)
    return buffer.getvalue()


def register(api, email):
    response = api.post("/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def auth(user):
    return {"Authorization": f"Bearer {user['accessToken']}"}


def create_project(api, owner, consent=True):
    response = api.post(
        "/v1/projects",
        headers=auth(owner),
        json={"roomType": "living_room", "budgetBand": "15k_to_30k_sgd", "consent": consent},
    )
    assert response.status_code == 201, response.text
    return response.json()


def upload(api, owner, project_id, *, key="upload-1", version=0, fmt="PNG", data=None):
    raw = data if data is not None else image_bytes(fmt)
    return api.post(
        f"/v1/projects/{project_id}/assets",
        headers=auth(owner),
        data={"expectedStateVersion": str(version), "idempotencyKey": key},
        files={"file": (f"room.{fmt.lower()}", raw, f"image/{fmt.lower()}")},
    )


def test_homeowner_uploads_a_real_image_and_sees_it_listed(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)

    created = upload(api, owner, project["id"])
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["mediaType"] == "image/png"
    assert body["originalFilename"] == "room.png"
    assert body["sizeBytes"] > 0
    assert body["deleted"] is False
    assert body["stateVersion"] == 1

    listed = api.get(f"/v1/projects/{project['id']}", headers=auth(owner)).json()
    assert [asset["id"] for asset in listed["assets"]] == [body["id"]]
    assert listed["assets"][0]["sha256"] == body["sha256"]


def test_upload_requires_consent_homeowner_and_valid_image(api):
    owner = register(api, "owner@example.com")
    unconsented = create_project(api, owner, consent=False)
    consented = create_project(api, owner, consent=True)

    assert upload(api, owner, unconsented["id"]).status_code == 409
    assert upload(api, owner, consented["id"], fmt="GIF").status_code == 415
    assert upload(api, owner, consented["id"], data=b"not-an-image").status_code == 400
    assert upload(api, owner, consented["id"], data=b"\x00" * (10 * 1024 * 1024 + 1)).status_code == 413


def test_upload_is_idempotent_and_rejects_conflicting_reuse(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)

    first = upload(api, owner, project["id"], key="same")
    replay = upload(api, owner, project["id"], key="same")
    assert replay.json() == first.json()

    conflict = upload(api, owner, project["id"], key="same", data=image_bytes(color="blue"))
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_stale_version_and_non_member_are_rejected(api):
    owner = register(api, "owner@example.com")
    stranger = register(api, "stranger@example.com")
    project = create_project(api, owner)

    stale = upload(api, owner, project["id"], version=5)
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STATE_VERSION_STALE"
    assert upload(api, stranger, project["id"]).status_code == 403


def test_members_can_read_image_content_but_outsiders_cannot(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)
    asset = upload(api, owner, project["id"]).json()

    fetched = api.get(
        f"/v1/projects/{project['id']}/assets/{asset['id']}/content",
        headers=auth(owner),
    )
    assert fetched.status_code == 200
    assert fetched.headers["content-type"].startswith("image/png")
    assert Image.open(BytesIO(fetched.content)).size == (8, 8)

    stranger = register(api, "stranger@example.com")
    denied = api.get(
        f"/v1/projects/{project['id']}/assets/{asset['id']}/content",
        headers=auth(stranger),
    )
    assert denied.status_code == 403

    missing = api.get(
        f"/v1/projects/{project['id']}/assets/does-not-exist/content",
        headers=auth(owner),
    )
    assert missing.status_code == 404


def test_soft_delete_removes_bytes_but_keeps_a_tombstone(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)
    asset = upload(api, owner, project["id"]).json()

    deleted = api.request(
        "DELETE",
        f"/v1/projects/{project['id']}/assets/{asset['id']}",
        headers=auth(owner),
        json={"idempotencyKey": "delete-1", "expectedStateVersion": 1, "data": {}},
    )
    assert deleted.status_code == 200
    assert deleted.json()["stateVersion"] == 2

    listed = api.get(f"/v1/projects/{project['id']}", headers=auth(owner)).json()
    assert listed["assets"][0]["deleted"] is True
    assert listed["assets"][0]["deletedAt"] is not None

    content = api.get(
        f"/v1/projects/{project['id']}/assets/{asset['id']}/content",
        headers=auth(owner),
    )
    assert content.status_code == 404


def test_analysis_readiness_ignores_deleted_assets(api):
    owner = register(api, "owner@example.com")
    project = create_project(api, owner)
    assets = [upload(api, owner, project["id"], key=f"u{i}", version=i).json() for i in range(3)]
    api.request(
        "DELETE",
        f"/v1/projects/{project['id']}/assets/{assets[0]['id']}",
        headers=auth(owner),
        json={"idempotencyKey": "delete-1", "expectedStateVersion": 3, "data": {}},
    )
    started = api.post(
        f"/v1/projects/{project['id']}/analysis-runs",
        headers=auth(owner),
        json={"idempotencyKey": "run-1", "expectedStateVersion": 4, "data": {}},
    )
    assert started.status_code == 409
    assert started.json()["error"]["code"] == "ASSET_COUNT_INVALID"
