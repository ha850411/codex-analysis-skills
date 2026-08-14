#!/usr/bin/env node

import assert from "node:assert/strict";
import { validateDecisionSlate } from "./validate_decision_slate.mjs";

const tableCell = "立即可打：WE ML @3.00；底價 2.76；0.5u";

function validSlate() {
  return {
    schema_version: 1,
    generated_at: "2026-08-14T13:30:00+08:00",
    market_coverage: {
      status: "partial",
      checked_market_types: ["ML"],
      unavailable_or_unmapped_market_types: ["1st Map ML"],
    },
    matches: [
      {
        match_key: "lpl:2026-08-14:we-tes",
        action: "bet_now",
        selection: "WE ML",
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
        match_key: "lck:2026-08-14:ns-bro",
        action: "price_watch",
        selection: "BRO ML",
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
    validateDecisionSlate(slate, reportFor(slate), slate.matches.map((item) => item.match_key)),
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
