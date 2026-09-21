"""Milestone 3: preference-to-space binding and joint approval.

A confirmed floor preference is mapped onto a supported material catalogue
entry, bound to a room, then explicitly applied as a new immutable space
version. Unsupported values fail, approximations require an explicit
acknowledgement, and a room identity change marks bindings for review instead
of silently transferring them. Joint approval must match both the brief and
the space version/hash.
"""


import pytest
from fastapi.testclient import TestClient

from alignspace.domain.enums import ActorKind, AttributeStatus, EvidenceSource
from alignspace.domain.models import Attribute, Evidence
from alignspace.persistence.uow import SqlAlchemyUnitOfWork

HOMEOWNER = {"X-Actor-Id": "homeowner-1", "X-Actor-Role": "homeowner"}
DESIGNER = {"X-Actor-Id": "designer-1", "X-Actor-Role": "designer"}


def current_version(client: TestClient, project_id: str, headers=HOMEOWNER) -> int:
    return client.get(f"/v1/projects/{project_id}", headers=headers).json()["stateVersion"]


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
    response = client.request(
        method,
        path,
        headers=headers,
        json={
            "idempotencyKey": key,
            "expectedStateVersion": current_version(client, project_id, headers),
            "data": data,
        },
    )
    assert response.status_code == expected, response.text
    return response


@pytest.fixture
def floor_project(client: TestClient, ready_project: str) -> str:
    """A project with one confirmed floor material preference."""
    container = client.app.state.container
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        state = uow.projects.load(ready_project)
        updated = state.model_copy(
            update={
                "attributes": [
                    Attribute(
                        id="pref-floor-material",
                        target_element="floor",
                        dimension="material",
                        value="pale oak",
                        status=AttributeStatus.CONFIRMED,
                        confidence=1.0,
                        evidence=[
                            Evidence(
                                source_type=EvidenceSource.HOMEOWNER_ANSWER,
                                source_id="cand-floor",
                                description="Homeowner confirmed the floor material.",
                            )
                        ],
                        actor=ActorKind.HOMEOWNER,
                    ),
                    Attribute(
                        id="pref-floor-proposed",
                        target_element="floor",
                        dimension="material",
                        value="warm grey",
                        status=AttributeStatus.PROPOSED,
                        confidence=0.6,
                        evidence=[
                            Evidence(
                                source_type=EvidenceSource.IMAGE,
                                source_id="asset-1",
                                description="Model inferred the floor material.",
                            )
                        ],
                        actor=ActorKind.VISION_AGENT,
                    ),
                ]
            }
        )
        uow.projects._replace_entities(updated)
        uow.commit()
    return ready_project


def add_room(client: TestClient, project_id: str, *, key: str = "room-1") -> str:
    response = write(
        client,
        "POST",
        f"/v1/projects/{project_id}/space/rooms",
        project_id,
        key,
        {"name": "客厅", "roomType": "living_room", "width": 4000, "depth": 5000},
    )
    return response.json()["plan"]["rooms"][-1]["id"]


def create_binding(
    client: TestClient,
    project_id: str,
    room_id: str,
    *,
    attribute_id: str = "pref-floor-material",
    material_option_id: str | None = None,
    confirm_approximation: bool = False,
    key: str = "binding-1",
    headers=HOMEOWNER,
    expected: int = 200,
):
    data: dict = {"attributeId": attribute_id, "roomId": room_id}
    if material_option_id is not None:
        data["materialOptionId"] = material_option_id
    if confirm_approximation:
        data["confirmApproximation"] = True
    return write(
        client,
        "POST",
        f"/v1/projects/{project_id}/space/bindings",
        project_id,
        key,
        data,
        headers=headers,
        expected=expected,
    )


def test_a_confirmed_floor_preference_binds_and_applies_to_a_new_space_version(
    client, floor_project
):
    room_id = add_room(client, floor_project)
    bound = create_binding(client, floor_project, room_id).json()
    assert len(bound["bindings"]) == 1
    binding = bound["bindings"][0]
    assert binding["status"] == "active"
    assert binding["materialOptionId"] == "floor.engineered-oak"
    assert binding["approximation"] == "exact"
    # Binding alone is a proposal: the space plan is unchanged so far.
    assert client.get(f"/v1/projects/{floor_project}/space", headers=HOMEOWNER).json()[
        "plan"
    ]["rooms"][0]["floor"]["materialOptionId"] is None

    applied = write(
        client,
        "POST",
        f"/v1/projects/{floor_project}/space/bindings/{binding['id']}/apply",
        floor_project,
        "apply-1",
        {},
    ).json()
    assert applied["version"] == 2
    assert applied["plan"]["rooms"][0]["floor"]["materialOptionId"] == "floor.engineered-oak"
    assert applied["plan"]["rooms"][0]["floor"]["bindingId"] == binding["id"]

    # Reload keeps both the applied material and the binding record.
    reloaded = client.get(f"/v1/projects/{floor_project}/space", headers=HOMEOWNER).json()
    assert reloaded["plan"]["rooms"][0]["floor"]["materialOptionId"] == "floor.engineered-oak"
    bindings = client.get(
        f"/v1/projects/{floor_project}/space/bindings", headers=HOMEOWNER
    ).json()
    assert bindings["bindings"][0]["appliedSpaceVersion"] == 2


