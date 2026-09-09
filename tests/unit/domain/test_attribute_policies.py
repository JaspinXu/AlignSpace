from uuid import uuid4

import pytest

from alignspace.domain.enums import ActorKind, AttributeStatus, EvidenceSource
from alignspace.domain.models import Attribute, Evidence, ProjectState
from alignspace.domain.patches import StatePatch, UpsertAttribute, apply_patch
from alignspace.domain.policies import DomainRuleError


def make_attribute(actor: ActorKind, status: AttributeStatus) -> Attribute:
    source_type = (
        EvidenceSource.IMAGE
        if actor == ActorKind.VISION_AGENT
        else EvidenceSource.HOMEOWNER_ANSWER
    )
    return Attribute(
        id=str(uuid4()),
        target_element="wall",
        dimension="colour",
        value="warm beige",
        status=status,
        confidence=1.0 if actor == ActorKind.HOMEOWNER else 0.82,
        evidence=[
            Evidence(
                source_type=source_type,
                source_id="source-1",
                description="Recorded evidence",
            )
        ],
        actor=actor,
    )


def test_unmentioned_attribute_is_not_materialised() -> None:
    state = ProjectState(project_id="project-1")
    assert state.attributes == []


def test_homeowner_can_confirm_explicit_preference() -> None:
    state = ProjectState(project_id="project-1")
    attribute = make_attribute(ActorKind.HOMEOWNER, AttributeStatus.CONFIRMED)
    patch = StatePatch(
        expected_state_version=0, operations=[UpsertAttribute(attribute=attribute)]
    )
    updated = apply_patch(state, patch)
    assert updated.attributes == [attribute]
    assert updated.state_version == 1


def test_vision_agent_cannot_confirm_preference() -> None:
    state = ProjectState(project_id="project-1")
    attribute = make_attribute(ActorKind.VISION_AGENT, AttributeStatus.CONFIRMED)
    patch = StatePatch(
        expected_state_version=0, operations=[UpsertAttribute(attribute=attribute)]
    )
    with pytest.raises(DomainRuleError, match="vision observations must remain proposed"):
        apply_patch(state, patch)
