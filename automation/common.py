#!/usr/bin/env python3
"""賽事分析自動排程模組共用的確定性基礎功能。"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterator, Sequence
from zoneinfo import ZoneInfo


TAIPEI = ZoneInfo("Asia/Taipei")
REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE = os.environ.get("AUTOMATION_MODULE", "mlb").strip().lower()
if MODULE not in {"mlb", "lol"}:
    raise RuntimeError(f"Unsupported AUTOMATION_MODULE: {MODULE!r}")


def load_repo_env() -> None:
    """只從 .env 載入自動排程允許的鍵，且不覆寫現有程序環境。"""
    allowed = {
        "GITHUB_PAT",
        "MLB_AUTOMATION_STATE_DIR",
        "LOL_AUTOMATION_STATE_DIR",
        "AUTOMATION_NOTIFICATION_EMAIL",
        "CODEX_BIN",
        "GH_BIN",
        "SMTP_FROM",
        "SMTP_HOST",
        "SMTP_PASSWORD",
        "SMTP_PORT",
        "SMTP_SECURITY",
        "SMTP_USERNAME",
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
    os.environ.get(
        f"{MODULE.upper()}_AUTOMATION_STATE_DIR",
        REPO_ROOT / ".automation-state" / MODULE,
    )
).expanduser().resolve()


class JobError(RuntimeError):
    """可預期且能提供使用者處理方式的作業錯誤。"""


def target_date(offset_days: int = 0) -> str:
    return (datetime.now(TAIPEI).date() + timedelta(days=offset_days)).isoformat()


def review_branch(module: str, date: str) -> str:
    """依模組與賽事日期產生固定的賽後檢討 feature 分支名稱。"""
    normalized_module = module.strip().upper()
    if normalized_module not in {"MLB", "LOL"}:
        raise JobError(f"Unsupported review branch module: {module!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        raise JobError(f"Invalid review branch date: {date!r}")
    return f"feature/{normalized_module}-{date[5:7]}{date[8:10]}"


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
    model = os.environ.get("AUTOMATION_CODEX_MODEL", "").strip()
    reasoning_effort = os.environ.get("AUTOMATION_REASONING_EFFORT", "").strip()
    command = [
        codex,
        # These are root CLI options and must appear before the `exec` subcommand.
        "--search",
        "--ask-for-approval",
        "never",
        "exec",
        "--ephemeral",
        "--color",
        "never",
        "--sandbox",
        "workspace-write",
        "--cd",
        str(workdir),
        "--output-last-message",
        str(last_message),
    ]
    for directory in add_dirs:
        command.extend(["--add-dir", str(directory)])
    if model:
        command.extend(["--model", model])
    if reasoning_effort:
        command.extend(["--config", f'model_reasoning_effort="{reasoning_effort}"'])
    command.append(prompt)
    return command


def github_env() -> dict[str, str]:
    """回傳暫時性的 GitHub 驗證環境變數，不將 PAT 寫入磁碟。"""
    token = os.environ.get("GITHUB_PAT", "").strip()
    if not token:
        return {}
    return {"GH_TOKEN": token}


def github_git_env() -> dict[str, str]:
    """透過記憶體中的 Git 設定完成 GitHub HTTPS 驗證。"""
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


def send_email(subject: str, body: str) -> list[str]:
    """透過已設定的 SMTP 寄送 UTF-8 純文字通知。"""
    import smtplib
    import ssl
    from email.message import EmailMessage

    host = os.environ.get("SMTP_HOST", "").strip()
    recipient_setting = os.environ.get("AUTOMATION_NOTIFICATION_EMAIL", "").strip()
    recipients = [
        address.strip()
        for address in recipient_setting.split(",")
        if address.strip()
    ]
    username = os.environ.get("SMTP_USERNAME", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "")
    sender = os.environ.get("SMTP_FROM", "").strip() or username
    security = os.environ.get("SMTP_SECURITY", "starttls").strip().lower()
    try:
        port = int(os.environ.get("SMTP_PORT", "465" if security == "ssl" else "587"))
    except ValueError as exc:
        raise JobError("SMTP_PORT must be an integer") from exc

    missing = []
    if not host:
        missing.append("SMTP_HOST")
    if not recipients:
        missing.append("AUTOMATION_NOTIFICATION_EMAIL")
    if not sender:
        missing.append("SMTP_FROM or SMTP_USERNAME")
    if missing:
        raise JobError(f"Missing email settings: {', '.join(missing)}")
    if security not in {"starttls", "ssl", "none"}:
        raise JobError("SMTP_SECURITY must be starttls, ssl, or none")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    context = ssl.create_default_context()
    if security == "ssl":
        smtp_connection = smtplib.SMTP_SSL(host, port, timeout=30, context=context)
    else:
        smtp_connection = smtplib.SMTP(host, port, timeout=30)
    with smtp_connection as smtp:
        if security == "starttls":
            smtp.starttls(context=context)
        if username:
            if not password:
                raise JobError("SMTP_PASSWORD is required when SMTP_USERNAME is set")
            smtp.login(username, password)
        smtp.send_message(message)
    return recipients


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
