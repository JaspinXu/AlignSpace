"""Restart recovery: rebuild the application over the same business database,
checkpoint and asset directory, then continue the workflow and retries."""

from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from alignspace.auth.config import AuthConfig

ORIGIN = {"Origin": "http://localhost:5173"}
PASSWORD = "a sufficiently long password"
SECRET = "trial-restart-secret-that-is-long-enough"


def _image_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "red").save(buffer, format="PNG")
    return buffer.getvalue()


class Trial:
    """Starts and stops real applications over one fixed data set."""

    def __init__(self, database, checkpoint):
        self.database_url = f"sqlite:///{database}"
        self.checkpoint = str(checkpoint)
        self.client: TestClient | None = None

    def start(self) -> TestClient:
        from alignspace.main import create_app

        app = create_app(
            database_url=self.database_url,
            checkpoint_path=self.checkpoint,
            auth_config=AuthConfig(secret=SECRET, secure_cookie=False),
        )
        self.client = TestClient(app, headers=ORIGIN)
        self.client.__enter__()
        return self.client

    def stop(self) -> None:
        if self.client is not None:
            self.client.__exit__(None, None, None)
            self.client = None


@pytest.fixture
def trial(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIGNSPACE_ASSET_DIR", str(tmp_path / "assets"))
    handle = Trial(tmp_path / "trial.db", tmp_path / "checkpoints.db")
    yield handle
    handle.stop()


def _register(client, email):
    response = client.post("/v1/auth/register", json={"email": email, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def _login(client, email):
    response = client.post("/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()


def _auth(user):
    return {"Authorization": f"Bearer {user['accessToken']}"}


def _version(client, project_id, user):
    response = client.get(f"/v1/projects/{project_id}", headers=_auth(user))
    assert response.status_code == 200, response.text
    return response.json()["stateVersion"]


def _project_state(client, project_id, user):
    return client.get(f"/v1/projects/{project_id}/state", headers=_auth(user)).json()["projectState"]


def _write(client, method, path, project_id, user, key, data, expected=(200, 201)):
    response = client.request(
        method,
        path,
        headers=_auth(user),
        json={
            "idempotencyKey": key,
            "expectedStateVersion": _version(client, project_id, user),
            "data": data,
        },
    )
    assert response.status_code in expected, response.text
    return response.json()


def _bootstrap(client):
    owner = _register(client, "owner@example.com")
    designer = _register(client, "designer@example.com")
    project = client.post(
        "/v1/projects",
        headers=_auth(owner),
        json={"roomType": "living_room", "budgetBand": "15k_to_30k_sgd", "consent": True},
    ).json()
    project_id = project["id"]
    code = client.post(
        f"/v1/projects/{project_id}/join-code", headers=_auth(owner)
    ).json()["code"]
    joined = client.post("/v1/projects/join", headers=_auth(designer), json={"code": code})
    assert joined.status_code == 200, joined.text
    version = 0
    for index in range(3):
        upload = client.post(
            f"/v1/projects/{project_id}/assets",
            headers=_auth(owner),
            data={"expectedStateVersion": str(version), "idempotencyKey": f"asset-{index}"},
            files={"file": (f"room-{index}.png", _image_bytes(), "image/png")},
        )
        assert upload.status_code == 201, upload.text
        version = upload.json()["stateVersion"]
    return owner, designer, project_id


def _start_analysis(client, project_id, owner):
    return _write(
        client,
        "POST",
        f"/v1/projects/{project_id}/analysis-runs",
        project_id,
        owner,
        "analysis-1",
        {},
        expected=(202,),
    )


def _answer_broad(client, project_id, owner, question):
    parts = [
        {"assetId": option["assetId"], "targetElement": option["targetElement"]}
        for option in question["options"]
    ]
    return _write(
        client,
        "POST",
        f"/v1/projects/{project_id}/questions/{question['id']}/answer",
        project_id,
        owner,
        "answer-broad",
        {"parts": parts},
        expected=(202,),
    )


def _answer_details(client, project_id, owner, response):
    for _ in range(12):
        pending = response.get("pendingQuestion")
        if not pending or pending.get("kind") != "detail":
            break
        selection = [
            {"attributeId": option["attributeId"], "decision": "confirmed", "value": option["value"]}
            for option in pending["options"]
        ]
        response = _write(
            client,
            "POST",
            f"/v1/projects/{project_id}/questions/{pending['id']}/answer",
            project_id,
            owner,
            f"detail-{pending['id']}",
            {"selection": selection},
            expected=(202,),
        )
    return response


def _explicit_preferences(client, project_id, owner):
    for dimension, value in {
        "style": "warm modern",
        "layout": "clear conversational seating",
        "furniture": "compact rounded furniture",
        "mood": "calm and welcoming",
        "function": "conversation and reading",
    }.items():
        _write(
            client,
            "PATCH",
            f"/v1/projects/{project_id}/attributes/manual-{dimension}",
            project_id,
            owner,
            f"manual-{dimension}",
            {
                "targetElement": "living_room",
                "dimension": dimension,
                "value": value,
                "status": "confirmed",
            },
        )


def _to_designer_wait(client, project_id, owner):
    started = _start_analysis(client, project_id, owner)
    broad = _answer_broad(client, project_id, owner, started["pendingQuestion"])
    _answer_details(client, project_id, owner, broad)
    _explicit_preferences(client, project_id, owner)
    state = client.get(f"/v1/projects/{project_id}/state", headers=_auth(owner)).json()[
        "projectState"
    ]
    assert state["waitReason"] == "designer", state["waitReason"]
    return state


def _to_awaiting_approval(client, project_id, owner, designer):
    _to_designer_wait(client, project_id, owner)
    _write(
        client,
        "POST",
        f"/v1/projects/{project_id}/constraints",
        project_id,
        designer,
        "constraint-advisory",
        {
            "category": "budget",
            "statement": "预算档位已在项目信息中确认",
            "severity": "advisory",
            "appliesTo": "living_room",
        },
    )
    reviewed = _write(
        client,
        "POST",
        f"/v1/projects/{project_id}/designer-reviews",
        project_id,
        designer,
        "review-1",
        {"note": "确认约束"},
    )
    assert reviewed["status"] == "awaiting_approval", reviewed["status"]
    return reviewed


def test_restart_at_homeowner_wait_continues(trial):
    client = trial.start()
    owner, designer, project_id = _bootstrap(client)
    started = _start_analysis(client, project_id, owner)
    pending_question = started["pendingQuestion"]
    version = started["stateVersion"]
    assets = client.get(f"/v1/projects/{project_id}", headers=_auth(owner)).json()["assets"]
    trial.stop()

    client = trial.start()
    owner = _login(client, "owner@example.com")
    designer = _login(client, "designer@example.com")
    snapshot = client.get(f"/v1/projects/{project_id}/state", headers=_auth(owner)).json()
    assert snapshot["pendingQuestion"]["id"] == pending_question["id"]
    assert snapshot["projectState"]["stateVersion"] == version
    assert snapshot["project"]["role"] == "homeowner"
    member = client.get(f"/v1/projects/{project_id}", headers=_auth(designer))
    assert member.status_code == 200
    assert [item["id"] for item in member.json()["assets"]] == [
        item["id"] for item in assets
    ]
    content = client.get(
        f"/v1/projects/{project_id}/assets/{assets[0]['id']}/content", headers=_auth(owner)
    )
    assert content.status_code == 200
    assert content.headers["content-type"].startswith("image/png")

    broad = _answer_broad(client, project_id, owner, pending_question)
    _answer_details(client, project_id, owner, broad)
    _explicit_preferences(client, project_id, owner)
    state = client.get(f"/v1/projects/{project_id}/state", headers=_auth(owner)).json()[
        "projectState"
    ]
    assert state["waitReason"] == "designer"
    assert len([item for item in state["questions"] if item["id"] == "question-liked-elements"]) == 1


def test_restart_at_designer_wait_continues(trial):
    client = trial.start()
    owner, designer, project_id = _bootstrap(client)
    _to_designer_wait(client, project_id, owner)
    _write(
        client,
        "POST",
        f"/v1/projects/{project_id}/constraints",
        project_id,
        designer,
        "constraint-advisory",
        {
            "category": "budget",
            "statement": "预算档位已在项目信息中确认",
            "severity": "advisory",
            "appliesTo": "living_room",
        },
    )
    before = _project_state(client, project_id, owner)
    trial.stop()

    client = trial.start()
    owner = _login(client, "owner@example.com")
    designer = _login(client, "designer@example.com")
    after = _project_state(client, project_id, owner)
    assert after["waitReason"] == "designer"
    assert after["stateVersion"] == before["stateVersion"]
    assert sorted(after["attributes"], key=lambda item: item["id"]) == sorted(
        before["attributes"], key=lambda item: item["id"]
    )
    assert sorted(after["constraints"], key=lambda item: item["id"]) == sorted(
        before["constraints"], key=lambda item: item["id"]
    )

    reviewed = _write(
        client,
        "POST",
        f"/v1/projects/{project_id}/designer-reviews",
        project_id,
        designer,
        "review-1",
        {"note": "确认约束"},
    )
    assert reviewed["status"] == "awaiting_approval"


def test_restart_at_awaiting_approval_continues(trial):
    client = trial.start()
    owner, designer, project_id = _bootstrap(client)
    _to_awaiting_approval(client, project_id, owner, designer)
    briefs = client.get(
        f"/v1/projects/{project_id}/briefs/latest", headers=_auth(owner)
    ).json()
    trial.stop()

    client = trial.start()
    owner = _login(client, "owner@example.com")
    designer = _login(client, "designer@example.com")
    restarted = client.get(
        f"/v1/projects/{project_id}/briefs/latest", headers=_auth(owner)
    ).json()
    assert restarted["version"] == briefs["version"]
    assert restarted["contentHash"] == briefs["contentHash"]
    state = client.get(f"/v1/projects/{project_id}/state", headers=_auth(owner)).json()[
        "projectState"
    ]
    assert state["approvals"] == []

    first = _write(
        client,
        "POST",
        f"/v1/projects/{project_id}/briefs/{restarted['version']}/approvals",
        project_id,
        owner,
        "approve-owner",
        {"contentHash": restarted["contentHash"]},
    )
    assert first["status"] == "awaiting_approval"
    second = _write(
        client,
        "POST",
        f"/v1/projects/{project_id}/briefs/{restarted['version']}/approvals",
        project_id,
        designer,
        "approve-designer",
        {"contentHash": restarted["contentHash"]},
    )
    assert second["status"] == "approved"
    assert len(second["projectState"]["approvals"]) == 2


def test_delete_advance_recovery_survives_restart(trial, monkeypatch):
    client = trial.start()
    owner, _designer, project_id = _bootstrap(client)
    started = _start_analysis(client, project_id, owner)
    options = started["pendingQuestion"]["options"]
    first = options[0]
    second = next(
        option
        for option in options
        if option["assetId"] != first["assetId"]
        and option["targetElement"] != first["targetElement"]
    )
    broad = _write(
        client,
        "POST",
        f"/v1/projects/{project_id}/questions/{started['pendingQuestion']['id']}/answer",
        project_id,
        owner,
        "answer-broad",
        {
            "parts": [
                {"assetId": first["assetId"], "targetElement": first["targetElement"]},
                {"assetId": second["assetId"], "targetElement": second["targetElement"]},
            ]
        },
        expected=(202,),
    )
    detail = broad["pendingQuestion"]
    asset_to_delete = detail["options"][0]["assetId"]
    envelope = {
        "idempotencyKey": "delete-restart",
        "expectedStateVersion": _version(client, project_id, owner),
        "data": {},
    }
    url = f"/v1/projects/{project_id}/assets/{asset_to_delete}"

    def failing(project_id_arg, actor):
        raise RuntimeError("injected advance failure")

    container = client.app.state.container
    monkeypatch.setattr(container.workflow, "advance_interview", failing)
    with pytest.raises(RuntimeError):
        client.request("DELETE", url, headers=_auth(owner), json=envelope)
    trial.stop()

    client = trial.start()
    owner = _login(client, "owner@example.com")
    retried = client.request("DELETE", url, headers=_auth(owner), json=envelope)
    assert retried.status_code == 200, retried.text
    state = client.get(f"/v1/projects/{project_id}/state", headers=_auth(owner)).json()[
        "projectState"
    ]
    assert retried.json()["stateVersion"] == state["stateVersion"]
    following = client.get(
        f"/v1/projects/{project_id}/questions/next", headers=_auth(owner)
    )
    assert following.status_code == 200, following.text


def test_answer_retry_after_restart_returns_the_same_result(trial):
    client = trial.start()
    owner, _designer, project_id = _bootstrap(client)
    started = _start_analysis(client, project_id, owner)
    question = started["pendingQuestion"]
    parts = [
        {"assetId": option["assetId"], "targetElement": option["targetElement"]}
        for option in question["options"]
    ]
    envelope = {
        "idempotencyKey": "answer-retry",
        "expectedStateVersion": started["stateVersion"],
        "data": {"parts": parts},
    }
    url = f"/v1/projects/{project_id}/questions/{question['id']}/answer"
    first = client.request("POST", url, headers=_auth(owner), json=envelope)
    assert first.status_code == 202, first.text
    trial.stop()

    client = trial.start()
    owner = _login(client, "owner@example.com")
    retry = client.request("POST", url, headers=_auth(owner), json=envelope)
    assert retry.status_code == 202, retry.text
    assert retry.json() == first.json()
    state = client.get(f"/v1/projects/{project_id}/state", headers=_auth(owner)).json()[
        "projectState"
    ]
    assert state["stateVersion"] == first.json()["stateVersion"]


def test_delete_finalise_failure_completes_after_restart(trial, monkeypatch):
    from alignspace.persistence.repository import IdempotencyRepository

    client = trial.start()
    owner, _designer, project_id = _bootstrap(client)
    started = _start_analysis(client, project_id, owner)
    options = started["pendingQuestion"]["options"]
    first = options[0]
    second = next(
        option
        for option in options
        if option["assetId"] != first["assetId"]
        and option["targetElement"] != first["targetElement"]
    )
    broad = _write(
        client,
        "POST",
        f"/v1/projects/{project_id}/questions/{started['pendingQuestion']['id']}/answer",
        project_id,
        owner,
        "answer-broad",
        {
            "parts": [
                {"assetId": first["assetId"], "targetElement": first["targetElement"]},
                {"assetId": second["assetId"], "targetElement": second["targetElement"]},
            ]
        },
        expected=(202,),
    )
    asset_to_delete = broad["pendingQuestion"]["options"][0]["assetId"]
    envelope = {
        "idempotencyKey": "delete-finalise-restart",
        "expectedStateVersion": _version(client, project_id, owner),
        "data": {},
    }
    url = f"/v1/projects/{project_id}/assets/{asset_to_delete}"

    original = IdempotencyRepository.replace_response
    calls = {"count": 0}

    def flaky(self, *args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("injected finalise failure")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(IdempotencyRepository, "replace_response", flaky)
    with pytest.raises(RuntimeError):
        client.request("DELETE", url, headers=_auth(owner), json=envelope)
    advanced = _version(client, project_id, owner)
    trial.stop()

    client = trial.start()
    owner = _login(client, "owner@example.com")
    retried = client.request("DELETE", url, headers=_auth(owner), json=envelope)
    assert retried.status_code == 200, retried.text
    assert retried.json()["stateVersion"] == advanced
    state = _project_state(client, project_id, owner)
    assert state["stateVersion"] == advanced
    questions = len(state["questions"])

    # A completed replay must not advance again or add versions/questions.
    replay = client.request("DELETE", url, headers=_auth(owner), json=envelope)
    assert replay.json() == retried.json()
    after = _project_state(client, project_id, owner)
    assert after["stateVersion"] == advanced
    assert len(after["questions"]) == questions


def test_restart_preserves_multiple_brief_versions(trial):
    client = trial.start()
    owner, designer, project_id = _bootstrap(client)
    _to_awaiting_approval(client, project_id, owner, designer)
    latest = client.get(
        f"/v1/projects/{project_id}/briefs/latest", headers=_auth(owner)
    ).json()
    payload = dict(latest["payload"])
    payload["goals"] = ["保留祖传书柜"]
    edited = _write(
        client,
        "PATCH",
        f"/v1/projects/{project_id}/briefs/{latest['version']}",
        project_id,
        owner,
        "edit-1",
        {"payload": payload},
    )
    assert edited["version"] == 2
    before = _project_state(client, project_id, owner)
    trial.stop()

    client = trial.start()
    owner = _login(client, "owner@example.com")
    after = _project_state(client, project_id, owner)
    assert len(after["briefVersions"]) == 2
    assert sorted((item["version"], item["contentHash"]) for item in after["briefVersions"]) == sorted(
        (item["version"], item["contentHash"]) for item in before["briefVersions"]
    )
    assert sorted(item["id"] for item in after["attributes"]) == sorted(
        item["id"] for item in before["attributes"]
    )
    assert sorted(item["value"] for item in after["attributes"]) == sorted(
        item["value"] for item in before["attributes"]
    )
    assert sorted(item["status"] for item in after["attributes"]) == sorted(
        item["status"] for item in before["attributes"]
    )
    assert sorted(item["statement"] for item in after["constraints"]) == sorted(
        item["statement"] for item in before["constraints"]
    )
    restored = client.get(
        f"/v1/projects/{project_id}/briefs/latest", headers=_auth(owner)
    ).json()
    assert restored["payload"]["goals"] == ["保留祖传书柜"]
