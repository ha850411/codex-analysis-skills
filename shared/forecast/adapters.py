"""Explicit legacy formats. Missing score distributions are never reconstructed."""
from __future__ import annotations

from .core import number, instant, digest


def adapt_evaluation(row, source):
    if source not in {"lol-history-v1","mlb-history-v1","valorant-snapshot-v1"}:
        raise ValueError("explicit supported source format required")
    r=row
    sport=source.split("-")[0]
    event=str(r.get("event_id") or r.get("match_key") or r.get("match_id") or r.get("game_id") or "")
    created=r.get("predicted_at") or r.get("created_at")
    start=r.get("actual_start") or r.get("start_time") or r.get("first_pitch") or r.get("scheduled_start")
    eligible="legacy_unverified"; reason="legacy source lacks verified forecast timing"
    if created and start:
        if instant(created)>=instant(start):
            eligible="reconstructed_after_start"; reason="forecast created after start"
        elif r.get("included_in_prospective_metrics") is False or r.get("evaluation_status") in {"reconstructed_after_start","excluded"}:
            reason="legacy record explicitly excluded"
        else:
            # This qualifies for a legacy diagnostic, not proof of a persisted original.
            reason="timestamps precede start; original immutable artifact still requires verification"
    result_status=r.get("result_status") or r.get("actual_status")
    actual=None; scores=None; probs=None; means=None
    if source=="lol-history-v1":
        scores=r.get("exact_score_probabilities")
        if scores:
            scores={k:number(v) for k,v in scores.items()}
        actual=r.get("actual_score")
        if r.get("team1_win_prob") is not None:
            p=number(r["team1_win_prob"])
            b=number(r.get("team2_win_prob",1-p))
            probs={"a":p,"b":b,"draw":max(0.,1-p-b)}
        result_status=result_status or ("final" if actual else "unknown")
    elif source=="mlb-history-v1":
        x,y=r.get("actual_away_runs"),r.get("actual_home_runs")
        if x is not None and y is not None: actual=f"{int(x)}-{int(y)}"
        if r.get("home_win_prob") is not None:
            p=number(r["home_win_prob"]); probs={"a":1-p,"b":p,"draw":0.}
        if r.get("away_runs_mean") is not None: means=[r["away_runs_mean"],r["home_runs_mean"]]
        result_status=result_status or "unknown"
    else:
        scores={}
        for k,p in r.get("main_score_distribution",{}).items():
            side,x,y=k.split("_"); x,y=int(x),int(y)
            scores[f"{x}-{y}" if side=="a" else f"{y}-{x}"]=number(p,0,100)/100
        actual=r.get("actual_score"); result_status=result_status or "unknown"
    result_status="final" if str(result_status).lower() in {"final","completed","complete"} else str(result_status).lower()
    if not event or not created or not r.get("model_version"):
        raise ValueError("legacy record missing event, timestamp or model version")
    return {"schema_version":"2.0","source_format":source,"source_hash":digest(row),
            "sport":sport,"event_id":event,"snapshot":r.get("snapshot","unknown"),
            "created_at":created,"scheduled_start":start,
            "data_cutoff":r.get("data_cutoff") or created,"model_version":r["model_version"],
            "competition":r.get("tournament") or r.get("competition") or sport,
            "status":r.get("status","baseline"),"eligibility":eligible,"exclusion_reason":reason,
            "score_distribution":scores,"winner_probabilities":probs,"means":means,
            "actual_score":actual,"result_status":result_status,
            "legacy_prestart_timestamps":bool(created and start and instant(created)<instant(start))}


def audit(rows, source):
    from collections import Counter
    normalized=[]; errors=[]
    for i,r in enumerate(rows):
        try: normalized.append(adapt_evaluation(r,source))
        except (ValueError,KeyError,TypeError) as exc: errors.append({"row":i+1,"error":str(exc)})
    return {"source_format":source,"rows":len(rows),"normalized":len(normalized),
            "eligibility":dict(Counter(r["eligibility"] for r in normalized)),
            "prestart_timestamp_rows":sum(r["legacy_prestart_timestamps"] for r in normalized),
            "with_score_distribution":sum(bool(r["score_distribution"]) for r in normalized),
            "with_final_result":sum(r["result_status"]=="final" for r in normalized),
            "errors":errors,"accuracy_improvement_claim":False}
