#!/usr/bin/env node

import assert from "node:assert/strict";
import { validateDecisionSlate } from "./validate_decision_slate.mjs";

const tableCell = "立即可打：WE ML @3.00；底價 2.76；0.5u";

function validSlate() {
  const firstKey = "lpl:2026-08-14:we-tes";
  const secondKey = "lck:2026-08-14:ns-bro";
  const evaluation = ({
    evaluationId,
    matchKey,
    selection,
    family,
    side,
    line,
    modelProbability,
    bettingProbability,
    currentOdds,
    gate = family === "series_ml" ? "not_required" : "pass",
    blockers = [],
  }) => ({
    evaluation_id: evaluationId,
    match_key: matchKey,
    selection,
    market_family: family,
    selection_side: side,
    line,
    model_probability: modelProbability,
    betting_probability: bettingProbability,
    current_odds: currentOdds,
    minimum_acceptable_odds: Math.ceil((1.02 / bettingProbability) * 100) / 100,
    adjusted_ev: Number((currentOdds * bettingProbability - 1).toFixed(4)),
    market_gate: gate,
    hard_blockers: blockers,
    source_artifact: `odds-${matchKey}.json`,
  });
  const marketEvaluations = [
    evaluation({ evaluationId: "we-ml", matchKey: firstKey, selection: "WE ML", family: "series_ml", side: "team1", line: null, modelProbability: 0.40, bettingProbability: 0.37, currentOdds: 3.00 }),
    evaluation({ evaluationId: "tes-ml", matchKey: firstKey, selection: "TES ML", family: "series_ml", side: "team2", line: null, modelProbability: 0.60, bettingProbability: 0.57, currentOdds: 1.30 }),
    evaluation({ evaluationId: "we-plus-1.5", matchKey: firstKey, selection: "WE +1.5", family: "series_spread", side: "team1", line: 1.5, modelProbability: 0.70, bettingProbability: 0.67, currentOdds: 1.25 }),
    evaluation({ evaluationId: "tes-minus-1.5", matchKey: firstKey, selection: "TES -1.5", family: "series_spread", side: "team2", line: -1.5, modelProbability: 0.30, bettingProbability: 0.27, currentOdds: 3.40 }),
    evaluation({ evaluationId: "we-tes-over-2.5", matchKey: firstKey, selection: "Over 2.5", family: "series_total_maps", side: "over", line: 2.5, modelProbability: 0.55, bettingProbability: 0.52, currentOdds: 1.80 }),
    evaluation({ evaluationId: "we-tes-under-2.5", matchKey: firstKey, selection: "Under 2.5", family: "series_total_maps", side: "under", line: 2.5, modelProbability: 0.45, bettingProbability: 0.42, currentOdds: 2.00 }),
    evaluation({ evaluationId: "bro-ml", matchKey: secondKey, selection: "BRO ML", family: "series_ml", side: "team2", line: null, modelProbability: 0.56, bettingProbability: 0.53, currentOdds: 1.82 }),
    evaluation({ evaluationId: "ns-ml", matchKey: secondKey, selection: "NS ML", family: "series_ml", side: "team1", line: null, modelProbability: 0.44, bettingProbability: 0.41, currentOdds: 1.80 }),
    evaluation({ evaluationId: "bro-plus-1.5", matchKey: secondKey, selection: "BRO +1.5", family: "series_spread", side: "team2", line: 1.5, modelProbability: 0.80, bettingProbability: 0.77, currentOdds: 1.20 }),
    evaluation({ evaluationId: "ns-minus-1.5", matchKey: secondKey, selection: "NS -1.5", family: "series_spread", side: "team1", line: -1.5, modelProbability: 0.20, bettingProbability: 0.17, currentOdds: 5.00 }),
    evaluation({ evaluationId: "ns-bro-over-2.5", matchKey: secondKey, selection: "Over 2.5", family: "series_total_maps", side: "over", line: 2.5, modelProbability: 0.50, bettingProbability: 0.47, currentOdds: 1.90 }),
    evaluation({ evaluationId: "ns-bro-under-2.5", matchKey: secondKey, selection: "Under 2.5", family: "series_total_maps", side: "under", line: 2.5, modelProbability: 0.50, bettingProbability: 0.47, currentOdds: 1.90 }),
  ];
  const marketChecks = [firstKey, secondKey].flatMap((matchKey) => [
    { match_key: matchKey, format: "BO3", market_family: "series_ml", line: null, status: "priced", evaluated_selection_count: 2, artifact_path: `odds-${matchKey}.json` },
    { match_key: matchKey, format: "BO3", market_family: "series_spread", line: 1.5, status: "priced", evaluated_selection_count: 2, artifact_path: `odds-${matchKey}.json` },
    { match_key: matchKey, format: "BO3", market_family: "series_total_maps", line: 2.5, status: "priced", evaluated_selection_count: 2, artifact_path: `odds-${matchKey}.json` },
  ]);
  return {
    schema_version: 2,
    generated_at: "2026-08-14T13:30:00+08:00",
    market_coverage: {
      status: "full",
      checked_market_types: ["ML", "Spread", "Totals"],
      unavailable_or_unmapped_market_types: [],
      market_checks: marketChecks,
    },
    market_evaluations: marketEvaluations,
    matches: [
      {
        match_key: firstKey,
        action: "bet_now",
        selection: "WE ML",
        market_evaluation_id: "we-ml",
        current_odds: 3.0,
        betting_probability: 0.37,
        minimum_acceptable_odds: 2.76,
        adjusted_ev: 0.11,
        model_confidence: 0.70,
        stake_units: 0.5,
        hard_blockers: [],
        trigger: null,
        reason: "調整後 EV 通過且無硬阻擋",
        table_cell: tableCell,
      },
      {
        match_key: secondKey,
        action: "price_watch",
        selection: "BRO ML",
        market_evaluation_id: "bro-ml",
        current_odds: 1.82,
        betting_probability: 0.53,
        minimum_acceptable_odds: 1.93,
        adjusted_ev: -0.0354,
        model_confidence: 0.77,
        stake_units: 0,
        hard_blockers: [],
        trigger: "BRO ML 升至 1.93 後重抓價格",
        reason: "方向成立但當前價不足",
        table_cell: "等價：BRO ML @1.82；≥1.93 才進場；目前 0u",
      },
    ],
    ranking: [
      { rank: 1, match_key: "lpl:2026-08-14:we-tes", rationale: "唯一立即可打" },
      { rank: 2, match_key: "lck:2026-08-14:ns-bro", rationale: "最接近觸發價" },
    ],
    all_zero_audit: null,
  };
}

