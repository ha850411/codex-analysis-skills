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

function upgradeToV3(forecast = upgradeToV2()) {
  forecast.competition = {
    league: "LPL",
    event: "LPL 2026 Split 3",
    stage: "Group Ascend Week 4",
    format: "BO3",
  };
  forecast.patch_context = {
    league: "LPL",
    event: "LPL 2026 Split 3",
    stage: "Group Ascend Week 4",
    status: "confirmed",
    value: "26.16",
    checked_at: "2026-08-13T15:00:00+08:00",
    conflicts: [],
    sources: [{
      url: "https://example.test/official-match-page",
      kind: "official_match_page",
      league: "LPL",
      event: "LPL 2026 Split 3",
      stage: "Group Ascend Week 4",
      checked_at: "2026-08-13T15:00:00+08:00",
    }],
  };
  return forecast;
}

function payloadV3(forecast = upgradeToV3()) {
  return { schema_version: 3, forecasts: [forecast] };
}

function upgradeToV4(forecast = upgradeToV3()) {
  const evidenceRefs = [];
  forecast.teams.forEach((forecastTeam, index) => {
    const suffix = index === 0 ? "tes" : "lgd";
    const opponent = index === 0 ? "LGD" : "TES";
    const latestKey = `lpl-2026-08-08-${suffix}`;
    forecastTeam.last_series.series_key = latestKey;
    forecastTeam.recent_series = {
      league: forecast.competition.league,
      event: forecast.competition.event,
      searched_at: "2026-08-13T15:00:00+08:00",
      search_complete: true,
      insufficient_reason: null,
      series: [
        {
          series_key: latestKey,
          played_at: "2026-08-08T07:00:00+08:00",
          opponent,
          score: index === 0 ? "2-1" : "1-2",
          format: "BO3",
          patch: "26.16",
          players: [...forecastTeam.last_series.players],
          source: "https://example.test/last-series",
          checked_at: "2026-08-13T12:00:00+08:00",
        },
        {
          series_key: `lpl-2026-08-03-${suffix}`,
          played_at: "2026-08-03T07:00:00+08:00",
          opponent: `${opponent} Academy`,
          score: index === 0 ? "0-2" : "2-0",
          format: "BO3",
          patch: "26.15",
          players: [...forecastTeam.last_series.players],
          source: "https://example.test/previous-series",
          checked_at: "2026-08-13T12:00:00+08:00",
        },
      ],
    };
    evidenceRefs.push(latestKey, `lpl-2026-08-03-${suffix}`);
  });
  forecast.model_ensemble.models.find(
    (model) => model.kind === "recent_event",
  ).evidence_refs = evidenceRefs;
  return forecast;
}

function payloadV4(forecast = upgradeToV4()) {
  return { schema_version: 4, forecasts: [forecast] };
}

function upgradeToV5(forecast = upgradeToV4()) {
  forecast.teams.forEach((forecastTeam) => {
    forecastTeam.projected_lineup = {
      ...forecastTeam.projected_lineup,
      status: "projected",
      source_kind: "latest_formal_series",
      source: forecastTeam.last_series.source,
      checked_at: "2026-08-13T12:00:00+08:00",
      recheck_by: "2026-08-13T16:30:00+08:00",
    };
  });
  forecast.series_distribution = {
    outcomes: {
      "2-0": 0.20,
      "2-1": 0.295,
      "1-2": 0.305,
      "0-2": 0.20,
    },
    reported_mode: "1-2",
  };
  return forecast;
}

function payloadV5(forecast = upgradeToV5()) {
  return { schema_version: 5, forecasts: [forecast] };
}

assert.doesNotThrow(() => validateSnapshot(payload()));
assert.doesNotThrow(() => validateSnapshot(payloadV2()));
assert.doesNotThrow(() => validateSnapshot(payloadV3()));
assert.doesNotThrow(() => validateSnapshot(payloadV4()));
assert.doesNotThrow(() => validateSnapshot(payloadV5()));

{
  const forecast = upgradeToV5();
  delete forecast.teams[0].projected_lineup.status;
  assert.throws(() => validateSnapshot(payloadV5(forecast)), /status must be confirmed or projected/);
}

{
  const forecast = upgradeToV5();
  forecast.teams[0].projected_lineup.status = "confirmed";
  assert.throws(() => validateSnapshot(payloadV5(forecast)), /requires an official source/);
}

{
  const forecast = upgradeToV5();
  forecast.series_distribution.reported_mode = "0-2";
  assert.throws(() => validateSnapshot(payloadV5(forecast)), /highest-probability score/);
}

{
  const forecast = upgradeToV5();
  forecast.series_distribution.outcomes["2-0"] = 0.205;
  forecast.series_distribution.outcomes["0-2"] = 0.195;
  assert.throws(() => validateSnapshot(payloadV5(forecast)), /target-team win sum/);
}

{
  const forecast = upgradeToV4();
  delete forecast.teams[0].recent_series;
  assert.throws(() => validateSnapshot(payloadV4(forecast)), /recent_series/);
}

{
  const forecast = upgradeToV4();
  forecast.teams[0].recent_series.series.pop();
  forecast.teams[0].recent_series.insufficient_reason = null;
  assert.throws(() => validateSnapshot(payloadV4(forecast)), /insufficient_reason/);
}

{
  const forecast = upgradeToV4();
  const recentModel = forecast.model_ensemble.models.find(
    (model) => model.kind === "recent_event",
  );
  recentModel.evidence_refs.pop();
  assert.throws(() => validateSnapshot(payloadV4(forecast)), /evidence_refs must include/);
}

{
  const forecast = upgradeToV3();
  delete forecast.patch_context;
  assert.throws(() => validateSnapshot(payloadV3(forecast)), /patch_context/);
}

{
  const forecast = upgradeToV3();
  forecast.patch_context.sources[0].stage = "Previous Week";
  assert.throws(() => validateSnapshot(payloadV3(forecast)), /scope must match/);
}

{
  const forecast = upgradeToV3();
  forecast.patch_context.sources[0].kind = "same_stage_match";
  assert.throws(() => validateSnapshot(payloadV3(forecast)), /requires an official source/);
}

{
  const forecast = upgradeToV3();
  forecast.patch_context = {
    ...forecast.patch_context,
    status: "scenario",
    value: null,
    conflicts: ["官方規章與同週賽事頁不一致"],
    scenarios: [
      { value: "26.15", probability: 0.4, evidence: "規章尚列舊版" },
      { value: "26.16", probability: 0.6, evidence: "同階段公告列新版" },
    ],
  };
  assert.doesNotThrow(() => validateSnapshot(payloadV3(forecast)));
  forecast.patch_context.scenarios[1].probability = 0.5;
  assert.throws(() => validateSnapshot(payloadV3(forecast)), /probabilities must sum to 1/);
}

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
