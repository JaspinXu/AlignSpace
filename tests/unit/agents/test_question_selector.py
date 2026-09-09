import pytest

from alignspace.agents.question_selector import QuestionCandidate, score, select_question


def test_selector_prefers_high_information_non_repeated_question() -> None:
    candidates = [
        QuestionCandidate(
            id="wall-material",
            uncertainty=0.9,
            impact=0.8,
            conflict_relevance=0.8,
            coverage_gap=0.7,
            effort=0.2,
            fingerprint="wall-material",
        ),
        QuestionCandidate(
            id="chair-colour",
            uncertainty=0.4,
            impact=0.2,
            conflict_relevance=0.0,
            coverage_gap=0.3,
            effort=0.2,
            fingerprint="chair-colour",
        ),
    ]

    selected = select_question(candidates, history={"chair-colour"})

    assert selected is not None
    assert selected.id == "wall-material"


def test_selector_returns_none_when_every_candidate_repeats() -> None:
    candidate = QuestionCandidate(
        id="wall",
        uncertainty=1,
        impact=1,
        conflict_relevance=1,
        coverage_gap=1,
        effort=0,
        fingerprint="wall",
    )

    assert select_question([candidate], history={"wall"}) is None


def test_score_uses_the_specified_weights() -> None:
    candidate = QuestionCandidate(
        id="wall",
        uncertainty=1,
        impact=1,
        conflict_relevance=1,
        coverage_gap=1,
        effort=1,
        fingerprint="wall",
    )

    assert score(candidate) == pytest.approx(0.9)
