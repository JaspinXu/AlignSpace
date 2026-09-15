from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app import knowledge, interview


DIMENSIONS = (
    "style",
    "colour",
    "material",
    "lighting",
    "layout",
    "mood",
    "function",
    "maintenance",
)


QUESTION_BANK: list[dict[str, Any]] = [
    {
        "id": "style_direction",
        "target": "homeowner",
        "dimension": "style",
        "prompt": "Which overall direction feels most like the home you want?",
        "rationale": "Style separates the broadest groups of references.",
        "options": ["warm_modern", "japandi", "contemporary_luxe", "industrial", "scandinavian", "no_fixed_style"],
        "impact": 1.0,
    },
    {
        "id": "room_mood",
        "target": "homeowner",
        "dimension": "mood",
        "prompt": "What should the living room feel like most of the time?",
        "rationale": "Mood helps translate subjective words into design decisions.",
        "options": ["calm", "cosy", "bright", "dramatic", "social"],
        "impact": 0.92,
    },
    {
        "id": "colour_palette",
        "target": "homeowner",
        "dimension": "colour",
        "prompt": "Which colour family should dominate the room?",
        "rationale": "Colour quickly removes visually incompatible directions.",
        "options": ["warm_neutral", "light_neutral", "earthy", "monochrome", "deep_tones"],
        "impact": 0.9,
    },
    {
        "id": "primary_material",
        "target": "homeowner",
        "dimension": "material",
        "prompt": "Which material would you most like to see repeated?",
        "rationale": "A repeated material gives the designer a concrete visual anchor.",
        "options": ["light_oak", "walnut", "stone", "metal", "soft_textiles"],
        "impact": 0.85,
    },
    {
        "id": "lighting_preference",
        "target": "homeowner",
        "dimension": "lighting",
        "prompt": "Which lighting character matters most to you?",
        "rationale": "Lighting strongly changes how colours and materials are perceived.",
        "options": ["soft_layered", "natural_bright", "warm_ambient", "statement", "task_focused"],
        "impact": 0.82,
    },
    {
        "id": "main_function",
        "target": "homeowner",
        "dimension": "function",
        "prompt": "What is the living room's most important everyday job?",
        "rationale": "The main activity determines priorities before styling details.",
        "options": ["family_relaxing", "hosting", "tv_and_media", "flexible_use", "quiet_retreat"],
        "impact": 0.97,
    },
    {
        "id": "layout_strategy",
        "target": "designer",
        "dimension": "layout",
        "prompt": "Which layout strategy is most feasible for this project?",
        "rationale": "The designer validates that the preferred direction fits the space.",
        "options": ["open_flow", "zoned", "compact", "conversation_focused", "storage_led"],
        "impact": 0.95,
    },
    {
        "id": "maintenance_level",
        "target": "designer",
        "dimension": "maintenance",
        "prompt": "Which maintenance profile should guide material selection?",
        "rationale": "This turns lifestyle expectations into a practical design constraint.",
        "options": ["easy_care", "balanced", "premium_care"],
        "impact": 0.75,
    },
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def create_project(name: str, housing_type: str | None = None) -> dict[str, Any]:
    project_id = new_id("project")
    state = {
        "schemaVersion": "1.1.0",
        "id": project_id,
        "name": name.strip(),
        "roomType": "living_room",
        "housingType": housing_type.strip() if housing_type else None,
        "status": "homeowner_review",
        "stateVersion": 1,
        "briefVersion": 1,
        "questionCount": 0,
        "maxQuestions": 10,
        "goals": [],
        "antiPreferences": [],
        "attributes": [],
        "constraints": [],
        "conflicts": [],
        "answers": [],
        "references": [],
        "agentMessages": [],
        "approvals": [],
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }
    add_agent_message(
        state,
        "alignment_agent",
        "homeowner",
        "I will ask the smallest number of high-value questions needed to turn inspiration into a shared brief.",
        "orientation",
    )
    return recompute(state)


def add_agent_message(state: dict[str, Any], sender: str, recipient: str, text: str, kind: str) -> None:
    state["agentMessages"].append(
        {
            "id": new_id("message"),
            "sender": sender,
            "recipient": recipient,
            "text": text,
            "kind": kind,
            "createdAt": now_iso(),
        }
    )
    state["agentMessages"] = state["agentMessages"][-30:]


def migrate_project(previous: dict[str, Any]) -> dict[str, Any]:
    """Project only supported fields into the alignment schema; re-approve changes."""
    template = create_project(previous['name'], previous.get('housingType'))
    state = {key: deepcopy(previous.get(key, default)) for key, default in template.items()}
    state['schemaVersion'] = '1.1.0'
    categories = {'space', 'function', 'maintenance', 'timeline', 'safety', 'regulatory', 'availability', 'other'}
    removed_statements = [c.get('statement', '') for c in state['constraints'] if c.get('category') not in categories]
    state['constraints'] = [c for c in state['constraints'] if c.get('category') in categories]
    ids = {c['id'] for c in state['constraints']}
    state['conflicts'] = [c for c in state['conflicts'] if not c.get('constraintId') or c['constraintId'] in ids]
    for ref in state['references']:
        if 'sourceDetails' in ref:
            ref['sourceDetails'] = {k: v for k, v in ref['sourceDetails'].items()
                if k in {'flatType', 'area', 'year', 'designer', 'style', 'features', 'imageUrl'}}
        if ref.get('status') == 'catalogue_link':
            ref['note'] = 'Saved for discussion. Choose which details you like; saving does not confirm preferences.'
    state['agentMessages'] = [m for m in state['agentMessages']
                              if not any(text and text in m.get('text', '') for text in removed_statements)]
    add_agent_message(state, 'alignment_agent', 'homeowner_and_designer',
                      'Your project now uses the updated alignment brief. Review it together and approve this version.', 'schema_update')
    return bump_and_recompute(state)


def _confirmed_map(state: dict[str, Any]) -> dict[str, str]:
    return {
        item["dimension"]: item["value"]
        for item in state["attributes"]
        if item["status"] == "confirmed"
    }


def _ranked_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    return knowledge.directions(state)


def _entropy(values: list[str]) -> float:
    if not values:
        return 0.0
    total = len(values)
    return -sum((count / total) * math.log2(count / total) for count in Counter(values).values())


def next_question(state: dict[str, Any], role: str | None = None) -> dict[str, Any] | None:
    if state["questionCount"] >= state["maxQuestions"] or (role and state.get("interviewPaused", {}).get(role)):
        return None
    # The confirmed map is fixed for this call; rebuilding it per candidate made
    # question selection quadratic in the size of the question bank.
    confirmed = _confirmed_map(state)
    answers = state["answers"]
    answered = {a["questionId"] for a in answers if not a.get("detail") or a.get("basis") == confirmed.get(a["dimension"])}
    scored: list[tuple[float, float, dict[str, Any]]] = []
    open_conflict_dimensions = {
        conflict.get("dimension")
        for conflict in state["conflicts"]
        if conflict["status"] == "open" and conflict.get("dimension")
    }
    for question in [*QUESTION_BANK, *interview.DETAIL_QUESTIONS]:
        detail = question.get("detail")
        if detail and not interview.eligible(question, confirmed, answers):
            continue
        if role and question['target'] != role:
            continue
        dimension = question["dimension"]
        if question["id"] in answered or (not detail and dimension in confirmed):
            continue
        information_gain = _entropy(question["options"])
        conflict_bonus = 0.7 if dimension in open_conflict_dimensions else 0
        coverage_bonus = 0.25 if dimension not in confirmed else 0
        score = information_gain * question["impact"] + conflict_bonus + coverage_bonus
        if not detail:
            score += 5  # Resolve missing shared vocabulary before optional details.
        elif question.get("after"):
            score += 2
        elif "*" not in question["requires"]:
            score += 1  # A conditional follow-up narrows an actual prior choice.
        scored.append((score, information_gain, question))
    if not scored:
        return None
    score, information_gain, selected = max(scored, key=lambda item: (item[0], item[2]["impact"]))
    return {
        **deepcopy(selected),
        "options": selected["options"] + ["not_sure"],
        "informationGain": round(information_gain, 3),
        "selectionScore": round(score, 3),
        "sequence": state["questionCount"] + 1,
        "selectionMethod": "option-entropy heuristic; not measured information gain",
    }


def answer_question(state: dict[str, Any], question_id: str, role: str, value: str, *, revision: bool = False) -> dict[str, Any]:
    if not revision and (state['questionCount'] >= state['maxQuestions'] or state.get("interviewPaused", {}).get(role)):
        raise ValueError('Question limit reached; edit the brief to complete remaining decisions')
    question = next((item for item in [*QUESTION_BANK, *interview.DETAIL_QUESTIONS] if item["id"] == question_id), None)
    if not question:
        raise ValueError("Unknown question")
    if question["target"] != role:
        raise ValueError(f"This question must be answered by the {question['target']}")
    if question.get("detail") and not (revision and value == "not_sure") and not interview.eligible(question, _confirmed_map(state), state["answers"]):
        raise ValueError("This follow-up does not apply to the current preferences")
    if question.get("detail"):
        state["answers"] = [a for a in state["answers"] if not (a["questionId"] == question_id and a.get("basis") != _confirmed_map(state).get(a["dimension"]))]
    if any(item["questionId"] == question_id for item in state["answers"]):
        raise ValueError("Question has already been answered")
    if value not in [*question["options"], "not_sure"]:
        raise ValueError("Answer is not one of the allowed options")
    if value != 'not_sure' and not question.get('detail'):
        validate_preference(state, question['dimension'], value)

    answer_id = new_id("answer")
    state["answers"].append(
        {
            "id": answer_id,
            "questionId": question_id,
            **({"detail": True, "prompt": question["prompt"], "promptZh": question["promptZh"], "valueZh": question["optionsZh"].get(value, "暂不确定"), "basis": _confirmed_map(state).get(question["dimension"])} if question.get("detail") else {}),
            "target": role,
            "dimension": question["dimension"],
            "value": value,
            "createdAt": now_iso(),
        }
    )
    state["questionCount"] += 1
    if value != "not_sure" and not question.get("detail"):
        state["attributes"] = [
            item for item in state["attributes"]
        ]
        for item in state['attributes']:
            if item['dimension'] == question['dimension'] and item['status'] == 'confirmed':
                item['status'] = 'rejected'
        state["attributes"].append(
            {
                "id": new_id("attribute"),
                "dimension": question["dimension"],
                "value": value,
                "status": "confirmed",
                "confidence": 1.0,
                "evidence": [
                    {
                        "sourceType": f"{role}_answer" if role == "homeowner" else "designer_note",
                        "sourceId": answer_id,
                        "description": f"Confirmed by the {role} in the adaptive interview.",
                    }
                ],
                "actor": role,
                "updatedAt": now_iso(),
            }
        )

    source_agent = f"{role}_agent"
    other_role = "designer" if role == "homeowner" else "homeowner"
    other_agent = f"{other_role}_agent"
    readable = value.replace("_", " ")
    add_agent_message(state, source_agent, other_agent, f"{'Skipped' if value == 'not_sure' else 'Detail recorded' if question.get('detail') else 'Confirmed'} {question['dimension']}: {readable}.", "qa_answer")
    add_agent_message(
        state,
        other_agent,
        role,
        ('No preference was confirmed. You can revisit this decision in the shared brief.' if value == 'not_sure' else 'This optional detail is saved alongside the core decisions in the shared brief.' if question.get('detail') else f"I translated that into a shared {question['dimension']} requirement and will cross-check it against the other side's constraints."),
        "cross_check",
    )
    return bump_and_recompute(state)


def add_preferences(state: dict[str, Any], goals: list[str], anti_preferences: list[str]) -> dict[str, Any]:
    state["goals"] = list(dict.fromkeys(item.strip() for item in goals if item.strip()))
    state["antiPreferences"] = list(
        dict.fromkeys(item.strip() for item in anti_preferences if item.strip())
    )
    add_agent_message(
        state,
        "homeowner_agent",
        "designer_agent",
        "The homeowner's goals and anti-preferences have been structured for review.",
        "translation",
    )
    return bump_and_recompute(state)


def add_reference(state: dict[str, Any], reference: dict[str, Any]) -> dict[str, Any]:
    state["references"].append(reference)
    add_agent_message(
        state,
        "homeowner_agent",
        "designer_agent",
        f"A new inspiration reference was added: {reference.get('note') or reference['filename']}.",
        "reference",
    )
    return bump_and_recompute(state)


REFERENCE_KEYWORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "style": {
        "warm_modern": ("warm modern", "modern warm"),
        "japandi": ("japandi", "zen"),
        "contemporary_luxe": ("luxury", "luxe", "hotel"),
        "industrial": ("industrial", "loft"),
        "scandinavian": ("scandinavian", "nordic"),
    },
    "colour": {
        "warm_neutral": ("warm neutral", "beige", "cream"),
        "light_neutral": ("light neutral", "white", "pale"),
        "earthy": ("earthy", "terracotta", "olive"),
        "monochrome": ("monochrome", "black and white", "grey"),
        "deep_tones": ("deep tone", "navy", "dark"),
    },
    "material": {
        "light_oak": ("light oak", "pale wood"),
        "walnut": ("walnut", "dark wood"),
        "stone": ("stone", "marble", "travertine"),
        "metal": ("metal", "steel"),
        "soft_textiles": ("textile", "fabric", "soft sofa"),
    },
    "lighting": {
        "soft_layered": ("layered light", "soft light"),
        "natural_bright": ("natural light", "daylight", "bright"),
        "warm_ambient": ("warm light", "ambient"),
        "statement": ("statement light", "chandelier", "pendant"),
        "task_focused": ("task light", "reading light"),
    },
}


