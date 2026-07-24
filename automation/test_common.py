from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import time
from datetime import datetime, timedelta

from automation.common import (
    TAIPEI,
    JobError,
    cleanup_old_reports,
    load_pr_summary,
    recreate_dated_output_dir,
)


class PrSummaryTests(unittest.TestCase):
    def write(self, content: str) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "pr-summary.md"
        path.write_text(content, encoding="utf-8")
        return path

    def test_accepts_required_sections(self) -> None:
        path = self.write(
            "## 本次調整\n\n- 降低過時資料權重。\n\n"
            "## 發現的問題\n\n- 原流程未檢查資料時效。\n"
        )
        self.assertEqual(load_pr_summary(path), path.read_text(encoding="utf-8").strip())

    def test_rejects_missing_or_empty_sections(self) -> None:
        for content in (
            "## 本次調整\n\n- 調整權重。\n",
            "## 本次調整\n\n## 發現的問題\n\n- 資料過時。\n",
        ):
            with self.subTest(content=content):
                with self.assertRaises(JobError):
                    load_pr_summary(self.write(content))

    def test_rejects_oversized_summary(self) -> None:
        path = self.write(
            "## 本次調整\n\n- 調整。\n\n## 發現的問題\n\n- " + "過長" * 100
        )
        with self.assertRaises(JobError):
            load_pr_summary(path, max_chars=100)


class CleanupTests(unittest.TestCase):
    def test_cleanup_deletes_reports_older_than_three_days(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            today = datetime.now(TAIPEI).date()
            dates = {
                "today": (today).isoformat(),
                "one_day_ago": (today - timedelta(days=1)).isoformat(),
                "two_days_ago": (today - timedelta(days=2)).isoformat(),
                "three_days_ago": (today - timedelta(days=3)).isoformat(),
                "four_days_ago": (today - timedelta(days=4)).isoformat(),
                "ten_days_ago": (today - timedelta(days=10)).isoformat(),
            }
            # Create prediction & review dirs for mlb and lol
            for module in ("mlb", "lol"):
                for category in ("predictions", "reviews"):
                    for key, d_str in dates.items():
                        path = root / module / category / d_str
                        path.mkdir(parents=True, exist_ok=True)
                        (path / "report.md").write_text("test", encoding="utf-8")

            # Perform cleanup (days=3)
            deleted = cleanup_old_reports(days=3, state_dir=root)

            # Assert four_days_ago and ten_days_ago are deleted
            self.assertFalse((root / "mlb/predictions" / dates["four_days_ago"]).exists())
            self.assertFalse((root / "mlb/predictions" / dates["ten_days_ago"]).exists())
            self.assertFalse((root / "lol/reviews" / dates["four_days_ago"]).exists())

            # Assert today, 1 day, 2 days, 3 days ago are kept
            self.assertTrue((root / "mlb/predictions" / dates["today"]).exists())
            self.assertTrue((root / "mlb/predictions" / dates["one_day_ago"]).exists())
            self.assertTrue((root / "mlb/predictions" / dates["two_days_ago"]).exists())
            self.assertTrue((root / "mlb/predictions" / dates["three_days_ago"]).exists())

            self.assertEqual(len(deleted), 8)  # 2 modules * 2 categories * 2 old dates

    def test_cleanup_dry_run_does_not_delete_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            today = datetime.now(TAIPEI).date()
            old_date = (today - timedelta(days=5)).isoformat()
            target_path = root / "mlb/predictions" / old_date
            target_path.mkdir(parents=True, exist_ok=True)

            deleted = cleanup_old_reports(days=3, state_dir=root, dry_run=True)
            self.assertIn(target_path, deleted)
            self.assertTrue(target_path.exists())


class RecreateOutputDirTests(unittest.TestCase):
    def test_recreates_only_the_requested_date_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            predictions = Path(temp_dir) / "predictions"
            target = predictions / "2026-07-22"
            target.mkdir(parents=True)
            (target / "old.txt").write_text("old", encoding="utf-8")

            self.assertTrue(recreate_dated_output_dir(target, predictions))
            self.assertTrue(target.is_dir())
            self.assertEqual(list(target.iterdir()), [])

    def test_rejects_paths_outside_the_expected_parent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            predictions = root / "predictions"
            outside = root / "2026-07-22"
            outside.mkdir()
            marker = outside / "keep.txt"
            marker.write_text("keep", encoding="utf-8")

            with self.assertRaises(JobError):
                recreate_dated_output_dir(outside, predictions)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")


class NotifyReviewByEmailTests(unittest.TestCase):
    def test_notify_review_by_email_creates_receipt_and_calls_send_email(self) -> None:
        from unittest import mock
        from automation.common import notify_review_by_email
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "postmortem.md").write_text("postmortem content", encoding="utf-8")
            (review_dir / "pr-summary.md").write_text("## 本次調整\n- 無\n\n## 發現的問題\n- 無", encoding="utf-8")

            with mock.patch("automation.common.send_email", return_value=["test@example.com"]) as send_mock:
                notify_review_by_email("lol", review_dir, "2026-07-22", pr_created=False)
                send_mock.assert_called_once()
                subject, body = send_mock.call_args[0]
                self.assertIn("LOL 復盤報告已完成（未建立 PR）｜2026-07-22", subject)
                self.assertIn("LOL 預測復盤報告已完成", body)
                receipt = review_dir / "email-notification.json"
                self.assertTrue(receipt.is_file())

            # Second call should skip sending email because receipt exists
            with mock.patch("automation.common.send_email") as send_mock2:
                notify_review_by_email("lol", review_dir, "2026-07-22", pr_created=False)
                send_mock2.assert_not_called()


class NotifyFailureByEmailTests(unittest.TestCase):
    def test_notify_failure_by_email_creates_receipt_and_sends_email(self) -> None:
        from unittest import mock
        from automation.common import fail, notify_failure_by_email
        with tempfile.TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "2026-07-22"
            job_dir.mkdir()
            exc = JobError("Schedule verification incomplete: missing source")

            with mock.patch("automation.common.send_email", return_value=["user@example.com"]) as send_mock:
                notify_failure_by_email(job_dir, "prediction", exc, module="lol")
                send_mock.assert_called_once()
                subject, body = send_mock.call_args[0]
                self.assertIn("LOL 自動排程預測遇到問題｜2026-07-22", subject)
                self.assertIn("Schedule verification incomplete: missing source", body)

                receipt = job_dir / "email-failure-notification.json"
                self.assertTrue(receipt.is_file())

            # Second call with same error should skip sending email
            with mock.patch("automation.common.send_email") as send_mock2:
                notify_failure_by_email(job_dir, "prediction", exc, module="lol")
                send_mock2.assert_not_called()

    def test_fail_function_triggers_failure_notification(self) -> None:
        from unittest import mock
        from automation.common import fail
        with tempfile.TemporaryDirectory() as temp_dir:
            job_dir = Path(temp_dir) / "2026-07-22"
            job_dir.mkdir()
            exc = RuntimeError("Unexpected engine crash")

            with mock.patch("automation.common.send_email", return_value=["user@example.com"]) as send_mock:
                code = fail(job_dir, "prediction", exc)
                self.assertEqual(code, 1)
                send_mock.assert_called_once()
                subject, body = send_mock.call_args[0]
                self.assertIn("自動排程預測遇到問題", subject)
                self.assertIn("Unexpected engine crash", body)

                status_json = json.loads((job_dir / "status.json").read_text(encoding="utf-8"))
                self.assertEqual(status_json["status"], "failed")
                self.assertIn("Unexpected engine crash", status_json["error"])


if __name__ == "__main__":
    unittest.main()


