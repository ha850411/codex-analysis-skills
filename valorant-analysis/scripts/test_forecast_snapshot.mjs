#!/usr/bin/env node

import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { recordForecast } from "./record_forecast.mjs";
import { validateSnapshot } from "./validate_forecast_snapshot.mjs";

const teamB = ["Jinggg", "f0rsakeN", "something", "d4v41", "invy"];

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function validSnapshot() {
  return {
    schema_version: 1,
    forecast_id: "vct-pac-20260809-vl-prx-post-veto-v1",
    event_id: "vlr-698914",
    snapshot: "post-veto",
    veto_status: "post-veto",
    created_at: "2026-08-09T14:00:00+08:00",
    data_cutoff: "2026-08-09T13:55:00+08:00",
    scheduled_start: "2026-08-09T16:00:00+08:00",
    model_version: "valorant-model-v1",
    skill_revision: "test-revision",
    format: "BO3",
    teams: { a: "VARREL", b: "Paper Rex" },
    market_data_visibility: "withheld_from_probability_stages",
    scenarios: [{
      id: "official-veto-map-sub",
      weight: 100,
      veto: {
        bans: ["Breeze", "Haven", "Summit", "Ascent"],
        map_order: ["Split", "Sunset", "Lotus"],
        pick_owners: ["a", "b", "decider"],
      },
      lineups_by_map: {
        Split: { a: ["XuNa", "Foxy9", "oonzmlp", "Zexy", "C1ndeR"], b: teamB },
        Sunset: { a: ["XuNa", "Foxy9", "oonzmlp", "Zexy", "Klaus"], b: teamB },
        Lotus: { a: ["XuNa", "Foxy9", "oonzmlp", "Zexy", "Klaus"], b: teamB },
      },
      score_distribution: { a_2_0: 20, a_2_1: 25, b_2_1: 30, b_2_0: 25 },
    }],
    main_score_distribution: { a_2_0: 20, a_2_1: 25, b_2_1: 30, b_2_0: 25 },
    model_confidence: {
      value: 70,
      components: {
        dataCompleteness: 75,
        freshness: 80,
        lineupCertainty: 60,
        regimeRelevance: 70,
        modelStability: 65,
      },
    },
    evidence: [{
      id: "match-page",
      url: "https://www.vlr.gg/698914/example",
      retrieved_at: "2026-08-09T13:55:00+08:00",
      claim: "賽事身分、名單與 veto",
    }],
  };
}

test("accepts map-specific six-player rotation and reports it", () => {
  const result = validateSnapshot(validSnapshot());
  assert.equal(result.map_specific_lineup_scenarios, 1);
  assert.equal(result.weighted_confidence, 70);
});

test("pre-veto snapshots require multiple weighted paths", () => {
  const payload = validSnapshot();
  payload.snapshot = "pre-veto";
  payload.veto_status = "pre-veto";
  assert.throws(() => validateSnapshot(payload), /at least two weighted scenarios/);
});

test("rejects a main distribution that is not the scenario mixture", () => {
  const payload = validSnapshot();
  payload.main_score_distribution.a_2_0 = 21;
  payload.main_score_distribution.b_2_0 = 24;
  assert.throws(() => validateSnapshot(payload), /weighted scenario mixture/);
});

test("rejects a forecast created after scheduled start", () => {
  const payload = validSnapshot();
  payload.created_at = "2026-08-09T16:01:00+08:00";
  assert.throws(() => validateSnapshot(payload), /strictly before scheduled_start/);
});

test("records idempotently and blocks conflicting overwrite", (context) => {
  const ledgerRoot = fs.mkdtempSync(path.join(os.tmpdir(), "valorant-forecast-"));
  context.after(() => fs.rmSync(ledgerRoot, { recursive: true, force: true }));
  const payload = validSnapshot();
  assert.equal(recordForecast(payload, ledgerRoot).status, "recorded");
  assert.equal(recordForecast(payload, ledgerRoot).status, "already_recorded");
  const conflict = clone(payload);
  conflict.model_version = "different-model";
  assert.throws(() => recordForecast(conflict, ledgerRoot), /immutable forecast_id collision/);
});
