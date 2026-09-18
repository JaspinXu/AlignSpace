"""State-space simulation for the advisory belief (V7 note, section 8).

Generates homeowners with a known hidden preference per dimension, emits noisy evidence
(model note proposals, repeated bursts, saved homes, off-target mentions) and measures
whether the belief recovers the hidden value better than naive vote counting.

This validates method logic and implementation only.  It is NOT evidence of real user
satisfaction or business impact; those need real, homeowner- and time-split records.

    python scripts/simulate_belief.py --homeowners 400 --seed 7
"""
from __future__ import annotations

import argparse
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import belief, engine  # noqa: E402

OPTIONS = {q["dimension"]: q["options"] for q in engine.QUESTION_BANK}


def simulate_homeowner(rng: random.Random) -> tuple[dict, dict[str, str], dict[str, list[str]]]:
    truth = {d: rng.choice(opts) for d, opts in OPTIONS.items()}
    state = engine.create_project("sim", rng.choice(["HDB 4-room", "Condo 2-bedroom", None]))
    attributes, votes = [], {d: [] for d in OPTIONS}
    for index in range(rng.randint(1, 5)):
        source = f"ref{index}"
        for dimension, options in OPTIONS.items():
            if rng.random() > 0.35:
                continue
            accurate = rng.random() < 0.7
            value = truth[dimension] if accurate else rng.choice([o for o in options if o != truth[dimension]])
            confidence = min(1.0, max(0.0, rng.gauss(0.75 if accurate else 0.55, 0.15)))
            # Bursts: the same off-target value repeated several times (e.g. recommendation feed).
            repeats = rng.choice([1, 1, 1, 4]) if not accurate else 1
            for burst in range(repeats):
                attributes.append({"id": f"a{len(attributes)}", "dimension": dimension, "value": value,
                                   "status": "proposed", "confidence": round(confidence, 2),
                                   "evidence": [{"sourceType": "homeowner_answer", "sourceId": f"{source}-{burst}",
                                                 "description": "sim"}], "updatedAt": None})
                votes[dimension].append(value)
    state["attributes"] = attributes
    return state, truth, votes


def run(homeowners: int, seed: int) -> dict[str, float]:
    rng = random.Random(seed)
    hits = Counter()
    brier_belief = brier_votes = 0.0
    leaning_total = leaning_correct = 0
    for _ in range(homeowners):
        state, truth, votes = simulate_homeowner(rng)
        computed = belief.compute(state, OPTIONS, {})
        for dimension, entry in computed["dimensions"].items():
            if not votes[dimension]:
                continue
            hits["n"] += 1
            hits["belief"] += entry["top"] == truth[dimension]
            counted = Counter(votes[dimension])
            vote_top = sorted(counted.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            hits["votes"] += vote_top == truth[dimension]
            probabilities = belief._normalise(entry["_alpha"])
            share = {k: v / len(votes[dimension]) for k, v in counted.items()}
            for option in OPTIONS[dimension]:
                target = 1.0 if option == truth[dimension] else 0.0
                brier_belief += (probabilities.get(option, 0) - target) ** 2
                brier_votes += (share.get(option, 0) - target) ** 2
            if entry["status"] == "leaning":
                leaning_total += 1
                leaning_correct += entry["top"] == truth[dimension]
    n = max(1, hits["n"])
    return {"dimensions_with_evidence": hits["n"], "top1_belief": hits["belief"] / n, "top1_vote_count": hits["votes"] / n,
            "brier_belief": brier_belief / n, "brier_vote_count": brier_votes / n,
            "leaning_rate": leaning_total / n, "leaning_precision": leaning_correct / max(1, leaning_total)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--homeowners", type=int, default=400)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    for key, value in run(args.homeowners, args.seed).items():
        print(f"{key:26s} {value:.3f}" if isinstance(value, float) else f"{key:26s} {value}")
