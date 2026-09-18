#!/usr/bin/env python3
"""Audit the shared CS v2 model; ablations are diagnostics, never new forecasts."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.forecast.core import derive, digest
from shared.forecast.models import history_before, predict, train


def audit(model, event, history, claims=None):
    if model.get("model_version") not in {"cs-baseline-v2.0", "cs-challenger-v2.0"}:
        raise ValueError("unsupported model; audit its actual implementation separately")
    if model.get("feature_model"):
        raise ValueError("feature model needs its own input-mapping audit")
    rows = history_before(history, model["trained_as_of"], "cs")
    rebuilt = train(history, "cs", model["trained_as_of"], model["variant"])
    if digest(rebuilt) != digest(model):
        raise ValueError("model does not replay from supplied history and current engine")
    result = predict(model, event)
    maps = sorted({m for s in event.get("veto_scenarios", []) for m in s["maps"]})
    by_map = {}
    for name in maps:
        e = copy.deepcopy(event)
        e["best_of"] = 1
        e["veto_scenarios"] = [{**event["veto_scenarios"][0], "maps": [name]}]
        by_map[name] = {
            "a_probability": predict(model, e)["score_distribution"]["1-0"],
            "counts": {t: model["map_counts"].get(t + "::" + name, [0., 0.])
                       for t in event["participants"]},
            "meaning": "standalone pre-series marginal; not a live/reached-map forecast",
        }
    aliases = []
    for i, a in enumerate(maps):
        for b in maps[i + 1:]:
            if abs(by_map[a]["a_probability"] - by_map[b]["a_probability"]) < 1e-12:
                aliases.append([a, b])

    # One switch at a time, with original ratings, cutoff, maps and all other inputs fixed.
    variants = {"original": copy.deepcopy(model),
                "without_shared_state": copy.deepcopy(model),
                "without_map_offsets": copy.deepcopy(model)}
    variants["without_shared_state"]["shared_state_sigma"] = 0.
    variants["without_map_offsets"]["map_counts"] = {}
    ablations = {}
    for name, candidate in variants.items():
        scores = predict(candidate, event)["score_distribution"]
        ablations[name] = {"score_distribution": scores, "derived": derive(scores)}

    facts = {
        "rating_update_unit": "one_update_per_series_using_map_share",
        "rating_opponent_adjusted": True,
        "rating_initialization": "all_teams_1500_no_external_prior",
        "map_offsets_used": model["variant"] == "challenger" and bool(maps),
        "map_offsets_opponent_adjusted": False,
        "round_scores_used": False,
        "side_or_economy_features_used": False,
        "map_counts_time_weighted": False,
        "shared_state_fit_uses_map_offsets": False,
        "map_prior_pseudocounts": [15, 15],
    }
    mismatches = [{"claim": k, "asserted": v, "actual": facts.get(k)}
                  for k, v in (claims or {}).items() if k not in facts or v != facts[k]]
    formats = Counter(str(r.get("best_of", "unknown")) for r in rows)
    completed = Counter(r["completed_at"] for r in rows)
    available = Counter(r["available_at"] for r in rows)
    losses = {float(k): v for k, v in model.get("shared_state_training_losses", {}).items()}
    sigma = model.get("shared_state_sigma", 0.)
    flags = []
    if rows and len({r.get("competition") for r in rows}) == 1:
        flags.append("single_competition_cold_start")
    if sigma and not formats.get(str(event["best_of"])):
        flags.append("shared_state_target_format_unseen")
    if losses and sigma == max(losses) and sigma > 0:
        flags.append("shared_state_grid_upper_boundary")
    if len(completed) == 1 and len(rows) > 1:
        flags.append("completion_times_collapsed_check_upper_bound_semantics")
    if aliases:
        flags.append("different_maps_same_model_probability")
    if any(min(v[1] for v in m["counts"].values()) == 0 for m in by_map.values()):
        flags.append("target_map_has_zero_team_sample")
    return {
        "schema_version": 1, "audit_passed": not mismatches,
        "purpose": "input_mapping_and_isolated_sensitivity",
        "production_change": False, "accuracy_improvement_established": False,
        "model_hash": digest(model), "event_hash": digest(event), "history_hash": digest(history),
        "engine_sha256": hashlib.sha256((ROOT / "shared/forecast/models.py").read_bytes()).hexdigest(),
        "model_version": model["model_version"], "facts": facts,
        "claim_mismatches": mismatches, "flags": flags,
        "training": {"series_n": len(rows), "maps_n": sum(len(r.get("games", [])) for r in rows),
                     "best_of_counts": dict(formats), "completed_time_count": len(completed),
                     "available_time_count": len(available), "shared_state_sigma": sigma,
                     "shared_state_training_losses": losses},
        "maps": by_map, "same_probability_pairs": aliases,
        "original_distribution": result["score_distribution"], "ablations": ablations,
        "limitations": ["Fixed-input ablations are not paired walk-forward evidence.",
                        "Flags require evidence review; they do not authorize probability overrides.",
                        "Retrieval upper bounds cannot be backdated to build historical holdouts."],
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("model", "event", "history", "output"):
        p.add_argument("--" + name, required=True, type=Path)
    p.add_argument("--claims", type=Path, help="optional asserted input-mapping facts")
    args = p.parse_args()
    read = lambda path: json.loads(path.read_text())
    result = audit(read(args.model), read(args.event), read(args.history),
                   read(args.claims) if args.claims else None)
    encoded = json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    if args.output.exists() and args.output.read_text() != encoded:
        raise ValueError("use a new output path; existing audit differs")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(encoded)
    print(json.dumps({"audit_passed": result["audit_passed"], "flags": result["flags"],
                      "output": str(args.output)}, ensure_ascii=False))
    return 0 if result["audit_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
