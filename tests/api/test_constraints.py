def _headers(actor_id: str = "homeowner-1", role: str = "homeowner") -> dict[str, str]:
    return {"X-Actor-Id": actor_id, "X-Actor-Role": role}


def _designer() -> dict[str, str]:
    return _headers("designer-1", "designer")


def _confirmed_preference(client, project_id: str, *, key: str = "manual-material") -> int:
    response = client.patch(
        f"/v1/projects/{project_id}/attributes/manual-material",
        headers=_headers(),
        json={
            "idempotencyKey": key,
            "expectedStateVersion": 0,
            "data": {
                "targetElement": "worktop",
                "dimension": "material",
                "value": "natural stone",
                "status": "confirmed",
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["stateVersion"]


def _create_constraint(
    client,
    project_id: str,
    *,
    version: int,
    key: str = "constraint-1",
    **overrides: object,
):
    data: dict[str, object] = {
        "category": "budget",
        "statement": "天然石材工作台超出当前预算档位",
        "rationale": "改用石材效果饰面可在预算内实现相近观感",
        "severity": "important",
        "appliesTo": "worktop",
        "attributeId": "manual-material",
    }
    data.update(overrides)
    return client.post(
        f"/v1/projects/{project_id}/constraints",
        headers=_designer(),
        json={"idempotencyKey": key, "expectedStateVersion": version, "data": data},
    )


def test_designer_creates_constraint_and_rule_derives_conflict(client, ready_project) -> None:
    version = _confirmed_preference(client, ready_project)

    created = _create_constraint(client, ready_project, version=version)

    assert created.status_code == 200, created.text
    state = created.json()["projectState"]
    constraint = state["constraints"][0]
    assert constraint["proposedBy"] == "designer-1"
    assert constraint["owner"] == "designer"
    assert constraint["verificationStatus"] == "designer_asserted"
    assert constraint["appliesTo"] == "worktop"
    assert constraint["attributeId"] == "manual-material"
    assert constraint["withdrawn"] is False
    conflict = state["conflicts"][0]
    assert conflict["constraintId"] == constraint["id"]
    assert conflict["status"] == "open"


def test_only_designers_write_and_only_members_read(client, ready_project) -> None:
    version = _confirmed_preference(client, ready_project)
    forbidden = client.post(
        f"/v1/projects/{ready_project}/constraints",
        headers=_headers(),
        json={"idempotencyKey": "h", "expectedStateVersion": version, "data": {}},
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "FORBIDDEN"

    assert (
        client.get(
            f"/v1/projects/{ready_project}/constraints",
            headers=_headers("stranger", "homeowner"),
        ).status_code
        == 403
    )
    listed = client.get(f"/v1/projects/{ready_project}/constraints", headers=_designer())
    assert listed.status_code == 200
    assert listed.json() == []


def test_advisory_constraint_on_confirmed_preference_has_no_conflict(client, ready_project) -> None:
    version = _confirmed_preference(client, ready_project)
    created = _create_constraint(client, ready_project, version=version, severity="advisory")
    assert created.status_code == 200, created.text
    assert created.json()["projectState"]["conflicts"] == []


def test_update_refreshes_then_downgrade_removes_open_derived_conflict(
    client, ready_project
) -> None:
    version = _confirmed_preference(client, ready_project)
    created = _create_constraint(client, ready_project, version=version).json()
    constraint_id = created["projectState"]["constraints"][0]["id"]

    updated = client.patch(
        f"/v1/projects/{ready_project}/constraints/{constraint_id}",
        headers=_designer(),
        json={
            "idempotencyKey": "update-1",
            "expectedStateVersion": created["stateVersion"],
            "data": {"statement": "更新后的预算约束", "severity": "advisory"},
        },
    )

    assert updated.status_code == 200, updated.text
    state = updated.json()["projectState"]
    assert state["constraints"][0]["statement"] == "更新后的预算约束"
    assert state["conflicts"] == []


def test_withdraw_marks_constraint_and_drops_open_derived_conflict(client, ready_project) -> None:
    version = _confirmed_preference(client, ready_project)
    created = _create_constraint(client, ready_project, version=version).json()
    constraint_id = created["projectState"]["constraints"][0]["id"]

    withdrawn = client.post(
        f"/v1/projects/{ready_project}/constraints/{constraint_id}/withdraw",
        headers=_designer(),
        json={"idempotencyKey": "withdraw-1", "expectedStateVersion": created["stateVersion"], "data": {}},
    )

    assert withdrawn.status_code == 200, withdrawn.text
    state = withdrawn.json()["projectState"]
    assert state["constraints"][0]["withdrawn"] is True
    assert state["conflicts"] == []

    edit = client.patch(
        f"/v1/projects/{ready_project}/constraints/{constraint_id}",
        headers=_designer(),
        json={"idempotencyKey": "edit-withdrawn", "expectedStateVersion": withdrawn.json()["stateVersion"], "data": {"statement": "nope"}},
    )
    assert edit.status_code == 400


def test_constraint_idempotency_and_stale_version(client, ready_project) -> None:
    version = _confirmed_preference(client, ready_project)

    first = _create_constraint(client, ready_project, version=version, key="same")
    replay = _create_constraint(client, ready_project, version=version, key="same")
    assert replay.json() == first.json()

    conflict = _create_constraint(
        client, ready_project, version=version, key="same", statement="不同内容"
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_CONFLICT"

    stale = _create_constraint(client, ready_project, version=0, key="stale")
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "STATE_VERSION_STALE"


def test_constraint_change_invalidates_existing_approvals(client, brief_ready_project) -> None:
    latest = client.get(
        f"/v1/projects/{brief_ready_project}/briefs/latest", headers=_headers()
    ).json()
    homeowner = client.post(
        f"/v1/projects/{brief_ready_project}/briefs/1/approvals",
        headers=_headers(),
        json={
            "idempotencyKey": "approve-homeowner",
            "expectedStateVersion": 1,
            "data": {"contentHash": latest["contentHash"]},
        },
    )
    assert homeowner.status_code == 200, homeowner.text
    designer = client.post(
        f"/v1/projects/{brief_ready_project}/briefs/1/approvals",
        headers=_designer(),
        json={
            "idempotencyKey": "approve-designer",
            "expectedStateVersion": homeowner.json()["stateVersion"],
            "data": {"contentHash": latest["contentHash"]},
        },
    )
    assert designer.json()["status"] == "approved"

    created = _create_constraint(
        client,
        brief_ready_project,
        version=designer.json()["stateVersion"],
        attributeId="confirmed-material",
    )

    assert created.status_code == 200, created.text
    state = created.json()["projectState"]
    assert state["approvals"] == []
    assert state["status"] == "alignment"
