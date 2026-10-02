"""Joint opponent-adjusted map model with ridge-shrunk conditional effects."""
from __future__ import annotations

import math
from collections import Counter

from shared.forecast.core import canonical, digest, instant, number
from shared.forecast.models import latent_games
from .data import history
from . import VERSION

DEFAULTS = {"half_life_days": 90., "layers": ["team", "map", "patch", "roster", "agents", "side"],
            "penalties": {"team": 2., "map": 8., "patch": 16., "roster": 12., "agents": 24., "side": 12.},
            "steps": 500, "tolerance": 1e-8, "fit_correlation": False, "veto_prior": 2.}
FACTORS = {"team": "opponent-adjusted-map-strength", "map": "opponent-adjusted-map-strength",
           "patch": "patch-agent-regime-map-pooling", "agents": "patch-agent-regime-map-pooling",
           "roster": "roster-era-strength-transfer", "side": "map-start-side-effect"}


def logistic(z):
    return 1 / (1 + math.exp(-max(-35., min(35., z))))


def settings(config=None):
    import copy
    result = copy.deepcopy(DEFAULTS)
    for k, v in (config or {}).items():
        if k not in result:
            raise ValueError("unknown model parameter " + k)
        result[k] = v
    if not isinstance(result["layers"], list) or "team" not in result["layers"] or len(set(result["layers"])) != len(result["layers"]) or set(result["layers"]) - set(FACTORS):
        raise ValueError("invalid feature layers")
    if result["half_life_days"] is not None:
        number(result["half_life_days"], 1, 10000)
    if set(result["penalties"]) != set(FACTORS):
        raise ValueError("all shrinkage penalties required")
    for v in result["penalties"].values():
        number(v, .0001, 10000)
    if isinstance(result["steps"], bool) or not isinstance(result["steps"], int) or not 1 <= result["steps"] <= 10000:
        raise ValueError("invalid optimizer steps")
    number(result["tolerance"], 1e-12, .01)
    number(result["veto_prior"], .01, 1000)
    if not isinstance(result["fit_correlation"], bool):
        raise ValueError("fit_correlation must be boolean")
    return result


def features(teams, mp, ctx, layers):
    values = {}
    def add(family, key, sign):
        if family in layers:
            values[canonical([family, *key])] = sign
    for i, team in enumerate(teams):
        sign = 1. if i == 0 else -1.
        add("team", [team], sign)
        if mp is None:
            continue
        add("map", [team, mp], sign)
        if ctx.get("patch"):
            add("patch", [team, mp, ctx["patch"]], sign)
        if ctx.get("lineups"):
            add("roster", [team, sorted(ctx["lineups"][i])], sign)
        if ctx.get("agents"):
            add("agents", [team, mp, sorted(ctx["agents"][i].items())], sign)
    if mp is not None and ctx.get("a_start_side"):
        add("side", [mp], 1. if ctx["a_start_side"] == "attack" else -1.)
    return values


def observations(rows, cutoff, config):
    out = []
    for row in rows:
        n = sum(row["score"])
        days = (instant(cutoff) - instant(row["completed_at"])).total_seconds() / 86400
        decay = 2 ** (-days / config["half_life_days"]) if config["half_life_days"] else 1.
        a = row["participants"][0]
        won = 0
        for game in row["games"]:
            y = float(game["winner"] == a)
            won += y
            out.append((features(row["participants"], game["map"], game["context"], config["layers"]), y, decay / n))
        rest = n - len(row["games"])
        if rest:
            out.append((features(row["participants"], None, {}, config["layers"]),
                        (row["score"][0] - won) / rest, decay * rest / n))
    return out


def fit_strength(rows, cutoff, config):
    import json
    obs = observations(rows, cutoff, config)
    keys = sorted({k for x, _, _ in obs for k in x})
    index = {k: i for i, k in enumerate(keys)}
    xs = [([(index[k], v) for k, v in x.items()], y, w) for x, y, w in obs]
    penalties = [config["penalties"][json.loads(k)[0]] for k in keys]
    weights = [0.] * len(keys)
    def loss(beta, gradient=False):
        total = sum(p * b * b / 2 for p, b in zip(penalties, beta))
        grad = [p * b for p, b in zip(penalties, beta)] if gradient else None
        for x, y, w in xs:
            z = sum(beta[j] * v for j, v in x)
            total += w * (max(z, 0) + math.log1p(math.exp(-abs(z))) - y * z)
            if gradient:
                err = w * (logistic(z) - y)
                for j, v in x:
                    grad[j] += err * v
        return total, grad
    rate, converged, iterations = .1, False, 0
    previous, _ = loss(weights)
    for iterations in range(1, config["steps"] + 1):
        current, grad = loss(weights, True)
        norm = sum(g * g for g in grad)
        if norm ** .5 < config["tolerance"]:
            converged = True
            break
        step = rate
        for _ in range(60):
            trial = [b - step * g for b, g in zip(weights, grad)]
            new, _ = loss(trial)
            if new <= current - .0001 * step * norm:
                break
            step *= .5
        else:
            raise ValueError("map optimizer line search failed")
        weights = trial
        if abs(previous - new) <= config["tolerance"] * max(1., abs(previous)):
            converged = True
            previous = new
            break
        previous, rate = new, step * 1.25
    return {"weights": dict(zip(keys, weights)), "fit": {"converged": converged,
            "iterations": iterations, "objective": previous, "observations": len(obs),
            "series_weighting": "one total pre-decay unit per series; observed maps plus residual unknown-map share"}}


