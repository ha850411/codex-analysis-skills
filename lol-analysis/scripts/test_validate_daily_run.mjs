#!/usr/bin/env node

import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { validateDailyRun } from "./validate_daily_run.mjs";

const matchKey = "bo3:daily-1";
const start = "2026-08-17T16:00:00+08:00";
const predictedAt = "2026-08-17T12:00:00+08:00";
const tableCell = "等價：ALP ML @1.70；≥1.79 才進場；目前 0u";

function match() {
  return {
    match_key: matchKey,
    start,
    league: "LCK",
    stage: "Rounds 3-4 Legend Group",
    format: "BO3",
    team1: "Alpha",
    team2: "Beta",
    participant_status: "confirmed",
  };
}

function schedule() {
  const scheduled = match();
  return {
    schema_version: 2,
    date: "2026-08-17",
    timezone: "Asia/Taipei",
    window: {
      start: "2026-08-17T00:00:00+08:00",
      end: "2026-08-17T23:59:59+08:00",
    },
    target_leagues: ["LCK"],
    candidate_set: {
      role: "candidate",
      source: "https://bo3.gg/lol/matches/current",
      checked_at: predictedAt,
      matches: [scheduled],
    },
    official_sets: [{
      role: "official_global",
      source: "https://lolesports.com/schedule",
      checked_at: predictedAt,
      coverage_start: "2026-08-17T00:00:00+08:00",
      coverage_end: "2026-08-17T23:59:59+08:00",
      matches: [scheduled],
    }],
    independent_coverage: [{
      role: "independent_league",
      league: "LCK",
      source: "https://example.test/lck",
      checked_at: predictedAt,
      matches: [scheduled],
    }],
    complete: true,
    no_matches: false,
    conflicts: [],
    added_matches: [],
    removed_candidates: [],
    matches: [scheduled],
  };
}

function team(name, suffix, abbreviation) {
  const players = ["Top", "Jungle", "Mid", "ADC", "Support"].map(
    (position) => `${position}${suffix}`,
  );
  const seriesKey = `lck-2026-08-10-${suffix}`;
  return {
    name,
    abbreviation,
    last_series: {
      series_key: seriesKey,
      played_at: "2026-08-10T16:00:00+08:00",
      players,
      source: "https://example.test/last-series",
      checked_at: predictedAt,
    },
    projected_lineup: {
      players: [...players],
      status: "established",
      source_kind: "stable_recent_starters",
      source: "https://lol.fandom.com/wiki/Example_Team",
      checked_at: predictedAt,
      established_basis: {
        series_keys: [seriesKey, `lck-2026-08-06-${suffix}`],
        roster_sources: [{
          url: "https://lol.fandom.com/wiki/Example_Team",
          kind: "leaguepedia_roster",
          checked_at: predictedAt,
        }],
        rotation_candidates: [],
      },
    },
    recent_series: {
      league: "LCK",
      event: "LCK 2026 Rounds 3-4",
      searched_at: predictedAt,
      search_complete: true,
      insufficient_reason: null,
      series: [
        {
          series_key: seriesKey,
          played_at: "2026-08-10T16:00:00+08:00",
          opponent: name === "Alpha" ? "Gamma" : "Delta",
          score: "2-1",
          format: "BO3",
          patch: "26.16",
          players: [...players],
          source: "https://example.test/last-series",
          checked_at: predictedAt,
        },
        {
          series_key: `lck-2026-08-06-${suffix}`,
          played_at: "2026-08-06T16:00:00+08:00",
          opponent: name === "Alpha" ? "Delta" : "Gamma",
          score: "0-2",
          format: "BO3",
          patch: "26.15",
          players: [...players],
          source: "https://example.test/previous-series",
          checked_at: predictedAt,
        },
      ],
    },
  };
}

