"""Apply a structured homeowner interview answer to the shared state.

A confirmed/rejected/not_applicable selection is written into shared preferences
(attributes). Free text is kept only as a note and is never parsed. Preferences
keep their id and evidence when updated, and any resulting change re-checks
designer constraints, brief staleness and approvals.
"""

from alignspace.domain.constraints import flag_brief_change, reconcile_constraints
from alignspace.domain.enums import (
    ActorKind,
    AttributeStatus,
    ConflictStatus,
    EvidenceSource,
    QuestionKind,
)
from alignspace.domain.models import Attribute, Evidence, ProjectState, Question
from alignspace.domain.policies import (
    calculate_completeness,
    record_conflict_attempt,
    validate_professional_claim,
)

DECISION_STATUS = {
    "confirmed": AttributeStatus.CONFIRMED,
    "rejected": AttributeStatus.REJECTED,
    "not_applicable": AttributeStatus.NOT_APPLICABLE,
}


class InterviewResponseError(ValueError):
    """Raised when a structured interview answer cannot be applied."""


def apply_interview_response(
    state: ProjectState, question: Question, data: dict[str, object]
) -> ProjectState:
    if question.kind == QuestionKind.CONFLICT or question.id.startswith("question-conflict-"):
        return _resolve_conflict_question(state, question, data)
    return _apply_preference_answer(state, question, data)


def _apply_preference_answer(
    state: ProjectState, question: Question, data: dict[str, object]
) -> ProjectState:
    skipped = bool(data.get("skipped"))
    selection = data.get("selection") or []
    parts = data.get("parts") or []
    note = data.get("answer")
    if not isinstance(selection, list):
        raise InterviewResponseError("selection must be a list")
    if not skipped and not selection and not parts and not (
        isinstance(note, str) and note.strip()
    ):
        raise InterviewResponseError("answer requires a note, selection, parts or skip")

    attributes = list(state.attributes)
    if not skipped:
        for item in selection:
            if not isinstance(item, dict):
                raise InterviewResponseError("selection items must be objects")
            attributes = _upsert_from_selection(attributes, question, item)

    response = {"skipped": skipped, "parts": parts, "selection": selection, "answer": note}
    questions = [
        item.model_copy(update={"answer": note, "skipped": skipped, "response": response})
        if item.id == question.id
        else item
        for item in state.questions
    ]
    updated = state.model_copy(update={"attributes": attributes, "questions": questions})
    updated = updated.model_copy(
        update={
            "conflicts": reconcile_constraints(updated),
            "completeness": calculate_completeness(updated),
        }
    )
    return flag_brief_change(updated)


def _upsert_from_selection(
    attributes: list[Attribute], question: Question, item: dict[str, object]
) -> list[Attribute]:
    status = DECISION_STATUS.get(str(item.get("decision", "confirmed")))
    if status is None:
        raise InterviewResponseError(f"unsupported decision {item.get('decision')!r}")

    attribute_id = item.get("attributeId")
    existing = _find(attributes, attribute_id) if isinstance(attribute_id, str) else None
    asset_id = _as_text(item.get("assetId")) or _image_source(existing) or question.asset_id
    target = _as_text(item.get("targetElement")) or (existing.target_element if existing else None) or question.target_element
    dimension = _as_text(item.get("dimension")) or (existing.dimension if existing else None) or question.dimension
    if existing is None:
        if not (asset_id and target and dimension):
            raise InterviewResponseError(
                "a new preference requires assetId, targetElement and dimension"
            )
        attribute_id = f"pref-{asset_id}-{target}-{dimension}"
        existing = _find(attributes, attribute_id)

    value = _as_text(item.get("value")) or (existing.value if existing else None)
    if not value:
        raise InterviewResponseError("a preference requires a value")
    validate_professional_claim(value)

    evidence = list(existing.evidence) if existing else []
    evidence.append(
        Evidence(
            source_type=EvidenceSource.HOMEOWNER_ANSWER,
            source_id=question.id,
            description="Homeowner structured answer.",
        )
    )
    changed = Attribute(
        id=attribute_id,
        target_element=existing.target_element if existing else target,
        dimension=existing.dimension if existing else dimension,
        value=value,
        status=status,
        confidence=1.0,
        evidence=evidence,
        actor=ActorKind.HOMEOWNER,
    )
    return [item for item in attributes if item.id != attribute_id] + [changed]


def _resolve_conflict_question(
    state: ProjectState, question: Question, data: dict[str, object]
) -> ProjectState:
    answer = data.get("answer")
    if not isinstance(answer, str) or not answer.strip():
        raise InterviewResponseError("conflict answers require text")
    conflict_id = question.id.removeprefix("question-conflict-")
    conflict = next((item for item in state.conflicts if item.id == conflict_id), None)
    if conflict is None:
        raise InterviewResponseError("conflict not found")
    validate_professional_claim(answer.strip())
    changed = record_conflict_attempt(conflict).model_copy(
        update={"status": ConflictStatus.RESOLVED, "resolution": answer.strip()}
    )
    questions = [
        item.model_copy(update={"answer": answer.strip()}) if item.id == question.id else item
        for item in state.questions
    ]
    updated = state.model_copy(
        update={
            "questions": questions,
            "conflicts": [
                changed if item.id == conflict_id else item for item in state.conflicts
            ],
        }
    )
    return flag_brief_change(updated)


def _find(attributes: list[Attribute], attribute_id: object) -> Attribute | None:
    if not isinstance(attribute_id, str):
        return None
    return next((item for item in attributes if item.id == attribute_id), None)


def _image_source(attribute: Attribute | None) -> str | None:
    if attribute is None:
        return None
    return next(
        (
            evidence.source_id
            for evidence in attribute.evidence
            if evidence.source_type == EvidenceSource.IMAGE
        ),
        None,
    )


def _as_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
