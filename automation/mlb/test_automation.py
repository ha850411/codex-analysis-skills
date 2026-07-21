from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path

from common import JobError, atomic_json, load_jsonl
from predict_next_day import extract_taipei_games, validate_forecasts
from review_today import is_recent_report, safe_date, validate_skill_frontmatter


class AutomationTests(unittest.TestCase):
    def test_atomic_json_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "status.json"
            atomic_json(path, {"status": "ok", "中文": True})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["status"], "ok")

    def test_load_jsonl_rejects_non_object(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "records.jsonl"
            path.write_text("[]\n", encoding="utf-8")
            with self.assertRaises(JobError):
                load_jsonl(path)

    def test_no_games_sentinel_is_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecasts.jsonl"
            path.write_text(
                json.dumps({"status": "no-games", "date": "2026-12-25", "sources": ["MLB"]}) + "\n",
                encoding="utf-8",
            )
            validate_forecasts(path)

    def test_invalid_date_is_rejected(self) -> None:
        with self.assertRaises(JobError):
            safe_date("2026-7-2")

    def test_frontmatter_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory) / "demo-skill"
            skill.mkdir()
            (skill / "SKILL.md").write_text(
                "---\nname: demo-skill\ndescription: Demo\n---\n\n# Demo\n",
                encoding="utf-8",
            )
            validate_skill_frontmatter(skill)

    def test_schedule_is_filtered_by_taipei_date(self) -> None:
        payload = {
            "dates": [{"games": [
                {"gamePk": 1, "gameDate": "2026-07-21T23:00:00Z"},
                {"gamePk": 2, "gameDate": "2026-07-22T17:00:00Z"},
            ]}]
        }
        games = extract_taipei_games([payload], "2026-07-22")
        self.assertEqual([game["gamePk"] for game in games], [1])

    def test_report_must_be_within_24_hours(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "prediction.md"
            report.write_text("report", encoding="utf-8")
            self.assertTrue(is_recent_report(report))
            old = time.time() - 25 * 3600
            __import__("os").utime(report, (old, old))
            self.assertFalse(is_recent_report(report))


if __name__ == "__main__":
    unittest.main()
