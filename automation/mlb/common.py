#!/usr/bin/env python3
"""Shared, deterministic plumbing for the MLB scheduled jobs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Sequence
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
REPO_ROOT = Path(__file__).resolve().parents[2]


def load_repo_env() -> None:
    """Load only automation-approved keys from .env without overriding the process."""
    allowed = {
        "GITHUB_PAT",
        "MLB_AUTOMATION_STATE_DIR",
        "MLB_CODEX_MODEL",
        "MLB_GIT_BASE_BRANCH",
        "CODEX_BIN",
        "GH_BIN",
    }
    env_file = REPO_ROOT / ".env"
    if not env_file.is_file():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in allowed or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


load_repo_env()

STATE_ROOT = Path(
    os.environ.get("MLB_AUTOMATION_STATE_DIR", REPO_ROOT / ".automation-state" / "mlb")
).expanduser().resolve()


class JobError(RuntimeError):
    """Expected operational failure with a user-actionable message."""


def target_date(offset_days: int = 0) -> str:
    return (datetime.now(TAIPEI).date() + timedelta(days=offset_days)).isoformat()


def require_executable(name: str, env_name: str | None = None) -> str:
    configured = os.environ.get(env_name, "") if env_name else ""
    executable = configured or shutil.which(name)
    if not executable:
        hint = f" or set {env_name}" if env_name else ""
        raise JobError(f"Cannot find {name!r} on PATH{hint}.")
    return executable


def run(
    argv: Sequence[str],
    *,
    cwd: Path = REPO_ROOT,
    check: bool = True,
    capture: bool = False,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    result = subprocess.run(
        list(argv),
        cwd=cwd,
        env=merged_env,
        check=False,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if check and result.returncode != 0:
        detail = f"\n{result.stdout.strip()}" if capture and result.stdout else ""
        raise JobError(f"Command failed ({result.returncode}): {' '.join(argv)}{detail}")
    return result


def atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


@contextmanager
def job_lock(name: str) -> Iterator[None]:
    lock = STATE_ROOT / "locks" / f"{name}.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        lock.mkdir()
    except FileExistsError as exc:
        raise JobError(f"Job is already running: {name} ({lock})") from exc
    try:
        yield
    finally:
        try:
            lock.rmdir()
        except FileNotFoundError:
            pass


def write_status(job_dir: Path, job: str, status: str, **extra: object) -> None:
    atomic_json(
        job_dir / "status.json",
        {
            "job": job,
            "status": status,
            "updated_at": datetime.now(TAIPEI).isoformat(),
            **extra,
        },
    )


def codex_command(
    workdir: Path,
    last_message: Path,
    prompt: str,
    *,
    add_dirs: Sequence[Path] = (),
) -> list[str]:
    codex = require_executable("codex", "CODEX_BIN")
    model = os.environ.get("MLB_CODEX_MODEL", "").strip()
    command = [
        codex,
        "exec",
        "--search",
        "--ephemeral",
        "--color",
        "never",
        "--sandbox",
        "workspace-write",
        "--ask-for-approval",
        "never",
        "--cd",
        str(workdir),
        "--output-last-message",
        str(last_message),
    ]
    for directory in add_dirs:
        command.extend(["--add-dir", str(directory)])
    if model:
        command.extend(["--model", model])
    command.append(prompt)
    return command


def github_env() -> dict[str, str]:
    """Return ephemeral GitHub auth variables without persisting the PAT."""
    token = os.environ.get("GITHUB_PAT", "").strip()
    if not token:
        return {}
    return {"GH_TOKEN": token}


def github_git_env() -> dict[str, str]:
    """Authenticate GitHub HTTPS via an in-memory Git config entry."""
    token = os.environ.get("GITHUB_PAT", "").strip()
    if not token:
        return {}
    import base64

    credential = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return {
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"Authorization: Basic {credential}",
    }


def assert_nonempty(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise JobError(f"Expected non-empty artifact was not created: {path}")


def load_jsonl(path: Path) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw.strip():
            continue
        try:
            value = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise JobError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise JobError(f"JSONL record must be an object at {path}:{line_number}")
        records.append(value)
    if not records:
        raise JobError(f"No records found in {path}")
    return records


def fail(job_dir: Path, job: str, exc: BaseException) -> int:
    write_status(job_dir, job, "failed", error=str(exc))
    print(f"{job}: {exc}", file=sys.stderr)
    return 1
