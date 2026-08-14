#!/usr/bin/env node

import fs from "node:fs";
import { pathToFileURL } from "node:url";

const STATUS = new Set(["prospective_pre_match", "reconstructed_after_start"]);

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

function stringList(value, label, length = null) {
  if (
    !Array.isArray(value) ||
    value.length === 0 ||
    (length !== null && value.length !== length) ||
    value.some((item) => typeof item !== "string" || item.trim() === "")
  ) {
    const suffix = length === null ? "" : ` with ${length} entries`;
    fail(`${label} must be a non-empty string list${suffix}`);
  }
  return value;
}

function samePlayers(left, right) {
  return left.every((player, index) => player === right[index]);
}

function validateTeam(team, label, predictedAt) {
  object(team, label);
  nonemptyString(team.name, `${label}.name`);

  const last = object(team.last_series, `${label}.last_series`);
  const lastPlayed = timestamp(last.played_at, `${label}.last_series.played_at`);
  if (lastPlayed >= predictedAt) fail(`${label}.last_series must predate the forecast`);
  const lastPlayers = stringList(
    last.players,
    `${label}.last_series.players`,
    5,
  );
  nonemptyString(last.source, `${label}.last_series.source`);
  const lastChecked = timestamp(last.checked_at, `${label}.last_series.checked_at`);
  if (lastChecked > predictedAt) fail(`${label}.last_series was checked after predicted_at`);

  const projected = object(team.projected_lineup, `${label}.projected_lineup`);
  const projectedPlayers = stringList(
    projected.players,
    `${label}.projected_lineup.players`,
    5,
  );
  if (!samePlayers(lastPlayers, projectedPlayers)) {
    const change = object(team.change_evidence, `${label}.change_evidence`);
    nonemptyString(change.source, `${label}.change_evidence.source`);
    nonemptyString(change.reason, `${label}.change_evidence.reason`);
    const published = timestamp(
      change.published_at,
      `${label}.change_evidence.published_at`,
    );
    if (published <= lastPlayed) {
      fail(`${label}.change_evidence must be newer than last_series`);
    }
    if (published > predictedAt) {
      fail(`${label}.change_evidence was published after predicted_at`);
    }
    const checked = timestamp(change.checked_at, `${label}.change_evidence.checked_at`);
    if (checked > predictedAt) fail(`${label}.change_evidence was checked after predicted_at`);
  }
}

function validateH2h(h2h, label, predictedAt, scheduledStart) {
  object(h2h, label);
  const searchedAt = timestamp(h2h.searched_at, `${label}.searched_at`);
  if (searchedAt > predictedAt) fail(`${label} was searched after predicted_at`);
  stringList(h2h.sources, `${label}.sources`);
  if (h2h.search_complete !== true) fail(`${label}.search_complete must be true`);
  if (!Array.isArray(h2h.matches)) fail(`${label}.matches must be an array`);

  for (const [index, rawMatch] of h2h.matches.entries()) {
    const match = object(rawMatch, `${label}.matches[${index}]`);
    const playedAt = timestamp(match.played_at, `${label}.matches[${index}].played_at`);
    if (playedAt >= predictedAt) fail(`${label}.matches[${index}] must predate the forecast`);
    const ageDays = (scheduledStart - playedAt) / 86_400_000;
    const comparable =
      ageDays >= 0 &&
      ageDays <= 30 &&
      match.same_event === true &&
      match.comparable_roster === true;
    if (!comparable) continue;

    if (!Array.isArray(match.games) || match.games.length === 0) {
      fail(`${label}.matches[${index}] comparable rematch requires game evidence`);
    }
    for (const [gameIndex, game] of match.games.entries()) {
      object(game, `${label}.matches[${index}].games[${gameIndex}]`);
      nonemptyString(
        game.winner,
        `${label}.matches[${index}].games[${gameIndex}].winner`,
      );
      nonemptyString(
        game.blue_team,
        `${label}.matches[${index}].games[${gameIndex}].blue_team`,
      );
      nonemptyString(
        game.red_team,
        `${label}.matches[${index}].games[${gameIndex}].red_team`,
      );
      stringList(
        game.picks,
        `${label}.matches[${index}].games[${gameIndex}].picks`,
        10,
      );
    }
    stringList(match.mechanisms, `${label}.matches[${index}].mechanisms`);
    const countermodel = object(
      match.direct_rematch_countermodel,
      `${label}.matches[${index}].direct_rematch_countermodel`,
    );
    const probability = countermodel.series_probability;
    const weight = countermodel.ensemble_weight;
    nonemptyString(countermodel.team, `${label}.matches[${index}].direct_rematch_countermodel.team`);
    if (
      typeof probability !== "number" ||
      probability < 0 ||
      probability > 1 ||
      typeof weight !== "number" ||
      weight < 0 ||
      weight > 1
    ) {
      fail(`${label}.matches[${index}] countermodel probability/weight must be 0..1`);
    }
  }
}

