"""Read-only feature-use audit; supplied context is not a fitted series effect."""
from __future__ import annotations

import json
from collections import defaultdict

from shared.forecast.core import canonical, digest, validate
from .series import validate_forecast


FAMILIES = ("team", "map", "patch", "roster", "agents", "side")


def families(trace, field):
    return {json.loads(key)[0] for key in trace.get(field, {})}


def supplied(mp, ctx):
    return {
        "team": True, "map": mp is not None, "patch": bool(ctx.get("patch")),
        "roster": bool(ctx.get("lineups")), "agents": bool(ctx.get("agents")),
        "side": ctx.get("a_start_side") in ("attack", "defense"),
    }


def audit_model_use(record, model=None, event=None):
    validate(record)
    if record["sport"] != "valorant" or record["scope"] != "full-series":
        raise ValueError("audit series separately from conditional-map forecasts")
    if (model is None) != (event is None):
        raise ValueError("model and event must be supplied together")
    detail = record.get("valorant")
    if detail:
        validate_forecast(record, model, event)
    elif model is not None:
        from shared.forecast.cli import forecast
        if canonical(record) != canonical(forecast(model, event)):
            raise ValueError("forecast differs from model/input replay")

    scenarios = [s for s in record.get("scenarios", []) if s["weight"] > 0]
    resolved = sum(s["weight"] for s in scenarios if s.get("maps"))
    unresolved = sum(s["weight"] for s in scenarios
                     if s.get("order_id", s["id"]).split("/")[0] == "unresolved-map-order")
    if resolved + unresolved > 1 + 1e-9:
        raise ValueError("map-order audit has overlapping scenario mass")
    traces = (detail or {}).get("feature_audit", {})
    primary_keys, present = set(), set()
    maps = defaultdict(lambda: {"selected_scenario_weight": 0.,
                               "input_weight": {k: 0. for k in FAMILIES},
                               "fitted_families": set(), "unseen_families": set()})
    if detail:
        for scenario in scenarios:
            pairs = list(zip(scenario["maps"], scenario["contexts"])) or [(None, {})]
            for mp, ctx in pairs:
                key = digest([mp, ctx])[:20]
                if key not in traces:
                    raise ValueError("primary context lacks a feature-use trace")
                trace = traces[key]
                if trace.get("map") != mp or canonical(trace.get("context")) != canonical(ctx):
                    raise ValueError("feature-use trace context differs from primary scenario")
                primary_keys.add(key)
                inputs = supplied(mp, ctx)
                present.update(k for k, value in inputs.items() if value)
                if mp is not None:
                    row = maps[mp]
                    row["selected_scenario_weight"] += scenario["weight"]
                    for k, value in inputs.items():
                        row["input_weight"][k] += scenario["weight"] * value
                    row["fitted_families"].update(families(trace, "used"))
                    row["unseen_families"].update(families(trace, "unseen"))

    supplemental = set(traces) - primary_keys
    features = {}
    for family in FAMILIES:
        used = sum(family in families(traces[key], "used") for key in primary_keys)
        extra = sum(family in families(traces[key], "used") for key in supplemental)
        if detail:
            status = "fitted_input" if used else ("input_only" if family in present else "not_modeled")
        else:
            # v2 lacks fitted-feature traces; only explicit unresolved contexts are known.
            status = "not_modeled" if unresolved >= 1 - 1e-9 and family != "team" else "unknown"
        features[family] = {"primary_status": status, "primary_fitted_trace_count": used if detail else None,
                            "supplemental_only_fitted_trace_count": extra if detail else None}
    for row in maps.values():
        for key in ("fitted_families", "unseen_families"):
            row[key] = sorted(row[key])
    return {
        "forecast_id": record["forecast_id"], "forecast_hash": digest(record),
        "model_version": record["model_version"], "data_cutoff": record["data_cutoff"],
        "full_model_replay": model is not None, "changes_forecast": False,
        "map_order": {"resolved_weight": resolved, "unresolved_weight": unresolved,
                      "unknown_weight": max(0., 1 - resolved - unresolved)},
        "features": features, "primary_contexts_by_map": dict(sorted(maps.items())),
        "limitations": [
            "fitted_input means a fitted parameter was addressed, not that its coefficient is nonzero or improves prediction.",
            "Input weights describe selected pre-match scenarios, not the probability a map is played.",
            "Supplemental-only traces do not establish use in the series score distribution.",
            "Context presence does not verify the real lineup/agents/side; compare those with sourced facts separately.",
            "v2 snapshots without traces remain unknown except for explicitly unresolved map contexts.",
        ],
    }
