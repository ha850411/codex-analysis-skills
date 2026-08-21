#!/usr/bin/env node

import fs from "node:fs";
import { pathToFileURL } from "node:url";

const STATUS = new Set(["prospective_pre_match", "reconstructed_after_start"]);
const MODEL_KINDS = new Set([
  "baseline_prior",
  "recent_event",
  "underdog_countermodel",
  "direct_rematch",
]);
const POSITIONS = new Set(["Top", "Jungle", "Mid", "ADC", "Support"]);
const FORMATS = new Set(["BO1", "BO2", "BO3", "BO5"]);
const PATCH_STATUS = new Set(["confirmed", "scenario"]);
const LINEUP_STATUS = new Set(["confirmed", "established", "projected"]);
const LINEUP_SOURCE_KINDS = new Set([
  "official_match_lineup",
  "official_team_announcement",
  "stable_recent_starters",
  "latest_formal_series",
  "independent_match_page",
]);
const CONFIRMED_LINEUP_SOURCE_KINDS = new Set([
  "official_match_lineup",
  "official_team_announcement",
]);
const ESTABLISHED_LINEUP_SOURCE_KINDS = new Set(["stable_recent_starters"]);
const ROSTER_SOURCE_KINDS = new Set([
  "official_roster",
  "leaguepedia_roster",
  "liquipedia_roster",
]);
const PATCH_SOURCE_KINDS = new Set([
  "official_rulebook",
  "official_announcement",
  "official_match_page",
  "same_stage_match",
  "independent_event_page",
]);
const OFFICIAL_PATCH_SOURCE_KINDS = new Set([
  "official_rulebook",
  "official_announcement",
  "official_match_page",
]);

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

function probability(value, label) {
  if (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1) {
    fail(`${label} must be a number from 0 to 1`);
  }
  return value;
}

function close(left, right, tolerance = 1e-6) {
  return Math.abs(left - right) <= tolerance;
}

function validatePatchContext(forecast, label, predictedAt) {
  const competition = object(forecast.competition, `${label}.competition`);
  const league = nonemptyString(competition.league, `${label}.competition.league`);
  const event = nonemptyString(competition.event, `${label}.competition.event`);
  const stage = nonemptyString(competition.stage, `${label}.competition.stage`);
  if (!FORMATS.has(competition.format)) fail(`${label}.competition.format is invalid`);

  const patch = object(forecast.patch_context, `${label}.patch_context`);
  if (patch.league !== league || patch.event !== event || patch.stage !== stage) {
    fail(`${label}.patch_context scope must match competition league, event, and stage`);
  }
  if (!PATCH_STATUS.has(patch.status)) fail(`${label}.patch_context.status is invalid`);
  const patchCheckedAt = timestamp(patch.checked_at, `${label}.patch_context.checked_at`);
  if (patchCheckedAt > predictedAt) fail(`${label}.patch_context was checked after predicted_at`);
  if (!Array.isArray(patch.sources) || patch.sources.length === 0) {
    fail(`${label}.patch_context.sources must be a non-empty array`);
  }
  let hasOfficialSource = false;
  for (const [index, rawSource] of patch.sources.entries()) {
    const sourceLabel = `${label}.patch_context.sources[${index}]`;
    const source = object(rawSource, sourceLabel);
    nonemptyString(source.url, `${sourceLabel}.url`);
    const kind = nonemptyString(source.kind, `${sourceLabel}.kind`);
    if (!PATCH_SOURCE_KINDS.has(kind)) fail(`${sourceLabel}.kind is invalid`);
    if (OFFICIAL_PATCH_SOURCE_KINDS.has(kind)) hasOfficialSource = true;
    if (source.league !== league || source.event !== event || source.stage !== stage) {
      fail(`${sourceLabel} scope must match competition league, event, and stage`);
    }
    const checkedAt = timestamp(source.checked_at, `${sourceLabel}.checked_at`);
    if (checkedAt > predictedAt) fail(`${sourceLabel} was checked after predicted_at`);
  }
  if (!Array.isArray(patch.conflicts)) fail(`${label}.patch_context.conflicts must be an array`);

  if (patch.status === "confirmed") {
    nonemptyString(patch.value, `${label}.patch_context.value`);
    if (!hasOfficialSource) {
      fail(`${label}.patch_context confirmed status requires an official source`);
    }
    if (patch.conflicts.length !== 0) {
      fail(`${label}.patch_context confirmed status cannot retain conflicts`);
    }
    if (patch.scenarios !== undefined && patch.scenarios !== null) {
      fail(`${label}.patch_context confirmed status cannot include scenarios`);
    }
    return;
  }

  if (patch.value !== null && patch.value !== undefined) {
    fail(`${label}.patch_context scenario status must not use a single value`);
  }
  if (patch.conflicts.length === 0) {
    fail(`${label}.patch_context scenario status requires documented conflicts`);
  }
  if (!Array.isArray(patch.scenarios) || patch.scenarios.length < 2) {
    fail(`${label}.patch_context.scenarios must contain at least two patch scenarios`);
  }
  let weightSum = 0;
  const seenValues = new Set();
  for (const [index, rawScenario] of patch.scenarios.entries()) {
    const scenarioLabel = `${label}.patch_context.scenarios[${index}]`;
    const scenario = object(rawScenario, scenarioLabel);
    const value = nonemptyString(scenario.value, `${scenarioLabel}.value`);
    if (seenValues.has(value)) fail(`${scenarioLabel}.value is duplicated`);
    seenValues.add(value);
    weightSum += probability(scenario.probability, `${scenarioLabel}.probability`);
    nonemptyString(scenario.evidence, `${scenarioLabel}.evidence`);
  }
  if (!close(weightSum, 1)) {
    fail(`${label}.patch_context scenario probabilities must sum to 1`);
  }
}