function reportFor(slate) {
  return `分析正文\n\n### 簡表總結\n\n| 比賽 | 投注決策 |\n|---|---|\n${slate.matches.map((item) => `| ${item.match_key} | ${item.table_cell} |`).join("\n")}\n`;
}

{
  const slate = validSlate();
  assert.doesNotThrow(() =>
    validateDecisionSlate(
      slate,
      reportFor(slate),
      slate.matches.map((item) => ({ match_key: item.match_key, format: "BO3" })),
    ),
  );
}

{
  const slate = validSlate();
  const firstKey = slate.matches[0].match_key;
  slate.market_evaluations = slate.market_evaluations.filter(
    (evaluation) => !(
      evaluation.match_key === firstKey &&
      evaluation.market_family === "series_total_maps"
    ),
  );
  slate.market_coverage.market_checks = slate.market_coverage.market_checks.filter(
    (check) => !(
      check.match_key === firstKey &&
      check.market_family === "series_total_maps"
    ),
  );
  slate.market_coverage.market_checks
    .filter((check) => check.match_key === firstKey)
    .forEach((check) => { check.format = "BO5"; });
  slate.market_coverage.market_checks.push(
    { match_key: firstKey, format: "BO5", market_family: "series_spread", line: 2.5, status: "unavailable", evaluated_selection_count: 0, artifact_path: "odds-bo5.json" },
    { match_key: firstKey, format: "BO5", market_family: "series_total_maps", line: 3.5, status: "unavailable", evaluated_selection_count: 0, artifact_path: "odds-bo5.json" },
    { match_key: firstKey, format: "BO5", market_family: "series_total_maps", line: 4.5, status: "unavailable", evaluated_selection_count: 0, artifact_path: "odds-bo5.json" },
  );
  slate.market_coverage.status = "partial";
  slate.market_coverage.unavailable_or_unmapped_market_types = [
    `${firstKey}: Spread 2.5`,
    `${firstKey}: Totals 3.5`,
    `${firstKey}: Totals 4.5`,
  ];
  const schedule = [
    { match_key: firstKey, format: "BO5" },
    { match_key: slate.matches[1].match_key, format: "BO3" },
  ];
  assert.doesNotThrow(() => validateDecisionSlate(slate, reportFor(slate), schedule));
  slate.market_coverage.market_checks = slate.market_coverage.market_checks.filter(
    (check) => !(
      check.match_key === firstKey &&
      check.market_family === "series_total_maps" &&
      check.line === 3.5
    ),
  );
  assert.throws(
    () => validateDecisionSlate(slate, reportFor(slate), schedule),
    /must check series_total_maps:3.5/,
  );
}

