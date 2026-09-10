import unicodedata

from alignspace.domain.enums import (
    AttributeStatus,
    ConflictStatus,
    ConstraintSeverity,
    Role,
)
from alignspace.domain.models import BriefVersion, Conflict, ProjectState, Question


class DomainRuleError(ValueError):
    """Raised when a change violates a domain invariant."""


class StaleStateError(ValueError):
    """Raised when a patch was generated from an older state version."""


class PolicyViolationError(ValueError):
    """Raised when an unsupported assurance requires qualified review."""


PROFESSIONAL_CLAIM_PATTERNS: dict[str, tuple[str, ...]] = {
    "structural": (
        "non load bearing",
        "load bearing",
        "safe to remove",
        "structurally safe",
    ),
    "electrical": (
        "existing wiring",
        "electrical load",
        "circuit capacity",
        "wiring can safely",
    ),
    "regulatory": (
        "hdb approval",
        "ura approval",
        "bca approval",
        "code compliant",
        "permit guaranteed",
    ),
    "safety-critical": (
        "definitely fire safe",
        "definitely safe",
        "asbestos free",
        "safety guaranteed",
    ),
    "exact-price": (
        "cost exactly",
        "exactly sgd",
        "guaranteed price",
        "fixed price",
    ),
    "live-availability": (
        "in stock now",
        "available today",
        "currently available",
        "live availability",
    ),
}


def _normalize_claim(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return " ".join(
        "".join(character if character.isalnum() else " " for character in normalized).split()
    )


def professional_claim_category(text: str) -> str | None:
    normalized = _normalize_claim(text)
    for category, patterns in PROFESSIONAL_CLAIM_PATTERNS.items():
        if any(pattern in normalized for pattern in patterns):
            return category
    return None


def professional_content_category(value: object) -> str | None:
    if isinstance(value, str):
        return professional_claim_category(value)
    if isinstance(value, dict):
        for item in value.values():
            category = professional_content_category(item)
            if category is not None:
                return category
    if isinstance(value, list):
        for item in value:
            category = professional_content_category(item)
            if category is not None:
                return category
    return None


def validate_professional_claim(text: str) -> None:
    category = professional_claim_category(text)
    if category is not None:
        raise PolicyViolationError(
            f"professional review required for unsupported {category} assurance"
        )


REQUIRED_DIMENSIONS = frozenset(
    {"style", "colour", "material", "lighting", "layout", "furniture", "mood", "function"}
)
DECIDED_STATUSES = frozenset(
    {AttributeStatus.CONFIRMED, AttributeStatus.UNRESOLVED, AttributeStatus.NOT_APPLICABLE}
)


def add_question(state: ProjectState, question: Question) -> ProjectState:
    count = sum(item.target_role == Role.HOMEOWNER for item in state.questions)
    if question.target_role == Role.HOMEOWNER and count >= 10:
        raise DomainRuleError("homeowner question budget exhausted")
    return state.model_copy(update={"questions": [*state.questions, question]})


def calculate_completeness(state: ProjectState) -> float:
    decided = {
        attribute.dimension
        for attribute in state.attributes
        if attribute.status in DECIDED_STATUSES
    }
    return len(decided & REQUIRED_DIMENSIONS) / len(REQUIRED_DIMENSIONS)


def can_draft_brief(state: ProjectState) -> bool:
    critical_open = any(
        item.status == ConflictStatus.OPEN and item.severity == ConstraintSeverity.CRITICAL
        for item in state.conflicts
    )
    return state.completeness >= 0.85 and not critical_open


def record_conflict_attempt(conflict: Conflict) -> Conflict:
    if conflict.resolution_attempts >= 2:
        raise DomainRuleError("conflict resolution budget exhausted")
    attempts = conflict.resolution_attempts + 1
    status = ConflictStatus.ESCALATED if attempts >= 2 else ConflictStatus.OPEN
    return conflict.model_copy(update={"resolution_attempts": attempts, "status": status})


def can_approve(state: ProjectState, brief: BriefVersion) -> bool:
    if not can_draft_brief(state) or brief.completeness < 0.85:
        return False
    approved_roles = {
        item.role
        for item in state.approvals
        if item.brief_version == brief.version and item.content_hash == brief.content_hash
    }
    return approved_roles == {Role.HOMEOWNER, Role.DESIGNER}
