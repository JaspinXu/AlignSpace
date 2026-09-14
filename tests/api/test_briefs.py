def _headers(actor_id: str = "homeowner-1", role: str = "homeowner") -> dict[str, str]:
    return {"X-Actor-Id": actor_id, "X-Actor-Role": role}


def test_both_roles_must_approve_same_brief(client, brief_ready_project) -> None:
    project_id = brief_ready_project
    project = client.get(f"/v1/projects/{project_id}", headers=_headers()).json()
    brief = client.get(
        f"/v1/projects/{project_id}/briefs/latest",
        headers=_headers(),
    ).json()

    first = client.post(
        f"/v1/projects/{project_id}/briefs/{brief['version']}/approvals",
        headers=_headers(),
        json={
            "idempotencyKey": "approve-h",
            "expectedStateVersion": project["stateVersion"],
            "data": {"contentHash": brief["contentHash"]},
        },
    )

    assert first.status_code == 200
    assert first.json()["status"] == "awaiting_approval"

    replay = client.post(
        f"/v1/projects/{project_id}/briefs/{brief['version']}/approvals",
        headers=_headers(),
        json={
            "idempotencyKey": "approve-h",
            "expectedStateVersion": project["stateVersion"],
            "data": {"contentHash": brief["contentHash"]},
        },
    )
    assert replay.json() == first.json()

    second = client.post(
        f"/v1/projects/{project_id}/briefs/{brief['version']}/approvals",
        headers=_headers("designer-1", "designer"),
        json={
            "idempotencyKey": "approve-d",
            "expectedStateVersion": first.json()["stateVersion"],
            "data": {"contentHash": brief["contentHash"]},
        },
    )

    assert second.status_code == 200
    assert second.json()["status"] == "approved"
    assert len(second.json()["projectState"]["approvals"]) == 2


def test_approval_rejects_a_mismatched_content_hash(client, brief_ready_project) -> None:
    project_id = brief_ready_project
    response = client.post(
        f"/v1/projects/{project_id}/briefs/1/approvals",
        headers=_headers(),
        json={
            "idempotencyKey": "approve-wrong",
            "expectedStateVersion": 1,
            "data": {"contentHash": "0" * 64},
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BRIEF_HASH_MISMATCH"


def test_editing_brief_creates_new_version_and_clears_approvals(
    client,
    brief_ready_project,
) -> None:
    project_id = brief_ready_project
    original = client.get(
        f"/v1/projects/{project_id}/briefs/latest",
        headers=_headers(),
    ).json()
    approved = client.post(
        f"/v1/projects/{project_id}/briefs/1/approvals",
        headers=_headers(),
        json={
            "idempotencyKey": "approve-before-edit",
            "expectedStateVersion": 1,
            "data": {"contentHash": original["contentHash"]},
        },
    ).json()
    payload = original["payload"]
    payload["goals"] = [*payload["goals"], "Make room for a reading chair"]

    edited = client.patch(
        f"/v1/projects/{project_id}/briefs/1",
        headers=_headers("designer-1", "designer"),
        json={
            "idempotencyKey": "edit-brief",
            "expectedStateVersion": approved["stateVersion"],
            "data": {"payload": payload},
        },
    )

    assert edited.status_code == 200
    assert edited.json()["version"] == 2
    assert edited.json()["stateVersion"] == approved["stateVersion"] + 1
    assert edited.json()["contentHash"] != original["contentHash"]
    assert edited.json()["approvals"] == []


def test_invalid_brief_edit_is_rejected(client, brief_ready_project) -> None:
    response = client.patch(
        f"/v1/projects/{brief_ready_project}/briefs/1",
        headers=_headers("designer-1", "designer"),
        json={
            "idempotencyKey": "invalid-edit",
            "expectedStateVersion": 1,
            "data": {"payload": []},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BRIEF_SCHEMA_INVALID"


def test_brief_edit_cannot_change_project_scope(client, brief_ready_project) -> None:
    original = client.get(
        f"/v1/projects/{brief_ready_project}/briefs/latest",
        headers=_headers(),
    ).json()
    payload = original["payload"]
    payload["project"]["id"] = "other-project"

    response = client.patch(
        f"/v1/projects/{brief_ready_project}/briefs/1",
        headers=_headers("designer-1", "designer"),
        json={
            "idempotencyKey": "scope-edit",
            "expectedStateVersion": 1,
            "data": {"payload": payload},
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "BRIEF_SCHEMA_INVALID"


def test_brief_edit_ignores_client_completeness(client, brief_ready_project) -> None:
    original = client.get(
        f"/v1/projects/{brief_ready_project}/briefs/latest",
        headers=_headers(),
    ).json()
    payload = dict(original["payload"])
    payload["completeness"] = 0.5

    response = client.patch(
        f"/v1/projects/{brief_ready_project}/briefs/1",
        headers=_headers("designer-1", "designer"),
        json={
            "idempotencyKey": "incomplete-edit",
            "expectedStateVersion": 1,
            "data": {"payload": payload},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["completeness"] == 0.875
    assert response.json()["payload"]["completeness"] == 0.875
