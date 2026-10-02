"""Opportunity-conditioned empirical veto, with exact legal path enumeration."""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache

from shared.forecast.core import canonical, digest, instant, number
from .data import evidence_refs, names


class MissingVetoEvidence(ValueError):
    """Valid input, but insufficient observations to infer a primary veto mixture."""


def fit_veto(rows, cutoff, config):
    records = []
    for row in rows:
        if not row.get("veto"):
            continue
        age = (instant(cutoff) - instant(row["completed_at"])).total_seconds() / 86400
        weight = 2 ** (-age / config["half_life_days"]) if config["half_life_days"] else 1.
        records.append({"event_id": row["event_id"], "participants": row["participants"], "best_of": row["best_of"],
                        "pool": sorted(row["veto"]["pool"]), "actions": row["veto"]["actions"],
                        "available_at": row["veto"]["available_at"], "source_url": row["source_url"],
                        "weight": weight})
    return {"method": "opportunity-rates-with-global-shrinkage", "prior": config["veto_prior"], "records": records}


def explicit_paths(event):
    paths = event["veto_scenarios"]
    names([p["id"] for p in paths], "veto scenario IDs")
    if abs(sum(number(p["weight"]) for p in paths) - 1) > 1e-8:
        raise ValueError("veto weights must sum to one")
    output = []
    for p in paths:
        names(p["maps"], "ordered veto maps", event["best_of"])
        if not set(p["maps"]) <= set(event["map_pool"]):
            raise ValueError("veto map outside current pool")
        evidence_refs(event, p.get("evidence_ids"))
        if p.get("weight_source") not in ("confirmed", "analyst_elicited", "fitted") or not p.get("weight_basis"):
            raise ValueError("explicit veto weights require source and basis")
        owners = p.get("pick_owners", [None] * event["best_of"])
        if len(owners) != event["best_of"] or any(o not in (None, "a", "b") for o in owners):
            raise ValueError("invalid pick owners")
        output.append({"id": p["id"], "weight": p["weight"], "maps": p["maps"], "pick_owners": owners})
    if event["snapshot"] == "post-veto" and (len(paths) != 1 or paths[0]["weight_source"] != "confirmed"):
        raise ValueError("post-veto requires one confirmed complete path")
    return output, {"mode": "explicit", "path_weights": [{k: p[k] for k in
                    ("id", "weight", "weight_source", "weight_basis", "evidence_ids")} for p in paths],
                    "full_action_coverage": "not_modeled"}


