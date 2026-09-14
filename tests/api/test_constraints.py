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
        "incompatibleWith": ["natural stone"],
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


def test_constraint_without_declared_incompatibility_has_no_conflict(client, ready_project) -> None:
    version = _confirmed_preference(client, ready_project)
    created = _create_constraint(client, ready_project, version=version, incompatibleWith=[])
    assert created.status_code == 200, created.text
    assert created.json()["projectState"]["conflicts"] == []


def test_update_clears_declared_incompatibility_and_removes_open_conflict(
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
            "data": {"statement": "更新后的预算约束", "incompatibleWith": []},
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


def test_material_constraint_change_after_resolution_opens_a_new_conflict(
    client, ready_project
) -> None:
    version = _confirmed_preference(client, ready_project)
    created = _create_constraint(client, ready_project, version=version).json()
    constraint_id = created["projectState"]["constraints"][0]["id"]
    conflict_id = created["projectState"]["conflicts"][0]["id"]
    resolved = client.post(
        f"/v1/projects/{ready_project}/conflicts/{conflict_id}/resolve",
        headers=_headers(),
        json={
            "idempotencyKey": "resolve-1",
            "expectedStateVersion": created["stateVersion"],
            "data": {"status": "resolved", "resolution": "改用低成本石材效果饰面"},
        },
    )
    assert resolved.status_code == 200, resolved.text

    updated = client.patch(
        f"/v1/projects/{ready_project}/constraints/{constraint_id}",
        headers=_designer(),
        json={
            "idempotencyKey": "edit-1",
            "expectedStateVersion": resolved.json()["stateVersion"],
            "data": {"statement": "石材改为关键成本限制", "severity": "critical"},
        },
    )

    assert updated.status_code == 200, updated.text
    conflicts = updated.json()["projectState"]["conflicts"]
    assert any(c["id"] == conflict_id and c["status"] == "resolved" for c in conflicts)
    opened = [c for c in conflicts if c["status"] == "open"]
    assert len(opened) == 1
    assert opened[0]["severity"] == "critical"
    assert "-r2-" in opened[0]["id"]


def test_preference_change_re_reconciles_the_linked_conflict(client, ready_project) -> None:
    version = _confirmed_preference(client, ready_project)
    created = _create_constraint(client, ready_project, version=version).json()
    assert len(created["projectState"]["conflicts"]) == 1

    changed = client.patch(
        f"/v1/projects/{ready_project}/attributes/manual-material",
        headers=_headers(),
        json={
            "idempotencyKey": "change-material",
            "expectedStateVersion": created["stateVersion"],
            "data": {"status": "confirmed", "value": "recycled glass"},
        },
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["projectState"]["conflicts"] == []

    restored = client.patch(
        f"/v1/projects/{ready_project}/attributes/manual-material",
        headers=_headers(),
        json={
            "idempotencyKey": "restore-material",
            "expectedStateVersion": changed.json()["stateVersion"],
            "data": {"status": "confirmed", "value": "natural stone"},
        },
    )
    assert len(restored.json()["projectState"]["conflicts"]) == 1


def test_stale_brief_blocks_reapproval_until_regenerated(client, brief_ready_project) -> None:
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
    blocked = client.post(
        f"/v1/projects/{brief_ready_project}/briefs/1/approvals",
        headers=_headers(),
        json={
            "idempotencyKey": "approve-stale",
            "expectedStateVersion": created.json()["stateVersion"],
            "data": {"contentHash": latest["contentHash"]},
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "APPROVAL_NOT_ALLOWED"

    realigned = client.post(
        f"/v1/projects/{brief_ready_project}/realign",
        headers=_headers(),
        json={
            "idempotencyKey": "realign-1",
            "expectedStateVersion": created.json()["stateVersion"],
            "data": {},
        },
    )
    assert realigned.status_code == 200, realigned.text
    assert realigned.json()["projectState"]["briefStale"] is False
    regenerated = client.get(
        f"/v1/projects/{brief_ready_project}/briefs/latest", headers=_headers()
    ).json()
    assert regenerated["version"] == 2
    assert any(
        item["statement"] == "天然石材工作台超出当前预算档位"
        for item in regenerated["payload"]["constraints"]
    )

    first = client.post(
        f"/v1/projects/{brief_ready_project}/briefs/2/approvals",
        headers=_headers(),
        json={
            "idempotencyKey": "approve-v2-homeowner",
            "expectedStateVersion": realigned.json()["stateVersion"],
            "data": {"contentHash": regenerated["contentHash"]},
        },
    )
    second = client.post(
        f"/v1/projects/{brief_ready_project}/briefs/2/approvals",
        headers=_designer(),
        json={
            "idempotencyKey": "approve-v2-designer",
            "expectedStateVersion": first.json()["stateVersion"],
            "data": {"contentHash": regenerated["contentHash"]},
        },
    )
    assert second.json()["status"] == "approved"


def test_editing_a_stale_brief_rebuilds_from_current_state(client, brief_ready_project) -> None:
    stale_source = client.get(
        f"/v1/projects/{brief_ready_project}/briefs/latest", headers=_headers()
    ).json()
    created = _create_constraint(
        client, brief_ready_project, version=1, attributeId="confirmed-material"
    )
    assert created.json()["projectState"]["briefStale"] is True

    edited_payload = dict(stale_source["payload"])
    edited_payload["goals"] = ["保留祖传书柜"]
    edited = client.patch(
        f"/v1/projects/{brief_ready_project}/briefs/1",
        headers=_headers(),
        json={
            "idempotencyKey": "edit-stale",
            "expectedStateVersion": created.json()["stateVersion"],
            "data": {"payload": edited_payload},
        },
    )

    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["version"] == 2
    assert body["payload"]["goals"] == ["保留祖传书柜"]
    assert any(
        item["statement"] == "天然石材工作台超出当前预算档位"
        for item in body["payload"]["constraints"]
    )
    state = client.get(f"/v1/projects/{brief_ready_project}/state", headers=_headers()).json()
    assert state["projectState"]["briefStale"] is False


def test_realign_preserves_user_edited_goals(client, brief_ready_project) -> None:
    source = client.get(
        f"/v1/projects/{brief_ready_project}/briefs/latest", headers=_headers()
    ).json()
    edited_payload = dict(source["payload"])
    edited_payload["goals"] = ["保留祖传书柜"]
    edited = client.patch(
        f"/v1/projects/{brief_ready_project}/briefs/1",
        headers=_headers(),
        json={
            "idempotencyKey": "edit-goals",
            "expectedStateVersion": 1,
            "data": {"payload": edited_payload},
        },
    )
    assert edited.status_code == 200, edited.text

    created = _create_constraint(
        client,
        brief_ready_project,
        version=edited.json()["stateVersion"],
        attributeId="confirmed-material",
    )
    realigned = client.post(
        f"/v1/projects/{brief_ready_project}/realign",
        headers=_headers(),
        json={
            "idempotencyKey": "realign-goals",
            "expectedStateVersion": created.json()["stateVersion"],
            "data": {},
        },
    )

    assert realigned.status_code == 200, realigned.text
    regenerated = client.get(
        f"/v1/projects/{brief_ready_project}/briefs/latest", headers=_headers()
    ).json()
    assert regenerated["version"] == 3
    assert regenerated["payload"]["goals"] == ["保留祖传书柜"]
    assert any(
        item["statement"] == "天然石材工作台超出当前预算档位"
        for item in regenerated["payload"]["constraints"]
    )


def test_preference_value_change_after_resolution_opens_a_new_conflict(
    client, ready_project
) -> None:
    version = _confirmed_preference(client, ready_project)
    created = _create_constraint(
        client,
        ready_project,
        version=version,
        incompatibleWith=["natural stone", "solid oak"],
    ).json()
    conflict_id = created["projectState"]["conflicts"][0]["id"]
    resolved = client.post(
        f"/v1/projects/{ready_project}/conflicts/{conflict_id}/resolve",
        headers=_headers(),
        json={
            "idempotencyKey": "resolve-1",
            "expectedStateVersion": created["stateVersion"],
            "data": {"status": "resolved", "resolution": "允许天然石材作为例外"},
        },
    )
    assert resolved.status_code == 200, resolved.text

    changed = client.patch(
        f"/v1/projects/{ready_project}/attributes/manual-material",
        headers=_headers(),
        json={
            "idempotencyKey": "to-solid-oak",
            "expectedStateVersion": resolved.json()["stateVersion"],
            "data": {"status": "confirmed", "value": "solid oak"},
        },
    )

    assert changed.status_code == 200, changed.text
    conflicts = changed.json()["projectState"]["conflicts"]
    assert any(c["id"] == conflict_id and c["status"] == "resolved" for c in conflicts)
    opened = [c for c in conflicts if c["status"] == "open"]
    assert len(opened) == 1
    assert "solid oak" in opened[0]["impact"]


def test_brief_edit_cannot_drop_system_constraints(client, brief_ready_project) -> None:
    source = client.get(
        f"/v1/projects/{brief_ready_project}/briefs/latest", headers=_headers()
    ).json()
    created = _create_constraint(
        client, brief_ready_project, version=1, attributeId="confirmed-material"
    )
    first = client.patch(
        f"/v1/projects/{brief_ready_project}/briefs/1",
        headers=_headers(),
        json={
            "idempotencyKey": "edit-1",
            "expectedStateVersion": created.json()["stateVersion"],
            "data": {"payload": {**source["payload"], "goals": ["用户目标"]}},
        },
    )
    assert first.status_code == 200, first.text

    # A later, non-stale edit submits a payload with no constraints and a low completeness.
    tampered = dict(first.json()["payload"])
    tampered["constraints"] = []
    tampered["completeness"] = 0.1
    tampered["goals"] = ["用户目标2"]
    second = client.patch(
        f"/v1/projects/{brief_ready_project}/briefs/2",
        headers=_headers(),
        json={
            "idempotencyKey": "edit-2",
            "expectedStateVersion": first.json()["stateVersion"],
            "data": {"payload": tampered},
        },
    )

    assert second.status_code == 200, second.text
    body = second.json()
    assert body["version"] == 3
    assert body["payload"]["goals"] == ["用户目标2"]
    assert body["payload"]["completeness"] == 0.875
    assert any(
        item["statement"] == "天然石材工作台超出当前预算档位"
        for item in body["payload"]["constraints"]
    )


def test_brief_edit_blocked_by_open_critical_conflict(client, brief_ready_project) -> None:
    created = _create_constraint(
        client,
        brief_ready_project,
        version=1,
        severity="critical",
        attributeId="confirmed-material",
        incompatibleWith=["confirmed material"],
    )
    conflicts = created.json()["projectState"]["conflicts"]
    assert any(c["status"] == "open" and c["severity"] == "critical" for c in conflicts)

    response = client.patch(
        f"/v1/projects/{brief_ready_project}/briefs/1",
        headers=_headers(),
        json={
            "idempotencyKey": "edit-critical",
            "expectedStateVersion": created.json()["stateVersion"],
            "data": {"payload": {}},
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BRIEF_REVIEW_FAILED"