function validateForecast(forecast, index) {
  const label = `forecasts[${index}]`;
  object(forecast, label);
  nonemptyString(forecast.match_key, `${label}.match_key`);
  nonemptyString(forecast.snapshot, `${label}.snapshot`);
  const predictedAt = timestamp(forecast.predicted_at, `${label}.predicted_at`);
  const scheduledStart = timestamp(
    forecast.scheduled_start,
    `${label}.scheduled_start`,
  );
  const cutoff = forecast.actual_start
    ? timestamp(forecast.actual_start, `${label}.actual_start`)
    : scheduledStart;
  if (!STATUS.has(forecast.evaluation_status)) {
    fail(`${label}.evaluation_status is invalid`);
  }
  const expectedStatus =
    predictedAt < cutoff ? "prospective_pre_match" : "reconstructed_after_start";
  if (forecast.evaluation_status !== expectedStatus) {
    fail(`${label}.evaluation_status must be ${expectedStatus}`);
  }

  if (!Array.isArray(forecast.teams) || forecast.teams.length !== 2) {
    fail(`${label}.teams must contain exactly two teams`);
  }
  forecast.teams.forEach((team, teamIndex) =>
    validateTeam(team, `${label}.teams[${teamIndex}]`, predictedAt),
  );
  validateH2h(
    forecast.recent_direct_h2h,
    `${label}.recent_direct_h2h`,
    predictedAt,
    scheduledStart,
  );

  const betting = object(forecast.betting, `${label}.betting`);
  if (
    typeof betting.stake_units !== "number" ||
    !Number.isFinite(betting.stake_units) ||
    betting.stake_units < 0
  ) {
    fail(`${label}.betting.stake_units must be a non-negative number`);
  }
  if (
    expectedStatus === "reconstructed_after_start" &&
    betting.stake_units !== 0
  ) {
    fail(`${label} reconstructed forecasts must use 0u`);
  }
}

export function validateSnapshot(payload) {
  object(payload, "root");
  if (payload.schema_version !== 1) fail("schema_version must be 1");
  if (!Array.isArray(payload.forecasts) || payload.forecasts.length === 0) {
    fail("forecasts must be a non-empty array");
  }
  const seen = new Set();
  payload.forecasts.forEach((forecast, index) => {
    validateForecast(forecast, index);
    if (seen.has(forecast.match_key)) fail(`duplicate match_key: ${forecast.match_key}`);
    seen.add(forecast.match_key);
  });
  return payload;
}

function main() {
  const input = process.argv[2];
  if (!input) {
    console.error("Usage: validate_forecast_evidence.mjs <forecast-evidence.json>");
    process.exit(2);
  }
  try {
    validateSnapshot(JSON.parse(fs.readFileSync(input, "utf8")));
    console.log(`OK: ${input}`);
  } catch (error) {
    console.error(`ERROR: ${error.message}`);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) main();
