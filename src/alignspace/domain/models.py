from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from alignspace.domain.enums import (
    ActorKind,
    AttributeStatus,
    ConflictStatus,
    ConstraintCategory,
    ConstraintOwner,
    ConstraintSeverity,
    ConstraintVerificationStatus,
    EvidenceSource,
    ProjectStatus,
    Role,
)


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


class Constraint(DomainModel):
    id: str
    category: ConstraintCategory
    statement: str
    rationale: str = ""
    severity: ConstraintSeverity
    verification_status: ConstraintVerificationStatus
    owner: ConstraintOwner


class Question(DomainModel):
    id: str
    target_role: Role
    text: str
    rationale: str = ""
    options: list[str] = Field(default_factory=list)
    answer: str | None = None
    repetition_fingerprint: str = ""


class Conflict(DomainModel):
    id: str
    type: str
    summary: str
    impact: str
    status: ConflictStatus
    resolution: str | None = None
    severity: ConstraintSeverity
    resolution_attempts: int = Field(default=0, ge=0)


class BriefVersion(DomainModel):
    version: int
    content_hash: str
    payload: dict[str, object]
    completeness: float = Field(ge=0, le=1)


class Approval(DomainModel):
    role: Role
    actor_id: str
    brief_version: int
    content_hash: str
    approved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProjectState(DomainModel):
    project_id: str
    state_version: int = 0
    status: ProjectStatus = ProjectStatus.DRAFT
    attributes: list[Attribute] = Field(default_factory=list)
    constraints: list[Constraint] = Field(default_factory=list)
    questions: list[Question] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    brief_versions: list[BriefVersion] = Field(default_factory=list)
    approvals: list[Approval] = Field(default_factory=list)
    completeness: float = Field(default=0, ge=0, le=1)
    current_node: str | None = None
    wait_reason: str | None = None