function evidence() {
  return {
    schema_version: 7,
    factor_registry_snapshot: {
      schema_version: 1,
      source: ".automation-state/lol/history/factor-registry.json",
      checked_at: predictedAt,
      factors: [
        {
          factor_id: "long-term-strength-shrinkage-prior",
          status: "active",
          used_for_prediction: true,
        },
        {
          factor_id: "recent-regime-and-opponent-adjusted-performance",
          status: "active",
          used_for_prediction: true,
        },
        {
          factor_id: "draft-champion-pool-fearless-and-adjustment",
          status: "active",
          used_for_prediction: true,
        },
      ],
    },
    forecasts: [{
      match_key: matchKey,
      scheduled_start: start,
      predicted_at: predictedAt,
      snapshot: "established-lineup/pre-draft",
      evaluation_status: "prospective_pre_match",
      teams: [team("Alpha", "A", "ALP"), team("Beta", "B", "BET")],
      competition: {
        league: "LCK",
        event: "LCK 2026 Rounds 3-4",
        stage: "Rounds 3-4 Legend Group",
        format: "BO3",
      },
      patch_context: {
        league: "LCK",
        event: "LCK 2026 Rounds 3-4",
        stage: "Rounds 3-4 Legend Group",
        status: "confirmed",
        value: "26.16",
        checked_at: predictedAt,
        conflicts: [],
        sources: [{
          url: "https://example.test/official-match-page",
          kind: "official_match_page",
          league: "LCK",
          event: "LCK 2026 Rounds 3-4",
          stage: "Rounds 3-4 Legend Group",
          checked_at: predictedAt,
        }],
      },
      recent_direct_h2h: {
        searched_at: predictedAt,
        search_complete: true,
        sources: ["https://example.test/h2h"],
        matches: [],
      },
      lineup_uncertainties: [],
      model_ensemble: {
        target_team: "Alpha",
        models: [
          {
            name: "strength-prior",
            kind: "baseline_prior",
            probability_team: "Alpha",
            series_probability: 0.65,
            weight: 0.3,
            evidence: "opponent-adjusted prior",
            factor_ids: ["long-term-strength-shrinkage-prior"],
          },
          {
            name: "recent-event",
            kind: "recent_event",
            probability_team: "Alpha",
            series_probability: 0.60,
            weight: 0.4,
            evidence: "same-event recent form",
            evidence_refs: [
              "lck-2026-08-10-A",
              "lck-2026-08-06-A",
              "lck-2026-08-10-B",
              "lck-2026-08-06-B",
            ],
            factor_ids: ["recent-regime-and-opponent-adjusted-performance"],
          },
          {
            name: "underdog-countermodel",
            kind: "underdog_countermodel",
            probability_team: "Alpha",
            series_probability: 0.55,
            weight: 0.3,
            evidence: "Beta repeatable paths",
            factor_ids: ["draft-champion-pool-fearless-and-adjustment"],
          },
        ],
        central_probability: 0.60,
        spread: 0.10,
      },
      series_distribution: {
        outcomes: {
          "2-0": 0.30,
          "2-1": 0.30,
          "1-2": 0.25,
          "0-2": 0.15,
        },
        reported_mode: "2-0",
      },
      series_generation: {
        method: "conditional_game_tree",
        probability_team: "Alpha",
        nodes: [
          {
            path: "ROOT",
            team1_game_win_probability: 0.5,
            evidence: "balanced opening-side scenario",
          },
          {
            path: "W",
            team1_game_win_probability: 0.6,
            evidence: "Alpha response after a game-one win",
          },
          {
            path: "L",
            team1_game_win_probability: 0.7,
            evidence: "Alpha response after a game-one loss",
          },
          {
            path: "WL",
            team1_game_win_probability: 0.5454545454545454,
            evidence: "decider after Alpha wins then loses",
          },
          {
            path: "LW",
            team1_game_win_probability: 0.5454545454545454,
            evidence: "decider after Alpha loses then wins",
          },
        ],
      },
      betting: { stake_units: 0 },
    }],
  };
}

