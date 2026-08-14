from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.parse
from argparse import Namespace
from contextlib import nullcontext
from datetime import time as datetime_time
from pathlib import Path
from unittest import mock

AUTOMATION_DIR = Path(__file__).resolve().parents[1]
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))
os.environ["AUTOMATION_MODULE"] = "lol"
os.environ["AUTOMATION_EMAIL_TRANSPORT"] = "mock"

from common import REPO_ROOT, JobError
from predict_next_day import (
    ScheduleFetch,
    _fetch_schedule_payload,
    extract_riot_schedule,
    extract_taipei_s_matches,
    fetch_schedule,
    forecast_window,
    main as prediction_main,
    prompt_for as prediction_prompt_for,
    validate_forecast_schedule,
    validate_forecasts,
    validate_market_collection,
    validate_probability_checks,
    validate_schedule_verification,
)
from review_today import is_recent_report, main as review_main, prompt_for, settled_match_ids


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
                mock.patch(
                    "predict_next_day.fetch_riot_schedule",
                    return_value={"matches": []},
                ),
                mock.patch("predict_next_day.codex_command", return_value=["codex", "exec"]),
                mock.patch("predict_next_day.run") as run_mock,
                mock.patch(
                    "predict_next_day.validate_schedule_verification",
                    return_value={"no_matches": False},
                ),
                mock.patch("predict_next_day.finalize_prediction", return_value="https://notion.example/report"),
            ):
                self.assertEqual(prediction_main(), 0)

            run_mock.assert_called_once_with(["codex", "exec"], timeout=None)
            self.assertFalse((output_dir / "prediction.md").exists())
            self.assertFalse((output_dir / "forecasts.jsonl").exists())
            self.assertFalse((output_dir / "email-notification.json").exists())
            self.assertTrue((output_dir / "schedule-precheck.json").exists())
            self.assertTrue((output_dir / "bo3-filtered-response.json").exists())
            self.assertTrue((output_dir / "bo3-unfiltered-response.json").exists())
            self.assertTrue((output_dir / "riot-schedule-precheck.json").exists())

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
                    "predict_next_day.fetch_riot_schedule",
                    return_value={"matches": []},
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
                    "predict_next_day.fetch_riot_schedule",
                    return_value={"matches": []},
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
            run_mock.assert_called_once_with(["codex", "exec"], timeout=None)
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

    def test_riot_embedded_event_time_prevents_next_day_pairing_mixup(self) -> None:
        """Regression: 2026-07-30 agent assigned Jul 31 LCP teams to Jul 30."""
        html = (
            '{"__typename":"EventMatch","id":"1","blockName":"Swiss",'
            '"startTime":"2026-07-30T09:00:00Z","state":"unstarted","type":"match",'
            '"league":{"__typename":"League","id":"lcp","name":"LCP"},'
            '"tournament":{"__typename":"Tournament","id":"t","name":"Split 3 2026"},'
            '"matchTeams":[{"__typename":"MatchTeam","id":"a",'
            '"name":"Fukuoka SoftBank HAWKS gaming"},{"__typename":"MatchTeam",'
            '"id":"b","name":"DetonatioN FocusMe"}]}'
            '{"__typename":"EventMatch","id":"2","blockName":"Swiss",'
            '"startTime":"2026-07-31T09:00:00Z","state":"unstarted","type":"match",'
            '"league":{"__typename":"League","id":"lcp","name":"LCP"},'
            '"tournament":{"__typename":"Tournament","id":"t","name":"Split 3 2026"},'
            '"matchTeams":[{"__typename":"MatchTeam","id":"c",'
            '"name":"Team Secret Whales"},{"__typename":"MatchTeam","id":"d",'
            '"name":"MVK Esports"}]}'
        )
        result = extract_riot_schedule(html, "2026-07-30")
        self.assertEqual(result["match_count"], 1)
        self.assertEqual(result["matches"][0]["team1"], "Fukuoka SoftBank HAWKS gaming")
        self.assertEqual(result["matches"][0]["team2"], "DetonatioN FocusMe")
        self.assertEqual(
            result["matches"][0]["start_time"],
            "2026-07-30T17:00:00+08:00",
        )

    def test_prediction_prompt_uses_riot_event_json_not_relative_date_labels(self) -> None:
        prompt = prediction_prompt_for(
            "2026-07-30", Path("/tmp/lol-predictions/2026-07-30")
        )
        self.assertIn("riot-schedule-precheck.json", prompt)
        self.assertIn("start_time_utc", prompt)
        self.assertIn("Today／Tomorrow", prompt)

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

    def test_schedule_api_receives_utc_window_boundaries(self) -> None:
        payload = io.BytesIO(
            json.dumps({"results": [], "total": {"count": 0}}).encode("utf-8")
        )
        with mock.patch(
            "predict_next_day.urllib.request.urlopen",
            return_value=payload,
        ) as urlopen_mock:
            _fetch_schedule_payload("2026-07-25", tier_filtered=True)

        request = urlopen_mock.call_args.args[0]
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.full_url).query)
        self.assertEqual(
            query["filter[matches.start_date][gt]"],
            ["2026-07-25T01:59:59Z"],
        )
        self.assertEqual(
            query["filter[matches.start_date][lt]"],
            ["2026-07-26T02:00:00Z"],
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

    def test_review_prompt_requires_accuracy_improvement_evidence(self) -> None:
        prompt = prompt_for(
            "2026-07-21",
            Path("/prediction"),
            Path("/review"),
            Path("/worktree"),
            {1},
        )
        self.assertIn("improvement-plan.json", prompt)
        self.assertIn("baseline/challenger paired walk-forward", prompt)
        self.assertIn("跨日 evaluated history", prompt)
        self.assertIn("不可只看單日", prompt)
        self.assertIn("不得作為 skill 修正或 PR 的唯一內容", prompt)
        self.assertIn("factor-registry.json", prompt)
        self.assertIn("無增量效益", prompt)
        self.assertIn("retired 因子之後不再抓取、判斷或報告", prompt)
        self.assertNotIn("保持最小差異", prompt)

    def test_prediction_prompt_resolves_stale_wiki_with_current_official_source(
        self,
    ) -> None:
        prompt = prediction_prompt_for(
            "2026-07-25",
            Path("/predictions/2026-07-25"),
        )
        self.assertIn("Riot／LoL Esports 全域或多賽區官方賽程", prompt)
        self.assertIn("不得要求每一個第三方 wiki 都一致", prompt)
        self.assertIn("已確認過期的 wiki 單獨", prompt)
        self.assertIn("只有來源不一致且依上述優先序仍無法消解", prompt)
        self.assertIn('scope="global-s-tier"', prompt)
        self.assertIn("聯賽專頁只能貢獻該聯賽子集合", prompt)
        self.assertIn("bo3_match_id=null", prompt)
        self.assertIn("bo3.gg 不得出現在 coverage_sources", prompt)
        self.assertIn("原始回應只保存在候選 precheck artifacts", prompt)
        self.assertIn("decision-slate.json", prompt)
        self.assertIn("任何非 bet_now 的 table_cell 都不得只寫 0u", prompt)
        self.assertIn("當前價達標、證據閘門通過且沒有硬阻擋", prompt)
        self.assertIn("若全日 0u，必須保存 all_zero_audit", prompt)

    def test_exact_score_contract(self) -> None:
        record = {
            "match_key": "bo3:1", "bo3_match_id": 1,
            "predicted_at": "now", "start_time": "later",
            "snapshot": "pre-match", "model_version": "v1", "team1": "A",
            "team2": "B", "tournament": "LPL", "tier": "s", "bo_type": 3,
            "exact_score_probabilities": {"2-0": 0.25, "2-1": 0.30, "1-2": 0.25, "0-2": 0.20},
            "team1_win_prob": 0.55, "team2_win_prob": 0.45,
            "team1_at_least_one_prob": 0.80, "team2_at_least_one_prob": 0.75,
            "both_at_least_one_prob": 0.55,
            "model_confidence": 0.70,
            "confidence_components": {
                "data_completeness": 0.70, "freshness": 0.90,
                "lineup_certainty": 0.75, "regime_relevance": 0.74,
                "model_stability": 0.62, "raw_weighted": 0.75,
                "final_after_non_compensatory_cap": 0.70,
            },
            "fragility_triggers": ["critical_vod_incomplete"],
            "sources": ["bo3.gg"],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecasts.jsonl"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            validate_forecasts(path)
            record["team1_win_prob"] = 0.60
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            with self.assertRaises(JobError):
                validate_forecasts(path)

    def test_confidence_check_uses_non_compensatory_final_value(self) -> None:
        record = {
            "match_key": "bo3:1", "bo3_match_id": 1,
            "predicted_at": "now", "start_time": "later",
            "snapshot": "pre-lineup/pre-draft", "model_version": "v1",
            "team1": "A", "team2": "B", "tournament": "LPL",
            "tier": "s", "bo_type": 3,
            "exact_score_probabilities": {
                "2-0": 0.25, "2-1": 0.30, "1-2": 0.25, "0-2": 0.20,
            },
            "team1_win_prob": 0.55, "team2_win_prob": 0.45,
            "team1_at_least_one_prob": 0.80,
            "team2_at_least_one_prob": 0.75,
            "both_at_least_one_prob": 0.55,
            "model_confidence": 0.70,
            "confidence_components": {
                "data_completeness": 0.70, "freshness": 0.90,
                "lineup_certainty": 0.75, "regime_relevance": 0.74,
                "model_stability": 0.62, "raw_weighted": 0.75,
                "final_after_non_compensatory_cap": 0.70,
            },
            "fragility_triggers": ["critical_vod_incomplete"],
            "sources": ["https://lolesports.com"],
        }
        raw_only_check = {
            "checks": [{
                "type": "weighted_confidence", "name": "A-B confidence",
                "match_key": "bo3:1", "value": 75,
                "components": {
                    "dataCompleteness": 70, "freshness": 90,
                    "lineupCertainty": 75, "regimeRelevance": 74,
                    "modelStability": 62,
                },
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            forecasts = root / "forecasts.jsonl"
            checks = root / "probability-checks.json"
            forecasts.write_text(json.dumps(record) + "\n", encoding="utf-8")
            checks.write_text(json.dumps(raw_only_check), encoding="utf-8")
            validate_forecasts(forecasts)
            with self.assertRaises(JobError):
                validate_probability_checks(checks, forecasts)

            fixed = raw_only_check["checks"][0]
            fixed.update({
                "value": 70,
                "rawWeighted": 75,
                "applyNonCompensatoryCap": True,
                "fragilityTriggers": ["critical_vod_incomplete"],
            })
            checks.write_text(json.dumps(raw_only_check), encoding="utf-8")
            validate_probability_checks(checks, forecasts)

    def test_shared_validator_applies_lol_confidence_cap(self) -> None:
        payload = {
            "checks": [{
                "type": "weighted_confidence", "name": "LoL capped",
                "value": 70,
                "components": {
                    "dataCompleteness": 70, "freshness": 90,
                    "lineupCertainty": 75, "regimeRelevance": 74,
                    "modelStability": 62,
                },
            }],
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "checks.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            command = [
                "node", str(REPO_ROOT / "shared/validate_probabilities.mjs"),
                str(path),
            ]
            old_result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(old_result.returncode, 1)

            payload["checks"][0].update({
                "rawWeighted": 75,
                "applyNonCompensatoryCap": True,
                "fragilityTriggers": ["critical_vod_incomplete"],
            })
            path.write_text(json.dumps(payload), encoding="utf-8")
            fixed_result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(fixed_result.returncode, 0, fixed_result.stderr)

    def test_schedule_verification_requires_two_source_roles_and_exact_diff(self) -> None:
        candidate_key = "bo3:124500"
        added_key = "lol:lck:20260723T1700+0800:t1:kt-rolster"
        all_keys = [added_key, candidate_key]
        precheck = {
            "window_start": "2026-07-23T10:00:00+08:00",
            "window_end": "2026-07-24T10:00:00+08:00",
            "matches": [{"match_key": candidate_key, "match_id": 124500}],
        }
        verification = {
            "verified_at": "2026-07-23T11:30:00+08:00",
            "timezone": "Asia/Taipei",
            "window_start": precheck["window_start"],
            "window_end": precheck["window_end"],
            "complete": True,
            "no_matches": False,
            "candidate_match_keys": [candidate_key],
            "added_match_keys": [added_key],
            "removed_match_keys": [],
            "conflicts": [],
            "coverage_sources": [
                {
                    "role": "official",
                    "scope": "global-s-tier",
                    "url": "https://lolesports.com/en-US/leagues/lck%2Clpl%2Clcp%2Clec%2Clcs",
                    "checked_at": "2026-07-23T11:25:00+08:00",
                    "match_keys": all_keys,
                },
                {
                    "role": "independent",
                    "scope": "global-s-tier",
                    "url": "https://liquipedia.net/leagueoflegends/Liquipedia%3AMatches",
                    "checked_at": "2026-07-23T11:26:00+08:00",
                    "match_keys": all_keys,
                },
            ],
            "sources": [
                {
                    "role": "official",
                    "url": "https://lolesports.com/en-US/leagues/lck%2Clpl%2Clcp%2Clec%2Clcs",
                    "checked_at": "2026-07-23T11:25:00+08:00",
                },
                {
                    "role": "independent",
                    "url": "https://liquipedia.net/leagueoflegends/Liquipedia%3AMatches",
                    "checked_at": "2026-07-23T11:26:00+08:00",
                },
            ],
            "matches": [
                {
                    "match_key": added_key,
                    "bo3_match_id": None,
                    "start_time": "2026-07-23T17:00:00+08:00",
                    "tier": "s",
                    "bo_type": 3,
                    "team1": "T1",
                    "team2": "KT Rolster",
                    "tournament": "LCK 2026",
                    "source_urls": [
                        "https://lolesports.com/en-US/leagues/lck%2Clpl%2Clcp%2Clec%2Clcs",
                        "https://liquipedia.net/leagueoflegends/Liquipedia%3AMatches",
                    ],
                },
                {
                    "match_key": candidate_key,
                    "bo3_match_id": 124500,
                    "start_time": "2026-07-23T19:00:00+08:00",
                    "tier": "s",
                    "bo_type": 3,
                    "team1": "Bilibili Gaming",
                    "team2": "ThunderTalk Gaming",
                    "tournament": "LPL 2026 Split 3",
                    "source_urls": [
                        "https://lolesports.com/en-US/leagues/lck%2Clpl%2Clcp%2Clec%2Clcs",
                        "https://liquipedia.net/leagueoflegends/Liquipedia%3AMatches",
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
                [item["match_key"] for item in result["matches"]],
                [added_key, candidate_key],
            )

            lck_url = "https://liquipedia.net/leagueoflegends/LCK/2026"
            lpl_url = "https://liquipedia.net/leagueoflegends/LPL/2026/Split_3"
            split_coverage = json.loads(json.dumps(verification))
            split_coverage["coverage_sources"] = [
                verification["coverage_sources"][0],
                {
                    "role": "independent",
                    "scope": "competition-s-tier",
                    "competition": "LCK",
                    "url": lck_url,
                    "checked_at": "2026-07-23T11:26:00+08:00",
                    "match_keys": [added_key],
                },
                {
                    "role": "independent",
                    "scope": "competition-s-tier",
                    "competition": "LPL",
                    "url": lpl_url,
                    "checked_at": "2026-07-23T11:26:00+08:00",
                    "match_keys": [candidate_key],
                },
            ]
            split_coverage["sources"].extend(
                [
                    {
                        "role": "independent",
                        "url": lck_url,
                        "checked_at": "2026-07-23T11:26:00+08:00",
                    },
                    {
                        "role": "independent",
                        "url": lpl_url,
                        "checked_at": "2026-07-23T11:26:00+08:00",
                    },
                ]
            )
            split_coverage["matches"][0]["source_urls"] = [
                split_coverage["sources"][0]["url"],
                lck_url,
            ]
            split_coverage["matches"][1]["source_urls"] = [
                split_coverage["sources"][0]["url"],
                lpl_url,
            ]
            verification_path.write_text(
                json.dumps(split_coverage), encoding="utf-8"
            )
            validate_schedule_verification(verification_path, precheck_path)

            bo3_as_independent = json.loads(json.dumps(verification))
            bo3_url = "https://bo3.gg/lol/matches/current?tiers=s"
            bo3_as_independent["coverage_sources"][1]["url"] = bo3_url
            bo3_as_independent["sources"][1]["url"] = bo3_url
            for match in bo3_as_independent["matches"]:
                match["source_urls"][1] = bo3_url
            verification_path.write_text(
                json.dumps(bo3_as_independent), encoding="utf-8"
            )
            with self.assertRaisesRegex(JobError, "bo3.gg is candidate-only"):
                validate_schedule_verification(verification_path, precheck_path)

            verification["added_match_keys"] = []
            verification_path.write_text(json.dumps(verification), encoding="utf-8")
            with self.assertRaises(JobError):
                validate_schedule_verification(verification_path, precheck_path)

    def test_lpl_only_pages_cannot_prove_global_schedule_completeness(self) -> None:
        """Regression: 2026-07-29 bo3.gg omitted two LCK S-tier matches."""
        precheck = {
            "window_start": "2026-07-29T10:00:00+08:00",
            "window_end": "2026-07-30T10:00:00+08:00",
            "matches": [{"match_key": "bo3:124508", "match_id": 124508}],
        }
        verification = {
            "verified_at": "2026-07-29T10:02:49+08:00",
            "timezone": "Asia/Taipei",
            "window_start": precheck["window_start"],
            "window_end": precheck["window_end"],
            "complete": True,
            "no_matches": False,
            "candidate_match_keys": ["bo3:124508"],
            "added_match_keys": [],
            "removed_match_keys": [],
            "conflicts": [],
            "coverage_sources": [
                {
                    "role": "official",
                    "scope": "global-s-tier",
                    "url": "https://lolesports.com/en-US/leagues/lpl",
                    "checked_at": "2026-07-29T10:02:49+08:00",
                    "match_keys": ["bo3:124508"],
                },
                {
                    "role": "independent",
                    "scope": "global-s-tier",
                    "url": "https://liquipedia.net/leagueoflegends/LPL/2026/Split_3",
                    "checked_at": "2026-07-29T10:02:49+08:00",
                    "match_keys": ["bo3:124508"],
                },
            ],
            "sources": [
                {
                    "role": "official",
                    "url": "https://lolesports.com/en-US/leagues/lpl",
                    "checked_at": "2026-07-29T10:02:49+08:00",
                },
                {
                    "role": "independent",
                    "url": "https://liquipedia.net/leagueoflegends/LPL/2026/Split_3",
                    "checked_at": "2026-07-29T10:02:49+08:00",
                },
            ],
            "matches": [
                {
                    "match_key": "bo3:124508",
                    "bo3_match_id": 124508,
                    "start_time": "2026-07-29T17:00:00+08:00",
                    "tier": "s",
                    "bo_type": 3,
                    "team1": "Top Esports",
                    "team2": "Anyone's Legend",
                    "tournament": "LPL 2026 Split 3",
                    "source_urls": [
                        "https://lolesports.com/en-US/leagues/lpl",
                        "https://liquipedia.net/leagueoflegends/LPL/2026/Split_3",
                    ],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            precheck_path = root / "schedule-precheck.json"
            verification_path = root / "schedule-verification.json"
            precheck_path.write_text(json.dumps(precheck), encoding="utf-8")
            verification_path.write_text(json.dumps(verification), encoding="utf-8")
            with self.assertRaisesRegex(JobError, "invalid scope"):
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
                        "candidate_match_keys": [],
                        "added_match_keys": [],
                        "removed_match_keys": [],
                        "conflicts": ["official source lists one unresolved match"],
                        "coverage_sources": [],
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
                json.dumps({"match_key": "bo3:124500"}) + "\n", encoding="utf-8"
            )
            verification = {
                "matches": [
                    {"match_key": "bo3:124499"},
                    {"match_key": "bo3:124500"},
                ]
            }
            with self.assertRaisesRegex(JobError, "exactly equal"):
                validate_forecast_schedule(forecasts_path, verification)

    def test_market_collection_requires_one_auditable_artifact_per_match(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            success = {
                "status": "success",
                "collection": {
                    "event_resolution": "conservative_team_alias",
                    "event_lookup_attempts": 1,
                    "odds_request_attempts": 1,
                },
                "source": {"provider": "Odds-API.io"},
                "event": {"provider_event_id": 7185943806},
            }
            failed = {
                "status": "failed",
                "attempted_at": "2026-07-29T14:30:00+08:00",
                "error": {"kind": "market_unavailable"},
            }
            (root / "odds-drx-ns.json").write_text(
                json.dumps(success), encoding="utf-8"
            )
            (root / "odds-tes-al.error.json").write_text(
                json.dumps(failed), encoding="utf-8"
            )
            manifest_path = root / "market-collection.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "generated_at": "2026-07-29T14:31:00+08:00",
                        "attempts": [
                            {
                                "match_key": "bo3:1",
                                "status": "success",
                                "artifact": "odds-drx-ns.json",
                            },
                            {
                                "match_key": "bo3:2",
                                "status": "failed",
                                "artifact": "odds-tes-al.error.json",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            verification = {
                "matches": [{"match_key": "bo3:1"}, {"match_key": "bo3:2"}]
            }
            result = validate_market_collection(
                manifest_path, root, verification
            )
            self.assertEqual(len(result["attempts"]), 2)

    def test_market_collection_rejects_missing_match_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "odds.json").write_text(
                json.dumps(
                    {
                        "status": "success",
                        "collection": {},
                        "source": {"provider": "Odds-API.io"},
                        "event": {"provider_event_id": 1},
                    }
                ),
                encoding="utf-8",
            )
            manifest_path = root / "market-collection.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "generated_at": "2026-07-29T14:31:00+08:00",
                        "attempts": [
                            {
                                "match_key": "bo3:1",
                                "status": "success",
                                "artifact": "odds.json",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            verification = {
                "matches": [{"match_key": "bo3:1"}, {"match_key": "bo3:2"}]
            }
            with self.assertRaisesRegex(JobError, "exactly equal"):
                validate_market_collection(manifest_path, root, verification)

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
