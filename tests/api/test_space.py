"""Milestone 2: space persistence, versioning and role permissions.

The space draft is shared by the homeowner and the designer, but only the
homeowner may delete rooms or objects. Every substantive edit creates a new
immutable :class:`SpaceVersion`; a non-substantive edit creates none.
"""

import pytest
from fastapi.testclient import TestClient

HOMEOWNER = {"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"}
DESIGNER = {"X-Actor-Id": "designer-1", "X-Actor-Role": "designer"}
STRANGER = {"X-Actor-Id": "stranger-1", "X-Actor-Role": "homeowner"}


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


def space(client: TestClient, project_id: str, headers: dict[str, str] = HOMEOWNER) -> dict:
    response = client.get(f"/v1/projects/{project_id}/space", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def create_room(
    client: TestClient,
    project_id: str,
    *,
    key: str = "room-1",
    name: str = "客厅",
    width: float = 4000,
    depth: float = 5000,
    headers: dict[str, str] = HOMEOWNER,
    expected: int = 200,
):
    return write(
        client,
        "POST",
        f"/v1/projects/{project_id}/space/rooms",
        project_id,
        key,
        {"name": name, "roomType": "living_room", "width": width, "depth": depth},
        headers=headers,
        expected=expected,
    )


def test_a_new_project_has_no_space_and_keeps_the_original_brief_flow(client, ready_project):
    snapshot = space(client, ready_project)
    assert snapshot["version"] is None
    assert snapshot["contentHash"] is None
    assert snapshot["plan"] is None
    # The brief-only flow still works: state loads and no space is fabricated.
    state = client.get(f"/v1/projects/{ready_project}/state", headers=HOMEOWNER)
    assert state.status_code == 200
    assert state.json()["projectState"]["spaceVersions"] == []
    assert client.get(f"/v1/projects/{ready_project}/space/versions", headers=HOMEOWNER).json()[
        "versions"
    ] == []


def test_creating_a_rectangular_room_persists_stable_ids_and_a_version(client, ready_project):
    created = create_room(client, ready_project).json()

    assert created["version"] == 1
    assert created["source"] == "rectangular_dimensions"
    assert created["previousVersion"] is None
    room = created["plan"]["rooms"][0]
    assert room["name"] == "客厅"
    assert room["id"].startswith("room-")
    assert room["floor"]["id"] == f"floor-{room['id']}"
    assert [wall["id"] for wall in room["walls"]] == [
        f"wall-{room['id']}-north",
        f"wall-{room['id']}-east",
        f"wall-{room['id']}-south",
        f"wall-{room['id']}-west",
    ]

    reloaded = space(client, ready_project)
    assert reloaded["version"] == 1
    assert reloaded["contentHash"] == created["contentHash"]
    assert reloaded["plan"] == created["plan"]


def test_the_designer_can_edit_the_space_draft_but_not_delete_it(client, ready_project):
    created = create_room(client, ready_project, headers=DESIGNER).json()
    room_id = created["plan"]["rooms"][0]["id"]

    edited = write(
        client,
        "PATCH",
        f"/v1/projects/{ready_project}/space/rooms/{room_id}",
        ready_project,
        "designer-rename",
        {"name": "会客厅"},
        headers=DESIGNER,
    )
    assert edited.json()["plan"]["rooms"][0]["name"] == "会客厅"

    denied = write(
        client,
        "DELETE",
        f"/v1/projects/{ready_project}/space/rooms/{room_id}",
        ready_project,
        "designer-delete",
        {},
        headers=DESIGNER,
        expected=403,
    )
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    deleted = write(
        client,
        "DELETE",
        f"/v1/projects/{ready_project}/space/rooms/{room_id}",
        ready_project,
        "owner-delete",
        {},
    ).json()
    assert deleted["plan"]["rooms"] == []


def test_patching_a_room_size_regenerates_its_walls(client, ready_project):
    created = create_room(client, ready_project).json()
    room_id = created["plan"]["rooms"][0]["id"]

    updated = write(
        client,
        "PATCH",
        f"/v1/projects/{ready_project}/space/rooms/{room_id}",
        ready_project,
        "resize",
        {"width": 6000, "depth": 7000},
    ).json()

    assert updated["version"] == 2
    assert updated["previousVersion"] == 1
    room = updated["plan"]["rooms"][0]
    assert room["size"] == {"width": 6000, "depth": 7000}
    north = next(wall for wall in room["walls"] if wall["id"].endswith("north"))
    assert north["start"] == {"x": 0, "y": 0}
    assert north["end"] == {"x": 6000, "y": 0}


def test_object_patch_accepts_only_whitelisted_fields(client, ready_project):
    created = create_room(client, ready_project).json()
    room_id = created["plan"]["rooms"][0]["id"]
    object_created = write(
        client,
        "POST",
        f"/v1/projects/{ready_project}/space/objects",
        ready_project,
        "object-1",
        {"roomId": room_id, "kind": "furniture", "label": "沙发"},
    ).json()
    object_id = object_created["plan"]["objects"][0]["id"]

    updated = write(
        client,
        "PATCH",
        f"/v1/projects/{ready_project}/space/objects/{object_id}",
        ready_project,
        "move-object",
        {"label": "布艺沙发"},
    ).json()
    assert updated["plan"]["objects"][0]["label"] == "布艺沙发"

    # A whole-plan overwrite must not be accepted through the object endpoint.
    rejected = write(
        client,
        "PATCH",
        f"/v1/projects/{ready_project}/space/objects/{object_id}",
        ready_project,
        "overwrite",
        {"plan": {"rooms": []}},
        expected=400,
    )
    assert rejected.json()["error"]["code"] == "INVALID_REQUEST"


def test_edits_are_isolated_between_projects(client, ready_project):
    other = _second_project(client)
    created = create_room(client, ready_project).json()
    room_id = created["plan"]["rooms"][0]["id"]

    write(
        client,
        "PATCH",
        f"/v1/projects/{other}/space/rooms/{room_id}",
        other,
        "cross-project",
        {"name": "偷来的房间"},
        expected=404,
    )
    assert space(client, other)["version"] is None


def test_non_members_are_forbidden(client, ready_project):
    response = client.get(f"/v1/projects/{ready_project}/space", headers=STRANGER)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_stale_state_version_is_rejected(client, ready_project):
    create_room(client, ready_project)
    response = client.post(
        f"/v1/projects/{ready_project}/space/rooms",
        headers=HOMEOWNER,
        json={
            "idempotencyKey": "stale",
            "expectedStateVersion": 0,
            "data": {"name": "客厅", "width": 4000, "depth": 5000},
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STATE_VERSION_STALE"


def test_idempotency_replays_and_conflicts_on_different_content(client, ready_project):
    version = client.get(f"/v1/projects/{ready_project}", headers=HOMEOWNER).json()["stateVersion"]
    path = f"/v1/projects/{ready_project}/space/rooms"
    envelope = {
        "idempotencyKey": "room-replay",
        "expectedStateVersion": version,
        "data": {"name": "客厅", "width": 4000, "depth": 5000},
    }
    first = client.post(path, headers=HOMEOWNER, json=envelope)
    assert first.status_code == 200, first.text
    replay = client.post(path, headers=HOMEOWNER, json=envelope)
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert len(space(client, ready_project)["plan"]["rooms"]) == 1

    conflict = client.post(
        path,
        headers=HOMEOWNER,
        json={
            "idempotencyKey": "room-replay",
            "expectedStateVersion": first.json()["stateVersion"],
            "data": {"name": "客厅", "width": 3000, "depth": 3000},
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_versions_are_immutable_and_listed_newest_first(client, ready_project):
    created = create_room(client, ready_project).json()
    room_id = created["plan"]["rooms"][0]["id"]
    write(
        client,
        "PATCH",
        f"/v1/projects/{ready_project}/space/rooms/{room_id}",
        ready_project,
        "rename",
        {"name": "会客厅"},
    )
    listing = client.get(
        f"/v1/projects/{ready_project}/space/versions", headers=HOMEOWNER
    ).json()
    assert [item["version"] for item in listing["versions"]] == [2, 1]
    assert listing["versions"][1]["contentHash"] == created["contentHash"]


def test_a_no_op_patch_does_not_create_a_version(client, ready_project):
    created = create_room(client, ready_project).json()
    room_id = created["plan"]["rooms"][0]["id"]
    unchanged = write(
        client,
        "PATCH",
        f"/v1/projects/{ready_project}/space/rooms/{room_id}",
        ready_project,
        "noop",
        {"name": "客厅"},
    ).json()
    assert unchanged["version"] == 1
    listing = client.get(
        f"/v1/projects/{ready_project}/space/versions", headers=HOMEOWNER
    ).json()
    assert [item["version"] for item in listing["versions"]] == [1]


def test_materials_catalogue_is_available_and_target_filtered(client, ready_project):
    all_options = client.get(f"/v1/projects/{ready_project}/materials", headers=DESIGNER).json()
    assert any(item["id"] == "floor.engineered-oak" for item in all_options["options"])

    floor_only = client.get(
        f"/v1/projects/{ready_project}/materials", params={"target": "floor"}, headers=DESIGNER
    ).json()
    assert all("floor" in item["targets"] for item in floor_only["options"])
    assert all(
        "wall" not in item["targets"] or "floor" in item["targets"]
        for item in floor_only["options"]
    )


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("ALIGNSPACE_AUTH_SECRET", "test-secret-for-authentication-with-enough-entropy")
    monkeypatch.setenv("ALIGNSPACE_DEV", "1")
    from alignspace.main import create_app

    app = create_app(
        database_url=f"sqlite:///{tmp_path / 'space-auth.db'}",
        checkpoint_path=str(tmp_path / "space-checkpoints.db"),
    )
    with TestClient(app, headers={"Origin": "http://localhost:5173"}) as test_client:
        yield test_client


def test_space_requires_authentication(auth_client):
    # The real application verifies the bearer token before any membership check.
    response = auth_client.get("/v1/projects/anything/space")
    assert response.status_code == 401


def _second_project(client: TestClient) -> str:
    response = client.post(
        "/v1/projects",
        headers=HOMEOWNER,
        json={"roomType": "living_room", "budgetBand": "15k_to_30k_sgd", "consent": True},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]
