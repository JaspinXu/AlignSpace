import json
from pathlib import Path

from alignspace.domain.enums import ProjectStatus
from alignspace.domain.models import BriefVersion, ProjectState, calculate_brief_content_hash

_CONSTRAINT_EXCLUDES = {
    "evidence",
    "verified_by",
    "withdrawn",
    "revision",
    "incompatible_with",
}


def build_brief_payload(state: ProjectState) -> dict[str, object]:
    root = Path(__file__).resolve().parents[3]
    payload = json.loads((root / "examples/project-haven.design-brief.json").read_text())
    payload["project"]["id"] = state.project_id
    payload["project"]["status"] = ProjectStatus.AWAITING_APPROVAL.value
    payload["completeness"] = state.completeness
    payload["version"] = max((brief.version for brief in state.brief_versions), default=0) + 1
    payload.pop("contentHash", None)
    payload["approvals"] = []
    payload["attributes"] = [
        attribute.model_dump(mode="json", by_alias=True, exclude_none=True)
        for attribute in state.attributes
    ]
    payload["constraints"] = [
        constraint.model_dump(
            mode="json",
            by_alias=True,
            exclude=_CONSTRAINT_EXCLUDES,
            exclude_none=True,
        )
        for constraint in state.constraints
        if not constraint.withdrawn
    ]
    payload["conflicts"] = [
        conflict.model_dump(mode="json", by_alias=True, exclude_none=True)
        for conflict in state.conflicts
    ]
    payload["unresolvedDecisions"] = [
        attribute.value
        for attribute in state.attributes
        if attribute.status.value == "unresolved"
    ]
    return payload


def build_brief_version(state: ProjectState) -> BriefVersion:
    payload = build_brief_payload(state)
    return BriefVersion(
        version=int(payload["version"]),
        content_hash=calculate_brief_content_hash(payload),
        payload=payload,
        completeness=float(payload["completeness"]),
    )
