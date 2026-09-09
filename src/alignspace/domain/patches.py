from typing import Literal

from pydantic import BaseModel

from alignspace.domain.enums import ActorKind, AttributeStatus
from alignspace.domain.models import Attribute, ProjectState
from alignspace.domain.policies import DomainRuleError, StaleStateError


class UpsertAttribute(BaseModel):
    op: Literal["upsert_attribute"] = "upsert_attribute"
    attribute: Attribute


PatchOperation = UpsertAttribute


class StatePatch(BaseModel):
    expected_state_version: int
    operations: list[PatchOperation]


def apply_patch(state: ProjectState, patch: StatePatch) -> ProjectState:
    if patch.expected_state_version != state.state_version:
        raise StaleStateError(
            f"expected version {patch.expected_state_version}, current version {state.state_version}"
        )
    attributes = list(state.attributes)
    for operation in patch.operations:
        attribute = operation.attribute
        if (
            attribute.actor == ActorKind.VISION_AGENT
            and attribute.status != AttributeStatus.PROPOSED
        ):
            raise DomainRuleError("vision observations must remain proposed")
        attributes = [item for item in attributes if item.id != attribute.id]
        attributes.append(attribute)
    return state.model_copy(
        update={"attributes": attributes, "state_version": state.state_version + 1}
    )
