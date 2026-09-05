"""Canonical forecast contract. Probabilities are fractions, never inferred units."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

SPORTS = {"lol", "cs", "valorant", "dota2", "mlb", "nba", "soccer"}
WEIGHTS = dict(data_completeness=.25, freshness=.20, lineup_certainty=.25,
               regime_relevance=.20, model_stability=.10)


def instant(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be an ISO-8601 string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result


def number(value, low=0, high=1):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("expected finite number")
    if not low <= value <= high:
        raise ValueError(f"number outside [{low}, {high}]")
    return value


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def distribution(value):
    if not isinstance(value, dict) or not value:
        raise ValueError("distribution must be a nonempty object")
    for key, probability in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError("distribution keys must be nonempty strings")
        number(probability)
    if abs(sum(value.values()) - 1) > 1e-8:
        raise ValueError("distribution must sum to 1 (fraction units)")
    return value


def score_pair(key):
    if not re.fullmatch(r"\d+-\d+", key):
        raise ValueError(f"invalid score: {key}")
    return tuple(map(int, key.split("-")))


def derive(scores):
    distribution(scores)
    winners = dict(a=0.0, draw=0.0, b=0.0)
    totals, margins = {}, {}
    means = [0., 0.]
    for key, p in scores.items():
        a, b = score_pair(key)
        winners["a" if a > b else "b" if b > a else "draw"] += p
        totals[str(a+b)] = totals.get(str(a+b), 0.) + p
        margins[str(a-b)] = margins.get(str(a-b), 0.) + p
        means[0] += p*a
        means[1] += p*b
    # Stable ties, with tie disclosure. A tied mode is never claimed unique.
    modes = sorted(k for k, p in scores.items() if abs(p-max(scores.values())) < 1e-12)
    winner_modes = sorted(k for k, p in winners.items() if abs(p-max(winners.values())) < 1e-12)
    return {"winner_probabilities": winners, "winner_pick": winner_modes[0],
            "winner_ties": winner_modes, "score_mode": modes[0], "score_ties": modes,
            "score_mode_probability": scores[modes[0]], "score_top3": sorted(scores, key=lambda k: (-scores[k], k))[:3],
            "means": means, "total_distribution": totals, "margin_distribution": margins,
            "a_at_least_one": sum(p for s,p in scores.items() if score_pair(s)[0] > 0),
            "b_at_least_one": sum(p for s,p in scores.items() if score_pair(s)[1] > 0),
            "both_at_least_one": sum(p for s,p in scores.items() if min(score_pair(s)) > 0)}


def series_tree(best_of, nodes):
    if isinstance(best_of,bool) or best_of not in (1, 2, 3, 5):
        raise ValueError("supported formats: BO1, BO2, BO3, BO5")
    output, used = {}, set()
    def walk(a, b, path, mass):
        terminal = a+b == 2 if best_of == 2 else max(a,b) == best_of//2+1
        if terminal:
            key = f"{a}-{b}"
            output[key] = output.get(key, 0.) + mass
            return
        key = path or "ROOT"
        if key not in nodes:
            raise ValueError(f"missing conditional node {key}")
        used.add(key)
        p = number(nodes[key])
        walk(a+1,b,path+"W",mass*p)
        walk(a,b+1,path+"L",mass*(1-p))
    walk(0,0,"",1.)
    if set(nodes) != used:
        raise ValueError("unused conditional nodes")
    return distribution(output)


def mixture(scenarios):
    if not scenarios or abs(sum(number(s["weight"]) for s in scenarios)-1) > 1e-8:
        raise ValueError("scenario weights must sum to 1")
    result = {}
    for scenario in scenarios:
        for key,p in distribution(scenario["score_distribution"]).items():
            result[key] = result.get(key, 0.) + scenario["weight"]*p
    return distribution(result)


def validate(record):
    if record.get("schema_version") != "2.0" or record.get("probability_unit") != "fraction":
        raise ValueError("expected forecast v2.0 with explicit fraction units")
    required = ("forecast_id", "event_id", "sport", "competition", "snapshot", "created_at",
                "data_cutoff", "scheduled_start", "model_version", "parameter_version", "status",
                "participants", "evidence", "missing_data", "confidence", "scope", "eligibility")
    for key in required:
        if key not in record:
            raise ValueError(f"missing {key}")
    for key in ("forecast_id", "event_id", "competition", "snapshot", "model_version", "parameter_version", "scope"):
        if not isinstance(record[key], str) or not record[key].strip():
            raise ValueError(f"invalid {key}")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,180}", record["forecast_id"]):
        raise ValueError("forecast_id is not a safe filename")
    if record["sport"] not in SPORTS or record["status"] not in {"baseline", "experiment", "production", "unmodeled"}:
        raise ValueError("invalid sport or model status")
    if record["eligibility"] not in {"prospective", "historical_replay", "reconstructed_after_start", "legacy_unverified"}:
        raise ValueError("invalid eligibility")
    cutoff, created, start = (instant(record[k]) for k in ("data_cutoff", "created_at", "scheduled_start"))
    if cutoff > created:
        raise ValueError("data cutoff after forecast creation")
    if record["eligibility"] == "prospective" and created >= instant(record.get("actual_start") or record["scheduled_start"]):
        raise ValueError("prospective forecast must precede start")
    if len(record["participants"]) != 2 or len(set(record["participants"])) != 2:
        raise ValueError("two distinct participants required; a then b")
    if not all(isinstance(p,str) and p.strip() for p in record["participants"]):
        raise ValueError("invalid participants")
    if not isinstance(record["missing_data"], list) or not isinstance(record["evidence"], list):
        raise ValueError("evidence and missing_data must be arrays")
    if not all(isinstance(x,str) and x.strip() for x in record["missing_data"]):
        raise ValueError("missing_data must contain nonempty reasons")
    for key in ("key_points","risks"):
        if key in record and (not isinstance(record[key],list) or not all(isinstance(x,str) and x.strip() for x in record[key])):
            raise ValueError(f"{key} must contain nonempty strings")
    ids = set()
    for e in record["evidence"]:
        for key in ("id", "url", "available_at", "retrieved_at", "claim"):
            if not isinstance(e.get(key), str) or not e[key].strip():
                raise ValueError(f"evidence missing {key}")
        if e["id"] in ids:
            raise ValueError("duplicate evidence id")
        if not e["url"].startswith(("https://","http://")):
            raise ValueError("evidence URL must be HTTP(S)")
        ids.add(e["id"])
        if instant(e["available_at"]) > cutoff:
            raise ValueError("evidence available after cutoff")
        retrieved = instant(e["retrieved_at"])
        if record["eligibility"] == "prospective" and retrieved > created:
            raise ValueError("evidence retrieved after forecast creation")
    if record["status"] != "unmodeled" and not record["evidence"]:
        raise ValueError("modeled forecast requires evidence")
    confidence = record["confidence"]
    if confidence is not None:
        components = confidence["components"]
        value = math.floor(sum(number(components[k],0,100)*w for k,w in WEIGHTS.items())+.5)
        if confidence["value"] != value:
            raise ValueError("confidence must equal weighted evidence-quality score")
    elif not record["missing_data"]:
        raise ValueError("missing confidence requires reason")
    eligible=record.get("recommendation_eligible",False)
    if not isinstance(eligible,bool) or eligible and record["status"]!="production":
        raise ValueError("only production can be recommendation eligible")
    decision=record.get("decision")
    if decision is not None:
        if not isinstance(decision,dict): raise ValueError("decision must be an object")
        stake=number(decision.get("stake_units",0),0,100)
        if not eligible and (stake>0 or decision.get("status") not in {"wait","avoid"}):
            raise ValueError("uncalibrated forecasts can only wait/avoid with zero stake")
        if stake>0:
            for field in ("market_source","market_retrieved_at","market_expires_at","market_odds"):
                if field not in decision: raise ValueError(f"positive stake missing {field}")
            number(decision["market_odds"],1.000001,1000000)
            if instant(decision["market_retrieved_at"])<created:
                raise ValueError("market must be collected after probability lock")
            if instant(decision["market_expires_at"])<=instant(decision["market_retrieved_at"]):
                raise ValueError("invalid market expiration")
    if record["status"] == "unmodeled":
        if record.get("score_distribution") or not record["missing_data"]:
            raise ValueError("unmodeled requires missing-data reason and no distribution")
        return record
    scores = distribution(record["score_distribution"])
    derived = derive(scores)
    if record["sport"] in {"lol", "cs", "valorant", "dota2"}:
        bo = record.get("best_of")
        if isinstance(bo,bool) or bo not in (1,2,3,5):
            raise ValueError("best_of required")
        expected = {"2-0", "1-1", "0-2"} if bo == 2 else {f"{bo//2+1}-{i}" for i in range(bo//2+1)} | {f"{i}-{bo//2+1}" for i in range(bo//2+1)}
        if set(scores) != expected:
            raise ValueError("incomplete or impossible series score support")
    if record["sport"] in {"mlb", "nba"} and derived["winner_probabilities"]["draw"] > 1e-12 and record["scope"] == "full-game":
        raise ValueError("full-game NBA/MLB cannot finish tied")
    if record.get("scenarios"):
        mixed = mixture(record["scenarios"])
        if any(abs(mixed.get(k,0)-scores.get(k,0)) > 1e-8 for k in set(mixed)|set(scores)):
            raise ValueError("main distribution differs from scenario mixture")
    if "derived" in record and canonical(record["derived"]) != canonical(derived):
        raise ValueError("derived values differ from main distribution")
    return record


def record_forecast(value, root):
    validate(value)
    if instant(value["created_at"]) > datetime.now(timezone.utc):
        raise ValueError("cannot record forecast from the future")
    target = Path(root) / value["sport"] / "history" / "forecasts" / (value["forecast_id"]+".json")
    if (value["eligibility"]=="prospective" and not target.exists()
            and datetime.now(timezone.utc)>=instant(value.get("actual_start") or value["scheduled_start"])):
        raise ValueError("cannot first record a prospective forecast after start; use historical_replay or reconstructed_after_start")
    target.parent.mkdir(parents=True, exist_ok=True)
    content = canonical(value)+"\n"
    with tempfile.NamedTemporaryFile(mode="w",encoding="utf8",dir=target.parent,delete=False) as stream:
        temporary=Path(stream.name)
        try:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        try:
            os.link(temporary,target)
        except FileExistsError:
            if canonical(json.loads(target.read_text())) != canonical(value):
                raise ValueError("immutable forecast ID collision")
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": str(target), "sha256": digest(value)}


def settlement_ev(odds, *, win, half_win=0, push=0, half_loss=0):
    number(odds,1,1000000)
    parts = [number(p) for p in (win,half_win,push,half_loss)]
    if sum(parts)>1+1e-10:
        raise ValueError("settlement mass exceeds 1")
    return odds*win+(odds+1)/2*half_win+push+.5*half_loss-1
