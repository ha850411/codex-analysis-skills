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


def cleanup_old_reports(
    days: int = 30,
    state_dir: Path | None = None,
    dry_run: bool = False,
) -> list[Path]:
    """刪除指定天數（預設 30 天）以前的自動化報告與產物。"""
    if state_dir is None:
        state_dir = REPO_ROOT / ".automation-state"
    state_dir = state_dir.expanduser().resolve()
    if not state_dir.exists():
        return []

    cutoff_date = datetime.now(TAIPEI).date() - timedelta(days=days)
    deleted: list[Path] = []

    dirs_to_check: list[Path] = [state_dir]
    for child in state_dir.iterdir():
        if child.is_dir():
            dirs_to_check.append(child)

    for mod_dir in dirs_to_check:
        for category in ("predictions", "reviews", "worktrees"):
            cat_dir = mod_dir / category
            if not cat_dir.is_dir():
                continue
            for item in list(cat_dir.iterdir()):
                item_date = None
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", item.name):
                    try:
                        item_date = datetime.strptime(item.name, "%Y-%m-%d").date()
                    except ValueError:
                        pass
                if item_date is None:
                    mtime = item.stat().st_mtime
                    item_date = datetime.fromtimestamp(mtime, tz=TAIPEI).date()

                if item_date < cutoff_date:
                    if not dry_run:
                        if item.is_dir():
                            if (item / ".git").exists():
                                git = shutil.which("git")
                                if git:
                                    run([git, "worktree", "remove", "--force", str(item)], check=False)
                            if item.exists():
                                shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink(missing_ok=True)
                    deleted.append(item)

    if deleted and not dry_run:
        git = shutil.which("git")
        if git:
            run([git, "worktree", "prune"], check=False)

    return deleted


def recreate_dated_output_dir(output_dir: Path, expected_parent: Path) -> bool:
    """安全地刪除並重建單一 YYYY-MM-DD 排程輸出目錄。"""
    output_dir = output_dir.expanduser()
    expected_parent = expected_parent.expanduser().resolve()
    if output_dir.parent.resolve() != expected_parent:
        raise JobError(f"Refusing to reset output outside {expected_parent}: {output_dir}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", output_dir.name):
        raise JobError(f"Refusing to reset non-dated output directory: {output_dir}")

    removed = output_dir.exists() or output_dir.is_symlink()
    if output_dir.is_symlink() or output_dir.is_file():
        output_dir.unlink()
    elif output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    return removed


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


