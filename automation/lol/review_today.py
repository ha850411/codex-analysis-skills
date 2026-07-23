#!/usr/bin/env python3
"""依 JSON 設定的台灣時間檢討前一日 LoL S Tier 預測。"""

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
os.environ["AUTOMATION_MODULE"] = "lol"

from common import (
    REPO_ROOT, STATE_ROOT, JobError, assert_nonempty, codex_command, fail,
    github_env, github_git_env, job_lock, load_jsonl, load_pr_summary, notify_review_by_email, require_executable, review_branch, run,
    target_date, write_status,
)
from predict_next_day import fetch_schedule


def safe_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise JobError(f"Invalid date: {value!r}")
    return value


def is_recent_report(path: Path, max_age_hours: float = 24.0) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    age_seconds = time.time() - path.stat().st_mtime
    return -300 <= age_seconds <= max_age_hours * 3600


def settled_match_ids(matches: list[dict[str, object]], forecast_ids: set[int]) -> set[int]:
    settled: set[int] = set()
    for match in matches:
        match_id = match.get("id")
        status = str(match.get("status", "")).lower()
        if isinstance(match_id, int) and match_id in forecast_ids and (
            isinstance(match.get("winner_team_id"), int)
            or status in {"finished", "completed", "done"}
        ):
            settled.add(match_id)
    return settled


def prompt_for(target: str, prediction_dir: Path, review_dir: Path, worktree: Path, settled: set[int]) -> str:
    return f"""使用 `$lol-analysis` 對 {target}（台灣時間 UTC+8）的 LoL S Tier 預測做正式 postmortem，必要時修正 skill。

原始不可覆寫資料：
- 預測報告：{prediction_dir / 'prediction.md'}
- 預測 JSONL：{prediction_dir / 'forecasts.jsonl'}
- 本次已完賽 match IDs：{sorted(settled)}

必須完整讀取 {worktree / 'lol-analysis/SKILL.md'}、shared 契約、
`lol-analysis/references/postmortem-calibration.md` 與 `$skill-creator` 更新原則。

要求：
1. 只評估上述已完賽 match IDs。用 bo3.gg、官方聯賽來源、可信 box score/VOD 查核版本、名單、逐局勝方、選邊與 BP；保持預測時點和賽後資訊邊界。
2. 將每場完整原預測欄位加上 actual_score、actual_winner、game_winners、result_sources，寫到 {review_dir / 'evaluated-forecasts.jsonl'}；不得覆寫原檔。
3. 將逐場命中、Brier score、log loss、信心校準、BP/版本/名單歸因與 cohort 限制寫入 {review_dir / 'postmortem.md'}。
4. 單場爆冷、單次 BP 或小樣本不得觸發 skill 修改。只有可重複的流程錯誤或足夠批次證據才可修改 {worktree / 'lol-analysis'}。
5. 不得修改 shared、其他 skill、automation、Git 設定或原始預測；不得自行 commit、push 或開 PR，外層程式會處理。
6. 若修改 skill，鐵則是去蕪存菁：只保留能改善分析的指令，刪除或合併無效、重複、已被取代的規則，不得以賽後案例為由無限追加特例。新增規則時應同步取代舊規則，並保持最小差異、驗證受影響內容。既有輸出章節、表格、欄位、順序與 JSON key 不得新增、刪除、改名或重排，也不得修改 `lol-analysis/references/output-template.md`。在 postmortem 記錄證據、修改、測試、回退方式與未解問題。
7. 若證據不足，明確寫「不修改 skill／不建立 PR」與需要累積的 cohort，不為產生 PR 而修改。
8. 另外將 PR 短摘要寫到 {review_dir / 'pr-summary.md'}，只能包含 `## 本次調整` 與 `## 發現的問題` 兩節；各用 1–3 點簡述實際 skill 調整及促成調整的可重複流程問題，總長不得超過 2,000 字。若未修改 skill，仍說明本次未調整及證據不足的問題。
"""


def prepare_worktree(target: str, base: str) -> tuple[Path, str]:
    git = require_executable("git")
    branch = review_branch("LOL", target)
    worktree = STATE_ROOT / "worktrees" / target
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
    return [line[3:].split(" -> ")[-1] for line in (result.stdout or "").splitlines()]


def validate_skill_frontmatter(skill_dir: Path) -> None:
    skill_file = skill_dir / "SKILL.md"
    if not skill_file.is_file():
        raise JobError(f"Missing skill file: {skill_file}")
    text = skill_file.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise JobError("SKILL.md must begin with YAML frontmatter")
    frontmatter = text.split("\n---\n", 1)[0].splitlines()[1:]
    keys = {line.split(":", 1)[0].strip() for line in frontmatter if ":" in line}
    if keys != {"name", "description"}:
        raise JobError(f"Unexpected SKILL.md frontmatter keys: {sorted(keys)}")
    name = next(line for line in frontmatter if line.startswith("name:")).split(":", 1)[1].strip().strip("'\"")
    if name != "lol-analysis":
        raise JobError(f"Invalid skill name: {name!r}")