function validateTeam(
  team,
  label,
  predictedAt,
  scheduledStart,
  requireSeriesKey = false,
  requireLineupState = false,
) {
  object(team, label);
  nonemptyString(team.name, `${label}.name`);

  const last = object(team.last_series, `${label}.last_series`);
  const lastSeriesKey = requireSeriesKey
    ? nonemptyString(last.series_key, `${label}.last_series.series_key`)
    : null;
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
  if (requireLineupState) {
    if (!LINEUP_STATUS.has(projected.status)) {
      fail(`${label}.projected_lineup.status must be confirmed, established, or projected`);
    }
    const sourceKind = nonemptyString(
      projected.source_kind,
      `${label}.projected_lineup.source_kind`,
    );
    if (!LINEUP_SOURCE_KINDS.has(sourceKind)) {
      fail(`${label}.projected_lineup.source_kind is invalid`);
    }
    nonemptyString(projected.source, `${label}.projected_lineup.source`);
    const lineupCheckedAt = timestamp(
      projected.checked_at,
      `${label}.projected_lineup.checked_at`,
    );
    if (lineupCheckedAt > predictedAt) {
      fail(`${label}.projected_lineup was checked after predicted_at`);
    }
    if (projected.status === "confirmed") {
      if (!CONFIRMED_LINEUP_SOURCE_KINDS.has(sourceKind)) {
        fail(`${label}.projected_lineup confirmed status requires an official source`);
      }
      if (projected.recheck_by !== null && projected.recheck_by !== undefined) {
        fail(`${label}.projected_lineup confirmed status cannot include recheck_by`);
      }
    } else if (projected.status === "established") {
      if (!ESTABLISHED_LINEUP_SOURCE_KINDS.has(sourceKind)) {
        fail(`${label}.projected_lineup established status requires stable_recent_starters`);
      }
      if (projected.recheck_by !== null && projected.recheck_by !== undefined) {
        fail(`${label}.projected_lineup established status cannot include recheck_by`);
      }
      const basis = object(
        projected.established_basis,
        `${label}.projected_lineup.established_basis`,
      );
      const seriesKeys = stringList(
        basis.series_keys,
        `${label}.projected_lineup.established_basis.series_keys`,
      );
      if (seriesKeys.length !== 2 || new Set(seriesKeys).size !== 2) {
        fail(
          `${label}.projected_lineup established status requires exactly two unique recent series keys`,
        );
      }
      const recentSeries = object(team.recent_series, `${label}.recent_series`);
      if (!Array.isArray(recentSeries.series) || recentSeries.series.length < 2) {
        fail(`${label}.projected_lineup established status requires two recent series`);
      }
      const latestTwo = recentSeries.series.slice(0, 2);
      const latestKeys = latestTwo.map((series, index) =>
        nonemptyString(
          object(series, `${label}.recent_series.series[${index}]`).series_key,
          `${label}.recent_series.series[${index}].series_key`,
        )
      );
      if (!samePlayers(seriesKeys, latestKeys)) {
        fail(
          `${label}.projected_lineup established series keys must be the latest two series`,
        );
      }
      for (const [index, series] of latestTwo.entries()) {
        const players = stringList(
          series.players,
          `${label}.recent_series.series[${index}].players`,
          5,
        );
        if (!samePlayers(players, projectedPlayers)) {
          fail(
            `${label}.projected_lineup established players must match both latest series`,
          );
        }
      }
      if (!Array.isArray(basis.roster_sources) || basis.roster_sources.length === 0) {
        fail(
          `${label}.projected_lineup established status requires a roster cross-check source`,
        );
      }
      for (const [index, rawRosterSource] of basis.roster_sources.entries()) {
        const rosterLabel =
          `${label}.projected_lineup.established_basis.roster_sources[${index}]`;
        const rosterSource = object(rawRosterSource, rosterLabel);
        nonemptyString(rosterSource.url, `${rosterLabel}.url`);
        const rosterKind = nonemptyString(rosterSource.kind, `${rosterLabel}.kind`);
        if (!ROSTER_SOURCE_KINDS.has(rosterKind)) {
          fail(`${rosterLabel}.kind is invalid`);
        }
        const rosterCheckedAt = timestamp(rosterSource.checked_at, `${rosterLabel}.checked_at`);
        if (rosterCheckedAt > predictedAt) {
          fail(`${rosterLabel} was checked after predicted_at`);
        }
      }
      if (!Array.isArray(basis.rotation_candidates)) {
        fail(
          `${label}.projected_lineup.established_basis.rotation_candidates must be an array`,
        );
      }
      if (basis.rotation_candidates.length !== 0) {
        fail(`${label}.projected_lineup established status cannot retain rotation candidates`);
      }
    } else {
      const recheckBy = timestamp(
        projected.recheck_by,
        `${label}.projected_lineup.recheck_by`,
      );
      if (recheckBy <= predictedAt || recheckBy >= scheduledStart) {
        fail(
          `${label}.projected_lineup.recheck_by must be after predicted_at and before scheduled_start`,
        );
      }
    }
  }
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
  return lastSeriesKey;
}

