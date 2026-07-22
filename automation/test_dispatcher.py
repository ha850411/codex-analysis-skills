from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from automation.render_crontab import render
from automation.run_scheduled import ConfigError, load_config, module_environment, parse_args
from config import module_schedule_time


class DispatcherConfigTests(unittest.TestCase):
    @staticmethod
    def module(
        enabled: bool = True,
        prediction: str = "21:00",
        review: str = "20:30",
    ) -> dict[str, object]:
        return {
            "enabled": enabled,
            "model": "gpt-5.6-sol",
            "reasoning_effort": "high",
            "schedule": {"prediction": prediction, "review": review},
        }

    def write(self, payload: object) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "modules.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_enabled_flags_are_loaded(self) -> None:
        mlb = self.module(enabled=False)
        lol = {
            **self.module(prediction="09:00", review="08:30"),
            "schedule_source": "https://bo3.gg/lol/matches/current?tiers=s",
            "tier": "s",
        }
        path = self.write(
            {"timezone": "Asia/Taipei", "modules": {"mlb": mlb, "lol": lol}}
        )
        self.assertFalse(load_config(path)["mlb"]["enabled"])

    def test_unknown_module_is_rejected(self) -> None:
        path = self.write(
            {"timezone": "Asia/Taipei", "modules": {"shell": self.module()}}
        )
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_lol_source_cannot_be_widened(self) -> None:
        path = self.write(
            {
                "timezone": "Asia/Taipei",
                "modules": {
                    "lol": {
                        **self.module(prediction="09:00", review="08:30"),
                        "schedule_source": "any",
                        "tier": "all",
                    }
                },
            }
        )
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_model_and_reasoning_effort_are_required(self) -> None:
        missing_model_settings = self.module()
        del missing_model_settings["model"]
        missing_model = self.write(
            {"timezone": "Asia/Taipei", "modules": {"mlb": missing_model_settings}}
        )
        with self.assertRaises(ConfigError):
            load_config(missing_model)
        invalid_settings = self.module()
        invalid_settings["reasoning_effort"] = "extreme"
        invalid_effort = self.write(
            {"timezone": "Asia/Taipei", "modules": {"mlb": invalid_settings}}
        )
        with self.assertRaises(ConfigError):
            load_config(invalid_effort)

    def test_schedule_requires_strict_hhmm_and_review_before_prediction(self) -> None:
        invalid_format = self.write(
            {
                "timezone": "Asia/Taipei",
                "modules": {"mlb": self.module(prediction="9:00", review="08:30")},
            }
        )
        with self.assertRaisesRegex(ConfigError, "HH:MM"):
            load_config(invalid_format)

        invalid_order = self.write(
            {
                "timezone": "Asia/Taipei",
                "modules": {"mlb": self.module(prediction="09:00", review="09:30")},
            }
        )
        with self.assertRaisesRegex(ConfigError, "earlier than prediction"):
            load_config(invalid_order)

    def test_module_schedule_time_is_loaded_from_json(self) -> None:
        path = self.write(
            {
                "timezone": "Asia/Taipei",
                "modules": {"mlb": self.module(prediction="18:45", review="18:15")},
            }
        )
        scheduled_at = module_schedule_time("mlb", "prediction", path)
        self.assertEqual((scheduled_at.hour, scheduled_at.minute), (18, 45))

    def test_crontab_is_rendered_from_json_schedule(self) -> None:
        path = self.write(
            {
                "timezone": "Asia/Taipei",
                "modules": {"mlb": self.module(prediction="18:45", review="18:15")},
            }
        )
        with mock.patch("config.CONFIG_FILE", path):
            crontab = render(
                Path("/repo root"),
                Path("/usr/bin/python3"),
                Path("/usr/local/bin/codex"),
                Path("/repo root/.automation-state/logs"),
            )
        self.assertIn("45 18 * * *", crontab)
        self.assertIn("15 18 * * *", crontab)
        self.assertIn("prediction --module mlb", crontab)
        self.assertIn("review --module mlb", crontab)

    def test_module_environment_passes_codex_settings(self) -> None:
        env = module_environment({"model": "gpt-5.6-sol", "reasoning_effort": "high"})
        self.assertEqual(env["AUTOMATION_CODEX_MODEL"], "gpt-5.6-sol")
        self.assertEqual(env["AUTOMATION_REASONING_EFFORT"], "high")

    def test_module_filter_is_parsed_without_consuming_job_arguments(self) -> None:
        with mock.patch.object(
            sys,
            "argv",
            ["run_scheduled.py", "prediction", "--module", "lol", "--dry-run"],
        ):
            args = parse_args()
        self.assertEqual(args.module, "lol")
        self.assertEqual(args.extra, ["--dry-run"])


if __name__ == "__main__":
    unittest.main()
