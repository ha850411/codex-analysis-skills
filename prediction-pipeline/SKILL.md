---
name: prediction-pipeline
description: "Coordinate auditable predictions when the user requests 「啟用 agy 紅隊」「agy 紅隊審查」「交給 agy 複核」「雙模型審查」, agy, agy-cli or 「模型互審」 in a prediction or *-analysis request. Announce models for the Codex primary forecast, agy review, Codex final adjudication and conditional post-market decision; proceed without confirmation to create input.json, forecast, review, adjudicate, validate and export Markdown, JSON and YouTube scripts. Never show a model plan for ordinary single-model predictions."
---

# Codex × agy Prediction Pipeline

Respond in Traditional Chinese (Taiwan). Handle only predictions explicitly requesting agy, 「紅隊」 or 「模型互審」; do not start extra models for ordinary single-model analysis. Use the corresponding `*-analysis` skill for domain analysis.

## Startup and data

1. Read `references/model-defaults.json`; the user's current selections take precedence. Run `agy models` to verify availability. Report invalid settings or unavailable models; never silently substitute a model.
2. Announce the models for the primary forecast, red team, final adjudication and conditional market decision, then proceed without another confirmation. In ordinary conversations, default to the current session model; start Codex CLI only when the configuration requires it.
3. Read `references/runbook.md` and `references/contracts.md`; create input and run directories under the relevant schemas. The user need not supply JSON or CLI commands.
4. For new calculations, use the canonical forecast in `../shared/forecast/contract.md`, then convert it to existing v1 input with `pipeline-input`. The primary forecast, red team and final adjudication receive only inputs isolated from market data.

## Review and adjudication

- Include required domain analysis in the primary report before agy reviews the full text. Red-team comments are evidence to adjudicate, not a replacement forecast.
- Focus the red team on facts, chronology, input mapping, strongest counterevidence and distribution errors that could change conclusions. Record source locations, affected assumptions and verifiable corrections in existing finding fields. Model agreement is not new evidence. Do not average two win probabilities to manufacture findings or compromise; retain the original forecast if no substantive issue exists.
- The primary forecast and final adjudication must retain computed values in `computed_probability_groups`. To change probabilities, rebuild the upstream canonical forecast first, then rerun downstream stages. For old inputs without this field, retain legacy mode and disclose calculation-provenance limits.
- Accept or reject every finding with reasons and disposition. Answer every unresolved question or explain the gap and impact. Record all actual numerical and textual edits in changes.
- Preserve coverage using the primary report's section headings. Each section must contain an answer, gap or reason it does not apply. Removing repetition has no word-count-ratio constraint.
- On agy formatting failure, save raw output and errors first. Allow one format-repair attempt with the same model; if it fails again, stop that workflow. Never fabricate a successful artifact.

## Markets and delivery

- Only after locking probabilities, collect prices per match, retry and save success/failure evidence under `../shared/markets/collection-contract.md`. Market data must not feed back into probabilities.
- Create a separate post-market decision only when prices exist, covering every bet_id and summary-table row. Without prices, still complete the model report and label 0u. Disclose incomplete market coverage.
- Run pipeline export to validate schemas, cross-stage consistency, confidence, probabilities, adjudication and market arithmetic. Fix failures upstream.
- Under `../shared/forecast/report-template.md`, output complete prediction.md, prediction.json and chat-summary.md, plus a narration script when requested. End both chat and the full report with exactly one five-column summary table; place links and sources before it.
- Keep full red-team findings and adjudications in JSON; include only conclusion-changing edits in the report body. External publication requires existing authorization; activating agy does not itself authorize publication.

## Report storage

After export, call shared `report_archive.py save` under `../shared/report-storage.md` with the domain skill's sport, actual report mode and target Taiwan date. Archive the full run's reports, JSON, sources/snapshots, validation, red-team and adjudication attachments. Gemini and Codex use the same tool; record agent/model truthfully. Preserve existing templates, model selections and scheduled output paths. On workflow failure, save diagnostic artifacts only with `--status validation-failed` or `incomplete`; never present them as completed reports. The outer analysis skill reuses the successful receipt and report links; save again only when attachments or content change.
