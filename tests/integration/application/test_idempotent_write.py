import pytest

from alignspace.application.commands import ActorContext, WriteEnvelope
from alignspace.domain.enums import Role
from alignspace.persistence.repository import IdempotencyConflictError


def test_identical_write_returns_original_result(service) -> None:
    actor = ActorContext(actor_id="homeowner-1", role=Role.HOMEOWNER)
    envelope = WriteEnvelope(idempotency_key="same-key", expected_state_version=0, data={})

    first = service.start_analysis("project-1", actor, envelope)
    second = service.start_analysis("project-1", actor, envelope)

    assert second == first
    assert first.state_version == 1
    assert first.wait_reason == "homeowner"


def test_same_key_with_different_content_is_rejected(service) -> None:
    actor = ActorContext(actor_id="homeowner-1", role=Role.HOMEOWNER)
    service.start_analysis(
        "project-1",
        actor,
        WriteEnvelope(idempotency_key="same-key", expected_state_version=0, data={}),
    )

    with pytest.raises(IdempotencyConflictError):
        service.start_analysis(
            "project-1",
            actor,
            WriteEnvelope(
                idempotency_key="same-key",
                expected_state_version=0,
                data={"fixture": "different"},
            ),
        )


def test_homeowner_can_resume_pending_question(service) -> None:
    actor = ActorContext(actor_id="homeowner-1", role=Role.HOMEOWNER)
    first = service.start_analysis(
        "project-1",
        actor,
        WriteEnvelope(idempotency_key="start", expected_state_version=0, data={}),
    )

    resumed = service.resume(
        "project-1",
        actor,
        "homeowner",
        WriteEnvelope(
            idempotency_key="answer",
            expected_state_version=first.state_version,
            data={"answer": "I also like the warm lighting"},
        ),
    )

    assert resumed.state_version == 2
    assert resumed.wait_reason == "homeowner"
