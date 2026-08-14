#!/usr/bin/env node

import fs from "node:fs";
import { pathToFileURL } from "node:url";

const ACTIONS = new Set(["bet_now", "price_watch", "live_only", "pass"]);
const COVERAGE = new Set(["full", "partial", "none"]);
const EPSILON = 0.002;

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

function finiteNumber(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    fail(`${label} must be a finite number`);
  }
  return value;
}

function optionalOdds(value, label) {
  if (value === null) return null;
  finiteNumber(value, label);
  if (value <= 1) fail(`${label} must be greater than 1`);
  return value;
}

function stringList(value, label, allowEmpty = false) {
  if (
    !Array.isArray(value) ||
    (!allowEmpty && value.length === 0) ||
    value.some((item) => typeof item !== "string" || item.trim() === "")
  ) {
    fail(`${label} must be ${allowEmpty ? "a" : "a non-empty"} string list`);
  }
  return value;
}

function validateMarketCoverage(raw) {
  const coverage = object(raw, "market_coverage");
  if (!COVERAGE.has(coverage.status)) fail("market_coverage.status is invalid");
  stringList(coverage.checked_market_types, "market_coverage.checked_market_types");
  stringList(
    coverage.unavailable_or_unmapped_market_types,
    "market_coverage.unavailable_or_unmapped_market_types",
    true,
  );
  if (
    coverage.status === "partial" &&
    coverage.unavailable_or_unmapped_market_types.length === 0
  ) {
    fail("partial market coverage must list unavailable or unmapped market types");
  }
  return coverage;
}

function validateDecision(raw, index) {
  const label = `matches[${index}]`;
  const decision = object(raw, label);
  nonemptyString(decision.match_key, `${label}.match_key`);
  if (!ACTIONS.has(decision.action)) fail(`${label}.action is invalid`);
  nonemptyString(decision.selection, `${label}.selection`);
  nonemptyString(decision.reason, `${label}.reason`);
  const tableCell = nonemptyString(decision.table_cell, `${label}.table_cell`);
  if (/^\s*0(?:\.0+)?u\s*$/i.test(tableCell)) {
    fail(`${label}.table_cell cannot be only 0u`);
  }

  const stake = finiteNumber(decision.stake_units, `${label}.stake_units`);
  if (stake < 0 || stake > 2 || Math.abs(stake * 4 - Math.round(stake * 4)) > 1e-9) {
    fail(`${label}.stake_units must be a 0.25u increment from 0u to 2u`);
  }
  const blockers = stringList(decision.hard_blockers, `${label}.hard_blockers`, true);
  const confidence = finiteNumber(decision.model_confidence, `${label}.model_confidence`);
  if (confidence < 0 || confidence > 1) {
    fail(`${label}.model_confidence must be between 0 and 1`);
  }
  const currentOdds = optionalOdds(decision.current_odds, `${label}.current_odds`);
  const minimumOdds = optionalOdds(
    decision.minimum_acceptable_odds,
    `${label}.minimum_acceptable_odds`,
  );

  let adjustedEv = null;
  if (decision.betting_probability !== null) {
    const probability = finiteNumber(
      decision.betting_probability,
      `${label}.betting_probability`,
    );
    if (probability <= 0 || probability >= 1) {
      fail(`${label}.betting_probability must be between 0 and 1`);
    }
    if (currentOdds !== null) {
      adjustedEv = finiteNumber(decision.adjusted_ev, `${label}.adjusted_ev`);
      const expected = currentOdds * probability - 1;
      if (Math.abs(adjustedEv - expected) > EPSILON) {
        fail(`${label}.adjusted_ev is inconsistent with current odds and betting probability`);
      }
    } else if (decision.adjusted_ev !== null) {
      fail(`${label}.adjusted_ev must be null without current odds`);
    }
    if (minimumOdds !== null) {
      const expectedMinimum = 1.02 / probability;
      if (Math.abs(minimumOdds - expectedMinimum) > 0.02) {
        fail(`${label}.minimum_acceptable_odds must equal 1.02 / betting_probability`);
      }
    }
  } else if (decision.adjusted_ev !== null) {
    fail(`${label}.adjusted_ev requires betting_probability`);
  }

  const qualifiesOnPrice =
    currentOdds !== null &&
    minimumOdds !== null &&
    currentOdds + 1e-9 >= minimumOdds;

  if (decision.action === "bet_now") {
    if (stake <= 0) fail(`${label} bet_now must use a non-zero stake`);
    if (blockers.length > 0) fail(`${label} bet_now cannot have hard blockers`);
    if (!qualifiesOnPrice) fail(`${label} bet_now price must meet its minimum`);
    if (adjustedEv === null || adjustedEv < 0.02 - EPSILON) {
      fail(`${label} bet_now must have at least 2% adjusted EV`);
    }
    const confidenceCap =
      confidence < 0.6 ? 0 :
        confidence < 0.7 ? 0.25 :
          confidence < 0.8 ? 0.5 :
            confidence < 0.9 ? 1 : 1.5;
    if (stake > confidenceCap) {
      fail(`${label}.stake_units exceeds the model-confidence cap`);
    }
  } else {
    if (stake !== 0) fail(`${label} non-bet action must use 0u`);
    if (qualifiesOnPrice && blockers.length === 0) {
      fail(`${label} qualifying price cannot remain 0u without a hard blocker`);
    }
    if (decision.action === "price_watch") {
      if (minimumOdds === null) fail(`${label} price_watch requires a trigger price`);
      nonemptyString(decision.trigger, `${label}.trigger`);
    } else if (decision.action === "live_only") {
      nonemptyString(decision.trigger, `${label}.trigger`);
    } else if (blockers.length === 0) {
      fail(`${label} pass requires at least one hard blocker`);
    }
  }

  return decision;
}

