import json
from pathlib import Path

from jsonschema import Draft202012Validator

from app import engine


def completed_state():
    state = engine.create_project("Test home", "HDB")
    state = engine.add_preferences(state, ["Relax together"], ["Cold surfaces"])
    for question_id, role, value in engine.demo_answers():
        state = engine.answer_question(state, question_id, role, value)
    return state


def test_akinator_selector_returns_a_bounded_high_information_question():
    state = engine.create_project("Test home")
    question = engine.next_question(state)
    assert question is not None
    assert question["target"] in {"homeowner", "designer"}
    assert question["informationGain"] > 0
    assert question["sequence"] == 1
    assert "not_sure" in question["options"]


def test_answers_create_cross_agent_messages_and_ready_brief():
    state = completed_state()
    assert state["readiness"]["readyForApproval"] is True
    assert state["readiness"]["stage"] == "Commit"
    assert len(state["attributes"]) == 8
    assert any(message["kind"] == "qa_answer" for message in state["agentMessages"])
    assert any(message["kind"] == "cross_check" for message in state["agentMessages"])

    brief = engine.build_brief(state)
    schema = json.loads(Path("schemas/design-brief.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(brief)


def test_conflict_requires_human_resolution_before_approval():
    state = completed_state()
    state = engine.add_constraint(
        state,
        {
            "category": "space",
            "statement": "A strongly zoned layout would block the balcony route",
            "rationale": "Maintain a safe circulation path",
            "severity": "important",
            "affectedDimension": "layout",
            "incompatibleValue": "zoned",
        },
    )
    assert state["conflicts"][0]["status"] == "open"
    assert state["readiness"]["readyForApproval"] is False

    state = engine.resolve_conflict(state, state["conflicts"][0]["id"], "accept_designer_constraint")
    assert state["readiness"]["readyForApproval"] is False
    assert 'layout' in state['readiness']['missingDimensions']
    assert not any(a['dimension'] == 'layout' and a['status'] == 'confirmed' for a in state['attributes'])


def test_edit_after_approval_clears_status_and_approvals():
    state = completed_state()
    engine.approve(state, 'homeowner', 'h1')
    engine.approve(state, 'designer', 'd1')
    engine.add_preferences(state, ['Changed goal'], [])
    assert state['status'] != 'approved'
    assert state['approvals'] == []


def test_no_matches_does_not_report_perfect_concentration():
    state = completed_state()
    state['attributes'][0]['value'] = 'unknown'
    engine.recompute(state)
    assert state['readiness']['candidateConcentration'] == 0


def test_two_approvals_use_the_same_content_hash():
    state = completed_state()
    state = engine.approve(state, "homeowner", "homeowner-1")
    first_hash = state["approvals"][0]["contentHash"]
    state = engine.approve(state, "designer", "designer-1")
    assert state["status"] == "approved"
    assert {approval["contentHash"] for approval in state["approvals"]} == {first_hash}


def test_reference_note_analysis_never_auto_confirms():
    state = engine.create_project("Reference test")
    state = engine.add_reference(
        state,
        {
            "id": "reference-1",
            "filename": "room.jpg",
            "note": "I like the Japandi style and light oak",
        },
    )
    state = engine.analyse_references(state)
    assert {(item["dimension"], item["value"]) for item in state["attributes"]} == {
        ("style", "japandi"),
        ("material", "light_oak"),
    }
    assert all(item["status"] == "proposed" for item in state["attributes"])
