#!/usr/bin/env python3
"""Offline, immutable LoL strength experiment. No prices or publication side effects.

The single candidate fits opponent strengths jointly instead of one-pass Elo.
Its coefficients, history window and output status are never selected by outcomes.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.forecast.cli import forecast as baseline_forecast, read, write
from shared.forecast.core import derive, digest, instant, validate
from shared.forecast.models import constant_tree, history_before, train as elo_train

VERSION = "lol-joint-strength-v1"
PARAMETERS = {"ridge": 1.0, "series_weight": "one", "half_life_days": None,
              "target": "map_share", "distribution": "constant_game_rate"}
MARKET_KEYS = {"odds", "decimal_odds", "market_odds", "market_data", "price_comparisons"}


def reject_market(value):
    if isinstance(value, dict):
        if MARKET_KEYS.intersection(value) or value.get("kind") == "market":
            raise ValueError("market data is not a strength-model input")
        for item in value.values():
            reject_market(item)
    elif isinstance(value, list):
        for item in value:
            reject_market(item)


def logistic(value):
    if value >= 0:
        return 1 / (1 + math.exp(-value))
    exp = math.exp(value)
    return exp / (1 + exp)


def solve(matrix, vector):
    """Small positive-definite Newton system, without a scientific-stack dependency."""
    a = [list(row) + [value] for row, value in zip(matrix, vector)]
    n = len(a)
    for col in range(n):
        pivot = max(range(col, n), key=lambda i: abs(a[i][col]))
        a[col], a[pivot] = a[pivot], a[col]
        if abs(a[col][col]) < 1e-14:
            raise ValueError("singular strength fit")
        divisor = a[col][col]
        a[col] = [x / divisor for x in a[col]]
        for row in range(n):
            if row == col:
                continue
            scale = a[row][col]
            a[row] = [x - scale * y for x, y in zip(a[row], a[col])]
    return [row[-1] for row in a]


def objective(strengths, observations):
    ridge = PARAMETERS["ridge"]
    n = len(strengths)
    loss = ridge * sum(x*x for x in strengths) / 2
    gradient = [ridge*x for x in strengths]
    hessian = [[ridge if i == j else 0. for j in range(n)] for i in range(n)]
    for terms, target in observations:
        x = sum(strengths[i]*coefficient for i, coefficient in terms)
        p = logistic(x)
        loss += max(x, 0) + math.log1p(math.exp(-abs(x))) - target*x
        for i, coefficient in terms:
            gradient[i] += (p-target)*coefficient
            for j, other in terms:
                hessian[i][j] += p*(1-p)*coefficient*other
    return loss, gradient, hessian


def fit(history, cutoff, method="joint"):
    reject_market(history)
    if method not in {"joint", "opponent_zero_ablation"}:
        raise ValueError("unknown fixed experiment method")
    rows = history_before(history, cutoff, "lol")
    if not rows:
        raise ValueError("no eligible pre-cutoff LoL series")
    teams = sorted({t for r in rows for t in r["participants"]})
    indices = {team: i for i, team in enumerate(teams)}
    observations, counts = [], {t: 0 for t in teams}
    adjacency = {t: set() for t in teams}
    for row in rows:
        bo = row.get("best_of")
        if isinstance(bo, bool) or bo not in (1, 2, 3, 5):
            raise ValueError("history requires an explicit supported best_of")
        a, b = row["participants"]
        x, y = row["score"]
        if f"{int(x)}-{int(y)}" not in constant_tree(bo, .5):
            raise ValueError("incomplete or impossible historical series result")
        target = x/(x+y)
        if method == "joint":
            observations.append(([(indices[a], 1.), (indices[b], -1.)], target))
        else:
            # Each team's same ridge likelihood, with its opponent fixed at zero.
            observations.extend([([(indices[a], 1.)], target), ([(indices[b], 1.)], 1-target)])
        counts[a] += 1
        counts[b] += 1
        adjacency[a].add(b)
        adjacency[b].add(a)
    strengths = [0.]*len(teams)
    for iteration in range(100):
        loss, gradient, hessian = objective(strengths, observations)
        if max(abs(x) for x in gradient) < 1e-9:
            break
        delta = solve(hessian, gradient)
        scale = 1.
        while scale >= 2**-24:
            candidate = [x-scale*d for x, d in zip(strengths, delta)]
            if objective(candidate, observations)[0] <= loss + 1e-12:
                strengths = candidate
                break
            scale /= 2
        else:
            raise ValueError("strength fit line search failed")
    loss, gradient, _ = objective(strengths, observations)
    if max(abs(x) for x in gradient) >= 1e-8:
        raise ValueError("strength fit did not converge")
    return dict(schema_version="1.0", sport="lol", status="experiment",
                model_version=VERSION if method == "joint" else VERSION+"-opponent-zero",
                method=method, parameters=copy.deepcopy(PARAMETERS), trained_as_of=cutoff,
                parameter_version=digest(dict(method=method, **PARAMETERS)),
                training_hash=digest(rows), training_event_ids=[r["event_id"] for r in rows],
                n=len(rows), strengths=dict(zip(teams, strengths)), team_series_counts=counts,
                opponents={t: sorted(v) for t, v in adjacency.items()},
                optimization=dict(iterations=iteration+1, objective=loss,
                                  max_abs_gradient=max(abs(x) for x in gradient)))


def build_forecast(model, event, created_at, eligibility):
    reject_market(event)
    if event.get("sport") != "lol" or event.get("best_of") not in (3, 5):
        raise ValueError("this experiment supports pre-draft LoL BO3/BO5 only")
    if event.get("scope") not in {"series", "full-series", "full-game"} or not event.get("snapshot", "").startswith(("pre-draft", "pre-match")):
        raise ValueError("this experiment requires a pre-draft series snapshot")
    if instant(model["trained_as_of"]) != instant(event["data_cutoff"]):
        raise ValueError("model and event must use exactly the same cutoff")
    if event["event_id"] in model["training_event_ids"]:
        raise ValueError("target event leaked into training")
    a, b = event["participants"]
    if any(t not in model["strengths"] for t in (a, b)):
        raise ValueError("both target teams need observed training series")
    seen, queue = {a}, [a]
    for team in queue:
        for opponent in model["opponents"][team]:
            if opponent not in seen:
                seen.add(opponent)
                queue.append(opponent)
    if b not in seen:
        raise ValueError("target teams lack a connected opponent comparison")
    p = logistic(model["strengths"][a]-model["strengths"][b])
    fields = ("event_id", "sport", "competition", "snapshot", "data_cutoff", "scheduled_start",
              "participants", "evidence", "confidence", "scope", "best_of", "actual_start")
    record = {k: copy.deepcopy(event[k]) for k in fields if k in event}
    record.update(schema_version="2.0", probability_unit="fraction", created_at=created_at,
                  model_version=model["model_version"], parameter_version=model["parameter_version"],
                  model_artifact_hash=digest(model), status="experiment", eligibility=eligibility,
                  recommendation_eligible=False, calibration_status="not_empirically_calibrated",
                  parameter_source="regularized_fit_on_frozen_series", score_distribution=constant_tree(event["best_of"], p),
                  missing_data=list(event.get("missing_data", []))+[
                      "Joint strength candidate has no verified forward improvement.",
                      "Same original history window; no fitted roster, draft or Fearless dependence effects.",
                      "BO5 length retains the constant-game-rate structural limit."],
                  fitted_game_probability=p)
    record["derived"] = derive(record["score_distribution"])
    record["forecast_id"] = "f-"+digest(record)[:32]
    validate(record)
    return record


def pair(control, history, *, replay_mode=False, now=None):
    """now is injectable for offline tests; CLI always reads the actual UTC clock."""
    reject_market(control)
    validate(control)
    if "actual_score" in control or control.get("result_status") == "final":
        raise ValueError("control must be the original unevaluated forecast")
    if control["model_version"].startswith("lol-analyst-scenarios-"):
        from analyst_forecast import replay
        replay(control)
        baseline = control["generation_input"]["baseline"]
    elif control["model_version"] == "lol-baseline-v2.0":
        baseline = control
    else:
        raise ValueError("unsupported control; preserve it and record unavailable challenger")
    stamp = now or datetime.now(timezone.utc).isoformat()
    if not replay_mode and control["eligibility"] != "prospective":
        raise ValueError("forward pairing requires a prospective control")
    if instant(stamp) < instant(control["created_at"]):
        raise ValueError("challenger cannot predate its control")
    if not replay_mode and instant(stamp) >= instant(control.get("actual_start") or control["scheduled_start"]):
        raise ValueError("post-start computation requires --replay; it is not a forward sample")
    eligible = history_before(history, control["data_cutoff"], "lol")
    event = {k: copy.deepcopy(baseline[k]) for k in (
        "event_id", "sport", "competition", "snapshot", "created_at", "data_cutoff", "scheduled_start",
        "participants", "evidence", "confidence", "scope", "best_of", "actual_start", "eligibility") if k in baseline}
    retrained = elo_train(history, "lol", control["data_cutoff"])
    reproduced = baseline_forecast(retrained, event)
    for key, value in baseline["score_distribution"].items():
        if abs(reproduced["score_distribution"][key]-value) > 1e-10:
            raise ValueError("frozen history does not reproduce the original score baseline")
    if retrained["training_hash"] != digest(eligible):
        raise ValueError("training selection differs between arms")
    eligibility = "historical_replay" if replay_mode else "prospective"
    model = fit(eligible, event["data_cutoff"])
    candidate = build_forecast(model, control, stamp, eligibility)
    ablation_model = fit(eligible, event["data_cutoff"], "opponent_zero_ablation")
    ablation = build_forecast(ablation_model, control, stamp, eligibility)
    script_paths = [Path(__file__).resolve(), ROOT/'shared/forecast/core.py', ROOT/'shared/forecast/models.py']
    audit = dict(schema_version="lol-strength-pair-v1", created_at=stamp,
                 event_id=control["event_id"], data_cutoff=control["data_cutoff"],
                 mode="development_replay" if replay_mode else "prospective_shadow",
                 forward_sample=not replay_mode, production_change=False,
                 control_forecast_id=control["forecast_id"], control_hash=digest(control),
                 baseline_forecast_id=baseline["forecast_id"], baseline_hash=digest(baseline),
                 candidate_forecast_id=candidate["forecast_id"], candidate_hash=digest(candidate),
                 eligible_history_hash=digest(eligible), supplied_history_hash=digest(history),
                 included_series=len(eligible), excluded_series=len(history)-len(eligible),
                 evidence_hash=digest(control["evidence"]), baseline_replay_passed=True,
                 code_hashes={str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in script_paths},
                 probabilities={"control": control["derived"]["winner_probabilities"],
                                "baseline": baseline["derived"]["winner_probabilities"],
                                "candidate": candidate["derived"]["winner_probabilities"],
                                "opponent_zero_ablation": ablation["derived"]["winner_probabilities"]})
    return {"control.json": copy.deepcopy(control), "baseline.json": copy.deepcopy(baseline),
            "history.json": copy.deepcopy(eligible), "history-input.json": copy.deepcopy(history),
            "challenger.json": candidate, "model.json": model,
            "ablation.json": ablation, "ablation-model.json": ablation_model, "pair-audit.json": audit}


def verify_pair(directory):
    directory = Path(directory)
    audit = read(str(directory/'pair-audit.json'))
    if audit.get("mode") not in {"development_replay", "prospective_shadow"}:
        raise ValueError("invalid pair mode")
    if audit.get("forward_sample") is not (audit["mode"] == "prospective_shadow"):
        raise ValueError("forward sample flag disagrees with pair mode")
    rebuilt = pair(read(str(directory/'control.json')), read(str(directory/'history-input.json')),
                   replay_mode=audit["mode"] == "development_replay", now=audit["created_at"])
    for name in ("control.json", "baseline.json", "history.json", "challenger.json", "model.json", "ablation.json", "ablation-model.json"):
        if digest(read(str(directory/name))) != digest(rebuilt[name]):
            raise ValueError(f"pair replay differs: {name}")
    for field in ("control_hash", "baseline_hash", "candidate_hash", "eligible_history_hash", "supplied_history_hash",
                  "included_series", "excluded_series", "evidence_hash", "code_hashes", "probabilities"):
        if audit[field] != rebuilt["pair-audit.json"][field]:
            raise ValueError(f"pair provenance differs: {field}")
    return dict(valid=True, forecast_id=audit["candidate_forecast_id"], forward_sample=audit["forward_sample"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("pair")
    command.add_argument("--control", required=True)
    command.add_argument("--history", required=True)
    command.add_argument("--output-dir", required=True)
    command.add_argument("--replay", action="store_true")
    command = commands.add_parser("verify")
    command.add_argument("directory")
    args = parser.parse_args()
    try:
        if args.command == "verify":
            result = verify_pair(args.directory)
        else:
            outputs = pair(read(args.control), read(args.history), replay_mode=args.replay)
            destination = Path(args.output_dir)
            # Check all existing names before writing any file.
            for name, value in outputs.items():
                path = destination/name
                if path.exists() and digest(read(str(path))) != digest(value):
                    raise ValueError(f"immutable experiment directory already contains a different {name}")
            for name, value in outputs.items():
                write(str(destination/name), value)
            result = outputs["pair-audit.json"]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print(f"strength experiment error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