_ZH_ALIASES = {
    'warm_modern': ('暖色现代', '温暖现代'), 'japandi': ('日式北欧', '日系', '日式'),
    'contemporary_luxe': ('轻奢', '豪华'), 'industrial': ('工业风',), 'scandinavian': ('北欧',),
    'warm_neutral': ('暖中性', '奶油色'), 'light_neutral': ('浅中性', '浅色'), 'earthy': ('大地色',),
    'monochrome': ('黑白', '单色'), 'deep_tones': ('深色',), 'light_oak': ('浅橡木', '浅色橡木'),
    'walnut': ('胡桃木',), 'stone': ('石材', '大理石'), 'metal': ('金属',), 'soft_textiles': ('布艺', '织物'),
    'soft_layered': ('柔和灯光', '分层灯光'), 'natural_bright': ('自然光', '采光'),
    'warm_ambient': ('暖光', '氛围灯'), 'statement': ('吊灯', '造型灯'), 'task_focused': ('阅读灯', '工作灯')}
for _values in REFERENCE_KEYWORDS.values():
    for _value in _values:
        _values[_value] += _ZH_ALIASES.get(_value, ())


def _candidate_exclusions(state: dict[str, Any], candidate: dict[str, Any]) -> list[str]:
    excluded = []
    for dimension in DIMENSIONS:
        value = candidate.get(dimension, '')
        keywords = (value.replace('_', ' '), *REFERENCE_KEYWORDS.get(dimension, {}).get(value, ()))
        if any(re.search((re.escape(k) if re.search(r'[\u4e00-\u9fff]', k) else r'(?<!\w)' + re.escape(k) + r'(?!\w)'), text.lower())
               for text in state['antiPreferences'] for k in keywords if k):
            excluded.append(dimension)
    return excluded


