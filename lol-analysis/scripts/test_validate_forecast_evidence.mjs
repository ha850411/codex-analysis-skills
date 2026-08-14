#!/usr/bin/env node

import assert from "node:assert/strict";
import { validateSnapshot } from "./validate_forecast_evidence.mjs";

function team(name, players) {
  return {
    name,
    last_series: {
      played_at: "2026-08-08T07:00:00+08:00",
      players,
      source: "https://example.test/last-series",
      checked_at: "2026-08-13T12:00:00+08:00",
    },
    projected_lineup: { players: [...players] },
  };
}

function validForecast() {
  return {
    match_key: "bo3:124532",
    scheduled_start: "2026-08-13T17:00:00+08:00",
    predicted_at: "2026-08-13T15:30:00+08:00",
    snapshot: "pre-lineup/pre-draft",
    evaluation_status: "prospective_pre_match",
    teams: [
      team("TES", ["TopA", "JungleA", "MidA", "AdcA", "SupportA"]),
      team("LGD", ["TopB", "JungleB", "MidB", "AdcB", "SupportB"]),
    ],
    recent_direct_h2h: {
      searched_at: "2026-08-13T13:00:00+08:00",
      search_complete: true,
      sources: ["https://example.test/h2h"],
      matches: [
        {
          played_at: "2026-08-01T17:00:00+08:00",
          same_event: true,
          comparable_roster: true,
          games: [
            {
              winner: "LGD",
              blue_team: "LGD",
              red_team: "TES",
              picks: ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
            },
          ],
          mechanisms: ["LGD middle-jungle pressure"],
          direct_rematch_countermodel: {
            team: "LGD",
            series_probability: 0.34,
            ensemble_weight: 0.25,
          },
        },
      ],
    },
    betting: { stake_units: 0 },
  };
}

function payload(forecast = validForecast()) {
  return { schema_version: 1, forecasts: [forecast] };
}

function upgradeToV2(forecast = validForecast()) {
  forecast.lineup_uncertainties = [];
  forecast.model_ensemble = {
    target_team: "LGD",
    models: [
      {
        name: "strength-prior",
        kind: "baseline_prior",
        series_probability: 0.58,
        weight: 0.25,
        evidence: "long-term opponent-adjusted strength",
      },
      {
        name: "recent-event",
        kind: "recent_event",
        series_probability: 0.62,
        weight: 0.25,
        evidence: "same-event recent series",
      },
      {
        name: "underdog-win-path",
        kind: "underdog_countermodel",
        series_probability: 0.48,
        weight: 0.25,
        evidence: "opponent repeatable win paths",
      },
      {
        name: "direct-rematch",
        kind: "direct_rematch",
        source_match_index: 0,
        series_probability: 0.34,
        weight: 0.25,
        evidence: "comparable direct rematch",
      },
    ],
    central_probability: 0.505,
    spread: 0.28,
  };
  return forecast;
}

function payloadV2(forecast = upgradeToV2()) {
  return { schema_version: 2, forecasts: [forecast] };
}

assert.doesNotThrow(() => validateSnapshot(payload()));
assert.doesNotThrow(() => validateSnapshot(payloadV2()));

{
  const forecast = validForecast();
  forecast.teams[0].projected_lineup.players[1] = "OlderJungler";
  assert.throws(() => validateSnapshot(payload(forecast)), /change_evidence/);
}

{
  const forecast = upgradeToV2();
  delete forecast.model_ensemble;
  assert.throws(() => validateSnapshot(payloadV2(forecast)), /model_ensemble/);
}

{
  const forecast = upgradeToV2();
  forecast.model_ensemble.central_probability = 0.58;
  assert.throws(() => validateSnapshot(payloadV2(forecast)), /weighted model output/);
}

{
  const forecast = upgradeToV2();
  forecast.model_ensemble.models = forecast.model_ensemble.models.filter(
    (model) => model.kind !== "direct_rematch",
  );
  forecast.model_ensemble.models[0].weight = 1 / 3;
  forecast.model_ensemble.models[1].weight = 1 / 3;
  forecast.model_ensemble.models[2].weight = 1 / 3;
  forecast.model_ensemble.central_probability = 0.56;
  forecast.model_ensemble.spread = 0.14;
  assert.throws(() => validateSnapshot(payloadV2(forecast)), /missing direct_rematch/);
}

{
  const forecast = upgradeToV2();
  forecast.lineup_uncertainties = [
    {
      team: "TES",
      position: "Jungle",
      candidates: ["JungleA", "AltJungle"],
      scenarios: [
        {
          starter: "JungleA",
          probability: 0.6,
          team_series_probability: 0.55,
          evidence: "latest formal series",
        },
        {
          starter: "AltJungle",
          probability: 0.4,
          team_series_probability: 0.61,
          evidence: "recent official rotation",
        },
      ],
      recheck_by: "2026-08-13T16:30:00+08:00",
      resolution_trigger: "official match roster or on-stage draft client",
    },
  ];
  assert.doesNotThrow(() => validateSnapshot(payloadV2(forecast)));
  forecast.lineup_uncertainties[0].scenarios[1].probability = 0.3;
  assert.throws(() => validateSnapshot(payloadV2(forecast)), /probabilities must sum to 1/);
}

{
  const forecast = validForecast();
  forecast.teams[0].projected_lineup.players[1] = "AnnouncedJungler";
  forecast.teams[0].change_evidence = {
    source: "https://example.test/match-lineup",
    reason: "match-specific starter announcement",
    published_at: "2026-08-12T18:00:00+08:00",
    checked_at: "2026-08-13T12:00:00+08:00",
  };
  assert.doesNotThrow(() => validateSnapshot(payload(forecast)));
  forecast.teams[0].change_evidence.published_at = "2026-08-01T18:00:00+08:00";
  assert.throws(() => validateSnapshot(payload(forecast)), /newer than last_series/);
}

{
  const forecast = validForecast();
  forecast.recent_direct_h2h.matches[0].games = [];
  assert.throws(() => validateSnapshot(payload(forecast)), /game evidence/);
}

{
  const forecast = validForecast();
  forecast.recent_direct_h2h.matches[0].direct_rematch_countermodel = { team: "LGD" };
  assert.throws(() => validateSnapshot(payload(forecast)), /probability\/weight/);
}

{
  const forecast = validForecast();
  delete forecast.recent_direct_h2h.matches[0].direct_rematch_countermodel.team;
  assert.throws(() => validateSnapshot(payload(forecast)), /countermodel.team/);
}

{
  const forecast = validForecast();
  forecast.predicted_at = "2026-08-13T17:30:00+08:00";
  forecast.evaluation_status = "reconstructed_after_start";
  forecast.betting.stake_units = 0.25;
  assert.throws(() => validateSnapshot(payload(forecast)), /must use 0u/);
  forecast.betting.stake_units = 0;
  assert.doesNotThrow(() => validateSnapshot(payload(forecast)));
}

console.log("OK: validate_forecast_evidence regression tests");