def validate_changes(worktree: Path) -> None:
    paths = changed_paths(worktree)
    disallowed = [path for path in paths if not path.startswith("lol-analysis/")]
    if disallowed:
        raise JobError(f"Postmortem changed disallowed paths: {', '.join(disallowed)}")
    if "lol-analysis/references/output-template.md" in paths:
        raise JobError("Postmortem must not change the LoL output template")
    codex_home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    validator = codex_home / "skills" / ".system" / "skill-creator" / "scripts" / "quick_validate.py"
    if not validator.is_file():
        raise JobError(f"Cannot find skill validator: {validator}")
    result = run(["python3", str(validator), str(worktree / "lol-analysis")], cwd=worktree, check=False, capture=True)
    if result.returncode != 0:
        output = result.stdout or ""
        if "No module named 'yaml'" not in output:
            raise JobError(f"Official skill validation failed:\n{output.strip()}")
        validate_skill_frontmatter(worktree / "lol-analysis")
    for script in sorted((worktree / "lol-analysis" / "scripts").glob("*.py")):
        compile(script.read_text(encoding="utf-8"), str(script), "exec")


def ensure_github_ready(base: str) -> None:
    run([require_executable("gh", "GH_BIN"), "auth", "status"], capture=True, env=github_env())
    run(["git", "fetch", "origin", base], env=github_git_env())


def create_pr(worktree: Path, branch: str, base: str, target: str, report: Path, summary: Path) -> str:
    pr_summary = load_pr_summary(summary)
    gh = require_executable("gh", "GH_BIN")
    run(["git", "add", "lol-analysis"], cwd=worktree)
    run(["git", "commit", "-m", f"fix(lol): apply {target} postmortem findings"], cwd=worktree)
    run(["git", "push", "--set-upstream", "origin", branch], cwd=worktree, env=github_git_env())
    audit = report.read_text(encoding="utf-8")
    if len(audit) > 52_000:
        audit = audit[:52_000] + "\n\n[完整報告保留於執行主機；PR 內容已截斷。]"
    body = f"Automated LoL S Tier postmortem for {target} (Asia/Taipei).\n\n{pr_summary}\n\n<details><summary>完整檢討證據</summary>\n\n{audit}\n\n</details>"
    result = run([gh, "pr", "create", "--base", base, "--head", branch, "--title", f"LoL postmortem: {target}", "--body", body], cwd=worktree, capture=True, env=github_env())
    return (result.stdout or "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="覆寫要檢討的報告日期（YYYY-MM-DD）")
    parser.add_argument("--dry-run", action="store_true", help="只顯示工作內容，不使用網路或 Codex")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = safe_date(args.date or target_date(-1))
    base = "master"
    prediction_dir = STATE_ROOT / "predictions" / target
    review_dir = STATE_ROOT / "reviews" / target
    report = review_dir / "postmortem.md"
    try:
        with job_lock("review"):
            review_dir.mkdir(parents=True, exist_ok=True)
            if args.dry_run:
                print(prompt_for(target, prediction_dir, review_dir, Path("<isolated-worktree>"), set()))
                return 0
            prediction_report = prediction_dir / "prediction.md"
            forecasts_file = prediction_dir / "forecasts.jsonl"
            if not is_recent_report(prediction_report) or not is_recent_report(forecasts_file):
                write_status(review_dir, "review", "skipped", target_date=target, reason="no prediction report from the last 24 hours")
                print(f"Review skipped; no prediction report from the last 24 hours: {target}")
                return 0
            records = load_jsonl(forecasts_file)
            forecast_ids = {value for record in records if isinstance((value := record.get("match_id")), int)}
            settled = settled_match_ids(fetch_schedule(target), forecast_ids)
            if not settled:
                write_status(review_dir, "review", "skipped", target_date=target, reason="no forecast matches have settled")
                print(f"Review skipped; no forecast LoL S Tier matches have settled: {target}")
                return 0
            write_status(review_dir, "review", "running", target_date=target, settled_match_ids=sorted(settled))
            ensure_github_ready(base)
            worktree, branch = prepare_worktree(target, base)
            run(codex_command(worktree, review_dir / "agent-last-message.md", prompt_for(target, prediction_dir, review_dir, worktree, settled), add_dirs=(review_dir,)))
            assert_nonempty(report)
            evaluated = load_jsonl(review_dir / "evaluated-forecasts.jsonl")
            evaluated_ids = {value for record in evaluated if isinstance((value := record.get("match_id")), int)}
            if evaluated_ids != settled:
                raise JobError(f"Evaluated match IDs {sorted(evaluated_ids)} do not match settled IDs {sorted(settled)}")
            paths = changed_paths(worktree)
            if not paths:
                notify_review_by_email("lol", review_dir, target, pr_created=False)
                write_status(review_dir, "review", "complete", target_date=target, pr_created=False, email_notified=True)
                print(f"Review complete; no skill change justified: {report}")
                return 0
            validate_changes(worktree)
            pr_url = create_pr(worktree, branch, base, target, report, review_dir / "pr-summary.md")
            notify_review_by_email("lol", review_dir, target, pr_created=True, pr_url=pr_url)
            write_status(review_dir, "review", "complete", target_date=target, pr_created=True, pr_url=pr_url, email_notified=True)
            print(f"Review complete; PR created: {pr_url}")
            return 0
    except (JobError, OSError) as exc:
        return fail(review_dir, "review", exc)


if __name__ == "__main__":
    raise SystemExit(main())
