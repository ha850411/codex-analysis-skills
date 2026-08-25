#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { validateProbabilities } from "../../shared/validate_probabilities.mjs";
import { validateDecisionSlate } from "./validate_decision_slate.mjs";
import { validateSnapshot } from "./validate_forecast_evidence.mjs";
import { validateSchedule } from "./validate_schedule_completeness.mjs";

const REQUIRED_FILES = {
  schedule: "schedule-verification.json",
  evidence: "forecast-evidence.json",
  probabilities: "probability-checks.json",
  decisions: "decision-slate.json",
  report: "prediction.md",
};

function fail(message) {
  throw new Error(message);
}

function displayAbbreviation(team, label) {
  if (typeof team.abbreviation !== "string" || team.abbreviation.trim() === "") {
    fail(`${label}.abbreviation is required for daily-summary display`);
  }
  const abbreviation = team.abbreviation.trim();
  if (!/^[A-Z0-9]{2,8}$/.test(abbreviation)) {
    fail(`${label}.abbreviation must be a 2-8 character uppercase alphanumeric code`);
  }
  return abbreviation;
}

function includesDisplayToken(text, token) {
  const escaped = token.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^A-Za-z0-9])${escaped}($|[^A-Za-z0-9])`).test(text);
}

function exactKeySet(actual, expected, label) {
  if (
    actual.size !== expected.size ||
    [...expected].some((matchKey) => !actual.has(matchKey))
  ) {
    fail(`${label} match keys must exactly equal the verified schedule`);
  }
}

function usesLineupWaitLanguage(value) {
  if (typeof value !== "string") return false;
  return [
    /等(?:待)?(?:雙方)?(?:正式)?先發/,
    /(?:須|需|待|尚待).{0,12}(?:雙方)?(?:正式)?先發/,
    /(?:正式)?先發(?:尚未|未|待)(?:確認|公布)/,
    /(?:正式)?先發一致/,
    /確認先發.{0,4}(?:後|才|且)/,
  ].some((pattern) => pattern.test(value));
}

function validateEvidenceCoverage(evidence, schedule) {
  if (evidence.schema_version !== 7) {
    fail("forecast-evidence.json must use schema_version 7 for a daily run");
  }
  validateSnapshot(evidence);

  const scheduleByKey = new Map(
    schedule.matches.map((match) => [match.match_key, match]),
  );
  exactKeySet(
    new Set(evidence.forecasts.map((forecast) => forecast.match_key)),
    new Set(scheduleByKey.keys()),
    "forecast evidence",
  );

  for (const forecast of evidence.forecasts) {
    const scheduled = scheduleByKey.get(forecast.match_key);
    if (Date.parse(forecast.scheduled_start) !== Date.parse(scheduled.start)) {
      fail(`${forecast.match_key} forecast start must match the verified schedule`);
    }
    if (
      forecast.competition.league !== scheduled.league ||
      forecast.competition.stage !== scheduled.stage ||
      forecast.competition.format !== scheduled.format
    ) {
      fail(`${forecast.match_key} competition scope must match the verified schedule`);
    }
    const forecastTeams = new Set(forecast.teams.map((team) => team.name));
    const scheduledTeams = new Set([scheduled.team1, scheduled.team2]);
    if (
      forecastTeams.size !== scheduledTeams.size ||
      [...scheduledTeams].some((team) => !forecastTeams.has(team))
    ) {
      fail(`${forecast.match_key} teams must match the verified schedule`);
    }
    const abbreviations = forecast.teams.map((team, teamIndex) =>
      displayAbbreviation(team, `${forecast.match_key}.teams[${teamIndex}]`)
    );
    if (new Set(abbreviations).size !== abbreviations.length) {
      fail(`${forecast.match_key} team abbreviations must be unique`);
    }
  }
}

function validateDecisionEligibility(evidence, decisions) {
  const decisionByKey = new Map(
    decisions.matches.map((decision) => [decision.match_key, decision]),
  );
  for (const forecast of evidence.forecasts) {
    const decision = decisionByKey.get(forecast.match_key);
    const statusByTeam = new Map(
      forecast.teams.map((team) => [team.name, team.projected_lineup.status]),
    );
    const uncertaintyTeams = new Set(
      forecast.lineup_uncertainties.map((uncertainty) => uncertainty.team),
    );
    const projectedTeams = forecast.teams
      .filter((team) => team.projected_lineup.status === "projected")
      .map((team) => team.name);
    for (const team of projectedTeams) {
      if (!uncertaintyTeams.has(team)) {
        fail(
          `${forecast.match_key} projected lineup for ${team} requires a concrete ` +
          "lineup_uncertainty with named candidates",
        );
      }
    }
    for (const team of uncertaintyTeams) {
      if (statusByTeam.get(team) !== "projected") {
        fail(`${forecast.match_key} lineup uncertainty for ${team} requires projected status`);
      }
    }

    const hasUnresolvedLineup = projectedTeams.length > 0 || uncertaintyTeams.size > 0;
    if (hasUnresolvedLineup && decision.action === "bet_now") {
      fail(
        `${forecast.match_key} unresolved lineup uncertainty cannot use bet_now; ` +
        "publish a conditional decision or create a post-lineup snapshot",
      );
    }
    if (!hasUnresolvedLineup) {
      const decisionLanguage = [
        decision.reason,
        decision.trigger,
        decision.table_cell,
        ...(Array.isArray(decision.hard_blockers) ? decision.hard_blockers : []),
      ];
      if (decisionLanguage.some(usesLineupWaitLanguage)) {
        fail(
          `${forecast.match_key} established or confirmed lineups cannot be used as ` +
          "a wait-for-lineup condition",
        );
      }
    }
  }
}

function scoreOrder(format) {
  if (format === "BO1") return ["1-0", "0-1"];
  if (format === "BO2") return ["2-0", "1-1", "0-2"];
  if (format === "BO3") return ["2-0", "2-1", "1-2", "0-2"];
  if (format === "BO5") return ["3-0", "3-1", "3-2", "2-3", "1-3", "0-3"];
  fail(`unsupported format ${format}`);
}

function markdownCells(line) {
  const trimmed = line.trim();
  if (!trimmed.startsWith("|")) return [];
  return trimmed
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((cell) => cell.trim());
}

function validateReportTeamDisplay(evidence, report) {
  for (const forecast of evidence.forecasts) {
    for (const [teamIndex, team] of forecast.teams.entries()) {
      const abbreviation = displayAbbreviation(
        team,
        `${forecast.match_key}.teams[${teamIndex}]`,
      );
      if (!includesDisplayToken(report, abbreviation)) {
        fail(`${forecast.match_key} report must display team abbreviation ${abbreviation}`);
      }
      if (team.name !== abbreviation && report.includes(team.name)) {
        fail(
          `${forecast.match_key} report must use team abbreviations only; ` +
          `found full team name ${team.name}`,
        );
      }
    }
  }
}

function validateReportedModes(evidence, decisions, report) {
  const summary = report.slice(report.indexOf("簡表總結"));
  const summaryLines = summary.split(/\r?\n/);
  const header = summaryLines
    .map(markdownCells)
    .find((cells) => cells.some((cell) => cell.includes("核心預測")));
  if (!header) fail("最終簡表必須包含核心預測欄");
  const corePredictionIndex = header.findIndex((cell) => cell.includes("核心預測"));
  const decisionByKey = new Map(
    decisions.matches.map((decision) => [decision.match_key, decision]),
  );
  for (const forecast of evidence.forecasts) {
    const decision = decisionByKey.get(forecast.match_key);
    const rows = summaryLines.filter((line) => line.includes(decision.table_cell));
    if (rows.length !== 1) {
      fail(`${forecast.match_key} final summary must contain exactly one decision row`);
    }
    const corePrediction = markdownCells(rows[0])[corePredictionIndex];
    if (!corePrediction) {
      fail(`${forecast.match_key} final summary is missing its core prediction cell`);
    }
    const score = forecast.series_distribution.reported_mode;
    const [left, right] = score.split("-").map(Number);
    const winner = left === right
      ? null
      : forecast.teams[left > right ? 0 : 1];
    const winnerAbbreviation = winner === null
      ? null
      : displayAbbreviation(winner, `${forecast.match_key}.predicted_winner`);
    if (
      winnerAbbreviation !== null &&
      !includesDisplayToken(corePrediction, winnerAbbreviation)
    ) {
      fail(
        `${forecast.match_key} final summary must use the predicted winner ` +
        `abbreviation ${winnerAbbreviation}`,
      );
    }
    if (
      !corePrediction.includes(score) &&
      !corePrediction.includes(score.replace("-", ":"))
    ) {
      fail(`${forecast.match_key} final summary score must match series_distribution.reported_mode`);
    }
  }
}

function validateProbabilityCoverage(probabilities, scheduleKeys, decisions, evidence) {
  validateProbabilities(probabilities);
  const expected = new Set(scheduleKeys);
  const checksByKey = new Map();

  for (const [index, check] of probabilities.checks.entries()) {
    if (typeof check.match_key !== "string" || check.match_key.trim() === "") {
      fail(`probability-checks.json checks[${index}].match_key is required`);
    }
    if (!expected.has(check.match_key)) {
      fail(`probability-checks.json contains an unverified match key: ${check.match_key}`);
    }
    if (!checksByKey.has(check.match_key)) checksByKey.set(check.match_key, []);
    checksByKey.get(check.match_key).push(check);
  }
  exactKeySet(new Set(checksByKey.keys()), expected, "probability checks");

  const decisionByKey = new Map(
    decisions.matches.map((decision) => [decision.match_key, decision]),
  );
  const forecastByKey = new Map(
    evidence.forecasts.map((forecast) => [forecast.match_key, forecast]),
  );
  for (const matchKey of expected) {
    const checks = checksByKey.get(matchKey);
    for (const requiredType of ["sum", "equal", "weighted_confidence"]) {
      if (!checks.some((check) => check.type === requiredType)) {
        fail(`${matchKey} probability checks require ${requiredType}`);
      }
    }
    const confidenceChecks = checks.filter(
      (check) => check.type === "weighted_confidence",
    );
    if (confidenceChecks.length !== 1) {
      fail(`${matchKey} must contain exactly one weighted_confidence check`);
    }
    const decisionConfidence = decisionByKey.get(matchKey).model_confidence;
    if (confidenceChecks[0].value / 100 !== decisionConfidence) {
      fail(`${matchKey} model confidence must match decision-slate.json`);
    }

    const forecast = forecastByKey.get(matchKey);
    const exactScoreChecks = checks.filter((check) => check.type === "sum");
    if (exactScoreChecks.length !== 1) {
      fail(`${matchKey} must contain exactly one exact-score sum check`);
    }
    const expectedValues = scoreOrder(forecast.competition.format).map(
      (score) => forecast.series_distribution.outcomes[score] * 100,
    );
    if (
      exactScoreChecks[0].values.length !== expectedValues.length ||
      expectedValues.some(
        (value, index) => Math.abs(value - exactScoreChecks[0].values[index]) > 0.2,
      )
    ) {
      fail(`${matchKey} exact-score check must match series_distribution outcome order`);
    }
  }
}

function scoreParts(score, label) {
  const match = /^(\d+)-(\d+)$/.exec(score);
  if (!match) fail(`${label} is not a valid exact-series score`);
  return [Number(match[1]), Number(match[2])];
}

function derivedMarketProbability(forecast, evaluation) {
  let total = 0;
  for (const [score, probability] of Object.entries(forecast.series_distribution.outcomes)) {
    const [team1Games, team2Games] = scoreParts(score, `${forecast.match_key}.${score}`);
    let wins = false;
    if (evaluation.market_family === "series_ml") {
      wins = evaluation.selection_side === "team1"
        ? team1Games > team2Games
        : team2Games > team1Games;
    } else if (evaluation.market_family === "series_spread") {
      const margin = evaluation.selection_side === "team1"
        ? team1Games - team2Games
        : team2Games - team1Games;
      wins = margin + evaluation.line > 0;
    } else if (evaluation.market_family === "series_total_maps") {
      const maps = team1Games + team2Games;
      wins = evaluation.selection_side === "over"
        ? maps > evaluation.line
        : maps < evaluation.line;
    }
    if (wins) total += probability;
  }
  return total;
}

function validateMarketEvaluationProbabilities(evidence, decisions) {
  const forecastByKey = new Map(
    evidence.forecasts.map((forecast) => [forecast.match_key, forecast]),
  );
  for (const [index, evaluation] of decisions.market_evaluations.entries()) {
    const forecast = forecastByKey.get(evaluation.match_key);
    if (!forecast) {
      fail(`market_evaluations[${index}] references an unknown forecast`);
    }
    const expected = derivedMarketProbability(forecast, evaluation);
    if (Math.abs(evaluation.model_probability - expected) > 0.002) {
      fail(
        `${evaluation.evaluation_id} model_probability must be derived from ` +
        `series_distribution (expected ${expected.toFixed(4)})`,
      );
    }
  }
}

export function validateDailyRun({
  schedule: rawSchedule,
  evidence,
  probabilities,
  decisions,
  report,
}) {
  const schedule = validateSchedule(rawSchedule);
  const scheduleKeys = schedule.matches.map((match) => match.match_key);
  validateEvidenceCoverage(evidence, schedule);
  validateDecisionSlate(decisions, report, schedule.matches);
  validateDecisionEligibility(evidence, decisions);
  validateProbabilityCoverage(probabilities, scheduleKeys, decisions, evidence);
  validateMarketEvaluationProbabilities(evidence, decisions);
  validateReportTeamDisplay(evidence, report);
  validateReportedModes(evidence, decisions, report);
  return {
    pass: true,
    match_count: scheduleKeys.length,
    match_keys: scheduleKeys,
  };
}

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, "utf8"));
}

function main() {
  const runDirectory = process.argv[2];
  if (!runDirectory) {
    console.error("Usage: validate_daily_run.mjs <run-directory>");
    process.exit(2);
  }
  try {
    const resolved = path.resolve(runDirectory);
    const files = Object.fromEntries(
      Object.entries(REQUIRED_FILES).map(([key, filename]) => {
        const filePath = path.join(resolved, filename);
        if (!fs.existsSync(filePath)) fail(`missing required daily-run artifact: ${filename}`);
        return [key, filePath];
      }),
    );
    const result = validateDailyRun({
      schedule: readJson(files.schedule),
      evidence: readJson(files.evidence),
      probabilities: readJson(files.probabilities),
      decisions: readJson(files.decisions),
      report: fs.readFileSync(files.report, "utf8"),
    });
    console.log(`OK: ${resolved} (${result.match_count} matches)`);
  } catch (error) {
    console.error(`ERROR: ${error.message}`);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