function expectedScoreKeys(format) {
  if (format === "BO1") return ["1-0", "0-1"];
  if (format === "BO2") return ["2-0", "1-1", "0-2"];
  if (format === "BO3") return ["2-0", "2-1", "1-2", "0-2"];
  if (format === "BO5") return ["3-0", "3-1", "3-2", "2-3", "1-3", "0-3"];
  fail(`unsupported format ${format}`);
}

function validateSeriesDistribution(forecast, label) {
  const distribution = object(
    forecast.series_distribution,
    `${label}.series_distribution`,
  );
  const outcomes = object(
    distribution.outcomes,
    `${label}.series_distribution.outcomes`,
  );
  const expectedScores = expectedScoreKeys(forecast.competition.format);
  const actualScores = Object.keys(outcomes);
  if (
    actualScores.length !== expectedScores.length ||
    expectedScores.some((score) => !Object.hasOwn(outcomes, score))
  ) {
    fail(
      `${label}.series_distribution.outcomes must contain the complete ${forecast.competition.format} score set`,
    );
  }

  let total = 0;
  let maximum = -1;
  for (const score of expectedScores) {
    const outcomeProbability = probability(
      outcomes[score],
      `${label}.series_distribution.outcomes.${score}`,
    );
    total += outcomeProbability;
    maximum = Math.max(maximum, outcomeProbability);
  }
  if (!close(total, 1)) {
    fail(`${label}.series_distribution probabilities must sum to 1`);
  }

  const reportedMode = nonemptyString(
    distribution.reported_mode,
    `${label}.series_distribution.reported_mode`,
  );
  if (!expectedScores.includes(reportedMode)) {
    fail(`${label}.series_distribution.reported_mode is not a valid score`);
  }
  if (!close(outcomes[reportedMode], maximum)) {
    fail(`${label}.series_distribution.reported_mode must be a highest-probability score`);
  }

  const targetTeam = forecast.model_ensemble.target_team;
  const targetIndex = forecast.teams.findIndex((team) => team.name === targetTeam);
  if (targetIndex < 0) {
    fail(`${label}.series_distribution cannot resolve model target team`);
  }
  let targetWinProbability = 0;
  for (const score of expectedScores) {
    const [left, right] = score.split("-").map(Number);
    if ((targetIndex === 0 && left > right) || (targetIndex === 1 && right > left)) {
      targetWinProbability += outcomes[score];
    }
  }
  if (!close(targetWinProbability, forecast.model_ensemble.central_probability)) {
    fail(
      `${label}.series_distribution target-team win sum must equal model_ensemble.central_probability`,
    );
  }
}

