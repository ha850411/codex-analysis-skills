---
name: cs-analysis
description: "Analyze Counter-Strike 2/CS:GO esports, choose a winner, and give compact score, per-map, total-map and market predictions. Use for CS2, HLTV matchups, BO1/BO3/BO5, veto updates, 「即時比分」「經濟滾球」「整日賽事」「賽後校準」. Exclude installation, settings and general gameplay. Default to Traditional Chinese and Taiwan time."
---

# Counter-Strike Match Analysis

Respond in Traditional Chinese (Taiwan). Use Taiwan time (Asia/Taipei). Support BO1/BO3/BO5; separate historical CS:GO data from CS2.

## Conclusion principles

- Start with 「**我看好 {隊名} 贏。**」, immediately followed by win probability and that team's representative score. Default to the higher series win probability in the same primary distribution. Even near parity, choose the higher side and add 「小幅優勢」; do not substitute 「雙方都有機會」 or 「等 veto 再說」 for an answer.
- For exactly equal probabilities, choose qualitatively using verified matchups, label 「模型同率，定性選 X」, and keep percentages unchanged. If quantification is unavailable but comparable evidence exists, name a qualitative winner and label 「勝率未量化」. Only when there is no basis to choose, state that the winner cannot be determined and list gaps; never choose arbitrarily or invent 50%.
- The favored team's representative score is its most probable winning outcome. If it differs from the overall modal score, list the actual mode and probability on a separate line; do not call the representative score the most likely overall outcome. See `references/prediction-data.md` for calculations.
- Separate 「看好誰贏」 from 「是否下注」. Missing prices, 0u, and baseline/experimental status do not replace winner assessment. Choosing a side neither guarantees a win nor increases the original probability.
- Default to detailed results with brief explanation: tabulate data; give at most three one-sentence reasons tying comparable evidence to this match's maps/roles. Retain only the most important reversal condition; attach full research and audits. Expand reasoning only when the user requests depth.

## Execution contract

Read `../shared/analysis-core.md` first, and `../shared/forecast/contract.md` when generating new probabilities. The shared layer handles time, snapshots, probabilities and evaluation; this skill handles per-map data, rosters/roles, the current map pool, veto, side selection and LAN/Online. Use this skill's compact results template.

- Confirm the requested event and Taiwan date. For daily requests, inventory the entire target set; do not select only easy matches.
- Read `references/source-priority.md` to verify changing facts. Save event identity, source content, publication and verification times; never fill gaps from model memory.
- Before modeling in `full` or `daily-summary`, read applicable sections of `references/domain-analysis.md`. Also read relevant sections for veto/roster follow-ups; quick mode does not waive research. For new probabilities, read `../shared/prediction-methodology.md`, verify evidence against actual inputs, and check counterevidence. Domain reasoning must not directly overwrite computed results.
- Verify roster, map and opponent-strength comparability before comparing attack/defense, opening-kill conversion and economy rounds. Distinguish map-selection bias from repeatable weaknesses; never present a projected veto as official.
- When using the shared CS v2 model, run `scripts/audit_model.py` under section 4.1 of `references/domain-analysis.md`. Check actual rating updates, per-map opponent adjustments, data periods and BO applicability before interpreting results. Audits and ablations are diagnostic; they do not automatically change probabilities or promote versions.
- For live betting, verify the live score, team orientation, side switches, current rules and available economy state under section 7 of `references/domain-analysis.md`; rebuild the distribution with a model that accepts that state. Shared prematch predict does not support round economy: changing timestamps and snapshot names does not make it live. Keep snapshot names `live-m{X}-r{Y}`, `live-post-m{X}` or `live-halftime`; set `data_cutoff` to the confirmed round time. Under the shared contract, distinguish `reconstructed_after_start` from prospective forecasts for a specific map; never present either as a prospective prematch forecast for the whole series.
- New calculations: `python3 shared/forecast/cli.py train|predict|validate|record|derive|evaluate|render`. See the shared contract for inputs and examples. Label baseline, experimental, and production models separately.
- Build the primary score distribution first, then run `scripts/summarize_forecast.py` under `references/prediction-data.md` to derive the winner, scores, expected map count/difference and conditional per-map probabilities. Do not estimate separate display values or infer round scores from series win probability.
- Create a complete new snapshot when official information changes. Before publication, validate and save it, then render the report from the same data.
- After completing or updating a report, automatically classify and archive it under `../shared/report-storage.md` using shared `report_archive.py save --sport cs` with the actual task mode and date. Gemini and Codex use the same workflow; preserve output templates, original paths, and historical versions.

## Modes and output

- Read the applicable mode in `references/output-template.md`. For a single prematch forecast use full: conclusion, data, compact per-map table, and at most three reasons. 「完整分析」 retains all applicable data; only 「深入／詳細／展開原因」 expands explanations. Deliver results directly in chat; attachments must not replace the answer.
- Use quick for a single probability follow-up: answer its probability, composition, fair price and key limitations, continuing the market the user is asking about. For new veto/roster information, use the update format and show affected maps and before/after results; do not merely repeat the old conclusion.
- Use daily-summary for the full daily target set. Use live for in-play requests, prioritizing the confirmed state, conditional probabilities, changes from the previous snapshot and invalidation conditions. Brief explanations must still include required numbers and unknowns. Validate new probabilities and save snapshots.
- Do not repeat a five-column bottom summary for a single match. In daily-summary, use one match-prediction overview table plus short per-match cards. This presentation rule is CS-specific; other sports retain their templates.
- Every match must show 「預測信心度（證據品質）x/100」 separately from win probability. Retain the canonical forecast's score; it is not winner accuracy. Show N/A with a reason when unknown. Consolidate major data limitations into one line instead of repeating them.
- Both full and daily-summary chat bodies must show both teams' win probabilities for every forecast map, with actual team names as columns. Cover 1/3/5 possible map slots for BO1/BO3/BO5. Daily per-map probabilities must not appear only in attachments. Label official/projected veto; condition later-map win probabilities on 「該圖開打時」 and separately show the probability of reaching the map. State gaps when computation is unsupported; do not substitute historical win rates.
- Introduce market data only after probabilities are locked; read `../shared/markets/collection-contract.md`. Assign no positive stake without traceable prices or when using an uncalibrated baseline.
- Activate `../prediction-pipeline/SKILL.md` only when the user explicitly requests agy or 「模型互審」. Do not start extra models for ordinary analysis.
- Export to Notion under `../shared/notion/skill-instructions.md` and existing authorization.

## Postmortem and improvement

First read `../shared/postmortem-improvement.md` and `references/postmortem-calibration.md`. Prioritize winner accuracy, then scores; report probability quality and coverage separately. Never reconstruct a supposed original prediction without its original snapshot. Register new factors as candidate; keep them experiment-only without paired out-of-sample evidence of improvement. Lower confidence or stakes do not demonstrate improved accuracy.

Inventory that day's published reports and deduplicate by event. Keep separate ledgers for pre-veto, post-veto, live and reconstruction after start. Store the cross-day error ledger, evaluated records and `factor-registry.json` in `.automation-state/cs/history/`. Each review must read history for the same version/snapshot; an update to the same match is not another successful prediction.
