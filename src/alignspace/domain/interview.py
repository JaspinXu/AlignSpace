"""Apply a structured homeowner interview answer to the shared state.

A confirmed/rejected/not_applicable selection is written into shared preferences
(attributes), validated against the current question and the still-active source
images. Free text is kept only as a note and is never parsed. Preferences keep
their id and evidence when updated, and any resulting change re-checks designer
constraints, brief staleness and approvals.
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
    state: ProjectState,
    question: Question,
    data: dict[str, object],
    active_asset_ids: set[str] | None = None,
) -> ProjectState:
    if question.kind == QuestionKind.CONFLICT or question.id.startswith("question-conflict-"):
        return _resolve_conflict_question(state, question, data)
    validate_interview_response(state, question, data, active_asset_ids)
    return _apply_preference_answer(state, question, data)


def validate_interview_response(
    state: ProjectState,
    question: Question,
    data: dict[str, object],
    active_asset_ids: set[str] | None = None,
) -> None:
    """Reject answers that do not belong to the current question or whose source
    image is gone, so a stale option can never rewrite an unrelated preference."""
    if data.get("skipped") is True:
        return
    if question.kind == QuestionKind.BROAD_PARTS:
        if data.get("selection"):
            raise InterviewResponseError(
                "broad questions accept parts, not preference selections"
            )
        allowed_parts = {(option.asset_id, option.target_element) for option in question.options}
        for item in data.get("parts") or []:
            if not isinstance(item, dict):
                raise InterviewResponseError("parts items must be objects")
            key = (item.get("assetId"), item.get("targetElement"))
            if key not in allowed_parts:
                raise InterviewResponseError("selected part is not part of the current question")
            _require_active(key[0], active_asset_ids)
        return

    if data.get("parts"):
        raise InterviewResponseError("detail questions accept a selection, not parts")
    selection = data.get("selection") or []
    if not isinstance(selection, list):
        raise InterviewResponseError("selection must be a list")
    by_id = {option.attribute_id: option for option in question.options if option.attribute_id}
    by_triple = {
        (option.asset_id, option.target_element, option.dimension): option
        for option in question.options
    }
    for item in selection:
        if not isinstance(item, dict):
            raise InterviewResponseError("selection items must be objects")
        attribute_id = item.get("attributeId")
        if isinstance(attribute_id, str) and attribute_id:
            option = by_id.get(attribute_id)
            if option is None:
                raise InterviewResponseError("selection is not part of the current question")
            asset_id = item.get("assetId") or option.asset_id
        else:
            triple = (
                item.get("assetId") or question.asset_id,
                item.get("targetElement") or question.target_element,
                item.get("dimension") or question.dimension,
            )
            option = by_triple.get(triple)
            if option is None:
                raise InterviewResponseError("selection is not part of the current question")
            asset_id = option.asset_id
        _require_active(asset_id, active_asset_ids)


def _require_active(asset_id: object, active_asset_ids: set[str] | None) -> None:
    if active_asset_ids is None or asset_id is None:
        return
    if asset_id not in active_asset_ids:
        raise InterviewResponseError("the source image for this selection is no longer available")


def _apply_preference_answer(
    state: ProjectState, question: Question, data: dict[str, object]
) -> ProjectState:
    skipped = bool(data.get("skipped"))
    selection = data.get("selection") or []
    parts = data.get("parts") or []
    note = data.get("answer")
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
    if existing is None and asset_id and not _has_image_evidence(evidence, asset_id):
        evidence.append(
            Evidence(
                source_type=EvidenceSource.IMAGE,
                source_id=asset_id,
                description=f"Homeowner preference for {target} {dimension}.",
            )
        )
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


def _has_image_evidence(evidence: list[Evidence], asset_id: str) -> bool:
    return any(
        item.source_type == EvidenceSource.IMAGE and item.source_id == asset_id
        for item in evidence
    )


def _as_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None
