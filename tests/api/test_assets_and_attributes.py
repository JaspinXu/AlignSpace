def _headers(actor_id: str = "homeowner-1", role: str = "homeowner") -> dict[str, str]:
    return {"X-Actor-Id": actor_id, "X-Actor-Role": role}


def test_designer_cannot_manage_reference_assets(client, ready_project, upload_image) -> None:
    created = upload_image(ready_project, headers=_headers(), key="homeowner-asset", version=0)
    assert created.status_code == 201
    add_attempt = upload_image(
        ready_project, headers=_headers("designer-1", "designer"),
        key="designer-asset", version=1,
    )
    assert add_attempt.status_code == 403
    remove_attempt = client.request(
        "DELETE",
        f"/v1/projects/{ready_project}/assets/{created.json()['id']}",
        headers=_headers("designer-1", "designer"),
        json={"idempotencyKey": "designer-delete", "expectedStateVersion": 1, "data": {}},
    )
    assert remove_attempt.status_code == 403


def test_asset_registration_requires_consent(client, project_without_consent, upload_image) -> None:
    response = upload_image(
        project_without_consent, headers=_headers(), key="asset-1", version=0
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "CONSENT_REQUIRED"


def test_register_and_soft_delete_are_versioned_and_idempotent(
    client, ready_project, upload_image
) -> None:
    first = upload_image(ready_project, headers=_headers(), key="asset-create", version=0)
    replay = upload_image(ready_project, headers=_headers(), key="asset-create", version=0)
    assert first.status_code == 201
    assert replay.json() == first.json()

    asset_id = first.json()["id"]
    listed = client.get(f"/v1/projects/{ready_project}", headers=_headers()).json()["assets"]
    assert listed[0]["id"] == asset_id
    assert listed[0]["deleted"] is False

    deleted = client.request(
        "DELETE",
        f"/v1/projects/{ready_project}/assets/{asset_id}",
        headers=_headers(),
        json={"idempotencyKey": "asset-delete", "expectedStateVersion": 1, "data": {}},
    )
    assert deleted.status_code == 200
    assert deleted.json()["stateVersion"] == 2
    after = client.get(f"/v1/projects/{ready_project}", headers=_headers()).json()["assets"]
    assert after[0]["deleted"] is True


def test_asset_conflicting_replay_returns_stable_error(client, ready_project, upload_image) -> None:
    first = upload_image(ready_project, headers=_headers(), key="asset-create", version=0)
    conflict = upload_image(
        ready_project, headers=_headers(), key="asset-create", version=0, color="blue"
    )
    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_project_accepts_at_most_ten_reference_assets(client, ready_project, upload_image) -> None:
    for index in range(10):
        response = upload_image(
            ready_project, headers=_headers(), key=f"asset-{index}", version=index
        )
        assert response.status_code == 201
    rejected = upload_image(ready_project, headers=_headers(), key="asset-11", version=10)
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


def test_attribute_correction_requires_a_status(client, project_with_attribute) -> None:
    response = client.patch(
        f"/v1/projects/{project_with_attribute}/attributes/wall-colour",
        headers=_headers(),
        json={
            "idempotencyKey": "missing-status",
            "expectedStateVersion": 0,
            "data": {"value": "soft warm beige"},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_homeowner_can_add_an_explicit_sparse_preference(client, ready_project) -> None:
    response = client.patch(
        f"/v1/projects/{ready_project}/attributes/manual-style",
        headers=_headers(),
        json={
            "idempotencyKey": "manual-style",
            "expectedStateVersion": 0,
            "data": {
                "targetElement": "living_room",
                "dimension": "style",
                "value": "warm modern",
                "status": "confirmed",
            },
        },
    )

    assert response.status_code == 200
    assert response.json()["projectState"]["completeness"] == 0.125
    assert response.json()["projectState"]["attributes"][0]["id"] == "manual-style"
