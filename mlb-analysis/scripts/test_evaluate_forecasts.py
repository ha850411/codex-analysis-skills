#!/usr/bin/env python3
"""Regression tests for the MLB immutable forecast evaluator."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from evaluate_forecasts import _validate_record, availability_audit


class AvailabilityAuditTests(unittest.TestCase):
    def test_missing_data_counts_include_scorable_and_unscored_records(self) -> None:
        records = [
            _validate_record(
                {
                    "game_id": "baseline-1",
                    "snapshot": "pre-lineup",
                    "model_version": "baseline-v1",
                    "status": "baseline",
                    "home_win_prob": 0.55,
                    "away_runs_mean": 4.1,
                    "home_runs_mean": 4.4,
                    "missing_data": ["lineup", "weather"],
                    "actual_away_runs": 3,
                    "actual_home_runs": 5,
                },
                1,
            ),
            _validate_record(
                {
                    "game_id": "unmodeled-1",
                    "snapshot": "pre-lineup",
                    "model_version": "N/A-no-model",
                    "status": "unmodeled",
                    "missing_data": ["lineup"],
                    "actual_away_runs": 2,
                    "actual_home_runs": 4,
                },
                2,
            ),
        ]

        audit = availability_audit(records)

        self.assertEqual(audit["scorable_records"], 1)
        self.assertEqual(audit["unscored_records"], 1)
        self.assertEqual(audit["missing_data_counts"], {"lineup": 2, "weather": 1})


if __name__ == "__main__":
    unittest.main()
