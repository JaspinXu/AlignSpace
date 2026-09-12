from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, Protocol

from pydantic import BaseModel, Field

from alignspace.domain.enums import NextAction, ReviewDecision
from alignspace.domain.models import Attribute, ProjectState
from alignspace.domain.patches import PatchOperation

if TYPE_CHECKING:
    from alignspace.agents.alignment import AlignmentAgent
    from alignspace.agents.designer import DesignerAgent
    from alignspace.agents.homeowner import HomeownerInterviewAgent
    from alignspace.agents.review import ReviewAgent
    from alignspace.agents.vision import VisionAnalyst


class AssetRef(NamedTuple):
    id: str
    media_type: str
    sha256: str


class VisionProvider(Protocol):
    def analyze(self, state: ProjectState, assets: list[AssetRef]) -> list[Attribute]: ...


class LanguageModelProvider(Protocol):
    def generate(self, task: str, payload: dict[str, object]) -> dict[str, object]: ...


class AgentResult(BaseModel):
    state: ProjectState
    patches: list[PatchOperation] = Field(default_factory=list)
    next_action: NextAction | None = None
    review_decision: ReviewDecision | None = None


class AgentBundle(NamedTuple):
    vision: VisionAnalyst
    homeowner: HomeownerInterviewAgent
    designer: DesignerAgent
    alignment: AlignmentAgent
    review: ReviewAgent
