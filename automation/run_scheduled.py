#!/usr/bin/env python3
"""對所有已啟用且在允許清單內的模組執行指定排程階段。"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


AUTOMATION_DIR = Path(__file__).resolve().parent
REPO_ROOT = AUTOMATION_DIR.parent
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))

from common import cleanup_old_reports
from config import ConfigError, KNOWN_MODULES, load_config

PHASE_SCRIPTS = {
    "prediction": "predict_next_day.py",
    "review": "review_today.py",
}
def module_environment(settings: dict[str, object]) -> dict[str, str]:
    """將單一模組的模型設定轉成子程序專用環境變數。"""
    env = os.environ.copy()
    env["AUTOMATION_CODEX_MODEL"] = str(settings["model"]).strip()
    env["AUTOMATION_REASONING_EFFORT"] = str(settings["reasoning_effort"])
    return env


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=sorted(PHASE_SCRIPTS))
    parser.add_argument("--module", choices=sorted(KNOWN_MODULES), help="只執行指定模組")
    args, extra = parser.parse_known_args()
    args.extra = extra
    return args


def main() -> int:
    args = parse_args()
    if args.phase == "prediction":
        is_dry_run = "--dry-run" in args.extra
        cleaned = cleanup_old_reports(days=30, dry_run=is_dry_run)
        if cleaned:
            status = "Would clean" if is_dry_run else "Cleaned"
            print(f"[cleanup] {status} {len(cleaned)} report item(s) older than 30 days.", flush=True)

    try:
        modules = load_config()
    except ConfigError as exc:
        print(f"automation config: {exc}", file=sys.stderr)
        return 2
    failures: list[str] = []
    enabled = [
        name
        for name in sorted(modules)
        if modules[name]["enabled"] and (args.module is None or name == args.module)
    ]
    if not enabled:
        scope = f"module {args.module}" if args.module else "automation modules"
        print(f"No enabled {scope} for {args.phase}.")
        return 0
    for name in enabled:
        script = AUTOMATION_DIR / name / PHASE_SCRIPTS[args.phase]
        if not script.is_file():
            print(f"[{name}] missing job script: {script}", file=sys.stderr)
            failures.append(name)
            continue
        print(f"[{name}] starting {args.phase}", flush=True)
        result = subprocess.run(
            [sys.executable, str(script), *args.extra],
            cwd=REPO_ROOT,
            check=False,
            env=module_environment(modules[name]),
        )
        if result.returncode:
            failures.append(name)
            print(f"[{name}] {args.phase} failed ({result.returncode})", file=sys.stderr)
        else:
            print(f"[{name}] {args.phase} finished", flush=True)
    if failures:
        print(f"Failed modules: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
