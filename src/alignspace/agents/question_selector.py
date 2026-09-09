from pydantic import BaseModel, Field


class QuestionCandidate(BaseModel):
    id: str
    uncertainty: float = Field(ge=0, le=1)
    impact: float = Field(ge=0, le=1)
    conflict_relevance: float = Field(ge=0, le=1)
    coverage_gap: float = Field(ge=0, le=1)
    effort: float = Field(ge=0, le=1)
    fingerprint: str
    text: str = ""


def score(candidate: QuestionCandidate) -> float:
    return (
        0.35 * candidate.uncertainty
        + 0.30 * candidate.impact
        + 0.20 * candidate.conflict_relevance
        + 0.10 * candidate.coverage_gap
        - 0.05 * candidate.effort
    )


def select_question(
    candidates: list[QuestionCandidate], history: set[str]
) -> QuestionCandidate | None:
    eligible = [candidate for candidate in candidates if candidate.fingerprint not in history]
    return max(eligible, key=score, default=None)
