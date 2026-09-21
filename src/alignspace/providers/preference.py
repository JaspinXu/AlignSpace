"""Candidate preference analysis provider boundary.

The provider turns selected reference images plus a homeowner description into
*proposed* design entries and candidate values. It never writes formal
preferences and never edits a space: proposals still have to be confirmed by the
homeowner.

The deterministic mock is the only provider used by tests and by this round. It
is explicitly rule-based, so a passing mock run must never be described as
verified image understanding.
"""

import hashlib
import re
from dataclasses import dataclass
from typing import NamedTuple, Protocol

from pydantic import BaseModel, Field

from alignspace.domain.enums import EvidenceSource
from alignspace.domain.models import DomainModel, Evidence
from alignspace.domain.preferences import (
    CandidateDimension,
    Certainty,
    ProviderMode,
)


class AnalysisAsset(NamedTuple):
    id: str
    media_type: str
    sha256: str
    data: bytes


@dataclass(frozen=True)
class PreferenceAnalysisRequest:
    assets: list[AnalysisAsset]
    description: str
    prompt_version: str
    schema_version: str


class ProposedCandidate(DomainModel):
    dimension: CandidateDimension
    certainty: Certainty
    proposed_value: str | None = None
    evidence: list[Evidence] = Field(default_factory=list)


class ProposedEntry(DomainModel):
    source_asset_id: str
    target_element: str
    attention_dimensions: list[CandidateDimension] = Field(default_factory=list)
    candidates: list[ProposedCandidate] = Field(default_factory=list)


class PreferenceAnalysisResult(BaseModel):
    """Provider DTO. Converted to domain candidates only after human review."""

    model_config = {"populate_by_name": True}

    entries: list[ProposedEntry] = Field(default_factory=list)
    model: str
    provider_mode: ProviderMode


class PreferenceAnalysisProvider(Protocol):
    def analyze(self, request: PreferenceAnalysisRequest) -> PreferenceAnalysisResult: ...


# --- deterministic mock -------------------------------------------------------

# Only parts and dimensions the homeowner actually mentioned produce candidates.
# Matching the description is deliberately a fixed, readable rule table, not a
# language model; nothing here reasons about an image's real content.
PART_KEYWORDS: dict[str, str] = {
    "床": "bed",
    "墙壁": "wall",
    "墙": "wall",
    "地板": "floor",
    "地面": "floor",
    "沙发": "sofa",
    "桌椅": "table_chair",
    "桌": "table",
    "椅": "chair",
    "窗帘": "curtain",
    "灯光": "lighting",
    "灯": "lighting",
}

DIMENSION_KEYWORDS: dict[str, CandidateDimension] = {
    "颜色": CandidateDimension.COLOUR,
    "色彩": CandidateDimension.COLOUR,
    "色": CandidateDimension.COLOUR,
    "材质": CandidateDimension.MATERIAL,
    "材料": CandidateDimension.MATERIAL,
    "样式": CandidateDimension.STYLE,
    "风格": CandidateDimension.STYLE,
    "铺设": CandidateDimension.LAYING,
    "铺法": CandidateDimension.LAYING,
    "灯光": CandidateDimension.LIGHTING,
    "照明": CandidateDimension.LIGHTING,
}

_VALUE_LIBRARY: dict[CandidateDimension, tuple[str, ...]] = {
    CandidateDimension.COLOUR: ("warm beige", "soft grey", "muted sage"),
    CandidateDimension.STYLE: ("warm modern", "soft minimal", "quiet classic"),
    CandidateDimension.LAYING: ("herringbone", "straight plank", "large-format tile"),
    CandidateDimension.LIGHTING: ("warm ambient", "layered soft light"),
}

_CLAUSE_SPLIT = re.compile(r"[、，,；;。.\n]+")


def parse_attention_dimensions(description: str) -> list[tuple[str, list[CandidateDimension]]]:
    """Return ``[(target_element, [dimensions])]`` mentioned by the homeowner.

    A clause contributes only when it names both a part and at least one
    dimension, so an unmentioned part never becomes an empty preference.
    """
    found: dict[str, list[CandidateDimension]] = {}
    for clause in _CLAUSE_SPLIT.split(description):
        part = next((value for key, value in PART_KEYWORDS.items() if key in clause), None)
        if part is None:
            continue
        dimensions: list[CandidateDimension] = []
        for keyword, dimension in DIMENSION_KEYWORDS.items():
            if keyword in clause and dimension not in dimensions:
                dimensions.append(dimension)
        if not dimensions:
            continue
        bucket = found.setdefault(part, [])
        for dimension in dimensions:
            if dimension not in bucket:
                bucket.append(dimension)
    return list(found.items())


class MockPreferenceAnalysisProvider:
    """Deterministic, explicable stand-in for real image understanding."""

    MODEL = "mock-deterministic"
    provider_mode = ProviderMode.MOCK

    def analyze(self, request: PreferenceAnalysisRequest) -> PreferenceAnalysisResult:
        entries: list[ProposedEntry] = []
        for asset in request.assets:
            for target_element, dimensions in parse_attention_dimensions(request.description):
                entries.append(
                    ProposedEntry(
                        source_asset_id=asset.id,
                        target_element=target_element,
                        attention_dimensions=dimensions,
                        candidates=[
                            self._candidate(asset, target_element, dimension)
                            for dimension in dimensions
                        ],
                    )
                )
        return PreferenceAnalysisResult(
            entries=entries,
            model=self.MODEL,
            provider_mode=ProviderMode.MOCK,
        )

    @staticmethod
    def _candidate(
        asset: AnalysisAsset, target_element: str, dimension: CandidateDimension
    ) -> ProposedCandidate:
        data_url_note = (
            f"Mock {dimension.value} observation from image {asset.sha256[:8]}: "
            f"{target_element}."
        )
        evidence = [
            Evidence(
                source_type=EvidenceSource.IMAGE,
                source_id=asset.id,
                description=data_url_note,
            )
        ]
        if dimension == CandidateDimension.MATERIAL:
            # Materials cannot be determined from a reference image here, so the
            # candidate is explicit about being uncertain instead of guessing.
            return ProposedCandidate(
                dimension=dimension,
                certainty=Certainty.UNCERTAIN,
                proposed_value=None,
                evidence=evidence,
            )
        options = _VALUE_LIBRARY.get(dimension, ("unspecified",))
        digest = hashlib.sha256(
            f"{asset.sha256}|{target_element}|{dimension.value}".encode()
        ).hexdigest()
        return ProposedCandidate(
            dimension=dimension,
            certainty=Certainty.INFERRED,
            proposed_value=options[int(digest[:8], 16) % len(options)],
            evidence=evidence,
        )
