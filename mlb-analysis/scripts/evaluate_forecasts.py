#!/usr/bin/env python3
"""Evaluate immutable MLB forecast records with proper probabilistic scores."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


REQUIRED_FIELDS = {
    "game_id",
    "snapshot",
    "model_version",
    "home_win_prob",
    "away_runs_mean",
    "home_runs_mean",
    "actual_away_runs",
    "actual_home_runs",
}

UNMODELED_REQUIRED_FIELDS = {
    "game_id",
    "snapshot",
    "model_version",
    "status",
    "missing_data",
    "actual_away_runs",
    "actual_home_runs",
}


def _number(record: dict[str, Any], key: str) -> float:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{key} must be finite")
    return value


def _probability(record: dict[str, Any], key: str) -> float:
    value = _number(record, key)
    if value < 0 or value > 1:
        raise ValueError(f"{key} must use the 0-1 probability scale")
    return value


def _parse_time(value: Any, key: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be an ISO-8601 string")
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{key} must be ISO-8601") from exc


def _validate_record(record: Any, line_number: int) -> dict[str, Any]:
    if not isinstance(record, dict):
        raise ValueError(f"record {line_number} must be an object")
    status = record.get("status", "modeled")
    if not isinstance(status, str) or not status.strip():
        raise ValueError(f"record {line_number}: status must be non-empty")
    status = status.strip()
    scorable = status == "modeled"
    required = REQUIRED_FIELDS if scorable else UNMODELED_REQUIRED_FIELDS
    missing = sorted(required - record.keys())
    if missing:
        raise ValueError(f"record {line_number} missing: {', '.join(missing)}")

    cleaned = dict(record)
    cleaned["status"] = status
    cleaned["_scorable"] = scorable
    game_id = cleaned["game_id"]
    if isinstance(game_id, bool) or not isinstance(game_id, (str, int)) or not str(game_id).strip():
        raise ValueError(f"record {line_number}: game_id must be a non-empty string or integer")
    cleaned["game_id"] = str(game_id).strip()
    for key in ("snapshot", "model_version"):
        if not isinstance(cleaned[key], str) or not cleaned[key].strip():
            raise ValueError(f"record {line_number}: {key} must be non-empty")
        cleaned[key] = cleaned[key].strip()

    if scorable:
        cleaned["home_win_prob"] = _probability(cleaned, "home_win_prob")
        for key in ("away_runs_mean", "home_runs_mean"):
            cleaned[key] = _number(cleaned, key)
            if cleaned[key] < 0:
                raise ValueError(f"record {line_number}: {key} cannot be negative")
    else:
        missing_data = cleaned.get("missing_data")
        if not isinstance(missing_data, list) or not missing_data:
            raise ValueError(f"record {line_number}: unmodeled record needs non-empty missing_data")
        if not all(isinstance(value, str) and value.strip() for value in missing_data):
            raise ValueError(f"record {line_number}: missing_data values must be non-empty strings")

    for key in ("actual_away_runs", "actual_home_runs"):
        cleaned[key] = _number(cleaned, key)
        if cleaned[key] < 0:
            raise ValueError(f"record {line_number}: {key} cannot be negative")
    for key in ("actual_away_runs", "actual_home_runs"):
        if not cleaned[key].is_integer():
            raise ValueError(f"record {line_number}: {key} must be an integer")
        cleaned[key] = int(cleaned[key])
    if cleaned["actual_away_runs"] == cleaned["actual_home_runs"]:
        raise ValueError(f"record {line_number}: settled MLB games cannot end tied")

    if scorable and "market_home_prob_no_vig" in cleaned and cleaned["market_home_prob_no_vig"] is not None:
        cleaned["market_home_prob_no_vig"] = _probability(cleaned, "market_home_prob_no_vig")

    interval_groups = (
        ("away_runs_p10", "away_runs_p90"),
        ("home_runs_p10", "home_runs_p90"),
        ("total_runs_p10", "total_runs_p90"),
    )
    for lower_key, upper_key in interval_groups:
        present = scorable and (lower_key in cleaned or upper_key in cleaned)
        if present and (cleaned.get(lower_key) is None or cleaned.get(upper_key) is None):
            raise ValueError(f"record {line_number}: {lower_key} and {upper_key} must appear together")
        if present:
            lower = _number(cleaned, lower_key)
            upper = _number(cleaned, upper_key)
            if lower > upper:
                raise ValueError(f"record {line_number}: {lower_key} cannot exceed {upper_key}")
            cleaned[lower_key] = lower
            cleaned[upper_key] = upper

    has_prediction_time = "predicted_at" in cleaned or "first_pitch" in cleaned
    if has_prediction_time:
        if "predicted_at" not in cleaned or "first_pitch" not in cleaned:
            raise ValueError(f"record {line_number}: predicted_at and first_pitch must appear together")
        predicted_at = _parse_time(cleaned["predicted_at"], "predicted_at")
        first_pitch = _parse_time(cleaned["first_pitch"], "first_pitch")
        if predicted_at.tzinfo is None or first_pitch.tzinfo is None:
            raise ValueError(f"record {line_number}: timestamps must include an offset")
        if predicted_at >= first_pitch:
            raise ValueError(f"record {line_number}: prediction is not strictly pregame")
    return cleaned


def _read_records(path: str) -> list[dict[str, Any]]:
    if path == "-":
        text = sys.stdin.read()
    else:
        text = Path(path).read_text(encoding="utf-8")
    stripped = text.lstrip()
    if not stripped:
        raise ValueError("forecast log is empty")
    if stripped.startswith("["):
        raw_records = json.loads(text)
        if not isinstance(raw_records, list):
            raise ValueError("JSON input must be an array")
    else:
        raw_records = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if line.strip():
                try:
                    raw_records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid JSON on line {line_number}: {exc}") from exc
    return [_validate_record(record, index) for index, record in enumerate(raw_records, 1)]


def _outcome(record: dict[str, Any]) -> int:
    return int(record["actual_home_runs"] > record["actual_away_runs"])


def _log_loss(probability: float, outcome: int) -> float:
    probability = min(max(probability, 1e-12), 1 - 1e-12)
    return -(outcome * math.log(probability) + (1 - outcome) * math.log(1 - probability))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _round(value: float) -> float:
    return round(value, 6)


def _calibration(records: list[dict[str, Any]], bin_width: float) -> list[dict[str, Any]]:
    bin_count = int(round(1.0 / bin_width))
    bins: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        index = min(int(record["home_win_prob"] / bin_width), bin_count - 1)
        bins[index].append(record)
    output = []
    for index in sorted(bins):
        group = bins[index]
        predicted = _mean([record["home_win_prob"] for record in group])
        observed = _mean([_outcome(record) for record in group])
        output.append(
            {
                "range": [round(index * bin_width, 3), round((index + 1) * bin_width, 3)],
                "n": len(group),
                "mean_predicted": _round(predicted),
                "observed_home_win_rate": _round(observed),
                "calibration_gap": _round(observed - predicted),
                "small_sample_warning": len(group) < 30,
            }
        )
    return output


def _coverage(
    records: list[dict[str, Any]], lower_key: str, upper_key: str, actual: Callable[[dict[str, Any]], float]
) -> dict[str, Any] | None:
    eligible = [r for r in records if r.get(lower_key) is not None and r.get(upper_key) is not None]
    if not eligible:
        return None
    covered = [r[lower_key] <= actual(r) <= r[upper_key] for r in eligible]
    widths = [r[upper_key] - r[lower_key] for r in eligible]
    return {
        "n": len(eligible),
        "coverage": _round(_mean([float(value) for value in covered])),
        "mean_width": _round(_mean(widths)),
    }


def summarize(records: list[dict[str, Any]], bin_width: float) -> dict[str, Any]:
    outcomes = [_outcome(record) for record in records]
    probabilities = [record["home_win_prob"] for record in records]
    away_errors = [record["away_runs_mean"] - record["actual_away_runs"] for record in records]
    home_errors = [record["home_runs_mean"] - record["actual_home_runs"] for record in records]
    total_errors = [away + home for away, home in zip(away_errors, home_errors)]
    exact_hits = [
        round(record["away_runs_mean"]) == record["actual_away_runs"]
        and round(record["home_runs_mean"]) == record["actual_home_runs"]
        for record in records
    ]

    result: dict[str, Any] = {
        "n": len(records),
        "small_sample_warning": len(records) < 200,
        "moneyline": {
            "brier": _round(_mean([(p - y) ** 2 for p, y in zip(probabilities, outcomes)])),
            "log_loss": _round(_mean([_log_loss(p, y) for p, y in zip(probabilities, outcomes)])),
            "directional_accuracy_diagnostic": _round(
                _mean([float((p >= 0.5) == bool(y)) for p, y in zip(probabilities, outcomes)])
            ),
        },
        "runs": {
            "team_run_mae": _round(
                _mean([abs(error) for error in away_errors + home_errors])
            ),
            "away_run_bias": _round(_mean(away_errors)),
            "home_run_bias": _round(_mean(home_errors)),
            "total_run_mae": _round(_mean([abs(error) for error in total_errors])),
            "total_run_bias": _round(_mean(total_errors)),
            "rounded_mean_exact_score_hit_rate_diagnostic": _round(
                _mean([float(value) for value in exact_hits])
            ),
        },
        "calibration": _calibration(records, bin_width),
        "interval_coverage": {
            "away_80": _coverage(records, "away_runs_p10", "away_runs_p90", lambda r: r["actual_away_runs"]),
            "home_80": _coverage(records, "home_runs_p10", "home_runs_p90", lambda r: r["actual_home_runs"]),
            "total_80": _coverage(
                records,
                "total_runs_p10",
                "total_runs_p90",
                lambda r: r["actual_away_runs"] + r["actual_home_runs"],
            ),
        },
    }

    market_records = [record for record in records if record.get("market_home_prob_no_vig") is not None]
    if market_records:
        result["closing_market_audit_only"] = {
            "n": len(market_records),
            "brier": _round(
                _mean(
                    [
                        (record["market_home_prob_no_vig"] - _outcome(record)) ** 2
                        for record in market_records
                    ]
                )
            ),
            "log_loss": _round(
                _mean(
                    [
                        _log_loss(record["market_home_prob_no_vig"], _outcome(record))
                        for record in market_records
                    ]
                )
            ),
            "note": "postgame benchmark only; never a production feature",
        }
    return result


def availability_audit(records: list[dict[str, Any]]) -> dict[str, Any]:
    scorable = [record for record in records if record["_scorable"]]
    unscored = [record for record in records if not record["_scorable"]]
    status_counts = Counter(record["status"] for record in records)
    missing_data_counts = Counter(
        item
        for record in unscored
        for item in record.get("missing_data", [])
    )
    snapshots: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "scorable": 0, "unscored": 0}
    )
    for record in records:
        bucket = snapshots[record["snapshot"]]
        bucket["total"] += 1
        key = "scorable" if record["_scorable"] else "unscored"
        bucket[key] += 1
    total = len(records)
    return {
        "total_records": total,
        "scorable_records": len(scorable),
        "unscored_records": len(unscored),
        "model_coverage": _round(len(scorable) / total) if total else 0.0,
        "status_counts": dict(sorted(status_counts.items())),
        "missing_data_counts": dict(sorted(missing_data_counts.items())),
        "by_snapshot": dict(sorted(snapshots.items())),
        "note": "Only status=modeled records enter probabilistic and run-error metrics.",
    }


def _paired_loss(record: dict[str, Any], metric: str) -> float:
    outcome = _outcome(record)
    if metric == "brier":
        return (record["home_win_prob"] - outcome) ** 2
    if metric == "log_loss":
        return _log_loss(record["home_win_prob"], outcome)
    if metric == "team_run_mae":
        away = abs(record["away_runs_mean"] - record["actual_away_runs"])
        home = abs(record["home_runs_mean"] - record["actual_home_runs"])
        return (away + home) / 2.0
    raise ValueError(f"unknown metric: {metric}")


def compare_versions(
    records: list[dict[str, Any]], old_version: str, new_version: str, seed: int
) -> dict[str, Any]:
    by_version: dict[str, dict[tuple[str, str], dict[str, Any]]] = defaultdict(dict)
    for record in records:
        key = (record["game_id"], record["snapshot"])
        version = record["model_version"]
        if key in by_version[version]:
            raise ValueError(f"duplicate {version} record for {key}")
        by_version[version][key] = record
    if old_version not in by_version or new_version not in by_version:
        raise ValueError("both comparison versions must exist in the log")
    shared = sorted(set(by_version[old_version]) & set(by_version[new_version]))
    if not shared:
        raise ValueError("comparison versions have no paired game_id + snapshot records")

    rng = random.Random(seed)
    output: dict[str, Any] = {
        "old_version": old_version,
        "new_version": new_version,
        "paired_n": len(shared),
        "interpretation": "delta is new minus old; negative is better",
        "metrics": {},
    }
    for metric in ("brier", "log_loss", "team_run_mae"):
        deltas = [
            _paired_loss(by_version[new_version][key], metric)
            - _paired_loss(by_version[old_version][key], metric)
            for key in shared
        ]
        bootstrap = []
        for _ in range(2_000):
            bootstrap.append(_mean([deltas[rng.randrange(len(deltas))] for _ in deltas]))
        bootstrap.sort()
        output["metrics"][metric] = {
            "mean_delta": _round(_mean(deltas)),
            "bootstrap_95pct_interval": [
                _round(bootstrap[int(0.025 * len(bootstrap))]),
                _round(bootstrap[int(0.975 * len(bootstrap)) - 1]),
            ],
        }
    output["promotion_warning"] = (
        "Do not promote from a small paired sample or when uncertainty spans meaningful regression."
    )
    return output


def _demo_records() -> list[dict[str, Any]]:
    records = []
    for index in range(1, 41):
        actual_home = 5 if index % 3 else 2
        actual_away = 3 if index % 4 else 6
        for version, probability, home_mean in (
            ("old", 0.60, 5.2),
            ("new", 0.56, 4.7),
        ):
            records.append(
                {
                    "game_id": f"demo-{index}",
                    "snapshot": "post-lineup",
                    "model_version": version,
                    "home_win_prob": probability,
                    "away_runs_mean": 4.0,
                    "home_runs_mean": home_mean,
                    "actual_away_runs": actual_away,
                    "actual_home_runs": actual_home,
                    "away_runs_p10": 1,
                    "away_runs_p90": 7,
                    "home_runs_p10": 1,
                    "home_runs_p90": 8,
                    "total_runs_p10": 3,
                    "total_runs_p90": 14,
                }
            )
    return [_validate_record(record, index) for index, record in enumerate(records, 1)]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate immutable MLB forecast JSONL/JSON records. Probabilities use 0-1."
    )
    parser.add_argument("input", nargs="?", help="JSONL/JSON path, or - for stdin")
    parser.add_argument("--demo", action="store_true", help="run deterministic smoke-test records")
    parser.add_argument("--bin-width", type=float, default=0.10, help="calibration bin width")
    parser.add_argument("--compare", nargs=2, metavar=("OLD", "NEW"), help="paired model versions")
    parser.add_argument("--seed", type=int, default=20260718, help="bootstrap seed")
    args = parser.parse_args()

    if args.demo == bool(args.input):
        parser.error("provide exactly one of input or --demo")
    if args.bin_width <= 0 or args.bin_width > 0.5 or abs(round(1 / args.bin_width) * args.bin_width - 1) > 1e-9:
        parser.error("--bin-width must evenly divide 1 and be in (0, 0.5]")

    try:
        records = _demo_records() if args.demo else _read_records(args.input)
        scorable_records = [record for record in records if record["_scorable"]]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in scorable_records:
            grouped[record["model_version"]].append(record)
        result: dict[str, Any] = {
            "records": len(records),
            "availability": availability_audit(records),
            "by_model_version": {
                version: summarize(group, args.bin_width) for version, group in sorted(grouped.items())
            },
        }
        if args.compare:
            result["paired_comparison"] = compare_versions(
                scorable_records, args.compare[0], args.compare[1], args.seed
            )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
