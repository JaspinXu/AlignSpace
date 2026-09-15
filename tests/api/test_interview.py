def _headers(actor_id: str = "homeowner-1", role: str = "homeowner") -> dict[str, str]:
    return {"X-Actor-Id": actor_id, "X-Actor-Role": role}


def _state(client, project_id: str) -> dict:
    return client.get(f"/v1/projects/{project_id}/state", headers=_headers()).json()["projectState"]


def _start(client, project_id: str, version: int = 3) -> dict:
    response = client.post(
        f"/v1/projects/{project_id}/analysis-runs",
        headers=_headers(),
        json={"idempotencyKey": "run-1", "expectedStateVersion": version, "data": {}},
    )
    assert response.status_code == 202, response.text
    return response.json()


def _answer(client, project_id: str, question_id: str, data: dict, *, key: str, version: int):
    return client.post(
        f"/v1/projects/{project_id}/questions/{question_id}/answer",
        headers=_headers(),
        json={"idempotencyKey": key, "expectedStateVersion": version, "data": data},
    )


def _select_all_parts(question: dict) -> dict:
    return {
        "parts": [
            {"assetId": option["assetId"], "targetElement": option["targetElement"]}
            for option in question["options"]
        ]
    }


def _first_detail(client, project_id: str, started: dict) -> tuple[dict, dict, dict]:
    broad = _answer(
        client,
        project_id,
        started["pendingQuestion"]["id"],
        _select_all_parts(started["pendingQuestion"]),
        key="broad",
        version=started["stateVersion"],
    )
    assert broad.status_code == 202, broad.text
    detail = broad.json()["pendingQuestion"]
    assert detail["kind"] == "detail"
    return broad.json(), detail, detail["options"][0]


def _record(state: dict, attribute_id: str) -> dict:
    return next(item for item in state["attributes"] if item["id"] == attribute_id)


def test_broad_then_detail_writes_a_confirmed_preference_with_source(
    client, analysis_ready_project
) -> None:
    started = _start(client, analysis_ready_project)
    assert started["pendingQuestion"]["kind"] == "broad_parts"
    assert started["pendingQuestion"]["options"]

    broad, detail, option = _first_detail(client, analysis_ready_project, started)
    answered = _answer(
        client,
        analysis_ready_project,
        detail["id"],
        {
            "selection": [
                {
                    "attributeId": option["attributeId"],
                    "decision": "confirmed",
                    "value": option["value"],
                }
            ]
        },
        key="detail",
        version=broad["stateVersion"],
    )

    assert answered.status_code == 202, answered.text
    record = _record(answered.json()["projectState"], option["attributeId"])
    assert record["status"] == "confirmed"
    assert record["actor"] == "homeowner"
    assert record["targetElement"] == option["targetElement"]
    assert record["dimension"] == option["dimension"]
    sources = {(item["sourceType"], item["sourceId"]) for item in record["evidence"]}
    assert ("image", option["assetId"]) in sources
    assert any(source == "homeowner_answer" for source, _ in sources)


def test_custom_value_keeps_the_same_preference_id(client, analysis_ready_project) -> None:
    started = _start(client, analysis_ready_project)
    broad, detail, option = _first_detail(client, analysis_ready_project, started)
    answered = _answer(
        client,
        analysis_ready_project,
        detail["id"],
        {
            "selection": [
                {
                    "attributeId": option["attributeId"],
                    "decision": "confirmed",
                    "value": "candlelit amber",
                }
            ]
        },
        key="custom",
        version=broad["stateVersion"],
    )

    record = _record(answered.json()["projectState"], option["attributeId"])
    assert record["value"] == "candlelit amber"
    assert any(item["sourceType"] == "image" for item in record["evidence"])


def test_not_applicable_records_explicit_no_preference(client, analysis_ready_project) -> None:
    started = _start(client, analysis_ready_project)
    broad, detail, option = _first_detail(client, analysis_ready_project, started)
    answered = _answer(
        client,
        analysis_ready_project,
        detail["id"],
        {"selection": [{"attributeId": option["attributeId"], "decision": "not_applicable"}]},
        key="not-applicable",
        version=broad["stateVersion"],
    )

    record = _record(answered.json()["projectState"], option["attributeId"])
    assert record["status"] == "not_applicable"


