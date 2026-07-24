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
    load_improvement_plan,
    load_pr_summary,
    recreate_dated_output_dir,
    sync_evaluated_history,
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


class ImprovementPlanTests(unittest.TestCase):
    @staticmethod
    def plan() -> dict[str, object]:
        return {
            "objective": "out_of_sample_predictive_accuracy",
            "change_type": "data_pipeline",
            "decision": "merge",
            "production_change": True,
            "confidence_or_stake_only": False,
            "predictive_mechanism": "修正先發資料時序，避免錯誤投手進入得分分布",
            "baseline": {
                "model_version": "v1",
                "sample_size": 8,
                "metrics": {"brier": 0.24},
            },
            "challenger": {
                "model_version": "v1.0.1",
                "sample_size": 8,
                "metrics": {"brier": 0.21},
            },
            "validation": {"method": "regression_test", "passed": True},
            "evidence": ["test_probable_pitcher_snapshot"],
            "rollback": "回復 v1 並停用新 freshness gate",
        }

    def write(self, plan: dict[str, object]) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "improvement-plan.json"
        path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
        return path

    def test_accepts_validated_predictive_fix(self) -> None:
        plan = load_improvement_plan(self.write(self.plan()), has_changes=True)
        self.assertEqual(plan["decision"], "merge")

    def test_rejects_confidence_only_pr(self) -> None:
        plan = self.plan()
        plan["confidence_or_stake_only"] = True
        with self.assertRaisesRegex(JobError, "do not qualify"):
            load_improvement_plan(self.write(plan), has_changes=True)

    def test_model_change_requires_paired_walk_forward(self) -> None:
        plan = self.plan()
        plan["change_type"] = "feature_model"
        with self.assertRaisesRegex(JobError, "paired_walk_forward"):
            load_improvement_plan(self.write(plan), has_changes=True)


