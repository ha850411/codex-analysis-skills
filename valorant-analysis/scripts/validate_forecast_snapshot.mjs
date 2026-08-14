#!/usr/bin/env node

import fs from "node:fs";
import { pathToFileURL } from "node:url";

const SCORE_KEYS = {
  BO1: ["a_1_0", "b_1_0"],
  BO3: ["a_2_0", "a_2_1", "b_2_1", "b_2_0"],
  BO5: ["a_3_0", "a_3_1", "a_3_2", "b_3_2", "b_3_1", "b_3_0"],
};

const MAP_COUNTS = { BO1: 1, BO3: 3, BO5: 5 };
const SNAPSHOTS = new Set(["pre-lineup", "post-lineup", "pre-veto", "post-veto"]);
const CONFIDENCE_WEIGHTS = {
  dataCompleteness: 0.25,
  freshness: 0.20,
  lineupCertainty: 0.25,
  regimeRelevance: 0.20,
  modelStability: 0.10,
};

function invariant(condition, message) {
  if (!condition) throw new Error(message);
}

function finitePercent(value, label) {
  invariant(typeof value === "number" && Number.isFinite(value), `${label} must be numeric`);
  invariant(value >= 0 && value <= 100, `${label} must be within [0, 100]`);
  return value;
}

function requiredString(value, label) {
  invariant(typeof value === "string" && value.trim() !== "", `${label} must be non-empty`);
  return value.trim();
}

function zonedTime(value, label) {
  const text = requiredString(value, label);
  invariant(/(?:Z|[+-]\d{2}:\d{2})$/.test(text), `${label} must include a timezone offset`);
  const timestamp = Date.parse(text);
  invariant(Number.isFinite(timestamp), `${label} must be ISO-8601`);
  return timestamp;
}

function validateDistribution(distribution, keys, label) {
  invariant(distribution && typeof distribution === "object" && !Array.isArray(distribution), `${label} must be an object`);
  const actualKeys = Object.keys(distribution).sort();
  invariant(JSON.stringify(actualKeys) === JSON.stringify([...keys].sort()), `${label} must contain exactly: ${keys.join(", ")}`);
  const values = keys.map((key) => finitePercent(distribution[key], `${label}.${key}`));
  const total = values.reduce((sum, value) => sum + value, 0);
  invariant(Math.abs(total - 100) <= 0.2, `${label} sums to ${total.toFixed(2)}%, expected 100%`);
  return distribution;
}

function validateLineup(lineup, label) {
  invariant(Array.isArray(lineup) && lineup.length === 5, `${label} must contain exactly five players`);
  const players = lineup.map((player, index) => requiredString(player, `${label}[${index}]`));
  invariant(new Set(players).size === 5, `${label} cannot contain duplicate players`);
  return players;
}

function validateScenario(scenario, index, format, keys) {
  const label = `scenarios[${index}]`;
  invariant(scenario && typeof scenario === "object" && !Array.isArray(scenario), `${label} must be an object`);
  requiredString(scenario.id, `${label}.id`);
  finitePercent(scenario.weight, `${label}.weight`);

  const veto = scenario.veto;
  invariant(veto && typeof veto === "object" && !Array.isArray(veto), `${label}.veto must be an object`);
  invariant(Array.isArray(veto.bans), `${label}.veto.bans must be an array`);
  veto.bans.forEach((map, mapIndex) => requiredString(map, `${label}.veto.bans[${mapIndex}]`));
  invariant(Array.isArray(veto.map_order) && veto.map_order.length === MAP_COUNTS[format], `${label}.veto.map_order must contain ${MAP_COUNTS[format]} maps`);
  const mapOrder = veto.map_order.map((map, mapIndex) => requiredString(map, `${label}.veto.map_order[${mapIndex}]`));
  invariant(new Set(mapOrder).size === mapOrder.length, `${label}.veto.map_order cannot contain duplicate maps`);
  invariant(Array.isArray(veto.pick_owners) && veto.pick_owners.length === mapOrder.length, `${label}.veto.pick_owners must align with map_order`);
  veto.pick_owners.forEach((owner, ownerIndex) => {
    invariant(["a", "b", "decider"].includes(owner), `${label}.veto.pick_owners[${ownerIndex}] must be a, b, or decider`);
  });

  const lineups = scenario.lineups_by_map;
  invariant(lineups && typeof lineups === "object" && !Array.isArray(lineups), `${label}.lineups_by_map must be an object`);
  const signatures = { a: new Set(), b: new Set() };
  for (const map of mapOrder) {
    const mapLineups = lineups[map] || lineups["*"];
    invariant(mapLineups && typeof mapLineups === "object", `${label}.lineups_by_map must cover ${map} or use *`);
    for (const side of ["a", "b"]) {
      const players = validateLineup(mapLineups[side], `${label}.lineups_by_map.${map}.${side}`);
      signatures[side].add([...players].sort().join("|"));
    }
  }

  validateDistribution(scenario.score_distribution, keys, `${label}.score_distribution`);
  return {
    mapSpecificLineup: signatures.a.size > 1 || signatures.b.size > 1,
  };
}