def test_skipping_the_broad_question_creates_no_preference(client, analysis_ready_project) -> None:
    started = _start(client, analysis_ready_project)
    skipped = _answer(
        client,
        analysis_ready_project,
        started["pendingQuestion"]["id"],
        {"skipped": True},
        key="skip-broad",
        version=started["stateVersion"],
    )

    assert skipped.status_code in (200, 202), skipped.text
    state = skipped.json()["projectState"]
    assert all(item["status"] != "confirmed" for item in state["attributes"])
    broad = next(item for item in state["questions"] if item["id"] == "question-liked-elements")
    assert broad["skipped"] is True


def test_deleting_a_source_image_drops_its_proposed_observations(
    client, analysis_ready_project
) -> None:
    started = _start(client, analysis_ready_project)
    state = _state(client, analysis_ready_project)
    asset_id = next(
        item["evidence"][0]["sourceId"]
        for item in state["attributes"]
        if item["status"] == "proposed" and item["evidence"]
    )

    deleted = client.request(
        "DELETE",
        f"/v1/projects/{analysis_ready_project}/assets/{asset_id}",
        headers=_headers(),
        json={
            "idempotencyKey": "delete-source",
            "expectedStateVersion": state["stateVersion"],
            "data": {},
        },
    )
    assert deleted.status_code == 200, deleted.text

    after = _state(client, analysis_ready_project)
    proposed = [item for item in after["attributes"] if item["status"] == "proposed"]
    assert proposed
    assert all(
        evidence["sourceId"] != asset_id
        for item in proposed
        for evidence in item["evidence"]
        if evidence["sourceType"] == "image"
    )
    assert started["pendingQuestion"]["id"]


def test_deleting_a_source_image_retires_its_question_options(
    client, analysis_ready_project
) -> None:
    started = _start(client, analysis_ready_project)
    _broad, detail, option = _first_detail(client, analysis_ready_project, started)
    state = _state(client, analysis_ready_project)

    deleted = client.request(
        "DELETE",
        f"/v1/projects/{analysis_ready_project}/assets/{option['assetId']}",
        headers=_headers(),
        json={
            "idempotencyKey": "delete-detail-source",
            "expectedStateVersion": state["stateVersion"],
            "data": {},
        },
    )
    assert deleted.status_code == 200, deleted.text

    after = _state(client, analysis_ready_project)
    question = next(item for item in after["questions"] if item["id"] == detail["id"])
    assert option["assetId"] not in {item["assetId"] for item in question["options"]}

    stale = _answer(
        client,
        analysis_ready_project,
        detail["id"],
        {
            "selection": [
                {
                    "attributeId": option["attributeId"],
                    "decision": "confirmed",
                    "value": option["value"],
                }
            ]
        },
        key="stale-option",
        version=after["stateVersion"],
    )
    assert stale.status_code == 400, stale.text
    current = _state(client, analysis_ready_project)
    assert all(item["id"] != option["attributeId"] for item in current["attributes"])


def test_answer_rejects_a_selection_from_another_question(
    client, analysis_ready_project
) -> None:
    started = _start(client, analysis_ready_project)
    state = _state(client, analysis_ready_project)
    wall = next(
        item
        for item in state["attributes"]
        if item["status"] == "proposed" and item["targetElement"] == "wall"
    )
    broad, detail, _ = _first_detail(client, analysis_ready_project, started)
    assert detail["targetElement"] != "wall"

    response = _answer(
        client,
        analysis_ready_project,
        detail["id"],
        {
            "selection": [
                {"attributeId": wall["id"], "decision": "confirmed", "value": wall["value"]}
            ]
        },
        key="unrelated",
        version=broad["stateVersion"],
    )

    assert response.status_code == 400, response.text
    after = _state(client, analysis_ready_project)
    assert _record(after, wall["id"])["status"] == "proposed"