def validate_preference(state: dict[str, Any], dimension: str, value: str) -> None:
    question = next((q for q in QUESTION_BANK if q['dimension'] == dimension), None)
    if not question or value not in question['options']:
        raise ValueError(f'Unsupported {dimension} value')
    if _candidate_exclusions(state, {dimension: value}):
        raise ValueError(f'{dimension}: {value} conflicts with a stated must-avoid preference')
    if any(c.get('affectedDimension') == dimension and c.get('incompatibleValue') == value and not c.get('waived') for c in state['constraints']):
        raise ValueError(f'{dimension}: {value} conflicts with an active designer constraint')


def apply_model_proposals(state: dict[str, Any], proposals: list[dict[str, Any]]) -> dict[str, Any]:
    existing = {(a['dimension'], a['value'], a['evidence'][0]['sourceId']) for a in state['attributes'] if a['evidence']}
    for proposal in proposals:
        key = (proposal['dimension'], proposal['value'], proposal['sourceId'])
        if key in existing:
            continue
        existing.add(key)
        state['attributes'].append({'id': new_id('attribute'), 'dimension': proposal['dimension'],
            'value': proposal['value'], 'status': 'proposed', 'confidence': proposal['confidence'],
            'evidence': [{'sourceType': proposal['sourceType'], 'sourceId': proposal['sourceId'],
                          'description': proposal['description']}], 'actor': 'vision_agent', 'updatedAt': now_iso()})
    add_agent_message(state, 'vision_agent', 'homeowner',
        'Model observations are suggestions, not confirmed preferences. Confirm only the elements you want in your room.', 'analysis')
    return bump_and_recompute(state)


