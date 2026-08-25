#!/usr/bin/env node

import fs from "node:fs";
import { pathToFileURL } from "node:url";
import { validateSchedule } from "./validate_schedule_completeness.mjs";

const ACTIONS = new Set(["bet_now", "price_watch", "live_only", "pass"]);
const COVERAGE = new Set(["full", "partial", "none"]);
const MARKET_FAMILIES = new Set(["series_ml", "series_spread", "series_total_maps"]);
const MARKET_CHECK_STATUSES = new Set(["priced", "unavailable", "unmapped", "failed"]);
const MARKET_GATE_STATUSES = new Set(["pass", "fail", "not_required"]);
const EPSILON = 0.002;

const REQUIRED_MARKETS_BY_FORMAT = {
  BO3: [
    ["series_ml", null],
    ["series_spread", 1.5],
    ["series_total_maps", 2.5],
  ],
  BO5: [
    ["series_ml", null],
    ["series_spread", 1.5],
    ["series_spread", 2.5],
    ["series_total_maps", 3.5],
    ["series_total_maps", 4.5],
  ],
};

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

function optionalLine(value, label) {
  if (value === null) return null;
  const line = finiteNumber(value, label);
  if (line <= 0 || Math.abs(line * 2 - Math.round(line * 2)) > 1e-9) {
    fail(`${label} must be a positive half-map line`);
  }
  return line;
}

function requiredMarketKey(family, line) {
  return `${family}:${line === null ? "none" : line}`;
}

function scheduleContext(scheduleMatches) {
  if (scheduleMatches === null) return null;
  if (!Array.isArray(scheduleMatches)) fail("schedule context must be an array");
  return scheduleMatches.map((item, index) => {
    if (typeof item === "string") return { match_key: item, format: null };
    const match = object(item, `schedule[${index}]`);
    return {
      match_key: nonemptyString(match.match_key, `schedule[${index}].match_key`),
      format: match.format == null ? null : nonemptyString(match.format, `schedule[${index}].format`),
    };
  });
}

function validateMarketEvaluation(raw, index) {
  const label = `market_evaluations[${index}]`;
  const evaluation = object(raw, label);
  nonemptyString(evaluation.evaluation_id, `${label}.evaluation_id`);
  nonemptyString(evaluation.match_key, `${label}.match_key`);
  nonemptyString(evaluation.selection, `${label}.selection`);
  nonemptyString(evaluation.source_artifact, `${label}.source_artifact`);
  if (!MARKET_FAMILIES.has(evaluation.market_family)) {
    fail(`${label}.market_family is invalid`);
  }
  if (!MARKET_GATE_STATUSES.has(evaluation.market_gate)) {
    fail(`${label}.market_gate is invalid`);
  }
  const validSides = evaluation.market_family === "series_total_maps"
    ? new Set(["over", "under"])
    : new Set(["team1", "team2"]);
  if (!validSides.has(evaluation.selection_side)) {
    fail(`${label}.selection_side is invalid for ${evaluation.market_family}`);
  }

  if (evaluation.market_family === "series_ml") {
    if (evaluation.line !== null) fail(`${label}.line must be null for series_ml`);
    if (evaluation.market_gate !== "not_required") {
      fail(`${label}.market_gate must be not_required for series_ml`);
    }
  } else {
    const line = finiteNumber(evaluation.line, `${label}.line`);
    if (line === 0 || Math.abs(line * 2 - Math.round(line * 2)) > 1e-9) {
      fail(`${label}.line must be a non-zero half-map line`);
    }
    if (evaluation.market_family === "series_total_maps" && line <= 0) {
      fail(`${label}.line must be positive for series_total_maps`);
    }
    if (evaluation.market_gate === "not_required") {
      fail(`${label}.market_gate must explicitly pass or fail for derived map markets`);
    }
  }

  const modelProbability = finiteNumber(
    evaluation.model_probability,
    `${label}.model_probability`,
  );
  const bettingProbability = finiteNumber(
    evaluation.betting_probability,
    `${label}.betting_probability`,
  );
  if (modelProbability <= 0 || modelProbability >= 1) {
    fail(`${label}.model_probability must be between 0 and 1`);
  }
  if (bettingProbability <= 0 || bettingProbability >= 1) {
    fail(`${label}.betting_probability must be between 0 and 1`);
  }
  if (bettingProbability > modelProbability + EPSILON) {
    fail(`${label}.betting_probability cannot exceed model_probability`);
  }
  const currentOdds = optionalOdds(evaluation.current_odds, `${label}.current_odds`);
  if (currentOdds === null) fail(`${label}.current_odds is required for a priced evaluation`);
  const minimumOdds = optionalOdds(
    evaluation.minimum_acceptable_odds,
    `${label}.minimum_acceptable_odds`,
  );
  if (minimumOdds === null) fail(`${label}.minimum_acceptable_odds is required`);
  const expectedMinimum = 1.02 / bettingProbability;
  if (Math.abs(minimumOdds - expectedMinimum) > 0.02) {
    fail(`${label}.minimum_acceptable_odds must equal 1.02 / betting_probability`);
  }
  const adjustedEv = finiteNumber(evaluation.adjusted_ev, `${label}.adjusted_ev`);
  if (Math.abs(adjustedEv - (currentOdds * bettingProbability - 1)) > EPSILON) {
    fail(`${label}.adjusted_ev is inconsistent with current odds and betting probability`);
  }
  const blockers = stringList(evaluation.hard_blockers, `${label}.hard_blockers`, true);
  if (evaluation.market_gate === "fail" && blockers.length === 0) {
    fail(`${label} failed market gate must name a hard blocker`);
  }
  return evaluation;
}

