---
name: valorant-analysis
description: "Analyze Valorant/特戰英豪 esports schedules, rosters, patches, map pools, veto, agent pools, series probabilities, market value and 「賽後校準」. Use for VCT, Masters, Champions, Challengers, Game Changers, BO3/BO5, 「至少一圖」「今日決策」. Exclude installation, settings, general gameplay and non-esports questions. Default to Traditional Chinese and Taiwan time."
---

# Valorant Match Analysis

Respond in Traditional Chinese (Taiwan). Use Taiwan time (Asia/Taipei). Preserve map-specific rotations within six-player rosters; zero samples or frequent bans do not imply weakness.

## Execution contract

Read `../shared/analysis-core.md` first, and `../shared/forecast/contract.md` when generating new probabilities. The shared layer handles time, snapshots, probabilities, evaluation and output; this skill handles the current event map pool, per-map rosters, agent pools, veto, pick owner and side selection.

- Confirm the requested event and Taiwan date. For daily requests, inventory the entire target set; do not select only easy matches.
- Read `references/source-priority.md` to verify changing facts. Save event identity, source content, publication and verification times; never fill gaps from model memory.
- Before modeling in `full` or `daily-summary`, read the applicable sections of `references/domain-analysis.md`. For new probabilities, also read `../shared/prediction-methodology.md`, verify evidence against actual inputs, and check counterevidence. Domain reasoning must not directly overwrite computed results.
- Jointly check each map's five players, roles, agent composition and veto path. Keep unplayed or frequently banned maps uncertain. Check sample comparability and opponent counters first; never change scores just to avoid predicting 2-1 for every match.
- Infer veto choices from observed ban/pick opportunities under `references/domain-analysis.md` §4.1. Track primary weighted paths separately from sensitivity paths; map win rates alone do not establish pick preference.
- Before publication, run `audit-model-use` under `references/forecast-engine.md` on the selected series snapshot. Tie numerical claims to primary fitted inputs; keep unintegrated tactical reasoning conditional. Save the audit and the loaded skill/reference hashes beside the snapshot without changing its schema.
- Published calculations retain the existing shared `forecast/cli.py train|predict|validate|record|derive|evaluate|render` entry until paired evidence supports a model switch. For trials and shadow comparisons, read `references/forecast-engine.md` and use `python3 valorant-analysis/scripts/valorant_forecast.py train|predict|validate|record|render|evaluate|compare|walk-forward`. This v3 entry is experiment-only: it connects timestamped map/roster inputs and legal veto paths to the primary distribution, and renders the existing template. When timestamped inputs are available, save v3 beside the existing primary as a shadow forecast; keep the published report on its selected primary snapshot. Missing veto evidence must retain the explicit unresolved fallback. Never describe implementation tests or development replays as improved accuracy.
- Use shared `forecast/cli.py validate|record|derive|evaluate` for canonical v2 interoperability. Before recording v3, also run its own `validate --model ... --event ...` for full input/model replay. The shared validator alone does not verify map marginals or fitted-feature use. Model, event and forecast artifacts remain create-only; new evidence requires a new snapshot.
- Build the primary score distribution first; derive the winner, modal score, and other markets from it. If the predicted winner and modal score favor different sides, explain both; do not manually change scores.
- Create a complete new snapshot when official information changes. Before publication, validate and save it, then render the report from the same data.
- After completing or updating a report, automatically classify and archive it under `../shared/report-storage.md` using shared `report_archive.py save --sport valorant` with the actual task mode and date. Gemini and Codex use the same workflow; preserve output templates, original paths, and historical versions.
- Replay legacy snapshots under `references/forecast-snapshot.md`, preserving their original IDs. Use shared record for new v2 snapshots.

## Modes and output

- Default to quick for a single follow-up. New probabilities still require validation and snapshots; shorten only the prose. A prediction update must retain the required numerical fields for the affected match.
- Default to full for one match and daily-summary for a full day. Read and strictly follow `references/output-template.md` for every prediction output, including quick updates.
- In both chat and the full report, use the mandatory per-match format: winner, both teams' win probabilities and fair odds, complete series score distribution, applicable map handicaps and totals, expected maps, evidence confidence, and both teams' forecast win probabilities for every map in the current event pool. Daily summaries must repeat this format for every match; never move required numbers solely into an attachment.
- Show per-map probabilities under explicit veto, roster and side assumptions, conditional on that map being played. Distinguish these from historical win rates and map appearance probabilities. Preserve every map row; use N/A with a specific reason for unavailable estimates or excluded maps, never invented percentages.
- Follow the numerical blocks with up to three supporting points, the main risk, model status, sources and the full-report link, then exactly one five-column summary table at the bottom. Check every required field against the template before delivery; a generic renderer's output alone does not establish format compliance.
- Model confidence measures evidence quality, separately from win probability. Show N/A with a reason when unknown.
- Introduce market data only after probabilities are locked; read `../shared/markets/collection-contract.md`. Assign no positive stake without traceable prices or when using an uncalibrated baseline.
- Activate `../prediction-pipeline/SKILL.md` only when the user explicitly requests agy or 「模型互審」. Do not start extra models for ordinary analysis.
- Export to Notion under `../shared/notion/skill-instructions.md` and existing authorization.

## Postmortem and improvement

First read `../shared/postmortem-improvement.md` and `references/postmortem-calibration.md`. Prioritize winner accuracy, then scores; report probability quality and coverage separately. Never reconstruct a supposed original prediction without its original snapshot. Register new factors as candidate; keep them experiment-only without paired out-of-sample evidence of improvement. Lower confidence or stakes do not demonstrate improved accuracy.