export function validateSnapshot(payload) {
  invariant(payload && typeof payload === "object" && !Array.isArray(payload), "snapshot must be an object");
  invariant(payload.schema_version === 1, "schema_version must equal 1");
  const forecastId = requiredString(payload.forecast_id, "forecast_id");
  invariant(/^[a-z0-9][a-z0-9._-]{2,127}$/.test(forecastId), "forecast_id must be a lowercase file-safe identifier");
  requiredString(payload.event_id, "event_id");
  invariant(SNAPSHOTS.has(payload.snapshot), `snapshot must be one of ${[...SNAPSHOTS].join(", ")}`);
  invariant(["pre-veto", "post-veto"].includes(payload.veto_status), "veto_status must be pre-veto or post-veto");
  requiredString(payload.model_version, "model_version");
  requiredString(payload.skill_revision, "skill_revision");
  invariant(Object.hasOwn(SCORE_KEYS, payload.format), "format must be BO1, BO3, or BO5");
  invariant(payload.teams && typeof payload.teams === "object", "teams must be an object");
  const teamA = requiredString(payload.teams.a, "teams.a");
  const teamB = requiredString(payload.teams.b, "teams.b");
  invariant(teamA !== teamB, "teams.a and teams.b must differ");
  invariant(payload.market_data_visibility === "withheld_from_probability_stages", "market_data_visibility must be withheld_from_probability_stages");

  const createdAt = zonedTime(payload.created_at, "created_at");
  const dataCutoff = zonedTime(payload.data_cutoff, "data_cutoff");
  const scheduledStart = zonedTime(payload.scheduled_start, "scheduled_start");
  invariant(dataCutoff <= createdAt, "data_cutoff cannot be after created_at");
  invariant(createdAt < scheduledStart, "created_at must be strictly before scheduled_start");

  invariant(Array.isArray(payload.scenarios) && payload.scenarios.length > 0, "scenarios must be a non-empty array");
  if (payload.veto_status === "pre-veto") {
    invariant(payload.scenarios.length >= 2, "pre-veto snapshots require at least two weighted scenarios");
  }
  const scenarioIds = payload.scenarios.map((scenario) => scenario?.id);
  invariant(new Set(scenarioIds).size === scenarioIds.length, "scenario ids must be unique");
  const scoreKeys = SCORE_KEYS[payload.format];
  const scenarioResults = payload.scenarios.map((scenario, index) => validateScenario(scenario, index, payload.format, scoreKeys));
  const weightTotal = payload.scenarios.reduce((sum, scenario) => sum + scenario.weight, 0);
  invariant(Math.abs(weightTotal - 100) <= 0.2, `scenario weights sum to ${weightTotal.toFixed(2)}%, expected 100%`);

  validateDistribution(payload.main_score_distribution, scoreKeys, "main_score_distribution");
  for (const key of scoreKeys) {
    const mixed = payload.scenarios.reduce((sum, scenario) => sum + scenario.weight * scenario.score_distribution[key] / 100, 0);
    invariant(Math.abs(payload.main_score_distribution[key] - mixed) <= 0.2, `main_score_distribution.${key} does not equal the weighted scenario mixture`);
  }

  const confidence = payload.model_confidence;
  invariant(confidence && typeof confidence === "object", "model_confidence must be an object");
  invariant(Number.isInteger(confidence.value), "model_confidence.value must be an integer");
  let weightedConfidence = 0;
  for (const [component, weight] of Object.entries(CONFIDENCE_WEIGHTS)) {
    weightedConfidence += finitePercent(confidence.components?.[component], `model_confidence.components.${component}`) * weight;
  }
  weightedConfidence = Math.round(weightedConfidence);
  invariant(confidence.value === weightedConfidence, `model_confidence.value must equal weighted components (${weightedConfidence})`);

  invariant(Array.isArray(payload.evidence) && payload.evidence.length > 0, "evidence must be a non-empty array");
  payload.evidence.forEach((item, index) => {
    requiredString(item?.id, `evidence[${index}].id`);
    requiredString(item?.url, `evidence[${index}].url`);
    const retrievedAt = zonedTime(item?.retrieved_at, `evidence[${index}].retrieved_at`);
    invariant(retrievedAt <= dataCutoff, `evidence[${index}].retrieved_at cannot be after data_cutoff`);
    requiredString(item?.claim, `evidence[${index}].claim`);
  });

  return {
    forecast_id: forecastId,
    format: payload.format,
    scenario_count: payload.scenarios.length,
    map_specific_lineup_scenarios: scenarioResults.filter((result) => result.mapSpecificLineup).length,
    weighted_confidence: weightedConfidence,
  };
}

function runCli() {
  if (process.argv.length !== 3) {
    console.error("Usage: node validate_forecast_snapshot.mjs <forecast-snapshot.json>");
    process.exit(2);
  }
  try {
    const payload = JSON.parse(fs.readFileSync(process.argv[2], "utf8"));
    console.log(JSON.stringify({ pass: true, ...validateSnapshot(payload) }, null, 2));
  } catch (error) {
    console.error(`Validation error: ${error.message}`);
    process.exit(1);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) runCli();
