from fastapi.testclient import TestClient

from app.main import create_app


def make_client(tmp_path):
    return TestClient(create_app(tmp_path / "test.db", tmp_path / "uploads"))


def test_health_and_project_creation(tmp_path):
    client = make_client(tmp_path)
    assert client.get("/health").json()["status"] == "ok"
    response = client.post(
        "/api/projects",
        json={"name": "Haven", "housingType": "HDB", "budgetBand": "15k_to_30k_sgd"},
    )
    assert response.status_code == 201
    project = response.json()
    assert project["nextQuestion"] is not None
    assert project["stateVersion"] == 1


def test_optimistic_state_version_rejects_stale_writes(tmp_path):
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={"name": "Haven", "budgetBand": "under_15k_sgd"},
    ).json()
    path = f"/api/projects/{project['id']}/preferences"
    first = client.put(
        path,
        json={"goals": ["Relax"], "antiPreferences": [], "expectedStateVersion": 1},
    )
    assert first.status_code == 200
    stale = client.put(
        path,
        json={"goals": ["Host"], "antiPreferences": [], "expectedStateVersion": 1},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "BRIEF_VERSION_STALE"


def test_demo_completes_and_exports_a_valid_brief(tmp_path):
    client = make_client(tmp_path)
    project = client.post("/api/demo", json={}).json()
    assert project["readiness"]["readyForApproval"] is True
    brief_response = client.get(f"/api/projects/{project['id']}/brief")
    assert brief_response.status_code == 200
    assert brief_response.json()["completeness"] == 1


def test_reference_upload_and_conservative_analysis(tmp_path):
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={"name": "Reference project", "budgetBand": "under_15k_sgd"},
    ).json()
    upload = client.post(
        f"/api/projects/{project['id']}/references",
        files={"file": ("inspiration.png", b"\x89PNG\r\n\x1a\nexample", "image/png")},
        data={"note": "I like the Japandi feeling and light oak"},
    )
    assert upload.status_code == 201

    analysed = client.post(f"/api/projects/{project['id']}/analysis-runs", json={})
    assert analysed.status_code == 200
    proposals = [item for item in analysed.json()["attributes"] if item["status"] == "proposed"]
    assert {(item["dimension"], item["value"]) for item in proposals} == {
        ("style", "japandi"),
        ("material", "light_oak"),
    }


def test_upload_rejects_mismatched_image_content(tmp_path):
    client = make_client(tmp_path)
    project = client.post(
        "/api/projects",
        json={"name": "Unsafe upload", "budgetBand": "under_15k_sgd"},
    ).json()
    response = client.post(
        f"/api/projects/{project['id']}/references",
        files={"file": ("fake.png", b"not an image", "image/png")},
    )
    assert response.status_code == 422
