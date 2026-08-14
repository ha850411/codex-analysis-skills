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
