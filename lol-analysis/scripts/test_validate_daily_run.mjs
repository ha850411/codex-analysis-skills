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
const tableCell = "等價：Alpha ML @1.80；≥2.04 才進場；目前 0u";

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

function team(name, suffix) {
  const players = ["Top", "Jungle", "Mid", "ADC", "Support"].map(
    (position) => `${position}${suffix}`,
  );
  const seriesKey = `lck-2026-08-10-${suffix}`;
  return {
    name,
    last_series: {
      series_key: seriesKey,
      played_at: "2026-08-10T16:00:00+08:00",
      players,
      source: "https://example.test/last-series",
      checked_at: predictedAt,
    },
    projected_lineup: { players: [...players] },
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
    schema_version: 4,
    forecasts: [{
      match_key: matchKey,
      scheduled_start: start,
      predicted_at: predictedAt,
      snapshot: "pre-lineup/pre-draft",
      evaluation_status: "prospective_pre_match",
      teams: [team("Alpha", "A"), team("Beta", "B")],
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
            series_probability: 0.65,
            weight: 0.3,
            evidence: "opponent-adjusted prior",
          },
          {
            name: "recent-event",
            kind: "recent_event",
            series_probability: 0.60,
            weight: 0.4,
            evidence: "same-event recent form",
            evidence_refs: [
              "lck-2026-08-10-A",
              "lck-2026-08-06-A",
              "lck-2026-08-10-B",
              "lck-2026-08-06-B",
            ],
          },
          {
            name: "underdog-countermodel",
            kind: "underdog_countermodel",
            series_probability: 0.55,
            weight: 0.3,
            evidence: "Beta repeatable paths",
          },
        ],
        central_probability: 0.60,
        spread: 0.10,
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
    schema_version: 1,
    generated_at: "2026-08-17T12:30:00+08:00",
    market_coverage: {
      status: "partial",
      checked_market_types: ["ML"],
      unavailable_or_unmapped_market_types: ["map handicap"],
    },
    matches: [{
      match_key: matchKey,
      action: "price_watch",
      selection: "Alpha ML",
      current_odds: 1.8,
      betting_probability: 0.5,
      minimum_acceptable_odds: 2.04,
      adjusted_ev: -0.1,
      model_confidence: 0.7,
      stake_units: 0,
      hard_blockers: [],
      trigger: "價格升至 2.04 後重跑",
      reason: "當前價未達門檻",
      table_cell: tableCell,
    }],
    ranking: [{ rank: 1, match_key: matchKey, rationale: "唯一場次" }],
    all_zero_audit: {
      why_no_bet_now: "唯一已映射市場未達底價",
      closest_candidate_match_key: matchKey,
      rerun_triggers: ["價格達 2.04"],
    },
  };
}

function report() {
  return `分析正文\n\n### 簡表總結\n\n| 比賽 | 決策 |\n|---|---|\n| Alpha vs Beta | ${tableCell} |\n`;
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

assert.doesNotThrow(() => validateDailyRun(validRun()));

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
  decision.action = "bet_now";
  decision.current_odds = 2.1;
  decision.adjusted_ev = 0.05;
  decision.stake_units = 0.25;
  decision.trigger = null;
  decision.table_cell = "立即可打：Alpha ML @2.10；底價 2.04；0.25u";
  run.decisions.all_zero_audit = null;
  run.report = report().replace(tableCell, decision.table_cell);
  assert.throws(() => validateDailyRun(run), /unresolved lineup uncertainty/);
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