function probabilities() {
  const common = { match_key: matchKey };
  return {
    tolerance: 0.2,
    checks: [
      { ...common, name: "exact score", type: "sum", values: [30, 30, 25, 15] },
      { ...common, name: "Alpha win", type: "equal", left: 60, right: [30, 30] },
      {
        ...common,
        name: "confidence",
        type: "weighted_confidence",
        value: 70,
        components: {
          dataCompleteness: 70,
          freshness: 70,
          lineupCertainty: 70,
          regimeRelevance: 70,
          modelStability: 70,
        },
        rawWeighted: 70,
        applyNonCompensatoryCap: false,
        fragilityTriggers: [],
      },
    ],
  };
}

function decisions() {
  return {
    schema_version: 2,
    generated_at: "2026-08-17T12:30:00+08:00",
    market_coverage: {
      status: "full",
      checked_market_types: ["ML", "Spread", "Totals"],
      unavailable_or_unmapped_market_types: [],
      market_checks: [
        { match_key: matchKey, format: "BO3", market_family: "series_ml", line: null, status: "priced", evaluated_selection_count: 2, artifact_path: "odds-daily-1.json" },
        { match_key: matchKey, format: "BO3", market_family: "series_spread", line: 1.5, status: "priced", evaluated_selection_count: 2, artifact_path: "odds-daily-1.json" },
        { match_key: matchKey, format: "BO3", market_family: "series_total_maps", line: 2.5, status: "priced", evaluated_selection_count: 2, artifact_path: "odds-daily-1.json" },
      ],
    },
    market_evaluations: [
      {
        evaluation_id: "alp-ml",
        match_key: matchKey,
        selection: "ALP ML",
        market_family: "series_ml",
        selection_side: "team1",
        line: null,
        model_probability: 0.60,
        betting_probability: 0.57,
        current_odds: 1.70,
        minimum_acceptable_odds: 1.79,
        adjusted_ev: -0.031,
        market_gate: "not_required",
        hard_blockers: [],
        source_artifact: "odds-daily-1.json",
      },
      {
        evaluation_id: "bet-ml",
        match_key: matchKey,
        selection: "BET ML",
        market_family: "series_ml",
        selection_side: "team2",
        line: null,
        model_probability: 0.40,
        betting_probability: 0.37,
        current_odds: 2.40,
        minimum_acceptable_odds: 2.76,
        adjusted_ev: -0.112,
        market_gate: "not_required",
        hard_blockers: [],
        source_artifact: "odds-daily-1.json",
      },
      {
        evaluation_id: "alp-plus-1.5",
        match_key: matchKey,
        selection: "ALP +1.5",
        market_family: "series_spread",
        selection_side: "team1",
        line: 1.5,
        model_probability: 0.85,
        betting_probability: 0.82,
        current_odds: 1.15,
        minimum_acceptable_odds: 1.25,
        adjusted_ev: -0.057,
        market_gate: "pass",
        hard_blockers: [],
        source_artifact: "odds-daily-1.json",
      },
      {
        evaluation_id: "bet-minus-1.5",
        match_key: matchKey,
        selection: "BET -1.5",
        market_family: "series_spread",
        selection_side: "team2",
        line: -1.5,
        model_probability: 0.15,
        betting_probability: 0.12,
        current_odds: 6.50,
        minimum_acceptable_odds: 8.50,
        adjusted_ev: -0.22,
        market_gate: "pass",
        hard_blockers: [],
        source_artifact: "odds-daily-1.json",
      },
      {
        evaluation_id: "over-2.5",
        match_key: matchKey,
        selection: "Over 2.5",
        market_family: "series_total_maps",
        selection_side: "over",
        line: 2.5,
        model_probability: 0.55,
        betting_probability: 0.52,
        current_odds: 1.80,
        minimum_acceptable_odds: 1.97,
        adjusted_ev: -0.064,
        market_gate: "pass",
        hard_blockers: [],
        source_artifact: "odds-daily-1.json",
      },
      {
        evaluation_id: "under-2.5",
        match_key: matchKey,
        selection: "Under 2.5",
        market_family: "series_total_maps",
        selection_side: "under",
        line: 2.5,
        model_probability: 0.45,
        betting_probability: 0.42,
        current_odds: 2.00,
        minimum_acceptable_odds: 2.43,
        adjusted_ev: -0.16,
        market_gate: "pass",
        hard_blockers: [],
        source_artifact: "odds-daily-1.json",
      },
    ],
    matches: [{
      match_key: matchKey,
      action: "price_watch",
      selection: "ALP ML",
      market_evaluation_id: "alp-ml",
      current_odds: 1.7,
      betting_probability: 0.57,
      minimum_acceptable_odds: 1.79,
      adjusted_ev: -0.031,
      model_confidence: 0.7,
      stake_units: 0,
      hard_blockers: [],
      trigger: "價格升至 1.79 後重跑",
      reason: "當前價未達門檻",
      table_cell: tableCell,
    }],
    ranking: [{ rank: 1, match_key: matchKey, rationale: "唯一場次" }],
    all_zero_audit: {
      why_no_bet_now: "所有已映射市場皆未達底價",
      closest_candidate_match_key: matchKey,
      rerun_triggers: ["任一候選價格達底價"],
    },
  };
}

