"""Advisory Bayesian belief over the eight core decisions, plus a constrained next-action policy.

Adapted from the team's V7 model note ("装修设计贝叶斯动态偏好与方案执行模型"):

* Evidence and belief are separated.  Answers, reviewed suggestions, reference-note
  proposals and saved homes are *evidence* (D_it).  The belief is a Dirichlet posterior
  over each dimension's options (the categorical analogue of the note's Gaussian state).
* Evidence quality q gates how much each item may move the belief (q -> observation
  noise R).  Human confirmation is a high-quality anchor (R_conf << R_0).
* Repeated evidence for the same value has diminishing weight, so one note that repeats
  a word, or many saves of similar homes, cannot manufacture false certainty.
* Must-avoid notes and active designer constraints are hard constraints (G): they mask
  options before anything is scored and are never traded off against reward.
* A weak population prior from attributed public homes of a compatible housing type is
  used only for cold start; it states co-occurrence, not influence between homeowners.
* The policy chooses among safe, explainable assistance actions
  (ask / confirm / show / recommend / present / defer).  Its weights are initial
  hypotheses, NOT learned: there is no intervention log large enough to train a policy
  yet.  Every recommendation and what happened next is logged so one can be trained later.

The belief NEVER confirms a preference and is excluded from the signed brief; only a
human answer or a human review changes the brief (decision D-008).
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

MODEL_VERSION = "belief-0.1 (hand-set priors; uncalibrated)"

# Pseudo-counts.  A human anchor is worth far more than any single machine observation.
BASE_PRIOR = 0.5            # per option: wide prior, z_0 ~ N(mu_pop, Sigma_large)
POPULATION_WEIGHT = 1.0     # total pseudo-count spread by the population prior (lambda_pop)
ANCHOR_WEIGHT = 8.0         # human answer / confirmation (R_conf << R_0)
OBSERVATION_WEIGHT = 2.0    # maximum weight of one machine observation at q = 1
REJECTION_FACTOR = 0.5      # a rejected suggestion halves that option's mass
HALF_LIFE_DAYS = 30.0       # Phi(dt): unconfirmed evidence fades as the project moves on
NOT_SURE_RATE = 0.15        # assumed probability that an asked question is skipped

# Evidence quality q = sigmoid(b0 + b1*explicitness + b3*reliability - b5*dispersion).
QUALITY_BETA = {"bias": -2.0, "explicit": 3.0, "reliable": 1.0, "dispersion": 1.0}
EXPLICITNESS = {"model_note": 0.6, "image": 0.6, "offline_rule": 0.4, "saved_home": 0.2}

# Provisional thresholds (theta).  Tune on a real validation split, never on the test split.
LEANING_PROBABILITY = 0.45
LEANING_MARGIN = 0.20
CONFIDENCE_TEMPERATURE = 0.1

# Reward weights lambda_1..lambda_5 and action costs.  Clicks and dwell time are never rewards.
REWARD = {"uncertainty": 1.0, "execution": 0.8, "confirmation": 0.6, "acceptance": 1.2, "cost": 1.0}
ACTION_COST = {"ask": 0.15, "confirm": 0.05, "show": 0.25, "recommend": 0.10, "present": 0.05, "defer": 0.0}

# Discovery style labels that map unambiguously to AlignSpace style options.
_DISCOVERY_STYLE = {"scandinavian": "scandinavian", "japandi": "japandi",
                    "industrial": "industrial", "modern luxe": "contemporary_luxe"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_days(timestamp: str | None, now: datetime) -> float:
    if not timestamp:
        return 0.0
    try:
        moment = datetime.fromisoformat(timestamp)
    except ValueError:
        return 0.0
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return max(0.0, (now - moment).total_seconds() / 86400)


def _entropy(probabilities: list[float]) -> float:
    return -sum(p * math.log2(p) for p in probabilities if p > 0)


def _normalise(alpha: dict[str, float]) -> dict[str, float]:
    total = sum(alpha.values())
    return {k: (v / total if total else 0.0) for k, v in alpha.items()}


def quality(explicitness: float, reliability: float, dispersion: float) -> float:
    b = QUALITY_BETA
    z = b["bias"] + b["explicit"] * explicitness + b["reliable"] * reliability - b["dispersion"] * dispersion
    return 1 / (1 + math.exp(-z))


def _property_group(housing_type: str | None) -> str | None:
    text = (housing_type or "").lower()
    if "hdb" in text:
        return "HDB"
    if any(word in text for word in ("condo", "executive condominium", "penthouse", "duplex", "loft", "walk-up", "studio")):
        return "Condo"
    if any(word in text for word in ("landed", "terrace", "semi-detached", "bungalow", "cluster", "shophouse", "detached")):
        return "Landed"
    return None


def discovery_styles(label: str | None) -> list[str]:
    text = (label or "").lower()
    return sorted({value for key, value in _DISCOVERY_STYLE.items() if key in text})


@lru_cache(maxsize=1)
def _population_homes() -> tuple[tuple[str, tuple[str, ...]], ...]:
    path = Path(__file__).with_name("static") / "singapore.json"
    try:
        projects = json.loads(path.read_text(encoding="utf-8")).get("projects", [])
    except (OSError, ValueError):
        return ()
    return tuple((p.get("propertyType") or "", tuple(discovery_styles(p.get("style")))) for p in projects)


def population_prior(housing_type: str | None, options: list[str]) -> tuple[dict[str, float], int]:
    """Style frequencies among compatible public homes: a weak cold-start prior, not influence."""
    group = _property_group(housing_type)
    if not group:
        return {}, 0
    homes = [styles for kind, styles in _population_homes() if kind == group]
    counts = {option: 0.0 for option in options}
    for styles in homes:
        for style in styles:
            if style in counts:
                counts[style] += 1 / len(styles)
    total = sum(counts.values())
    if not total:
        return {}, len(homes)
    return {k: POPULATION_WEIGHT * v / total for k, v in counts.items() if v}, len(homes)


def _evidence(state: dict[str, Any], dimension: str, now: datetime) -> tuple[list[dict], list[str]]:
    """Collect (value, weight, kind) observations and rejected values for one dimension."""
    items: list[dict[str, Any]] = []
    rejected: list[str] = []
    per_source: dict[str, set[str]] = {}
    for attribute in state.get("attributes", []):
        if attribute["dimension"] == dimension and attribute["status"] == "proposed" and attribute.get("evidence"):
            per_source.setdefault(attribute["evidence"][0]["sourceId"], set()).add(attribute["value"])
    for attribute in state.get("attributes", []):
        if attribute["dimension"] != dimension:
            continue
        if attribute["status"] == "confirmed":
            items.append({"value": attribute["value"], "weight": ANCHOR_WEIGHT, "kind": "human_anchor", "quality": 1.0})
        elif attribute["status"] == "rejected":
            rejected.append(attribute["value"])
        elif attribute["status"] == "proposed" and attribute.get("evidence"):
            source = attribute["evidence"][0]
            offline = attribute.get("confidence", 0) == 0
            kind = "offline_rule" if offline else ("image" if source.get("sourceType") == "image" else "model_note")
            reliability = 0.5 if offline else float(attribute.get("confidence", 0.5))
            dispersion = len(per_source.get(source["sourceId"], ())) - 1
            q = quality(EXPLICITNESS[kind], reliability, dispersion)
            decay = 0.5 ** (_age_days(attribute.get("updatedAt"), now) / HALF_LIFE_DAYS)
            items.append({"value": attribute["value"], "weight": OBSERVATION_WEIGHT * q * decay, "kind": kind, "quality": q})
    if dimension == "style":
        for reference in state.get("references", []):
            if reference.get("status") != "catalogue_link":
                continue
            styles = discovery_styles((reference.get("sourceDetails") or {}).get("style"))
            for style in styles:
                # A multi-style listing is less specific evidence for any one of its styles.
                q = quality(EXPLICITNESS["saved_home"], 0.5, len(styles) - 1)
                items.append({"value": style, "weight": OBSERVATION_WEIGHT * q, "kind": "saved_home", "quality": q})
    return items, rejected


def dimension_belief(state: dict[str, Any], dimension: str, options: list[str], blocked: set[str],
                     now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    feasible = [option for option in options if option not in blocked]
    prior, population_size = population_prior(state.get("housingType"), options) if dimension == "style" else ({}, 0)
    alpha = {option: BASE_PRIOR + prior.get(option, 0.0) for option in feasible}
    items, rejected = _evidence(state, dimension, now)
    # Diminishing returns for repeated evidence: the k-th observation of a value counts 1/k.
    by_value: dict[str, list[dict]] = {}
    for item in items:
        by_value.setdefault(item["value"], []).append(item)
    evidence_mass = 0.0
    anchored = False
    for value, group in by_value.items():
        if value not in alpha:
            continue  # infeasible under a hard constraint, or free text outside the vocabulary
        group.sort(key=lambda item: -item["weight"])
        for rank, item in enumerate(group, start=1):
            weight = item["weight"] if item["kind"] == "human_anchor" else item["weight"] / rank
            alpha[value] += weight
            evidence_mass += weight
            anchored = anchored or item["kind"] == "human_anchor"
    for value in rejected:
        if value in alpha:
            alpha[value] = max(BASE_PRIOR * 0.2, alpha[value] * REJECTION_FACTOR)
    probabilities = _normalise(alpha)
    ranked = sorted(probabilities.items(), key=lambda kv: (-kv[1], kv[0]))
    top_value, top_p = ranked[0] if ranked else (None, 0.0)
    second_p = ranked[1][1] if len(ranked) > 1 else 0.0
    concentration = sum(alpha.values())
    variance = top_p * (1 - top_p) / (concentration + 1) if concentration else 1.0
    confidence = math.exp(-variance / CONFIDENCE_TEMPERATURE) * (top_p - second_p)
    entropy = _entropy(list(probabilities.values()))
    max_entropy = math.log2(len(probabilities)) if len(probabilities) > 1 else 1.0
    confirmed_blocked = any(item["kind"] == "human_anchor" and item["value"] not in alpha for item in items)
    if not feasible or confirmed_blocked:
        status = "blocked"
    elif anchored:
        status = "confirmed"
    elif top_p >= LEANING_PROBABILITY and top_p - second_p >= LEANING_MARGIN and evidence_mass > 0:
        status = "leaning"
    else:
        status = "uncertain"
    return {
        "dimension": dimension,
        "status": status,
        "top": top_value,
        "topProbability": round(top_p, 3),
        "margin": round(top_p - second_p, 3),
        "confidence": round(confidence, 3),
        "entropy": round(entropy, 3),
        "normalisedEntropy": round(entropy / max_entropy, 3) if max_entropy else 0.0,
        "evidenceWeight": round(evidence_mass, 3),
        "evidenceCount": len([i for i in items if i["value"] in alpha]),
        "probabilities": {k: round(v, 3) for k, v in ranked},
        "blockedOptions": sorted(blocked & set(options)),
        "populationPriorHomes": population_size,
        "_alpha": alpha,
    }


def expected_information_gain(entry: dict[str, Any]) -> float:
    """Expected uncertainty removed (bits) by asking this dimension.

    A human answer settles the decision for the brief, so the posterior entropy after a
    real answer is treated as zero; a skipped question ("not sure") removes nothing.
    """
    if entry["status"] in {"confirmed", "blocked"}:
        return 0.0
    probabilities = list(_normalise(entry["_alpha"]).values())
    return max(0.0, (1 - NOT_SURE_RATE) * _entropy(probabilities))


def compute(state: dict[str, Any], options_by_dimension: dict[str, list[str]],
            blocked_by_dimension: dict[str, set[str]], now: datetime | None = None) -> dict[str, Any]:
    now = now or _now()
    dimensions = {}
    for dimension, options in options_by_dimension.items():
        entry = dimension_belief(state, dimension, options, blocked_by_dimension.get(dimension, set()), now)
        entry["expectedInformationGain"] = round(expected_information_gain(entry), 3)
        dimensions[dimension] = entry
    # A confirmed decision is settled for the brief, so it contributes no open uncertainty.
    total_uncertainty = sum(0.0 if d["status"] == "confirmed" else d["normalisedEntropy"] for d in dimensions.values())
    return {
        "modelVersion": MODEL_VERSION,
        "dimensions": dimensions,
        "uncertainty": round(total_uncertainty / max(1, len(dimensions)), 3),
        "leaning": [d for d, e in dimensions.items() if e["status"] == "leaning"],
        "uncertain": [d for d, e in dimensions.items() if e["status"] == "uncertain"],
        "blocked": [d for d, e in dimensions.items() if e["status"] == "blocked"],
        "note": "Advisory estimate from the evidence so far. It never confirms a preference and is not part of the signed brief.",
    }


def public(belief: dict[str, Any]) -> dict[str, Any]:
    """Strip internal pseudo-counts before storing or returning the belief."""
    return {**belief, "dimensions": {d: {k: v for k, v in e.items() if not k.startswith("_")}
                                      for d, e in belief["dimensions"].items()}}


def _action(kind: str, role: str, title: str, reason: str, *, dimension: str | None = None,
            gain: float = 0.0, execution: float = 0.0, confirmation: float = 0.0,
            acceptance: float = 0.0, **extra: Any) -> dict[str, Any]:
    cost = ACTION_COST[kind]
    reward = (REWARD["uncertainty"] * gain + REWARD["execution"] * execution + REWARD["confirmation"] * confirmation
              + REWARD["acceptance"] * acceptance - REWARD["cost"] * cost)
    return {"action": kind, "role": role, "dimension": dimension, "title": title, "reason": reason,
            "expectedReward": round(reward, 3),
            "components": {"uncertaintyReduction": round(gain, 3), "executionGain": round(execution, 3),
                           "confirmation": round(confirmation, 3), "acceptance": round(acceptance, 3), "cost": cost},
            **extra}


def next_actions(state: dict[str, Any], belief: dict[str, Any], questions: dict[str, dict | None],
                 owners: dict[str, str] | None = None) -> dict[str, Any]:
    """Constrained, explainable policy.  Hard constraints filter first; reward ranks the rest."""
    readiness = state["readiness"]
    dims = belief["dimensions"]
    coverage_gain = 1 / max(1, len(dims))  # confirming one missing dimension raises execution by this much
    open_conflicts = [c for c in state.get("conflicts", []) if c["status"] in {"open", "escalated"}]
    critical = [c for c in state.get("constraints", []) if c["severity"] == "critical"]
    pending = [a for a in state.get("attributes", []) if a["status"] == "proposed"]
    result: dict[str, Any] = {}
    for role in ("homeowner", "designer"):
        candidates: list[dict[str, Any]] = []
        # Present: only when every hard gate is already satisfied.
        if state.get("status") == "approved":
            candidates.append(_action("present", role, "Export or print the approved brief",
                                      "Both participants approved the same version.", acceptance=0.5))
        elif readiness["readyForApproval"]:
            candidates.append(_action("present", role, "Review and approve the shared brief",
                                      "Every decision is confirmed and no blocking issue remains.", acceptance=1.0))
        # Recommend: a readiness blocker (e.g. two confirmed values for one decision) needs a human edit.
        if role == "homeowner":
            for blocker in readiness.get("blockers", []):
                candidates.append(_action("recommend", role, "Resolve a blocking issue in the brief", blocker,
                                          execution=coverage_gain, confirmation=0.5, blocker=True))
        # Recommend: an open conflict or professional review is a blocker the designer must address.
        if role == "designer":
            for conflict in open_conflicts:
                candidates.append(_action("recommend", role, "Propose a resolution for the open conflict",
                                          conflict["summary"], dimension=conflict.get("dimension"),
                                          execution=coverage_gain, confirmation=0.5))
            for constraint in critical:
                candidates.append(_action("recommend", role, "Arrange professional review",
                                          f"Critical constraint: {constraint['statement']}", execution=coverage_gain))
        # Confirm: the evidence already leans one way and a matching suggestion awaits review.
        if role == "homeowner":
            for attribute in pending:
                entry = dims.get(attribute["dimension"])
                if not entry or entry["status"] != "leaning" or entry["top"] != attribute["value"]:
                    continue
                candidates.append(_action(
                    "confirm", role, "Check a likely preference",
                    "Your notes and saved references point the same way. Confirm it only if it is right.",
                    dimension=attribute["dimension"], value=attribute["value"], attributeId=attribute["id"],
                    gain=entry["entropy"], execution=coverage_gain, confirmation=entry["topProbability"]))
        # Ask: the adaptive question for this role, valued by expected entropy reduction.
        question = questions.get(role)
        if question:
            entry = dims.get(question["dimension"]) if not question.get("detail") else None
            gain = entry["expectedInformationGain"] if entry else 0.1
            candidates.append(_action("ask", role, "Answer the next question",
                                      question["prompt"], dimension=question["dimension"], questionId=question["id"],
                                      gain=gain, execution=coverage_gain if entry else 0.0))
        # Show: two options are close and there is already some evidence; a side-by-side comparison helps.
        if role == "homeowner":
            for dimension, entry in dims.items():
                ranked = list(entry["probabilities"].items())
                if entry["status"] != "uncertain" or entry["evidenceCount"] == 0 or len(ranked) < 2:
                    continue
                (first, p1), (second, p2) = ranked[0], ranked[1]
                if p1 - p2 < 0.1 and p1 > 1.5 / len(ranked):
                    candidates.append(_action(
                        "show", role, "Compare two directions side by side",
                        "Your references point to two directions about equally. Look at both and note what you prefer.",
                        dimension=dimension, compare=[first, second], gain=entry["expectedInformationGain"] * 0.5))
        candidates.sort(key=lambda c: (-c["expectedReward"], c["action"]))
        if not candidates or candidates[0]["expectedReward"] <= 0:
            other = "designer" if role == "homeowner" else "homeowner"
            waiting = [d for d in readiness.get("missingDimensions", []) if (owners or {}).get(d) == other]
            own = [d for d in readiness.get("missingDimensions", []) if (owners or {}).get(d) == role]
            if own and not questions.get(role):
                candidates.insert(0, _action("defer", role, "Start another round of questions",
                                             "This question round is complete, but these decisions still need your answer: "
                                             + ", ".join(own) + ".", resumeInterview=True))
            elif waiting:
                # Optional detail questions stay available as alternatives.
                title = "Invite your designer" if role == "homeowner" else "Wait for the homeowner"
                reason = f"The remaining decisions are for the {other}: " + ", ".join(waiting) + "."
                candidates.insert(0, _action("defer", role, title, reason, waitingFor=other))
            elif role == "designer" and readiness.get("blockers"):
                candidates.insert(0, _action("defer", role, "Wait for the homeowner",
                                             "The homeowner needs to resolve: " + "; ".join(readiness["blockers"]),
                                             waitingFor="homeowner"))
            elif candidates:
                pass  # e.g. an optional detail question: still the most useful safe step
            elif role == "homeowner":
                candidates.insert(0, _action("defer", role, "Add a note about what you like",
                                             "There is not enough reliable evidence for a useful suggestion yet."))
            else:
                candidates.insert(0, _action("defer", role, "Wait for more evidence",
                                             "The homeowner has not shared enough yet; there is nothing safe to recommend."))
        result[role] = {**candidates[0], "alternatives": candidates[1:3]}
    result["policy"] = "constrained contextual bandit with hand-set weights; not trained on outcomes"
    return result


def snapshot(state: dict[str, Any]) -> dict[str, Any]:
    belief = state.get("belief") or {}
    return {"uncertainty": belief.get("uncertainty"), "nextActions": deepcopy_actions(state.get("nextActions"))}


def deepcopy_actions(actions: dict[str, Any] | None) -> dict[str, Any]:
    if not actions:
        return {}
    return {role: {k: actions[role].get(k) for k in ("action", "dimension", "value", "questionId")}
            for role in ("homeowner", "designer") if role in actions}


def log_outcome(state: dict[str, Any], before: dict[str, Any], role: str, event: str,
                dimension: str | None, outcome: str, **detail: Any) -> None:
    """Intervention log: what the policy suggested, what the person did, and what changed."""
    suggested = (before.get("nextActions") or {}).get(role, {})
    followed = bool(suggested) and suggested.get("dimension") == dimension and (
        (event == "answer" and suggested.get("action") == "ask" and suggested.get("questionId") == detail.get("questionId"))
        or (event == "review" and suggested.get("action") == "confirm")
        or (event == "resolve" and suggested.get("action") == "recommend")
        or (event == "approve" and suggested.get("action") == "present"))
    after = (state.get("belief") or {}).get("uncertainty")
    entry = {"at": _now().isoformat(), "role": role, "event": event, "dimension": dimension, "outcome": outcome,
             "suggested": suggested or None, "followedSuggestion": followed,
             "uncertaintyBefore": before.get("uncertainty"), "uncertaintyAfter": after,
             "stateVersion": state.get("stateVersion")}
    state.setdefault("decisionLog", []).append(entry)
    state["decisionLog"] = state["decisionLog"][-200:]
