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
MLB_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "mlb-analysis" / "scripts"
if str(MLB_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(MLB_SCRIPTS_DIR))
os.environ["AUTOMATION_MODULE"] = "mlb"

from common import JobError, atomic_json, codex_command, load_jsonl, review_branch, send_email
from build_public_baseline import (
    _confidence,
    fit_public_environment,
    parse_pitcher_projection,
    phase_run_means,
)
from evaluate_forecasts import _read_records, availability_audit
from predict_next_day import (
    extract_taipei_games,
    finalize_prediction,
    forecast_window,
    main as prediction_main,
    validate_forecasts,
    validate_against_public_baseline,
    validate_notion_summary,
)
from review_today import (
    is_recent_report,
    main as review_main,
    prompt_for,
    safe_date,
    validate_skill_frontmatter,
)


class AutomationTests(unittest.TestCase):
    @staticmethod
    def _confidence_inputs() -> dict[str, object]:
        profile = {
            "games": 120.0,
            "offense_runs_per_game": 4.5,
            "defense_runs_per_game": 4.5,
        }
        starter = {
            "source": "same_season_ra9_shrunk",
            "games_started": 20,
            "innings": 120.0,
            "projected_ra9": 4.2,
            "projected_innings": 5.5,
        }
        return {
            "game": {
                "gameDate": "2026-07-23T00:00:00+00:00",
                "gameNumber": 1,
            },
            "environment": {
                "completed_game_count": 1500,
                "away_runs_per_game": 4.4,
                "home_runs_per_game": 4.6,
            },
            "away_profile": profile,
            "home_profile": profile,
            "away_probable": {"id": 1},
            "home_probable": {"id": 2},
            "away_starter": starter,
            "home_starter": starter,
            "away_means": {"f5": 2.5, "late": 1.9},
            "home_means": {"f5": 2.6, "late": 2.0},
            "predicted_at": "2026-07-22T22:00:00+00:00",
        }

    def test_public_baseline_confidence_is_uncapped_and_weighted(self) -> None:
        confidence, components, diagnostics = _confidence(**self._confidence_inputs())
        weighted_score = (
            0.25 * components["dataCompleteness"]
            + 0.20 * components["freshness"]
            + 0.25 * components["lineupCertainty"]
            + 0.20 * components["regimeRelevance"]
            + 0.10 * components["modelStability"]
        )
        expected = int(weighted_score + 0.5) / 100.0
        self.assertEqual(confidence, expected)
        self.assertGreater(confidence, 0.55)
        self.assertIsNone(diagnostics["hard_cap"])

    def test_public_baseline_confidence_varies_by_game_evidence(self) -> None:
        strong_inputs = self._confidence_inputs()
        strong, _, _ = _confidence(**strong_inputs)

        weak_inputs = self._confidence_inputs()
        weak_inputs["game"] = {
            "gameDate": "2026-07-23T08:00:00+00:00",
            "gameNumber": 2,
        }
        weak_inputs["home_probable"] = None
        weak_inputs["home_starter"] = {
            "source": "league_fallback_tbd_starter",
            "games_started": 0,
            "innings": 0.0,
            "projected_ra9": 4.5,
            "projected_innings": 4.5,
        }
        weak, weak_components, weak_diagnostics = _confidence(**weak_inputs)

        self.assertLess(weak, strong)
        self.assertLess(weak_components["freshness"], 90)
        self.assertLess(weak_components["lineupCertainty"], 30)
        self.assertTrue(weak_diagnostics["second_doubleheader_game"])

    def test_public_baseline_fits_only_auditable_numeric_inputs(self) -> None:
        games = []
        for index in range(120):
            away_score = index % 8
            home_score = (index * 3 + 1) % 9
            if away_score == home_score:
                home_score = (home_score + 1) % 10
            games.append({
                "teams": {
                    "away": {"team": {"id": 1}, "score": away_score},
                    "home": {"team": {"id": 2}, "score": home_score},
                }
            })
        environment = fit_public_environment(games)
        self.assertEqual(environment["completed_game_count"], 120)
        self.assertIn("1", environment["team_profiles"])
        self.assertGreater(environment["away_runs_per_game"], 0)
        self.assertGreaterEqual(environment["dispersion"]["away_team_sigma"], 0.05)

        fallback = parse_pitcher_projection({}, environment["team_runs_per_game"])
        means = phase_run_means(
            environment["team_profiles"]["1"],
            environment["team_profiles"]["2"],
            fallback,
            environment["away_runs_per_game"],
            environment["team_runs_per_game"],
        )
        self.assertGreater(means["f5"], 0)
        self.assertGreater(means["late"], 0)

    def test_existing_prediction_is_regenerated_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            output_dir = state_root / "predictions/2026-07-22"
            output_dir.mkdir(parents=True)
            (output_dir / "prediction.md").write_text("old", encoding="utf-8")
            (output_dir / "forecasts.jsonl").write_text("old\n", encoding="utf-8")
            (output_dir / "notion-publish.json").write_text("old", encoding="utf-8")

            with (
                mock.patch("predict_next_day.STATE_ROOT", state_root),
                mock.patch(
                    "predict_next_day.parse_args",
                    return_value=Namespace(date="2026-07-22", force=False, dry_run=False),
                ),
                mock.patch("predict_next_day.cleanup_old_reports"),
                mock.patch("predict_next_day.job_lock", side_effect=lambda _: nullcontext()),
                mock.patch("predict_next_day.fetch_schedule", return_value=[{"gamePk": 1}]),
                mock.patch("predict_next_day.build_public_baseline") as baseline_mock,
                mock.patch("predict_next_day.codex_command", return_value=["codex", "exec"]),
                mock.patch("predict_next_day.run") as run_mock,
                mock.patch("predict_next_day.finalize_prediction", return_value="https://notion.example/report"),
            ):
                self.assertEqual(prediction_main(), 0)

            run_mock.assert_called_once_with(["codex", "exec"])
            baseline_mock.assert_called_once_with(output_dir)
            self.assertFalse((output_dir / "prediction.md").exists())
            self.assertFalse((output_dir / "forecasts.jsonl").exists())
            self.assertFalse((output_dir / "notion-publish.json").exists())
            self.assertTrue((output_dir / "schedule-precheck.json").exists())

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

    def test_all_unmodeled_forecasts_are_valid_degraded_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecasts.jsonl"
            path.write_text(json.dumps({
                "game_id": 1,
                "predicted_at": "2026-07-21T21:00:00+08:00",
                "first_pitch": "2026-07-22T07:00:00+08:00",
                "snapshot": "pre-lineup",
                "model_version": "N/A-no-production-model",
                "away_team": "Away",
                "home_team": "Home",
                "status": "insufficient-model-data",
                "missing_data": ["production model"],
                "sources": ["MLB"],
            }) + "\n", encoding="utf-8")
            result = validate_forecasts(path)
            self.assertEqual(result["report_quality"], "degraded")
            self.assertEqual(result["modeled_count"], 0)
            self.assertEqual(result["unmodeled_count"], 1)

    def test_unmodeled_forecast_requires_auditable_fields(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecasts.jsonl"
            path.write_text(json.dumps({
                "game_id": 1,
                "status": "insufficient-model-data",
                "missing_data": ["production model"],
            }) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(JobError, "unmodeled record 1 missing"):
                validate_forecasts(path)

    def test_no_games_cannot_be_mixed_with_forecasts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecasts.jsonl"
            records = [
                {"status": "no-games", "date": "2026-12-25", "sources": ["MLB"]},
                {"game_id": 1, "status": "insufficient-model-data", "missing_data": ["model"]},
            ]
            path.write_text(
                "".join(json.dumps(record) + "\n" for record in records),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(JobError, "cannot mix no-games"):
                validate_forecasts(path)

    def test_modeled_forecast_requires_production_model_and_numeric_means(self) -> None:
        base = {
            "game_id": 1, "predicted_at": "2026-07-21T21:00:00+08:00",
            "first_pitch": "2026-07-22T07:00:00+08:00", "snapshot": "pre-lineup",
            "model_version": "mlb-production-v1", "away_team": "Away", "home_team": "Home",
            "away_f5_runs_mean": 2.1, "home_f5_runs_mean": 2.3,
            "away_late_runs_mean": 1.8, "home_late_runs_mean": 1.9,
            "away_runs_mean": 3.9, "home_runs_mean": 4.2,
            "home_win_prob": 0.54, "model_confidence": 0.62, "sources": ["MLB"],
            "f5_away_win_prob": 0.40, "f5_tie_prob": 0.20,
            "f5_home_win_prob": 0.40, "away_runs_p10": 1, "away_runs_p90": 7,
            "home_runs_p10": 1, "home_runs_p90": 8,
            "total_runs_p10": 4, "total_runs_p90": 14,
            "status": "modeled", "model_tier": "production",
            "validation_status": "walk-forward-validated", "recommendation_eligible": True,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "forecasts.jsonl"
            path.write_text(json.dumps(base) + "\n", encoding="utf-8")
            validate_forecasts(path)

            invalid_version = {**base, "model_version": "N/A-no-model"}
            path.write_text(json.dumps(invalid_version) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(JobError, "numeric model"):
                validate_forecasts(path)

            invalid_mean = {**base, "away_runs_mean": None}
            path.write_text(json.dumps(invalid_mean) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(JobError, "away_runs_mean"):
                validate_forecasts(path)

    def test_finalize_refuses_all_na_report(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            (output_dir / "prediction.md").write_text("# degraded report\n", encoding="utf-8")
            (output_dir / "forecasts.jsonl").write_text(json.dumps({
                "game_id": 1,
                "predicted_at": "2026-07-21T21:00:00+08:00",
                "first_pitch": "2026-07-22T07:00:00+08:00",
                "snapshot": "pre-lineup",
                "model_version": "N/A-no-production-model",
                "away_team": "Away",
                "home_team": "Home",
                "status": "insufficient-model-data",
                "missing_data": ["production model"],
                "sources": ["MLB"],
            }) + "\n", encoding="utf-8")
            (output_dir / "probability-checks.json").write_text(
                json.dumps({"checks": []}) + "\n", encoding="utf-8"
            )
            (output_dir / "notion-summary.json").write_text(json.dumps({
                "title": "MLB 2026-07-22", "sport": "MLB", "module": "mlb-analysis",
                "event": "MLB", "startTime": "2026-07-22T07:00:00+08:00",
                "prediction": "N/A", "winner": "N/A", "winProbability": "N/A",
                "recommendation": "觀望", "stake": "0u", "confidence": "N/A",
                "risk": "production model missing", "sourceStatus": "schedule checked",
                "analysisType": "daily-summary", "tags": ["MLB", "degraded"],
            }) + "\n", encoding="utf-8")
            (output_dir / "public-baseline.json").write_text(
                json.dumps({"forecasts": []}), encoding="utf-8"
            )
            with self.assertRaisesRegex(JobError, "public-baseline.json has no forecasts"):
                finalize_prediction(output_dir, "2026-07-22")

    def test_baseline_forecast_is_numeric_but_not_recommendation_eligible(self) -> None:
        record = {
            "game_id": "1", "predicted_at": "2026-07-21T21:00:00+08:00",
            "first_pitch": "2026-07-22T07:00:00+08:00", "snapshot": "pre-lineup",
            "model_version": "mlb-public-baseline-v1.1.0", "away_team": "Away",
            "home_team": "Home", "away_f5_runs_mean": 2.1, "home_f5_runs_mean": 2.3,
            "away_late_runs_mean": 1.8, "home_late_runs_mean": 1.9,
            "away_runs_mean": 3.9, "home_runs_mean": 4.2, "home_win_prob": 0.54,
            "f5_away_win_prob": 0.40, "f5_tie_prob": 0.20,
            "f5_home_win_prob": 0.40, "away_runs_p10": 1, "away_runs_p90": 7,
            "home_runs_p10": 1, "home_runs_p90": 8,
            "total_runs_p10": 4, "total_runs_p90": 14,
            "model_confidence": 0.55,
            "confidence_components": {
                "dataCompleteness": 55, "freshness": 55, "lineupCertainty": 55,
                "regimeRelevance": 55, "modelStability": 55,
            },
            "confidence_diagnostics": {"hard_cap": None},
            "status": "baseline",
            "model_tier": "public-data-baseline", "validation_status": "uncalibrated",
            "recommendation_eligible": False, "sources": ["MLB Stats API"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            forecasts = root / "forecasts.jsonl"
            baseline = root / "public-baseline.json"
            forecasts.write_text(json.dumps(record) + "\n", encoding="utf-8")
            baseline.write_text(json.dumps({"forecasts": [record]}), encoding="utf-8")
            result = validate_forecasts(forecasts)
            self.assertEqual(result["report_quality"], "baseline")
            self.assertEqual(result["baseline_count"], 1)
            validate_against_public_baseline(forecasts, baseline)

            changed = {**record, "home_win_prob": 0.60}
            forecasts.write_text(json.dumps(changed) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(JobError, "changed locked baseline fields"):
                validate_against_public_baseline(forecasts, baseline)

    def test_evaluator_audits_unmodeled_records_without_scoring_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "evaluated.jsonl"
            path.write_text(json.dumps({
                "game_id": 822787,
                "predicted_at": "2026-07-21T21:00:00+08:00",
                "first_pitch": "2026-07-22T07:07:00+08:00",
                "snapshot": "pre-lineup",
                "model_version": "N/A-no-production-model",
                "status": "insufficient-model-input",
                "missing_data": ["production model", "weather"],
                "actual_away_runs": 3,
                "actual_home_runs": 5,
            }) + "\n", encoding="utf-8")

            records = _read_records(str(path))
            audit = availability_audit(records)
            self.assertFalse(records[0]["_scorable"])
            self.assertEqual(records[0]["game_id"], "822787")
            self.assertEqual(audit["model_coverage"], 0.0)
            self.assertEqual(audit["unscored_records"], 1)
            self.assertEqual(audit["missing_data_counts"]["production model"], 1)

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

    def test_schedule_is_filtered_by_rolling_2100_window(self) -> None:
        payload = {
            "dates": [{"games": [
                {"gamePk": 1, "gameDate": "2026-07-22T12:59:59Z"},
                {"gamePk": 2, "gameDate": "2026-07-22T13:00:00Z"},
                {"gamePk": 3, "gameDate": "2026-07-23T12:59:59Z"},
                {"gamePk": 4, "gameDate": "2026-07-23T13:00:00Z"},
            ]}]
        }
        games = extract_taipei_games([payload], "2026-07-22")
        self.assertEqual([game["gamePk"] for game in games], [2, 3])

    def test_forecast_window_uses_configured_prediction_time(self) -> None:
        with mock.patch(
            "predict_next_day.module_schedule_time",
            return_value=datetime_time(hour=18, minute=45),
        ):
            start, end = forecast_window("2026-07-22")
        self.assertEqual(start.isoformat(), "2026-07-22T18:45:00+08:00")
        self.assertEqual(end.isoformat(), "2026-07-23T18:45:00+08:00")

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
        )
        self.assertIn("improvement-plan.json", prompt)
        self.assertIn("baseline/challenger paired walk-forward", prompt)
        self.assertIn("跨日 evaluated history", prompt)
        self.assertIn("不可只看單日", prompt)
        self.assertIn("不得作為 skill 修正或 PR 的唯一內容", prompt)
        self.assertNotIn("保持最小差異", prompt)

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
