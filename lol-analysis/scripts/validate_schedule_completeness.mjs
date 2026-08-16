#!/usr/bin/env node

import fs from "node:fs";
import { pathToFileURL } from "node:url";

const FORMATS = new Set(["BO1", "BO2", "BO3", "BO5"]);
const PARTICIPANT_STATUS = new Set(["confirmed", "resolved_from_bracket"]);

function fail(message) {
  throw new Error(message);
}

function object(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    fail(`${label} must be an object`);
  }
  return value;
}

function nonemptyString(value, label) {
  if (typeof value !== "string" || value.trim() === "") {
    fail(`${label} must be a non-empty string`);
  }
  return value;
}

function timestamp(value, label) {
  nonemptyString(value, label);
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) fail(`${label} must be an ISO-8601 timestamp`);
  return parsed;
}

function stringList(value, label, allowEmpty = false) {
  if (
    !Array.isArray(value) ||
    (!allowEmpty && value.length === 0) ||
    value.some((item) => typeof item !== "string" || item.trim() === "")
  ) {
    fail(`${label} must be ${allowEmpty ? "a" : "a non-empty"} string list`);
  }
  if (new Set(value).size !== value.length) fail(`${label} must not contain duplicates`);
  return value;
}

function isBo3Source(source) {
  try {
    return new URL(source).hostname.toLowerCase().endsWith("bo3.gg");
  } catch {
    fail(`invalid source URL: ${source}`);
  }
}

function validateResolutionEvidence(match, label) {
  const evidence = object(match.resolution_evidence, `${label}.resolution_evidence`);
  const officialBracketUrl = nonemptyString(
    evidence.official_bracket_url,
    `${label}.resolution_evidence.official_bracket_url`,
  );
  if (isBo3Source(officialBracketUrl)) {
    fail(`${label}.resolution_evidence.official_bracket_url cannot be bo3.gg`);
  }
  const candidateUrl = nonemptyString(
    evidence.candidate_url,
    `${label}.resolution_evidence.candidate_url`,
  );
  if (!isBo3Source(candidateUrl)) {
    fail(`${label}.resolution_evidence.candidate_url must be bo3.gg`);
  }
  const corroboratingSources = stringList(
    evidence.corroborating_sources,
    `${label}.resolution_evidence.corroborating_sources`,
  );
  if (corroboratingSources.some(isBo3Source)) {
    fail(`${label}.resolution_evidence.corroborating_sources cannot include bo3.gg`);
  }
  timestamp(evidence.resolved_at, `${label}.resolution_evidence.resolved_at`);
  nonemptyString(evidence.rationale, `${label}.resolution_evidence.rationale`);
}

function validateMatch(raw, label, windowStart, windowEnd, expectedLeague = null) {
  const match = object(raw, label);
  const matchKey = nonemptyString(match.match_key, `${label}.match_key`);
  const start = timestamp(match.start, `${label}.start`);
  if (start < windowStart || start > windowEnd) fail(`${label}.start is outside the window`);
  const league = nonemptyString(match.league, `${label}.league`);
  if (expectedLeague !== null && league !== expectedLeague) {
    fail(`${label}.league must equal its coverage league`);
  }
  nonemptyString(match.stage, `${label}.stage`);
  if (!FORMATS.has(match.format)) fail(`${label}.format is invalid`);
  const team1 = nonemptyString(match.team1, `${label}.team1`);
  const team2 = nonemptyString(match.team2, `${label}.team2`);
  if (team1 === team2) fail(`${label} teams must be different`);
  if (/^(tbd|to be determined|unknown)$/i.test(team1) || /^(tbd|to be determined|unknown)$/i.test(team2)) {
    fail(`${label} cannot use placeholder participants`);
  }
  if (!PARTICIPANT_STATUS.has(match.participant_status)) {
    fail(`${label}.participant_status is invalid`);
  }
  if (match.participant_status === "resolved_from_bracket") {
    validateResolutionEvidence(match, label);
  } else if (match.resolution_evidence !== undefined && match.resolution_evidence !== null) {
    fail(`${label}.resolution_evidence is only valid for resolved_from_bracket`);
  }
  return { ...match, match_key: matchKey };
}

function validateSourceSet(raw, label, role, windowStart, windowEnd, expectedLeague = null) {
  const sourceSet = object(raw, label);
  if (sourceSet.role !== role) fail(`${label}.role must be ${role}`);
  const source = nonemptyString(sourceSet.source, `${label}.source`);
  if (isBo3Source(source)) fail(`${label}.source cannot be bo3.gg`);
  timestamp(sourceSet.checked_at, `${label}.checked_at`);
  if (role === "official_global") {
    if (timestamp(sourceSet.coverage_start, `${label}.coverage_start`) !== windowStart) {
      fail(`${label}.coverage_start must equal the report window start`);
    }
    if (timestamp(sourceSet.coverage_end, `${label}.coverage_end`) !== windowEnd) {
      fail(`${label}.coverage_end must equal the report window end`);
    }
  }
  if (!Array.isArray(sourceSet.matches)) fail(`${label}.matches must be an array`);
  const matches = sourceSet.matches.map((match, index) =>
    validateMatch(match, `${label}.matches[${index}]`, windowStart, windowEnd, expectedLeague),
  );
  const keys = matches.map((match) => match.match_key);
  if (new Set(keys).size !== keys.length) fail(`${label}.matches contains duplicate match keys`);
  return matches;
}

