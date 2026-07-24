#!/usr/bin/env python3

import io
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pipeline


class PipelineUnitTests(unittest.TestCase):
    def complete_review(self) -> dict:
        return {
            "schema_version": "1.0",
            "prediction_id": "p1",
            "stage": "red_team",
            "generated_at": "2026-07-17T10:01:00+08:00",
            "reviewer": {"tool": "agy", "model": "test-model"},
            "verdict": "revise",
            "summary": "發現一項需裁決問題。",
            "findings": [{
                "id": "f1",
                "severity": "low",
                "category": "presentation",
                "claim": "缺少一項說明。",
                "evidence_ids": [],
                "recommended_action": "補上說明。",
            }],
            "consistency_checks": [
                {"audit_area": area, "name": area, "status": "pass", "details": f"已檢查 {area}。"}
                for area in sorted(pipeline.AUDIT_AREAS)
            ],
            "unresolved_questions": ["這項缺口會如何影響信心度？"],
        }

    def test_market_blind_input_removes_prices(self) -> None:
        source = {"prediction_id": "p1", "model_data": {"evidence": []}, "market_data": [{"decimal_odds": 2.0}]}
        result = pipeline.market_blind_input(source)
        self.assertNotIn("market_data", result)
        self.assertEqual(result["market_data_visibility"], "withheld_from_all_probability_stages")
        self.assertIn("market_data", source)

    def test_red_team_defaults_disable_confirmation(self) -> None:
        defaults = pipeline.load_model_defaults(pipeline.DEFAULT_MODEL_DEFAULTS)
        self.assertIs(defaults["confirmation_required"], False)
        self.assertIsInstance(defaults["red_team"]["model"], str)
        self.assertTrue(defaults["red_team"]["model"])

    def test_model_plan_is_notification_only(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            result = pipeline.notify_model_plan(
                "primary-model",
                "medium",
                "red-team-agent",
                "final-model",
                "high",
            )
        notice = output.getvalue()
        self.assertIsNone(result)
        self.assertIn("Codex 主預測：primary-model", notice)
        self.assertIn("agy 紅隊審查：red-team-agent", notice)
        self.assertIn("Codex 最終裁決：final-model", notice)
        self.assertIn("自動開始執行", notice)

    def test_confidence_weighting(self) -> None:
        confidence = {
            "value": 74,
            "rationale": "test",
            "components": {
                "data_completeness": 80,
                "freshness": 75,
                "lineup_certainty": 70,
                "regime_relevance": 75,
                "model_stability": 65,
            },
        }
        self.assertEqual(pipeline.validate_confidence(confidence, "test"), [])
        confidence["value"] = 80
        self.assertTrue(any("expected rounded weighted score" in error for error in pipeline.validate_confidence(confidence, "test")))

    def test_boolean_is_not_accepted_as_numeric_probability(self) -> None:
        prediction = {
            "schema_version": "1.0",
            "prediction_id": "p1",
            "stage": "primary",
            "generated_at": "2026-07-17T10:00:00+08:00",
            "model": "test-model",
            "reasoning_effort": "high",
            "thesis": "test",
            "probability_groups": [{
                "id": "winner",
                "label": "winner",
                "outcomes": [
                    {"key": "a", "label": "A", "probability": True},
                    {"key": "b", "label": "B", "probability": 99},
                ],
            }],
            "confidence": {
                "value": 74,
                "rationale": "test",
                "components": {
                    "data_completeness": 80,
                    "freshness": 75,
                    "lineup_certainty": 70,
                    "regime_relevance": 75,
                    "model_stability": 65,
                },
            },
            "key_factors": [],
            "risks": [],
            "missing_data": [],
        }
        self.assertTrue(any("probability must be from 0 to 100" in error for error in pipeline.validate_prediction(prediction, "primary")))

    def test_quarter_line_settlement_ev(self) -> None:
        input_data = {
            "market_data": [{
                "bet_id": "q1",
                "label": "A -0.25",
                "outcome_key": "win",
                "half_win_outcome_key": "half_win",
                "push_outcome_key": "push",
                "half_loss_outcome_key": "half_loss",
                "decimal_odds": 2.0,
                "book": "test",
                "retrieved_at": "2026-07-17T10:00:00+08:00",
            }]
        }
        final = {"probability_groups": [{
            "id": "settlement",
            "label": "settlement",
            "outcomes": [
                {"key": "win", "label": "win", "probability": 40},
                {"key": "half_win", "label": "half win", "probability": 10},
                {"key": "push", "label": "push", "probability": 10},
                {"key": "half_loss", "label": "half loss", "probability": 10},
                {"key": "loss", "label": "loss", "probability": 30},
            ],
        }]}
        row = pipeline.derived_markets(input_data, final)[0]
        self.assertAlmostEqual(row["ev"], 0.1)
        self.assertAlmostEqual(row["fair_odds"], 1.7778)

    def test_domain_summary_table_is_rendered_verbatim(self) -> None:
        final = {"presentation": {"summary_table": {
            "columns": ["比賽", "預測", "機率", "模型信心度", "建議"],
            "rows": [["A|B", "A", "60%", "74%", "觀望"]],
        }}}
        lines = pipeline.render_summary_table(final)
        self.assertIn("| 比賽 | 預測 | 機率 | 模型信心度 | 建議 |", lines)
        self.assertIn("A\\|B", lines[-1])

    def test_post_market_updates_summary_without_changing_locked_final(self) -> None:
        final = {"presentation": {"summary_table": {
            "columns": ["比賽", "模型信心度", "投注建議"],
            "rows": [["A vs B", "74%", "待市場價格"]],
        }}}
        post_market = {
            "summary_table_updates": [{
                "row_index": 0,
                "column": "投注建議",
                "advice": "A 1.50 為負 EV；不下注，0u",
            }]
        }
        rendered = pipeline.apply_post_market_summary(final, post_market)
        self.assertEqual(rendered["presentation"]["summary_table"]["rows"][0][2], "A 1.50 為負 EV；不下注，0u")
        self.assertEqual(final["presentation"]["summary_table"]["rows"][0][2], "待市場價格")

    def test_post_market_validation_rejects_pending_price_and_incomplete_market_decisions(self) -> None:
        input_data = {
            "prediction_id": "p1",
            "market_data": [{
                "bet_id": "a-ml",
                "outcome_key": "a",
                "decimal_odds": 1.5,
                "book": "Stake",
                "retrieved_at": "2026-07-17T10:00:00+08:00",
            }],
        }
        final = {
            "presentation": {
                "summary_table": {
                    "columns": ["比賽", "模型信心度", "投注建議"],
                    "rows": [["A vs B", "74%", "待市場價格"]],
                }
            }
        }
        post_market = {
            "schema_version": "1.0",
            "prediction_id": "p1",
            "stage": "post_market",
            "generated_at": "2026-07-17T10:05:00+08:00",
            "model": "test-model",
            "reasoning_effort": "high",
            "market_coverage": {
                "status": "partial",
                "books": ["Stake"],
                "requested_market_types": ["moneyline", "map handicap"],
                "collected_market_types": ["moneyline"],
                "unavailable_market_types": ["map handicap"],
                "note": "只取得獨贏盤。",
            },
            "recommendation_summary": "目前不下注。",
            "decisions": [{
                "bet_id": "a-ml",
                "recommendation": "pass",
                "stake_units": 0,
                "rationale": "市場價格低於模型公允價。",
            }],
            "summary_table_updates": [{
                "row_index": 0,
                "column": "投注建議",
                "advice": "待市場價格",
            }],
            "risks": [],
        }
        errors = pipeline.validate_post_market(post_market, input_data, final)
        self.assertTrue(any("cannot say market price is pending" in error for error in errors))
        post_market["summary_table_updates"][0]["advice"] = "A 1.50 為負 EV；不下注，0u"
        self.assertEqual(pipeline.validate_post_market(post_market, input_data, final), [])

    def test_detailed_analysis_sections_are_rendered_verbatim(self) -> None:
        final = {"presentation": {"analysis_sections": [
            {"heading": "A vs B 完整分析", "markdown": "**逐圖分析：**\n\n| 地圖 | 傾向 |\n| --- | --- |\n| Split | A 55% |"},
            {"heading": "模型校準", "markdown": "- 已套用 agy 修正"},
        ]}}
        lines = pipeline.render_analysis_sections(final)
        output = "\n".join(lines)
        self.assertIn("## A vs B 完整分析", output)
        self.assertIn("| Split | A 55% |", output)
        self.assertIn("## 模型校準", output)

    def test_markdown_includes_detailed_analysis_before_probability_tables(self) -> None:
        input_data = {
            "as_of": "2026-07-17T10:00:00+08:00",
            "event": {
                "competition": "Test League",
                "participants": ["A", "B"],
                "start_time": "2026-07-17T12:00:00+08:00",
                "timezone": "Asia/Taipei",
            },
            "model_data": {"evidence": []},
        }
        final = {
            "model": "test-model",
            "reasoning_effort": "high",
            "accepted_findings": ["f1"],
            "rejected_findings": [],
            "changes": [],
            "finding_adjudications": [{
                "finding_id": "f1",
                "decision": "accept",
                "rationale": "問題成立。",
                "resulting_action": "已補上說明。",
            }],
            "question_resolutions": [{
                "question": "這項缺口會如何影響信心度？",
                "status": "resolved",
                "response": "已反映在信心說明。",
                "impact": "不改機率，降低解讀確定性。",
            }],
            "probability_groups": [{
                "id": "winner",
                "label": "勝負",
                "outcomes": [
                    {"key": "a", "label": "A", "probability": 60},
                    {"key": "b", "label": "B", "probability": 40},
                ],
            }],
            "confidence": {
                "value": 74,
                "rationale": "test",
                "components": {
                    "data_completeness": 80,
                    "freshness": 75,
                    "lineup_certainty": 70,
                    "regime_relevance": 75,
                    "model_stability": 65,
                },
            },
            "risks": [],
            "missing_data": [],
            "presentation": {
                "headline": "headline",
                "executive_summary": "summary",
                "analysis_sections": [{"heading": "完整逐場分析", "markdown": "逐圖與 veto 正文"}],
                "key_points": [],
                "disclaimer": "",
                "summary_table": {
                    "columns": ["比賽", "預測", "機率", "模型信心度", "建議"],
                    "rows": [["A vs B", "A", "60%", "74%", "觀望"]],
                },
            },
        }
        review = self.complete_review()
        output = pipeline.render_markdown(input_data, final, review, [])
        self.assertLess(output.index("## 完整逐場分析"), output.index("## 最終機率"))
        self.assertNotIn("### Findings 與逐條裁決", output)
        self.assertNotIn("#### f1｜low｜presentation", output)
        self.assertNotIn("agy 疑問／主張：缺少一項說明。", output)
        self.assertIn("## agy 紅隊審查（精簡）", output)
        self.assertIn("未修改；保留原預測。", output)
        self.assertNotIn("Codex 裁決摘要", output)
        self.assertNotIn("完整一致性檢查", output)
        self.assertNotIn("#### Q1.", output)
        self.assertNotIn("Codex 回覆", output)
        self.assertEqual(output.count("## 簡表總結"), 1)
        self.assertTrue(output.rstrip().endswith("|"))

    def test_final_validation_rejects_missing_or_reserved_analysis_sections(self) -> None:
        presentation = {
            "headline": "headline",
            "executive_summary": "summary",
            "analysis_sections": [],
            "key_points": [],
            "disclaimer": "",
            "summary_table": {
                "columns": ["比賽", "預測", "機率", "模型信心度", "建議"],
                "rows": [["A vs B", "A", "60%", "74%", "觀望"]],
            },
            "youtube": {"title": "title", "hook": "hook", "sections": [], "closing": "closing"},
        }
        errors = pipeline.validate_prediction({"presentation": presentation}, "final")
        self.assertTrue(any("analysis_sections must be a non-empty array" in error for error in errors))
        presentation["analysis_sections"] = [{"heading": "完整分析", "markdown": "## 簡表總結"}]
        errors = pipeline.validate_prediction({"presentation": presentation}, "final")
        self.assertTrue(any("reserved final-output content" in error for error in errors))

    def test_review_requires_all_nine_audit_areas(self) -> None:
        review = self.complete_review()
        self.assertEqual(pipeline.validate_review(review), [])
        review["consistency_checks"].pop()
        self.assertTrue(any("missing audit areas" in error for error in pipeline.validate_review(review)))

    def test_legacy_reviewer_agent_field_remains_readable(self) -> None:
        review = self.complete_review()
        review["reviewer"] = {"tool": "agy", "agent": "legacy-model-label"}
        self.assertEqual(pipeline.validate_review(review), [])

    def test_review_selector_skips_empty_json_object(self) -> None:
        input_data = {"prediction_id": "p1", "model_data": {"evidence": []}, "market_data": []}
        primary = {
            "prediction_id": "p1",
            "analysis_sections": [],
            "thesis": "A",
            "confidence": {"value": 50, "components": {}},
            "probability_groups": [],
            "key_factors": [],
        }
        raw = "noise {} more-noise " + pipeline.json.dumps(self.complete_review(), ensure_ascii=False)
        review, errors = pipeline.select_review(raw, input_data, primary, "Gemini 3.5 Flash (High)")
        self.assertEqual(errors, [])
        self.assertIsNotNone(review)
        self.assertEqual(review["verdict"], "revise")
        self.assertEqual(review["reviewer"]["model"], "Gemini 3.5 Flash (High)")

    def test_invoke_agy_uses_model_flag_and_persists_raw_output(self) -> None:
        completed = subprocess.CompletedProcess(args=[], returncode=0, stdout='{"verdict":"pass"}', stderr="")
        with TemporaryDirectory() as temp_dir, patch.object(pipeline, "run_process", return_value=completed) as mocked:
            output = Path(temp_dir) / "red_team_review.json"
            raw = pipeline.invoke_agy("prompt", output, "Gemini 3.5 Flash (High)", 60)
            command = mocked.call_args.args[0]
            self.assertIn("--model", command)
            self.assertNotIn("--agent", command)
            self.assertEqual(command[command.index("--model") + 1], "Gemini 3.5 Flash (High)")
            self.assertEqual(raw, completed.stdout)
            self.assertEqual((Path(temp_dir) / "red-team-attempt-1-raw.txt").read_text(encoding="utf-8").strip(), completed.stdout)

    def test_red_team_retries_once_then_writes_only_valid_review(self) -> None:
        input_data = {"prediction_id": "p1", "model_data": {"evidence": []}, "market_data": []}
        primary = {
            "prediction_id": "p1",
            "analysis_sections": [],
            "thesis": "A",
            "confidence": {"value": 50, "components": {}},
            "probability_groups": [],
            "key_factors": [],
        }
        valid_raw = pipeline.json.dumps(self.complete_review(), ensure_ascii=False)
        with TemporaryDirectory() as temp_dir, \
                patch.object(pipeline, "require_agy_model"), \
                patch.object(pipeline, "invoke_agy", side_effect=["{}", valid_raw]) as mocked:
            output = Path(temp_dir) / "red_team_review.json"
            review = pipeline.create_red_team_review("prompt", output, input_data, primary, "test-model", 60)
            self.assertEqual(mocked.call_count, 2)
            self.assertEqual(review["verdict"], "revise")
            self.assertEqual(pipeline.load_json(output)["reviewer"]["model"], "test-model")
            self.assertTrue((Path(temp_dir) / "red-team-attempt-1-errors.txt").is_file())

    def test_red_team_does_not_write_official_artifact_after_two_invalid_responses(self) -> None:
        input_data = {"prediction_id": "p1", "model_data": {"evidence": []}, "market_data": []}
        primary = {
            "prediction_id": "p1",
            "analysis_sections": [],
            "thesis": "A",
            "confidence": {"value": 50, "components": {}},
            "probability_groups": [],
            "key_factors": [],
        }
        with TemporaryDirectory() as temp_dir, \
                patch.object(pipeline, "require_agy_model"), \
                patch.object(pipeline, "invoke_agy", side_effect=["{}", "{}"]):
            output = Path(temp_dir) / "red_team_review.json"
            with self.assertRaises(pipeline.PipelineError):
                pipeline.create_red_team_review("prompt", output, input_data, primary, "test-model", 60)
            self.assertFalse(output.exists())
            self.assertTrue((Path(temp_dir) / "red-team-attempt-2-errors.txt").is_file())

    def test_red_team_prompt_embeds_domain_skill_and_output_template(self) -> None:
        skill_path = pipeline.ROOT.parent / "lol-analysis" / "SKILL.md"
        contract = pipeline.domain_review_contract(str(skill_path))
        self.assertIn("DOMAIN SKILL", contract)
        self.assertIn("DOMAIN OUTPUT TEMPLATE", contract)
        self.assertIn("League of Legends", contract)

    def test_cross_validation_requires_every_finding_and_question_resolution(self) -> None:
        input_data = {"prediction_id": "p1", "model_data": {"evidence": []}, "market_data": []}
        primary = {
            "prediction_id": "p1",
            "analysis_sections": [{"heading": "完整分析", "markdown": "甲" * 100}],
            "thesis": "A",
            "confidence": {"value": 50, "components": {}},
            "probability_groups": [],
            "key_factors": [],
        }
        review = self.complete_review()
        final = {
            "prediction_id": "p1",
            "accepted_findings": [],
            "rejected_findings": [],
            "finding_adjudications": [],
            "question_resolutions": [],
            "changes": [],
            "thesis": "A",
            "confidence": {"value": 50, "components": {}},
            "probability_groups": [],
            "key_factors": [],
            "presentation": {"analysis_sections": [{"heading": "摘要", "markdown": "甲" * 20}]},
        }
        errors = pipeline.cross_validate(input_data, primary, review, final)
        self.assertTrue(any("red-team findings not adjudicated" in error for error in errors))
        self.assertTrue(any("question_resolutions" in error for error in errors))
        self.assertTrue(any("report collapsed" in error for error in errors))

        final["accepted_findings"] = ["f1"]
        final["finding_adjudications"] = [{
            "finding_id": "f1",
            "decision": "accept",
            "rationale": "成立",
            "resulting_action": "補充",
        }]
        final["question_resolutions"] = [{
            "question": review["unresolved_questions"][0],
            "status": "unresolved",
            "response": "缺少資料",
            "impact": "降低信心",
        }]
        final["presentation"]["analysis_sections"][0]["markdown"] = "甲" * 70
        self.assertEqual(pipeline.cross_validate(input_data, primary, review, final), [])

    def test_export_keeps_full_red_team_review_in_json_and_only_lists_changes_in_markdown(self) -> None:
        confidence = {
            "value": 74,
            "rationale": "測試信心度",
            "components": {
                "data_completeness": 80,
                "freshness": 75,
                "lineup_certainty": 70,
                "regime_relevance": 75,
                "model_stability": 65,
            },
        }
        probability_groups = [{
            "id": "winner",
            "label": "勝負",
            "outcomes": [
                {"key": "a", "label": "A", "probability": 60},
                {"key": "b", "label": "B", "probability": 40},
            ],
        }]
        input_data = {
            "schema_version": "1.0",
            "prediction_id": "p1",
            "created_at": "2026-07-17T10:00:00+08:00",
            "as_of": "2026-07-17T10:00:00+08:00",
            "sport": "Test",
            "mode": "full",
            "question": "A vs B？",
            "event": {
                "event_id": "e1",
                "competition": "Test League",
                "start_time": "2026-07-17T12:00:00+08:00",
                "timezone": "Asia/Taipei",
                "format": "BO3",
                "participants": ["A", "B"],
            },
            "model_data": {
                "data_quality": {"completeness": 80, "missing": [], "warnings": []},
                "evidence": [],
                "notes": [],
            },
            "market_data": [],
        }
        primary = {
            "schema_version": "1.0",
            "prediction_id": "p1",
            "stage": "primary",
            "generated_at": "2026-07-17T10:01:00+08:00",
            "model": "primary-model",
            "reasoning_effort": "high",
            "thesis": "A 小優",
            "analysis_sections": [{"heading": "完整分析", "markdown": "完整主報告內容。" * 20}],
            "probability_groups": probability_groups,
            "confidence": confidence,
            "key_factors": [],
            "risks": [],
            "missing_data": [],
        }
        review = self.complete_review()
        final = {
            "schema_version": "1.0",
            "prediction_id": "p1",
            "stage": "final",
            "generated_at": "2026-07-17T10:02:00+08:00",
            "model": "final-model",
            "reasoning_effort": "high",
            "accepted_findings": ["f1"],
            "rejected_findings": [],
            "finding_adjudications": [{"finding_id": "f1", "decision": "accept", "rationale": "成立。", "resulting_action": "補充說明。"}],
            "question_resolutions": [{"question": review["unresolved_questions"][0], "status": "resolved", "response": "已回答。", "impact": "不改機率。"}],
            "changes": [{
                "path": "presentation.analysis_sections.完整分析",
                "before": "未說明樣本限制",
                "after": "補充樣本限制",
                "reason": "回應紅隊 finding",
                "finding_ids": ["f1"],
            }],
            "thesis": "A 小優",
            "probability_groups": probability_groups,
            "confidence": confidence,
            "key_factors": [],
            "risks": [],
            "missing_data": [],
            "presentation": {
                "headline": "完整測試報告",
                "executive_summary": "A 小優。",
                "analysis_sections": [{"heading": "完整分析", "markdown": "完整主報告內容。" * 20}],
                "key_points": [],
                "disclaimer": "僅供測試。",
                "summary_table": {"columns": ["比賽", "預測", "機率", "模型信心度", "建議"], "rows": [["A vs B", "A", "60%", "74%", "觀望"]]},
                "youtube": {"title": "測試", "hook": "測試", "sections": [], "closing": "測試"},
            },
        }
        with TemporaryDirectory() as temp_dir:
            run_dir = Path(temp_dir)
            pipeline.atomic_json(run_dir / "input.json", input_data)
            pipeline.atomic_json(run_dir / "model-input.json", pipeline.market_blind_input(input_data))
            pipeline.atomic_json(run_dir / "primary_prediction.json", primary)
            pipeline.atomic_json(run_dir / "red_team_review.json", review)
            pipeline.atomic_json(run_dir / "final_prediction.json", final)
            pipeline.export_run(run_dir)
            markdown = (run_dir / "prediction.md").read_text(encoding="utf-8")
            bundle = pipeline.load_json(run_dir / "prediction.json")
            self.assertNotIn("### Findings 與逐條裁決", markdown)
            self.assertNotIn("agy 疑問／主張：缺少一項說明。", markdown)
            self.assertNotIn("Codex 裁決摘要", markdown)
            self.assertNotIn("完整一致性檢查", markdown)
            self.assertNotIn("Codex 回覆：已回答。", markdown)
            self.assertNotIn("agy 結論", markdown)
            self.assertNotIn("審查模型", markdown)
            self.assertIn("## agy 紅隊審查（精簡）", markdown)
            self.assertIn("- presentation.analysis_sections.完整分析：未說明樣本限制 → 補充樣本限制", markdown)
            self.assertNotIn("回應紅隊 finding", markdown)
            self.assertEqual(bundle["red_team"]["findings"][0]["id"], "f1")
            self.assertEqual(bundle["adjudication"]["finding_adjudications"][0]["finding_id"], "f1")
            self.assertEqual(bundle["adjudication"]["question_resolutions"][0]["status"], "resolved")

    def test_red_team_markdown_says_unchanged_when_no_changes(self) -> None:
        output = pipeline.render_red_team_review(self.complete_review(), {"changes": []})
        self.assertEqual(output, ["## agy 紅隊審查（精簡）", "", "未修改；保留原預測。"])

    def test_red_team_markdown_truncates_verbose_change_values(self) -> None:
        long_text = "過長說明" * 30
        output = pipeline.render_red_team_review(
            self.complete_review(),
            {"changes": [{"path": "analysis", "before": long_text, "after": long_text}]},
        )
        self.assertIn("… → ", output[-1])
        self.assertTrue(output[-1].endswith("…"))
        self.assertNotIn(long_text, output[-1])
        self.assertLess(len(output[-1]), len(long_text) * 2)

    def test_youtube_output_ends_with_summary_table(self) -> None:
        input_data = {"as_of": "2026-07-17T10:00:00+08:00"}
        final = {
            "model": "test-model",
            "reasoning_effort": "high",
            "presentation": {
                "summary_table": {
                    "columns": ["比賽", "預測", "機率", "模型信心度", "建議"],
                    "rows": [["A vs B", "A", "60%", "74%", "觀望"]],
                },
                "youtube": {
                    "title": "title",
                    "hook": "hook",
                    "sections": [],
                    "closing": "closing",
                },
            },
        }
        output = pipeline.render_youtube(input_data, final)
        self.assertIn("## 簡表總結", output)
        self.assertNotIn("## 預測總結", output)
        self.assertTrue(output.rstrip().endswith("|"))


if __name__ == "__main__":
    unittest.main()