def test_only_the_homeowner_may_bind_but_the_designer_may_apply(client, floor_project):
    room_id = add_room(client, floor_project)
    denied = create_binding(
        client, floor_project, room_id, headers=DESIGNER, expected=403
    )
    assert denied.json()["error"]["code"] == "FORBIDDEN"

    binding = create_binding(client, floor_project, room_id).json()["bindings"][0]
    applied = write(
        client,
        "POST",
        f"/v1/projects/{floor_project}/space/bindings/{binding['id']}/apply",
        floor_project,
        "designer-apply",
        {},
        headers=DESIGNER,
    ).json()
    assert applied["plan"]["rooms"][0]["floor"]["materialOptionId"] == "floor.engineered-oak"


def test_an_unconfirmed_preference_cannot_be_bound(client, floor_project):
    room_id = add_room(client, floor_project)
    rejected = create_binding(
        client,
        floor_project,
        room_id,
        attribute_id="pref-floor-proposed",
        key="proposed-binding",
        expected=409,
    )
    assert rejected.json()["error"]["code"] == "SPACE_STATE_INVALID"


def test_an_unsupported_material_is_rejected(client, ready_project):
    container = client.app.state.container
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        state = uow.projects.load(ready_project)
        state = state.model_copy(
            update={
                "attributes": [
                    Attribute(
                        id="pref-floor-material",
                        target_element="floor",
                        dimension="material",
                        value="solid gold",
                        status=AttributeStatus.CONFIRMED,
                        confidence=1.0,
                        evidence=[
                            Evidence(
                                source_type=EvidenceSource.HOMEOWNER_ANSWER,
                                source_id="cand-floor",
                                description="Homeowner confirmed the floor material.",
                            )
                        ],
                        actor=ActorKind.HOMEOWNER,
                    )
                ]
            }
        )
        uow.projects._replace_entities(state)
        uow.commit()
    room_id = add_room(client, ready_project)
    rejected = create_binding(client, ready_project, room_id, expected=409)
    assert rejected.json()["error"]["code"] == "UNSUPPORTED_MATERIAL"


def test_an_approximation_requires_an_explicit_acknowledgement(client, ready_project):
    container = client.app.state.container
    with SqlAlchemyUnitOfWork(container.session_factory) as uow:
        state = uow.projects.load(ready_project)
        state = state.model_copy(
            update={
                "attributes": [
                    Attribute(
                        id="pref-floor-material",
                        target_element="floor",
                        dimension="material",
                        value="natural stone",
                        status=AttributeStatus.CONFIRMED,
                        confidence=1.0,
                        evidence=[
                            Evidence(
                                source_type=EvidenceSource.HOMEOWNER_ANSWER,
                                source_id="cand-floor",
                                description="Homeowner confirmed the floor material.",
                            )
                        ],
                        actor=ActorKind.HOMEOWNER,
                    )
                ]
            }
        )
        uow.projects._replace_entities(state)
        uow.commit()
    room_id = add_room(client, ready_project)
    blocked = create_binding(client, ready_project, room_id, key="needs-ack", expected=409)
    assert blocked.json()["error"]["code"] == "APPROXIMATION_REQUIRES_CONFIRMATION"

    accepted = create_binding(
        client,
        ready_project,
        room_id,
        confirm_approximation=True,
        key="acknowledged",
    ).json()
    binding = accepted["bindings"][0]
    assert binding["approximation"] == "approximate"
    assert binding["note"]


def test_deleting_a_room_marks_its_bindings_for_review_without_silent_transfer(
    client, floor_project
):
    room_id = add_room(client, floor_project)
    binding = create_binding(client, floor_project, room_id).json()["bindings"][0]
    replacement = add_room(client, floor_project, key="room-2")
    # A second room exists, but the binding must not move to it silently.
    deleted = write(
        client,
        "DELETE",
        f"/v1/projects/{floor_project}/space/rooms/{room_id}",
        floor_project,
        "delete-room",
        {},
    ).json()
    assert all(room["id"] != room_id for room in deleted["plan"]["rooms"])
    bindings = client.get(
        f"/v1/projects/{floor_project}/space/bindings", headers=HOMEOWNER
    ).json()["bindings"]
    stored = next(item for item in bindings if item["id"] == binding["id"])
    assert stored["status"] == "needs_review"
    assert stored["roomId"] == room_id
    assert stored["roomId"] != replacement


