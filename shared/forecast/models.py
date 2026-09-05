"""Small reproducible baselines and challengers; no prices, no invented features.

The default models are deliberately uncalibrated. Train on timestamped final results,
evaluate with expanding windows, and promote outside this module only with evidence.
"""
from __future__ import annotations

import math
from collections import defaultdict
from .core import SPORTS, instant, number, distribution, series_tree, mixture, digest

ESPORTS = {"lol", "cs", "valorant", "dota2"}
PARAMETERS = {"baseline": {"k": 24., "half_life_days": None, "prior_games": 30.},
              "challenger": {"k": 24., "half_life_days": 90., "prior_games": 30.}}


def logistic(x):
    return 1/(1+math.exp(-max(-35,min(35,x))))


def latent_games(p, sigma):
    """Three-point shared-state quadrature, centered to preserve marginal p."""
    weights=[1/6,2/3,1/6]
    shifts=[-math.sqrt(3)*sigma,0.,math.sqrt(3)*sigma]
    lo,hi=-40.,40.
    for _ in range(80):
        mid=(lo+hi)/2
        if sum(w*logistic(mid+s) for w,s in zip(weights,shifts))<p: lo=mid
        else: hi=mid
    return [(w,logistic((lo+hi)/2+s)) for w,s in zip(weights,shifts)]


