#!/usr/bin/env python3
"""Build a reproducible, no-market MLB baseline from official public data.

This is the skill's numerical fallback, not a betting model.  It uses only games
completed before ``as_of``, shrinks team run rates and starter RA9 toward the
same-season league environment, estimates score dispersion from those completed
games, and delegates coherent market derivation to ``simulate_scores.py``.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from simulate_scores import _validate_config, simulate


MODEL_VERSION = "mlb-public-baseline-v1.0.0"
TEAM_PRIOR_GAMES = 30.0
STARTER_PRIOR_INNINGS = 40.0
WORKLOAD_PRIOR_STARTS = 5.0
WORKLOAD_PRIOR_IP = 5.2
MIN_COMPLETED_GAMES = 100
USER_AGENT = "codex-mlb-public-baseline/1.0"


class BaselineError(RuntimeError):
    pass


def _fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise BaselineError(f"official MLB data request failed: {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BaselineError(f"official MLB data returned a non-object: {url}")
    return payload


def _iso_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise BaselineError("as_of must include a timezone offset")
    return parsed


def _schedule_url(start: str, end: str, *, hydrate: bool = False) -> str:
    query: dict[str, str | int] = {
        "sportId": 1,
        "gameType": "R",
        "startDate": start,
        "endDate": end,
    }
    if hydrate:
        query["hydrate"] = "probablePitcher,team,venue"
    return "https://statsapi.mlb.com/api/v1/schedule?" + urllib.parse.urlencode(query)


def _all_games(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        game
        for date_bucket in payload.get("dates", [])
        if isinstance(date_bucket, dict)
        for game in date_bucket.get("games", [])
        if isinstance(game, dict)
    ]


def completed_games_before(payload: dict[str, Any], as_of: datetime) -> list[dict[str, Any]]:
    completed: list[dict[str, Any]] = []
    for game in _all_games(payload):
        try:
            game_time = _iso_datetime(str(game["gameDate"]))
            away = game["teams"]["away"]
            home = game["teams"]["home"]
            away_score = away["score"]
            home_score = home["score"]
        except (KeyError, TypeError, ValueError):
            continue
        if (
            game_time >= as_of
            or game.get("status", {}).get("abstractGameState") != "Final"
            or isinstance(away_score, bool)
            or isinstance(home_score, bool)
            or not isinstance(away_score, int)
            or not isinstance(home_score, int)
            or away_score == home_score
        ):
            continue
        completed.append(game)
    return completed


def fit_public_environment(completed: list[dict[str, Any]]) -> dict[str, Any]:
    if len(completed) < MIN_COMPLETED_GAMES:
        raise BaselineError(
            f"public baseline needs at least {MIN_COMPLETED_GAMES} completed games; "
            f"found {len(completed)}"
        )
    team_totals: dict[int, dict[str, float]] = {}
    away_scores: list[int] = []
    home_scores: list[int] = []
    for game in completed:
        away = game["teams"]["away"]
        home = game["teams"]["home"]
        away_id = int(away["team"]["id"])
        home_id = int(home["team"]["id"])
        away_score = int(away["score"])
        home_score = int(home["score"])
        away_scores.append(away_score)
        home_scores.append(home_score)
        for team_id, scored, allowed in (
            (away_id, away_score, home_score),
            (home_id, home_score, away_score),
        ):
            row = team_totals.setdefault(team_id, {"games": 0.0, "runs_for": 0.0, "runs_against": 0.0})
            row["games"] += 1
            row["runs_for"] += scored
            row["runs_against"] += allowed

    away_mean = statistics.fmean(away_scores)
    home_mean = statistics.fmean(home_scores)
    global_mean = (away_mean + home_mean) / 2.0
    profiles: dict[str, dict[str, float]] = {}
    for team_id, row in team_totals.items():
        games = row["games"]
        profiles[str(team_id)] = {
            "games": games,
            "offense_runs_per_game": (
                row["runs_for"] + TEAM_PRIOR_GAMES * global_mean
            ) / (games + TEAM_PRIOR_GAMES),
            "defense_runs_per_game": (
                row["runs_against"] + TEAM_PRIOR_GAMES * global_mean
            ) / (games + TEAM_PRIOR_GAMES),
        }

    away_var = statistics.variance(away_scores)
    home_var = statistics.variance(home_scores)
    covariance = sum(
        (away - away_mean) * (home - home_mean)
        for away, home in zip(away_scores, home_scores)
    ) / (len(completed) - 1)
    shared_variance = math.log1p(max(0.0, covariance) / (away_mean * home_mean))
    away_total_variance = math.log1p(max(0.0, away_var - away_mean) / away_mean**2)
    home_total_variance = math.log1p(max(0.0, home_var - home_mean) / home_mean**2)
    shared_variance = min(shared_variance, away_total_variance, home_total_variance)
    dispersion = {
        "shared_game_sigma": round(math.sqrt(max(0.0, shared_variance)), 6),
        "away_team_sigma": round(
            math.sqrt(max(0.0025, away_total_variance - shared_variance)), 6
        ),
        "home_team_sigma": round(
            math.sqrt(max(0.0025, home_total_variance - shared_variance)), 6
        ),
    }
    return {
        "completed_game_count": len(completed),
        "away_runs_per_game": away_mean,
        "home_runs_per_game": home_mean,
        "team_runs_per_game": global_mean,
        "team_profiles": profiles,
        "dispersion": dispersion,
    }


def _pitcher_url(person_id: int, season_start: str, cutoff_date: str) -> str:
    query = urllib.parse.urlencode(
        {
            "stats": "byDateRange",
            "group": "pitching",
            "gameType": "R",
            "startDate": season_start,
            "endDate": cutoff_date,
        }
    )
    return f"https://statsapi.mlb.com/api/v1/people/{person_id}/stats?{query}"


def parse_pitcher_projection(
    payload: dict[str, Any], league_ra9: float
) -> dict[str, float | int | str]:
    splits = [
        split
        for block in payload.get("stats", [])
        if isinstance(block, dict)
        for split in block.get("splits", [])
        if isinstance(split, dict) and split.get("sport", {}).get("id") == 1
    ]
    if not splits:
        return {
            "source": "league_fallback_no_mlb_history",
            "games_started": 0,
            "innings": 0.0,
            "projected_ra9": league_ra9,
            "projected_innings": 4.5,
        }
    stat = splits[0].get("stat", {})
    outs = float(stat.get("outs", 0) or 0)
    innings = outs / 3.0
    starts = int(stat.get("gamesStarted", 0) or 0)
    runs = float(stat.get("runs", 0) or 0)
    projected_ra9 = (
        runs + STARTER_PRIOR_INNINGS * league_ra9 / 9.0
    ) / (innings + STARTER_PRIOR_INNINGS) * 9.0
    projected_innings = (
        innings + WORKLOAD_PRIOR_STARTS * WORKLOAD_PRIOR_IP
    ) / (starts + WORKLOAD_PRIOR_STARTS)
    if starts < 3:
        projected_innings = min(projected_innings, 4.5)
    return {
        "source": "same_season_ra9_shrunk",
        "games_started": starts,
        "innings": round(innings, 3),
        "projected_ra9": round(min(max(projected_ra9, 2.0), 8.0), 4),
        "projected_innings": round(min(max(projected_innings, 3.5), 6.5), 3),
    }


def phase_run_means(
    offense: dict[str, float],
    defense: dict[str, float],
    starter: dict[str, float | int | str],
    league_side_mean: float,
    league_global_mean: float,
) -> dict[str, float]:
    offense_factor = offense["offense_runs_per_game"] / league_global_mean
    defense_factor = defense["defense_runs_per_game"] / league_global_mean
    starter_factor = float(starter["projected_ra9"]) / league_global_mean
    projected_ip = float(starter["projected_innings"])
    f5_starter_share = min(5.0, projected_ip) / 5.0
    late_starter_share = min(4.0, max(0.0, projected_ip - 5.0)) / 4.0
    f5_pitching_factor = (
        f5_starter_share * starter_factor + (1.0 - f5_starter_share) * defense_factor
    )
    late_pitching_factor = (
        late_starter_share * starter_factor + (1.0 - late_starter_share) * defense_factor
    )
    f5 = league_side_mean * 5.0 / 9.0 * math.sqrt(offense_factor * f5_pitching_factor)
    late = league_side_mean * 4.0 / 9.0 * math.sqrt(offense_factor * late_pitching_factor)
    return {"f5": round(min(max(f5, 0.2), 7.5), 4), "late": round(min(max(late, 0.15), 6.0), 4)}


def _game_team(game: dict[str, Any], side: str) -> dict[str, Any]:
    return game["teams"][side]


def _probable(game: dict[str, Any], side: str) -> dict[str, Any] | None:
    value = _game_team(game, side).get("probablePitcher")
    return value if isinstance(value, dict) and isinstance(value.get("id"), int) else None


def _confidence(has_away_starter: bool, has_home_starter: bool) -> tuple[float, dict[str, int]]:
    both = has_away_starter and has_home_starter
    components = {
        "dataCompleteness": 58 if both else 43,
        "freshness": 90,
        "lineupCertainty": 45 if both else 30,
        "regimeRelevance": 68,
        "modelStability": 35,
    }
    weighted = (
        0.25 * components["dataCompleteness"]
        + 0.20 * components["freshness"]
        + 0.25 * components["lineupCertainty"]
        + 0.20 * components["regimeRelevance"]
        + 0.10 * components["modelStability"]
    )
    cap = 55 if both else 45
    return round(min(weighted, cap) / 100.0, 4), components


def build_forecast(
    game: dict[str, Any],
    environment: dict[str, Any],
    pitcher_projections: dict[int, dict[str, float | int | str]],
    predicted_at: str,
    iterations: int,
) -> dict[str, Any]:
    away = _game_team(game, "away")
    home = _game_team(game, "home")
    away_id = int(away["team"]["id"])
    home_id = int(home["team"]["id"])
    profiles = environment["team_profiles"]
    if str(away_id) not in profiles or str(home_id) not in profiles:
        raise BaselineError(f"game {game['gamePk']} has a team without completed-game history")
    away_probable = _probable(game, "away")
    home_probable = _probable(game, "home")
    league_ra9 = float(environment["team_runs_per_game"])
    fallback = {
        "source": "league_fallback_tbd_starter",
        "games_started": 0,
        "innings": 0.0,
        "projected_ra9": league_ra9,
        "projected_innings": 4.5,
    }
    away_starter = pitcher_projections.get(int(away_probable["id"]), fallback) if away_probable else fallback
    home_starter = pitcher_projections.get(int(home_probable["id"]), fallback) if home_probable else fallback
    away_means = phase_run_means(
        profiles[str(away_id)], profiles[str(home_id)], home_starter,
        float(environment["away_runs_per_game"]), league_ra9,
    )
    home_means = phase_run_means(
        profiles[str(home_id)], profiles[str(away_id)], away_starter,
        float(environment["home_runs_per_game"]), league_ra9,
    )
    config = {
        "model_version": MODEL_VERSION,
        "game_id": str(game["gamePk"]),
        "iterations": iterations,
        "seed": int(game["gamePk"]) * 1009 + int(predicted_at[:10].replace("-", "")),
        "dispersion": environment["dispersion"],
        "extra_innings": {
            "away_mean_per_half": round(float(environment["away_runs_per_game"]) / 9.0 * 1.35, 4),
            "home_mean_per_half": round(float(environment["home_runs_per_game"]) / 9.0 * 1.35, 4),
        },
        "scenarios": [{
            "name": "public-pre-lineup-baseline", "weight": 1.0,
            "away": {"f5_mean": away_means["f5"], "late_mean_6_to_9": away_means["late"]},
            "home": {"f5_mean": home_means["f5"], "late_mean_6_to_9": home_means["late"]},
        }],
        "markets": {
            "f5_totals": [4.0, 4.5, 5.0],
            "full_totals": [7.5, 8.0, 8.5, 9.0, 9.5],
            "f5_run_lines": [{"team": "away", "line": 0.5}, {"team": "home", "line": -0.5}],
            "full_run_lines": [{"team": "away", "line": 1.5}, {"team": "home", "line": -1.5}],
        },
    }
    simulation = simulate(_validate_config(config))
    confidence, confidence_components = _confidence(away_probable is not None, home_probable is not None)
    missing_data = [
        "official starting lineups and defensive positions",
        "reliever-level recent workload and availability",
        "validated weather, roof, and park run adjustment",
        "external rest-of-season player projections",
        "same-version walk-forward calibration",
    ]
    if away_probable is None:
        missing_data.append(f"{away['team']['name']} probable starter")
    if home_probable is None:
        missing_data.append(f"{home['team']['name']} probable starter")
    sources = [
        "https://statsapi.mlb.com/api/v1/schedule",
        "https://statsapi.mlb.com/api/v1/people/{personId}/stats",
        "mlb-analysis/scripts/build_public_baseline.py",
    ]
    return {
        "game_id": str(game["gamePk"]),
        "predicted_at": predicted_at,
        "first_pitch": _iso_datetime(str(game["gameDate"])).isoformat(),
        "snapshot": "pre-lineup",
        "model_version": MODEL_VERSION,
        "status": "baseline",
        "model_tier": "public-data-baseline",
        "validation_status": "uncalibrated",
        "recommendation_eligible": False,
        "away_team": away["team"]["name"],
        "home_team": home["team"]["name"],
        "venue": game.get("venue", {}).get("name", "TBD"),
        "away_probable_pitcher": away_probable.get("fullName") if away_probable else "TBD",
        "home_probable_pitcher": home_probable.get("fullName") if home_probable else "TBD",
        "away_f5_runs_mean": simulation["f5"]["expected_runs"]["away"],
        "home_f5_runs_mean": simulation["f5"]["expected_runs"]["home"],
        "away_late_runs_mean": away_means["late"],
        "home_late_runs_mean": home_means["late"],
        "away_runs_mean": simulation["full_game"]["expected_runs"]["away"],
        "home_runs_mean": simulation["full_game"]["expected_runs"]["home"],
        "home_win_prob": round(simulation["full_game"]["home_win_pct"] / 100.0, 6),
        "f5_away_win_prob": round(simulation["f5"]["away_win_pct"] / 100.0, 6),
        "f5_tie_prob": round(simulation["f5"]["tie_pct"] / 100.0, 6),
        "f5_home_win_prob": round(simulation["f5"]["home_win_pct"] / 100.0, 6),
        "away_runs_p10": simulation["full_game"]["central_intervals"]["away_80"][0],
        "away_runs_p90": simulation["full_game"]["central_intervals"]["away_80"][1],
        "home_runs_p10": simulation["full_game"]["central_intervals"]["home_80"][0],
        "home_runs_p90": simulation["full_game"]["central_intervals"]["home_80"][1],
        "total_runs_p10": simulation["full_game"]["central_intervals"]["total_80"][0],
        "total_runs_p90": simulation["full_game"]["central_intervals"]["total_80"][1],
        "model_confidence": confidence,
        "confidence_components": confidence_components,
        "missing_data": missing_data,
        "sources": sources,
        "model_inputs": {
            "away_team_profile": profiles[str(away_id)],
            "home_team_profile": profiles[str(home_id)],
            "away_starter": away_starter,
            "home_starter": home_starter,
            "phase_run_means": {"away": away_means, "home": home_means},
        },
        "simulation": simulation,
    }


def build(schedule_precheck: Path, iterations: int) -> dict[str, Any]:
    snapshot = json.loads(schedule_precheck.read_text(encoding="utf-8"))
    game_ids = {int(value) for value in snapshot.get("game_ids", [])}
    if not game_ids:
        raise BaselineError("schedule precheck has no game_ids")
    predicted_at = str(snapshot.get("checked_at", "")).strip()
    as_of = _iso_datetime(predicted_at)
    season = as_of.year
    season_start = f"{season}-03-01"
    cutoff_date = (as_of.astimezone(timezone.utc).date() - timedelta(days=1)).isoformat()
    history_url = _schedule_url(season_start, as_of.date().isoformat())
    history_payload = _fetch_json(history_url)
    completed = completed_games_before(history_payload, as_of)
    environment = fit_public_environment(completed)

    target_start = min(_iso_datetime(str(snapshot["window_start"])), as_of).date().isoformat()
    target_end = _iso_datetime(str(snapshot["window_end"])).date().isoformat()
    target_url = _schedule_url(target_start, target_end, hydrate=True)
    target_games = [game for game in _all_games(_fetch_json(target_url)) if int(game.get("gamePk", -1)) in game_ids]
    found = {int(game["gamePk"]) for game in target_games}
    if found != game_ids:
        raise BaselineError(f"schedule mismatch; missing game IDs: {sorted(game_ids - found)}")

    pitcher_ids = {
        int(probable["id"])
        for game in target_games
        for side in ("away", "home")
        for probable in [_probable(game, side)]
        if probable is not None
    }
    pitcher_projections: dict[int, dict[str, float | int | str]] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_fetch_json, _pitcher_url(pid, season_start, cutoff_date)): pid
            for pid in pitcher_ids
        }
        for future in as_completed(futures):
            pid = futures[future]
            try:
                pitcher_projections[pid] = parse_pitcher_projection(
                    future.result(), float(environment["team_runs_per_game"])
                )
            except BaselineError:
                pitcher_projections[pid] = parse_pitcher_projection(
                    {}, float(environment["team_runs_per_game"])
                )

    forecasts = [
        build_forecast(game, environment, pitcher_projections, predicted_at, iterations)
        for game in sorted(target_games, key=lambda item: item["gameDate"])
    ]
    return {
        "model_version": MODEL_VERSION,
        "model_tier": "public-data-baseline",
        "validation_status": "uncalibrated",
        "recommendation_policy": "probabilities are directional; stake must remain 0u until walk-forward promotion",
        "as_of": predicted_at,
        "history_cutoff": cutoff_date,
        "environment": environment,
        "forecasts": forecasts,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("schedule_precheck", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=75_000)
    args = parser.parse_args()
    if not 50_000 <= args.iterations <= 2_000_000:
        parser.error("--iterations must be between 50000 and 2000000")
    try:
        result = build(args.schedule_precheck, args.iterations)
    except (BaselineError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    print(json.dumps({
        "model_version": result["model_version"],
        "forecast_count": len(result["forecasts"]),
        "output": str(args.output),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
