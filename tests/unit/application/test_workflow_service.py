import pytest

from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.application.service import AuthorizationError, WorkflowService
from alignspace.domain.enums import Role
from alignspace.domain.policies import StaleStateError


def test_designer_cannot_answer_homeowner_question(service: WorkflowService) -> None:
    actor = ActorContext(actor_id="designer-1", role=Role.DESIGNER)
    envelope = WriteEnvelope(
        idempotency_key="key-1",
        expected_state_version=1,
        data={"answer": "yes"},
    )

    with pytest.raises(AuthorizationError, match="homeowner"):
        service.resume("project-1", actor, "homeowner", envelope)


def test_non_member_cannot_start_analysis(service: WorkflowService) -> None:
    actor = ActorContext(actor_id="outsider", role=Role.HOMEOWNER)
    envelope = WriteEnvelope(idempotency_key="key-1", expected_state_version=0, data={})

    with pytest.raises(AuthorizationError, match="not a project member"):
        service.start_analysis("project-1", actor, envelope)


def test_start_analysis_rejects_stale_state(service: WorkflowService) -> None:
    actor = ActorContext(actor_id="homeowner-1", role=Role.HOMEOWNER)
    envelope = WriteEnvelope(idempotency_key="key-stale", expected_state_version=3, data={})

    with pytest.raises(StaleStateError, match="expected version 3, current version 0"):
        service.start_analysis("project-1", actor, envelope)


def test_homeowner_can_confirm_an_observed_attribute(service: WorkflowService) -> None:
    actor = ActorContext(actor_id="homeowner-1", role=Role.HOMEOWNER)
    envelope = WriteEnvelope(
        idempotency_key="confirm-wall",
        expected_state_version=0,
        data={"status": "confirmed", "value": "soft warm beige"},
    )

    response = service.edit_attribute("project-1", "wall-colour", actor, envelope)

    attribute = next(
        item for item in response.project_state["attributes"] if item["id"] == "wall-colour"
    )
    assert response.state_version == 1
    assert attribute["status"] == "confirmed"
    assert attribute["value"] == "soft warm beige"
    assert attribute["actor"] == "homeowner"