function validateRanking(raw, matchKeys) {
  if (!Array.isArray(raw) || raw.length !== matchKeys.size) {
    fail("ranking must include every match exactly once");
  }
  const seenRanks = new Set();
  const seenKeys = new Set();
  for (const [index, rawRank] of raw.entries()) {
    const label = `ranking[${index}]`;
    const rank = object(rawRank, label);
    if (!Number.isInteger(rank.rank) || rank.rank < 1) fail(`${label}.rank is invalid`);
    nonemptyString(rank.match_key, `${label}.match_key`);
    nonemptyString(rank.rationale, `${label}.rationale`);
    if (!matchKeys.has(rank.match_key)) fail(`${label}.match_key is not in matches`);
    if (seenRanks.has(rank.rank) || seenKeys.has(rank.match_key)) {
      fail("ranking contains duplicate ranks or match keys");
    }
    seenRanks.add(rank.rank);
    seenKeys.add(rank.match_key);
  }
  const ordered = [...seenRanks].sort((a, b) => a - b);
  if (ordered.some((rank, index) => rank !== index + 1)) {
    fail("ranking ranks must be contiguous from 1");
  }
}

function validateAllZeroAudit(raw, allZero, matchKeys) {
  if (!allZero) {
    if (raw !== null && raw !== undefined) {
      fail("all_zero_audit must be null when the slate has a non-zero stake");
    }
    return;
  }
  const audit = object(raw, "all_zero_audit");
  nonemptyString(audit.why_no_bet_now, "all_zero_audit.why_no_bet_now");
  nonemptyString(audit.closest_candidate_match_key, "all_zero_audit.closest_candidate_match_key");
  if (!matchKeys.has(audit.closest_candidate_match_key)) {
    fail("all_zero_audit.closest_candidate_match_key is not in matches");
  }
  stringList(audit.rerun_triggers, "all_zero_audit.rerun_triggers");
}

function validateReport(report, decisions) {
  const matches = report.match(/簡表總結/g) ?? [];
  if (matches.length !== 1) fail("prediction.md must contain exactly one 簡表總結");
  const summary = report.slice(report.indexOf("簡表總結"));
  for (const [index, decision] of decisions.entries()) {
    if (!summary.includes(decision.table_cell)) {
      fail(`matches[${index}].table_cell is not present in the final summary`);
    }
  }
}

export function validateDecisionSlate(payload, report = null, scheduleKeys = null) {
  object(payload, "root");
  if (payload.schema_version !== 1) fail("schema_version must be 1");
  nonemptyString(payload.generated_at, "generated_at");
  if (!Number.isFinite(Date.parse(payload.generated_at))) {
    fail("generated_at must be an ISO-8601 timestamp");
  }
  validateMarketCoverage(payload.market_coverage);
  if (!Array.isArray(payload.matches) || payload.matches.length === 0) {
    fail("matches must be a non-empty array");
  }
  const decisions = payload.matches.map(validateDecision);
  const matchKeys = new Set(decisions.map((decision) => decision.match_key));
  if (matchKeys.size !== decisions.length) fail("matches contains duplicate match keys");
  if (scheduleKeys !== null) {
    const expected = new Set(scheduleKeys);
    if (
      expected.size !== matchKeys.size ||
      [...expected].some((matchKey) => !matchKeys.has(matchKey))
    ) {
      fail("decision match keys must exactly equal the verified schedule");
    }
  }
  validateRanking(payload.ranking, matchKeys);
  validateAllZeroAudit(
    payload.all_zero_audit,
    decisions.every((decision) => decision.stake_units === 0),
    matchKeys,
  );
  if (report !== null) validateReport(report, decisions);
  return payload;
}

function main() {
  const [input, reportPath, schedulePath] = process.argv.slice(2);
  if (!input || !reportPath) {
    console.error(
      "Usage: validate_decision_slate.mjs <decision-slate.json> <prediction.md> [schedule-verification.json]",
    );
    process.exit(2);
  }
  try {
    const scheduleKeys = schedulePath
      ? JSON.parse(fs.readFileSync(schedulePath, "utf8")).matches.map(
        (match) => match.match_key,
      )
      : null;
    validateDecisionSlate(
      JSON.parse(fs.readFileSync(input, "utf8")),
      fs.readFileSync(reportPath, "utf8"),
      scheduleKeys,
    );
    console.log(`OK: ${input}`);
  } catch (error) {
    console.error(`ERROR: ${error.message}`);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