def test_new_preference_without_attribute_id_keeps_image_evidence(
    client, analysis_ready_project
) -> None:
    started = _start(client, analysis_ready_project)
    broad, detail, option = _first_detail(client, analysis_ready_project, started)

    answered = _answer(
        client,
        analysis_ready_project,
        detail["id"],
        {
            "selection": [
                {
                    "assetId": option["assetId"],
                    "targetElement": option["targetElement"],
                    "dimension": option["dimension"],
                    "decision": "confirmed",
                    "value": "custom value",
                }
            ]
        },
        key="new-preference",
        version=broad["stateVersion"],
    )

    assert answered.status_code == 202, answered.text
    record = _record(
        answered.json()["projectState"],
        f"pref-{option['assetId']}-{option['targetElement']}-{option['dimension']}",
    )
    assert any(
        item["sourceType"] == "image" and item["sourceId"] == option["assetId"]
        for item in record["evidence"]
    )
    assert any(item["sourceType"] == "homeowner_answer" for item in record["evidence"])


def test_broad_question_rejects_a_preference_selection(client, analysis_ready_project) -> None:
    started = _start(client, analysis_ready_project)
    option = started["pendingQuestion"]["options"][0]

    with_selection = _answer(
        client,
        analysis_ready_project,
        started["pendingQuestion"]["id"],
        {
            "selection": [
                {
                    "assetId": option["assetId"],
                    "targetElement": option["targetElement"],
                    "dimension": "colour",
                    "decision": "confirmed",
                    "value": "injected",
                }
            ]
        },
        key="broad-selection",
        version=started["stateVersion"],
    )
    assert with_selection.status_code == 400, with_selection.text

    unknown_asset = _answer(
        client,
        analysis_ready_project,
        started["pendingQuestion"]["id"],
        {"parts": [{"assetId": "does-not-exist", "targetElement": option["targetElement"]}]},
        key="broad-bad-asset",
        version=started["stateVersion"],
    )
    assert unknown_asset.status_code == 400, unknown_asset.text

    state = _state(client, analysis_ready_project)
    assert all(item["status"] != "confirmed" for item in state["attributes"])


def test_detail_question_rejects_parts(client, analysis_ready_project) -> None:
    started = _start(client, analysis_ready_project)
    broad, detail, option = _first_detail(client, analysis_ready_project, started)

    response = _answer(
        client,
        analysis_ready_project,
        detail["id"],
        {"parts": [{"assetId": option["assetId"], "targetElement": option["targetElement"]}]},
        key="detail-parts",
        version=broad["stateVersion"],
    )
    assert response.status_code == 400, response.text


def test_retiring_the_current_question_advances_to_the_next(
    client, analysis_ready_project
) -> None:
    started = _start(client, analysis_ready_project)
    options = started["pendingQuestion"]["options"]
    first = options[0]
    second = next(
        item
        for item in options
        if item["assetId"] != first["assetId"] and item["targetElement"] != first["targetElement"]
    )
    broad = _answer(
        client,
        analysis_ready_project,
        started["pendingQuestion"]["id"],
        {
            "parts": [
                {"assetId": first["assetId"], "targetElement": first["targetElement"]},
                {"assetId": second["assetId"], "targetElement": second["targetElement"]},
            ]
        },
        key="broad",
        version=started["stateVersion"],
    )
    assert broad.status_code == 202, broad.text
    detail = broad.json()["pendingQuestion"]
    asset_to_delete = detail["options"][0]["assetId"]
    state = _state(client, analysis_ready_project)

    deleted = client.request(
        "DELETE",
        f"/v1/projects/{analysis_ready_project}/assets/{asset_to_delete}",
        headers=_headers(),
        json={
            "idempotencyKey": "delete-only-source",
            "expectedStateVersion": state["stateVersion"],
            "data": {},
        },
    )
    assert deleted.status_code == 200, deleted.text

    following = client.get(
        f"/v1/projects/{analysis_ready_project}/questions/next", headers=_headers()
    )
    assert following.status_code == 200, following.text
    assert following.json()["id"] != detail["id"]
