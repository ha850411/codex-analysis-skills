"""Cutoff-aware inputs. Missing map metadata never becomes invented evidence."""
from __future__ import annotations

import copy
import re
from collections import Counter

from shared.forecast.core import digest, instant, number
from shared.forecast.models import history_before


def reject_market(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if re.search(r"(^|_)(odds|market|stake|price|betting)(_|$)", key, re.I):
                raise ValueError("market fields cannot enter model inputs: " + key)
            reject_market(item)
    elif isinstance(value, list):
        for item in value:
            reject_market(item)


def names(values, label, size=None):
    if not isinstance(values, list) or not values or any(
        not isinstance(x, str) or not x.strip() for x in values
    ) or len(set(values)) != len(values) or (size is not None and len(values) != size):
        raise ValueError("invalid " + label)
    return values


def context(value):
    if not isinstance(value, dict):
        raise ValueError("map context must be an object")
    allowed = {"patch", "lineups", "agents", "a_start_side"}
    if set(value) - allowed:
        raise ValueError("unsupported map context fields: " + str(sorted(set(value) - allowed)))
    if "patch" in value and (not isinstance(value["patch"], str) or not value["patch"]):
        raise ValueError("invalid patch")
    if "lineups" in value:
        if len(value["lineups"]) != 2:
            raise ValueError("lineups require A and B")
        for lineup in value["lineups"]:
            names(lineup, "five-player map lineup", 5)
        if set(value["lineups"][0]) & set(value["lineups"][1]):
            raise ValueError("same player on both teams")
    if "agents" in value:
        if "lineups" not in value or len(value["agents"]) != 2:
            raise ValueError("agent assignments require both five-player lineups")
        for lineup, assignments in zip(value["lineups"], value["agents"]):
            if not isinstance(assignments, dict) or set(assignments) != set(lineup):
                raise ValueError("agent assignments must match map lineup")
            if any(not isinstance(v, str) or not v for v in assignments.values()):
                raise ValueError("invalid agent assignment")
    if value.get("a_start_side") not in (None, "attack", "defense"):
        raise ValueError("a_start_side must be attack, defense or null")
    return copy.deepcopy(value)


def history(rows, cutoff):
    """A result and its later-enriched map fields have separate availability gates."""
    reject_market(rows)
    selected = history_before(rows, cutoff, "valorant")
    output, exclusions = [], Counter()
    for source in selected:
        row = copy.deepcopy(source)
        bo = row.get("best_of")
        x, y = row["score"]
        if isinstance(bo, bool) or bo not in (1, 3, 5) or max(x, y) != bo // 2 + 1 or min(x, y) >= max(x, y):
            raise ValueError("unsupported or impossible Valorant series score")
        games, seen, wins = [], set(), Counter()
        for game in row.get("games", []):
            name, winner = game.get("map"), game.get("winner")
            if not isinstance(name, str) or not name or name in seen or winner not in row["participants"]:
                raise ValueError("duplicate/invalid observed map or winner")
            seen.add(name)
            wins[winner] += 1
            available = game.get("available_at", row.get("map_data_verified_at", row["available_at"]))
            if row.get("started_at") and instant(available) < instant(row["started_at"]):
                raise ValueError("map outcome availability predates series start")
            if instant(available) > instant(cutoff):
                exclusions["map_metadata_after_cutoff"] += 1
                continue
            ctx = context(game.get("context", {}))
            ctx_time = game.get("context_available_at", available)
            if instant(ctx_time) > instant(cutoff):
                ctx = {}
                exclusions["map_context_after_cutoff"] += 1
                prior = [v for v in game.get("context_versions", []) if instant(v["available_at"]) <= instant(cutoff)]
                if prior:
                    version = max(prior, key=lambda v: instant(v["available_at"]))
                    ctx, ctx_time = context(version["context"]), version["available_at"]
            games.append({"map": name, "winner": winner, "context": ctx,
                          "available_at": available, "context_available_at": ctx_time,
                          "source_url": game.get("source_url", row["source_url"])})
        if any(wins[t] > s for t, s in zip(row["participants"], row["score"])):
            raise ValueError("map outcomes contradict series score")
        row["games"] = games
        if row.get("veto"):
            v = row["veto"]
            if instant(v["available_at"]) > instant(cutoff):
                row.pop("veto")
                exclusions["veto_after_cutoff"] += 1
            else:
                validate_veto_record(v, row["participants"])
                chosen = [a["map"] for a in v["actions"] if a["action"] in ("pick", "decider")]
                if len(chosen) != bo or not {g["map"] for g in games} <= set(chosen):
                    raise ValueError("veto selections contradict best_of or observed maps")
        output.append(row)
    return output, dict(exclusions)


def validate_veto_record(veto, participants):
    remaining = set(names(veto["pool"], "historical map pool"))
    actions = veto["actions"]
    if not actions:
        raise ValueError("empty observed veto")
    for action in actions:
        if set(action["available_before"]) != remaining or len(action["available_before"]) != len(remaining):
            raise ValueError("veto opportunity set differs from remaining pool")
        kind = action["action"]
        if kind not in ("ban", "pick", "decider") or action["map"] not in remaining:
            raise ValueError("illegal veto action")
        if kind == "decider":
            if len(remaining) != 1 or action.get("team") is not None:
                raise ValueError("decider must be the sole remaining map")
        elif action.get("team") not in participants:
            raise ValueError("veto actor not a participant")
        remaining.remove(action["map"])
    if remaining:
        raise ValueError("historical veto must include every pool map")


def evidence_refs(event, refs):
    available = {e["id"]: e for e in event["evidence"]}
    if not refs or not set(refs) <= set(available):
        raise ValueError("structured input requires known evidence IDs")
    if any(instant(available[k]["available_at"]) > instant(event["data_cutoff"]) for k in refs):
        raise ValueError("input evidence postdates cutoff")


def event_input(event):
    reject_market(event)
    if set(event) & {"actual_score", "result_status", "score_distribution", "winner_probabilities"}:
        raise ValueError("target outcomes/probabilities must be separate from forecast inputs")
    if instant(event["data_cutoff"]) >= instant(event.get("actual_start") or event["scheduled_start"]):
        raise ValueError("pre-match cutoff must precede start, including historical replays")
    if event.get("sport") != "valorant" or event.get("best_of") not in (1, 3, 5):
        raise ValueError("Valorant BO1/BO3/BO5 required")
    if isinstance(event["best_of"], bool):
        raise ValueError("invalid best_of")
    if event.get("scope") != "full-series" or event.get("current_score") or event.get("initial_score"):
        raise ValueError("v3 currently supports standard pre-match full series, not live/map advantages")
    if event.get("snapshot") not in ("pre-veto", "post-lineup", "post-veto"):
        raise ValueError("unsupported snapshot; live requires a different conditional model")
    names(event["participants"], "participants", 2)
    names(event["map_pool"], "current event map pool")
    if len(event["map_pool"]) < event["best_of"] or len(event["map_pool"]) > 7:
        raise ValueError("exact veto enumeration supports pools up to seven maps")
    evidence_refs(event, event.get("input_evidence_ids"))
    for mp, value in event.get("contexts_by_map", {}).items():
        if mp not in event["map_pool"]:
            raise ValueError("context for map outside event pool")
        context(value)
    scenarios = event.get("roster_scenarios", [])
    if scenarios:
        if abs(sum(number(s["weight"]) for s in scenarios) - 1) > 1e-8:
            raise ValueError("roster weights must sum to one")
        names([s["id"] for s in scenarios], "roster scenario IDs")
        for s in scenarios:
            evidence_refs(event, s.get("evidence_ids"))
            if s.get("weight_source") not in ("confirmed", "analyst_elicited", "fitted") or not s.get("weight_basis"):
                raise ValueError("roster scenario weights need provenance")
            for mp, ctx in s.get("contexts_by_map", {}).items():
                if mp not in event["map_pool"]:
                    raise ValueError("roster map outside pool")
                context(ctx)
    return event


def input_hash(value):
    return digest(value)
