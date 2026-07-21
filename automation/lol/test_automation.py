from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

AUTOMATION_DIR = Path(__file__).resolve().parents[1]
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))
os.environ["AUTOMATION_MODULE"] = "lol"

from common import JobError
from predict_next_day import extract_taipei_s_matches, validate_forecasts
from review_today import is_recent_report, settled_match_ids


class LolAutomationTests(unittest.TestCase):
    def test_filters_tier_and_taipei_date(self) -> None:
        records = [
            {"id": 1, "tier": "s", "start_date": "2026-07-22T09:00:00Z"},
            {"id": 2, "tier": "a", "start_date": "2026-07-22T09:00:00Z"},
            {"id": 3, "tier": "s", "start_date": "2026-07-21T09:00:00Z"},
        ]
        self.assertEqual([item["id"] for item in extract_taipei_s_matches(records, "2026-07-22")], [1])

    def test_exact_score_contract(self) -> None:
        record = {
            "match_id": 1, "predicted_at": "now", "start_time": "later",
            "snapshot": "pre-match", "model_version": "v1", "team1": "A",
            "team2": "B", "tournament": "LPL", "tier": "s", "bo_type": 3,
            "exact_score_probabilities": {"2-0": 0.25, "2-1": 0.30, "1-2": 0.25, "0-2": 0.20},
            "team1_win_prob": 0.55, "team2_win_prob": 0.45,
            "team1_at_least_one_prob": 0.80, "team2_at_least_one_prob": 0.75,
            "model_confidence": 0.64, "sources": ["bo3.gg"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecasts.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            validate_forecasts(path)
            record["team1_win_prob"] = 0.60
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaises(JobError):
                validate_forecasts(path)

    def test_settled_match_filter(self) -> None:
        matches = [
            {"id": 1, "status": "finished", "winner_team_id": 10},
            {"id": 2, "status": "upcoming", "winner_team_id": None},
            {"id": 3, "status": "finished", "winner_team_id": 30},
        ]
        self.assertEqual(settled_match_ids(matches, {1, 2}), {1})

    def test_report_must_be_recent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prediction.md"
            path.write_text("report", encoding="utf-8")
            self.assertTrue(is_recent_report(path))
            old = time.time() - 25 * 3600
            __import__("os").utime(path, (old, old))
            self.assertFalse(is_recent_report(path))


if __name__ == "__main__":
    unittest.main()
