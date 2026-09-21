from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image

HOMEOWNER = {"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"}
DESIGNER = {"X-Actor-Id": "designer-1", "X-Actor-Role": "designer"}
DESCRIPTION = "喜欢床的颜色和样式"


def png(colour: str = "red") -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), colour).save(buffer, format="PNG")
    return buffer.getvalue()


def seed_assets(
    client: TestClient, project_id: str, count: int = 3
) -> tuple[list[str], int]:
    version = 0
    asset_ids: list[str] = []
    for index in range(count):
        response = client.post(
            f"/v1/projects/{project_id}/assets",
            headers=HOMEOWNER,
            data={"expectedStateVersion": str(version), "idempotencyKey": f"seed-{index}"},
            files={"file": (f"room-{index}.png", png(), "image/png")},
        )
        assert response.status_code == 201, response.text
        version = response.json()["stateVersion"]
        asset_ids.append(response.json()["id"])
    return asset_ids, version


def board(client: TestClient, project_id: str, headers: dict[str, str] = HOMEOWNER) -> dict:
    response = client.get(
        f"/v1/projects/{project_id}/preference-analyses", headers=headers
    )
    assert response.status_code == 200, response.text
    return response.json()


def write(
    client: TestClient,
    method: str,
    path: str,
    project_id: str,
    key: str,
    data: dict,
    *,
    headers: dict[str, str] = HOMEOWNER,
    expected: int = 200,
):
    version = client.get(f"/v1/projects/{project_id}", headers=headers).json()["stateVersion"]
    response = client.request(
        method,
        path,
        headers=headers,
        json={"idempotencyKey": key, "expectedStateVersion": version, "data": data},
    )
    assert response.status_code == expected, response.text
    return response


def run_analysis(
    client: TestClient,
    project_id: str,
    asset_ids: list[str],
    *,
    key: str = "analysis-1",
    description: str = DESCRIPTION,
    headers: dict[str, str] = HOMEOWNER,
    expected: int = 202,
):
    return write(
        client,
        "POST",
        f"/v1/projects/{project_id}/preference-analyses",
        project_id,
        key,
        {"assetIds": asset_ids, "description": description},
        headers=headers,
        expected=expected,
    )


def flatten(payload: dict) -> list[dict]:
    return [candidate for run in payload["runs"] for entry in run["entries"] for candidate in entry["candidates"]]


def candidate_id(payload: dict, dimension: str) -> str:
    return next(item["id"] for item in flatten(payload) if item["dimension"] == dimension)


