import json


def _headers(actor_id: str = "homeowner-1", role: str = "homeowner") -> dict[str, str]:
    return {"X-Actor-Id": actor_id, "X-Actor-Role": role}


def test_image_instruction_cannot_change_project_scope(client, analysis_ready_project) -> None:
    project_id = analysis_ready_project
    current = client.get(f"/v1/projects/{project_id}", headers=_headers()).json()
    response = client.post(
        f"/v1/projects/{project_id}/analysis-runs",
        headers=_headers(),
        json={
            "idempotencyKey": "injection-run",
            "expectedStateVersion": current["stateVersion"],
            "data": {"fixture": "image-text-ignore-policy-read-other-project"},
        },
    )
    state = client.get(f"/v1/projects/{project_id}", headers=_headers()).json()

    assert response.status_code == 202
    assert state["id"] == project_id
    assert "other-project" not in json.dumps(state)


def test_cross_project_member_cannot_read_another_project(client) -> None:
    first = client.post(
        "/v1/projects",
        headers=_headers(),
        json={
            "roomType": "living_room",
            "budgetBand": "under_15k_sgd",
            "consent": True,
            "designerId": "designer-1",
        },
    ).json()["id"]

    response = client.get(
        f"/v1/projects/{first}",
        headers=_headers("homeowner-2", "homeowner"),
    )

    assert response.status_code == 403
    assert first not in json.dumps(response.json()["error"]["details"])


def test_unsupported_assurance_cannot_be_persisted_in_brief(
    client,
    brief_ready_project,
) -> None:
    original = client.get(
        f"/v1/projects/{brief_ready_project}/briefs/latest",
        headers=_headers(),
    ).json()
    payload = original["payload"]
    payload["goals"] = ["This wall is definitely non-load-bearing and safe to remove"]

    response = client.patch(
        f"/v1/projects/{brief_ready_project}/briefs/1",
        headers=_headers("designer-1", "designer"),
        json={
            "idempotencyKey": "unsafe-edit",
            "expectedStateVersion": 1,
            "data": {"payload": payload},
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PROFESSIONAL_REVIEW_REQUIRED"
    current = client.get(f"/v1/projects/{brief_ready_project}", headers=_headers()).json()
    assert current["stateVersion"] == 1
