"""Paired offline experiments. Failed predictions remain in the target set."""
from __future__ import annotations

import copy
import random
from collections import defaultdict
from datetime import datetime, timezone

from shared.forecast.core import derive, digest, instant, score_pair
from shared.forecast.evaluation import compare as shared_compare, evaluate as shared_evaluate, score
from shared.forecast.cli import forecast as old_forecast
from shared.forecast.models import train as old_train
from .data import history
from .strength import train
from .series import predict, validate_forecast


def market_scores(record):
    if record.get("actual_score") is not None:
        a, b = score_pair(record["actual_score"])
        bo = record.get("best_of")
        if bo not in (1, 3, 5) or max(a, b) != bo // 2 + 1 or min(a, b) >= max(a, b):
            raise ValueError("actual score incompatible with Valorant best_of")
    if score(record) is None or not record.get("score_distribution"):
        return None
    a, b = score_pair(record["actual_score"])
    scores, bo = record["score_distribution"], record.get("best_of")
    result = {}
    if bo == 3:
        margins, totals = [-1.5, 1.5], [2.5]
    elif bo == 5:
        margins, totals = [-2.5, -1.5, 1.5, 2.5], [3.5, 4.5]
    else:
        return result
    for line in margins:
        p = sum(p for s, p in scores.items() if score_pair(s)[0] - score_pair(s)[1] > line)
        result[f"margin_gt_{line}_brier"] = 2 * (p - float(a - b > line)) ** 2
    for line in totals:
        p = sum(p for s, p in scores.items() if sum(score_pair(s)) > line)
        result[f"total_gt_{line}_brier"] = 2 * (p - float(a + b > line)) ** 2
    return result


def evaluate(records):
    for record in records:
        if record.get("scope", "full-series") != "full-series":
            raise ValueError("evaluate series and named-map conditional forecasts separately")
        market_scores(record)
    out = shared_evaluate(records)
    values = defaultdict(list)
    for record in records:
        if record.get("valorant"):
            # Actual outcomes are appended for evaluation, not injected into predict.
            validate_forecast(record)
        for k, v in (market_scores(record) or {}).items():
            values[k].append(v)
    out["market_metrics"] = {k: {"value": sum(v) / len(v), "n": len(v)} for k, v in sorted(values.items())}
    out["market_metric_definition"] = "two-outcome Brier sum; complementary markets not counted twice"
    modeled = sum(r.get("status") != "unmodeled" and bool(r.get("score_distribution")) for r in records)
    settled = sum(r.get("result_status") == "final" and r.get("actual_score") is not None for r in records)
    out["prediction_availability"] = {"modeled_n": modeled, "target_n": len(records), "value": modeled / len(records) if records else 0.}
    out["settlement_coverage"] = {"settled_n": settled, "target_n": len(records), "value": settled / len(records) if records else 0.}
    return out