def constant_tree(bo,p):
    nodes={}
    def walk(a,b,path):
        if (a+b==2 if bo==2 else max(a,b)==bo//2+1): return
        nodes[path or "ROOT"]=p
        walk(a+1,b,path+"W");walk(a,b+1,path+"L")
    walk(0,0,"")
    return series_tree(bo,nodes)


def history_before(rows, cutoff, sport):
    cutoff = instant(cutoff)
    result, ids = [], set()
    for r in rows:
        if r.get("sport") != sport:
            continue
        if r.get("result_status") != "final":
            continue
        end = instant(r["completed_at"])
        available = instant(r["available_at"])
        if available < end:
            raise ValueError("result available before completion")
        if end >= cutoff or available > cutoff:
            continue
        if r["event_id"] in ids:
            raise ValueError("duplicate training event; aggregate map rows before fitting")
        ids.add(r["event_id"])
        if not r.get("source_url") or len(r["participants"]) != 2 or len(set(r["participants"]))!=2:
            raise ValueError("training results require source and participants")
        for score in r["score"]:
            number(score,0,1000)
            if int(score) != score:
                raise ValueError("training score must be integer")
        if len(r["score"]) != 2:
            raise ValueError("training score requires two values")
        result.append(r)
    return sorted(result,key=lambda r:(instant(r["completed_at"]),r["event_id"]))


def train(rows, sport, cutoff, variant="baseline", registry=None):
    if sport not in SPORTS or variant not in PARAMETERS:
        raise ValueError("unknown sport or variant")
    rows = history_before(rows,cutoff,sport)
    if not rows:
        raise ValueError("no eligible pre-cutoff final results")
    params = PARAMETERS[variant]
    model = {"schema_version":"1.0", "sport":sport, "trained_as_of":cutoff,
             "variant":variant,"status":"baseline" if variant=="baseline" else "experiment",
             "model_version":f"{sport}-{variant}-v2.0", "parameters":params,
             "parameter_version":digest(params), "training_hash":digest(rows),
             "training_event_ids":[r["event_id"] for r in rows], "n":len(rows)}
    if sport in ESPORTS:
        ratings, last_seen = {}, {}
        state_losses={sigma:0. for sigma in (0.,.25,.5,1.)}
        state_samples=0
        contexts = defaultdict(lambda:[0.,0.])
        for r in rows:
            a,b = r["participants"]
            for team in (a,b):
                rating = ratings.get(team,1500.)
                if params["half_life_days"] and team in last_seen:
                    days = (instant(r["completed_at"])-instant(last_seen[team])).total_seconds()/86400
                    rating = 1500+(rating-1500)*2**(-days/params["half_life_days"])
                ratings[team] = rating
                last_seen[team] = r["completed_at"]
            x,y = r["score"]
            if x+y == 0:
                raise ValueError("empty esports series")
            # Update using map share: this rating predicts a game, not a BO3 win.
            p = logistic((ratings[a]-ratings[b])*math.log(10)/400)
            bo=r.get("best_of")
            if bo in (2,3,5):
                observed=f"{x}-{y}"
                for sigma in state_losses:
                    prob=sum(w*constant_tree(bo,q).get(observed,0.) for w,q in latent_games(p,sigma))
                    if prob<=0: raise ValueError("historical series score incompatible with best_of")
                    state_losses[sigma]-=math.log(prob)
                state_samples+=1
            delta = params["k"]*(x/(x+y)-p)
            ratings[a] += delta
            ratings[b] -= delta
            # Only observed map records can estimate map effects. No narrative factors.
            for game in r.get("games",[]):
                if game.get("winner") not in (a,b) or not game.get("map"):
                    raise ValueError("observed games need named map and winner")
                for team in (a,b):
                    key = team+"::"+game["map"]
                    contexts[key][0] += game["winner"]==team
                    contexts[key][1] += 1
        sigma=min(state_losses,key=lambda x:(state_losses[x],x)) if variant=="challenger" and state_samples>=20 else 0.
        model.update(ratings=ratings,last_seen=last_seen,map_counts=dict(contexts),
                     shared_state_sigma=sigma,shared_state_fit_n=state_samples,
                     shared_state_training_losses=state_losses)
    else:
        # Shrunk offense/defense against a league environment; home order is explicit.
        team_stats = defaultdict(lambda:[0.,0.,0.])
        total_weight, total_points, home_delta = 0.,0.,0.
        residual_pairs = []
        for r in rows:
            days=(instant(cutoff)-instant(r["completed_at"])).total_seconds()/86400
            w=2**(-days/params["half_life_days"]) if params["half_life_days"] else 1.
            a,b=r["participants"]; x,y=r["score"]
            total_weight+=w; total_points+=w*(x+y)
            home=r.get("home_index")
            if home not in (0,1,None):
                raise ValueError("home_index must be 0, 1, or null")
            home_delta+=w*((x-y) if home==0 else (y-x) if home==1 else 0)
            for team,scored,allowed in ((a,x,y),(b,y,x)):
                s=team_stats[team]; s[0]+=w*scored; s[1]+=w*allowed; s[2]+=w
            residual_pairs.append((x,y,w))
        league=total_points/(2*total_weight)
        if league<=0:
            raise ValueError("cannot estimate positive scoring environment")
        means=[sum(r[i]*r[2] for r in residual_pairs)/total_weight for i in (0,1)]
        residuals=[[x-means[0],y-means[1],w] for x,y,w in residual_pairs]
        model.update(league_mean=league,team_stats=dict(team_stats),
                     home_advantage=home_delta/total_weight if variant=="challenger" else 0.,
                     residuals=residuals)
    if registry and variant=="challenger":
        from .features import fit
        model["feature_model"]=fit(rows,registry,sport,model.get("league_mean"))
        model["feature_registry_hash"]=digest(registry)
    return model


def predict(model, event):
    if model["sport"] != event["sport"] or len(event["participants"])!=2:
        raise ValueError("model/event sport or participants mismatch")
    if instant(model["trained_as_of"]) > instant(event["data_cutoff"]):
        raise ValueError("model trained after forecast cutoff")
    if event["event_id"] in model["training_event_ids"]:
        raise ValueError("target event leaked into training")
    sport=model["sport"]; a,b=event["participants"]
    missing=[]
    adjustments=None
    if model.get("feature_model"):
        from .features import adjustment
        adjustments=adjustment(model["feature_model"],event)
        if adjustments is None: missing.append("fitted factors missing at forecast cutoff; baseline fallback")
    if sport in ESPORTS:
        ratings=[]
        for team in (a,b):
            rating=model["ratings"].get(team,1500.)
            if team not in model["ratings"]:
                missing.append(f"{team} 缺隊伍樣本，使用聯盟先驗")
            half=model["parameters"]["half_life_days"]
            if half and team in model["last_seen"]:
                days=(instant(event["data_cutoff"])-instant(model["last_seen"][team])).total_seconds()/86400
                rating=1500+(rating-1500)*2**(-days/half)
            ratings.append(rating)
        p=logistic((ratings[0]-ratings[1])*math.log(10)/400)
        if adjustments: p=logistic(math.log(p/(1-p))+adjustments[0])
        bo=event["best_of"]
        paths=event.get("veto_scenarios") or [{"id":"unresolved-map-order","weight":1.,"maps":[]}]
        if event.get("veto_scenarios"):
            evidence_ids={e["id"] for e in event.get("evidence",[])}
            for path in paths:
                if not path.get("evidence_ids") or not set(path["evidence_ids"])<=evidence_ids:
                    raise ValueError("veto scenarios require known evidence IDs")
                if len(path.get("maps",[]))!=bo:
                    raise ValueError("veto scenarios require complete possible map order")
        if not event.get("veto_scenarios"):
            missing.append("地圖順序／draft 未定，目前僅使用基準強度")
        scenarios=[]
        for path in paths:
            nodes={}
            latent=latent_games(p,model.get("shared_state_sigma",0.))
            def build(w,l,key,state_weights):
                terminal=w+l==2 if bo==2 else max(w,l)==bo//2+1
                if terminal: return
                game_p=p
                maps=path.get("maps",[])
                if model["variant"]=="challenger" and w+l<len(maps):
                    offsets=[]
                    for team in (a,b):
                        wins,n=model["map_counts"].get(team+"::"+maps[w+l],[0.,0.])
                        offsets.append((wins+15)/(n+30)-.5)
                    game_p=logistic(math.log(p/(1-p))+2*(offsets[0]-offsets[1]))
                # Paths can encode evidence-based conditional adjustments from a separate
                # fitted model; this baseline does not invent momentum or draft effects.
                states=latent_games(game_p,model.get("shared_state_sigma",0.))
                # Condition on each possible path using its previous map-specific
                # likelihoods, never observed future outcomes.
                game_p=sum(m*q for m,(_,q) in zip(state_weights,states))/sum(state_weights)
                nodes[key or "ROOT"]=game_p
                build(w+1,l,key+"W",[m*q for m,(_,q) in zip(state_weights,states)])
                build(w,l+1,key+"L",[m*(1-q) for m,(_,q) in zip(state_weights,states)])
            build(0,0,"",[w for w,_ in latent])
            scenarios.append({"id":path["id"],"weight":path["weight"],"nodes":nodes,
                              "score_distribution":series_tree(bo,nodes)})
        scores=mixture(scenarios)
        missing.append("系列共同狀態僅經訓練期擬合，尚待樣本外驗證" if model.get("shared_state_sigma")
                       else "目前為條件獨立基準，系列相關性尚未校準")
        return {"score_distribution":scores,"scenarios":scenarios,"missing_data":missing}
    league=model["league_mean"]; prior=model["parameters"]["prior_games"]
    stats=[]
    for team in (a,b):
        x,y,n=model["team_stats"].get(team,[0.,0.,0.])
        if not n: missing.append(f"{team} 缺隊伍樣本，使用聯盟先驗")
        stats.append(((x+prior*league)/(n+prior),(y+prior*league)/(n+prior)))
    means=[stats[0][0]*stats[1][1]/league, stats[1][0]*stats[0][1]/league]
    home=event.get("home_index")
    if home in (0,1):
        means[home]+=model["home_advantage"]/2
        means[1-home]-=model["home_advantage"]/2
    means=[max(.05,x) for x in means]
    if adjustments:
        means=[max(.05,m+v) if sport=="nba" else m*math.exp(max(-3,min(3,v))) for m,v in zip(means,adjustments)]
    if sport=="nba":
        # Joint empirical residual distribution retains observed score dependence.
        scores={}; total=sum(r[2] for r in model["residuals"])
        for x,y,w in model["residuals"]:
            sa,sb=max(0,round(means[0]+x)),max(0,round(means[1]+y))
            if sa==sb:
                # Split tied regulation mass, explicitly an uncalibrated OT prior.
                for key in (f"{sa+1}-{sb}",f"{sa}-{sb+1}"):
                    scores[key]=scores.get(key,0)+w/total/2
            else:
                key=f"{sa}-{sb}"; scores[key]=scores.get(key,0)+w/total
        missing.extend(["傷兵、名單與出場分鐘效果尚未擬合", "延長賽使用對稱基準先驗"])
    else:
        scores=poisson_scores(*means, no_draw=sport=="mlb")
        missing.append("目前為獨立 Poisson 基準，離散程度與名單效果尚未校準")
        if sport=="mlb":
            missing.append("此為聚合比較基準；前五局、牛棚與再見得分須使用既有分階段模擬")
    return {"score_distribution":distribution(scores),"missing_data":missing,"means":means}


def poisson_scores(a_mean,b_mean,no_draw=False):
    arrays=[]
    for mean in (a_mean,b_mean):
        number(mean,.001,100)
        values=[math.exp(-mean)]
        k=0
        while sum(values)<1-1e-12:
            k+=1; values.append(values[-1]*mean/k)
        arrays.append(values)
    result={}
    for a,pa in enumerate(arrays[0]):
        for b,pb in enumerate(arrays[1]):
            if no_draw and a==b:
                for key in (f"{a+1}-{b}",f"{a}-{b+1}"):
                    result[key]=result.get(key,0)+pa*pb/2
            else:
                key=f"{a}-{b}"; result[key]=result.get(key,0)+pa*pb
    mass=sum(result.values())
    return {k:p/mass for k,p in result.items()}
