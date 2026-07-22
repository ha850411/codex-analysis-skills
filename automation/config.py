"""共用自動化模組設定與排程時間驗證。"""

from __future__ import annotations

import json
import re
from datetime import time
from pathlib import Path


AUTOMATION_DIR = Path(__file__).resolve().parent
CONFIG_FILE = AUTOMATION_DIR / "modules.json"
KNOWN_MODULES = {"mlb", "lol"}
REASONING_EFFORTS = {
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
}
SCHEDULE_PHASES = ("prediction", "review")


class ConfigError(RuntimeError):
    pass


def parse_schedule_time(value: object, field: str) -> time:
    """解析嚴格的 24 小時制 HH:MM，拒絕 cron 表達式與寬鬆格式。"""
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[01]\d|2[0-3]):[0-5]\d", value
    ):
        raise ConfigError(f"{field} must use 24-hour HH:MM format")
    hour, minute = (int(part) for part in value.split(":"))
    return time(hour=hour, minute=minute)


def load_config(path: Path | None = None) -> dict[str, dict[str, object]]:
    config_path = path or CONFIG_FILE
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing module config: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid module config JSON: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("timezone") != "Asia/Taipei":
        raise ConfigError("modules.json timezone must be Asia/Taipei")
    modules = payload.get("modules")
    if not isinstance(modules, dict):
        raise ConfigError("modules.json must contain a modules object")
    unknown = sorted(set(modules) - KNOWN_MODULES)
    if unknown:
        raise ConfigError(f"Unknown automation modules: {', '.join(unknown)}")

    normalized: dict[str, dict[str, object]] = {}
    for name, settings in modules.items():
        if not isinstance(settings, dict) or not isinstance(settings.get("enabled"), bool):
            raise ConfigError(f"modules.{name}.enabled must be true or false")
        model = settings.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ConfigError(f"modules.{name}.model must be a non-empty string")
        reasoning_effort = settings.get("reasoning_effort")
        if reasoning_effort not in REASONING_EFFORTS:
            allowed = ", ".join(sorted(REASONING_EFFORTS))
            raise ConfigError(f"modules.{name}.reasoning_effort must be one of: {allowed}")

        schedule = settings.get("schedule")
        if not isinstance(schedule, dict):
            raise ConfigError(f"modules.{name}.schedule must be an object")
        extra_phases = sorted(set(schedule) - set(SCHEDULE_PHASES))
        if extra_phases:
            raise ConfigError(
                f"modules.{name}.schedule has unknown phases: {', '.join(extra_phases)}"
            )
        parsed_times = {
            phase: parse_schedule_time(
                schedule.get(phase), f"modules.{name}.schedule.{phase}"
            )
            for phase in SCHEDULE_PHASES
        }
        if parsed_times["review"] >= parsed_times["prediction"]:
            raise ConfigError(
                f"modules.{name}.schedule.review must be earlier than prediction"
            )

        if name == "lol" and settings.get("enabled"):
            if (
                settings.get("schedule_source")
                != "https://bo3.gg/lol/matches/current?tiers=s"
                or settings.get("tier") != "s"
            ):
                raise ConfigError(
                    "Enabled LoL automation must use the approved bo3.gg S-tier source"
                )
        normalized[name] = settings
    return normalized


def module_schedule_time(
    module: str, phase: str, path: Path | None = None
) -> time:
    if module not in KNOWN_MODULES:
        raise ConfigError(f"Unknown automation module: {module}")
    if phase not in SCHEDULE_PHASES:
        raise ConfigError(f"Unknown schedule phase: {phase}")
    settings = load_config(path).get(module)
    if settings is None:
        raise ConfigError(f"Missing automation module config: {module}")
    schedule = settings["schedule"]
    if not isinstance(schedule, dict):
        raise AssertionError("schedule was validated by load_config")
    return parse_schedule_time(
        schedule[phase], f"modules.{module}.schedule.{phase}"
    )