{
  const slate = validSlate();
  slate.matches[0].action = "price_watch";
  slate.matches[0].stake_units = 0;
  slate.matches[0].trigger = "等更高價格";
  assert.throws(
    () => validateDecisionSlate(slate, reportFor(slate)),
    /qualifying price cannot remain 0u/,
  );
}

{
  const slate = validSlate();
  slate.matches = [slate.matches[1]];
  slate.market_evaluations = slate.market_evaluations.filter(
    (evaluation) => evaluation.match_key === slate.matches[0].match_key,
  );
  slate.market_coverage.market_checks = slate.market_coverage.market_checks.filter(
    (check) => check.match_key === slate.matches[0].match_key,
  );
  slate.ranking = [{ rank: 1, match_key: slate.matches[0].match_key, rationale: "最接近" }];
  assert.throws(
    () => validateDecisionSlate(slate, reportFor(slate)),
    /all_zero_audit must be an object/,
  );
  slate.all_zero_audit = {
    why_no_bet_now: "唯一已映射市場未達底價",
    closest_candidate_match_key: slate.matches[0].match_key,
    rerun_triggers: ["價格達 1.93", "正式先發公布"],
  };
  assert.doesNotThrow(() => validateDecisionSlate(slate, reportFor(slate)));
}

{
  const slate = validSlate();
  slate.market_coverage.market_checks = slate.market_coverage.market_checks.filter(
    (check) => !(check.match_key === slate.matches[0].match_key && check.market_family === "series_spread"),
  );
  slate.market_evaluations = slate.market_evaluations.filter(
    (evaluation) => !(evaluation.match_key === slate.matches[0].match_key && evaluation.market_family === "series_spread"),
  );
  assert.throws(
    () => validateDecisionSlate(
      slate,
      reportFor(slate),
      slate.matches.map((item) => ({ match_key: item.match_key, format: "BO3" })),
    ),
    /must check series_spread:1.5/,
  );
}

{
  const slate = validSlate();
  const spread = slate.market_evaluations.find((evaluation) => evaluation.evaluation_id === "we-plus-1.5");
  spread.current_odds = 1.70;
  spread.adjusted_ev = Number((spread.current_odds * spread.betting_probability - 1).toFixed(4));
  assert.throws(
    () => validateDecisionSlate(slate, reportFor(slate)),
    /highest adjusted-EV eligible market/,
  );
}

{
  const slate = validSlate();
  slate.matches[1].table_cell = "0u";
  assert.throws(
    () => validateDecisionSlate(slate, reportFor(slate)),
    /cannot be only 0u/,
  );
}

{
  const slate = validSlate();
  assert.throws(
    () => validateDecisionSlate(slate, "### 簡表總結\nmissing cells"),
    /not present in the final summary/,
  );
}

console.log("OK: validate_decision_slate regression tests");