def merge_pull_request(pr_url: str, worktree: Path) -> dict[str, str]:
    """合併剛驗證並推送的 PR，且確認 GitHub 回報的最終狀態為 MERGED。"""
    if not pr_url.strip():
        raise JobError("Cannot merge a PR without its URL")
    gh = require_executable("gh", "GH_BIN")
    head = run(
        ["git", "rev-parse", "HEAD"],
        cwd=worktree,
        capture=True,
    ).stdout
    head_sha = (head or "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head_sha):
        raise JobError(f"Cannot determine validated PR head commit: {head_sha!r}")

    run(
        [
            gh,
            "pr",
            "merge",
            pr_url,
            "--merge",
            "--match-head-commit",
            head_sha,
        ],
        cwd=worktree,
        capture=True,
        env=github_env(),
    )
    result = run(
        [
            gh,
            "pr",
            "view",
            pr_url,
            "--json",
            "state,mergedAt,mergeCommit,url",
        ],
        cwd=worktree,
        capture=True,
        env=github_env(),
    )
    try:
        payload = json.loads(result.stdout or "")
    except json.JSONDecodeError as exc:
        raise JobError(f"Cannot parse merged PR status for {pr_url}") from exc
    if not isinstance(payload, dict) or payload.get("state") != "MERGED":
        state = payload.get("state") if isinstance(payload, dict) else None
        raise JobError(f"PR merge was not confirmed for {pr_url}; state={state!r}")
    merge_commit = payload.get("mergeCommit")
    merge_sha = merge_commit.get("oid") if isinstance(merge_commit, dict) else None
    merged_at = payload.get("mergedAt")
    confirmed_url = payload.get("url")
    if not all(isinstance(value, str) and value for value in (merge_sha, merged_at, confirmed_url)):
        raise JobError(f"Merged PR status is incomplete for {pr_url}")
    return {
        "pr_url": confirmed_url,
        "head_commit": head_sha,
        "merge_commit": merge_sha,
        "merged_at": merged_at,
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


def notify_review_by_email(
    module: str,
    review_dir: Path,
    target: str,
    pr_created: bool,
    pr_url: str | None = None,
    pr_merged: bool = False,
    merge_commit: str | None = None,
) -> None:
    """發送復盤結果與 PR 狀態之 Email 通知。"""
    if pr_merged and (not pr_created or not pr_url or not merge_commit):
        raise JobError("Merged PR notification requires PR URL and merge commit")
    receipt = review_dir / "email-notification.json"
    if receipt.is_file():
        try:
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            if (
                isinstance(saved, dict)
                and saved.get("sent") is True
                and saved.get("pr_created") == pr_created
                and saved.get("pr_url") == pr_url
                and saved.get("pr_merged") == pr_merged
                and saved.get("merge_commit") == merge_commit
            ):
                return
        except json.JSONDecodeError:
            pass

    module_upper = module.strip().upper()
    report_file = review_dir / "postmortem.md"
    summary_file = review_dir / "pr-summary.md"

    pr_status_str = "已合併 PR" if pr_merged else ("已建立 PR" if pr_created else "未建立 PR")
    subject = f"{module_upper} 復盤報告已完成（{pr_status_str}）｜{target}"

    body_lines = [
        f"{target}（台灣時間）的 {module_upper} 預測復盤報告已完成。",
        "",
        (
            f"PR 狀態：已合併 - {pr_url}"
            if pr_merged
            else (
                f"PR 狀態：已建立 - {pr_url}"
                if pr_created and pr_url
                else "PR 狀態：未調整 Skill / 未建立 PR"
            )
        ),
        *([f"Merge commit：{merge_commit}"] if pr_merged else []),
        f"本地報告：{report_file}",
        "",
    ]

    if summary_file.is_file():
        body_lines.extend([
            "【復盤摘要】",
            summary_file.read_text(encoding="utf-8").strip(),
            "",
        ])

    body_lines.append(f"此信由 {module_upper} 自動排程復盤寄出。")
    body = "\n".join(body_lines)

    recipients = send_email(subject, body)
    atomic_json(
        receipt,
        {
            "sent": True,
            "sent_at": datetime.now(TAIPEI).isoformat(),
            "recipients": recipients,
            "pr_created": pr_created,
            "pr_url": pr_url,
            "pr_merged": pr_merged,
            "merge_commit": merge_commit,
        },
    )



def assert_nonempty(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise JobError(f"Expected non-empty artifact was not created: {path}")


def load_pr_summary(path: Path, max_chars: int = 4_000) -> str:
    """讀取可直接置於 PR 開頭的短版檢討摘要，並驗證必要章節。"""
    assert_nonempty(path)
    summary = path.read_text(encoding="utf-8").strip()
    if len(summary) > max_chars:
        raise JobError(
            f"PR summary is too long ({len(summary)} characters; max {max_chars}): {path}"
        )
    pattern = re.compile(
        r"^## 本次調整\s*\n(?P<changes>.+?)\n+## 發現的問題\s*\n(?P<issues>.+?)$",
        re.DOTALL,
    )
    match = pattern.fullmatch(summary)
    if not match or not all(match.group(name).strip() for name in ("changes", "issues")):
        raise JobError(
            "PR summary must contain non-empty '## 本次調整' and "
            f"'## 發現的問題' sections in that order: {path}"
        )
    return summary


def load_improvement_plan(path: Path, *, has_changes: bool) -> dict[str, object]:
    """驗證賽後檢討是否形成可稽核的精準度改善閉環。"""
    assert_nonempty(path)
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JobError(f"Invalid improvement plan JSON: {path}: {exc}") from exc
    if not isinstance(plan, dict):
        raise JobError(f"Improvement plan must be a JSON object: {path}")

    required = {
        "objective",
        "change_type",
        "decision",
        "production_change",
        "confidence_or_stake_only",
        "predictive_mechanism",
        "baseline",
        "challenger",
        "validation",
        "evidence",
        "rollback",
    }
    missing = sorted(required.difference(plan))
    if missing:
        raise JobError(f"Improvement plan missing keys {missing}: {path}")

    if plan["objective"] != "out_of_sample_predictive_accuracy":
        raise JobError("Improvement plan objective must be out_of_sample_predictive_accuracy")
    change_types = {
        "data_pipeline",
        "feature_model",
        "distribution",
        "calibration",
        "evaluation_infra",
        "none",
    }
    if plan["change_type"] not in change_types:
        raise JobError(f"Invalid improvement plan change_type: {plan['change_type']!r}")
    if plan["decision"] not in {"merge", "experiment-only", "no-change"}:
        raise JobError(f"Invalid improvement plan decision: {plan['decision']!r}")
    if not isinstance(plan["production_change"], bool):
        raise JobError("Improvement plan production_change must be boolean")
    if plan["confidence_or_stake_only"] is not False:
        raise JobError(
            "Confidence-, stake-, recommendation-, or wording-only changes do not qualify "
            "as predictive-accuracy improvements"
        )
    for key in ("predictive_mechanism", "rollback"):
        if not isinstance(plan[key], str) or not plan[key].strip():
            raise JobError(f"Improvement plan {key} must be a non-empty string")

    for label in ("baseline", "challenger"):
        artifact = plan[label]
        if not isinstance(artifact, dict):
            raise JobError(f"Improvement plan {label} must be an object")
        if set(("model_version", "sample_size", "metrics")).difference(artifact):
            raise JobError(
                f"Improvement plan {label} requires model_version, sample_size, and metrics"
            )
        if not isinstance(artifact["model_version"], str) or not artifact["model_version"].strip():
            raise JobError(f"Improvement plan {label}.model_version must be non-empty")
        if (
            not isinstance(artifact["sample_size"], int)
            or isinstance(artifact["sample_size"], bool)
            or artifact["sample_size"] < 0
        ):
            raise JobError(f"Improvement plan {label}.sample_size must be a non-negative integer")
        if not isinstance(artifact["metrics"], dict):
            raise JobError(f"Improvement plan {label}.metrics must be an object")

    validation = plan["validation"]
    if not isinstance(validation, dict):
        raise JobError("Improvement plan validation must be an object")
    if set(("method", "passed")).difference(validation):
        raise JobError("Improvement plan validation requires method and passed")
    if validation["method"] not in {
        "paired_walk_forward",
        "regression_test",
        "forward_test",
        "none",
    }:
        raise JobError(f"Invalid improvement validation method: {validation['method']!r}")
    if not isinstance(validation["passed"], bool):
        raise JobError("Improvement plan validation.passed must be boolean")

    evidence = plan["evidence"]
    if (
        not isinstance(evidence, list)
        or not evidence
        or any(not isinstance(item, str) or not item.strip() for item in evidence)
    ):
        raise JobError("Improvement plan evidence must be a non-empty array of strings")

    if has_changes:
        if plan["decision"] != "merge" or plan["change_type"] == "none":
            raise JobError("A postmortem PR requires decision=merge and a non-none change_type")
        if validation["method"] == "none" or validation["passed"] is not True:
            raise JobError("A postmortem PR requires a passed, non-none validation method")
        if plan["change_type"] in {"feature_model", "distribution", "calibration"}:
            if validation["method"] != "paired_walk_forward":
                raise JobError(
                    "Feature, distribution, and calibration production changes require "
                    "paired_walk_forward validation"
                )
            for label in ("baseline", "challenger"):
                if plan[label]["sample_size"] <= 0 or not plan[label]["metrics"]:
                    raise JobError(
                        f"{label} requires a positive sample_size and metrics for model changes"
                    )
    elif plan["decision"] == "merge":
        raise JobError("Improvement plan cannot use decision=merge when no skill files changed")

    return plan


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


def sync_evaluated_history(
    history_path: Path,
    source_paths: Sequence[Path],
    *,
    key_fields: Sequence[str],
) -> dict[str, int]:
    """把每日 evaluated forecasts 依不可變預測鍵合併到持久化 JSONL。"""
    if not key_fields:
        raise JobError("Evaluated history requires at least one key field")

    ordered: list[dict[str, object]] = []
    positions: dict[tuple[object, ...], int] = {}

    def record_key(record: dict[str, object], source: Path) -> tuple[object, ...]:
        values: list[object] = []
        for field in key_fields:
            value = record.get(field)
            if value is None or isinstance(value, (dict, list)):
                raise JobError(
                    f"Evaluated history record in {source} has invalid key field "
                    f"{field}={value!r}"
                )
            values.append(value)
        return tuple(values)

    candidates: list[Path] = []
    if history_path.is_file():
        candidates.append(history_path)
    candidates.extend(
        path
        for path in source_paths
        if path.is_file() and path.resolve() != history_path.resolve()
    )

    source_records = 0
    for source in candidates:
        records = load_jsonl(source)
        if source != history_path:
            source_records += len(records)
        for record in records:
            key = record_key(record, source)
            if key in positions:
                ordered[positions[key]] = record
            else:
                positions[key] = len(ordered)
                ordered.append(record)

    if not ordered:
        return {"records": 0, "source_records": source_records}

    history_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = history_path.with_suffix(history_path.suffix + ".tmp")
    temporary.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in ordered
        ),
        encoding="utf-8",
    )
    temporary.replace(history_path)
    return {"records": len(ordered), "source_records": source_records}


def notify_failure_by_email(
    job_dir: Path,
    job: str,
    exc: BaseException,
    module: str | None = None,
) -> None:
    """發送排程執行失敗／遇到問題之 Email 通知。"""
    receipt = job_dir / "email-failure-notification.json"
    if receipt.is_file():
        try:
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            if (
                isinstance(saved, dict)
                and saved.get("sent") is True
                and saved.get("error") == str(exc)
            ):
                return
        except json.JSONDecodeError:
            pass

    mod = (module or MODULE).strip().upper()
    job_label = "預測" if job == "prediction" else ("復盤" if job == "review" else job)
    target = (
        job_dir.name
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", job_dir.name)
        else target_date()
    )

    subject = f"{mod} 自動排程{job_label}遇到問題｜{target}"

    body_lines = [
        f"{target}（台灣時間）的 {mod} 自動排程{job_label}執行遇到問題，未完成分析報告。",
        "",
        "【錯誤訊息】",
        f"{type(exc).__name__}: {exc}",
        "",
        f"輸出目錄：{job_dir}",
        "",
        f"此信由 {mod} 自動排程錯誤通知寄出。",
    ]
    body = "\n".join(body_lines)

    try:
        recipients = send_email(subject, body)
        atomic_json(
            receipt,
            {
                "sent": True,
                "sent_at": datetime.now(TAIPEI).isoformat(),
                "recipients": recipients,
                "error": str(exc),
            },
        )
    except Exception as email_exc:
        print(
            f"Failed to send failure notification email: {email_exc}",
            file=sys.stderr,
        )


def fail(job_dir: Path, job: str, exc: BaseException) -> int:
    write_status(job_dir, job, "failed", error=str(exc))
    print(f"{job}: {exc}", file=sys.stderr)
    notify_failure_by_email(job_dir, job, exc)
    return 1