function validateRecentSeries(team, label, predictedAt, competition) {
  const recent = object(team.recent_series, `${label}.recent_series`);
  if (recent.league !== competition.league || recent.event !== competition.event) {
    fail(`${label}.recent_series scope must match competition league and event`);
  }
  const searchedAt = timestamp(recent.searched_at, `${label}.recent_series.searched_at`);
  if (searchedAt > predictedAt) {
    fail(`${label}.recent_series was searched after predicted_at`);
  }
  if (recent.search_complete !== true) {
    fail(`${label}.recent_series.search_complete must be true`);
  }
  if (!Array.isArray(recent.series) || recent.series.length > 2) {
    fail(`${label}.recent_series.series must contain the latest zero to two same-event series`);
  }
  if (recent.series.length < 2) {
    nonemptyString(
      recent.insufficient_reason,
      `${label}.recent_series.insufficient_reason`,
    );
  } else if (recent.insufficient_reason !== null && recent.insufficient_reason !== undefined) {
    fail(`${label}.recent_series.insufficient_reason must be null when two series are available`);
  }

  const seriesKeys = [];
  let previousPlayedAt = Number.POSITIVE_INFINITY;
  for (const [index, rawSeries] of recent.series.entries()) {
    const seriesLabel = `${label}.recent_series.series[${index}]`;
    const series = object(rawSeries, seriesLabel);
    const seriesKey = nonemptyString(series.series_key, `${seriesLabel}.series_key`);
    if (seriesKeys.includes(seriesKey)) fail(`${seriesLabel}.series_key is duplicated`);
    seriesKeys.push(seriesKey);
    const playedAt = timestamp(series.played_at, `${seriesLabel}.played_at`);
    if (playedAt >= predictedAt) fail(`${seriesLabel} must predate the forecast`);
    if (playedAt > previousPlayedAt) {
      fail(`${label}.recent_series.series must be ordered newest first`);
    }
    previousPlayedAt = playedAt;
    nonemptyString(series.opponent, `${seriesLabel}.opponent`);
    nonemptyString(series.score, `${seriesLabel}.score`);
    if (!FORMATS.has(series.format)) fail(`${seriesLabel}.format is invalid`);
    if (series.patch === null) {
      nonemptyString(series.patch_missing_reason, `${seriesLabel}.patch_missing_reason`);
    } else {
      nonemptyString(series.patch, `${seriesLabel}.patch`);
    }
    stringList(series.players, `${seriesLabel}.players`, 5);
    nonemptyString(series.source, `${seriesLabel}.source`);
    const checkedAt = timestamp(series.checked_at, `${seriesLabel}.checked_at`);
    if (checkedAt > predictedAt) fail(`${seriesLabel} was checked after predicted_at`);
  }
  return seriesKeys;
}