class EvaluatedHistoryTests(unittest.TestCase):
    def test_history_upserts_by_immutable_prediction_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            history = root / "history/evaluated-forecasts.jsonl"
            first = root / "review-1.jsonl"
            second = root / "review-2.jsonl"
            first.write_text(
                json.dumps(
                    {
                        "game_id": 1,
                        "predicted_at": "2026-07-22T21:00:00+08:00",
                        "snapshot": "pre-lineup",
                        "model_version": "v1",
                        "actual_home_runs": 3,
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            second.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "game_id": 1,
                                "predicted_at": "2026-07-22T21:00:00+08:00",
                                "snapshot": "pre-lineup",
                                "model_version": "v1",
                                "actual_home_runs": 4,
                            }
                        ),
                        json.dumps(
                            {
                                "game_id": 2,
                                "predicted_at": "2026-07-23T21:00:00+08:00",
                                "snapshot": "pre-lineup",
                                "model_version": "v1",
                                "actual_home_runs": 2,
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = sync_evaluated_history(
                history,
                (first, second),
                key_fields=("game_id", "predicted_at", "snapshot", "model_version"),
            )
            records = [
                json.loads(line)
                for line in history.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(result["records"], 2)
            self.assertEqual(records[0]["actual_home_runs"], 4)
            self.assertEqual(records[1]["game_id"], 2)

            sync_evaluated_history(
                history,
                (second,),
                key_fields=("game_id", "predicted_at", "snapshot", "model_version"),
            )
            self.assertEqual(
                len(history.read_text(encoding="utf-8").splitlines()),
                2,
            )


class CleanupTests(unittest.TestCase):
    def test_cleanup_deletes_reports_older_than_thirty_days_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            today = datetime.now(TAIPEI).date()
            dates = {
                "today": (today).isoformat(),
                "one_day_ago": (today - timedelta(days=1)).isoformat(),
                "twenty_nine_days_ago": (today - timedelta(days=29)).isoformat(),
                "thirty_days_ago": (today - timedelta(days=30)).isoformat(),
                "thirty_one_days_ago": (today - timedelta(days=31)).isoformat(),
                "sixty_days_ago": (today - timedelta(days=60)).isoformat(),
            }
            # Create prediction & review dirs for mlb and lol
            for module in ("mlb", "lol"):
                for category in ("predictions", "reviews"):
                    for key, d_str in dates.items():
                        path = root / module / category / d_str
                        path.mkdir(parents=True, exist_ok=True)
                        (path / "report.md").write_text("test", encoding="utf-8")
            history = root / "mlb/history/evaluated-forecasts.jsonl"
            history.parent.mkdir(parents=True)
            history.write_text("{}\n", encoding="utf-8")

            deleted = cleanup_old_reports(state_dir=root)

            self.assertFalse((root / "mlb/predictions" / dates["thirty_one_days_ago"]).exists())
            self.assertFalse((root / "mlb/predictions" / dates["sixty_days_ago"]).exists())
            self.assertFalse((root / "lol/reviews" / dates["thirty_one_days_ago"]).exists())

            self.assertTrue((root / "mlb/predictions" / dates["today"]).exists())
            self.assertTrue((root / "mlb/predictions" / dates["one_day_ago"]).exists())
            self.assertTrue((root / "mlb/predictions" / dates["twenty_nine_days_ago"]).exists())
            self.assertTrue((root / "mlb/predictions" / dates["thirty_days_ago"]).exists())
            self.assertTrue(history.exists())

            self.assertEqual(len(deleted), 8)  # 2 modules * 2 categories * 2 old dates

    def test_cleanup_dry_run_does_not_delete_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            today = datetime.now(TAIPEI).date()
            old_date = (today - timedelta(days=31)).isoformat()
            target_path = root / "mlb/predictions" / old_date
            target_path.mkdir(parents=True, exist_ok=True)

            deleted = cleanup_old_reports(state_dir=root, dry_run=True)
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


class MergePullRequestTests(unittest.TestCase):
    def test_merges_exact_validated_head_and_verifies_result(self) -> None:
        from types import SimpleNamespace
        from unittest import mock
        from automation.common import merge_pull_request

        head = "a" * 40
        merge_commit = "b" * 40
        pr_url = "https://github.com/example/repo/pull/7"
        responses = [
            SimpleNamespace(stdout=head + "\n"),
            SimpleNamespace(stdout=""),
            SimpleNamespace(
                stdout=json.dumps(
                    {
                        "state": "MERGED",
                        "mergedAt": "2026-07-24T01:00:00Z",
                        "mergeCommit": {"oid": merge_commit},
                        "url": pr_url,
                    }
                )
            ),
        ]
        with (
            mock.patch("automation.common.require_executable", return_value="/usr/bin/gh"),
            mock.patch("automation.common.run", side_effect=responses) as run_mock,
        ):
            result = merge_pull_request(pr_url, Path("/tmp/review-worktree"))

        merge_argv = run_mock.call_args_list[1].args[0]
        self.assertIn("--match-head-commit", merge_argv)
        self.assertIn(head, merge_argv)
        self.assertEqual(result["merge_commit"], merge_commit)
        self.assertEqual(result["pr_url"], pr_url)


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

    def test_merged_pr_email_includes_pr_and_merge_commit(self) -> None:
        from unittest import mock
        from automation.common import notify_review_by_email
        with tempfile.TemporaryDirectory() as temp_dir:
            review_dir = Path(temp_dir)
            (review_dir / "postmortem.md").write_text("postmortem content", encoding="utf-8")
            pr_url = "https://github.com/example/repo/pull/7"
            merge_commit = "a" * 40

            with mock.patch("automation.common.send_email", return_value=["test@example.com"]) as send_mock:
                notify_review_by_email(
                    "mlb",
                    review_dir,
                    "2026-07-23",
                    pr_created=True,
                    pr_url=pr_url,
                    pr_merged=True,
                    merge_commit=merge_commit,
                )
                subject, body = send_mock.call_args[0]
                self.assertIn("已合併 PR", subject)
                self.assertIn(pr_url, body)
                self.assertIn(merge_commit, body)
                receipt = json.loads(
                    (review_dir / "email-notification.json").read_text(encoding="utf-8")
                )
                self.assertTrue(receipt["pr_merged"])
                self.assertEqual(receipt["merge_commit"], merge_commit)

    def test_merged_pr_email_rejects_incomplete_merge_evidence(self) -> None:
        from automation.common import notify_review_by_email
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaisesRegex(JobError, "requires PR URL and merge commit"):
                notify_review_by_email(
                    "mlb",
                    Path(temp_dir),
                    "2026-07-23",
                    pr_created=True,
                    pr_url="https://github.com/example/repo/pull/7",
                    pr_merged=True,
                )


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
