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
const matchAudits = [];
const sweepProbabilities = [];
let winnerBrier = 0;
let winnerLogLoss = 0;
let exactScoreLogLoss = 0;
let winnerCorrect = 0;
let exactScoreCorrect = 0;
let actualSweeps = 0;
let twoOneModes = 0;
let coverageMisses = 0;

for (const [index, match] of input.matches.entries()) {
  const label = match.id || `matches[${index}]`;
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
  if (typeof match.scenario_covered !== "boolean") {
    fail(`${label}.scenario_covered must be true or false`);
  }

  const sideAWin = probabilities.a_2_0 + probabilities.a_2_1;
  const actualSideAWin = match.actual_score.startsWith("a_") ? 1 : 0;
  const clippedWinner = Math.min(1 - 1e-12, Math.max(1e-12, sideAWin));
  const actualScoreProbability = Math.max(1e-12, probabilities[match.actual_score]);
  const modeScore = Object.entries(probabilities).sort((left, right) => right[1] - left[1])[0][0];
  const sweepProbability = probabilities.a_2_0 + probabilities.b_2_0;
  const isSweep = match.actual_score.endsWith("2_0");
  const isTwoOneMode = modeScore.endsWith("2_1");
  const scenarioCovered = match.scenario_covered;

  winnerBrier += (sideAWin - actualSideAWin) ** 2;
  winnerLogLoss += -(actualSideAWin * Math.log(clippedWinner) + (1 - actualSideAWin) * Math.log(1 - clippedWinner));
  exactScoreLogLoss += -Math.log(actualScoreProbability);
  winnerCorrect += (sideAWin >= 0.5) === Boolean(actualSideAWin) ? 1 : 0;
  exactScoreCorrect += modeScore === match.actual_score ? 1 : 0;
  actualSweeps += isSweep ? 1 : 0;
  twoOneModes += isTwoOneMode ? 1 : 0;
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
  });
}

const count = input.matches.length;
const sweepDistribution = poissonBinomial(sweepProbabilities);
const atLeastActualSweeps = sweepDistribution
  .slice(actualSweeps)
  .reduce((sum, probability) => sum + probability, 0);
const twoOneModeRate = twoOneModes / count;
const warnings = [];

if (count >= 4 && twoOneModeRate >= 0.8) {
  warnings.push("SCORE_MODE_CONCENTRATION: at least 80% of BO3 modes are 2-1; audit shared series-state and veto-scenario mixing.");
}
if (coverageMisses > 0) {
  warnings.push("SCENARIO_COVERAGE_MISS: at least one realized lineup/veto path was absent from the pre-match scenario mixture.");
}
if (count < 20) {
  warnings.push("SMALL_SAMPLE: diagnostic batch only; do not claim long-run calibration from this cohort.");
}

const output = {
  matches: matchAudits,
  summary: {
    match_count: count,
    winner_correct: winnerCorrect,
    exact_score_correct: exactScoreCorrect,
    winner_brier: round(winnerBrier / count),
    winner_log_loss: round(winnerLogLoss / count),
    exact_score_log_loss: round(exactScoreLogLoss / count),
    expected_sweeps: round(sweepProbabilities.reduce((sum, value) => sum + value, 0), 2),
    actual_sweeps: actualSweeps,
    probability_at_least_actual_sweeps: round(atLeastActualSweeps, 5),
    two_one_mode_rate: round(twoOneModeRate, 4),
    scenario_coverage_misses: coverageMisses,
  },
  warnings,
};

console.log(JSON.stringify(output, null, 2));