def analyse_references(state: dict[str, Any]) -> dict[str, Any]:
    if not state["references"]:
        raise ValueError("Upload at least one reference before running analysis")
    existing = {
        (item["dimension"], item["value"], item["evidence"][0]["sourceId"])
        for item in state["attributes"]
        if item["evidence"]
    }
    proposals = 0
    for reference in state["references"]:
        evidence_text = reference.get('note', '').lower()
        # Offline fallback is conservative: ambiguous/negative clauses never become likes.
        positive_clauses = [part for part in re.split(r'[.!?;。！？；]|\bbut\b|但是|不过|但', evidence_text)
                            if not re.search(r"\b(no|not|never|avoid|dislike|without|unsure|uncertain)\b|n't|不|讨厌|避免|别用|拒绝|不要|没想好", part)]
        for dimension, values in REFERENCE_KEYWORDS.items():
            for value, keywords in values.items():
                if not any(keyword in part for keyword in keywords for part in positive_clauses):
                    continue
                if (dimension, value, reference["id"]) in existing:
                    continue
                state["attributes"].append(
                    {
                        "id": new_id("attribute"),
                        "dimension": dimension,
                        "value": value,
                        "status": "proposed",
                        "confidence": 0.0,
                        "evidence": [
                            {
                                "sourceType": "homeowner_answer",
                                "sourceId": reference["id"],
                                "description": f"Proposed from the homeowner's reference note: {reference.get('note') or reference['filename']}",
                            }
                        ],
                        "actor": "vision_agent",
                        "updatedAt": now_iso(),
                    }
                )
                proposals += 1
    if proposals:
        message = f"Offline note rules proposed {proposals} attributes; image pixels were not analysed. Confidence is uncalibrated (0). Confirm or reject each proposal."
    else:
        message = "The references do not contain enough explicit evidence for a safe proposal, so I will clarify with questions instead."
    add_agent_message(state, "vision_agent", "homeowner", message, "analysis")
    return bump_and_recompute(state)


