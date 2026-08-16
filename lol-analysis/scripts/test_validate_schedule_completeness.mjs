#!/usr/bin/env node

import assert from "node:assert/strict";
import { validateSchedule } from "./validate_schedule_completeness.mjs";

function match(matchKey, league, start, team1, team2) {
  return {
    match_key: matchKey,
    start,
    league,
    stage: "Week 1",
    format: "BO3",
    team1,
    team2,
    participant_status: "confirmed",
  };
}

function validSchedule() {
  const lck = match("bo3:1", "LCK", "2026-08-15T16:00:00+08:00", "HLE", "KT");
  const lpl = match("bo3:2", "LPL", "2026-08-15T19:00:00+08:00", "BLG", "WE");
  return {
    schema_version: 2,
    date: "2026-08-15",
    timezone: "Asia/Taipei",
    window: {
      start: "2026-08-15T00:00:00+08:00",
      end: "2026-08-15T23:59:59+08:00",
    },
    target_leagues: ["LCK", "LPL"],
    candidate_set: {
      role: "candidate",
      source: "https://bo3.gg/lol/matches/current",
      checked_at: "2026-08-15T12:00:00+08:00",
      matches: [lck, lpl],
    },
    official_sets: [{
      role: "official_global",
      source: "https://lolesports.com/schedule",
      checked_at: "2026-08-15T12:01:00+08:00",
      coverage_start: "2026-08-15T00:00:00+08:00",
      coverage_end: "2026-08-15T23:59:59+08:00",
      matches: [lck, lpl],
    }],
    independent_coverage: [
      {
        role: "independent_league",
        league: "LCK",
        source: "https://example.test/lck",
        checked_at: "2026-08-15T12:02:00+08:00",
        matches: [lck],
      },
      {
        role: "independent_league",
        league: "LPL",
        source: "https://example.test/lpl",
        checked_at: "2026-08-15T12:02:00+08:00",
        matches: [lpl],
      },
    ],
    complete: true,
    no_matches: false,
    conflicts: [],
    added_matches: [],
    removed_candidates: [],
    matches: [lck, lpl],
  };
}

assert.doesNotThrow(() => validateSchedule(validSchedule()));

{
  const schedule = validSchedule();
  schedule.official_sets[0].matches[1] = {
    ...schedule.official_sets[0].matches[1],
    team1: "TBD",
    participant_status: "placeholder",
  };
  assert.throws(() => validateSchedule(schedule), /placeholder participants|participant_status/);
}

{
  const schedule = validSchedule();
  schedule.independent_coverage[1].source = "https://bo3.gg/lol/matches/current";
  assert.throws(() => validateSchedule(schedule), /cannot be bo3\.gg/);
}

{
  const schedule = validSchedule();
  schedule.independent_coverage.pop();
  assert.throws(() => validateSchedule(schedule), /missing target league LPL/);
}

{
  const schedule = validSchedule();
  schedule.independent_coverage[1].matches[0] = {
    ...schedule.independent_coverage[1].matches[0],
    team1: "TES",
  };
  assert.throws(() => validateSchedule(schedule), /same confirmed matches/);
}

{
  const legacy = validSchedule();
  legacy.schema_version = 1;
  delete legacy.official_sets;
  delete legacy.independent_coverage;
  assert.throws(() => validateSchedule(legacy), /schema_version must be 2/);
}

console.log("OK: validate_schedule_completeness regression tests");
