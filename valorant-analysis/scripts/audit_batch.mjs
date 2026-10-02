#!/usr/bin/env node

import fs from "node:fs";

function usage() {
  console.error("Usage: node audit_batch.mjs <input.json|->");
  process.exit(2);
}

function fail(message) {
  console.error(`ERROR: ${message}`);
  process.exit(1);
}

function finitePercent(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 100) {
    fail(`${label} must be a number from 0 to 100`);
  }
  return value / 100;
}

function nearlyEqual(left, right, tolerance = 0.002) {
  return Math.abs(left - right) <= tolerance;
}

function poissonBinomial(probabilities) {
  let distribution = [1];
  for (const probability of probabilities) {
    const next = Array(distribution.length + 1).fill(0);
    distribution.forEach((mass, count) => {
      next[count] += mass * (1 - probability);
      next[count + 1] += mass * probability;
    });
    distribution = next;
  }
  return distribution;
}

function round(value, digits = 4) {
  return Number(value.toFixed(digits));
}

// v2 stores fractions and scores in participant A/B order. Never read derived
// percentages or infer A/B from the order on a results website.
function normalizeMatch(match) {
  if (match.schema_version !== "2.0") return match;
  if (match.probability_unit !== "fraction" || match.best_of !== 3 || match.scope !== "full-series") {
    fail("v2 batch audit requires fraction probabilities and full-series BO3 records");
  }
  const scores = { "2-0": "a_2_0", "2-1": "a_2_1", "1-2": "b_2_1", "0-2": "b_2_0" };
  if (!scores[match.actual_score]) fail("v2 actual_score must use participant A/B order");
  const distribution = {};
  if (Object.keys(match.score_distribution || {}).some((key) => !scores[key])) {
    fail("v2 BO3 distribution contains a non-terminal score");
  }
  for (const [score, legacy] of Object.entries(scores)) {
    const p = match.score_distribution?.[score];
    if (typeof p !== "number" || !Number.isFinite(p) || p < 0 || p > 1) {
      fail(`v2 score_distribution.${score} must be a fraction from 0 to 1`);
    }
    distribution[legacy] = p * 100;
  }
  return { ...match, id: match.forecast_id || match.event_id,
    score_distribution: distribution, actual_score: scores[match.actual_score] };
}

const inputPath = process.argv[2];
if (!inputPath) usage();

let raw;
try {
  raw = inputPath === "-" ? fs.readFileSync(0, "utf8") : fs.readFileSync(inputPath, "utf8");
} catch (error) {
  fail(`cannot read input: ${error.message}`);
}

let input;
try {
  input = JSON.parse(raw);
} catch (error) {
  fail(`invalid JSON: ${error.message}`);
}

if (!Array.isArray(input.matches) || input.matches.length === 0) {
  fail("matches must be a non-empty array");
}

const validScores = new Set(["a_2_0", "a_2_1", "b_2_1", "b_2_0"]);
const coverageDimensions = ["lineup_by_map", "first_bans", "map_picks", "pick_owners", "decider"];
const matchAudits = [];
const sweepProbabilities = [];
let winnerBrier = 0;
let winnerLogLoss = 0;
let exactScoreLogLoss = 0;
let winnerCorrect = 0;
let exactScoreCorrect = 0;
let actualSweeps = 0;
let twoOneModes = 0;
let sweepModes = 0;
let coverageMisses = 0;
let legacyCoverageRecords = 0;
const coverageMissesByDimension = Object.fromEntries(coverageDimensions.map((dimension) => [dimension, 0]));
const notModeledByDimension = Object.fromEntries(coverageDimensions.map((dimension) => [dimension, 0]));
const unknownByDimension = Object.fromEntries(coverageDimensions.map((dimension) => [dimension, 0]));
const seen = new Set();