def test_a_needs_review_binding_can_be_rebound_or_invalidated(client, floor_project):
    room_id = add_room(client, floor_project)
    binding = create_binding(client, floor_project, room_id).json()["bindings"][0]
    replacement = add_room(client, floor_project, key="room-2")
    write(
        client,
        "DELETE",
        f"/v1/projects/{floor_project}/space/rooms/{room_id}",
        floor_project,
        "delete-room",
        {},
    )

    rebound = write(
        client,
        "POST",
        f"/v1/projects/{floor_project}/space/bindings/{binding['id']}/review",
        floor_project,
        "rebind",
        {"status": "active", "roomId": replacement},
    ).json()["bindings"][0]
    assert rebound["status"] == "active"
    assert rebound["roomId"] == replacement

    invalidated = write(
        client,
        "POST",
        f"/v1/projects/{floor_project}/space/bindings/{binding['id']}/review",
        floor_project,
        "invalidate",
        {"status": "invalidated"},
    ).json()["bindings"][0]
    assert invalidated["status"] == "invalidated"


@pytest.fixture
def joint_project(client: TestClient, brief_ready_project: str) -> str:
    """A project with a complete brief and a space draft at version 1."""
    add_room(client, brief_ready_project)
    return brief_ready_project


def _latest_brief(client: TestClient, project_id: str) -> dict:
    response = client.get(f"/v1/projects/{project_id}/briefs/latest", headers=HOMEOWNER)
    assert response.status_code == 200, response.text
    return response.json()


def _approve_both(client: TestClient, project_id: str, key_suffix: str) -> dict:
    brief = _latest_brief(client, project_id)
    space = client.get(f"/v1/projects/{project_id}/space", headers=HOMEOWNER).json()
    data = {
        "briefVersion": brief["version"],
        "briefHash": brief["contentHash"],
        "spaceVersion": space["version"],
        "spaceHash": space["contentHash"],
    }
    first = write(
        client,
        "POST",
        f"/v1/projects/{project_id}/space/approvals",
        project_id,
        f"joint-homeowner-{key_suffix}",
        data,
    ).json()
    second = write(
        client,
        "POST",
        f"/v1/projects/{project_id}/space/approvals",
        project_id,
        f"joint-designer-{key_suffix}",
        data,
        headers=DESIGNER,
    ).json()
    return {"first": first, "second": second}


def test_joint_approval_requires_both_versions_and_hashes(client, joint_project):
    outcome = _approve_both(client, joint_project, "1")
    assert outcome["first"]["approved"] is False
    assert outcome["second"]["approved"] is True
    assert {item["role"] for item in outcome["second"]["approvals"]} == {"homeowner", "designer"}

    # A mismatched hash must not be accepted.
    brief = _latest_brief(client, joint_project)
    space = client.get(f"/v1/projects/{joint_project}/space", headers=HOMEOWNER).json()
    rejected = write(
        client,
        "POST",
        f"/v1/projects/{joint_project}/space/approvals",
        joint_project,
        "bad-hash",
        {
            "briefVersion": brief["version"],
            "briefHash": "0" * 64,
            "spaceVersion": space["version"],
            "spaceHash": space["contentHash"],
        },
        expected=409,
    )
    assert rejected.json()["error"]["code"] == "SPACE_APPROVAL_MISMATCH"


def test_an_old_space_approval_does_not_approve_a_new_version(client, joint_project):
    _approve_both(client, joint_project, "1")
    room_id = client.get(f"/v1/projects/{joint_project}/space", headers=HOMEOWNER).json()[
        "plan"
    ]["rooms"][0]["id"]
    write(
        client,
        "PATCH",
        f"/v1/projects/{joint_project}/space/rooms/{room_id}",
        joint_project,
        "rename",
        {"name": "会客厅"},
    )
    view = client.get(
        f"/v1/projects/{joint_project}/space/approvals", headers=HOMEOWNER
    ).json()
    assert view["spaceVersion"] == 2
    assert view["approved"] is False
    # The historical approval stays visible but does not apply to version 2.
    assert all(item["spaceVersion"] == 1 for item in view["approvals"])


def test_a_brief_only_approval_does_not_count_as_joint_approval(client, joint_project):
    brief = _latest_brief(client, joint_project)
    write(
        client,
        "POST",
        f"/v1/projects/{joint_project}/briefs/{brief['version']}/approvals",
        joint_project,
        "brief-approve",
        {"contentHash": brief["contentHash"]},
    )
    view = client.get(
        f"/v1/projects/{joint_project}/space/approvals", headers=HOMEOWNER
    ).json()
    assert view["approved"] is False
    assert view["approvals"] == []