def map_probability(model, teams, mp, ctx):
    vector = features(teams, mp, ctx, model["parameters"]["layers"])
    used = {k: v for k, v in vector.items() if k in model["strength"]["weights"]}
    z = sum(model["strength"]["weights"][k] * v for k, v in used.items())
    return logistic(z), {"used": used, "unseen": sorted(set(vector) - set(used))}


def correlation(rows, cutoff, config):
    """Optional chronological calibration within TRAINING data, never outer targets."""
    if not config["fit_correlation"]:
        return 0., {"method": "independent-control", "n": 0}
    split = len(rows) * 7 // 10
    earlier, later = rows[:split], rows[split:]
    complete = [r for r in later if len(r["games"]) == sum(r["score"])]
    if len(earlier) < 20 or len(complete) < 20:
        return 0., {"method": "insufficient-training-calibration-series", "n": len(complete)}
    boundary = min(instant(r.get("started_at", r["completed_at"])) for r in later)
    earlier = [r for r in earlier if instant(r["available_at"]) < boundary and
               all(instant(g["available_at"]) < boundary and instant(g["context_available_at"]) < boundary for g in r["games"])]
    if len(earlier) < 20:
        return 0., {"method": "insufficient-pre-boundary-inputs", "n": len(earlier)}
    fitted = {"parameters": config, "strength": fit_strength(earlier, boundary.isoformat(), config)}
    losses = {s: 0. for s in (0., .25, .5, 1.)}
    for r in complete:
        ps = [map_probability(fitted, r["participants"], g["map"], g["context"])[0] for g in r["games"]]
        for sigma in losses:
            masses = [1 / 6, 2 / 3, 1 / 6]
            for p, game in zip(ps, r["games"]):
                qs = [q for _, q in latent_games(p, sigma)]
                masses = [m * (q if game["winner"] == r["participants"][0] else 1 - q) for m, q in zip(masses, qs)]
            losses[sigma] -= math.log(max(1e-15, sum(masses)))
    selected = min(losses, key=lambda s: (losses[s], s))
    return selected, {"method": "chronological-training-calibration", "n": len(complete),
                      "boundary": boundary.isoformat(), "losses": {str(k): v for k, v in losses.items()}}


def train(raw, cutoff, config=None, registry=None):
    from .veto import fit_veto
    config = settings(config)
    rows, exclusions = history(raw, cutoff)
    if not rows:
        raise ValueError("no eligible final series before cutoff")
    required = sorted({FACTORS[k] for k in config["layers"]} | {"availability-conditioned-veto-selection"})
    entries = {f["factor_id"]: f for f in (registry or {}).get("factors", [])}
    for factor in required:
        if factor not in entries or entries[factor].get("status") not in ("active", "candidate"):
            raise ValueError("register non-retired candidate before fitting: " + factor)
        if not entries[factor].get("mechanism") or not entries[factor].get("pre_match_observable"):
            raise ValueError("factor definition missing: " + factor)
    sigma, diagnostic = correlation(rows, cutoff, config)
    model = {"engine_version": VERSION, "sport": "valorant", "status": "experiment",
             "trained_as_of": cutoff, "parameters": config, "parameter_version": digest({"config": config, "sigma": sigma}),
             "training_hash": digest(rows), "training_event_ids": [r["event_id"] for r in rows],
             "training_sources": sorted({r["source_url"] for r in rows}),
             "training_n": len(rows), "exclusions": exclusions, "registry_hash": digest(registry),
             "factor_ids": required, "strength": fit_strength(rows, cutoff, config),
             "shared_state_sigma": sigma, "correlation_fit": diagnostic,
             "veto": fit_veto(rows, cutoff, config),
             "map_samples": dict(Counter(g["map"] for r in rows for g in r["games"]))}
    model["model_version"] = VERSION + "-" + digest(config)[:10]
    return model
