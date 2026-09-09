from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from alignspace.domain.enums import ActorKind, AttributeStatus, EvidenceSource, ProjectStatus


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class DomainModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class Evidence(DomainModel):
    source_type: EvidenceSource
    source_id: str
    description: str


class Attribute(DomainModel):
    id: str
    target_element: str
    dimension: str
    value: str
    status: AttributeStatus
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    actor: ActorKind
    updated_at: datetime | None = None


class ProjectState(DomainModel):
    project_id: str
    state_version: int = 0
    status: ProjectStatus = ProjectStatus.DRAFT
    attributes: list[Attribute] = Field(default_factory=list)