function report() {
  return `分析正文：ALP 與 BET\n\n### 簡表總結\n\n| 比賽 | 核心預測 | 決策 |\n|---|---|---|\n| ALP vs BET | ALP 2-0 | ${tableCell} |\n`;
}

function validRun() {
  return {
    schedule: schedule(),
    evidence: evidence(),
    probabilities: probabilities(),
    decisions: decisions(),
    report: report(),
  };
}

function setProjectedLineup(run, teamIndex = 0) {
  const forecast = run.evidence.forecasts[0];
  const forecastTeam = forecast.teams[teamIndex];
  forecast.snapshot = "pre-lineup/pre-draft";
  forecastTeam.projected_lineup = {
    players: [...forecastTeam.last_series.players],
    status: "projected",
    source_kind: "latest_formal_series",
    source: "https://example.test/last-series",
    checked_at: predictedAt,
    recheck_by: "2026-08-17T15:30:00+08:00",
  };
}

assert.doesNotThrow(() => validateDailyRun(validRun()));

{
  const run = validRun();
  run.evidence.schema_version = 6;
  assert.throws(() => validateDailyRun(run), /must use schema_version 7/);
}

{
  const run = validRun();
  run.report = run.report.replace("ALP 2-0", "ALP 2-1");
  assert.throws(() => validateDailyRun(run), /score must match/);
}

{
  const run = validRun();
  run.report = run.report.replace("ALP 2-0", "BET 2-0");
  assert.throws(() => validateDailyRun(run), /predicted winner abbreviation/);
}

{
  const run = validRun();
  run.report = run.report.replace("ALP vs BET", "Alpha vs BET");
  assert.throws(() => validateDailyRun(run), /team abbreviations only/);
}

{
  const run = validRun();
  delete run.evidence.forecasts[0].teams[0].abbreviation;
  assert.throws(() => validateDailyRun(run), /abbreviation is required/);
}

{
  const run = validRun();
  run.probabilities.checks[0].values = [25, 35, 25, 15];
  assert.throws(() => validateDailyRun(run), /must match series_distribution/);
}

{
  const run = validRun();
  run.decisions.market_evaluations.find(
    (evaluation) => evaluation.evaluation_id === "over-2.5",
  ).model_probability = 0.56;
  assert.throws(
    () => validateDailyRun(run),
    /model_probability must be derived from series_distribution/,
  );
}

{
  const run = validRun();
  delete run.probabilities.checks[0].match_key;
  assert.throws(() => validateDailyRun(run), /match_key is required/);
}

{
  const run = validRun();
  run.evidence.forecasts[0].competition.stage = "Wrong Stage";
  run.evidence.forecasts[0].patch_context.stage = "Wrong Stage";
  run.evidence.forecasts[0].patch_context.sources[0].stage = "Wrong Stage";
  assert.throws(() => validateDailyRun(run), /scope must match the verified schedule/);
}

{
  const run = validRun();
  run.decisions.matches[0].model_confidence = 0.69;
  assert.throws(() => validateDailyRun(run), /model confidence must match/);
}

