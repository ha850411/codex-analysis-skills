#!/usr/bin/env python3
"""Derive coherent MLB markets from precomputed phase run means.

This script deliberately does not estimate team strength. Inputs such as run means
and dispersion must come from a versioned, walk-forward model. It simulates the
same games for F5, full-game moneyline, run lines, totals, and score intervals.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


def _require_number(value: Any, name: str, minimum: float, maximum: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric")
    value = float(value)
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}")
    return value


def _poisson(rng: random.Random, mean: float) -> int:
    if mean <= 0:
        return 0
    threshold = math.exp(-mean)
    product = 1.0
    count = 0
    while product > threshold:
        count += 1
        product *= rng.random()
    return count - 1


def _mean_one_lognormal(rng: random.Random, sigma: float) -> float:
    if sigma == 0:
        return 1.0
    return math.exp(rng.gauss(-0.5 * sigma * sigma, sigma))


def _percent(numerator: int, denominator: int) -> float:
    return round(100.0 * numerator / denominator, 4)


def _average(values: Iterable[int]) -> float:
    values = list(values)
    return sum(values) / len(values)


def _quantile(sorted_values: list[int], probability: float) -> int:
    if not sorted_values:
        raise ValueError("cannot calculate a quantile from an empty sample")
    index = math.ceil(probability * len(sorted_values)) - 1
    return sorted_values[min(max(index, 0), len(sorted_values) - 1)]


def _interval(values: list[int], central_mass: float) -> list[int]:
    ordered = sorted(values)
    tail = (1.0 - central_mass) / 2.0
    return [_quantile(ordered, tail), _quantile(ordered, 1.0 - tail)]


def _correlation(xs: list[int], ys: list[int]) -> float:
    mean_x = _average(xs)
    mean_y = _average(ys)
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    denominator_x = sum((x - mean_x) ** 2 for x in xs)
    denominator_y = sum((y - mean_y) ** 2 for y in ys)
    if denominator_x == 0 or denominator_y == 0:
        return 0.0
    return numerator / math.sqrt(denominator_x * denominator_y)


def _select_scenario(rng: random.Random, scenarios: list[dict[str, Any]]) -> dict[str, Any]:
    draw = rng.random()
    cumulative = 0.0
    for scenario in scenarios:
        cumulative += scenario["weight"]
        if draw <= cumulative:
            return scenario
    return scenarios[-1]


def _settlement(delta: float) -> str:
    if abs(delta) < 1e-9:
        return "push"
    return "win" if delta > 0 else "loss"


def _validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError("input must be a JSON object")

    iterations = int(_require_number(raw.get("iterations"), "iterations", 50_000, 2_000_000))
    seed = int(_require_number(raw.get("seed"), "seed", 0, 2**63 - 1))
    model_version = str(raw.get("model_version", "")).strip()
    game_id = str(raw.get("game_id", "")).strip()
    if not model_version or not game_id:
        raise ValueError("model_version and game_id are required")

    dispersion = raw.get("dispersion")
    if not isinstance(dispersion, dict):
        raise ValueError("dispersion must be an object fitted from historical data")
    shared_sigma = _require_number(
        dispersion.get("shared_game_sigma"), "dispersion.shared_game_sigma", 0, 1.5
    )
    away_sigma = _require_number(
        dispersion.get("away_team_sigma"), "dispersion.away_team_sigma", 0, 1.5
    )
    home_sigma = _require_number(
        dispersion.get("home_team_sigma"), "dispersion.home_team_sigma", 0, 1.5
    )

    extra = raw.get("extra_innings")
    if not isinstance(extra, dict):
        raise ValueError("extra_innings must be an object")
    extra_away = _require_number(
        extra.get("away_mean_per_half"), "extra_innings.away_mean_per_half", 0.05, 5
    )
    extra_home = _require_number(
        extra.get("home_mean_per_half"), "extra_innings.home_mean_per_half", 0.05, 5
    )

    scenarios_raw = raw.get("scenarios")
    if not isinstance(scenarios_raw, list) or not scenarios_raw:
        raise ValueError("scenarios must be a non-empty array")
    scenarios: list[dict[str, Any]] = []
    weight_sum = 0.0
    for index, source in enumerate(scenarios_raw):
        if not isinstance(source, dict):
            raise ValueError(f"scenarios[{index}] must be an object")
        name = str(source.get("name", "")).strip()
        if not name:
            raise ValueError(f"scenarios[{index}].name is required")
        weight = _require_number(source.get("weight"), f"scenarios[{index}].weight", 0, 1)
        if weight == 0:
            continue
        scenario: dict[str, Any] = {"name": name, "weight": weight}
        for side in ("away", "home"):
            team = source.get(side)
            if not isinstance(team, dict):
                raise ValueError(f"scenarios[{index}].{side} must be an object")
            scenario[side] = {
                "f5_mean": _require_number(
                    team.get("f5_mean"), f"scenarios[{index}].{side}.f5_mean", 0.05, 15
                ),
                "late_mean_6_to_9": _require_number(
                    team.get("late_mean_6_to_9"),
                    f"scenarios[{index}].{side}.late_mean_6_to_9",
                    0.05,
                    15,
                ),
            }
        scenarios.append(scenario)
        weight_sum += weight
    if not scenarios or abs(weight_sum - 1.0) > 1e-9:
        raise ValueError(f"positive scenario weights must sum to 1.0, got {weight_sum}")

    markets = raw.get("markets", {})
    if not isinstance(markets, dict):
        raise ValueError("markets must be an object")

    def totals(key: str) -> list[float]:
        values = markets.get(key, [])
        if not isinstance(values, list):
            raise ValueError(f"markets.{key} must be an array")
        return sorted({_require_number(value, f"markets.{key}", 0.5, 40) for value in values})

    def run_lines(key: str) -> list[dict[str, Any]]:
        values = markets.get(key, [])
        if not isinstance(values, list):
            raise ValueError(f"markets.{key} must be an array")
        result = []
        for index, value in enumerate(values):
            if not isinstance(value, dict) or value.get("team") not in {"away", "home"}:
                raise ValueError(f"markets.{key}[{index}] needs team=away|home")
            result.append(
                {
                    "team": value["team"],
                    "line": _require_number(value.get("line"), f"markets.{key}[{index}].line", -10, 10),
                }
            )
        return result

    return {
        "model_version": model_version,
        "game_id": game_id,
        "iterations": iterations,
        "seed": seed,
        "dispersion": {
            "shared_game_sigma": shared_sigma,
            "away_team_sigma": away_sigma,
            "home_team_sigma": home_sigma,
        },
        "extra_innings": {
            "away_mean_per_half": extra_away,
            "home_mean_per_half": extra_home,
        },
        "scenarios": scenarios,
        "markets": {
            "f5_totals": totals("f5_totals"),
            "full_totals": totals("full_totals"),
            "f5_run_lines": run_lines("f5_run_lines"),
            "full_run_lines": run_lines("full_run_lines"),
        },
    }


def simulate(config: dict[str, Any]) -> dict[str, Any]:
    rng = random.Random(config["seed"])
    iterations = config["iterations"]
    dispersion = config["dispersion"]
    extra = config["extra_innings"]

    f5_away_scores: list[int] = []
    f5_home_scores: list[int] = []
    final_away_scores: list[int] = []
    final_home_scores: list[int] = []
    final_scores: Counter[tuple[int, int]] = Counter()
    scenario_counts: Counter[str] = Counter()
    extra_games = 0

    for _ in range(iterations):
        scenario = _select_scenario(rng, config["scenarios"])
        scenario_counts[scenario["name"]] += 1
        common = _mean_one_lognormal(rng, dispersion["shared_game_sigma"])
        away_multiplier = common * _mean_one_lognormal(rng, dispersion["away_team_sigma"])
        home_multiplier = common * _mean_one_lognormal(rng, dispersion["home_team_sigma"])

        away = 0
        home = 0
        away_f5_rate = scenario["away"]["f5_mean"] / 5.0 * away_multiplier
        home_f5_rate = scenario["home"]["f5_mean"] / 5.0 * home_multiplier
        away_late_rate = scenario["away"]["late_mean_6_to_9"] / 4.0 * away_multiplier
        home_late_rate = scenario["home"]["late_mean_6_to_9"] / 4.0 * home_multiplier

        for _inning in range(1, 6):
            away += _poisson(rng, away_f5_rate)
            home += _poisson(rng, home_f5_rate)
        f5_away_scores.append(away)
        f5_home_scores.append(home)

        for _inning in range(6, 9):
            away += _poisson(rng, away_late_rate)
            home += _poisson(rng, home_late_rate)

        away += _poisson(rng, away_late_rate)
        if home <= away:
            home_add = _poisson(rng, home_late_rate)
            if home + home_add > away:
                home_add = away - home + 1
            home += home_add

        if away == home:
            extra_games += 1
            while away == home:
                away_add = _poisson(rng, extra["away_mean_per_half"] * away_multiplier)
                home_add = _poisson(rng, extra["home_mean_per_half"] * home_multiplier)
                away += away_add
                if home + home_add > away:
                    home_add = away - home + 1
                home += home_add

        final_away_scores.append(away)
        final_home_scores.append(home)
        final_scores[(away, home)] += 1

    f5_away_wins = sum(a > h for a, h in zip(f5_away_scores, f5_home_scores))
    f5_ties = sum(a == h for a, h in zip(f5_away_scores, f5_home_scores))
    f5_home_wins = iterations - f5_away_wins - f5_ties
    f5_decisions = iterations - f5_ties
    full_away_wins = sum(a > h for a, h in zip(final_away_scores, final_home_scores))
    full_home_wins = iterations - full_away_wins

    f5_totals = [a + h for a, h in zip(f5_away_scores, f5_home_scores)]
    full_totals = [a + h for a, h in zip(final_away_scores, final_home_scores)]

    def total_markets(scores: list[int], lines: list[float]) -> list[dict[str, Any]]:
        output = []
        for line in lines:
            counts = Counter(_settlement(score - line) for score in scores)
            output.append(
                {
                    "line": line,
                    "over_pct": _percent(counts["win"], iterations),
                    "push_pct": _percent(counts["push"], iterations),
                    "under_pct": _percent(counts["loss"], iterations),
                }
            )
        return output

    def line_markets(
        away_scores: list[int], home_scores: list[int], lines: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        output = []
        for market in lines:
            if market["team"] == "away":
                deltas = [a + market["line"] - h for a, h in zip(away_scores, home_scores)]
            else:
                deltas = [h + market["line"] - a for a, h in zip(away_scores, home_scores)]
            counts = Counter(_settlement(delta) for delta in deltas)
            output.append(
                {
                    "team": market["team"],
                    "line": market["line"],
                    "cover_pct": _percent(counts["win"], iterations),
                    "push_pct": _percent(counts["push"], iterations),
                    "no_cover_pct": _percent(counts["loss"], iterations),
                }
            )
        return output

    top_scores = [
        {"away": away, "home": home, "probability_pct": _percent(count, iterations)}
        for (away, home), count in final_scores.most_common(5)
    ]

    f5_two_way = None
    if f5_decisions:
        f5_two_way = {
            "away_win_pct": _percent(f5_away_wins, f5_decisions),
            "home_win_pct": _percent(f5_home_wins, f5_decisions),
        }

    return {
        "game_id": config["game_id"],
        "model_version": config["model_version"],
        "iterations": iterations,
        "seed": config["seed"],
        "simulation_parameters": {
            "dispersion": config["dispersion"],
            "extra_innings": config["extra_innings"],
            "walkoff_handling": "home scoring is capped at the run needed to win",
        },
        "scenario_realization_pct": {
            name: _percent(count, iterations) for name, count in sorted(scenario_counts.items())
        },
        "f5": {
            "away_win_pct": _percent(f5_away_wins, iterations),
            "tie_pct": _percent(f5_ties, iterations),
            "home_win_pct": _percent(f5_home_wins, iterations),
            "two_way_excluding_tie": f5_two_way,
            "expected_runs": {
                "away": round(_average(f5_away_scores), 4),
                "home": round(_average(f5_home_scores), 4),
                "total": round(_average(f5_totals), 4),
            },
            "central_intervals": {
                "away_50": _interval(f5_away_scores, 0.50),
                "away_80": _interval(f5_away_scores, 0.80),
                "home_50": _interval(f5_home_scores, 0.50),
                "home_80": _interval(f5_home_scores, 0.80),
                "total_50": _interval(f5_totals, 0.50),
                "total_80": _interval(f5_totals, 0.80),
            },
            "totals": total_markets(f5_totals, config["markets"]["f5_totals"]),
            "run_lines": line_markets(
                f5_away_scores, f5_home_scores, config["markets"]["f5_run_lines"]
            ),
        },
        "full_game": {
            "away_win_pct": _percent(full_away_wins, iterations),
            "home_win_pct": _percent(full_home_wins, iterations),
            "extra_innings_pct": _percent(extra_games, iterations),
            "score_correlation": round(_correlation(final_away_scores, final_home_scores), 4),
            "expected_runs": {
                "away": round(_average(final_away_scores), 4),
                "home": round(_average(final_home_scores), 4),
                "total": round(_average(full_totals), 4),
            },
            "central_intervals": {
                "away_50": _interval(final_away_scores, 0.50),
                "away_80": _interval(final_away_scores, 0.80),
                "home_50": _interval(final_home_scores, 0.50),
                "home_80": _interval(final_home_scores, 0.80),
                "total_50": _interval(full_totals, 0.50),
                "total_80": _interval(full_totals, 0.80),
            },
            "top_scorelines": top_scores,
            "totals": total_markets(full_totals, config["markets"]["full_totals"]),
            "run_lines": line_markets(
                final_away_scores, final_home_scores, config["markets"]["full_run_lines"]
            ),
        },
    }


def _demo_config() -> dict[str, Any]:
    return {
        "model_version": "demo-not-for-forecasting",
        "game_id": "away-at-home-demo",
        "iterations": 50_000,
        "seed": 20260718,
        "dispersion": {
            "shared_game_sigma": 0.10,
            "away_team_sigma": 0.20,
            "home_team_sigma": 0.20,
        },
        "extra_innings": {"away_mean_per_half": 0.75, "home_mean_per_half": 0.78},
        "scenarios": [
            {
                "name": "confirmed-lineup",
                "weight": 1.0,
                "away": {"f5_mean": 2.1, "late_mean_6_to_9": 1.7},
                "home": {"f5_mean": 2.4, "late_mean_6_to_9": 1.9},
            }
        ],
        "markets": {
            "f5_totals": [4.0, 4.5],
            "full_totals": [8.0, 8.5],
            "f5_run_lines": [{"team": "home", "line": -0.5}],
            "full_run_lines": [
                {"team": "home", "line": -1.5},
                {"team": "away", "line": 1.5},
            ],
        },
    }


def _read_input(path: str) -> dict[str, Any]:
    if path == "-":
        return json.load(sys.stdin)
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate coherent MLB score and market distributions from phase run means."
    )
    parser.add_argument("input", nargs="?", help="JSON config path, or - for stdin")
    parser.add_argument("--demo", action="store_true", help="run a deterministic smoke-test config")
    parser.add_argument("--output", help="optional output JSON path; stdout when omitted")
    args = parser.parse_args()

    if args.demo == bool(args.input):
        parser.error("provide exactly one of input or --demo")

    try:
        raw = _demo_config() if args.demo else _read_input(args.input)
        result = simulate(_validate_config(raw))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
