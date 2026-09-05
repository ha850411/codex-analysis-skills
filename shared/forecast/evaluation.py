"""Paired, time-aware evaluation. Missing predictions stay in the denominator."""
from __future__ import annotations

import math
import random
from collections import Counter, defaultdict
from .core import derive, distribution, instant, number, score_pair, digest


def score(record):
    if record.get("eligibility") not in {"prospective", "historical_replay"}:
        return None
    if record.get("result_status") != "final" or record.get("status") == "unmodeled":
        return None
    if record["eligibility"]=="prospective":
        if instant(record["data_cutoff"])>instant(record["created_at"]) or instant(record["created_at"])>=instant(record["scheduled_start"]):
            raise ValueError("invalid prospective evaluation timing")
    probs = record.get("winner_probabilities")
    scores = record.get("score_distribution")
    actual = record.get("actual_score")
    if scores:
        d=derive(scores)
        probs=d["winner_probabilities"]
    else:
        d=None
    if not probs or actual is None:
        return None
    distribution(probs)
    a,b=score_pair(actual)
    winner="a" if a>b else "b" if b>a else "draw"
    if set(probs) != {"a","b","draw"}:
        raise ValueError("winner distribution must include a/draw/b")
    pick=sorted(probs,key=lambda k:(-probs[k],k))[0]
    out={"winner_accuracy":float(pick==winner),
         "brier":sum((p-float(k==winner))**2 for k,p in probs.items()),
         "log_loss":-math.log(max(1e-15,probs[winner])),
         "pick_probability":probs[pick]}
    if d:
        out.update(exact_score_accuracy=float(d["score_mode"]==actual),
                   top3_accuracy=float(actual in d["score_top3"]),
                   exact_score_log_loss=-math.log(max(1e-15,scores.get(actual,0))),
                   team_score_mae=(abs(d["means"][0]-a)+abs(d["means"][1]-b))/2,
                   margin_mae=abs(d["means"][0]-d["means"][1]-a+b))
    elif record.get("means"):
        x,y=record["means"]
        out.update(team_score_mae=(abs(x-a)+abs(y-b))/2,margin_mae=abs(x-y-a+b))
    return out


def summary(records):
    measured=[(r,score(r)) for r in records]
    valid=[s for _,s in measured if s is not None]
    metrics={}
    for key in sorted({k for s in valid for k in s} - {"pick_probability"}):
        values=[s[key] for s in valid if key in s]
        metrics[key]={"value":sum(values)/len(values),"n":len(values)}
    bins=[]
    for low in range(0,100,10):
        group=[s for s in valid if low/100 <= s["pick_probability"] < (low+10)/100 or low==90 and s["pick_probability"]==1]
        if group:
            bins.append({"range":[low/100,(low+10)/100],"n":len(group),
                         "mean_probability":sum(s["pick_probability"] for s in group)/len(group),
                         "observed_accuracy":sum(s["winner_accuracy"] for s in group)/len(group)})
    return {"published_n":len(records),"scored_n":len(valid),
            "coverage":len(valid)/len(records) if records else 0.,"metrics":metrics,
            "calibration":bins,"excluded":dict(Counter(
                r.get("exclusion_reason") or r.get("eligibility","unknown")+":"+r.get("status","unknown")
                for r,s in measured if s is None))}


def evaluate(records):
    groups=defaultdict(list)
    seen=set()
    for r in records:
        key=tuple(r.get(k) for k in ("sport","event_id","snapshot","data_cutoff","model_version"))
        if None in key:
            raise ValueError("evaluation identity missing")
        if key in seen:
            raise ValueError("duplicate evaluation identity")
        seen.add(key)
        instant(r["data_cutoff"])
        group=" / ".join(str(r.get(k,"unknown")) for k in ("sport","competition","snapshot","model_version","eligibility"))
        groups[group].append(r)
    return {"schema_version":"2.0","objective":"winner_accuracy_then_exact_score",
            "overall":summary(records),
            "prospective":summary([r for r in records if r.get("eligibility")=="prospective"]),
            "historical_replay":summary([r for r in records if r.get("eligibility")=="historical_replay"]),
            "cohorts":{k:summary(v) for k,v in sorted(groups.items())}}


def compare(records, baseline, challenger, *, seed=20260905, resamples=2000, min_blocks=30):
    versions={baseline:{},challenger:{}}
    for r in records:
        if r["model_version"] not in versions: continue
        key=tuple(r[k] for k in ("sport","event_id","snapshot","data_cutoff"))
        if key in versions[r["model_version"]]:
            raise ValueError("duplicate paired forecast")
        versions[r["model_version"]][key]=r
    old,new=versions[baseline],versions[challenger]
    if not old or not new: raise ValueError("both versions required")
    common=sorted(set(old)&set(new)); metrics=defaultdict(lambda:defaultdict(list))
    for key in common:
        a,b=score(old[key]),score(new[key])
        if old[key].get("actual_score") != new[key].get("actual_score"):
            raise ValueError("paired outcomes differ")
        if old[key].get("eligibility") != new[key].get("eligibility"):
            raise ValueError("paired forecast eligibility differs")
        if a is None or b is None: continue
        day=instant(old[key]["data_cutoff"]).date().isoformat()
        for metric in set(a)&set(b)-{"pick_probability"}:
            metrics[metric][day].append(b[metric]-a[metric])
    rng=random.Random(seed); report={}
    for metric,blocks in sorted(metrics.items()):
        days=sorted(blocks); values=[v for d in days for v in blocks[d]]
        draws=[]
        for _ in range(resamples):
            sample=[v for _ in days for v in blocks[rng.choice(days)]]
            draws.append(sum(sample)/len(sample))
        draws.sort()
        report[metric]={"delta":sum(values)/len(values),"paired_n":len(values),"blocks":len(days),
                        "interval_95":[draws[int(.025*resamples)],draws[min(resamples-1,int(.975*resamples))]]}
    coverage_old,coverage_new=summary(list(old.values())),summary(list(new.values()))
    winner=report.get("winner_accuracy",{})
    passed=bool(winner and winner["blocks"]>=min_blocks and winner["interval_95"][0]>0)
    reasons=[]
    if not passed: reasons.append("winner improvement not established with sufficient time blocks")
    if set(old)!=set(new) or coverage_new["coverage"]<coverage_old["coverage"]:
        passed=False; reasons.append("unequal event coverage or reduced availability")
    for metric,r in report.items():
        if metric=="winner_accuracy": continue
        worse=r["delta"]<0 if metric.endswith("accuracy") else r["delta"]>0
        if worse: passed=False; reasons.append(f"secondary regression: {metric}")
    # Cohort guard uses paired metrics, never a pooled average hiding a harmed sport.
    cohort=lambda r:tuple(str(r.get(k,"unknown")) for k in ("sport","competition","snapshot","eligibility"))
    for group in sorted({cohort(old[k]) for k in common}):
        pairs=[(score(old[k]),score(new[k])) for k in common if cohort(old[k])==group]
        diffs=[b["winner_accuracy"]-a["winner_accuracy"] for a,b in pairs if a and b]
        if diffs and sum(diffs)<0:
            passed=False; reasons.append(f"winner regression in {' / '.join(group)}")
    return {"baseline":baseline,"challenger":challenger,"input_hash":digest(records),
            "seed":seed,"resamples":resamples,"min_blocks":min_blocks,"paired_events":len(common),
            "baseline_coverage":coverage_old["coverage"],"challenger_coverage":coverage_new["coverage"],
            "metrics":report,"decision":"eligible-for-review" if passed else "experiment-only",
            "passed":passed,"reasons":reasons,"production_change":False}