function evaluationsForCheck(evaluations, check) {
  return evaluations.filter((evaluation) => {
    if (
      evaluation.match_key !== check.match_key ||
      evaluation.market_family !== check.market_family
    ) return false;
    if (check.market_family === "series_ml") return evaluation.line === null;
    return Math.abs(Math.abs(evaluation.line) - check.line) <= 1e-9;
  });
}

function validateMarketCoverage(raw, scheduleMatches, evaluations) {
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
  if (!Array.isArray(coverage.market_checks) || coverage.market_checks.length === 0) {
    fail("market_coverage.market_checks must be a non-empty array");
  }
  const checks = coverage.market_checks.map((rawCheck, index) => {
    const label = `market_coverage.market_checks[${index}]`;
    const check = object(rawCheck, label);
    nonemptyString(check.match_key, `${label}.match_key`);
    const format = nonemptyString(check.format, `${label}.format`);
    if (!MARKET_FAMILIES.has(check.market_family)) {
      fail(`${label}.market_family is invalid`);
    }
    const line = optionalLine(check.line, `${label}.line`);
    if (check.market_family === "series_ml" && line !== null) {
      fail(`${label}.line must be null for series_ml`);
    }
    if (check.market_family !== "series_ml" && line === null) {
      fail(`${label}.line is required for ${check.market_family}`);
    }
    if (!MARKET_CHECK_STATUSES.has(check.status)) fail(`${label}.status is invalid`);
    if (!Number.isInteger(check.evaluated_selection_count) || check.evaluated_selection_count < 0) {
      fail(`${label}.evaluated_selection_count must be a non-negative integer`);
    }
    nonemptyString(check.artifact_path, `${label}.artifact_path`);
    const matchingEvaluations = evaluationsForCheck(evaluations, check);
    if (check.status === "priced") {
      if (check.evaluated_selection_count < 2) {
        fail(`${label} priced check must evaluate both sides of the market`);
      }
      if (check.evaluated_selection_count !== matchingEvaluations.length) {
        fail(`${label}.evaluated_selection_count does not match market_evaluations`);
      }
    } else if (check.evaluated_selection_count !== 0 || matchingEvaluations.length !== 0) {
      fail(`${label} non-priced check cannot contain priced evaluations`);
    }
    return { ...check, format, line };
  });

  const checkIds = checks.map((check) =>
    `${check.match_key}:${requiredMarketKey(check.market_family, check.line)}`
  );
  if (new Set(checkIds).size !== checkIds.length) {
    fail("market_coverage.market_checks contains duplicate match/family/line entries");
  }

  const contexts = scheduleContext(scheduleMatches);
  if (contexts !== null) {
    const expectedKeys = new Set(contexts.map((match) => match.match_key));
    if (checks.some((check) => !expectedKeys.has(check.match_key))) {
      fail("market checks contain a match outside the verified schedule");
    }
    for (const match of contexts) {
      const matchChecks = checks.filter((check) => check.match_key === match.match_key);
      if (matchChecks.length === 0) fail(`${match.match_key} has no market checks`);
      if (match.format !== null && matchChecks.some((check) => check.format !== match.format)) {
        fail(`${match.match_key} market-check format must match the verified schedule`);
      }
      for (const [family, line] of REQUIRED_MARKETS_BY_FORMAT[match.format] ?? [["series_ml", null]]) {
        if (!matchChecks.some((check) =>
          check.market_family === family &&
          (line === null ? check.line === null : Math.abs(check.line - line) <= 1e-9)
        )) {
          fail(`${match.match_key} ${match.format ?? "series"} must check ${requiredMarketKey(family, line)}`);
        }
      }
    }
    if (contexts.some((match) => match.format === "BO3" || match.format === "BO5")) {
      const checkedTypes = new Set(
        coverage.checked_market_types.map((marketType) => marketType.trim().toLowerCase()),
      );
      for (const requiredType of ["ml", "spread", "totals"]) {
        if (!checkedTypes.has(requiredType)) {
          fail(`market_coverage.checked_market_types must include ${requiredType}`);
        }
      }
    }
  }

  for (const evaluation of evaluations) {
    const matchingChecks = checks.filter((check) =>
      check.status === "priced" && evaluationsForCheck([evaluation], check).length === 1
    );
    if (matchingChecks.length !== 1) {
      fail(`${evaluation.evaluation_id} must belong to exactly one priced market check`);
    }
  }

  const pricedCount = checks.filter((check) => check.status === "priced").length;
  const expectedStatus = pricedCount === 0
    ? "none"
    : pricedCount === checks.length ? "full" : "partial";
  if (coverage.status !== expectedStatus) {
    fail(`market_coverage.status must be ${expectedStatus} for its market checks`);
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
  if (currentOdds !== null) {
    nonemptyString(decision.market_evaluation_id, `${label}.market_evaluation_id`);
  } else if (decision.market_evaluation_id !== null) {
    fail(`${label}.market_evaluation_id must be null without current odds`);
  }
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

function validateDecisionLinks(decisions, evaluations) {
  const evaluationsById = new Map();
  for (const evaluation of evaluations) {
    if (evaluationsById.has(evaluation.evaluation_id)) {
      fail(`duplicate market evaluation id: ${evaluation.evaluation_id}`);
    }
    evaluationsById.set(evaluation.evaluation_id, evaluation);
  }
  for (const [index, decision] of decisions.entries()) {
    if (decision.market_evaluation_id === null) continue;
    const evaluation = evaluationsById.get(decision.market_evaluation_id);
    if (!evaluation) fail(`matches[${index}].market_evaluation_id was not found`);
    if (evaluation.match_key !== decision.match_key) {
      fail(`matches[${index}] links to another match's market evaluation`);
    }
    if (evaluation.selection !== decision.selection) {
      fail(`matches[${index}].selection must match its market evaluation`);
    }
    for (const field of ["current_odds", "betting_probability", "minimum_acceptable_odds", "adjusted_ev"]) {
      if (Math.abs(evaluation[field] - decision[field]) > EPSILON) {
        fail(`matches[${index}].${field} must match its market evaluation`);
      }
    }
    if (decision.action === "bet_now" && evaluation.market_gate === "fail") {
      fail(`matches[${index}] cannot bet a market that failed its evidence gate`);
    }
  }
}

function validateQualifyingMarkets(decisions, evaluations) {
  for (const decision of decisions) {
    const qualifying = evaluations.filter((evaluation) =>
      evaluation.match_key === decision.match_key &&
      evaluation.current_odds + 1e-9 >= evaluation.minimum_acceptable_odds &&
      evaluation.adjusted_ev >= 0.02 - EPSILON &&
      evaluation.market_gate !== "fail" &&
      evaluation.hard_blockers.length === 0 &&
      decision.model_confidence >= 0.6
    );
    if (qualifying.length > 0 && decision.action !== "bet_now") {
      fail(`${decision.match_key} has a qualifying evaluated market and must use bet_now`);
    }
    if (decision.action === "bet_now") {
      const selected = evaluations.find(
        (evaluation) => evaluation.evaluation_id === decision.market_evaluation_id,
      );
      if (!selected || !qualifying.includes(selected)) {
        fail(`${decision.match_key} bet_now must select a qualifying market evaluation`);
      }
      const bestAdjustedEv = Math.max(...qualifying.map((evaluation) => evaluation.adjusted_ev));
      if (selected.adjusted_ev < bestAdjustedEv - EPSILON) {
        fail(`${decision.match_key} bet_now must select the highest adjusted-EV eligible market`);
      }
    }
  }
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

export function validateDecisionSlate(payload, report = null, scheduleMatches = null) {
  object(payload, "root");
  if (payload.schema_version !== 2) fail("schema_version must be 2");
  nonemptyString(payload.generated_at, "generated_at");
  if (!Number.isFinite(Date.parse(payload.generated_at))) {
    fail("generated_at must be an ISO-8601 timestamp");
  }
  if (!Array.isArray(payload.market_evaluations)) {
    fail("market_evaluations must be an array");
  }
  const evaluations = payload.market_evaluations.map(validateMarketEvaluation);
  validateMarketCoverage(payload.market_coverage, scheduleMatches, evaluations);
  if (!Array.isArray(payload.matches) || payload.matches.length === 0) {
    fail("matches must be a non-empty array");
  }
  const decisions = payload.matches.map(validateDecision);
  const matchKeys = new Set(decisions.map((decision) => decision.match_key));
  if (matchKeys.size !== decisions.length) fail("matches contains duplicate match keys");
  const contexts = scheduleContext(scheduleMatches);
  if (contexts !== null) {
    const expected = new Set(contexts.map((match) => match.match_key));
    if (
      expected.size !== matchKeys.size ||
      [...expected].some((matchKey) => !matchKeys.has(matchKey))
    ) {
      fail("decision match keys must exactly equal the verified schedule");
    }
  }
  const evaluationMatchKeys = new Set(evaluations.map((evaluation) => evaluation.match_key));
  if ([...evaluationMatchKeys].some((matchKey) => !matchKeys.has(matchKey))) {
    fail("market_evaluations contain a match outside matches");
  }
  validateDecisionLinks(decisions, evaluations);
  validateQualifyingMarkets(decisions, evaluations);
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
  if (!input || !reportPath || !schedulePath) {
    console.error(
      "Usage: validate_decision_slate.mjs <decision-slate.json> <prediction.md> <schedule-verification.json>",
    );
    process.exit(2);
  }
  try {
    const schedule = validateSchedule(JSON.parse(fs.readFileSync(schedulePath, "utf8")));
    validateDecisionSlate(
      JSON.parse(fs.readFileSync(input, "utf8")),
      fs.readFileSync(reportPath, "utf8"),
      schedule.matches,
    );
    console.log(`OK: ${input}`);
  } catch (error) {
    console.error(`ERROR: ${error.message}`);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