def paths(model, event):
    if event.get("veto_scenarios") and event.get("veto"):
        raise ValueError("provide explicit paths or a veto protocol, not both")
    if event.get("veto_scenarios"):
        return explicit_paths(event)
    veto = event.get("veto")
    if not veto:
        raise MissingVetoEvidence("未提供具來源的 veto 規則或完整路徑")
    evidence_refs(event, veto.get("evidence_ids"))
    pool, bo = event["map_pool"], event["best_of"]
    protocol = veto["protocol"]
    if len(protocol) != len(pool) or sum(p["action"] in ("pick", "decider") for p in protocol) != bo:
        raise ValueError("veto protocol must consume pool and select best_of maps")
    for i, step in enumerate(protocol):
        if step["action"] == "decider":
            if i != len(protocol) - 1 or step.get("actor") is not None:
                raise ValueError("decider is last with no actor")
        elif step["action"] not in ("ban", "pick") or step.get("actor") not in ("first", "second"):
            raise ValueError("protocol actors must be first/second")
    observed = veto.get("observed", [])
    if len(observed) > len(protocol):
        raise ValueError("too many observed veto actions")
    # Validate even prefixes with zero probability before trying a fallback.
    remaining = set(pool)
    for i, action in enumerate(observed):
        if action.get("action") != protocol[i]["action"] or action.get("map") not in remaining:
            raise ValueError("observed veto contradicts protocol or repeats a map")
        if action.get("actor") not in ((None,) if action["action"] == "decider" else ("a", "b")):
            raise ValueError("invalid observed veto actor")
        remaining.remove(action["map"])
    if event["snapshot"] == "post-veto" and len(observed) != len(protocol):
        raise ValueError("post-veto requires complete observed actions")
    first = veto.get("first_actor")
    if first not in (None, "a", "b"):
        raise ValueError("first_actor must be a, b or null")
    # A known actor in the prefix identifies who occupies the first/second slot.
    if len(protocol) == 1 and protocol[0]["action"] == "decider":
        first = "a"  # No team makes a choice in a one-map pool.
    elif observed:
        p0, a0 = protocol[0], observed[0]
        inferred = a0["actor"] if p0["actor"] == "first" else ("b" if a0["actor"] == "a" else "a")
        if first and first != inferred:
            raise ValueError("observed veto contradicts first_actor")
        first = inferred
    records = [r for r in model["veto"]["records"] if r["pool"] == sorted(pool) and r["best_of"] == bo]
    teams = event["participants"]
    counts = defaultdict(lambda: defaultdict(lambda: [0., 0.]))
    first_success, first_trials = 0., 0.
    for r in records:
        w = r["weight"]
        turns = defaultdict(int)
        for action in r["actions"]:
            kind, team = action["action"], action.get("team")
            if kind == "decider":
                continue
            turns[team, kind] += 1
            for key in ((team, kind, turns[team, kind]), (None, kind, turns[team, kind])):
                for mp in action["available_before"]:
                    counts[key][mp][1] += w
                    counts[key][mp][0] += w * (mp == action["map"])
        actor = r["actions"][0].get("team")
        if teams[0] in r["participants"]:
            first_success += w * (actor == teams[0])
            first_trials += w
        elif teams[1] in r["participants"]:
            first_success += w * (actor != teams[1])
            first_trials += w
    prior = model["veto"]["prior"]
    if first:
        orders = [(first, 1.)]
    elif first_trials:
        p = (first_success + prior / 2) / (first_trials + prior)
        orders = [("a", p), ("b", 1 - p)]
    else:
        raise MissingVetoEvidence("先後手未確認，且無兩隊同圖池首動樣本")

    @lru_cache(None)
    def choices(team, kind, turn, available):
        local, pooled = counts[team, kind, turn], counts[None, kind, turn]
        if not pooled:
            raise MissingVetoEvidence("缺少同圖池／行動輪次的歷史 veto 機會")
        scores = {}
        for mp in available:
            hits, trials = local.get(mp, (0., 0.))
            gh, gn = pooled.get(mp, (0., 0.))
            population = (gh + 1.) / (gn + 2.)
            scores[mp] = (hits + prior * population) / (trials + prior)
        mass = sum(scores.values())
        return {mp: v / mass for mp, v in scores.items()}

    leaves = []
    def walk(order, index, available, selected, owners, trace, turns, weight):
        if index == len(protocol):
            leaves.append({"maps": selected, "pick_owners": owners, "trace": trace, "weight": weight})
            return
        step = protocol[index]
        actor = None if step["action"] == "decider" else (order if step["actor"] == "first" else ("b" if order == "a" else "a"))
        turn_key = (actor, step["action"])
        turn = turns.get(turn_key, 0) + 1
        if index < len(observed):
            obs = observed[index]
            if obs.get("actor") != actor:
                raise ValueError("observed veto actor contradicts protocol")
            # Condition on the whole known prefix. Its probability is not a forecast.
            probabilities = {obs["map"]: 1.}
        elif step["action"] == "decider":
            if len(available) != 1:
                raise ValueError("decider requires one remaining map")
            probabilities = {available[0]: 1.}
        else:
            probabilities = choices(teams[0 if actor == "a" else 1], step["action"], turn, tuple(available))
        for mp, probability in probabilities.items():
            new_turns = dict(turns); new_turns[turn_key] = turn
            keep = step["action"] in ("pick", "decider")
            walk(order, index + 1, [x for x in available if x != mp], selected + ([mp] if keep else []),
                 owners + ([actor] if keep else []), trace + [[actor, step["action"], mp]],
                 new_turns, weight * probability)
    for order, weight in orders:
        walk(order, 0, sorted(pool), [], [], [], {}, weight)
    grouped = {}
    traces = []
    for leaf in leaves:
        key = canonical([leaf["maps"], leaf["pick_owners"]])
        group_id = "veto-" + digest([leaf["maps"], leaf["pick_owners"]])[:16]
        if key not in grouped:
            grouped[key] = {"id": group_id, "weight": 0., "maps": leaf["maps"], "pick_owners": leaf["pick_owners"]}
        grouped[key]["weight"] += leaf["weight"]
        traces.append({"order_id": group_id, "weight": leaf["weight"], "actions": leaf["trace"]})
    mass = sum(p["weight"] for p in grouped.values())
    if abs(mass - 1) > 1e-8:
        raise ValueError("veto enumeration lost probability mass")
    return list(grouped.values()), {"mode": "observed" if len(observed) == len(protocol) else "empirical",
            "first_actor": first, "first_actor_weights": dict(orders), "first_actor_effective_n": first_trials,
            "historical_event_ids": [r["event_id"] for r in records], "legal_paths": len(leaves),
            "retained_probability_mass": mass, "full_action_coverage": "modeled", "paths": traces,
            "limitations": ["首動權未知時由同圖池歷史首動頻率估計，並非官方確認。"] if first is None else []}
