from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import time
from datetime import datetime, timedelta

from automation.common import TAIPEI, JobError, cleanup_old_reports, load_pr_summary


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


if __name__ == "__main__":
    unittest.main()