def review_attribute(
    state: dict[str, Any], attribute_id: str, decision: str, value: str | None = None
) -> dict[str, Any]:
    attribute = next((item for item in state["attributes"] if item["id"] == attribute_id), None)
    if not attribute:
        raise ValueError("Attribute not found")
    if attribute["status"] != "proposed":
        raise ValueError("Only proposed attributes can be reviewed")
    if decision not in {"confirm", "reject", "edit"}:
        raise ValueError("Decision must be confirm, reject, or edit")
    if decision in {'confirm', 'edit'}:
        next_value = value.strip() if decision == 'edit' and value else attribute['value']
        validate_preference(state, attribute['dimension'], next_value)
        for previous in state['attributes']:
            if previous['id'] != attribute_id and previous['dimension'] == attribute['dimension'] and previous['status'] == 'confirmed':
                previous['status'] = 'rejected'
    if decision == "edit":
        if not value or not value.strip():
            raise ValueError("An edited value is required")
        attribute["value"] = value.strip()
        attribute["status"] = "confirmed"
    elif decision == "confirm":
        attribute["status"] = "confirmed"
        attribute["confidence"] = 1.0
    else:
        attribute["status"] = "rejected"
    attribute["actor"] = "homeowner"
    attribute["updatedAt"] = now_iso()
    add_agent_message(
        state,
        "homeowner_agent",
        "designer_agent",
        f"The homeowner {decision}ed the proposed {attribute['dimension']}: {attribute['value'].replace('_', ' ')}.",
        "evidence_review",
    )
    return bump_and_recompute(state)