function validateH2h(h2h, label, predictedAt, scheduledStart) {
  object(h2h, label);
  const searchedAt = timestamp(h2h.searched_at, `${label}.searched_at`);
  if (searchedAt > predictedAt) fail(`${label} was searched after predicted_at`);
  stringList(h2h.sources, `${label}.sources`);
  if (h2h.search_complete !== true) fail(`${label}.search_complete must be true`);
  if (!Array.isArray(h2h.matches)) fail(`${label}.matches must be an array`);

  const comparableCountermodels = [];
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
    comparableCountermodels.push({
      matchIndex: index,
      team: countermodel.team,
      seriesProbability: probability,
      ensembleWeight: weight,
    });
  }
  return comparableCountermodels;
}

function validateLineupUncertainties(forecast, label, predictedAt, scheduledStart) {
  if (!Array.isArray(forecast.lineup_uncertainties)) {
    fail(`${label}.lineup_uncertainties must be an array`);
  }
  const teamNames = new Set(forecast.teams.map((team) => team.name));
  const seen = new Set();
  for (const [index, rawUncertainty] of forecast.lineup_uncertainties.entries()) {
    const uncertaintyLabel = `${label}.lineup_uncertainties[${index}]`;
    const uncertainty = object(rawUncertainty, uncertaintyLabel);
    const team = nonemptyString(uncertainty.team, `${uncertaintyLabel}.team`);
    if (!teamNames.has(team)) fail(`${uncertaintyLabel}.team must match a forecast team`);
    const position = nonemptyString(uncertainty.position, `${uncertaintyLabel}.position`);
    if (!POSITIONS.has(position)) fail(`${uncertaintyLabel}.position is invalid`);
    const key = `${team}:${position}`;
    if (seen.has(key)) fail(`${uncertaintyLabel} duplicates ${key}`);
    seen.add(key);

    const candidates = stringList(
      uncertainty.candidates,
      `${uncertaintyLabel}.candidates`,
    );
    if (candidates.length < 2 || new Set(candidates).size !== candidates.length) {
      fail(`${uncertaintyLabel}.candidates must contain at least two unique starters`);
    }
    if (!Array.isArray(uncertainty.scenarios) || uncertainty.scenarios.length !== candidates.length) {
      fail(`${uncertaintyLabel}.scenarios must contain one entry per candidate`);
    }
    const scenarioCandidates = new Set();
    let scenarioWeight = 0;
    for (const [scenarioIndex, rawScenario] of uncertainty.scenarios.entries()) {
      const scenarioLabel = `${uncertaintyLabel}.scenarios[${scenarioIndex}]`;
      const scenario = object(rawScenario, scenarioLabel);
      const starter = nonemptyString(scenario.starter, `${scenarioLabel}.starter`);
      if (!candidates.includes(starter)) fail(`${scenarioLabel}.starter is not a candidate`);
      if (scenarioCandidates.has(starter)) fail(`${scenarioLabel}.starter is duplicated`);
      scenarioCandidates.add(starter);
      scenarioWeight += probability(scenario.probability, `${scenarioLabel}.probability`);
      probability(
        scenario.team_series_probability,
        `${scenarioLabel}.team_series_probability`,
      );
      nonemptyString(scenario.evidence, `${scenarioLabel}.evidence`);
    }
    if (!close(scenarioWeight, 1)) {
      fail(`${uncertaintyLabel}.scenario probabilities must sum to 1`);
    }
    const recheckBy = timestamp(uncertainty.recheck_by, `${uncertaintyLabel}.recheck_by`);
    if (recheckBy <= predictedAt || recheckBy >= scheduledStart) {
      fail(`${uncertaintyLabel}.recheck_by must be after predicted_at and before scheduled_start`);
    }
    nonemptyString(uncertainty.resolution_trigger, `${uncertaintyLabel}.resolution_trigger`);
  }
}

