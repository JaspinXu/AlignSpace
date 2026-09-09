from alignspace.agents.alignment import AlignmentAgent
from alignspace.agents.contracts import AgentBundle
from alignspace.agents.designer import DesignerAgent
from alignspace.agents.homeowner import HomeownerInterviewAgent
from alignspace.agents.review import ReviewAgent
from alignspace.agents.vision import VisionAnalyst
from alignspace.domain.enums import (
    ActorKind,
    AttributeStatus,
    ConstraintCategory,
    ConstraintOwner,
    ConstraintSeverity,
    ConstraintVerificationStatus,
    EvidenceSource,
)
from alignspace.domain.models import Attribute, Constraint, Evidence, ProjectState


class SequenceLanguageProvider:
    def __init__(self, outputs: list[dict[str, object]]) -> None:
        self._outputs = list(outputs)
        self.calls = 0

    def generate(self, task: str, payload: dict[str, object]) -> dict[str, object]:
        del task, payload
        if self.calls >= len(self._outputs):
            raise RuntimeError("no configured provider output remains")
        output = self._outputs[self.calls]
        self.calls += 1
        return output


class MockVisionProvider:
    def analyze(self, state: ProjectState) -> list[Attribute]:
        del state
        observations = [
            ("wall", "colour", "warm beige", 0.86),
            ("chair", "material", "natural oak", 0.83),
            ("floor", "colour", "pale oak", 0.81),
            ("lighting", "lighting", "warm ambient", 0.84),
        ]
        return [
            Attribute(
                id=f"mock-{target}-{dimension}",
                target_element=target,
                dimension=dimension,
                value=value,
                status=AttributeStatus.PROPOSED,
                confidence=confidence,
                evidence=[
                    Evidence(
                        source_type=EvidenceSource.IMAGE,
                        source_id="living-room-1",
                        description=f"Mock image observation: {target} {dimension}",
                    )
                ],
                actor=ActorKind.VISION_AGENT,
            )
            for target, dimension, value, confidence in observations
        ]


def build_mock_agents() -> AgentBundle:
    budget_constraint = Constraint(
        id="mock-natural-stone-budget",
        category=ConstraintCategory.BUDGET,
        statement="Natural stone exceeds the configured budget fixture.",
        rationale="Use a stone-effect finish with a lower fixture cost band.",
        severity=ConstraintSeverity.IMPORTANT,
        verification_status=ConstraintVerificationStatus.DESIGNER_ASSERTED,
        owner=ConstraintOwner.DESIGNER,
        evidence=[
            Evidence(
                source_type=EvidenceSource.DESIGNER_NOTE,
                source_id="designer-fixture-1",
                description="Deterministic designer budget feedback.",
            )
        ],
    )
    return AgentBundle(
        vision=VisionAnalyst(MockVisionProvider()),
        homeowner=HomeownerInterviewAgent(),
        designer=DesignerAgent([budget_constraint]),
        alignment=AlignmentAgent(),
        review=ReviewAgent(),
    )
