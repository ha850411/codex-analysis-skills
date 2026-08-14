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

assert.doesNotThrow(() => validateSnapshot(payload()));

{
  const forecast = validForecast();
  forecast.teams[0].projected_lineup.players[1] = "OlderJungler";
  assert.throws(() => validateSnapshot(payload(forecast)), /change_evidence/);
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
