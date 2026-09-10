import pytest

from alignspace.domain.policies import PolicyViolationError, validate_professional_claim


@pytest.mark.parametrize(
    "claim",
    [
        "This wall is definitely non-load-bearing and safe to remove",
        "The existing wiring can safely support this electrical load",
        "HDB approval is guaranteed and this is fully code compliant",
        "This finish is definitely fire-safe",
        "The completed work will cost exactly SGD 12,000",
        "This stone is in stock now and available today",
    ],
)
def test_unsupported_professional_assurance_is_blocked(claim: str) -> None:
    with pytest.raises(PolicyViolationError, match="professional review required"):
        validate_professional_claim(claim)


def test_matching_normalizes_case_punctuation_and_spacing() -> None:
    with pytest.raises(PolicyViolationError, match="structural"):
        validate_professional_claim("  NON–LOAD—BEARING... wall; SAFE TO REMOVE! ")


def test_ordinary_design_preference_is_allowed() -> None:
    validate_professional_claim("I prefer a warm beige wall and pale oak floor")
