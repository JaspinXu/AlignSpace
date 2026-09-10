import json
import tomllib
from pathlib import Path

import pytest
from pydantic import BaseModel

from alignspace.agents.contracts import AgentBundle
from alignspace.domain.enums import (
    AttributeStatus,
    ConstraintCategory,
    ConstraintOwner,
    ConstraintSeverity,
    ConstraintVerificationStatus,
    EvidenceSource,
    NextAction,
    ReviewDecision,
    Role,
)
from alignspace.domain.models import (
    BriefVersion,
    Constraint,
    Evidence,
    ProjectState,
    Question,
    calculate_brief_content_hash,
)
from alignspace.providers.mock import SequenceLanguageProvider, build_mock_agents
from alignspace.providers.validated import ProviderOutputError, generate_validated


def test_review_schema_validator_is_a_runtime_dependency() -> None:
    root = Path(__file__).resolve().parents[3]
    project = tomllib.loads((root / "pyproject.toml").read_text())

    assert any(
        dependency.startswith("jsonschema") for dependency in project["project"]["dependencies"]
    )


def test_mock_vision_returns_proposals_only() -> None:
    agents: AgentBundle = build_mock_agents()

    result = agents.vision.run(ProjectState(project_id="project-1"))

    assert len(result.patches) == 4
    assert all(operation.attribute.status == AttributeStatus.PROPOSED for operation in result.patches)
    assert result.state.state_version == 1


def test_alignment_requests_homeowner_when_visual_proposals_are_unconfirmed() -> None:
    agents = build_mock_agents()
    state = agents.vision.run(ProjectState(project_id="project-1")).state

    result = agents.alignment.run(state)

    assert result.next_action == NextAction.ASK_HOMEOWNER


def test_homeowner_agent_asks_broad_question_before_detail() -> None:
    agents = build_mock_agents()
    state = agents.vision.run(ProjectState(project_id="project-1")).state

    broad = agents.homeowner.run(state)

    assert broad.next_action == NextAction.ASK_HOMEOWNER
    assert broad.state.questions[-1].repetition_fingerprint == "liked-elements"

    answered = broad.state.model_copy(
        update={
            "questions": [
                broad.state.questions[-1].model_copy(update={"answer": "warm lighting"})
            ]
        }
    )
    detail = agents.homeowner.run(answered)

    assert detail.state.questions[-1].repetition_fingerprint != "liked-elements"
    assert "lighting" in detail.state.questions[-1].repetition_fingerprint
    assert detail.state.questions[-1].target_role == Role.HOMEOWNER


def test_designer_agent_only_applies_configured_fixture_feedback() -> None:
    agents = build_mock_agents()
    state = ProjectState(project_id="project-1")

    result = agents.designer.run(state)

    assert len(result.state.constraints) == 1
    assert result.state.constraints[0].evidence[0].source_id == "designer-fixture-1"
    assert len(result.state.conflicts) == 1
    assert result.state.conflicts[0].status == "open"


def test_alignment_routes_open_tradeoff_to_homeowner() -> None:
    agents = build_mock_agents()
    reviewed = agents.designer.run(ProjectState(project_id="project-1", completeness=1)).state

    result = agents.alignment.run(reviewed)

    assert result.next_action == NextAction.ASK_HOMEOWNER


def test_review_requires_policy_and_schema_gates() -> None:
    agents = build_mock_agents()
    incomplete = agents.review.run(ProjectState(project_id="project-1"))
    assert incomplete.review_decision == ReviewDecision.REPAIR

    root = Path(__file__).resolve().parents[3]
    payload = json.loads((root / "examples/project-haven.design-brief.json").read_text())
    brief = BriefVersion(
        version=payload["version"],
        content_hash=calculate_brief_content_hash(payload),
        payload=payload,
        completeness=payload["completeness"],
    )
    ready = ProjectState(project_id="project-1", completeness=0.9, brief_versions=[brief])

    reviewed = agents.review.run(ready)

    assert reviewed.review_decision == ReviewDecision.PASS


def test_invalid_provider_output_is_repaired_once() -> None:
    class Output(BaseModel):
        value: str

    provider = SequenceLanguageProvider(outputs=[{"wrong": "shape"}, {"value": "valid"}])

    result = generate_validated(provider, "test", {}, Output)

    assert result.value == "valid"
    assert provider.calls == 2


def test_provider_stops_after_second_invalid_output() -> None:
    class Output(BaseModel):
        value: str

    provider = SequenceLanguageProvider(outputs=[{"wrong": 1}, {"stillWrong": 2}])

    with pytest.raises(ProviderOutputError, match="two attempts"):
        generate_validated(provider, "test", {}, Output)

    assert provider.calls == 2


def test_homeowner_question_budget_is_not_bypassed() -> None:
    agents = build_mock_agents()
    state = ProjectState(
        project_id="project-1",
        questions=[
            Question(
                id=f"q-{index}",
                target_role=Role.HOMEOWNER,
                text=f"Question {index}",
                answer="answered",
                repetition_fingerprint=f"q-{index}",
            )
            for index in range(10)
        ],
    )

    result = agents.homeowner.run(state)

    assert result.state == state
    assert result.next_action == NextAction.STOP_UNRESOLVED


def test_alignment_escalates_unsupported_professional_claim() -> None:
    agents = build_mock_agents()
    state = ProjectState(
        project_id="project-1",
        completeness=1,
        constraints=[
            Constraint(
                id="unsafe-assurance",
                category=ConstraintCategory.SAFETY,
                statement="This wall is definitely non-load-bearing and safe to remove",
                severity=ConstraintSeverity.CRITICAL,
                verification_status=ConstraintVerificationStatus.DESIGNER_ASSERTED,
                owner=ConstraintOwner.DESIGNER,
                evidence=[
                    Evidence(
                        source_type=EvidenceSource.DESIGNER_NOTE,
                        source_id="designer-note-unsafe",
                        description="Unverified assurance.",
                    )
                ],
            )
        ],
    )

    result = agents.alignment.run(state)

    assert result.next_action == NextAction.REQUEST_PROFESSIONAL_REVIEW


def test_review_escalates_unsafe_claim_in_otherwise_valid_brief() -> None:
    agents = build_mock_agents()
    root = Path(__file__).resolve().parents[3]
    payload = json.loads((root / "examples/project-haven.design-brief.json").read_text())
    payload["goals"] = ["This wall is definitely non-load-bearing and safe to remove"]
    payload["completeness"] = 0.9
    brief = BriefVersion(
        version=payload["version"],
        content_hash=calculate_brief_content_hash(payload),
        payload=payload,
        completeness=0.9,
    )

    reviewed = agents.review.run(
        ProjectState(project_id="project-1", completeness=0.9, brief_versions=[brief])
    )

    assert reviewed.review_decision == ReviewDecision.ESCALATE
