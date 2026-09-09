def _headers(actor_id: str = "homeowner-1", role: str = "homeowner") -> dict[str, str]:
    return {"X-Actor-Id": actor_id, "X-Actor-Role": role}


def test_analysis_returns_pending_homeowner_question(client, analysis_ready_project) -> None:
    project_id = analysis_ready_project
    current = client.get(f"/v1/projects/{project_id}", headers=_headers()).json()

    response = client.post(
        f"/v1/projects/{project_id}/analysis-runs",
        headers=_headers(),
        json={
            "idempotencyKey": "run-1",
            "expectedStateVersion": current["stateVersion"],
            "data": {},
        },
    )

    assert response.status_code == 202
    assert response.json()["waitReason"] == "homeowner"
    assert response.json()["pendingQuestion"]["targetRole"] == "homeowner"

    pending = client.get(
        f"/v1/projects/{project_id}/questions/next",
        headers=_headers(),
    )
    assert pending.status_code == 200
    assert pending.json()["id"] == response.json()["pendingQuestion"]["id"]


def test_analysis_requires_three_reference_assets(client, ready_project) -> None:
    response = client.post(
        f"/v1/projects/{ready_project}/analysis-runs",
        headers=_headers(),
        json={"idempotencyKey": "run-1", "expectedStateVersion": 0, "data": {}},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ASSET_COUNT_INVALID"


def test_homeowner_answer_resumes_the_pending_question(client, analysis_ready_project) -> None:
    project_id = analysis_ready_project
    started = client.post(
        f"/v1/projects/{project_id}/analysis-runs",
        headers=_headers(),
        json={"idempotencyKey": "run-1", "expectedStateVersion": 3, "data": {}},
    ).json()
    question_id = started["pendingQuestion"]["id"]

    answered = client.post(
        f"/v1/projects/{project_id}/questions/{question_id}/answer",
        headers=_headers(),
        json={
            "idempotencyKey": "answer-1",
            "expectedStateVersion": started["stateVersion"],
            "data": {"answer": "I also like the warm lighting"},
        },
    )

    assert answered.status_code == 202
    assert answered.json()["stateVersion"] == started["stateVersion"] + 1
    assert answered.json()["pendingQuestion"]["id"] == "question-lighting-lighting"

    replay = client.post(
        f"/v1/projects/{project_id}/questions/{question_id}/answer",
        headers=_headers(),
        json={
            "idempotencyKey": "answer-1",
            "expectedStateVersion": started["stateVersion"],
            "data": {"answer": "I also like the warm lighting"},
        },
    )
    assert replay.status_code == 202
    assert replay.json() == answered.json()

    wrong_target = client.post(
        f"/v1/projects/{project_id}/questions/question-lighting-lighting/answer",
        headers=_headers(),
        json={
            "idempotencyKey": "answer-1",
            "expectedStateVersion": started["stateVersion"],
            "data": {"answer": "I also like the warm lighting"},
        },
    )
    assert wrong_target.status_code == 409
    assert wrong_target.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_designer_cannot_answer_homeowner_question(client, analysis_ready_project) -> None:
    project_id = analysis_ready_project
    started = client.post(
        f"/v1/projects/{project_id}/analysis-runs",
        headers=_headers(),
        json={"idempotencyKey": "run-1", "expectedStateVersion": 3, "data": {}},
    ).json()

    response = client.post(
        f"/v1/projects/{project_id}/questions/{started['pendingQuestion']['id']}/answer",
        headers=_headers("designer-1", "designer"),
        json={
            "idempotencyKey": "wrong-role",
            "expectedStateVersion": started["stateVersion"],
            "data": {"answer": "yes"},
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"


def test_blank_homeowner_answer_is_rejected_without_advancing_state(
    client,
    analysis_ready_project,
) -> None:
    project_id = analysis_ready_project
    started = client.post(
        f"/v1/projects/{project_id}/analysis-runs",
        headers=_headers(),
        json={"idempotencyKey": "run-1", "expectedStateVersion": 3, "data": {}},
    ).json()

    response = client.post(
        f"/v1/projects/{project_id}/questions/{started['pendingQuestion']['id']}/answer",
        headers=_headers(),
        json={
            "idempotencyKey": "blank-answer",
            "expectedStateVersion": started["stateVersion"],
            "data": {"answer": "   "},
        },
    )
    current = client.get(f"/v1/projects/{project_id}", headers=_headers()).json()

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
    assert current["stateVersion"] == started["stateVersion"]


def test_human_can_resolve_a_noncritical_conflict(client, brief_ready_project) -> None:
    response = client.post(
        f"/v1/projects/{brief_ready_project}/conflicts/finish-budget-conflict/resolve",
        headers=_headers(),
        json={
            "idempotencyKey": "resolve-1",
            "expectedStateVersion": 1,
            "data": {
                "status": "resolved",
                "resolution": "Use a lower-cost stone-effect finish.",
            },
        },
    )

    assert response.status_code == 200
    conflict = response.json()["projectState"]["conflicts"][0]
    assert conflict["status"] == "resolved"
    assert conflict["resolutionAttempts"] == 1


def test_homeowner_cannot_submit_designer_review(client, analysis_ready_project) -> None:
    response = client.post(
        f"/v1/projects/{analysis_ready_project}/designer-reviews",
        headers=_headers(),
        json={
            "idempotencyKey": "wrong-reviewer",
            "expectedStateVersion": 3,
            "data": {"note": "Looks feasible"},
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
