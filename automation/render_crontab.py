#!/usr/bin/env python3
"""依 modules.json 產生受管 crontab 內容。"""

from __future__ import annotations

import argparse
import shlex
import sys
from datetime import time
from pathlib import Path

AUTOMATION_DIR = Path(__file__).resolve().parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from config import ConfigError, load_config, parse_schedule_time


def cron_prefix(value: time) -> str:
    return f"{value.minute} {value.hour} * * *"


def scheduled_command(
    module: str,
    phase: str,
    schedule_value: object,
    repo_root: Path,
    python_bin: Path,
    codex_bin: Path,
    log_dir: Path,
) -> str:
    scheduled_at = parse_schedule_time(
        schedule_value, f"modules.{module}.schedule.{phase}"
    )
    command = (
        f"cd {shlex.quote(str(repo_root))} && "
        f"CODEX_BIN={shlex.quote(str(codex_bin))} "
        f"{shlex.quote(str(python_bin))} automation/run_scheduled.py "
        f"{phase} --module {module} >> "
        f"{shlex.quote(str(log_dir / f'{module}-{phase}.log'))} 2>&1"
    )
    return f"{cron_prefix(scheduled_at)} {command}"


def render(
    repo_root: Path, python_bin: Path, codex_bin: Path, log_dir: Path
) -> str:
    modules = load_config()
    lines = [
        "SHELL=/bin/zsh",
        "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin",
        "TZ=Asia/Taipei",
    ]
    for module in sorted(modules):
        schedule = modules[module]["schedule"]
        if not isinstance(schedule, dict):
            raise AssertionError("schedule was validated by load_config")
        for phase in ("prediction", "review"):
            lines.append(
                scheduled_command(
                    module,
                    phase,
                    schedule[phase],
                    repo_root,
                    python_bin,
                    codex_bin,
                    log_dir,
                )
            )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--python-bin", type=Path, required=True)
    parser.add_argument("--codex-bin", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        print(render(args.repo_root, args.python_bin, args.codex_bin, args.log_dir))
    except ConfigError as exc:
        print(f"automation config: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
