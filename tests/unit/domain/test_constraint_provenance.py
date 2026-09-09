import pytest
from pydantic import ValidationError

from alignspace.domain.enums import (
    ConstraintCategory,
    ConstraintOwner,
    ConstraintSeverity,
    ConstraintVerificationStatus,
    EvidenceSource,
)
from alignspace.domain.models import Constraint, Evidence


def constraint_fields() -> dict[str, object]:
    return {
        "id": "constraint-1",
        "category": ConstraintCategory.SAFETY,
        "statement": "Use a safe wall-mounting method.",
        "severity": ConstraintSeverity.CRITICAL,
        "verification_status": ConstraintVerificationStatus.DESIGNER_ASSERTED,
        "owner": ConstraintOwner.DESIGNER,
        "evidence": [
            Evidence(
                source_type=EvidenceSource.DESIGNER_NOTE,
                source_id="note-1",
                description="Designer feasibility review",
            )
        ],
    }


def test_designer_asserted_constraint_keeps_evidence_provenance() -> None:
    constraint = Constraint(**constraint_fields())

    assert constraint.evidence[0].source_type == EvidenceSource.DESIGNER_NOTE


def test_constraint_rejects_missing_evidence_provenance() -> None:
    fields = constraint_fields()
    fields["evidence"] = []

    with pytest.raises(ValidationError, match="at least 1 item"):
        Constraint(**fields)


def test_verified_constraint_rejects_non_professional_owner() -> None:
    fields = constraint_fields()
    fields.update(
        {
            "verification_status": ConstraintVerificationStatus.VERIFIED,
            "owner": ConstraintOwner.HOMEOWNER,
            "verified_by": "professional-1",
            "evidence": [
                Evidence(
                    source_type=EvidenceSource.PROFESSIONAL_REVIEW,
                    source_id="review-1",
                    description="Qualified professional review",
                )
            ],
        }
    )

    with pytest.raises(
        ValidationError,
        match="verified constraints must be owned by a qualified professional",
    ):
        Constraint(**fields)


def test_qualified_professional_can_verify_constraint_with_review_evidence() -> None:
    fields = constraint_fields()
    fields.update(
        {
            "verification_status": ConstraintVerificationStatus.VERIFIED,
            "owner": ConstraintOwner.QUALIFIED_PROFESSIONAL,
            "verified_by": "professional-1",
            "evidence": [
                Evidence(
                    source_type=EvidenceSource.PROFESSIONAL_REVIEW,
                    source_id="review-1",
                    description="Qualified professional review",
                )
            ],
        }
    )

    constraint = Constraint(**fields)

    assert constraint.verified_by == "professional-1"
