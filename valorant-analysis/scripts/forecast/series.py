"""One joint tree supplies series outcomes and played-map conditional probabilities."""
from __future__ import annotations

import copy
import json
from collections import defaultdict

from shared.forecast.core import canonical, derive, digest, instant, mixture, number, series_tree, validate
from shared.forecast.models import latent_games
from . import VERSION
from .data import context, event_input
from .strength import map_probability
from .veto import MissingVetoEvidence, paths


def tree(probabilities, sigma, best_of):
    if best_of not in (1, 3, 5) or len(probabilities) != best_of:
        raise ValueError("one map probability per possible game required")
    for probability in probabilities:
        number(probability)
    number(sigma, 0, 10)
    states = [[p] * 3 if p in (0, 1) else [q for _, q in latent_games(p, sigma)] for p in probabilities]
    nodes, played, won = {}, [0.] * best_of, [0.] * best_of
    def walk(a, b, key, masses):
        if max(a, b) == best_of // 2 + 1:
            return
        i, reach = a + b, sum(masses)
        success = sum(m * q for m, q in zip(masses, states[i]))
        probability = success / reach if reach else probabilities[i]
        nodes[key or "ROOT"] = probability
        played[i] += reach
        won[i] += success
        walk(a + 1, b, key + "W", [m * q for m, q in zip(masses, states[i])])
        walk(a, b + 1, key + "L", [m * (1 - q) for m, q in zip(masses, states[i])])
    walk(0, 0, "", [1 / 6, 2 / 3, 1 / 6])
    return {"nodes": nodes, "score_distribution": series_tree(best_of, nodes), "played": played, "won": won}


def predict(model, event):
    event_input(event)
    if model.get("engine_version") != VERSION or model.get("status") != "experiment":
        raise ValueError("expected an experimental Valorant v3 model")
    if instant(model["trained_as_of"]) > instant(event["data_cutoff"]):
        raise ValueError("model trained after forecast cutoff")
    if event["event_id"] in model["training_event_ids"]:
        raise ValueError("target event leaked into training")
    bo, pool, teams = event["best_of"], event["map_pool"], event["participants"]
    missing = list(event.get("missing_data", []))
    missing.append("Valorant v3 實驗模型；尚無配對樣本外改善證據。")
    if event.get("confidence") is None:
        missing.append("未提供逐場五項證據品質評分；信心度為 N/A。")
    try:
        orders, veto_audit = paths(model, event)
    except MissingVetoEvidence as exc:
        if event["snapshot"] == "post-veto":
            raise ValueError("post-veto cannot fall back to unresolved map order") from exc
        orders = [{"id": "unresolved-map-order", "weight": 1., "maps": [], "pick_owners": []}]
        veto_audit = {"mode": "unresolved", "reason": str(exc), "full_action_coverage": "not_modeled"}
        missing.append(str(exc) + "；系列僅用隊伍層效果，逐圖另為未整合的條件估計。")
    missing.extend(veto_audit.get("limitations", []))
    rosters = event.get("roster_scenarios") or [{"id": "given-context", "weight": 1., "contexts_by_map": {}}]
    lookup, feature_audit = {}, {}
    def estimate(mp, ctx):
        key = canonical([mp, ctx])
        if key not in lookup:
            p, trace = map_probability(model, teams, mp, ctx)
            lookup[key] = p
            feature_audit[digest([mp, ctx])[:20]] = {"map": mp, "context": ctx, "p_a": p, **trace}
        return lookup[key]
    def ctx_for(roster, mp):
        ctx = dict(event.get("contexts_by_map", {}).get(mp, {}))
        ctx.update(roster.get("contexts_by_map", {}).get(mp, {}))
        return context(ctx)
    totals = {mp: {"selected": 0., "played": 0., "won": 0.} for mp in pool}
    scenarios = []
    for roster in rosters:
        for order in orders:
            weight = roster["weight"] * order["weight"]
            if not weight:
                continue
            maps = order["maps"]
            contexts = [ctx_for(roster, mp) for mp in maps]
            ps = [estimate(mp, ctx) for mp, ctx in zip(maps, contexts)] if maps else [estimate(None, {})] * bo
            result = tree(ps, model["shared_state_sigma"], bo)
            scenarios.append({"id": order["id"] + "/" + roster["id"], "weight": weight,
                              "order_id": order["id"], "roster_id": roster["id"], "maps": maps,
                              "pick_owners": order["pick_owners"], "contexts": contexts,
                              "map_probabilities_before_results": ps,
                              "nodes": result["nodes"], "score_distribution": result["score_distribution"]})
            for i, mp in enumerate(maps):
                totals[mp]["selected"] += weight
                totals[mp]["played"] += weight * result["played"][i]
                totals[mp]["won"] += weight * result["won"][i]
    maps = {}
    for mp in pool:
        t = totals[mp]
        if veto_audit["mode"] == "unresolved":
            p = sum(r["weight"] * estimate(mp, ctx_for(r, mp)) for r in rosters)
            maps[mp] = {"a": p, "b": 1 - p, "selected_probability": None, "played_probability": None,
                        "status": "standalone-unintegrated", "reason": "名單／選邊依輸入假設；未知 veto，未與系列主分布整合。"}
        elif t["played"] > 0:
            p = t["won"] / t["played"]
            maps[mp] = {"a": p, "b": 1 - p, "selected_probability": t["selected"],
                        "played_probability": t["played"], "status": "conditional-on-play",
                        "reason": "同一情境樹，已按走到本圖的機率加權；名單／選邊依輸入假設。"}
        else:
            maps[mp] = {"a": None, "b": None, "selected_probability": t["selected"],
                        "played_probability": 0., "status": "excluded", "reason": "本場已 ban／不會開打。"}
    used_families = {json.loads(k)[0] for a in feature_audit.values() for k in a["used"]}
    for layer in ("map", "patch", "roster", "agents", "side"):
        if layer not in used_families:
            label = {"map": "逐圖", "patch": "版本", "roster": "五人組合", "agents": "特務配置", "side": "開局攻守方"}[layer]
            missing.append(label + "效果在本場沒有可用已擬合輸入；未把研究文字當成數值修正。")
    missing.append("veto 偏好尚未擬合名單／特務交互作用；高維對位與回合經濟未建模。")
    missing.append("pick owner 用於禁選與路徑標記，尚無獨立的選圖方勝率效果。")
    if not model["shared_state_sigma"]:
        missing.append("系列相依性使用獨立控制組；共同狀態未啟用或訓練校準未選中。")
    fields = ("event_id", "sport", "competition", "snapshot", "created_at", "data_cutoff", "scheduled_start",
              "actual_start", "participants", "scope", "best_of", "evidence", "confidence", "key_points", "risks", "analysis_sections")
    out = {k: copy.deepcopy(event[k]) for k in fields if k in event}
    out.setdefault("confidence", None)
    scores = mixture(scenarios)
    out.update(schema_version="2.0", probability_unit="fraction", status="experiment",
               eligibility=event.get("eligibility", "prospective"), recommendation_eligible=False,
               model_version=model["model_version"], parameter_version=model["parameter_version"],
               model_artifact_hash=digest(model), missing_data=list(dict.fromkeys(missing)),
               scenarios=scenarios, score_distribution=scores, derived=derive(scores))
    out["valorant"] = {"engine_version": VERSION, "input_hash": digest(event), "map_pool": pool,
                       "maps": maps, "veto": veto_audit, "feature_audit": feature_audit,
                       "shared_state_sigma": model["shared_state_sigma"],
                       "roster_weight_assumption": "P(roster) × P(veto); roster-dependent veto preferences not fitted",
                       "training_hash": model["training_hash"]}
    out["forecast_id"] = event.get("forecast_id") or "val3-" + digest(out)[:32]
    validate(out)
    return out


