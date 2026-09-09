from pydantic import Field

from alignspace.domain.enums import Role
from alignspace.domain.models import DomainModel, NonBlankString


class ActorContext(DomainModel):
    actor_id: NonBlankString
    role: Role


class WriteEnvelope[Payload](DomainModel):
    idempotency_key: NonBlankString
    expected_state_version: int = Field(ge=0)
    data: Payload
