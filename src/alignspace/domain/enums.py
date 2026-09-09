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
    HOMEOWNER = "homeowner"
    DESIGNER = "designer"
    ALIGNMENT_AGENT = "alignment_agent"


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