def validate_forecast(record, model=None, event=None):
    validate(record)
    detail = record["valorant"]
    if detail["engine_version"] != VERSION or record["status"] != "experiment" or record["recommendation_eligible"]:
        raise ValueError("invalid experimental engine status")
    pool, totals = detail["map_pool"], defaultdict(lambda: [0., 0., 0.])
    if set(detail["maps"]) != set(pool):
        raise ValueError("map display must cover entire event pool")
    for scenario in record["scenarios"]:
        maps = scenario["maps"]
        if detail["veto"]["mode"] != "unresolved" and (len(maps) != record["best_of"] or len(set(maps)) != len(maps) or not set(maps) <= set(pool)):
            raise ValueError("scenario map order is incomplete or outside pool")
        if len(scenario["pick_owners"]) != len(maps) or len(scenario["contexts"]) != len(maps):
            raise ValueError("scenario map context dimensions differ")
        rebuilt = tree(scenario["map_probabilities_before_results"], detail["shared_state_sigma"], record["best_of"])
        for field in ("nodes", "score_distribution"):
            if canonical(rebuilt[field]) != canonical(scenario[field]):
                raise ValueError("scenario does not replay: " + field)
        for i, mp in enumerate(scenario["maps"]):
            if mp not in totals:
                totals[mp] = [0., 0., 0.]
            totals[mp][0] += scenario["weight"]
            totals[mp][1] += scenario["weight"] * rebuilt["played"][i]
            totals[mp][2] += scenario["weight"] * rebuilt["won"][i]
    for mp, row in detail["maps"].items():
        if row["a"] is not None:
            number(row["a"]); number(row["b"])
        if row["a"] is not None and abs(row["a"] + row["b"] - 1) > 1e-10:
            raise ValueError("map probabilities not complementary")
        if detail["veto"]["mode"] != "unresolved":
            selected, played, won = totals[mp]
            if abs(row["selected_probability"] - selected) > 1e-9 or abs(row["played_probability"] - played) > 1e-9:
                raise ValueError("map appearance probabilities differ from series tree")
            if played and (row["a"] is None or abs(row["a"] - won / played) > 1e-9):
                raise ValueError("map conditional win rate differs from series tree")
            if not played and (row["a"] is not None or row["b"] is not None):
                raise ValueError("excluded maps must have N/A probabilities")
    if (model is None) != (event is None):
        raise ValueError("model and event are both required for full replay")
    if model is not None:
        if canonical(record) != canonical(predict(model, event)):
            raise ValueError("forecast differs from model/input replay")
    return {"valid": True, "full_replay": model is not None, "sha256": digest(record)}
