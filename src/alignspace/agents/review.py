import json
from pathlib import Path

from jsonschema import Draft202012Validator

from alignspace.agents.contracts import AgentResult
from alignspace.domain.enums import ReviewDecision
from alignspace.domain.models import ProjectState
from alignspace.domain.policies import can_draft_brief, professional_content_category


class ReviewAgent:
    def __init__(self, schema_path: Path | None = None) -> None:
        default_schema = Path(__file__).resolve().parents[3] / "schemas/design-brief.schema.json"
        path = schema_path or default_schema
        self._validator = Draft202012Validator(json.loads(path.read_text()))

    def run(self, state: ProjectState) -> AgentResult:
        if not can_draft_brief(state) or not state.brief_versions:
            return AgentResult(state=state, review_decision=ReviewDecision.REPAIR)
        latest = max(state.brief_versions, key=lambda brief: brief.version)
        if list(self._validator.iter_errors(latest.payload)):
            return AgentResult(state=state, review_decision=ReviewDecision.REPAIR)
        if professional_content_category(latest.payload) is not None:
            return AgentResult(state=state, review_decision=ReviewDecision.ESCALATE)
        return AgentResult(state=state, review_decision=ReviewDecision.PASS)
