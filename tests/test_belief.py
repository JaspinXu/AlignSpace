"""Belief and next-action policy: advisory only, hard constraints first, no false certainty."""
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from app import belief, engine


def with_reference(state, ref_id="r1", note="reference"):
    return engine.add_reference(state, {"id": ref_id, "filename": ref_id, "note": note})


def propose(state, dimension, value, source="r1", confidence=0.8):
    return engine.apply_model_proposals(state, [{"dimension": dimension, "value": value, "sourceId": source,
                                                  "sourceType": "homeowner_answer", "confidence": confidence,
                                                  "description": "test"}])


def test_no_evidence_keeps_the_original_question_order():
    state = engine.create_project("Order")
    assert engine.next_question(state)["id"] == "style_direction"
    assert state["belief"]["dimensions"]["colour"]["status"] == "uncertain"
    assert state["nextActions"]["homeowner"]["action"] == "ask"


def test_belief_never_confirms_and_is_not_signed():
    state = with_reference(engine.create_project("Advisory"))
    state = propose(state, "material", "light_oak")
    assert state["belief"]["dimensions"]["material"]["status"] == "leaning"
    assert not any(a["status"] == "confirmed" for a in state["attributes"])
    brief = engine.build_brief(state)
    assert "belief" not in brief and "nextActions" not in brief
    schema = json.loads(Path("schemas/design-brief.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(brief)


def test_leaning_evidence_suggests_confirmation_not_a_decision():
    state = with_reference(engine.create_project("Confirm"))
    state = propose(state, "material", "light_oak")
    action = state["nextActions"]["homeowner"]
    assert action["action"] == "confirm" and action["value"] == "light_oak"
    assert state["nextActions"]["designer"]["action"] != "confirm"


def test_repeated_evidence_has_diminishing_weight():
    single = propose(with_reference(engine.create_project("One")), "style", "japandi")
    repeated = engine.create_project("Many")
    for index in range(6):
        repeated = with_reference(repeated, f"r{index}")
        repeated = propose(repeated, "style", "japandi", source=f"r{index}")
    one = single["belief"]["dimensions"]["style"]["topProbability"]
    many = repeated["belief"]["dimensions"]["style"]["topProbability"]
    anchor = engine.answer_question(engine.create_project("Anchor"), "style_direction", "homeowner", "japandi")
    assert one < many < anchor["belief"]["dimensions"]["style"]["topProbability"]


def test_one_note_naming_many_values_is_weaker_evidence():
    focused = propose(with_reference(engine.create_project("Focused")), "style", "japandi")
    scattered = with_reference(engine.create_project("Scattered"))
    for value in ("japandi", "industrial", "scandinavian"):
        scattered = propose(scattered, "style", value)
    assert (scattered["belief"]["dimensions"]["style"]["probabilities"]["japandi"]
            < focused["belief"]["dimensions"]["style"]["probabilities"]["japandi"])


def test_hard_constraints_mask_options_before_scoring():
    state = engine.add_preferences(engine.create_project("Avoid"), [], ["No walnut"])
    state = with_reference(state)
    state = propose(state, "material", "walnut")
    material = state["belief"]["dimensions"]["material"]
    assert "walnut" in material["blockedOptions"] and "walnut" not in material["probabilities"]
    assert state["nextActions"]["homeowner"]["action"] != "confirm"


def test_rejected_suggestion_lowers_that_option():
    state = propose(with_reference(engine.create_project("Reject")), "colour", "earthy")
    before = state["belief"]["dimensions"]["colour"]["probabilities"]["earthy"]
    proposal = next(a for a in state["attributes"] if a["status"] == "proposed")
    state = engine.review_attribute(state, proposal["id"], "reject")
    assert state["belief"]["dimensions"]["colour"]["probabilities"]["earthy"] < before


def test_present_only_when_every_gate_passes_and_conflicts_go_to_designer():
    state = engine.create_project("Gates")
    for question_id, role, value in engine.demo_answers():
        state = engine.answer_question(state, question_id, role, value)
    assert state["nextActions"]["homeowner"]["action"] == "present"
    state = engine.add_constraint(state, {"category": "space", "statement": "Zoning blocks the balcony route",
                                          "severity": "important", "affectedDimension": "layout",
                                          "incompatibleValue": "zoned"})
    assert state["nextActions"]["homeowner"]["action"] != "present"
    assert state["nextActions"]["designer"]["action"] == "recommend"
    assert state["belief"]["dimensions"]["layout"]["status"] == "blocked"


def test_decision_log_records_suggestion_and_outcome():
    state = engine.create_project("Log")
    question = state["nextActions"]["homeowner"]
    state = engine.answer_question(state, question["questionId"], "homeowner", "japandi")
    entry = state["decisionLog"][-1]
    assert entry["event"] == "answer" and entry["outcome"] == "confirmed"
    assert entry["followedSuggestion"] is True
    assert entry["uncertaintyAfter"] < entry["uncertaintyBefore"]


def test_population_prior_is_weak_and_only_for_compatible_housing():
    unknown = engine.create_project("Unknown", "Not sure yet")
    hdb = engine.create_project("HDB", "HDB 4-room")
    assert unknown["belief"]["dimensions"]["style"]["populationPriorHomes"] == 0
    style = hdb["belief"]["dimensions"]["style"]
    assert style["populationPriorHomes"] > 0 and style["status"] == "uncertain"
    assert style["topProbability"] < 0.3


def test_quality_is_monotonic_in_its_inputs():
    assert belief.quality(1, .5, 0) > belief.quality(.6, .5, 0) > belief.quality(.2, .5, 0)
    assert belief.quality(.6, .9, 0) > belief.quality(.6, .3, 0)
    assert belief.quality(.6, .5, 0) > belief.quality(.6, .5, 2)


def test_simulation_recovers_hidden_preferences_at_least_as_well_as_vote_counting():
    import importlib.util
    spec = importlib.util.spec_from_file_location("simulate_belief", "scripts/simulate_belief.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.run(150, seed=3)
    assert result["top1_belief"] >= result["top1_vote_count"]
    assert result["leaning_precision"] > result["top1_belief"]  # "leaning" is the more reliable subset


def test_homeowner_is_told_to_invite_the_designer_when_only_designer_decisions_remain():
    state = engine.create_project("Handoff")
    for question_id, role, value in engine.demo_answers():
        if role == "homeowner":
            state = engine.answer_question(state, question_id, role, value)
    while engine.next_question(state, "homeowner"):
        question = engine.next_question(state, "homeowner")
        state = engine.answer_question(state, question["id"], "homeowner", "not_sure")
    state = engine.set_interview(state, "homeowner", "pause")
    engine.recompute(state)
    action = state["nextActions"]["homeowner"]
    assert action["action"] == "defer" and action["waitingFor"] == "designer"
    designer = state["nextActions"]["designer"]
    assert designer["action"] == "defer" and designer["resumeInterview"] is True  # shared round is used up


def test_readiness_blocker_gets_a_recommendation_and_approved_brief_gets_export():
    state = engine.create_project("Blocker")
    for question_id, role, value in engine.demo_answers():
        state = engine.answer_question(state, question_id, role, value)
    duplicate = dict(next(a for a in state["attributes"] if a["dimension"] == "style"), id="attribute_dup", value="japandi")
    state["attributes"].append(duplicate)
    engine.recompute(state)
    assert state["nextActions"]["homeowner"]["action"] == "recommend"
    assert state["nextActions"]["homeowner"]["blocker"] is True
    state["attributes"].remove(duplicate)
    engine.recompute(state)
    state = engine.approve(state, "homeowner", "h")
    state = engine.approve(state, "designer", "d")
    assert state["nextActions"]["homeowner"]["title"] == "Export or print the approved brief"


def test_stale_stored_suggestion_is_recomputed_when_presented():
    from app.main import _present
    state = engine.create_project("Stale")
    state["nextActions"]["homeowner"] = {"action": "defer", "title": "old"}
    assert _present(state)["nextActions"]["homeowner"]["action"] == "ask"