{
  const run = validRun();
  setProjectedLineup(run);
  assert.throws(
    () => validateDailyRun(run),
    /requires a concrete lineup_uncertainty with named candidates/,
  );
}

{
  const run = validRun();
  setProjectedLineup(run);
  run.evidence.forecasts[0].lineup_uncertainties = [{
    team: "Alpha",
    position: "Jungle",
    candidates: ["JungleA", "AltJungle"],
    scenarios: [
      {
        starter: "JungleA",
        probability: 0.6,
        team_series_probability: 0.60,
        evidence: "latest formal series",
      },
      {
        starter: "AltJungle",
        probability: 0.4,
        team_series_probability: 0.56,
        evidence: "recent official rotation",
      },
    ],
    recheck_by: "2026-08-17T15:30:00+08:00",
    resolution_trigger: "official match roster",
  }];
  const decision = run.decisions.matches[0];
  const evaluation = run.decisions.market_evaluations.find(
    (item) => item.evaluation_id === decision.market_evaluation_id,
  );
  decision.action = "bet_now";
  decision.current_odds = 2.1;
  decision.adjusted_ev = 0.197;
  decision.stake_units = 0.25;
  decision.trigger = null;
  decision.table_cell = "立即可打：ALP ML @2.10；底價 1.79；0.25u";
  evaluation.current_odds = decision.current_odds;
  evaluation.adjusted_ev = decision.adjusted_ev;
  run.decisions.all_zero_audit = null;
  run.report = report().replace(tableCell, decision.table_cell);
  assert.throws(() => validateDailyRun(run), /unresolved lineup uncertainty/);
}

{
  const run = validRun();
  const decision = run.decisions.matches[0];
  decision.trigger = "雙方正式先發一致後再進場";
  decision.table_cell = "等先發：ALP ML @1.70；正式先發一致後再進場；目前 0u";
  run.report = report().replace(tableCell, decision.table_cell);
  assert.throws(
    () => validateDailyRun(run),
    /cannot be used as a wait-for-lineup condition/,
  );
}

{
  const run = validRun();
  const forecast = run.evidence.forecasts[0];
  forecast.snapshot = "established-lineup/pre-draft";
  forecast.teams.forEach((forecastTeam) => {
    forecastTeam.projected_lineup = {
      players: [...forecastTeam.last_series.players],
      status: "established",
      source_kind: "stable_recent_starters",
      source: "https://lol.fandom.com/wiki/Example_Team",
      checked_at: predictedAt,
      established_basis: {
        series_keys: forecastTeam.recent_series.series
          .slice(0, 2)
          .map((series) => series.series_key),
        roster_sources: [{
          url: "https://lol.fandom.com/wiki/Example_Team",
          kind: "leaguepedia_roster",
          checked_at: predictedAt,
        }],
        rotation_candidates: [],
      },
    };
  });
  const decision = run.decisions.matches[0];
  const evaluation = run.decisions.market_evaluations.find(
    (item) => item.evaluation_id === decision.market_evaluation_id,
  );
  decision.action = "bet_now";
  decision.current_odds = 2.1;
  decision.adjusted_ev = 0.197;
  decision.stake_units = 0.25;
  decision.trigger = null;
  decision.table_cell = "立即可打：ALP ML @2.10；底價 1.79；0.25u";
  evaluation.current_odds = decision.current_odds;
  evaluation.adjusted_ev = decision.adjusted_ev;
  run.decisions.all_zero_audit = null;
  run.report = report().replace(tableCell, decision.table_cell);
  assert.doesNotThrow(() => validateDailyRun(run));
}

{
  const emptyRun = fs.mkdtempSync(path.join(os.tmpdir(), "lol-daily-run-missing-"));
  const script = path.join(path.dirname(fileURLToPath(import.meta.url)), "validate_daily_run.mjs");
  const result = spawnSync(process.execPath, [script, emptyRun], { encoding: "utf8" });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /missing required daily-run artifact/);
  fs.rmSync(emptyRun, { recursive: true, force: true });
}

console.log("OK: validate_daily_run regression tests");