function matchIdentity(match) {
  return [
    match.start,
    match.league,
    match.stage,
    match.format,
    match.team1,
    match.team2,
    match.participant_status,
  ].join("\u0000");
}

function toMap(matches, label) {
  const result = new Map();
  for (const match of matches) {
    const identity = matchIdentity(match);
    if (result.has(match.match_key) && result.get(match.match_key) !== identity) {
      fail(`${label} has conflicting identities for ${match.match_key}`);
    }
    result.set(match.match_key, identity);
  }
  return result;
}

function assertSameSet(left, right, label) {
  if (
    left.size !== right.size ||
    [...left].some(([key, identity]) => right.get(key) !== identity)
  ) {
    fail(`${label} must contain exactly the same confirmed matches`);
  }
}

export function validateSchedule(payload) {
  object(payload, "root");
  if (payload.schema_version !== 2) fail("schema_version must be 2");
  nonemptyString(payload.date, "date");
  if (payload.timezone !== "Asia/Taipei") fail("timezone must be Asia/Taipei");
  const window = object(payload.window, "window");
  const windowStart = timestamp(window.start, "window.start");
  const windowEnd = timestamp(window.end, "window.end");
  if (windowStart >= windowEnd) fail("window.start must be before window.end");
  const targetLeagues = stringList(payload.target_leagues, "target_leagues");
  if (payload.complete !== true) fail("complete must be true before prediction or publication");
  if (!Array.isArray(payload.conflicts)) fail("conflicts must be an array");
  if (payload.conflicts.length !== 0) fail("conflicts must be empty when complete=true");

  const candidate = object(payload.candidate_set, "candidate_set");
  if (candidate.role !== "candidate") fail("candidate_set.role must be candidate");
  nonemptyString(candidate.source, "candidate_set.source");
  timestamp(candidate.checked_at, "candidate_set.checked_at");
  if (!Array.isArray(candidate.matches)) fail("candidate_set.matches must be an array");
  stringList(payload.added_matches, "added_matches", true);
  stringList(payload.removed_candidates, "removed_candidates", true);

  if (!Array.isArray(payload.official_sets) || payload.official_sets.length === 0) {
    fail("official_sets must contain at least one official global set");
  }
  const officialMatches = payload.official_sets.flatMap((sourceSet, index) =>
    validateSourceSet(
      sourceSet,
      `official_sets[${index}]`,
      "official_global",
      windowStart,
      windowEnd,
    ),
  );

  if (!Array.isArray(payload.independent_coverage) || payload.independent_coverage.length === 0) {
    fail("independent_coverage must contain at least one source set");
  }
  const coveredLeagues = new Set();
  const independentMatches = payload.independent_coverage.flatMap((sourceSet, index) => {
    const label = `independent_coverage[${index}]`;
    const league = nonemptyString(sourceSet?.league, `${label}.league`);
    if (!targetLeagues.includes(league)) fail(`${label}.league is not a target league`);
    coveredLeagues.add(league);
    return validateSourceSet(
      sourceSet,
      label,
      "independent_league",
      windowStart,
      windowEnd,
      league,
    );
  });
  for (const league of targetLeagues) {
    if (!coveredLeagues.has(league)) fail(`independent coverage is missing target league ${league}`);
  }

  if (!Array.isArray(payload.matches)) fail("matches must be an array");
  const finalMatches = payload.matches.map((match, index) =>
    validateMatch(match, `matches[${index}]`, windowStart, windowEnd),
  );
  if (payload.no_matches !== (finalMatches.length === 0)) {
    fail("no_matches must reflect whether the final match set is empty");
  }
  const finalLeagues = new Set(finalMatches.map((match) => match.league));
  for (const league of finalLeagues) {
    if (!targetLeagues.includes(league)) fail(`matches contains non-target league ${league}`);
  }

  const officialMap = toMap(officialMatches, "official_sets");
  const independentMap = toMap(independentMatches, "independent_coverage");
  const finalMap = toMap(finalMatches, "matches");
  assertSameSet(officialMap, independentMap, "official and independent unions");
  assertSameSet(officialMap, finalMap, "verified schedule and source unions");
  return payload;
}

function main() {
  const input = process.argv[2];
  if (!input) {
    console.error("Usage: validate_schedule_completeness.mjs <schedule-verification.json>");
    process.exit(2);
  }
  try {
    validateSchedule(JSON.parse(fs.readFileSync(input, "utf8")));
    console.log(`OK: ${input}`);
  } catch (error) {
    console.error(`ERROR: ${error.message}`);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