function validateModelEnsemble(
  forecast,
  label,
  comparableCountermodels,
  requiredRecentEvidenceRefs = [],
) {
  const ensemble = object(forecast.model_ensemble, `${label}.model_ensemble`);
  const teamNames = forecast.teams.map((team) => team.name);
  const targetTeam = nonemptyString(ensemble.target_team, `${label}.model_ensemble.target_team`);
  if (!teamNames.includes(targetTeam)) {
    fail(`${label}.model_ensemble.target_team must match a forecast team`);
  }
  if (!Array.isArray(ensemble.models) || ensemble.models.length < 3) {
    fail(`${label}.model_ensemble.models must contain at least three models`);
  }

  const seenNames = new Set();
  const seenKinds = new Set();
  let weightSum = 0;
  let weightedProbability = 0;
  let minimum = 1;
  let maximum = 0;
  for (const [index, rawModel] of ensemble.models.entries()) {
    const modelLabel = `${label}.model_ensemble.models[${index}]`;
    const model = object(rawModel, modelLabel);
    const name = nonemptyString(model.name, `${modelLabel}.name`);
    if (seenNames.has(name)) fail(`${modelLabel}.name must be unique`);
    seenNames.add(name);
    const kind = nonemptyString(model.kind, `${modelLabel}.kind`);
    if (!MODEL_KINDS.has(kind)) fail(`${modelLabel}.kind is invalid`);
    seenKinds.add(kind);
    const modelProbability = probability(
      model.series_probability,
      `${modelLabel}.series_probability`,
    );
    const weight = probability(model.weight, `${modelLabel}.weight`);
    if (weight === 0) fail(`${modelLabel}.weight must be greater than 0`);
    nonemptyString(model.evidence, `${modelLabel}.evidence`);
    if (requiredRecentEvidenceRefs.length > 0 && kind === "recent_event") {
      const evidenceRefs = stringList(model.evidence_refs, `${modelLabel}.evidence_refs`);
      for (const requiredRef of requiredRecentEvidenceRefs) {
        if (!evidenceRefs.includes(requiredRef)) {
          fail(`${modelLabel}.evidence_refs must include recent series ${requiredRef}`);
        }
      }
    }
    weightSum += weight;
    weightedProbability += modelProbability * weight;
    minimum = Math.min(minimum, modelProbability);
    maximum = Math.max(maximum, modelProbability);
  }
  for (const requiredKind of ["baseline_prior", "recent_event", "underdog_countermodel"]) {
    if (!seenKinds.has(requiredKind)) {
      fail(`${label}.model_ensemble requires ${requiredKind}`);
    }
  }
  if (!close(weightSum, 1)) fail(`${label}.model_ensemble weights must sum to 1`);
  const central = probability(
    ensemble.central_probability,
    `${label}.model_ensemble.central_probability`,
  );
  if (!close(central, weightedProbability)) {
    fail(`${label}.model_ensemble.central_probability must equal the weighted model output`);
  }
  const spread = probability(ensemble.spread, `${label}.model_ensemble.spread`);
  if (!close(spread, maximum - minimum)) {
    fail(`${label}.model_ensemble.spread must equal max minus min model probability`);
  }

  for (const countermodel of comparableCountermodels) {
    const expectedProbability =
      countermodel.team === targetTeam
        ? countermodel.seriesProbability
        : 1 - countermodel.seriesProbability;
    const match = ensemble.models.find(
      (model) =>
        model.kind === "direct_rematch" &&
        model.source_match_index === countermodel.matchIndex,
    );
    if (!match) {
      fail(`${label}.model_ensemble is missing direct_rematch model for H2H index ${countermodel.matchIndex}`);
    }
    if (
      !close(match.series_probability, expectedProbability) ||
      !close(match.weight, countermodel.ensembleWeight)
    ) {
      fail(`${label}.direct_rematch model must match the H2H countermodel output and weight`);
    }
  }
}

