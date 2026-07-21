from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from automation.common import JobError, load_pr_summary


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


if __name__ == "__main__":
    unittest.main()
