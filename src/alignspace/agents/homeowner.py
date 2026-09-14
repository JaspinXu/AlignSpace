from alignspace.agents.contracts import AgentResult
from alignspace.agents.question_selector import QuestionCandidate, select_question
from alignspace.domain.enums import (
    AttributeStatus,
    EvidenceSource,
    NextAction,
    QuestionKind,
    Role,
)
from alignspace.domain.models import Attribute, ProjectState, Question, QuestionOption
from alignspace.domain.patches import StatePatch, UpsertQuestion, apply_patch

BROAD_FINGERPRINT = "liked-elements"


class HomeownerInterviewAgent:
    MAX_QUESTIONS = 10

    def run(self, state: ProjectState) -> AgentResult:
        homeowner_questions = [
            question for question in state.questions if question.target_role == Role.HOMEOWNER
        ]
        if len(homeowner_questions) >= self.MAX_QUESTIONS:
            return AgentResult(state=state, next_action=NextAction.STOP_UNRESOLVED)
        pending = next(
            (
                question
                for question in homeowner_questions
                if question.answer is None
                and not question.skipped
                and question.response is None
            ),
            None,
        )
        if pending is not None:
            return AgentResult(state=state, next_action=NextAction.ASK_HOMEOWNER)

        history = {question.repetition_fingerprint for question in homeowner_questions}
        if BROAD_FINGERPRINT not in history:
            return self._append(state, self._broad_question(state))

        open_conflict = next(
            (
                conflict
                for conflict in state.conflicts
                if conflict.status.value == "open"
                and f"conflict:{conflict.id}" not in history
            ),
            None,
        )
        if open_conflict is not None:
            return self._append(
                state,
                Question(
                    id=f"question-conflict-{open_conflict.id}",
                    target_role=Role.HOMEOWNER,
                    text=(
                        f"The designer identified this trade-off: {open_conflict.summary} "
                        "Which option do you want to adopt?"
                    ),
                    rationale=open_conflict.impact,
                    repetition_fingerprint=f"conflict:{open_conflict.id}",
                    kind=QuestionKind.CONFLICT,
                ),
            )

        scored = self._detail_questions(state, history)
        if not scored:
            return AgentResult(state=state, next_action=NextAction.STOP_UNRESOLVED)
        chosen = select_question([candidate for candidate, _ in scored], history)
        assert chosen is not None
        question = next(item for candidate, item in scored if candidate.id == chosen.id)
        return self._append(state, question)

    def _broad_question(self, state: ProjectState) -> Question:
        options: list[QuestionOption] = []
        seen: set[tuple[str | None, str]] = set()
        for attribute in state.attributes:
            if attribute.status != AttributeStatus.PROPOSED:
                continue
            asset_id = _image_source(attribute)
            key = (asset_id, attribute.target_element)
            if key in seen:
                continue
            seen.add(key)
            options.append(
                QuestionOption(
                    label=attribute.target_element,
                    asset_id=asset_id,
                    target_element=attribute.target_element,
                )
            )
        return Question(
            id="question-liked-elements",
            target_role=Role.HOMEOWNER,
            text="这些参考图片里，还有哪些部位是你希望保留的？",
            rationale="先广泛确定屋主喜欢的部位，再针对所选部位细化颜色、材质等。",
            repetition_fingerprint=BROAD_FINGERPRINT,
            kind=QuestionKind.BROAD_PARTS,
            options=options,
        )

    def _selected_parts(self, state: ProjectState) -> set[tuple[str, str]]:
        broad = next(
            (
                question
                for question in state.questions
                if question.repetition_fingerprint == BROAD_FINGERPRINT
            ),
            None,
        )
        if broad is None or not broad.response:
            return set()
        parts = broad.response.get("parts")
        selected: set[tuple[str, str]] = set()
        if isinstance(parts, list):
            for item in parts:
                if (
                    isinstance(item, dict)
                    and isinstance(item.get("assetId"), str)
                    and isinstance(item.get("targetElement"), str)
                ):
                    selected.add((item["assetId"], item["targetElement"]))
        return selected

    def _detail_questions(
        self, state: ProjectState, history: set[str]
    ) -> list[tuple[QuestionCandidate, Question]]:
        selected_parts = self._selected_parts(state)
        groups: dict[tuple[str, str], list[Attribute]] = {}
        for attribute in state.attributes:
            if attribute.status != AttributeStatus.PROPOSED:
                continue
            asset_id = _image_source(attribute)
            if asset_id is None or (asset_id, attribute.target_element) not in selected_parts:
                continue
            groups.setdefault((attribute.target_element, attribute.dimension), []).append(
                attribute
            )
        scored: list[tuple[QuestionCandidate, Question]] = []
        for (element, dimension), attributes in groups.items():
            fingerprint = f"detail:{element}:{dimension}"
            if fingerprint in history:
                continue
            text = f"关于「{element}」的{dimension}，你更偏好哪一种？"
            candidate = QuestionCandidate(
                id=f"{element}-{dimension}",
                uncertainty=min(1 - attribute.confidence for attribute in attributes),
                impact=0.8,
                conflict_relevance=0.5,
                coverage_gap=0.8,
                effort=0.2,
                fingerprint=fingerprint,
                text=text,
            )
            options = [
                QuestionOption(
                    label=(
                        f"{attribute.target_element} · {attribute.dimension} · "
                        f"{attribute.value}"
                    ),
                    value=attribute.value,
                    asset_id=_image_source(attribute),
                    target_element=attribute.target_element,
                    dimension=attribute.dimension,
                    attribute_id=attribute.id,
                )
                for attribute in attributes
            ]
            question = Question(
                id=f"question-detail-{element}-{dimension}",
                target_role=Role.HOMEOWNER,
                text=text,
                rationale="细化所选部位的高影响属性。",
                repetition_fingerprint=fingerprint,
                kind=QuestionKind.DETAIL,
                target_element=element,
                dimension=dimension,
                options=options,
            )
            scored.append((candidate, question))
        return scored

    @staticmethod
    def _append(state: ProjectState, question: Question) -> AgentResult:
        operation = UpsertQuestion(question=question)
        updated = apply_patch(
            state,
            StatePatch(expected_state_version=state.state_version, operations=[operation]),
        )
        return AgentResult(
            state=updated,
            patches=[operation],
            next_action=NextAction.ASK_HOMEOWNER,
        )


def _image_source(attribute: Attribute) -> str | None:
    return next(
        (
            evidence.source_id
            for evidence in attribute.evidence
            if evidence.source_type == EvidenceSource.IMAGE
        ),
        None,
    )
