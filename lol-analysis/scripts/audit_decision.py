#!/usr/bin/env python3
"""Offline ML decision stress on a locked forecast; no fitting or new forecast."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path

from analyst_forecast import audit, derive, digest, instant, replay, series_tree, write


def bounded_weights(weights, values, maximize=False, step=.10):
    """Optimize a linear mixture on sum(w)=1 and |w-w_original|<=step."""
    lower = [max(0., w-step) for w in weights]
    upper = [min(1., w+step) for w in weights]
    result = lower[:]
    remaining = 1-sum(result)
    for i in sorted(range(len(weights)), key=lambda i: values[i], reverse=maximize):
        add = min(remaining, upper[i]-result[i])
        result[i] += add
        remaining -= add
    if abs(remaining) > 1e-10:
        raise ValueError("infeasible weight budget")
    return result


def joint_cases(record, side):
    """Exact extrema on a finite rate-shift grid and bounded weight simplex.

    Each scenario independently chooses a uniform shift of -0.05, 0 or +0.05
    across its nodes. We enumerate each scenario's three alternatives, then
    optimize their nonnegative mixture. This does not bound arbitrary node
    perturbations, missing scenarios or a continuous probability interval.
    """
    alternatives, skipped = [], []
    for s in record["scenarios"]:
        options = []
        for delta in (-.05, 0., .05):
            nodes = {k: round(p+delta, 15) for k, p in s["nodes"].items()}
            if any(not 0 < p < 1 for p in nodes.values()):
                skipped.append({"scenario_id": s["id"], "delta": delta})
                continue
            scores = series_tree(record["best_of"], nodes)
            options.append(dict(delta=delta, nodes=nodes, score_distribution=scores,
                                probability=derive(scores)["winner_probabilities"][side]))
        alternatives.append(options)
    cases = {}
    for name, maximize in (("minimum", False), ("maximum", True)):
        chosen = [(max if maximize else min)(opts, key=lambda x: x["probability"])
                  for opts in alternatives]
        weights = bounded_weights([s["weight"] for s in record["scenarios"]],
                                  [o["probability"] for o in chosen], maximize)
        scores = {k: sum(w*o["score_distribution"][k] for w, o in zip(weights, chosen))
                  for k in record["score_distribution"]}
        cases[name] = dict(probability=derive(scores)["winner_probabilities"][side],
            score_distribution=scores, parameters=[dict(id=s["id"], weight=w,
                rate_shift=o["delta"], nodes=o["nodes"]) for s, w, o in
                zip(record["scenarios"], weights, chosen)])
    return cases, skipped


def audit_decision(record, quote):
    replay(record)
    required = {"forecast_id", "event_id", "market", "participants", "decimal_odds",
                "retrieved_at", "source_url", "book"}
    optional = {"entry_floor"}
    if not isinstance(quote, dict) or not required <= quote.keys() or quote.keys()-required-optional:
        raise ValueError("quote requires explicit ordered series ML mapping and provenance")
    if (quote["forecast_id"] != record["forecast_id"] or quote["event_id"] != record["event_id"]
            or quote["participants"] != record["participants"]):
        raise ValueError("quote and forecast identity/order differ")
    if quote["market"] != "series_ml" or record["best_of"] not in (3, 5):
        raise ValueError("only no-draw BO3/BO5 series ML supported")
    if not instant(record["created_at"]) <= instant(quote["retrieved_at"]) < instant(record["scheduled_start"]):
        raise ValueError("quote must follow lock and precede scheduled start")
    for field in ("source_url", "book"):
        if not isinstance(quote[field], str) or not quote[field].strip():
            raise ValueError("quote provenance missing")
    prices = quote["decimal_odds"]
    floors = quote.get("entry_floor", {})
    if not isinstance(prices, dict) or set(prices) != {"a", "b"}:
        raise ValueError("both sides of one book/time required; no mixed quotes")
    if not isinstance(floors, dict) or set(floors)-{"a", "b"}:
        raise ValueError("entry_floor keys must be a/b")
    for value in list(prices.values())+list(floors.values()):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 1:
            raise ValueError("finite decimal odds > 1 required")
    oat = audit(record)["forecasts"][0]
    implied = {side: 1/prices[side] for side in ("a", "b")}
    overround = sum(implied.values())
    results = {}
    for side in ("a", "b"):
        p = record["derived"]["winner_probabilities"][side]
        local = [p]+[c["metrics"]["winner_probabilities"][side] for c in oat["cases"]]
        cases, skipped = joint_cases(record, side)
        low, high = (cases[k]["probability"] for k in ("minimum", "maximum"))
        # Include original explicitly against harmless replay rounding noise.
        low, high = min(low, p), max(high, p)
        odds = prices[side]
        item = dict(team=record["participants"][0 if side == "a" else 1],
            probability=p, decimal_odds=odds, break_even=1/odds,
            market_no_vig_probability=implied[side]/overround,
            model_minus_market=p-implied[side]/overround,
            estimated_ev=p*odds-1, one_at_a_time_range=[min(local), max(local)],
            joint_stress_range=[low, high], joint_ev_range=[low*odds-1, high*odds-1],
            joint_witnesses=cases, skipped_rate_shifts=skipped,
            positive_ev_lost_under_joint_stress=p*odds > 1 and low*odds <= 1)
        if side in floors:
            floor = floors[side]
            item["entry_floor_audit"] = dict(decimal_odds=floor,
                estimated_ev=p*floor-1, joint_ev_range=[low*floor-1, high*floor-1],
                positive_ev_lost_under_joint_stress=p*floor > 1 and low*floor <= 1)
        results[side] = item
    return dict(schema_version="lol-decision-audit-v1", artifact_type="post_lock_decision_diagnostic",
        forecast_id=record["forecast_id"], forecast_sha256=digest(record), quote=copy.deepcopy(quote),
        quote_sha256=digest(quote), method="joint_scenario_uniform_rate_grid_and_bounded_weights",
        weight_radius=.10, scenario_rate_shifts=[-.05, 0., .05], results=results,
        calibrated=False, production_change=False, recommendation_eligible=record["recommendation_eligible"],
        limitations=["No outcomes used. Diagnostic extremes are neither forecasts nor confidence bounds.",
            "Rate steps reuse the existing audit, not estimates fitted to losing matches.",
            "Joint possibilities need evidence review; extrema need not be equally plausible.",
            "Passing stress does not establish an edge. Missing mechanisms and other parameter changes remain untested.",
            "Market no-vig is a separate benchmark, never fed into the locked model.",
            "No allocation, automatic side switch, or production qualification is generated."])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("forecast", type=Path)
    parser.add_argument("quote", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_decision(json.loads(args.forecast.read_text()), json.loads(args.quote.read_text()))
        if args.output.exists() and json.loads(args.output.read_text()) != result:
            raise ValueError("refusing to replace a different decision audit")
        write(str(args.output), result)
        print(json.dumps({"valid": True, "forecast_id": result["forecast_id"], "output": str(args.output)}))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(1, str(exc)+"\n")


if __name__ == "__main__":
    main()
