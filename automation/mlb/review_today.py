#!/usr/bin/env python3
"""依 JSON 設定的台灣時間檢討前一日 MLB 預測。"""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

AUTOMATION_DIR = Path(__file__).resolve().parents[1]
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))
os.environ["AUTOMATION_MODULE"] = "mlb"

from common import (
    REPO_ROOT,
    STATE_ROOT,
    JobError,
    assert_nonempty,
    codex_command,
    fail,
    github_env,
    github_git_env,
    job_lock,
    load_jsonl,
    load_pr_summary,
    notify_review_by_email,
    require_executable,
    review_branch,
    run,
    target_date,
    write_status,
)


def safe_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise JobError(f"Invalid date: {value!r}")
    return value


def is_recent_report(path: Path, max_age_hours: float = 24.0) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    age_seconds = time.time() - path.stat().st_mtime
    return -300 <= age_seconds <= max_age_hours * 3600


def prompt_for(date: str, prediction_dir: Path, review_dir: Path, worktree: Path) -> str:
    return f"""使用 `$mlb-analysis` 對 {date}（台灣時間 UTC+8）的排程預測做正式 postmortem，必要時修正 skill。

原始不可覆寫資料：
- 預測報告：{prediction_dir / 'prediction.md'}
- 預測 JSONL：{prediction_dir / 'forecasts.jsonl'}

必須完整讀取 {worktree / 'mlb-analysis/SKILL.md'}、shared 契約、
`mlb-analysis/references/postmortem-calibration.md` 與 `$skill-creator` 的更新原則。

要求：
1. 使用 MLB 官方 box score／Gameday 等即時來源查核每場最終結果與實際事件；保留當時可知資訊和賽後資訊的時間邊界。
2. 將含 actual_away_runs、actual_home_runs 的完整紀錄寫到 {review_dir / 'evaluated-forecasts.jsonl'}，保留原預測欄位，不覆寫原檔。
3. 執行 `python mlb-analysis/scripts/evaluate_forecasts.py {review_dir / 'evaluated-forecasts.jsonl'}`，將輸出與逐場歸因整理到 {review_dir / 'postmortem.md'}。若原紀錄未建模，保留原 N/A，不得賽後補造機率；改做 modeled coverage、status 與 missing_data 頻率稽核。
4. 單場冷門、BABIP、單次全壘打等合理變異不得觸發 skill 修改。只有確認可重複的流程錯誤，或批次 paired walk-forward 證據通過升版門檻時，才可修改 {worktree / 'mlb-analysis'}。
5. 不得修改 shared、其他 skill、automation、Git 設定或原始預測。不得自行 commit、push 或建立 PR；外層程式會處理。
6. 若修改 skill，鐵則是去蕪存菁：只保留能改善分析的指令，刪除或合併無效、重複、已被取代的規則，不得以賽後案例為由無限追加特例。新增規則時應同步取代舊規則，並保持最小差異、實際驗證所有受影響腳本。既有輸出章節、表格、欄位、順序與 JSON key 不得新增、刪除、改名或重排，也不得修改 `mlb-analysis/references/output-template.md`。在 postmortem.md 記錄證據、修改、測試、回退方式與仍未解問題。
7. 若證據不足，明確寫「不修改 skill／不建立 PR」以及需要累積的 cohort，不為了產生 PR 而修改。
8. 另外將 PR 短摘要寫到 {review_dir / 'pr-summary.md'}，只能包含 `## 本次調整` 與 `## 發現的問題` 兩節；各用 1–3 點簡述實際 skill 調整及促成調整的可重複流程問題，總長不得超過 2,000 字。若未修改 skill，仍說明本次未調整及證據不足的問題。
"""


