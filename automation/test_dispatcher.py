from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from automation.run_scheduled import ConfigError, load_config, module_environment, parse_args


class DispatcherConfigTests(unittest.TestCase):
    def write(self, payload: object) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "modules.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_enabled_flags_are_loaded(self) -> None:
        path = self.write({"timezone": "Asia/Taipei", "modules": {"mlb": {"enabled": False, "model": "gpt-5.6-sol", "reasoning_effort": "high"}, "lol": {"enabled": True, "model": "gpt-5.6-sol", "reasoning_effort": "high", "schedule_source": "https://bo3.gg/lol/matches/current?tiers=s", "tier": "s"}}})
        self.assertFalse(load_config(path)["mlb"]["enabled"])

    def test_unknown_module_is_rejected(self) -> None:
        path = self.write({"timezone": "Asia/Taipei", "modules": {"shell": {"enabled": True, "model": "gpt-5.6-sol", "reasoning_effort": "high"}}})
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_lol_source_cannot_be_widened(self) -> None:
        path = self.write({"timezone": "Asia/Taipei", "modules": {"lol": {"enabled": True, "model": "gpt-5.6-sol", "reasoning_effort": "high", "schedule_source": "any", "tier": "all"}}})
        with self.assertRaises(ConfigError):
            load_config(path)

    def test_model_and_reasoning_effort_are_required(self) -> None:
        missing_model = self.write({"timezone": "Asia/Taipei", "modules": {"mlb": {"enabled": True, "reasoning_effort": "high"}}})
        with self.assertRaises(ConfigError):
            load_config(missing_model)
        invalid_effort = self.write({"timezone": "Asia/Taipei", "modules": {"mlb": {"enabled": True, "model": "gpt-5.6-sol", "reasoning_effort": "extreme"}}})
        with self.assertRaises(ConfigError):
            load_config(invalid_effort)

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
