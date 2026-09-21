"""Candidate preference analysis domain model.

Three facts are deliberately kept separate:

* :attr:`DesignEntry.attention_dimensions` -- dimensions the homeowner said they
  care about ("I like the wall material").
* :attr:`CandidatePreference.proposed_value` -- what the model observed or
  inferred, with an explicit ``certainty`` ("the wall may be microcement").
* :attr:`CandidatePreference.confirmed_value` -- the design requirement the
  homeowner actually confirmed ("use microcement").

Confirming a preference never asserts that the real material in the photo was
verified. Candidates are an organisation of proposals; only confirmation writes
into the formal :class:`alignspace.domain.models.Attribute` system.
"""

import hashlib
import json
from enum import Enum

from pydantic import Field, model_validator

from alignspace.domain.models import DomainModel, Evidence, NonBlankString


class CandidateDimension(str, Enum):
    COLOUR = "colour"
    MATERIAL = "material"
    STYLE = "style"
    LAYING = "laying"
    LIGHTING = "lighting"
    OTHER = "other"


class Certainty(str, Enum):
    """How confident the model is in an observed/inferred value."""

    INFERRED = "inferred"
    UNCERTAIN = "uncertain"


class CandidateStatus(str, Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    DISMISSED = "dismissed"


class EntryStatus(str, Enum):
    OPEN = "open"
    PARTIALLY_CONFIRMED = "partially_confirmed"
    CONFIRMED = "confirmed"
    DISMISSED = "dismissed"
    SOURCE_DELETED = "source_deleted"


class AnalysisStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class ProviderMode(str, Enum):
    MOCK = "mock"
    DEEPSEEK = "deepseek"


class InputAsset(DomainModel):
    asset_id: NonBlankString
    sha256: str


class CandidatePreference(DomainModel):
    id: str
    entry_id: str
    dimension: CandidateDimension
    certainty: Certainty
    proposed_value: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    status: CandidateStatus = CandidateStatus.PROPOSED
    confirmed_value: str | None = None
    attribute_id: str | None = None
    decided_by: str | None = None

    @model_validator(mode="after")
    def validate_candidate(self) -> "CandidatePreference":
        proposed = self.proposed_value.strip() if self.proposed_value else None
        if self.certainty == Certainty.INFERRED and not proposed:
            raise ValueError("an inferred candidate requires a proposed value")
        if self.status == CandidateStatus.CONFIRMED:
            if not (self.confirmed_value and self.confirmed_value.strip()):
                raise ValueError("a confirmed candidate requires a confirmed value")
        elif self.confirmed_value is not None or self.attribute_id is not None:
            raise ValueError("only a confirmed candidate may carry a confirmed value")
        return self


class DesignEntry(DomainModel):
    """Organisational grouping for candidates of one source image and part."""

    id: str
    analysis_run_id: str
    source_asset_id: str | None
    target_element: NonBlankString
    attention_dimensions: list[CandidateDimension] = Field(default_factory=list)
    note: str = ""
    status: EntryStatus = EntryStatus.OPEN


class AnalysisRun(DomainModel):
    id: str
    status: AnalysisStatus
    requested_by: str
    description: str
    input_assets: list[InputAsset]
    input_fingerprint: str
    provider_mode: ProviderMode
    model: str
    prompt_version: str
    schema_version: str
    third_party_consent: bool = False
    error: str | None = None


def calculate_analysis_fingerprint(
    assets: list[tuple[str, str]],
    description: str,
    prompt_version: str,
) -> str:
    """Stable fingerprint of an analysis input.

    Asset order does not matter, but membership, image content hashes, the
    homeowner description and the prompt version do. A stored result whose
    fingerprint no longer matches must not overwrite newer state.
    """
    canonical = json.dumps(
        {
            "assets": sorted([asset_id, digest] for asset_id, digest in assets),
            "description": description,
            "promptVersion": prompt_version,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
