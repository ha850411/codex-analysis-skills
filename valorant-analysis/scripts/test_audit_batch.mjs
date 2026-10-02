#!/usr/bin/env node

import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const scriptPath = path.join(path.dirname(fileURLToPath(import.meta.url)), "audit_batch.mjs");

function run(matches) {
  const result = spawnSync(process.execPath, [scriptPath, "-"], {
    input: JSON.stringify({ matches }),
    encoding: "utf8",
  });
  return result;
}

const baseMatch = {
  id: "vl-prx",
  score_distribution: { a_2_0: 20, a_2_1: 25, b_2_1: 30, b_2_0: 25 },
  actual_score: "a_2_0",
};

test("reports map-lineup misses separately from veto coverage", () => {
  const result = run([{
    ...baseMatch,
    scenario_coverage: {
      lineup_by_map: false,
      first_bans: true,
      map_picks: true,
      pick_owners: true,
      decider: true,
    },
  }]);
  assert.equal(result.status, 0, result.stderr);
  const output = JSON.parse(result.stdout);
  assert.equal(output.summary.scenario_coverage_misses, 1);
  assert.equal(output.summary.scenario_coverage_misses_by_dimension.lineup_by_map, 1);
  assert.match(output.warnings.join("\n"), /lineup_by_map=1/);
});

test("keeps legacy overall coverage inputs readable", () => {
  const result = run([{ ...baseMatch, scenario_covered: true }]);
  assert.equal(result.status, 0, result.stderr);
  const output = JSON.parse(result.stdout);
  assert.equal(output.summary.legacy_scenario_coverage_records, 1);
  assert.match(output.warnings.join("\n"), /LEGACY_SCENARIO_COVERAGE/);
});

test("rejects records with no coverage field", () => {
  const result = run([baseMatch]);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /requires scenario_coverage/);
});

const dimensions = ["lineup_by_map", "first_bans", "map_picks", "pick_owners", "decider"];
const coverage = (value) => Object.fromEntries(dimensions.map((key) => [key, value]));
const nativeMatch = {
  schema_version: "2.0", probability_unit: "fraction", sport: "valorant",
  forecast_id: "published-r2", event_id: "event-1", snapshot: "pre-veto",
  data_cutoff: "2026-09-28T16:00:00Z", model_version: "test-v2",
  best_of: 3, scope: "full-series",
  score_distribution: { "2-0": 0.2, "2-1": 0.25, "1-2": 0.3, "0-2": 0.25 },
  actual_score: "2-1", scenario_coverage: coverage("not_modeled"),
  scenarios: [{ id: "unresolved-map-order", weight: 1 }],
};

test("reads canonical v2 fractions and labels both Brier conventions", () => {
  const result = run([nativeMatch]);
  assert.equal(result.status, 0, result.stderr);
  const out = JSON.parse(result.stdout);
  assert.equal(out.matches[0].side_a_win_probability, 45);
  assert.equal(out.matches[0].actual_score_probability, 25);
  assert.equal(out.summary.winner_brier, 0.3025);
  assert.equal(out.summary.winner_brier_sum, 0.605);
  assert.match(out.metric_definitions.winner_brier_sum, /shared v2/);
});

test("does not turn unmodeled dimensions into unexpected roster or veto misses", () => {
  const result = run([nativeMatch]);
  assert.equal(result.status, 0, result.stderr);
  const out = JSON.parse(result.stdout);
  assert.equal(out.matches[0].scenario_covered, false);
  assert.equal(out.summary.scenario_not_modeled_by_dimension.lineup_by_map, 1);
  assert.equal(out.summary.scenario_coverage_misses_by_dimension.lineup_by_map, 0);
});

test("does not accept sensitivity-only coverage for an unresolved primary forecast", () => {
  const result = run([{ ...nativeMatch, scenario_coverage: coverage(true), joint_scenario_covered: true }]);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /unresolved-map-order cannot claim/);
});

test("v2 cannot bypass dimension checks with the legacy overall coverage flag", () => {
  const result = run([{ ...nativeMatch, scenario_coverage: undefined, scenario_covered: true }]);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /v2 requires dimension-level/);
});

test("requires a joint match, not separately covered marginal dimensions", () => {
  const match = { ...nativeMatch, scenarios: [{ id: "path-1", weight: 1 }], scenario_coverage: coverage(true) };
  assert.equal(run([match]).status, 1);
  const result = run([{ ...match, joint_scenario_covered: false }]);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(JSON.parse(result.stdout).matches[0].scenario_covered, false);
});

test("preserves unknown coverage without counting it as a verified miss", () => {
  const result = run([{ ...baseMatch, scenario_coverage: coverage("unknown") }]);
  assert.equal(result.status, 0, result.stderr);
  const out = JSON.parse(result.stdout);
  assert.equal(out.summary.scenario_unknown_by_dimension.decider, 1);
  assert.equal(out.summary.scenario_coverage_misses_by_dimension.decider, 0);
});

test("rejects duplicate published revisions of one evaluation identity", () => {
  const result = run([nativeMatch, { ...nativeMatch, forecast_id: "unpublished-r1" }]);
  assert.equal(result.status, 1);
  assert.match(result.stderr, /duplicate evaluation identity/);
});

test("reports the lower sweep tail when every series goes to three maps", () => {
  const matches = ["one", "two"].map((id) => ({ ...baseMatch, id, actual_score: "a_2_1", scenario_covered: true }));
  const result = run(matches);
  assert.equal(result.status, 0, result.stderr);
  const out = JSON.parse(result.stdout);
  assert.equal(out.summary.probability_at_least_actual_sweeps, 1);
  assert.equal(out.summary.probability_at_most_actual_sweeps, 0.3025);
  assert.equal(out.summary.probability_exactly_actual_sweeps, 0.3025);
});

test("audits sweep-mode concentration as well as 2-1 concentration", () => {
  const matches = [0, 1, 2, 3].map((id) => ({ ...baseMatch, id: String(id),
    score_distribution: { a_2_0: 35, a_2_1: 25, b_2_1: 20, b_2_0: 20 }, scenario_covered: true }));
  const result = run(matches);
  assert.equal(result.status, 0, result.stderr);
  const out = JSON.parse(result.stdout);
  assert.equal(out.summary.sweep_mode_rate, 1);
  assert.match(out.warnings.join("\n"), /SWEEP_MODE_CONCENTRATION/);
});

test("rejects percent-valued v2 data and unsupported series scopes", () => {
  assert.equal(run([{ ...nativeMatch, probability_unit: "percent" }]).status, 1);
  assert.equal(run([{ ...nativeMatch, score_distribution: { ...nativeMatch.score_distribution, "2-0": 20 } }]).status, 1);
  assert.equal(run([{ ...nativeMatch, best_of: 5 }]).status, 1);
});
