from __future__ import annotations

import hashlib
import json
import math
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4


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
        "options": ["warm_modern", "japandi", "contemporary_luxe", "industrial", "scandinavian"],
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


CATALOG: list[dict[str, Any]] = [
    {"id": "quiet-oak", "title": "Quiet Oak", "style": "japandi", "mood": "calm", "colour": "light_neutral", "material": "light_oak", "lighting": "natural_bright", "function": "quiet_retreat", "layout": "open_flow", "maintenance": "easy_care", "budget": "15k_to_30k_sgd"},
    {"id": "soft-haven", "title": "Soft Haven", "style": "warm_modern", "mood": "cosy", "colour": "warm_neutral", "material": "soft_textiles", "lighting": "soft_layered", "function": "family_relaxing", "layout": "zoned", "maintenance": "balanced", "budget": "15k_to_30k_sgd"},
    {"id": "gallery-night", "title": "Gallery Night", "style": "contemporary_luxe", "mood": "dramatic", "colour": "deep_tones", "material": "stone", "lighting": "statement", "function": "hosting", "layout": "conversation_focused", "maintenance": "premium_care", "budget": "over_50k_sgd"},
    {"id": "nordic-daylight", "title": "Nordic Daylight", "style": "scandinavian", "mood": "bright", "colour": "light_neutral", "material": "light_oak", "lighting": "natural_bright", "function": "flexible_use", "layout": "open_flow", "maintenance": "easy_care", "budget": "under_15k_sgd"},
    {"id": "urban-frame", "title": "Urban Frame", "style": "industrial", "mood": "social", "colour": "monochrome", "material": "metal", "lighting": "task_focused", "function": "hosting", "layout": "open_flow", "maintenance": "easy_care", "budget": "15k_to_30k_sgd"},
    {"id": "walnut-club", "title": "Walnut Club", "style": "contemporary_luxe", "mood": "cosy", "colour": "deep_tones", "material": "walnut", "lighting": "warm_ambient", "function": "tv_and_media", "layout": "zoned", "maintenance": "premium_care", "budget": "30k_to_50k_sgd"},
    {"id": "family-canvas", "title": "Family Canvas", "style": "warm_modern", "mood": "bright", "colour": "warm_neutral", "material": "light_oak", "lighting": "soft_layered", "function": "family_relaxing", "layout": "storage_led", "maintenance": "easy_care", "budget": "30k_to_50k_sgd"},
    {"id": "compact-calm", "title": "Compact Calm", "style": "japandi", "mood": "calm", "colour": "earthy", "material": "soft_textiles", "lighting": "warm_ambient", "function": "quiet_retreat", "layout": "compact", "maintenance": "balanced", "budget": "under_15k_sgd"},
    {"id": "social-stone", "title": "Social Stone", "style": "warm_modern", "mood": "social", "colour": "earthy", "material": "stone", "lighting": "statement", "function": "hosting", "layout": "conversation_focused", "maintenance": "balanced", "budget": "30k_to_50k_sgd"},
    {"id": "media-loft", "title": "Media Loft", "style": "industrial", "mood": "dramatic", "colour": "monochrome", "material": "metal", "lighting": "soft_layered", "function": "tv_and_media", "layout": "zoned", "maintenance": "easy_care", "budget": "15k_to_30k_sgd"},
    {"id": "flexi-nordic", "title": "Flexi Nordic", "style": "scandinavian", "mood": "social", "colour": "light_neutral", "material": "soft_textiles", "lighting": "natural_bright", "function": "flexible_use", "layout": "compact", "maintenance": "easy_care", "budget": "under_15k_sgd"},
    {"id": "earth-studio", "title": "Earth Studio", "style": "japandi", "mood": "cosy", "colour": "earthy", "material": "walnut", "lighting": "warm_ambient", "function": "family_relaxing", "layout": "storage_led", "maintenance": "balanced", "budget": "30k_to_50k_sgd"},
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


def create_project(name: str, budget_band: str, housing_type: str | None = None) -> dict[str, Any]:
    project_id = new_id("project")
    state = {
        "schemaVersion": "1.0.0",
        "id": project_id,
        "name": name.strip(),
        "roomType": "living_room",
        "housingType": housing_type.strip() if housing_type else None,
        "budgetBand": budget_band,
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


def _confirmed_map(state: dict[str, Any]) -> dict[str, str]:
    return {
        item["dimension"]: item["value"]
        for item in state["attributes"]
        if item["status"] == "confirmed"
    }


def _compatible_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    confirmed = _confirmed_map(state)
    excluded: dict[str, set[str]] = {}
    for constraint in state["constraints"]:
        if constraint.get('waived'):
            continue
        dimension = constraint.get("affectedDimension")
        value = constraint.get("incompatibleValue")
        if dimension and value:
            excluded.setdefault(dimension, set()).add(value)

    compatible = []
    for candidate in CATALOG:
        if any(candidate.get(dimension) != value for dimension, value in confirmed.items()):
            continue
        if any(candidate.get(dimension) in values for dimension, values in excluded.items()):
            continue
        compatible.append(candidate)
    return compatible


def _ranked_candidates(state: dict[str, Any]) -> list[dict[str, Any]]:
    confirmed = _confirmed_map(state)
    compatible = _compatible_candidates(state)
    pool = compatible or [candidate for candidate in CATALOG if not any(
        c.get('affectedDimension') and c.get('incompatibleValue') == candidate.get(c['affectedDimension'])
        for c in state['constraints'] if not c.get('waived')
    )]
    ranked = []
    for candidate in pool:
        matches = sum(candidate.get(key) == value for key, value in confirmed.items())
        score = matches / max(1, len(confirmed))
        ranked.append({**candidate, "matchScore": round(score, 3)})
    return sorted(ranked, key=lambda item: (-item["matchScore"], item["title"]))


def _entropy(values: list[str]) -> float:
    if not values:
        return 0.0
    counts = {value: values.count(value) for value in set(values)}
    total = len(values)
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def next_question(state: dict[str, Any]) -> dict[str, Any] | None:
    if state["questionCount"] >= state["maxQuestions"]:
        return None
    answered = {answer["questionId"] for answer in state["answers"]}
    candidates = _compatible_candidates(state) or CATALOG
    scored: list[tuple[float, dict[str, Any]]] = []
    open_conflict_dimensions = {
        conflict.get("dimension")
        for conflict in state["conflicts"]
        if conflict["status"] == "open" and conflict.get("dimension")
    }
    for question in QUESTION_BANK:
        if question["id"] in answered or question['dimension'] in _confirmed_map(state):
            continue
        values = [candidate[question["dimension"]] for candidate in candidates]
        information_gain = _entropy(values)
        conflict_bonus = 0.7 if question["dimension"] in open_conflict_dimensions else 0
        coverage_bonus = 0.25 if question["dimension"] not in _confirmed_map(state) else 0
        score = information_gain * question["impact"] + conflict_bonus + coverage_bonus
        scored.append((score, question))
    if not scored:
        return None
    score, selected = max(scored, key=lambda pair: (pair[0], pair[1]["impact"]))
    remaining_values = {candidate[selected["dimension"]] for candidate in candidates}
    options = [option for option in selected["options"] if option in remaining_values]
    if len(options) < 2:
        options = selected["options"]
    return {
        **deepcopy(selected),
        "options": options + ["not_sure"],
        "informationGain": round(score, 3),
        "sequence": state["questionCount"] + 1,
        "remainingCandidateCount": len(_compatible_candidates(state)),
    }


def answer_question(state: dict[str, Any], question_id: str, role: str, value: str) -> dict[str, Any]:
    if state['questionCount'] >= state['maxQuestions']:
        raise ValueError('Question budget reached; edit the brief to complete remaining decisions')
    question = next((item for item in QUESTION_BANK if item["id"] == question_id), None)
    if not question:
        raise ValueError("Unknown question")
    if question["target"] != role:
        raise ValueError(f"This question must be answered by the {question['target']}")
    if any(item["questionId"] == question_id for item in state["answers"]):
        raise ValueError("Question has already been answered")
    if value not in [*question["options"], "not_sure"]:
        raise ValueError("Answer is not one of the allowed options")
    if any(c.get('affectedDimension') == question['dimension'] and c.get('incompatibleValue') == value and not c.get('waived') for c in state['constraints']):
        raise ValueError('This value conflicts with an active designer constraint. Choose a compatible value.')

    answer_id = new_id("answer")
    state["answers"].append(
        {
            "id": answer_id,
            "questionId": question_id,
            "target": role,
            "dimension": question["dimension"],
            "value": value,
            "createdAt": now_iso(),
        }
    )
    state["questionCount"] += 1
    if value != "not_sure":
        state["attributes"] = [
            item for item in state["attributes"] if item["dimension"] != question["dimension"]
        ]
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
    add_agent_message(state, source_agent, other_agent, f"Confirmed {question['dimension']}: {readable}.", "qa_answer")
    add_agent_message(
        state,
        other_agent,
        role,
        f"I translated that into a shared {question['dimension']} requirement and will cross-check it against the other side's constraints.",
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
        evidence_text = f"{reference.get('filename', '')} {reference.get('note', '')}".lower()
        for dimension, values in REFERENCE_KEYWORDS.items():
            for value, keywords in values.items():
                if not any(keyword in evidence_text for keyword in keywords):
                    continue
                if (dimension, value, reference["id"]) in existing:
                    continue
                state["attributes"].append(
                    {
                        "id": new_id("attribute"),
                        "dimension": dimension,
                        "value": value,
                        "status": "proposed",
                        "confidence": 0.72,
                        "evidence": [
                            {
                                "sourceType": "image",
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
        message = f"I found {proposals} tentative visual attribute{'s' if proposals != 1 else ''}. The homeowner must confirm or reject each one."
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
    candidates = _compatible_candidates(state)
    concentration = (1 - min(1, max(0, len(candidates) - 1) / max(1, len(CATALOG) - 1))) if candidates else 0
    open_conflicts = [item for item in state["conflicts"] if item["status"] in {'open', 'escalated'}]
    agreement = 1.0 if not open_conflicts else max(0.0, 1 - len(open_conflicts) * 0.35)
    critical = [item for item in state["constraints"] if item["severity"] == "critical"]
    risk_clearance = 0.0 if critical else 1.0
    score = 0.55 * coverage + 0.2 * concentration + 0.2 * agreement + 0.05 * risk_clearance
    if coverage < 0.35:
        stage = "Explore"
    elif open_conflicts:
        stage = "Clarify"
    elif coverage < 0.85:
        stage = "Focus"
    else:
        stage = "Commit"
    return {
        "score": round(score, 3),
        "coverage": round(coverage, 3),
        "candidateConcentration": round(concentration, 3),
        "agreement": round(agreement, 3),
        "riskClearance": round(risk_clearance, 3),
        "stage": stage,
        "readyForApproval": coverage == 1 and not open_conflicts and not critical,
        "missingDimensions": [dimension for dimension in DIMENSIONS if dimension not in confirmed],
        "exactCandidateCount": len(candidates),
    }


def recompute(state: dict[str, Any]) -> dict[str, Any]:
    readiness = _readiness(state)
    state["readiness"] = readiness
    state["shortlist"] = _ranked_candidates(state)[:3]
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
                if key in {"id", "category", "statement", "rationale", "severity", "verificationStatus", "owner"}
            }
        )
    brief = {
        "schemaVersion": "1.0.0",
        "project": {
            "id": state["id"],
            "roomType": state["roomType"],
            "housingType": state["housingType"],
            "budgetBand": state["budgetBand"],
            "status": state["status"],
        },
        "goals": state["goals"],
        "antiPreferences": state["antiPreferences"],
        "attributes": attributes,
        "constraints": constraints,
        "conflicts": conflicts,
        "unresolvedDecisions": [item["summary"] for item in state["conflicts"] if item["status"] in {'open', 'escalated'}] + [f"Choose {d}" for d in state['readiness']['missingDimensions']],
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
    state["approvals"] = [item for item in state["approvals"] if item["role"] != role]
    state["approvals"].append(approval)
    roles = {item["role"] for item in state["approvals"]}
    if roles == {"homeowner", "designer"}:
        state["status"] = "approved"
    state["stateVersion"] += 1
    state["updatedAt"] = now_iso()
    return recompute(state)


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