for (const [index, rawMatch] of input.matches.entries()) {
  const match = normalizeMatch(rawMatch);
  const label = match.id || `matches[${index}]`;
  const identity = match.event_id
    ? JSON.stringify([match.sport, match.event_id, match.snapshot, match.data_cutoff, match.model_version])
    : label;
  if (seen.has(identity)) fail(`${label}: duplicate evaluation identity; select the published snapshot once`);
  seen.add(identity);
  const scoreDistribution = match.score_distribution;
  if (!scoreDistribution || typeof scoreDistribution !== "object") {
    fail(`${label}.score_distribution is required`);
  }

  const probabilities = {};
  for (const score of validScores) {
    probabilities[score] = finitePercent(scoreDistribution[score], `${label}.score_distribution.${score}`);
  }
  const scoreSum = Object.values(probabilities).reduce((sum, value) => sum + value, 0);
  if (!nearlyEqual(scoreSum, 1)) {
    fail(`${label}.score_distribution sums to ${(scoreSum * 100).toFixed(2)}%, expected 100%`);
  }

  if (!validScores.has(match.actual_score)) {
    fail(`${label}.actual_score must be one of ${[...validScores].join(", ")}`);
  }
  let scenarioCoverage;
  let scenarioCovered;
  if (match.scenario_coverage && typeof match.scenario_coverage === "object" && !Array.isArray(match.scenario_coverage)) {
    scenarioCoverage = {};
    for (const dimension of coverageDimensions) {
      const coverage = match.scenario_coverage[dimension];
      if (![true, false, "not_modeled", "unknown"].includes(coverage)) {
        fail(`${label}.scenario_coverage.${dimension} must be true, false, not_modeled or unknown`);
      }
      scenarioCoverage[dimension] = coverage;
      coverageMissesByDimension[dimension] += coverage === false ? 1 : 0;
      notModeledByDimension[dimension] += coverage === "not_modeled" ? 1 : 0;
      unknownByDimension[dimension] += coverage === "unknown" ? 1 : 0;
    }
    scenarioCovered = Object.values(scenarioCoverage).every((value) => value === true);
    // Marginal matches in different scenarios do not establish a joint match.
    if (match.joint_scenario_covered !== undefined) {
      if (typeof match.joint_scenario_covered !== "boolean") fail(`${label}.joint_scenario_covered must be boolean`);
      if (match.joint_scenario_covered && !scenarioCovered) fail(`${label}: joint coverage contradicts dimension coverage`);
      scenarioCovered = scenarioCovered && match.joint_scenario_covered;
    } else if (match.schema_version === "2.0" && scenarioCovered) {
      fail(`${label}: v2 covered dimensions require joint_scenario_covered`);
    }
    if (match.scenarios?.length && match.scenarios.every((scenario) => scenario.id === "unresolved-map-order")
        && Object.values(scenarioCoverage).some((value) => value !== "not_modeled")) {
      fail(`${label}: unresolved-map-order cannot claim modeled lineup/veto coverage`);
    }
  } else if (match.schema_version === "2.0") {
    fail(`${label}: v2 requires dimension-level scenario_coverage`);
  } else if (typeof match.scenario_covered === "boolean") {
    scenarioCovered = match.scenario_covered;
    scenarioCoverage = { legacy_overall: scenarioCovered };
    legacyCoverageRecords += 1;
  } else {
    fail(`${label} requires scenario_coverage or legacy scenario_covered`);
  }

  const sideAWin = probabilities.a_2_0 + probabilities.a_2_1;
  const actualSideAWin = match.actual_score.startsWith("a_") ? 1 : 0;
  const clippedWinner = Math.min(1 - 1e-12, Math.max(1e-12, sideAWin));
  const actualScoreProbability = Math.max(1e-12, probabilities[match.actual_score]);
  const modeScore = Object.entries(probabilities).sort((left, right) => right[1] - left[1])[0][0];
  const sweepProbability = probabilities.a_2_0 + probabilities.b_2_0;
  const isSweep = match.actual_score.endsWith("2_0");
  const isTwoOneMode = modeScore.endsWith("2_1");
  winnerBrier += (sideAWin - actualSideAWin) ** 2;
  winnerLogLoss += -(actualSideAWin * Math.log(clippedWinner) + (1 - actualSideAWin) * Math.log(1 - clippedWinner));
  exactScoreLogLoss += -Math.log(actualScoreProbability);
  winnerCorrect += (sideAWin >= 0.5) === Boolean(actualSideAWin) ? 1 : 0;
  exactScoreCorrect += modeScore === match.actual_score ? 1 : 0;
  actualSweeps += isSweep ? 1 : 0;
  twoOneModes += isTwoOneMode ? 1 : 0;
  sweepModes += modeScore.endsWith("2_0") ? 1 : 0;
  coverageMisses += scenarioCovered ? 0 : 1;
  sweepProbabilities.push(sweepProbability);

  matchAudits.push({
    id: label,
    side_a_win_probability: round(sideAWin * 100, 2),
    actual_score: match.actual_score,
    predicted_mode: modeScore,
    actual_score_probability: round(actualScoreProbability * 100, 2),
    sweep_probability: round(sweepProbability * 100, 2),
    scenario_covered: scenarioCovered,
    scenario_coverage: scenarioCoverage,
    winner_brier_sum: round(2 * (sideAWin - actualSideAWin) ** 2),
  });
}

