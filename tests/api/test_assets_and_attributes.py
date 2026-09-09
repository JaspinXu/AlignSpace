def _headers(actor_id: str = "homeowner-1", role: str = "homeowner") -> dict[str, str]:
    return {"X-Actor-Id": actor_id, "X-Actor-Role": role}


def _asset_envelope(key: str, version: int) -> dict[str, object]:
    return {
        "idempotencyKey": key,
        "expectedStateVersion": version,
        "data": {
            "fixtureId": "living-room-1",
            "mediaType": "image/jpeg",
            "sizeBytes": 1024,
        },
    }


def test_asset_registration_requires_consent(client, project_without_consent) -> None:
    response = client.post(
        f"/v1/projects/{project_without_consent}/assets",
        headers=_headers(),
        json=_asset_envelope("asset-1", 0),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSENT_REQUIRED"


def test_register_and_delete_asset_are_versioned_and_idempotent(
    client,
    ready_project,
    monkeypatch,
) -> None:
    project_id = ready_project
    first = client.post(
        f"/v1/projects/{project_id}/assets",
        headers=_headers(),
        json=_asset_envelope("asset-create", 0),
    )
    replay = client.post(
        f"/v1/projects/{project_id}/assets",
        headers=_headers(),
        json=_asset_envelope("asset-create", 0),
    )

    assert first.status_code == 201
    assert replay.json() == first.json()
    assert first.json()["stateVersion"] == 1

    asset_id = first.json()["id"]
    listed = client.get(f"/v1/projects/{project_id}", headers=_headers())
    assert listed.json()["assets"] == [
        {
            "id": asset_id,
            "fixtureId": "living-room-1",
            "mediaType": "image/jpeg",
            "sizeBytes": 1024,
        }
    ]
    deleted_threads: list[str] = []
    monkeypatch.setattr(
        client.app.state.container.resources,
        "_checkpoint_delete",
        deleted_threads.append,
    )
    deleted = client.request(
        "DELETE",
        f"/v1/projects/{project_id}/assets/{asset_id}",
        headers=_headers(),
        json={
            "idempotencyKey": "asset-delete",
            "expectedStateVersion": 1,
            "data": {},
        },
    )
    project = client.get(f"/v1/projects/{project_id}", headers=_headers())

    assert deleted.status_code == 200
    assert deleted.json()["stateVersion"] == 2
    assert deleted_threads == [project_id]
    assert project.json()["assets"] == []


def test_asset_conflicting_replay_returns_stable_error(client, ready_project) -> None:
    project_id = ready_project
    first = client.post(
        f"/v1/projects/{project_id}/assets",
        headers=_headers(),
        json=_asset_envelope("asset-create", 0),
    )
    changed = _asset_envelope("asset-create", 0)
    changed["data"]["sizeBytes"] = 2048
    conflict = client.post(
        f"/v1/projects/{project_id}/assets",
        headers=_headers(),
        json=changed,
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_project_accepts_at_most_ten_reference_assets(client, ready_project) -> None:
    project_id = ready_project
    for index in range(10):
        payload = _asset_envelope(f"asset-{index}", index)
        payload["data"]["fixtureId"] = f"living-room-{index}"
        response = client.post(
            f"/v1/projects/{project_id}/assets",
            headers=_headers(),
            json=payload,
        )
        assert response.status_code == 201

    rejected = client.post(
        f"/v1/projects/{project_id}/assets",
        headers=_headers(),
        json=_asset_envelope("asset-11", 10),
    )

    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "ASSET_LIMIT_REACHED"


def test_homeowner_can_correct_an_observed_attribute(client, project_with_attribute) -> None:
    response = client.patch(
        f"/v1/projects/{project_with_attribute}/attributes/wall-colour",
        headers=_headers(),
        json={
            "idempotencyKey": "confirm-wall",
            "expectedStateVersion": 0,
            "data": {"status": "confirmed", "value": "soft warm beige"},
        },
    )

    assert response.status_code == 200
    assert response.json()["stateVersion"] == 1
    attribute = next(
        item
        for item in response.json()["projectState"]["attributes"]
        if item["id"] == "wall-colour"
    )
    assert attribute["status"] == "confirmed"
    assert attribute["value"] == "soft warm beige"
