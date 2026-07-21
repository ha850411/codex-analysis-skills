from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

AUTOMATION_DIR = Path(__file__).resolve().parents[1]
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))
os.environ["AUTOMATION_MODULE"] = "mlb"

from common import JobError, atomic_json, codex_command, load_jsonl, review_branch, send_email
from predict_next_day import extract_taipei_games, validate_forecasts, validate_notion_summary
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

    def test_review_branch_uses_feature_module_mmdd(self) -> None:
        self.assertEqual(review_branch("MLB", "2026-07-21"), "feature/MLB-0721")
        self.assertEqual(review_branch("LOL", "2026-07-21"), "feature/LOL-0721")

    @mock.patch("common.require_executable", return_value="/usr/bin/codex")
    def test_codex_command_uses_scheduled_model_settings(self, _: mock.Mock) -> None:
        settings = {
            "AUTOMATION_CODEX_MODEL": "gpt-5.6-sol",
            "AUTOMATION_REASONING_EFFORT": "high",
        }
        with mock.patch.dict(os.environ, settings, clear=False):
            command = codex_command(Path("/tmp/work"), Path("/tmp/last.txt"), "prompt")
        self.assertIn("gpt-5.6-sol", command)
        self.assertIn('model_reasoning_effort="high"', command)

    @mock.patch("common.require_executable", return_value="/usr/bin/codex")
    def test_codex_global_options_precede_exec_subcommand(self, _: mock.Mock) -> None:
        command = codex_command(Path("/tmp/work"), Path("/tmp/last.txt"), "prompt")
        exec_index = command.index("exec")
        self.assertLess(command.index("--search"), exec_index)
        self.assertLess(command.index("--ask-for-approval"), exec_index)
        self.assertEqual(command[command.index("--ask-for-approval") + 1], "never")

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

    def test_notion_summary_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "notion-summary.json"
            path.write_text(json.dumps({
                "title": "MLB 2026-07-22", "sport": "MLB", "module": "mlb-analysis",
                "event": "MLB", "startTime": "2026-07-22T01:00:00+08:00",
                "prediction": "daily slate", "winner": "N/A", "winProbability": "N/A",
                "recommendation": "see report", "stake": "N/A", "confidence": "60%",
                "risk": "lineups pending", "sourceStatus": "checked",
                "analysisType": "daily-summary", "tags": ["MLB", "prediction"],
            }), encoding="utf-8")
            summary = validate_notion_summary(path)
            self.assertEqual(summary["analysisType"], "daily-summary")

    @mock.patch("smtplib.SMTP")
    def test_email_uses_starttls_and_auth(self, smtp_class: mock.Mock) -> None:
        smtp = smtp_class.return_value.__enter__.return_value
        settings = {
            "SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587",
            "SMTP_SECURITY": "starttls", "SMTP_USERNAME": "sender@example.com",
            "SMTP_PASSWORD": "secret", "SMTP_FROM": "sender@example.com",
            "AUTOMATION_NOTIFICATION_EMAIL": "owner@example.com",
        }
        with mock.patch.dict(__import__("os").environ, settings, clear=False):
            recipients = send_email("subject", "body")
        self.assertEqual(recipients, ["owner@example.com"])
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with("sender@example.com", "secret")
        smtp.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