const count = input.matches.length;
const sweepDistribution = poissonBinomial(sweepProbabilities);
const atLeastActualSweeps = sweepDistribution
  .slice(actualSweeps)
  .reduce((sum, probability) => sum + probability, 0);
const atMostActualSweeps = sweepDistribution.slice(0, actualSweeps + 1)
  .reduce((sum, probability) => sum + probability, 0);
const twoOneModeRate = twoOneModes / count;
const sweepModeRate = sweepModes / count;
const warnings = [];

if (count >= 4 && twoOneModeRate >= 0.8) {
  warnings.push("SCORE_MODE_CONCENTRATION: at least 80% of BO3 modes are 2-1; inspect full distributions and cohort outcomes before changing parameters.");
}
if (count >= 4 && sweepModeRate >= 0.8) {
  warnings.push("SWEEP_MODE_CONCENTRATION: at least 80% of BO3 modes are 2-0; a modal score is not sweep certainty. Inspect total sweep mass before changing parameters.");
}
if (coverageMisses > 0) {
  const dimensions = Object.entries(coverageMissesByDimension)
    .filter(([, misses]) => misses > 0)
    .map(([dimension, misses]) => `${dimension}=${misses}`);
  const detail = dimensions.length > 0 ? ` (${dimensions.join(", ")})` : "";
  warnings.push(`SCENARIO_COVERAGE_MISS: coverage was not established for every realized lineup/veto path${detail}; distinguish misses, unmodeled dimensions and unknown evidence.`);
}
if (legacyCoverageRecords > 0) {
  warnings.push("LEGACY_SCENARIO_COVERAGE: dimension-level lineup/veto coverage was not available for every record.");
}
if (count < 20) {
  warnings.push("SMALL_SAMPLE: diagnostic batch only; do not claim long-run calibration from this cohort.");
}

const output = {
  matches: matchAudits,
  summary: {
    match_count: count,
    objective: "winner_accuracy_then_exact_score",
    winner_accuracy: round(winnerCorrect / count),
    exact_score_accuracy: round(exactScoreCorrect / count),
    winner_correct: winnerCorrect,
    exact_score_correct: exactScoreCorrect,
    winner_brier: round(winnerBrier / count),
    winner_brier_sum: round(2 * winnerBrier / count),
    winner_log_loss: round(winnerLogLoss / count),
    exact_score_log_loss: round(exactScoreLogLoss / count),
    expected_sweeps: round(sweepProbabilities.reduce((sum, value) => sum + value, 0), 2),
    actual_sweeps: actualSweeps,
    probability_at_least_actual_sweeps: round(atLeastActualSweeps, 5),
    probability_at_most_actual_sweeps: round(atMostActualSweeps, 5),
    probability_exactly_actual_sweeps: round(sweepDistribution[actualSweeps], 5),
    two_one_mode_rate: round(twoOneModeRate, 4),
    sweep_mode_rate: round(sweepModeRate, 4),
    scenario_coverage_misses: coverageMisses,
    scenario_coverage_misses_by_dimension: coverageMissesByDimension,
    scenario_not_modeled_by_dimension: notModeledByDimension,
    scenario_unknown_by_dimension: unknownByDimension,
    legacy_scenario_coverage_records: legacyCoverageRecords,
  },
  metric_definitions: {
    winner_brier: "legacy binary (p_A - y_A)^2; range 0-1",
    winner_brier_sum: "sum over A/B/draw; range 0-2; matches shared v2 evaluate for no-draw BO3",
    sweep_tails: "Poisson-binomial assuming independent series; diagnostic, not proof of calibration",
  },
  warnings,
};

console.log(JSON.stringify(output, null, 2));
