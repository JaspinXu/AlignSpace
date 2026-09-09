import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from alignspace.domain.enums import (
    ActorKind,
    AttributeStatus,
    ConflictStatus,
    ConflictType,
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


NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def calculate_brief_content_hash(payload: dict[str, object]) -> str:
    canonical_payload = {key: value for key, value in payload.items() if key != "approvals"}
    canonical_json = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class Evidence(DomainModel):
    source_type: EvidenceSource
    source_id: NonBlankString
    description: NonBlankString


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
    evidence: list[Evidence] = Field(min_length=1)
    verified_by: str | None = None

    @model_validator(mode="after")
    def validate_verified_provenance(self) -> "Constraint":
        if self.verification_status != ConstraintVerificationStatus.VERIFIED:
            return self
        if self.owner != ConstraintOwner.QUALIFIED_PROFESSIONAL:
            raise ValueError("verified constraints must be owned by a qualified professional")
        if not self.verified_by or not self.verified_by.strip():
            raise ValueError("verified constraints require verified_by")
        if not any(
            item.source_type == EvidenceSource.PROFESSIONAL_REVIEW for item in self.evidence
        ):
            raise ValueError("verified constraints require professional review evidence")
        return self


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
    type: ConflictType
    summary: str
    impact: str
    status: ConflictStatus
    resolution: str | None = None
    severity: ConstraintSeverity
    resolution_attempts: int = Field(default=0, ge=0, le=2)


class BriefVersion(DomainModel):
    version: int = Field(ge=1)
    content_hash: str
    payload: dict[str, object]
    completeness: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_content_hash(self) -> "BriefVersion":
        if self.content_hash != calculate_brief_content_hash(self.payload):
            raise ValueError("content_hash must match canonical payload SHA-256")
        return self


class Approval(DomainModel):
    role: Role
    actor_id: NonBlankString
    brief_version: int = Field(ge=1)
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
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
