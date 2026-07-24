from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from argparse import Namespace
from contextlib import nullcontext
from datetime import time as datetime_time
from pathlib import Path
from unittest import mock

AUTOMATION_DIR = Path(__file__).resolve().parents[1]
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))
os.environ["AUTOMATION_MODULE"] = "lol"

from common import JobError
from predict_next_day import (
    ScheduleFetch,
    extract_taipei_s_matches,
    fetch_schedule,
    forecast_window,
    main as prediction_main,
    validate_forecast_schedule,
    validate_forecasts,
    validate_schedule_verification,
)
from review_today import is_recent_report, main as review_main, settled_match_ids


class LolAutomationTests(unittest.TestCase):
    def test_existing_prediction_is_regenerated_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            output_dir = state_root / "predictions/2026-07-22"
            output_dir.mkdir(parents=True)
            (output_dir / "prediction.md").write_text("old", encoding="utf-8")
            (output_dir / "forecasts.jsonl").write_text("old\n", encoding="utf-8")
            (output_dir / "email-notification.json").write_text("old", encoding="utf-8")

            with (
                mock.patch("predict_next_day.STATE_ROOT", state_root),
                mock.patch(
                    "predict_next_day.parse_args",
                    return_value=Namespace(date="2026-07-22", force=False, dry_run=False),
                ),
                mock.patch("predict_next_day.cleanup_old_reports"),
                mock.patch("predict_next_day.job_lock", side_effect=lambda _: nullcontext()),
                mock.patch(
                    "predict_next_day.fetch_schedule",
                    return_value=ScheduleFetch(
                        matches=[{}],
                        filtered_payload={"results": []},
                        unfiltered_payload={"results": []},
                        filtered_match_ids=[],
                        client_filtered_match_ids=[],
                    ),
                ),
                mock.patch("predict_next_day.compact_match", return_value={}),
                mock.patch("predict_next_day.codex_command", return_value=["codex", "exec"]),
                mock.patch("predict_next_day.run") as run_mock,
                mock.patch(
                    "predict_next_day.validate_schedule_verification",
                    return_value={"no_matches": False},
                ),
                mock.patch("predict_next_day.finalize_prediction", return_value="https://notion.example/report"),
            ):
                self.assertEqual(prediction_main(), 0)

            run_mock.assert_called_once_with(["codex", "exec"])
            self.assertFalse((output_dir / "prediction.md").exists())
            self.assertFalse((output_dir / "forecasts.jsonl").exists())
            self.assertFalse((output_dir / "email-notification.json").exists())
            self.assertTrue((output_dir / "schedule-precheck.json").exists())
            self.assertTrue((output_dir / "bo3-filtered-response.json").exists())
            self.assertTrue((output_dir / "bo3-unfiltered-response.json").exists())

    def test_dry_run_preserves_existing_prediction_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            output_dir = state_root / "predictions/2026-07-22"
            output_dir.mkdir(parents=True)
            old_report = output_dir / "prediction.md"
            old_report.write_text("old", encoding="utf-8")

            with (
                mock.patch("predict_next_day.STATE_ROOT", state_root),
                mock.patch(
                    "predict_next_day.parse_args",
                    return_value=Namespace(date="2026-07-22", force=False, dry_run=True),
                ),
                mock.patch("predict_next_day.cleanup_old_reports"),
                mock.patch("predict_next_day.job_lock", side_effect=lambda _: nullcontext()),
                mock.patch("predict_next_day.fetch_schedule") as fetch_mock,
            ):
                self.assertEqual(prediction_main(), 0)

            self.assertEqual(old_report.read_text(encoding="utf-8"), "old")
            fetch_mock.assert_not_called()

    def test_incomplete_schedule_never_reaches_publish(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            schedule = ScheduleFetch(
                matches=[],
                filtered_payload={"results": []},
                unfiltered_payload={"results": []},
                filtered_match_ids=[],
                client_filtered_match_ids=[],
            )
            with (
                mock.patch("predict_next_day.STATE_ROOT", state_root),
                mock.patch(
                    "predict_next_day.parse_args",
                    return_value=Namespace(
                        date="2026-07-23", force=False, dry_run=False
                    ),
                ),
                mock.patch("predict_next_day.cleanup_old_reports"),
                mock.patch(
                    "predict_next_day.job_lock",
                    side_effect=lambda _: nullcontext(),
                ),
                mock.patch(
                    "predict_next_day.fetch_schedule", return_value=schedule
                ),
                mock.patch(
                    "predict_next_day.codex_command",
                    return_value=["codex", "exec"],
                ),
                mock.patch("predict_next_day.run"),
                mock.patch(
                    "predict_next_day.validate_schedule_verification",
                    side_effect=JobError("Schedule verification incomplete"),
                ),
                mock.patch(
                    "predict_next_day.finalize_prediction"
                ) as finalize_mock,
            ):
                self.assertEqual(prediction_main(), 1)
            finalize_mock.assert_not_called()
            status = json.loads(
                (
                    state_root
                    / "predictions/2026-07-23/status.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(status["status"], "failed")

    def test_empty_candidate_still_runs_two_source_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            schedule = ScheduleFetch(
                matches=[],
                filtered_payload={"results": []},
                unfiltered_payload={"results": []},
                filtered_match_ids=[],
                client_filtered_match_ids=[],
            )
            with (
                mock.patch("predict_next_day.STATE_ROOT", state_root),
                mock.patch(
                    "predict_next_day.parse_args",
                    return_value=Namespace(
                        date="2026-07-23", force=False, dry_run=False
                    ),
                ),
                mock.patch("predict_next_day.cleanup_old_reports"),
                mock.patch(
                    "predict_next_day.job_lock",
                    side_effect=lambda _: nullcontext(),
                ),
                mock.patch(
                    "predict_next_day.fetch_schedule", return_value=schedule
                ),
                mock.patch(
                    "predict_next_day.codex_command",
                    return_value=["codex", "exec"],
                ),
                mock.patch("predict_next_day.run") as run_mock,
                mock.patch(
                    "predict_next_day.validate_schedule_verification",
                    return_value={"no_matches": True},
                ),
                mock.patch(
                    "predict_next_day.finalize_prediction"
                ) as finalize_mock,
            ):
                self.assertEqual(prediction_main(), 0)
            run_mock.assert_called_once_with(["codex", "exec"])
            finalize_mock.assert_not_called()

    def test_filters_tier_and_rolling_1000_window(self) -> None:
        records = [
            {"id": 1, "tier": "s", "start_date": "2026-07-22T02:00:00Z"},
            {"id": 2, "tier": "a", "start_date": "2026-07-22T03:00:00Z"},
            {"id": 3, "tier": "s", "start_date": "2026-07-22T01:59:59Z"},
            {"id": 4, "tier": "s", "start_date": "2026-07-23T01:59:59Z"},
            {"id": 5, "tier": "s", "start_date": "2026-07-23T02:00:00Z"},
        ]
        self.assertEqual(
            [item["id"] for item in extract_taipei_s_matches(records, "2026-07-22")],
            [1, 4],
        )

    def test_forecast_window_uses_configured_prediction_time(self) -> None:
        with mock.patch(
            "predict_next_day.module_schedule_time",
            return_value=datetime_time(hour=6, minute=15),
        ):
            start, end = forecast_window("2026-07-22")
        self.assertEqual(start.isoformat(), "2026-07-22T06:15:00+08:00")
        self.assertEqual(end.isoformat(), "2026-07-23T06:15:00+08:00")

    def test_schedule_fetch_unions_server_and_client_side_tier_results(self) -> None:
        filtered = {
            "results": [
                {
                    "id": 124500,
                    "tier": "s",
                    "start_date": "2026-07-23T11:00:00Z",
                }
            ]
        }
        unfiltered = {
            "results": [
                {
                    "id": 124499,
                    "tier": "s",
                    "start_date": "2026-07-23T09:00:00Z",
                },
                {
                    "id": 124500,
                    "tier": "s",
                    "start_date": "2026-07-23T11:00:00Z",
                },
            ]
        }
        with mock.patch(
            "predict_next_day._fetch_schedule_payload",
            side_effect=[filtered, unfiltered],
        ):
            result = fetch_schedule("2026-07-23")
        self.assertEqual(
            [item["id"] for item in result.matches], [124499, 124500]
        )
        self.assertEqual(result.filtered_match_ids, [124500])
        self.assertEqual(
            result.client_filtered_match_ids, [124499, 124500]
        )

    def test_review_defaults_to_previous_report_date(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            with (
                mock.patch("review_today.STATE_ROOT", state_root),
                mock.patch(
                    "review_today.parse_args",
                    return_value=Namespace(date=None, dry_run=True),
                ),
                mock.patch("review_today.target_date", return_value="2026-07-21") as target_mock,
                mock.patch("review_today.job_lock", side_effect=lambda _: nullcontext()),
            ):
                self.assertEqual(review_main(), 0)
            target_mock.assert_called_once_with(-1)
            self.assertTrue((state_root / "reviews/2026-07-21").is_dir())

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

    def test_schedule_verification_requires_two_source_roles_and_exact_diff(self) -> None:
        precheck = {
            "window_start": "2026-07-23T10:00:00+08:00",
            "window_end": "2026-07-24T10:00:00+08:00",
            "matches": [{"match_id": 124500}],
        }
        verification = {
            "verified_at": "2026-07-23T11:30:00+08:00",
            "timezone": "Asia/Taipei",
            "window_start": precheck["window_start"],
            "window_end": precheck["window_end"],
            "complete": True,
            "no_matches": False,
            "candidate_match_ids": [124500],
            "added_match_ids": [124499],
            "removed_match_ids": [],
            "conflicts": [],
            "sources": [
                {
                    "role": "official",
                    "url": "https://lolesports.com/en-US/leagues/lpl",
                    "checked_at": "2026-07-23T11:25:00+08:00",
                },
                {
                    "role": "independent",
                    "url": "https://liquipedia.net/leagueoflegends/LPL/2026/Split_3",
                    "checked_at": "2026-07-23T11:26:00+08:00",
                },
            ],
            "matches": [
                {
                    "match_id": 124499,
                    "start_time": "2026-07-23T17:00:00+08:00",
                    "tier": "s",
                    "bo_type": 3,
                    "team1": "JD Gaming",
                    "team2": "Anyone's Legend",
                    "tournament": "LPL 2026 Split 3",
                    "source_urls": [
                        "https://lolesports.com/en-US/leagues/lpl",
                        "https://liquipedia.net/leagueoflegends/LPL/2026/Split_3",
                    ],
                },
                {
                    "match_id": 124500,
                    "start_time": "2026-07-23T19:00:00+08:00",
                    "tier": "s",
                    "bo_type": 3,
                    "team1": "Bilibili Gaming",
                    "team2": "ThunderTalk Gaming",
                    "tournament": "LPL 2026 Split 3",
                    "source_urls": [
                        "https://lolesports.com/en-US/leagues/lpl",
                        "https://liquipedia.net/leagueoflegends/LPL/2026/Split_3",
                    ],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            precheck_path = root / "schedule-precheck.json"
            verification_path = root / "schedule-verification.json"
            precheck_path.write_text(json.dumps(precheck), encoding="utf-8")
            verification_path.write_text(json.dumps(verification), encoding="utf-8")
            result = validate_schedule_verification(
                verification_path, precheck_path
            )
            self.assertEqual(
                [item["match_id"] for item in result["matches"]],
                [124499, 124500],
            )

            verification["added_match_ids"] = []
            verification_path.write_text(json.dumps(verification), encoding="utf-8")
            with self.assertRaises(JobError):
                validate_schedule_verification(verification_path, precheck_path)

    def test_incomplete_schedule_verification_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            precheck_path = root / "schedule-precheck.json"
            verification_path = root / "schedule-verification.json"
            precheck_path.write_text(
                json.dumps(
                    {
                        "window_start": "2026-07-23T10:00:00+08:00",
                        "window_end": "2026-07-24T10:00:00+08:00",
                        "matches": [],
                    }
                ),
                encoding="utf-8",
            )
            verification_path.write_text(
                json.dumps(
                    {
                        "verified_at": "2026-07-23T11:30:00+08:00",
                        "timezone": "Asia/Taipei",
                        "window_start": "2026-07-23T10:00:00+08:00",
                        "window_end": "2026-07-24T10:00:00+08:00",
                        "complete": False,
                        "no_matches": True,
                        "candidate_match_ids": [],
                        "added_match_ids": [],
                        "removed_match_ids": [],
                        "conflicts": ["official source lists one unresolved match"],
                        "sources": [],
                        "matches": [],
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(JobError, "incomplete"):
                validate_schedule_verification(verification_path, precheck_path)

    def test_forecasts_must_equal_verified_schedule(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            forecasts_path = Path(directory) / "forecasts.jsonl"
            forecasts_path.write_text(
                json.dumps({"match_id": 124500}) + "\n", encoding="utf-8"
            )
            verification = {
                "matches": [{"match_id": 124499}, {"match_id": 124500}]
            }
            with self.assertRaisesRegex(JobError, "exactly equal"):
                validate_forecast_schedule(forecasts_path, verification)

    def test_settled_match_filter(self) -> None:
        matches = [
            {"id": 1, "status": "finished", "winner_team_id": 10},
            {"id": 2, "status": "upcoming", "winner_team_id": None},
            {"id": 3, "status": "finished", "winner_team_id": 30},
        ]
        self.assertEqual(settled_match_ids(matches, {1, 2}), {1})
        schedule = ScheduleFetch(
            matches=matches,
            filtered_payload={},
            unfiltered_payload={},
            filtered_match_ids=[1],
            client_filtered_match_ids=[1],
        )
        self.assertEqual(settled_match_ids(schedule.matches, {1, 2}), {1})

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