function validateForecast(forecast, index, schemaVersion) {
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
  const lastSeriesKeys = forecast.teams.map((team, teamIndex) =>
    validateTeam(
      team,
      `${label}.teams[${teamIndex}]`,
      predictedAt,
      scheduledStart,
      schemaVersion >= 4,
      schemaVersion >= 5,
    ),
  );
  const comparableCountermodels = validateH2h(
    forecast.recent_direct_h2h,
    `${label}.recent_direct_h2h`,
    predictedAt,
    scheduledStart,
  );
  let requiredRecentEvidenceRefs = [];
  if (schemaVersion >= 4) {
    const competition = object(forecast.competition, `${label}.competition`);
    requiredRecentEvidenceRefs = [...lastSeriesKeys];
    forecast.teams.forEach((team, teamIndex) => {
      requiredRecentEvidenceRefs.push(
        ...validateRecentSeries(
          team,
          `${label}.teams[${teamIndex}]`,
          predictedAt,
          competition,
        ),
      );
    });
    requiredRecentEvidenceRefs = [...new Set(requiredRecentEvidenceRefs)];
  }
  if (schemaVersion >= 2) {
    validateLineupUncertainties(forecast, label, predictedAt, scheduledStart);
    const establishedTeams = new Set(
      forecast.teams
        .filter((team) => team.projected_lineup.status === "established")
        .map((team) => team.name),
    );
    if (
      forecast.lineup_uncertainties.some((uncertainty) =>
        establishedTeams.has(uncertainty.team)
      )
    ) {
      fail(`${label} established lineup cannot retain a lineup uncertainty`);
    }
    validateModelEnsemble(
      forecast,
      label,
      comparableCountermodels,
      requiredRecentEvidenceRefs,
    );
  }
  if (schemaVersion >= 3) {
    validatePatchContext(forecast, label, predictedAt);
  }
  if (schemaVersion >= 5) {
    const hasProjectedLineup = forecast.teams.some(
      (team) => team.projected_lineup.status === "projected",
    );
    const hasEstablishedLineup = forecast.teams.some(
      (team) => team.projected_lineup.status === "established",
    );
    if (hasProjectedLineup && !forecast.snapshot.includes("pre-lineup")) {
      fail(`${label}.snapshot must be pre-lineup while any lineup is projected`);
    }
    if (
      !hasProjectedLineup &&
      hasEstablishedLineup &&
      !forecast.snapshot.includes("established-lineup")
    ) {
      fail(`${label}.snapshot must be established-lineup when a fixed lineup is established`);
    }
    if (
      !hasProjectedLineup &&
      !hasEstablishedLineup &&
      !forecast.snapshot.includes("post-lineup")
    ) {
      fail(`${label}.snapshot must be post-lineup when both lineups are confirmed`);
    }
    validateSeriesDistribution(forecast, label);
  }

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
  if (![1, 2, 3, 4, 5].includes(payload.schema_version)) {
    fail("schema_version must be 1, 2, 3, 4, or 5");
  }
  if (!Array.isArray(payload.forecasts) || payload.forecasts.length === 0) {
    fail("forecasts must be a non-empty array");
  }
  const seen = new Set();
  payload.forecasts.forEach((forecast, index) => {
    validateForecast(forecast, index, payload.schema_version);
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