def add_constraint(state: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    constraint = {
        "id": new_id("constraint"),
        "category": data["category"],
        "statement": data["statement"].strip(),
        "rationale": data.get("rationale", "").strip(),
        "severity": data["severity"],
        "verificationStatus": "professional_review_required" if data["severity"] == "critical" else "designer_asserted",
        "owner": "designer",
        "affectedDimension": data.get("affectedDimension"),
        "incompatibleValue": data.get("incompatibleValue"),
        "createdAt": now_iso(),
    }
    state["constraints"].append(constraint)
    dimension = constraint.get("affectedDimension")
    incompatible = constraint.get("incompatibleValue")
    confirmed = _confirmed_map(state)
    if dimension and incompatible and confirmed.get(dimension) == incompatible:
        state["conflicts"].append(
            {
                "id": new_id("conflict"),
                "type": "preference_vs_constraint",
                "dimension": dimension,
                "constraintId": constraint['id'],
                "summary": f"The confirmed {dimension} preference conflicts with a designer constraint.",
                "homeownerPosition": incompatible,
                "designerPosition": constraint["statement"],
                "impact": constraint["rationale"] or "The design direction may need to change.",
                "status": "open",
                "resolution": None,
                "createdAt": now_iso(),
            }
        )
    add_agent_message(
        state,
        "designer_agent",
        "homeowner_agent",
        f"Designer constraint: {constraint['statement']}",
        "qa_question" if dimension else "constraint",
    )
    return bump_and_recompute(state)


def resolve_conflict(state: dict[str, Any], conflict_id: str, resolution: str) -> dict[str, Any]:
    conflict = next((item for item in state["conflicts"] if item["id"] == conflict_id), None)
    if not conflict:
        raise ValueError("Conflict not found")
    if resolution not in {'accept_designer_constraint', 'retain_preference_after_discussion', 'discuss_offline'}:
        raise ValueError('Unknown resolution')
    if resolution == 'accept_designer_constraint':
        for attribute in state['attributes']:
            if attribute['dimension'] == conflict.get('dimension') and attribute['value'] == conflict.get('homeownerPosition'):
                attribute['status'] = 'rejected'
    elif resolution == 'retain_preference_after_discussion':
        for constraint in state['constraints']:
            if constraint['id'] == conflict.get('constraintId'):
                if constraint['severity'] == 'critical':
                    raise ValueError('Critical constraints require professional review')
                constraint['waived'] = True
                constraint['rationale'] += ' | Withdrawn by agreement; preference retained.'
    conflict["status"] = "resolved" if resolution != "discuss_offline" else "escalated"
    conflict["resolution"] = resolution.strip()
    add_agent_message(
        state,
        "alignment_agent",
        "homeowner_and_designer",
        f"Conflict resolved: {resolution.replace('_', ' ')}.",
        "resolution",
    )
    return bump_and_recompute(state)


def _readiness(state: dict[str, Any]) -> dict[str, Any]:
    confirmed = _confirmed_map(state)
    coverage = len(set(confirmed) & set(DIMENSIONS)) / len(DIMENSIONS)
    concentration = 0  # Legacy field; a reference corpus is not a population of possible rooms.
    open_conflicts = [item for item in state["conflicts"] if item["status"] in {'open', 'escalated'}]
    agreement = 1.0 if not open_conflicts else max(0.0, 1 - len(open_conflicts) * 0.35)
    critical = [item for item in state["constraints"] if item["severity"] == "critical"]
    risk_clearance = 0.0 if critical else 1.0
    score = coverage  # Progress is decision coverage, not a design-quality estimate.
    if coverage < 0.35:
        stage = "Explore"
    elif open_conflicts:
        stage = "Clarify"
    elif coverage < 0.85:
        stage = "Focus"
    else:
        stage = "Commit"
    blockers = []
    for dimension in DIMENSIONS:
        values = [a['value'] for a in state['attributes'] if a['dimension'] == dimension and a['status'] == 'confirmed']
        if len(values) > 1:
            blockers.append(f'Reconcile multiple confirmed {dimension} values')
        for value in values:
            try:
                validate_preference(state, dimension, value)
            except ValueError as error:
                blockers.append(str(error))
    return {
        "score": round(score, 3),
        "coverage": round(coverage, 3),
        "candidateConcentration": round(concentration, 3),
        "agreement": round(agreement, 3),
        "riskClearance": round(risk_clearance, 3),
        "stage": stage,
        "readyForApproval": coverage == 1 and not open_conflicts and not critical and not blockers,
        "blockers": blockers,
        "missingDimensions": [dimension for dimension in DIMENSIONS if dimension not in confirmed],
        "scoreMeaning": "confirmed decision coverage",
    }


def recompute(state: dict[str, Any], *, refresh_knowledge: bool = True) -> dict[str, Any]:
    readiness = _readiness(state)
    state["readiness"] = readiness
    if refresh_knowledge:
        state["shortlist"] = _ranked_candidates(state)[:3]
        state["terminology"] = knowledge.terminology_for(state)
    if state.get("status") != "approved":
        if readiness["readyForApproval"]:
            state["status"] = "awaiting_approval"
        elif state["constraints"]:
            state["status"] = "alignment"
        else:
            state["status"] = "homeowner_review"
    state["updatedAt"] = now_iso()
    return state


def bump_and_recompute(state: dict[str, Any]) -> dict[str, Any]:
    state["stateVersion"] += 1
    state["briefVersion"] += 1
    state["approvals"] = []
    state['status'] = 'homeowner_review'
    return recompute(state)


def build_brief(state: dict[str, Any]) -> dict[str, Any]:
    conflicts = [
        {
            "id": item["id"],
            "type": item["type"],
            "summary": item["summary"],
            "impact": item["impact"],
            "status": item["status"],
            "resolution": item.get("resolution"),
        }
        for item in state["conflicts"]
    ]
    attributes = []
    for item in state["attributes"]:
        attributes.append(
            {
                key: value
                for key, value in item.items()
                if key in {"id", "dimension", "value", "status", "confidence", "evidence", "actor", "updatedAt"}
            }
        )
    constraints = []
    for item in state["constraints"]:
        constraints.append(
            {
                key: value
                for key, value in item.items()
                if key in {"id", "category", "statement", "rationale", "severity", "verificationStatus", "owner", "waived"}
            }
        )
    brief = {
        "schemaVersion": "1.1.0",
        "project": {
            "id": state["id"],
            "roomType": state["roomType"],
            "housingType": state["housingType"],
            "status": state["status"],
        },
        "goals": state["goals"],
        "antiPreferences": state["antiPreferences"],
        "attributes": attributes,
        "constraints": constraints,
        **({"designDetails": interview.active_details(state)} if any(a.get("detail") for a in state["answers"]) else {}),
        "conflicts": conflicts,
        "unresolvedDecisions": [item["summary"] for item in state["conflicts"] if item["status"] in {'open', 'escalated'}] + [f"Choose {d}" for d in state['readiness']['missingDimensions']] + state['readiness'].get('blockers', []),
        **({"knowledgeReferences": [r for r in state.get("shortlist", []) if r.get("kind") == "knowledge_reference"],
            "terminology": state["terminology"]} if "terminology" in state else {}),
        "completeness": state["readiness"]["coverage"],
        "version": state["briefVersion"],
        "approvals": state["approvals"],
    }
    hashable = deepcopy(brief)
    hashable["approvals"] = []
    hashable["project"]["status"] = "content"
    payload = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
    brief["contentHash"] = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return brief


def approve(state: dict[str, Any], role: str, actor_id: str) -> dict[str, Any]:
    if not state["readiness"]["readyForApproval"]:
        raise ValueError("The brief is not ready: complete the interview and resolve blocking issues")
    brief = build_brief(state)
    approval = {
        "role": role,
        "actorId": actor_id.strip(),
        "briefVersion": state["briefVersion"],
        "contentHash": brief["contentHash"],
        "approvedAt": now_iso(),
    }
    state["approvals"] = [item for item in state["approvals"]
                          if item["role"] != role and item['contentHash'] == brief['contentHash']]
    state["approvals"].append(approval)
    roles = {item["role"] for item in state["approvals"]}
    if roles == {"homeowner", "designer"}:
        state["status"] = "approved"
    else:
        state["status"] = "awaiting_approval"
    state["stateVersion"] += 1
    state["updatedAt"] = now_iso()
    return recompute(state, refresh_knowledge=False)


def demo_answers() -> list[tuple[str, str, str]]:
    return [
        ("main_function", "homeowner", "family_relaxing"),
        ("style_direction", "homeowner", "warm_modern"),
        ("room_mood", "homeowner", "cosy"),
        ("colour_palette", "homeowner", "warm_neutral"),
        ("primary_material", "homeowner", "soft_textiles"),
        ("lighting_preference", "homeowner", "soft_layered"),
        ("layout_strategy", "designer", "zoned"),
        ("maintenance_level", "designer", "balanced"),
    ]


def set_interview(state, role, action):
    if action not in {"continue", "pause"}:
        raise ValueError("Unknown interview action")
    if action == "continue":
        if state['questionCount'] >= state['maxQuestions']:
            state['maxQuestions'] = state['questionCount'] + 10
        elif not state.get('interviewPaused', {}).get(role):
            raise ValueError("Finish this round before starting another")
    state.setdefault('interviewPaused', {})[role] = action == "pause"
    # Workflow consent does not change the signed design content.
    state['stateVersion'] += 1
    state['updatedAt'] = now_iso()
    return state
