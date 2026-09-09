def _headers(actor_id: str = "homeowner-1", role: str = "homeowner") -> dict[str, str]:
    return {"X-Actor-Id": actor_id, "X-Actor-Role": role}


def test_create_and_read_project(client) -> None:
    response = client.post(
        "/v1/projects",
        headers=_headers(),
        json={
            "roomType": "living_room",
            "budgetBand": "15k_to_30k_sgd",
            "consent": True,
            "designerId": "designer-1",
        },
    )

    assert response.status_code == 201
    project_id = response.json()["id"]
    loaded = client.get(f"/v1/projects/{project_id}", headers=_headers())

    assert loaded.status_code == 200
    assert loaded.json() == {
        "id": project_id,
        "roomType": "living_room",
        "budgetBand": "15k_to_30k_sgd",
        "consent": True,
        "status": "draft",
        "stateVersion": 0,
        "assets": [],
    }


def test_designer_member_can_read_but_outsider_cannot(client) -> None:
    created = client.post(
        "/v1/projects",
        headers=_headers(),
        json={
            "roomType": "living_room",
            "budgetBand": "under_15k_sgd",
            "consent": True,
            "designerId": "designer-1",
        },
    ).json()

    designer = client.get(
        f"/v1/projects/{created['id']}",
        headers=_headers("designer-1", "designer"),
    )
    outsider = client.get(
        f"/v1/projects/{created['id']}",
        headers=_headers("stranger", "homeowner"),
    )

    assert designer.status_code == 200
    assert outsider.status_code == 403
    assert outsider.json()["error"]["code"] == "FORBIDDEN"
    assert outsider.json()["error"]["correlationId"]


def test_delete_project_removes_active_record_and_checkpoint(client, monkeypatch) -> None:
    project_id = client.post(
        "/v1/projects",
        headers=_headers(),
        json={
            "roomType": "bedroom",
            "budgetBand": "under_15k_sgd",
            "consent": False,
            "designerId": "designer-1",
        },
    ).json()["id"]

    deleted_threads: list[str] = []
    monkeypatch.setattr(
        client.app.state.container.resources,
        "_checkpoint_delete",
        deleted_threads.append,
    )

    deleted = client.delete(f"/v1/projects/{project_id}", headers=_headers())
    loaded = client.get(f"/v1/projects/{project_id}", headers=_headers())

    assert deleted.status_code == 204
    assert deleted_threads == [project_id]
    assert loaded.status_code == 404
    assert loaded.json()["error"]["code"] == "PROJECT_NOT_FOUND"


def test_project_requires_distinct_homeowner_and_designer(client) -> None:
    response = client.post(
        "/v1/projects",
        headers=_headers(),
        json={
            "roomType": "living_room",
            "budgetBand": "under_15k_sgd",
            "consent": True,
            "designerId": "homeowner-1",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_missing_actor_headers_use_stable_validation_error(client) -> None:
    response = client.get("/v1/projects/not-a-project")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert response.json()["error"]["recoverable"] is True


def test_designer_cannot_delete_project(client) -> None:
    project_id = client.post(
        "/v1/projects",
        headers=_headers(),
        json={
            "roomType": "living_room",
            "budgetBand": "under_15k_sgd",
            "consent": True,
            "designerId": "designer-1",
        },
    ).json()["id"]

    response = client.delete(
        f"/v1/projects/{project_id}",
        headers=_headers("designer-1", "designer"),
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    assert client.get(f"/v1/projects/{project_id}", headers=_headers()).status_code == 200
