#!/usr/bin/env python3
"""Derive CS presentation data from a validated forecast; never fit or alter it."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.forecast.core import derive, digest, score_pair, series_tree, validate
from shared.forecast.cli import write


def fair(probability):
    return 1 / probability if probability > 0 else None


def tree_maps(best_of, nodes):
    """Unconditional reach mass and A-win mass, indexed by map number."""
    reach = [0.0] * best_of
    wins = [0.0] * best_of
    target = best_of // 2 + 1

    def walk(a, b, path, mass):
        if max(a, b) == target:
            return
        index = a + b
        p = nodes[path or "ROOT"]
        reach[index] += mass
        wins[index] += mass * p
        walk(a + 1, b, path + "W", mass * p)
        walk(a, b + 1, path + "L", mass * (1 - p))

    walk(0, 0, "", 1.0)
    return reach, wins


def summarize(record):
    validate(record)
    if record["sport"] != "cs":
        raise ValueError("CS forecasts only")
    result = {
        "schema_version": "cs-presentation-1.0",
        "forecast_id": record["forecast_id"],
        "forecast_hash": digest(record),
        "probability_unit": "fraction",
        "participants": list(record["participants"]),
        "snapshot": record["snapshot"],
        "data_cutoff": record["data_cutoff"],
        "status": record["status"],
        "winner_pick": None,
        "missing_data": list(record["missing_data"]),
        "round_player_predictions": None,
        "round_player_reason": "No round or player model is supplied by this summarizer.",
    }
    if record["status"] == "unmodeled":
        return result
    bo = record["best_of"]
    if bo not in (1, 3, 5):
        raise ValueError("CS presentation supports BO1, BO3 and BO5")
    scores = record["score_distribution"]
    derived = derive(scores)
    winners = {side: derived["winner_probabilities"][side] for side in ("a", "b")}
    tied = len(derived["winner_ties"]) > 1
    representative = {}
    for side in ("a", "b"):
        winning = {s: p for s, p in scores.items()
                   if p > 0 and ((score_pair(s)[0] > score_pair(s)[1]) == (side == "a"))}
        peak = max(winning.values(), default=None)
        representative[side] = {
            "scores": sorted(s for s, p in winning.items() if abs(p - peak) < 1e-12),
            "probability": peak,
        }
    totals = derived["total_distribution"]
    expected_a, expected_b = derived["means"]
    lines = {}
    for line in ({1: [], 3: [2.5], 5: [3.5, 4.5]}[bo]):
        over = sum(p for total, p in totals.items() if int(total) > line)
        under = sum(p for total, p in totals.items() if int(total) < line)
        lines[str(line)] = {"over": over, "under": under,
                            "fair_over": fair(over), "fair_under": fair(under)}
    at_least = {}
    if bo > 1:
        for threshold in range(1, bo // 2 + 1):
            at_least[str(threshold)] = {
                side: sum(p for score, p in scores.items() if score_pair(score)[i] >= threshold)
                for i, side in enumerate(("a", "b"))}
    maps = [{"map_number": n,
             "reach_probability": sum(p for total, p in totals.items() if int(total) >= n),
             "a_win_given_played": None, "b_win_given_played": None}
            for n in range(1, bo + 1)]
    scenario_rows = []
    scenarios = [s for s in record.get("scenarios", []) if s["weight"] > 0]
    map_reason = "Complete conditional trees unavailable; map win rates cannot be inferred from series scores."
    if scenarios and all("nodes" in s for s in scenarios):
        weighted_reach = [0.0] * bo
        weighted_wins = [0.0] * bo
        for scenario in scenarios:
            replayed = series_tree(bo, scenario["nodes"])
            expected = scenario["score_distribution"]
            if any(abs(replayed.get(s, 0) - expected.get(s, 0)) > 1e-8
                   for s in set(replayed) | set(expected)):
                raise ValueError("conditional tree differs from scenario score distribution")
            reach, wins = tree_maps(bo, scenario["nodes"])
            scenario_rows.append({"id": scenario["id"], "weight": scenario["weight"],
                                  "maps": [{"map_number": i + 1, "reach_probability": reach[i],
                                            "a_win_given_played": wins[i] / reach[i] if reach[i] > 0 else None,
                                            "b_win_given_played": 1 - wins[i] / reach[i] if reach[i] > 0 else None}
                                           for i in range(bo)]})
            for i in range(bo):
                weighted_reach[i] += scenario["weight"] * reach[i]
                weighted_wins[i] += scenario["weight"] * wins[i]
        for i, row in enumerate(maps):
            if abs(row["reach_probability"] - weighted_reach[i]) > 1e-8:
                raise ValueError("map reach mass differs from series distribution")
            if weighted_reach[i] > 0:
                row["a_win_given_played"] = weighted_wins[i] / weighted_reach[i]
                row["b_win_given_played"] = 1 - row["a_win_given_played"]
        map_reason = None
    elif bo == 1:
        # For BO1 the series winner is exactly the only map winner.
        maps[0]["a_win_given_played"] = winners["a"]
        maps[0]["b_win_given_played"] = winners["b"]
        map_reason = None
    result.update(
        best_of=bo, winner_pick=None if tied else derived["winner_pick"],
        winner_ties=derived["winner_ties"], winner_probabilities=winners,
        winner_fair_odds={side: fair(p) for side, p in winners.items()},
        representative_scores=representative,
        score_modes=derived["score_ties"], score_mode_probability=derived["score_mode_probability"],
        score_distribution=dict(scores), expected_maps_won={"a": expected_a, "b": expected_b},
        expected_total_maps=expected_a + expected_b,
        expected_map_margin_a_minus_b=expected_a - expected_b,
        total_maps_distribution=dict(totals), total_lines=lines, at_least_maps=at_least,
        maps=maps, scenario_maps=scenario_rows, map_rate_reason=map_reason,
    )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", help="canonical CS forecast JSON")
    parser.add_argument("--output", required=True, help="create-only presentation JSON")
    args = parser.parse_args()
    try:
        result = summarize(json.loads(Path(args.input).read_text(encoding="utf8")))
        write(args.output, result)
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"CS presentation error: {exc}\n")
    print(json.dumps({"output": args.output, "forecast_id": result["forecast_id"],
                      "forecast_hash": result["forecast_hash"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
