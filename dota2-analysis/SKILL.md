---
name: dota2-analysis
description: "Analyze Dota 2 esports schedules, rosters, patches, hero pools, Draft/BP, lanes, series probabilities, market value and 「賽後校準」. Use for TI, Riyadh Masters, DreamLeague, ESL One, PGL, BLAST, FISSURE, BO1/BO2/BO3/BO5, 「至少一局」「今日決策」. Exclude installation, general gameplay and non-esports questions. Default to Traditional Chinese and Taiwan time."
---

# Dota 2 Match Analysis

Respond in Traditional Chinese (Taiwan). Use Taiwan time (Asia/Taipei). BO2 must include 2-0/1-1/0-2; never force it into a two-way moneyline.

## Execution contract

Read `../shared/analysis-core.md` first, and `../shared/forecast/contract.md` when generating new probabilities. The shared layer handles time, snapshots, probabilities, evaluation and output; this skill handles patches, the actual five players and roles, hero pools, draft, lanes and Radiant/Dire.

- Confirm the requested event and Taiwan date. For daily requests, inventory the entire target set; do not select only easy matches.
- Read `references/source-priority.md` to verify changing facts. Save event identity, source content, publication and verification times; never fill gaps from model memory.
- Before modeling in `full` or `daily-summary`, read the applicable sections of `references/domain-analysis.md`. For new probabilities, also read `../shared/prediction-methodology.md`, verify evidence against actual inputs, and check counterevidence. Domain reasoning must not directly overwrite computed results.
- Assess win conditions from the actual five players/roles, patch, and conversion of lanes into the first key items and objectives. Before draft publication, analyze evidenced composition functions and counters; do not invent a full BP or the magnitude of later-game adjustments.
- New calculations: `python3 shared/forecast/cli.py train|predict|validate|record|derive|evaluate|render`. See the shared contract for inputs and examples. Label baseline, experimental, and production models separately.
- Build the primary score distribution first; derive the winner, modal score, and other markets from it. If the predicted winner and modal score favor different sides, explain both; do not manually change scores.
- Create a complete new snapshot when official information changes. Before publication, validate and save it, then render the report from the same data.
- After completing or updating a report, automatically classify and archive it under `../shared/report-storage.md` using shared `report_archive.py save --sport dota2` with the actual task mode and date. Gemini and Codex use the same workflow; preserve output templates, original paths, and historical versions.

## Modes and output

- Default to quick for a single follow-up. New probabilities still require validation and snapshots; shorten only the prose.
- Default to full for one match and daily-summary for a full day. Read `references/output-template.md`.
- In chat, provide the conclusion, up to three supporting points, main risk, full-report link, and exactly one narrow table at the bottom. Keep details in the full report.
- Model confidence measures evidence quality, separately from win probability. Show N/A with a reason when unknown.
- Introduce market data only after probabilities are locked; read `../shared/markets/collection-contract.md`. Assign no positive stake without traceable prices or when using an uncalibrated baseline.
- Activate `../prediction-pipeline/SKILL.md` only when the user explicitly requests agy or 「模型互審」. Do not start extra models for ordinary analysis.
- Export to Notion under `../shared/notion/skill-instructions.md` and existing authorization.

## Postmortem and improvement

First read `../shared/postmortem-improvement.md` and `references/postmortem-calibration.md`. Prioritize winner accuracy, then scores; report probability quality and coverage separately. Never reconstruct a supposed original prediction without its original snapshot. Register new factors as candidate; keep them experiment-only without paired out-of-sample evidence of improvement. Lower confidence or stakes do not demonstrate improved accuracy.
