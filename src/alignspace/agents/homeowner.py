from alignspace.agents.contracts import AgentResult
from alignspace.agents.question_selector import QuestionCandidate, select_question
from alignspace.domain.enums import AttributeStatus, NextAction, Role
from alignspace.domain.models import ProjectState, Question
from alignspace.domain.patches import StatePatch, UpsertQuestion, apply_patch


class HomeownerInterviewAgent:
    def run(self, state: ProjectState) -> AgentResult:
        homeowner_questions = [
            question for question in state.questions if question.target_role == Role.HOMEOWNER
        ]
        if len(homeowner_questions) >= 10:
            return AgentResult(state=state, next_action=NextAction.STOP_UNRESOLVED)
        pending = next((question for question in homeowner_questions if question.answer is None), None)
        if pending is not None:
            return AgentResult(state=state, next_action=NextAction.ASK_HOMEOWNER)

        history = {question.repetition_fingerprint for question in homeowner_questions}
        if "liked-elements" not in history:
            question = Question(
                id="question-liked-elements",
                target_role=Role.HOMEOWNER,
                text=(
                    "Besides the elements you already mentioned, which other parts of these "
                    "images would you like to carry into your design?"
                ),
                rationale="Discover liked elements before asking detailed attribute questions.",
                repetition_fingerprint="liked-elements",
            )
            return self._append(state, question)

        broad_answer = next(
            (
                question.answer.casefold()
                for question in homeowner_questions
                if question.repetition_fingerprint == "liked-elements" and question.answer
            ),
            "",
        )
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
                ),
            )
        selected_attributes = [
            attribute
            for attribute in state.attributes
            if attribute.status == AttributeStatus.PROPOSED
            and any(
                term.casefold() in broad_answer
                for term in (attribute.target_element, attribute.dimension, attribute.value)
            )
        ]
        candidates = [
            QuestionCandidate(
                id=f"{attribute.target_element}-{attribute.dimension}",
                uncertainty=1 - attribute.confidence,
                impact=0.8,
                conflict_relevance=0.5,
                coverage_gap=0.8,
                effort=0.2,
                fingerprint=f"detail:{attribute.target_element}:{attribute.dimension}",
                text=(
                    f"What specifically do you prefer about the {attribute.dimension} of "
                    f"the {attribute.target_element}?"
                ),
            )
            for attribute in selected_attributes
        ]
        selected = select_question(candidates, history)
        if selected is None:
            return AgentResult(state=state, next_action=NextAction.STOP_UNRESOLVED)
        return self._append(
            state,
            Question(
                id=f"question-{selected.id}",
                target_role=Role.HOMEOWNER,
                text=selected.text,
                rationale="Confirm a selected high-impact visual detail.",
                repetition_fingerprint=selected.fingerprint,
            ),
        )

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