def test_analysis_produces_candidates_without_writing_formal_preferences(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    response = run_analysis(client, ready_project, asset_ids)
    payload = response.json()

    assert len(payload["runs"]) == 1
    run = payload["runs"][0]
    assert run["providerMode"] == "mock"
    assert run["status"] == "completed"
    assert run["stale"] is False
    dimensions = {item["dimension"] for item in flatten(payload)}
    assert dimensions == {"colour", "style"}
    assert all(item["status"] == "proposed" for item in flatten(payload))

    state = client.get(f"/v1/projects/{ready_project}/state", headers=HOMEOWNER).json()
    assert state["projectState"]["attributes"] == []


def test_only_the_homeowner_can_run_analysis_or_decide(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    denied = run_analysis(client, ready_project, asset_ids, headers=DESIGNER, expected=403)
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    run_analysis(client, ready_project, asset_ids)
    identifier = candidate_id(board(client, ready_project), "colour")
    denied = write(
        client,
        "POST",
        f"/v1/projects/{ready_project}/candidates/{identifier}/confirm",
        ready_project,
        "designer-confirm",
        {},
        headers=DESIGNER,
        expected=403,
    )
    assert denied.json()["error"]["code"] == "FORBIDDEN"


def test_the_designer_can_read_the_candidate_board(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    run_analysis(client, ready_project, asset_ids)
    payload = board(client, ready_project, DESIGNER)
    assert len(payload["runs"]) == 1
    assert flatten(payload)


def test_confirming_a_candidate_writes_exactly_one_formal_preference(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    run_analysis(client, ready_project, asset_ids)
    identifier = candidate_id(board(client, ready_project), "colour")

    confirmed = write(
        client,
        "POST",
        f"/v1/projects/{ready_project}/candidates/{identifier}/confirm",
        ready_project,
        "confirm-1",
        {},
    ).json()
    chosen = next(item for item in flatten(confirmed) if item["id"] == identifier)
    assert chosen["status"] == "confirmed"
    assert chosen["attributeId"] == f"pref-{identifier}"

    state = client.get(f"/v1/projects/{ready_project}/state", headers=HOMEOWNER).json()
    attributes = state["projectState"]["attributes"]
    assert [item["id"] for item in attributes] == [f"pref-{identifier}"]
    assert attributes[0]["status"] == "confirmed"
    assert attributes[0]["value"] == chosen["confirmedValue"]

    # Repeating the decision must not create a second preference.
    write(
        client,
        "POST",
        f"/v1/projects/{ready_project}/candidates/{identifier}/confirm",
        ready_project,
        "confirm-2",
        {},
    )
    state = client.get(f"/v1/projects/{ready_project}/state", headers=HOMEOWNER).json()
    assert len(state["projectState"]["attributes"]) == 1


def test_same_idempotency_key_replays_without_a_second_write(client, ready_project):
    asset_ids, version = seed_assets(client, ready_project)
    envelope = {
        "idempotencyKey": "analysis-1",
        "expectedStateVersion": version,
        "data": {"assetIds": asset_ids, "description": DESCRIPTION},
    }
    path = f"/v1/projects/{ready_project}/preference-analyses"
    first = client.post(path, headers=HOMEOWNER, json=envelope)
    assert first.status_code == 202, first.text

    # An identical envelope (same key and same expected version) is a replay.
    replay = client.post(path, headers=HOMEOWNER, json=envelope)
    assert replay.status_code == 202, replay.text
    assert replay.json() == first.json()
    assert len(board(client, ready_project)["runs"]) == 1


def test_reusing_a_key_with_different_content_conflicts(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    run_analysis(client, ready_project, asset_ids)
    conflict = run_analysis(
        client, ready_project, asset_ids, description="喜欢地板的铺设方式", expected=409
    )
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_reanalysis_preserves_a_confirmed_candidate(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    run_analysis(client, ready_project, asset_ids)
    identifier = candidate_id(board(client, ready_project), "colour")
    write(
        client,
        "POST",
        f"/v1/projects/{ready_project}/candidates/{identifier}/confirm",
        ready_project,
        "confirm-1",
        {},
    )

    run_analysis(client, ready_project, asset_ids, key="analysis-2")
    payload = board(client, ready_project)
    assert len(payload["runs"]) == 2
    preserved = next(item for item in flatten(payload) if item["id"] == identifier)
    assert preserved["status"] == "confirmed"
    assert preserved["confirmedValue"] is not None


def test_deleting_an_entry_keeps_confirmed_preferences(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    run_analysis(client, ready_project, asset_ids)
    payload = board(client, ready_project)
    entry_id = payload["runs"][0]["entries"][0]["id"]
    identifier = candidate_id(payload, "colour")
    write(
        client,
        "POST",
        f"/v1/projects/{ready_project}/candidates/{identifier}/confirm",
        ready_project,
        "confirm-1",
        {},
    )

    after = write(
        client,
        "DELETE",
        f"/v1/projects/{ready_project}/design-entries/{entry_id}",
        ready_project,
        "delete-entry-1",
        {},
    ).json()
    assert all(entry["id"] != entry_id for run in after["runs"] for entry in run["entries"])
    state = client.get(f"/v1/projects/{ready_project}/state", headers=HOMEOWNER).json()
    assert [item["id"] for item in state["projectState"]["attributes"]] == [f"pref-{identifier}"]


def test_rejecting_a_candidate_writes_no_preference(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    run_analysis(client, ready_project, asset_ids)
    identifier = candidate_id(board(client, ready_project), "style")
    payload = write(
        client,
        "POST",
        f"/v1/projects/{ready_project}/candidates/{identifier}/reject",
        ready_project,
        "reject-1",
        {},
    ).json()
    rejected = next(item for item in flatten(payload) if item["id"] == identifier)
    assert rejected["status"] == "rejected"
    state = client.get(f"/v1/projects/{ready_project}/state", headers=HOMEOWNER).json()
    assert state["projectState"]["attributes"] == []


def test_deleting_the_source_image_blocks_later_confirmation(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    run_analysis(client, ready_project, asset_ids)
    payload = board(client, ready_project)
    entry = next(item for item in payload["runs"][0]["entries"] if item["sourceAssetId"])
    identifier = entry["candidates"][0]["id"]

    write(
        client,
        "DELETE",
        f"/v1/projects/{ready_project}/assets/{entry['sourceAssetId']}",
        ready_project,
        "delete-source",
        {},
    )

    blocked = write(
        client,
        "POST",
        f"/v1/projects/{ready_project}/candidates/{identifier}/confirm",
        ready_project,
        "confirm-after-delete",
        {},
        expected=409,
    )
    assert blocked.json()["error"]["code"] == "CANDIDATE_STATE_INVALID"
    assert board(client, ready_project)["runs"][0]["stale"] is True


def test_stale_state_version_is_rejected(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    response = client.post(
        f"/v1/projects/{ready_project}/preference-analyses",
        headers=HOMEOWNER,
        json={"idempotencyKey": "stale", "expectedStateVersion": 0, "data": {
            "assetIds": asset_ids, "description": DESCRIPTION,
        }},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_VERSION_STALE"


def test_analysis_requires_a_description(client, ready_project):
    asset_ids, _ = seed_assets(client, ready_project)
    response = run_analysis(
        client, ready_project, asset_ids, description="   ", expected=409
    )
    assert response.json()["error"]["code"] == "CANDIDATE_STATE_INVALID"


def test_analysis_rejects_unknown_images(client, ready_project):
    seed_assets(client, ready_project)
    response = run_analysis(client, ready_project, ["not-an-asset"], expected=404)
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_deleting_the_source_image_marks_the_entry_source_deleted(
    client, ready_project
):
    asset_ids, _ = seed_assets(client, ready_project)
    run_analysis(client, ready_project, asset_ids)
    entry = next(
        item for item in board(client, ready_project)["runs"][0]["entries"]
    )
    assert entry["status"] == "open"
    assert entry["sourceAvailable"] is True

    write(
        client,
        "DELETE",
        f"/v1/projects/{ready_project}/assets/{entry['sourceAssetId']}",
        ready_project,
        "delete-source-entry",
        {},
    )

    after = next(item for item in board(client, ready_project)["runs"][0]["entries"])
    assert after["status"] == "source_deleted"
    assert after["sourceAvailable"] is False