def prepare_worktree(date: str, base: str) -> tuple[Path, str]:
    git = require_executable("git")
    branch = review_branch("MLB", date)
    worktree = STATE_ROOT / "worktrees" / date
    if worktree.exists():
        if (worktree / ".git").exists():
            return worktree, branch
        raise JobError(f"Refusing to replace non-worktree path: {worktree}")
    worktree.parent.mkdir(parents=True, exist_ok=True)
    local = run([git, "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], check=False)
    if local.returncode == 0:
        run([git, "worktree", "add", str(worktree), branch])
    else:
        run([git, "worktree", "add", "-b", branch, str(worktree), f"origin/{base}"])
    return worktree, branch


def changed_paths(worktree: Path) -> list[str]:
    result = run(["git", "status", "--porcelain"], cwd=worktree, capture=True)
    paths: list[str] = []
    for line in (result.stdout or "").splitlines():
        path = line[3:].split(" -> ")[-1]
        paths.append(path)
    return paths


def validate_changes(worktree: Path) -> None:
    paths = changed_paths(worktree)
    disallowed = [path for path in paths if not path.startswith("mlb-analysis/")]
    if disallowed:
        raise JobError(f"Postmortem changed disallowed paths: {', '.join(disallowed)}")
    if "mlb-analysis/references/output-template.md" in paths:
        raise JobError("Postmortem must not change the MLB output template")
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    validator = codex_home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    if not validator.is_file():
        raise JobError(f"Cannot find skill validator: {validator}")
    result = run(
        ["python3", str(validator), str(worktree / "mlb-analysis")],
        cwd=worktree,
        check=False,
        capture=True,
    )
    if result.returncode != 0:
        output = result.stdout or ""
        if "No module named 'yaml'" not in output:
            raise JobError(f"Official skill validation failed:\n{output.strip()}")
        validate_skill_frontmatter(worktree / "mlb-analysis")
    for script in sorted((worktree / "mlb-analysis" / "scripts").glob("*.py")):
        source = script.read_text(encoding="utf-8")
        compile(source, str(script), "exec")


def validate_skill_frontmatter(skill_dir: Path) -> None:
    """供 quick_validate 缺少 PyYAML 的主機使用，且不需額外相依套件的備援驗證。"""
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        raise JobError(f"Missing skill file: {skill_file}")
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise JobError("SKILL.md must begin with YAML frontmatter")
    frontmatter = text.split("\n---\n", 1)[0].splitlines()[1:]
    keys = {line.split(":", 1)[0].strip() for line in frontmatter if ":" in line}
    if keys != {"name", "description"}:
        raise JobError(f"SKILL.md frontmatter keys must be name and description, got: {sorted(keys)}")
    name_line = next((line for line in frontmatter if line.startswith("name:")), "")
    name = name_line.split(":", 1)[1].strip().strip("'\"")
    if name != skill_dir.name or not re.fullmatch(r"[a-z0-9-]{1,64}", name):
        raise JobError(f"Invalid skill name: {name!r}")
    description = next((line for line in frontmatter if line.startswith("description:")), "")
    if not description.split(":", 1)[1].strip():
        raise JobError("Skill description cannot be empty")


def ensure_github_ready(base: str) -> None:
    run(
        [require_executable("gh", "GH_BIN"), "auth", "status"],
        capture=True,
        env=github_env(),
    )
    run(["git", "fetch", "origin", base], env=github_git_env())


def create_pr(worktree: Path, branch: str, base: str, date: str, report: Path, summary: Path) -> str:
    pr_summary = load_pr_summary(summary)
    gh = require_executable("gh", "GH_BIN")
    run(["git", "add", "mlb-analysis"], cwd=worktree)
    run(["git", "commit", "-m", f"fix(mlb): apply {date} postmortem findings"], cwd=worktree)
    run(
        ["git", "push", "--set-upstream", "origin", branch],
        cwd=worktree,
        env=github_git_env(),
    )
    audit = report.read_text(encoding="utf-8")
    if len(audit) > 52_000:
        audit = audit[:52_000] + "\n\n[完整報告保留於執行主機；PR 內容因長度限制截斷。]"
    body = (
        f"Automated MLB postmortem for {date} (Asia/Taipei).\n\n"
        f"{pr_summary}\n\n"
        "<details><summary>完整檢討證據</summary>\n\n"
        f"{audit}\n\n</details>"
    )
    result = run(
        [gh, "pr", "create", "--base", base, "--head", branch, "--title", f"MLB postmortem: {date}", "--body", body],
        cwd=worktree,
        capture=True,
        env=github_env(),
    )
    return (result.stdout or "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="覆寫要檢討的報告日期（YYYY-MM-DD）")
    parser.add_argument("--dry-run", action="store_true", help="只顯示工作內容，不使用網路或 Codex")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    date = safe_date(args.date or target_date(-1))
    base = "master"
    prediction_dir = STATE_ROOT / "predictions" / date
    review_dir = STATE_ROOT / "reviews" / date
    report = review_dir / "postmortem.md"
    worktree: Path | None = None

    try:
        with job_lock("review"):
            review_dir.mkdir(parents=True, exist_ok=True)
            if args.dry_run:
                print(prompt_for(date, prediction_dir, review_dir, Path("<isolated-worktree>")))
                return 0
            prediction_report = prediction_dir / "prediction.md"
            forecasts_file = prediction_dir / "forecasts.jsonl"
            if not is_recent_report(prediction_report) or not is_recent_report(forecasts_file):
                write_status(
                    review_dir,
                    "review",
                    "skipped",
                    target_date=date,
                    reason="no prediction report from the last 24 hours",
                )
                print(f"Review skipped; no prediction report from the last 24 hours: {date}")
                return 0
            records = load_jsonl(forecasts_file)
            if all(record.get("status") == "no-games" for record in records):
                write_status(review_dir, "review", "skipped", target_date=date, reason="no MLB games")
                print(f"Review skipped; schedule had no MLB games: {date}")
                return 0
            write_status(review_dir, "review", "running", target_date=date)
            ensure_github_ready(base)
            worktree, branch = prepare_worktree(date, base)
            prompt = prompt_for(date, prediction_dir, review_dir, worktree)
            run(
                codex_command(
                    worktree,
                    review_dir / "agent-last-message.md",
                    prompt,
                    add_dirs=(review_dir,),
                )
            )
            assert_nonempty(report)
            assert_nonempty(review_dir / "evaluated-forecasts.jsonl")
            run(
                ["python3", "mlb-analysis/scripts/evaluate_forecasts.py", str(review_dir / "evaluated-forecasts.jsonl")],
                cwd=worktree,
            )
            paths = changed_paths(worktree)
            if not paths:
                notify_review_by_email("mlb", review_dir, date, pr_created=False)
                write_status(review_dir, "review", "complete", target_date=date, pr_created=False, email_notified=True)
                print(f"Review complete; no skill change justified: {report}")
                return 0
            validate_changes(worktree)
            pr_url = create_pr(worktree, branch, base, date, report, review_dir / "pr-summary.md")
            notify_review_by_email("mlb", review_dir, date, pr_created=True, pr_url=pr_url)
            write_status(review_dir, "review", "complete", target_date=date, pr_created=True, pr_url=pr_url, email_notified=True)
            print(f"Review complete; PR created: {pr_url}")
            return 0
    except (JobError, OSError) as exc:
        return fail(review_dir, "review", exc)


if __name__ == "__main__":
    raise SystemExit(main())
