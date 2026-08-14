from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import time
from datetime import datetime, timedelta

os.environ["AUTOMATION_EMAIL_TRANSPORT"] = "mock"

from automation.common import (
    TAIPEI,
    JobError,
    cleanup_old_reports,
    load_factor_registry,
    load_improvement_plan,
    load_pr_summary,
    recreate_dated_output_dir,
    send_email,
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
            "factor_audit": {
                "omission_search": "檢查資料缺口、交互作用與版本切換，未發現可直接上線的新因子",
                "noise_review": "檢查既有因子的增量效益與時序，未做因子異動",
                "new_candidates": [],
                "activated": [],
                "retired": [],
                "restored": [],
            },
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

    def test_registry_only_retirement_requires_paired_validation(self) -> None:
        plan = self.plan()
        plan.update({
            "change_type": "feature_model",
            "decision": "apply-registry",
            "validation": {"method": "paired_walk_forward", "passed": True},
        })
        plan["factor_audit"]["retired"] = ["recent-win-rate"]
        loaded = load_improvement_plan(
            self.write(plan),
            has_changes=False,
            factor_transitions={
                "new_candidates": [],
                "activated": [],
                "retired": ["recent-win-rate"],
                "restored": [],
            },
        )
        self.assertEqual(loaded["decision"], "apply-registry")

    def test_rejects_unvalidated_factor_restore(self) -> None:
        plan = self.plan()
        plan.update({
            "change_type": "feature_model",
            "decision": "apply-registry",
            "validation": {"method": "none", "passed": False},
        })
        plan["factor_audit"]["restored"] = ["travel-fatigue"]
        with self.assertRaisesRegex(JobError, "paired_walk_forward"):
            load_improvement_plan(
                self.write(plan),
                has_changes=False,
                factor_transitions={
                    "new_candidates": [],
                    "activated": [],
                    "retired": [],
                    "restored": ["travel-fatigue"],
                },
            )

    def test_model_change_requires_paired_walk_forward(self) -> None:
        plan = self.plan()
        plan["change_type"] = "feature_model"
        with self.assertRaisesRegex(JobError, "paired_walk_forward"):
            load_improvement_plan(self.write(plan), has_changes=True)


class FactorRegistryTests(unittest.TestCase):
    @staticmethod
    def factor(factor_id: str, status: str = "active") -> dict[str, object]:
        return {
            "factor_id": factor_id,
            "name": factor_id,
            "kind": "predictive_factor",
            "status": status,
            "used_for_prediction": status == "active",
            "mechanism": "可重複的賽前機制",
            "pre_match_observable": "只使用預測快照前可取得資料",
            "evidence": ["paired cohort"],
            "decision_reason": "目前生命週期裁決",
            "revisit_triggers": ["資料品質修復"] if status == "retired" else [],
            "last_reviewed": "2026-07-24T08:30:00+08:00",
        }

    def write(self, payload: dict[str, object], name: str) -> Path:
        directory = getattr(self, "_directory", None)
        if directory is None:
            directory = tempfile.TemporaryDirectory()
            self._directory = directory
            self.addCleanup(directory.cleanup)
        path = Path(directory.name) / name
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def registry(self, factors: list[dict[str, object]]) -> dict[str, object]:
        return {
            "schema_version": 1,
            "updated_at": "2026-07-24T08:30:00+08:00",
            "factors": factors,
        }

    def test_detects_retired_factor_without_deleting_history(self) -> None:
        prior = self.write(
            self.registry([self.factor("recent-win-rate")]),
            "prior.json",
        )
        retired = self.factor("recent-win-rate", "retired")
        current = self.write(self.registry([retired]), "current.json")
        _, transitions = load_factor_registry(current, prior_path=prior)
        self.assertEqual(transitions["retired"], ["recent-win-rate"])

    def test_new_factor_must_start_as_candidate(self) -> None:
        prior = self.write(self.registry([self.factor("elo")]), "prior.json")
        current = self.write(
            self.registry([
                self.factor("elo"),
                self.factor("travel-fatigue", "active"),
            ]),
            "current.json",
        )
        with self.assertRaisesRegex(JobError, "must enter.*candidate"):
            load_factor_registry(current, prior_path=prior)

    def test_rejects_deleting_retired_record(self) -> None:
        prior = self.write(
            self.registry([self.factor("travel-fatigue", "retired")]),
            "prior.json",
        )
        current = self.write(self.registry([]), "current.json")
        with self.assertRaisesRegex(JobError, "append-only"):
            load_factor_registry(current, prior_path=prior)

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

    def test_lol_history_prefers_match_key_with_legacy_id_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            history = root / "history/evaluated-forecasts.jsonl"
            legacy = root / "legacy.jsonl"
            current = root / "current.jsonl"
            shared = {
                "predicted_at": "2026-08-08T13:33:00+08:00",
                "snapshot": "pre-lineup/pre-draft",
                "model_version": "v1",
            }
            legacy.write_text(
                json.dumps({**shared, "match_id": 123, "actual_score": "2-0"})
                + "\n",
                encoding="utf-8",
            )
            current.write_text(
                "\n".join(
                    [
                        json.dumps({
                            **shared,
                            "match_id": 123,
                            "match_key": "bo3:123",
                            "actual_score": "2-1",
                        }),
                        json.dumps({
                            **shared,
                            "match_id": None,
                            "match_key": "lol:lck:20260808T1800+0800:ns:dns",
                            "actual_score": "0-2",
                        }),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            result = sync_evaluated_history(
                history,
                (legacy, current),
                key_fields=(
                    "match_key", "predicted_at", "snapshot", "model_version",
                ),
            )
            records = [
                json.loads(line)
                for line in history.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(result["records"], 2)
            self.assertEqual(records[0]["actual_score"], "2-1")
            self.assertIsNone(records[1]["match_id"])


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


class SendEmailTransportTests(unittest.TestCase):
    def test_mock_transport_never_opens_smtp_and_can_record_outbox(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            outbox = Path(temp_dir) / "mail" / "outbox.jsonl"
            with (
                mock.patch.dict(
                    os.environ,
                    {
                        "AUTOMATION_EMAIL_TRANSPORT": "mock",
                        "AUTOMATION_NOTIFICATION_EMAIL": "user@example.com",
                        "AUTOMATION_EMAIL_MOCK_OUTBOX": str(outbox),
                    },
                    clear=False,
                ),
                mock.patch("smtplib.SMTP") as smtp_mock,
                mock.patch("smtplib.SMTP_SSL") as smtp_ssl_mock,
            ):
                recipients = send_email("測試主旨", "測試內容")

            self.assertEqual(recipients, ["user@example.com"])
            smtp_mock.assert_not_called()
            smtp_ssl_mock.assert_not_called()
            messages = [
                json.loads(line)
                for line in outbox.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(len(messages), 1)
            self.assertEqual(messages[0]["subject"], "測試主旨")
            self.assertEqual(messages[0]["body"], "測試內容")

    def test_mock_transport_uses_non_routable_default_recipient(self) -> None:
        with mock.patch.dict(
            os.environ,
            {
                "AUTOMATION_EMAIL_TRANSPORT": "mock",
                "AUTOMATION_NOTIFICATION_EMAIL": "",
                "AUTOMATION_EMAIL_MOCK_OUTBOX": "",
            },
            clear=False,
        ):
            self.assertEqual(
                send_email("測試主旨", "測試內容"),
                ["mock@example.invalid"],
            )

    def test_rejects_unknown_email_transport(self) -> None:
        with mock.patch.dict(
            os.environ,
            {"AUTOMATION_EMAIL_TRANSPORT": "unexpected"},
            clear=False,
        ):
            with self.assertRaisesRegex(
                JobError,
                "AUTOMATION_EMAIL_TRANSPORT must be smtp or mock",
            ):
                send_email("測試主旨", "測試內容")


if __name__ == "__main__":
    unittest.main()
