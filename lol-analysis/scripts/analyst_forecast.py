#!/usr/bin/env python3
"""Build/replay explicitly subjective LoL scenarios, never a production model.

Offline only. Evidence supports mechanisms, not empirically fitted probabilities.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.forecast.core import derive, digest, instant, mixture, number, series_tree, validate
from shared.forecast.cli import write

VERSION = "lol-analyst-scenarios-v1"
KINDS = {"match_detail", "lineup", "patch", "schedule", "context"}


def nonempty(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty text")
    return value


def exact_fields(value, required, label):
    if not isinstance(value, dict) or set(value) != set(required):
        raise ValueError(f"{label} requires exactly: {', '.join(required)}")


def game_tree(best_of, probabilities):
    if not isinstance(probabilities, list) or len(probabilities) != best_of:
        raise ValueError("one first-team probability per possible game required")
    for p in probabilities:
        number(p)
        if p in (0, 1):
            raise ValueError("subjective game probabilities cannot assert certainty")
    nodes = {}

    def visit(a, b, path):
        if (a+b == 2 if best_of == 2 else max(a, b) == best_of//2+1):
            return
        nodes[path or "ROOT"] = probabilities[a+b]
        visit(a+1, b, path+"W")
        visit(a, b+1, path+"L")

    visit(0, 0, "")
    return nodes


def build(payload):
    exact_fields(payload, ("event", "baseline", "judgment"), "input")
    event, baseline, judgment = (copy.deepcopy(payload[k]) for k in ("event", "baseline", "judgment"))
    validate(baseline)
    if baseline["sport"] != "lol" or baseline["status"] != "baseline":
        raise ValueError("reference must be a canonical LoL baseline")
    for key in ("event_id", "sport", "participants", "data_cutoff", "best_of", "scheduled_start", "competition", "scope"):
        if event[key] != baseline[key]:
            raise ValueError("baseline/event mismatch: " + key)
    if event.get("eligibility", "prospective") != "prospective" or baseline["eligibility"] != "prospective":
        raise ValueError("analyst estimates require prospective inputs; do not reconstruct after results")
    exact_fields(judgment, ("locked_at", "baseline_departure", "counterargument", "scenarios"), "judgment")
    for key in ("baseline_departure", "counterargument"):
        nonempty(judgment[key], key)
    cutoff, locked, created = (instant(t) for t in (event["data_cutoff"], judgment["locked_at"], event["created_at"]))
    if not cutoff <= locked <= created or instant(baseline["created_at"]) > locked:
        raise ValueError("baseline and evidence must precede judgment lock and forecast creation")
    # Explicitly whitelist event fields: market data / hand-filled outcomes are not parameters.
    event_fields = {"event_id", "sport", "competition", "snapshot", "created_at", "data_cutoff", "scheduled_start",
                    "participants", "scope", "evidence", "confidence", "best_of", "actual_start", "eligibility",
                    "missing_data", "key_points", "risks", "analysis_sections"}
    if set(event) - event_fields:
        raise ValueError("unsupported event fields (market/outcome inputs are not permitted)")
    evidence = {e["id"]: e for e in event["evidence"]}
    participants = set(event["participants"])
    for e in evidence.values():
        if instant(e["retrieved_at"]) > locked:
            raise ValueError("evidence must be retrieved before judgment lock")
        if e.get("kind") not in KINDS:
            raise ValueError("evidence must have a non-market kind")
        teams = e.get("teams")
        if not isinstance(teams, list) or not set(teams) <= participants or len(set(teams)) != len(teams):
            raise ValueError("evidence teams must name covered event participants")

    def refs(values):
        if not isinstance(values, list) or not values or any(not isinstance(v, str) for v in values):
            raise ValueError("support and counterevidence references must be nonempty ID lists")
        if len(set(values)) != len(values) or not set(values) <= evidence.keys():
            raise ValueError("duplicate or unknown evidence reference")
        return [evidence[v] for v in values]

    inputs = judgment["scenarios"]
    if not isinstance(inputs, list) or not inputs:
        raise ValueError("at least one evidence-backed scenario required")
    scenarios, covered, ids = [], set(), set()
    for s in inputs:
        exact_fields(s, ("id", "weight", "weight_reason", "mechanism", "evidence_ids", "counterevidence_ids",
                         "game_probabilities", "probabilities_reason", "invalidation"), "scenario")
        for key in ("id", "weight_reason", "mechanism", "probabilities_reason", "invalidation"):
            nonempty(s[key], key)
        if s["id"] in ids:
            raise ValueError("duplicate scenario ID")
        ids.add(s["id"])
        if number(s["weight"]) <= 0:
            raise ValueError("scenario weights must be positive")
        support, counter = refs(s["evidence_ids"]), refs(s["counterevidence_ids"])
        if not any(e["kind"] == "match_detail" for e in support):
            raise ValueError("each scenario needs actual match-detail support")
        for e in support + counter:
            if e["kind"] == "match_detail":
                covered.update(e["teams"])
        nodes = game_tree(event["best_of"], s["game_probabilities"])
        scenarios.append(dict(id=s["id"], weight=s["weight"], nodes=nodes,
                              score_distribution=series_tree(event["best_of"], nodes)))
    if covered != participants:
        raise ValueError("referenced match-detail evidence must cover both teams")
    scores = mixture(scenarios)
    out = {k: v for k, v in event.items() if k in event_fields}
    out.update(schema_version="2.0", probability_unit="fraction", model_version=VERSION,
               parameter_version=digest(judgment), model_artifact_hash=digest(payload),
               status="experiment", eligibility="prospective", recommendation_eligible=False,
               parameter_source="analyst_elicited", calibration_status="not_empirically_calibrated",
               generation_input=copy.deepcopy(payload), scenarios=scenarios,
               score_distribution=scores, derived=derive(scores))
    out["missing_data"] = event.get("missing_data", []) + [
        "情境權重與單局率為分析者估計，尚無實證校準；證據引用不證明參數唯一正確。",
        "情境內依局數給定勝率，沒有依具體W/L歷史建模局間學習。"]
    out["analysis_sections"] = event.get("analysis_sections", []) + [
        {"heading": "分析者情境與比分基準的差異",
         "markdown": judgment["baseline_departure"] + "\n\n最強反證：" + judgment["counterargument"]}]
    for s in inputs:
        links = "、".join(f"[{ref}]({evidence[ref]['url']})" for ref in s["evidence_ids"])
        counters = "、".join(f"[{ref}]({evidence[ref]['url']})" for ref in s["counterevidence_ids"])
        games = "、".join(f"G{i+1} {p*100:.1f}%" for i, p in enumerate(s["game_probabilities"]))
        out["analysis_sections"].append({"heading": "情境："+s["id"], "markdown":
            f"{s['mechanism']}\n\n分析者權重 {s['weight']*100:.1f}%：{s['weight_reason']}\n\n"
            f"第一隊單局率：{games}。參數理由：{s['probabilities_reason']}\n\n"
            f"支持：{links}；反證：{counters}。失效條件：{s['invalidation']}"})
    out["baseline_comparison"] = dict(forecast_id=baseline["forecast_id"], sha256=digest(baseline),
        derived=derive(baseline["score_distribution"]),
        delta_first_team=derive(scores)["winner_probabilities"]["a"] - derive(baseline["score_distribution"])["winner_probabilities"]["a"])
    out["forecast_id"] = "f-"+digest(out)[:32]
    validate(out)
    return out


def replay(record):
    validate(record)
    if record.get("model_version") != VERSION:
        raise ValueError("not a LoL analyst-scenarios forecast")
    expected = build(record["generation_input"])
    if digest(expected) != digest(record):
        raise ValueError("forecast differs from replayed input; preserve locked artifacts")
    return {"valid": True, "replay_passed": True, "sha256": digest(record),
            "status": "experiment", "calibration_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("build", "validate"))
    parser.add_argument("input", type=Path)
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        payload = json.loads(args.input.read_text(encoding="utf8"))
        result = build(payload) if args.command == "build" else replay(payload)
        if args.output:
            write(args.output, result)
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    except (ValueError, KeyError, TypeError, OSError) as exc:
        parser.exit(2, f"analyst forecast error: {exc}\n")


if __name__ == "__main__":
    main()