def compare(records, baseline, challenger):
    for record in records:
        if record.get("valorant"):
            validate_forecast(record)
        market_scores(record)
    versions = {baseline: {}, challenger: {}}
    for record in records:
        if record["model_version"] not in versions:
            continue
        key = tuple(record[k] for k in ("event_id", "snapshot", "data_cutoff"))
        if key in versions[record["model_version"]]:
            raise ValueError("duplicate paired event")
        versions[record["model_version"]][key] = record
    old, new = versions[baseline], versions[challenger]
    for k in old.keys() & new.keys():
        if old[k]["participants"] != new[k]["participants"] or old[k].get("best_of") != new[k].get("best_of"):
            raise ValueError("paired participants/order or best_of differ")
    result = shared_compare(records, baseline, challenger)
    differences, cohort_diffs = defaultdict(lambda: defaultdict(list)), defaultdict(list)
    for key in sorted(old.keys() & new.keys()):
        left, right = old[key], new[key]
        a, b = market_scores(left), market_scores(right)
        if a is None or b is None:
            continue
        day = instant(left["data_cutoff"]).date().isoformat()
        for metric in a.keys() & b.keys():
            differences[metric][day].append(b[metric] - a[metric])
        group = (left.get("best_of"), left.get("evaluation_cohort", {}).get("patch", "unknown"),
                 left.get("evaluation_cohort", {}).get("roster_state", "unknown"), left["snapshot"])
        sa, sb = score(left), score(right)
        cohort_diffs[group].append((sb["winner_accuracy"] - sa["winner_accuracy"], sb.get("exact_score_accuracy", 0) - sa.get("exact_score_accuracy", 0)))
    rng = random.Random(20261001)
    result["market_metrics"] = {}
    for name, blocks in sorted(differences.items()):
        days = sorted(blocks)
        values = [x for day in days for x in blocks[day]]
        draws = []
        for _ in range(2000):
            sample = [v for _ in days for v in blocks[rng.choice(days)]]
            draws.append(sum(sample) / len(sample))
        draws.sort()
        delta = sum(values) / len(values)
        result["market_metrics"][name] = {"delta": delta, "paired_n": len(values), "blocks": len(days), "interval_95": [draws[50], draws[1950]]}
        if delta > 0:
            result["passed"] = False
            result["reasons"].append("market probability regression: " + name)
    result["valorant_cohorts"] = []
    for group, values in sorted(cohort_diffs.items(), key=lambda x: str(x[0])):
        dw, ds = (sum(v[i] for v in values) / len(values) for i in (0, 1))
        result["valorant_cohorts"].append({"group": list(group), "n": len(values), "winner_delta": dw, "exact_score_delta": ds})
        if dw < 0 or ds < 0:
            result["passed"] = False
            result["reasons"].append("Valorant cohort regression: " + str(group))
    result["decision"] = "eligible-for-review" if result["passed"] else "experiment-only"
    result["prediction_availability"] = {v: evaluate(list(items.values()))["prediction_availability"] for v, items in versions.items()}
    if result["prediction_availability"][challenger]["value"] < result["prediction_availability"][baseline]["value"]:
        result["passed"] = False
        result["decision"] = "experiment-only"
        result["reasons"].append("candidate prediction availability decreased")
    result["production_change"] = False
    return result


def walk_forward(payload, registry):
    targets = payload["targets"]
    if not targets or len({r["event"]["event_id"] for r in targets}) != len(targets):
        raise ValueError("one prespecified snapshot per target event required")
    records, fits = [], []
    candidate_version = None
    for target in sorted(targets, key=lambda t: instant(t["event"]["data_cutoff"])):
        event = copy.deepcopy(target["event"])
        event.pop("forecast_id", None)
        event.update(eligibility="historical_replay", created_at=datetime.now(timezone.utc).isoformat())
        outcome = target.get("outcome", {})
        allowed = {"actual_score", "result_status", "result_source_url", "result_observed_at"}
        if set(outcome) - allowed:
            raise ValueError("unsupported outcome fields")
        if outcome.get("result_status") == "final" and (not outcome.get("result_source_url") or not outcome.get("result_observed_at")):
            raise ValueError("final outcomes require provenance")
        for variant in ("control", "candidate"):
            # Variant identity is fixed even if an input cannot be modeled.
            from .strength import settings
            from . import VERSION
            version = "valorant-challenger-v2.0" if variant == "control" else VERSION + "-" + digest(settings(payload.get("config")))[:10]
            if variant == "candidate":
                candidate_version = version
            try:
                if instant(event["data_cutoff"]) >= instant(event.get("actual_start") or event["scheduled_start"]):
                    raise ValueError("pre-match cutoff must precede start")
                if variant == "control":
                    rows, _ = history(payload["history"], event["data_cutoff"])
                    m = old_train(rows, "valorant", event["data_cutoff"], "challenger")
                    forecast = old_forecast(m, event)
                else:
                    m = train(payload["history"], event["data_cutoff"], payload.get("config"), registry)
                    forecast = predict(m, event)
                fits.append({"event_id": event["event_id"], "variant": variant, "model_hash": digest(m), "training_ids": m["training_event_ids"]})
            except (ValueError, KeyError, TypeError) as exc:
                forecast = {k: event[k] for k in ("event_id", "sport", "competition", "snapshot", "data_cutoff", "created_at", "scheduled_start", "participants", "best_of")}
                forecast.update(model_version=version, status="unmodeled", eligibility="historical_replay", exclusion_reason=str(exc))
            forecast.update(outcome)
            forecast["evaluation_cohort"] = target.get("cohort", {})
            records.append(forecast)
    return {"experiment_hash": digest(payload), "records": records, "fits": fits,
            "evaluation": evaluate(records), "comparison": compare(records, "valorant-challenger-v2.0", candidate_version),
            "status": "experiment-only", "production_change": False,
            "note": "Fixed configuration replay; not prospective evidence. Examined development targets are not an untouched holdout."}
