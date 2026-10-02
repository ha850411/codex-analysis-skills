"""Import already archived VLR observations, preserving retrieval-time limitations."""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path

from shared.forecast.core import digest, instant
from .data import context, validate_veto_record


def import_archive(packet):
    root = Path(packet["run_dir"]).resolve()
    source = root / packet.get("history_file", "history.json")
    raw = json.loads(source.read_text())
    matches_path = root / packet.get("matches_file", "matches-complete.json")
    matches = json.loads(matches_path.read_text())
    aliases = packet.get("team_aliases", {})
    by_id = {r["event_id"]: copy.deepcopy(r) for r in raw}
    if len(by_id) != len(raw):
        raise ValueError("duplicate historical event")
    audit = {"source_history_hash": digest(raw), "source_matches_hash": digest(matches),
             "alias_hash": digest(aliases), "enriched": [], "excluded": [], "source_overrides": [],
             "note": "No fetches. Retrieved-at is a conservative availability bound, never a fabricated publication time."}
    seen = set()
    for match in matches:
        found = re.search(r"vlr\.gg/(\d+)", match.get("url", ""))
        if not found:
            audit["excluded"].append({"url": match.get("url"), "reason": "no stable VLR match ID"})
            continue
        mid = found.group(1)
        if mid in seen:
            raise ValueError("duplicate archived match content")
        seen.add(mid)
        event_id = "vlr-" + mid
        if event_id not in by_id:
            audit["excluded"].append({"event_id": event_id, "reason": "no original timestamped final series result"})
            continue
        row = by_id[event_id]
        source_root = root
        if event_id in packet.get("source_overrides", {}):
            source_root = Path(packet["source_overrides"][event_id]).resolve()
            alternate_path = source_root / "matches-complete.json"
            alternate = json.loads(alternate_path.read_text())
            selected = [m for m in alternate if re.search(r"vlr\.gg/" + mid + r"(?:/|$)", m.get("url", ""))]
            if len(selected) != 1:
                raise ValueError("source override must identify exactly one archived match")
            match = selected[0]
            audit["source_overrides"].append({"event_id": event_id, "matches_path": str(alternate_path), "match_hash": digest(match)})
        meta_path = source_root / "sources" / ("match-" + mid + "-meta.json")
        if not meta_path.exists():
            audit["excluded"].append({"event_id": event_id, "reason": "missing archived retrieval receipt; retained original history only"})
            continue
        meta = json.loads(meta_path.read_text())
        html_path = source_root / "sources" / ("match-" + mid + ".html")
        if meta.get("sha256"):
            if not html_path.exists() or hashlib.sha256(html_path.read_bytes()).hexdigest() != meta["sha256"]:
                raise ValueError("archived source content does not match receipt: " + event_id)
        retrieved = meta.get("retrieved_at")
        if not retrieved:
            audit["excluded"].append({"event_id": event_id, "reason": "retrieval timestamp missing"})
            continue
        available = max([retrieved, row["completed_at"], row["available_at"]], key=instant)
        patch_match = re.search(r"\bPatch\s+([\d.]+)", match.get("date", ""))
        patch = patch_match.group(1) if patch_match else None
        games = []
        for mp in match.get("maps", []):
            if not mp.get("map") or not mp.get("teams") or len(mp["teams"]) != 2:
                continue
            teams = {aliases.get(t["name"], t["name"]): t for t in mp["teams"]}
            if set(teams) != set(row["participants"]):
                raise ValueError("archived map participants conflict with historical identity: " + event_id)
            ordered = [teams[t] for t in row["participants"]]
            try:
                scores = [int(t["score"]) for t in ordered]
            except (KeyError, ValueError, TypeError):
                continue
            if min(scores) < 0 or scores[0] == scores[1]:
                continue
            ctx = {"patch": patch} if patch else {}
            players = [t.get("players", []) for t in ordered]
            if all(len(p) == 5 for p in players):
                ctx["lineups"] = [[p["player"] for p in lineup] for lineup in players]
                if all(len(p.get("agents", [])) == 1 for lineup in players for p in lineup):
                    ctx["agents"] = [{p["player"]: p["agents"][0] for p in lineup} for lineup in players]
            games.append({"map": mp["map"], "winner": row["participants"][0 if scores[0] > scores[1] else 1],
                          "context": context(ctx), "available_at": available, "context_available_at": available,
                          "source_url": match["url"], "round_score": scores})
        if games:
            # New observations replace the corresponding map record, never duplicate it.
            old = {g["map"]: g for g in row.get("games", [])}
            for game in games:
                previous = old.get(game["map"])
                if previous:
                    if previous["winner"] != game["winner"]:
                        raise ValueError("archived map winner contradicts original: " + event_id)
                    game["available_at"] = min(game["available_at"], previous.get("available_at", row.get("map_data_verified_at", row["available_at"])), key=instant)
                    if previous.get("context"):
                        game["context_versions"] = copy.deepcopy(previous.get("context_versions", [])) + [{
                            "context": previous["context"], "available_at": previous.get("context_available_at", previous.get("available_at", row["available_at"]))}]
                old[game["map"]] = game
            row["games"] = list(old.values())
        veto = match.get("veto", "")
        actions = []
        if veto:
            for piece in veto.split(";"):
                text = piece.strip()
                action = re.fullmatch(r"(.+?) (ban|pick) (.+)", text)
                decider = re.fullmatch(r"(.+?) remains", text)
                if action:
                    team, kind, mp = action.groups()
                    team = aliases.get(team, team)
                    if team not in row["participants"]:
                        actions = []
                        audit["excluded"].append({"event_id": event_id, "field": "veto", "reason": "unmapped actor alias: " + team})
                        break
                    actions.append({"team": team, "action": kind, "map": mp.strip()})
                elif decider:
                    actions.append({"team": None, "action": "decider", "map": decider.group(1).strip()})
                else:
                    actions = []
                    audit["excluded"].append({"event_id": event_id, "field": "veto", "reason": "unsupported archived veto syntax"})
                    break
            if actions:
                pool = [a["map"] for a in actions]
                remaining = set(pool)
                for action in actions:
                    action["available_before"] = sorted(remaining)
                    remaining.discard(action["map"])
                candidate = {"pool": sorted(pool), "actions": actions, "available_at": available,
                             "pool_basis": "inferred from complete archived veto, not an official target pool assertion"}
                validate_veto_record(candidate, row["participants"])
                row["veto"] = candidate
        audit["enriched"].append({"event_id": event_id, "map_count": len(games), "veto": bool(row.get("veto")), "available_at": available, "receipt": str(meta_path)})
    return {"history": list(by_id.values()), "audit": audit}
