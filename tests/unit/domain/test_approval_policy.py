import hashlib

import pytest
from pydantic import ValidationError

from alignspace.domain.enums import ConflictStatus, ConflictType, ConstraintSeverity, Role
from alignspace.domain.models import (
    Approval,
    BriefVersion,
    Conflict,
    ProjectState,
    calculate_brief_content_hash,
)
from alignspace.domain.policies import can_approve


def brief_payload() -> dict[str, object]:
    return {"style": "warm modern", "approvals": [{"role": "homeowner"}]}


def matching_approvals(
    *, brief_version: int = 2, content_hash: str | None = None
) -> list[Approval]:
    digest = content_hash or calculate_brief_content_hash(brief_payload())
    return [
        Approval(
            role=Role.HOMEOWNER,
            actor_id="h-1",
            brief_version=brief_version,
            content_hash=digest,
        ),
        Approval(
            role=Role.DESIGNER,
            actor_id="d-1",
            brief_version=brief_version,
            content_hash=digest,
        ),
    ]


def test_same_version_and_hash_from_both_roles_is_required() -> None:
    payload = brief_payload()
    content_hash = calculate_brief_content_hash(payload)
    brief = BriefVersion(version=2, content_hash=content_hash, payload=payload, completeness=0.9)
    state = ProjectState(
        project_id="project-1",
        completeness=0.9,
        approvals=matching_approvals(content_hash=content_hash),
    )

    assert can_approve(state, brief) is True


def test_brief_completeness_below_threshold_blocks_approval() -> None:
    payload = brief_payload()
    content_hash = calculate_brief_content_hash(payload)
    brief = BriefVersion(version=2, content_hash=content_hash, payload=payload, completeness=0.84)
    state = ProjectState(
        project_id="project-1",
        completeness=0.9,
        approvals=matching_approvals(content_hash=content_hash),
    )

    assert can_approve(state, brief) is False


def test_open_critical_conflict_blocks_approval() -> None:
    payload = brief_payload()
    content_hash = calculate_brief_content_hash(payload)
    brief = BriefVersion(version=2, content_hash=content_hash, payload=payload, completeness=0.9)
    state = ProjectState(
        project_id="project-1",
        completeness=0.9,
        approvals=matching_approvals(content_hash=content_hash),
        conflicts=[
            Conflict(
                id="c-1",
                type=ConflictType.PREFERENCE_VS_CONSTRAINT,
                summary="Unsafe wall change",
                impact="Professional review required",
                status=ConflictStatus.OPEN,
                severity=ConstraintSeverity.CRITICAL,
            )
        ],
    )

    assert can_approve(state, brief) is False


def test_content_hash_uses_canonical_json_without_top_level_approvals() -> None:
    payload = {"style": "é", "approvals": [{"role": "homeowner"}], "budget": 1200}

    digest = calculate_brief_content_hash(payload)

    assert digest == hashlib.sha256(
        '{"budget":1200,"style":"é"}'.encode()
    ).hexdigest()


def test_brief_rejects_content_hash_that_does_not_match_its_payload() -> None:
    payload = brief_payload()

    with pytest.raises(ValidationError, match="content_hash must match canonical payload SHA-256"):
        BriefVersion(version=2, content_hash="0" * 64, payload=payload, completeness=0.9)


def test_approval_rejects_non_lowercase_sha256_hash() -> None:
    with pytest.raises(ValidationError, match="content_hash"):
        Approval(role=Role.HOMEOWNER, actor_id="h-1", brief_version=2, content_hash="A" * 64)


def test_missing_designer_approval_blocks_approval() -> None:
    payload = brief_payload()
    content_hash = calculate_brief_content_hash(payload)
    brief = BriefVersion(version=2, content_hash=content_hash, payload=payload, completeness=0.9)
    state = ProjectState(
        project_id="project-1",
        completeness=0.9,
        approvals=matching_approvals(content_hash=content_hash)[:1],
    )

    assert can_approve(state, brief) is False


def test_approval_for_a_different_brief_version_blocks_approval() -> None:
    payload = brief_payload()
    content_hash = calculate_brief_content_hash(payload)
    brief = BriefVersion(version=2, content_hash=content_hash, payload=payload, completeness=0.9)
    state = ProjectState(
        project_id="project-1",
        completeness=0.9,
        approvals=matching_approvals(brief_version=1, content_hash=content_hash),
    )

    assert can_approve(state, brief) is False


def test_approval_for_a_different_valid_hash_blocks_approval() -> None:
    payload = brief_payload()
    content_hash = calculate_brief_content_hash(payload)
    different_hash = calculate_brief_content_hash({"style": "cool modern"})
    brief = BriefVersion(version=2, content_hash=content_hash, payload=payload, completeness=0.9)
    state = ProjectState(
        project_id="project-1",
        completeness=0.9,
        approvals=matching_approvals(content_hash=different_hash),
    )

    assert can_approve(state, brief) is False
