#!/usr/bin/env python3

import unittest

import pipeline


class PipelineUnitTests(unittest.TestCase):
    def test_market_blind_input_removes_prices(self) -> None:
        source = {"prediction_id": "p1", "model_data": {"evidence": []}, "market_data": [{"decimal_odds": 2.0}]}
        result = pipeline.market_blind_input(source)
        self.assertNotIn("market_data", result)
        self.assertEqual(result["market_data_visibility"], "withheld_from_all_probability_stages")
        self.assertIn("market_data", source)

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

    def test_youtube_output_ends_with_summary_table_and_model(self) -> None:
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
        self.assertTrue(output.endswith("預測使用模型：test-model high"))


if __name__ == "__main__":
    unittest.main()
