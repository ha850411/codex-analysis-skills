"""Optional numeric factor fitting with pre-match provenance and registry gates."""
from __future__ import annotations

import math
import re
from .core import instant,number,digest


def extract(row, factor_ids, *, cutoff):
    snapshot=row.get("feature_snapshot")
    if not snapshot: return None
    if instant(snapshot["available_at"])>instant(cutoff):
        raise ValueError("feature snapshot became available after prediction cutoff")
    if not snapshot.get("evidence_ids"):
        raise ValueError("numeric features require evidence IDs")
    evidence={e["id"]:e for e in row.get("evidence",[])}
    if not set(snapshot["evidence_ids"])<=set(evidence):
        raise ValueError("numeric feature references unknown evidence")
    for key in snapshot["evidence_ids"]:
        if instant(evidence[key]["available_at"])>instant(cutoff):
            raise ValueError("numeric feature evidence postdates cutoff")
    values=snapshot.get("values",{})
    if not all(k in values for k in factor_ids): return None
    return [number(values[k],-1e9,1e9) for k in factor_ids]


def fit(rows,registry,sport,league_mean=None):
    factors=[]
    for factor in registry.get("factors",[]):
        if factor["status"]=="retired": continue
        if factor["status"]=="active" and factor.get("used_for_prediction") is False: continue
        if factor["status"] not in {"active","candidate"}: raise ValueError("invalid factor status")
        if not factor.get("pre_match_observable") or not factor.get("mechanism"):
            raise ValueError("factor needs reproducible definition and mechanism")
        if re.search(r"market|odds|price|stake|賠率|盤口",factor["factor_id"],re.I):
            raise ValueError("market factors cannot enter probability fitting")
        factors.append(factor["factor_id"])
    if len(factors)!=len(set(factors)): raise ValueError("duplicate factor ID")
    if not factors: return None
    usable=[]
    for row in rows:
        start=row.get("started_at")
        if not start: continue
        x=extract(row,factors,cutoff=start)
        if x is None: continue
        a,b=row["score"]
        if sport in {"lol","cs","valorant","dota2"}:
            if a+b==0: continue
            target=[a/(a+b)]
        elif sport=="nba": target=[a-league_mean,b-league_mean]
        else: target=[math.log((a+.5)/league_mean),math.log((b+.5)/league_mean)]
        usable.append((x,target))
    if len(usable)<max(20,5*len(factors)): return None
    means=[sum(x[i] for x,_ in usable)/len(usable) for i in range(len(factors))]
    scales=[max(1e-9,math.sqrt(sum((x[i]-means[i])**2 for x,_ in usable)/len(usable))) for i in range(len(factors))]
    xs=[[1.]+[(v-m)/s for v,m,s in zip(x,means,scales)] for x,_ in usable]
    logistic=sport in {"lol","cs","valorant","dota2"}
    weights=[]
    for outcome in range(len(usable[0][1])):
        beta=[0.]*(len(factors)+1)
        for _ in range(800):
            grad=[0.]*len(beta)
            for x,(_,target) in zip(xs,usable):
                pred=sum(b*v for b,v in zip(beta,x))
                if logistic: pred=1/(1+math.exp(-max(-35,min(35,pred))))
                for i,value in enumerate(x): grad[i]+=(pred-target[outcome])*value/len(xs)
            for i in range(len(beta)):
                beta[i]-=.03*(grad[i]+(.1*beta[i] if i else 0.))
        weights.append(beta)
    return {"factor_ids":factors,"registry_hash":digest(registry),"n":len(usable),
            "means":means,"scales":scales,"weights":weights,"logistic":logistic,
            "status":"experiment","parameters":{"steps":800,"learning_rate":.03,"ridge":.1}}


def adjustment(model,event):
    snapshot=event.get("feature_snapshot")
    if snapshot and not set(snapshot.get("evidence_ids",[])) <= {e["id"] for e in event.get("evidence",[])}:
        raise ValueError("feature references unknown evidence")
    x=extract(event,model["factor_ids"],cutoff=event["data_cutoff"])
    if x is None: return None
    z=[(v-m)/s for v,m,s in zip(x,model["means"],model["scales"])]
    # Centered slopes only: team/league baselines continue to supply the intercept.
    return [sum(b*v for b,v in zip(weights[1:],z)) for weights in model["weights"]]
