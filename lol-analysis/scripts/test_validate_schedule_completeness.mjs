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
  const resolved = {
    ...schedule.matches[0],
    participant_status: "resolved_from_bracket",
    resolution_evidence: {
      official_bracket_url: "https://lolesports.com/schedule",
      candidate_url: "https://bo3.gg/lol/matches/hle-vs-kt",
      corroborating_sources: ["https://stake.com/sports/hle-kt"],
      resolved_at: "2026-08-15T12:00:00+08:00",
      rationale: "Completed bracket results uniquely determine both participants.",
    },
  };
  schedule.candidate_set.matches[0] = resolved;
  schedule.official_sets[0].matches[0] = resolved;
  schedule.independent_coverage[0].matches[0] = resolved;
  schedule.matches[0] = resolved;
  assert.doesNotThrow(() => validateSchedule(schedule));
}

{
  const schedule = validSchedule();
  const unresolved = {
    ...schedule.matches[0],
    participant_status: "resolved_from_bracket",
  };
  schedule.candidate_set.matches[0] = unresolved;
  schedule.official_sets[0].matches[0] = unresolved;
  schedule.independent_coverage[0].matches[0] = unresolved;
  schedule.matches[0] = unresolved;
  assert.throws(() => validateSchedule(schedule), /resolution_evidence/);
}

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

function multiSourceSchedule() {
  const schedule = validSchedule();
  schedule.verification_mode = "multi_source_crosscheck";
  delete schedule.official_sets;
  schedule.primary_sets = schedule.independent_coverage.map((source) => ({
    ...structuredClone(source),
    role: "primary_league",
    source: `https://lol.fandom.com/wiki/${source.league}/2026/Season`,
    coverage_start: schedule.window.start,
    coverage_end: schedule.window.end,
    provider_ids: ["leaguepedia"],
    evidence_note: "Synthetic fixture: full daily schedule read from Leaguepedia.",
  }));
  schedule.independent_coverage = schedule.independent_coverage.map((source) => ({
    ...source,
    source: `https://liquipedia.net/leagueoflegends/${source.league}/2026`,
    coverage_start: schedule.window.start,
    coverage_end: schedule.window.end,
    provider_ids: ["liquipedia"],
    evidence_note: "Synthetic fixture: independently maintained full daily schedule.",
  }));
  schedule.official_checks = schedule.target_leagues.map((league) => ({
    league,
    source: "https://lolesports.com/schedule",
    checked_at: "2026-08-15T12:03:00+08:00",
    status: "missing",
    note: "Synthetic regression: Riot omits the event; both independent schedules agree.",
  }));
  return schedule;
}

// Riot omission/unavailability no longer blocks independently corroborated schedules.
for (const status of ["missing", "unavailable", "stale", "consistent"]) {
  const schedule = multiSourceSchedule();
  schedule.official_checks.forEach((check) => { check.status = status; });
  assert.doesNotThrow(() => validateSchedule(schedule));
}

for (const mutate of [
  (s) => { s.independent_coverage[0].provider_ids = ["leaguepedia"]; },
  (s) => { s.independent_coverage[0].source = "https://lol.fandom.com/wiki/Another_page"; },
]) {
  const schedule = multiSourceSchedule();
  mutate(schedule);
  assert.throws(() => validateSchedule(schedule), /independent operators and upstream/);
}

{
  const schedule = multiSourceSchedule();
  schedule.official_checks[0].status = "conflict";
  schedule.official_checks[0].note = "Official announcement postpones this match.";
  assert.throws(() => validateSchedule(schedule), /official announcement conflict/);
}

for (const [mutate, message] of [
  [(s) => s.primary_sets.pop(), /primary coverage is missing target league/],
  [(s) => s.independent_coverage.pop(), /independent coverage is missing target league/],
  [(s) => s.official_checks.pop(), /official checks are missing target league/],
  [(s) => { delete s.primary_sets[0].coverage_start; }, /coverage_start/],
  [(s) => { s.independent_coverage[0].matches[0] = { ...s.matches[0], start: "2026-08-15T17:00:00+08:00" }; }, /same confirmed matches/],
  [(s) => { s.primary_sets[0].source = "https://bo3.gg/lol/matches/current"; }, /cannot be bo3/],
  [(s) => { s.primary_sets[0].matches.push(s.primary_sets[0].matches[0]); }, /duplicate match keys/],
  [(s) => { s.verification_mode = "unchecked"; }, /verification_mode/],
]) {
  const schedule = multiSourceSchedule();
  mutate(schedule);
  assert.throws(() => validateSchedule(schedule), message);
}

{
  const schedule = multiSourceSchedule();
  schedule.no_matches = true;
  schedule.matches = [];
  schedule.candidate_set.matches = [];
  for (const source of [...schedule.primary_sets, ...schedule.independent_coverage]) source.matches = [];
  assert.doesNotThrow(() => validateSchedule(schedule));
  delete schedule.independent_coverage[1].coverage_end;
  assert.throws(() => validateSchedule(schedule), /coverage_end/);
}

console.log("OK: validate_schedule_completeness regression tests");
