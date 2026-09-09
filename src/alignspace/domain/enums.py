from enum import Enum


class ProjectStatus(str, Enum):
    DRAFT = "draft"
    ANALYSING = "analysing"
    HOMEOWNER_REVIEW = "homeowner_review"
    DESIGNER_REVIEW = "designer_review"
    ALIGNMENT = "alignment"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    ARCHIVED = "archived"


class ActorKind(str, Enum):
    VISION_AGENT = "vision_agent"
    HOMEOWNER_INTERVIEW_AGENT = "homeowner_interview_agent"
    DESIGNER_AGENT = "designer_agent"
    HOMEOWNER = "homeowner"
    DESIGNER = "designer"
    ALIGNMENT_AGENT = "alignment_agent"
    REVIEW_AGENT = "review_agent"


class AttributeStatus(str, Enum):
    PROPOSED = "proposed"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    CONFLICTED = "conflicted"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class EvidenceSource(str, Enum):
    IMAGE = "image"
    HOMEOWNER_ANSWER = "homeowner_answer"
    DESIGNER_NOTE = "designer_note"
    SYSTEM_RULE = "system_rule"


class Role(str, Enum):
    HOMEOWNER = "homeowner"
    DESIGNER = "designer"


class ConstraintCategory(str, Enum):
    BUDGET = "budget"
    SPACE = "space"
    FUNCTION = "function"
    MAINTENANCE = "maintenance"
    TIMELINE = "timeline"
    SAFETY = "safety"
    REGULATORY = "regulatory"
    AVAILABILITY = "availability"
    OTHER = "other"


class ConstraintSeverity(str, Enum):
    ADVISORY = "advisory"
    IMPORTANT = "important"
    CRITICAL = "critical"


class ConstraintVerificationStatus(str, Enum):
    UNVERIFIED = "unverified"
    DESIGNER_ASSERTED = "designer_asserted"
    PROFESSIONAL_REVIEW_REQUIRED = "professional_review_required"
    VERIFIED = "verified"


class ConstraintOwner(str, Enum):
    DESIGNER = "designer"
    QUALIFIED_PROFESSIONAL = "qualified_professional"
    HOMEOWNER = "homeowner"


class ConflictStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    ACCEPTED_UNRESOLVED = "accepted_unresolved"


class NextAction(str, Enum):
    ASK_HOMEOWNER = "ask_homeowner"
    ASK_DESIGNER = "ask_designer"
    REQUEST_PROFESSIONAL_REVIEW = "request_professional_review"
    DRAFT_BRIEF = "draft_brief"
    STOP_UNRESOLVED = "stop_unresolved"


class ReviewDecision(str, Enum):
    REPAIR = "repair"
    DOWNGRADE = "downgrade"
    REDACT = "redact"
    ESCALATE = "escalate"
    PASS = "pass"
