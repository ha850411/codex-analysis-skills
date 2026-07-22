#!/usr/bin/env python3
"""依 JSON 設定的台灣時間預測未來 24 小時 LoL S Tier 賽事。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as date_type, datetime, timedelta
from pathlib import Path

AUTOMATION_DIR = Path(__file__).resolve().parents[1]
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))
os.environ["AUTOMATION_MODULE"] = "lol"

from common import (
    REPO_ROOT, STATE_ROOT, TAIPEI, JobError, atomic_json, assert_nonempty,
    cleanup_old_reports, codex_command, fail, job_lock, load_jsonl,
    recreate_dated_output_dir, run, send_email, target_date, write_status,
)
from config import ConfigError, module_schedule_time


SOURCE_URL = "https://bo3.gg/lol/matches/current?tiers=s"
API_URL = "https://api.bo3.gg/api/v1/matches"
SCORE_KEYS = {
    1: {"1-0", "0-1"},
    3: {"2-0", "2-1", "1-2", "0-2"},
    5: {"3-0", "3-1", "3-2", "2-3", "1-3", "0-3"},
}


def safe_date(value: str) -> str:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise JobError(f"Invalid date: {value!r}")
    date_type.fromisoformat(value)
    return value


def _parse_instant(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def forecast_window(target: str) -> tuple[datetime, datetime]:
    """回傳報告日期排程時間起算、起點含且終點不含的 24 小時視窗。"""
    day = date_type.fromisoformat(target)
    start = datetime.combine(day, module_schedule_time("lol", "prediction"), TAIPEI)
    return start, start + timedelta(days=1)


def extract_taipei_s_matches(records: list[dict[str, object]], target: str) -> list[dict[str, object]]:
    start, end = forecast_window(target)
    matches: dict[int, dict[str, object]] = {}
    for record in records:
        instant = _parse_instant(record.get("start_date"))
        match_id = record.get("id")
        if (
            instant is not None
            and isinstance(match_id, int)
            and str(record.get("tier", "")).lower() == "s"
            and start <= instant.astimezone(TAIPEI) < end
        ):
            matches[match_id] = record
    return sorted(
        matches.values(),
        key=lambda item: _parse_instant(item.get("start_date")) or end,
    )


def fetch_schedule(target: str) -> list[dict[str, object]]:
    start, end = forecast_window(target)
    params = {
        "filter[matches.discipline_id][eq]": "3",
        "filter[matches.tier][in]": "s",
        "filter[matches.start_date][gt]": (start - timedelta(seconds=1)).isoformat(),
        "filter[matches.start_date][lt]": end.isoformat(),
        "sort": "start_date",
        "page[limit]": "100",
    }
    request = urllib.request.Request(
        f"{API_URL}?{urllib.parse.urlencode(params)}",
        headers={"Accept": "application/json", "User-Agent": "codex-lol-automation/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise JobError(f"bo3.gg schedule precheck failed: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise JobError("bo3.gg schedule precheck returned invalid data")
    total = payload.get("total")
    if isinstance(total, dict) and isinstance(total.get("count"), int) and total["count"] > 100:
        raise JobError("bo3.gg returned more than 100 matches; refusing an incomplete slate")
    records = [item for item in payload["results"] if isinstance(item, dict)]
    return extract_taipei_s_matches(records, target)


def compact_match(record: dict[str, object]) -> dict[str, object]:
    bets = record.get("bet_updates") if isinstance(record.get("bet_updates"), dict) else {}
    team1 = bets.get("team_1") if isinstance(bets.get("team_1"), dict) else {}
    team2 = bets.get("team_2") if isinstance(bets.get("team_2"), dict) else {}
    slug = str(record.get("slug", ""))
    return {
        "match_id": record.get("id"),
        "start_time": record.get("start_date"),
        "tier": record.get("tier"),
        "bo_type": record.get("bo_type"),
        "status": record.get("status"),
        "tournament_id": record.get("tournament_id"),
        "team1_id": record.get("team1_id"),
        "team1": team1.get("name") or f"team:{record.get('team1_id')}",
        "team2_id": record.get("team2_id"),
        "team2": team2.get("name") or f"team:{record.get('team2_id')}",
        "url": f"https://bo3.gg/lol/matches/{slug}" if slug else SOURCE_URL,
    }


def prompt_for(target: str, output_dir: Path) -> str:
    start, end = forecast_window(target)
    return f"""使用 `$lol-analysis` 完成 LoL S Tier daily-summary 預測。

報告日期：{target}
預測視窗：{start.isoformat()}（含）至 {end.isoformat()}（不含），共 24 小時。

這是無人值守排程。必須完整讀取並遵守：
- {REPO_ROOT / 'lol-analysis/SKILL.md'}
- skill 指定的 shared 契約與 LoL references
- 已鎖定賽程：{output_dir / 'schedule-precheck.json'}

要求：
1. 只能預測 schedule-precheck.json 列出的比賽；它已鎖定上述 24 小時視窗。賽程入口固定為 {SOURCE_URL}。不得加入 A/B/C Tier，也不得依台灣日曆日自行增減比賽。
2. 查核賽制、名單、版本、近期樣本、BP/英雄池與可用 VOD。先鎖模型機率，再查市場；缺資料保留 N/A，不捏造。
3. 只准寫入 {output_dir}，不得修改 skill、shared 或其他 repo 檔案。排程已在啟動前清除該日期的舊輸出；必須建立本次 prediction.md、forecasts.jsonl、probability-checks.json 與 notion-summary.json。
4. 寫入 {output_dir / 'prediction.md'}，符合 skill 契約，全文最後只有一個「簡表總結」。
5. 寫入 {output_dir / 'forecasts.jsonl'}，每場一行 JSON object，至少包含：
   match_id, predicted_at, start_time, snapshot, model_version, team1, team2,
   tournament, tier="s", bo_type, exact_score_probabilities, team1_win_prob,
   team2_win_prob, team1_at_least_one_prob, team2_at_least_one_prob,
   model_confidence, sources。所有機率均用 0..1。
6. BO3 精確比分鍵必須為 2-0/2-1/1-2/0-2；BO5 為 3-0/3-1/3-2/2-3/1-3/0-3；總和為 1。系列勝率必須等於對應精確比分總和，「至少一局」必須是被橫掃機率的補數，model_confidence 不得冒充勝率。
7. 將上述檢查以百分比寫入 {output_dir / 'probability-checks.json'}，並執行
   `node shared/validate_probabilities.mjs {output_dir / 'probability-checks.json'}`。
8. 依 {REPO_ROOT / 'shared/notion/skill-instructions.md'} 寫入 {output_dir / 'notion-summary.json'}；使用 sport="LoL", module="lol-analysis", analysisType="daily-summary"，startTime 帶 +08:00。
9. 只建立本地 Notion summary；外層程式驗證後發布並寄 Email。最後確認所有檔案確實存在。
"""


def validate_forecasts(path: Path) -> None:
    required = {
        "match_id", "predicted_at", "start_time", "snapshot", "model_version",
        "team1", "team2", "tournament", "tier", "bo_type",
        "exact_score_probabilities", "team1_win_prob", "team2_win_prob",
        "team1_at_least_one_prob", "team2_at_least_one_prob",
        "model_confidence", "sources",
    }
    for index, record in enumerate(load_jsonl(path), 1):
        missing = sorted(required - record.keys())
        if missing:
            raise JobError(f"forecasts.jsonl record {index} missing: {', '.join(missing)}")
        if str(record["tier"]).lower() != "s":
            raise JobError(f"forecasts.jsonl record {index}: tier must be s")
        bo = record["bo_type"]
        if isinstance(bo, bool) or not isinstance(bo, int) or bo not in SCORE_KEYS:
            raise JobError(f"forecasts.jsonl record {index}: unsupported bo_type {bo!r}")
        scores = record["exact_score_probabilities"]
        if not isinstance(scores, dict) or set(scores) != SCORE_KEYS[bo]:
            raise JobError(f"forecasts.jsonl record {index}: invalid exact-score keys")
        values = list(scores.values())
        numeric = all(isinstance(value, (int, float)) and not isinstance(value, bool) and 0 <= value <= 1 for value in values)
        if not numeric or abs(sum(values) - 1) > 0.002:
            raise JobError(f"forecasts.jsonl record {index}: exact-score probabilities must sum to 1")
        for field in ("team1_win_prob", "team2_win_prob", "team1_at_least_one_prob", "team2_at_least_one_prob", "model_confidence"):
            value = record[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise JobError(f"forecasts.jsonl record {index}: {field} must be 0..1")
        wins = 1 if bo == 1 else (bo // 2 + 1)
        team1_sum = sum(value for score, value in scores.items() if score.startswith(f"{wins}-"))
        team2_sum = 1 - team1_sum
        if abs(record["team1_win_prob"] - team1_sum) > 0.002 or abs(record["team2_win_prob"] - team2_sum) > 0.002:
            raise JobError(f"forecasts.jsonl record {index}: series probabilities disagree with exact scores")
        t1_swept = scores[f"0-{wins}"]
        t2_swept = scores[f"{wins}-0"]
        if abs(record["team1_at_least_one_prob"] - (1 - t1_swept)) > 0.002 or abs(record["team2_at_least_one_prob"] - (1 - t2_swept)) > 0.002:
            raise JobError(f"forecasts.jsonl record {index}: at-least-one probabilities are inconsistent")


def validate_notion_summary(path: Path) -> dict[str, object]:
    assert_nonempty(path)
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JobError(f"Invalid Notion summary JSON: {exc}") from exc
    required = {"title", "sport", "module", "event", "startTime", "prediction", "winner", "winProbability", "recommendation", "stake", "confidence", "risk", "sourceStatus", "analysisType", "tags"}
    if not isinstance(summary, dict) or any(key not in summary for key in required):
        raise JobError("Notion summary is missing required fields")
    if summary["sport"] != "LoL" or summary["module"] != "lol-analysis" or summary["analysisType"] != "daily-summary":
        raise JobError("Notion summary must use LoL/lol-analysis/daily-summary")
    if not str(summary["startTime"]).endswith("+08:00"):
        raise JobError("Notion summary startTime must include +08:00")
    if summary["confidence"] is None or not str(summary["confidence"]).strip():
        raise JobError("Notion summary confidence cannot be empty")
    return summary


def publish_to_notion(output_dir: Path) -> str:
    receipt = output_dir / "notion-publish.json"
    if receipt.is_file():
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if saved.get("ok") is True and saved.get("url"):
            return str(saved["url"])
    validate_notion_summary(output_dir / "notion-summary.json")
    result = run(["node", "shared/notion/publish_prediction.mjs", "--summary", str(output_dir / "notion-summary.json"), "--markdown", str(output_dir / "prediction.md")], capture=True)
    try:
        published = json.loads(result.stdout or "")
    except json.JSONDecodeError as exc:
        raise JobError("Notion exporter did not return valid JSON") from exc
    if published.get("ok") is not True or not published.get("url"):
        raise JobError("Notion exporter did not confirm a page URL")
    atomic_json(receipt, published)
    return str(published["url"])


def notify_by_email(output_dir: Path, target: str, notion_url: str) -> None:
    receipt = output_dir / "email-notification.json"
    if receipt.is_file():
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if saved.get("sent") is True and saved.get("notion_url") == notion_url:
            return
    recipients = send_email(
        f"LoL S Tier 預測報告已完成｜{target}",
        f"{target}（台灣時間）的 LoL S Tier 預測報告已完成。\n\nNotion：{notion_url}\n本地報告：{output_dir / 'prediction.md'}\n\n此信由 LoL 自動排程寄出。",
    )
    atomic_json(receipt, {"sent": True, "sent_at": datetime.now(TAIPEI).isoformat(), "recipients": recipients, "notion_url": notion_url})


def finalize_prediction(output_dir: Path, target: str) -> str:
    assert_nonempty(output_dir / "prediction.md")
    assert_nonempty(output_dir / "forecasts.jsonl")
    assert_nonempty(output_dir / "probability-checks.json")
    validate_forecasts(output_dir / "forecasts.jsonl")
    validate_notion_summary(output_dir / "notion-summary.json")
    run(["node", "shared/validate_probabilities.mjs", str(output_dir / "probability-checks.json")])
    notion_url = publish_to_notion(output_dir)
    notify_by_email(output_dir, target, notion_url)
    write_status(output_dir, "prediction", "complete", target_date=target, notion_url=notion_url, email_notified=True)
    return notion_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="覆寫台灣時間目標日期（YYYY-MM-DD）")
    parser.add_argument("--force", action="store_true", help="相容舊呼叫；排程現在預設就會重跑")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cleanup_old_reports(days=3, dry_run=args.dry_run)
    target = safe_date(args.date or target_date())
    output_dir = STATE_ROOT / "predictions" / target
    try:
        with job_lock("prediction"):
            if args.dry_run:
                print(prompt_for(target, output_dir))
                return 0
            if recreate_dated_output_dir(output_dir, STATE_ROOT / "predictions"):
                print(f"[reset] Removed existing prediction directory: {output_dir}", flush=True)
            matches = fetch_schedule(target)
            window_start, window_end = forecast_window(target)
            snapshot = {
                "report_date": target,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "window_boundary": "start-inclusive/end-exclusive",
                "checked_at": datetime.now(TAIPEI).isoformat(),
                "source": SOURCE_URL,
                "api": API_URL,
                "tier": "s",
                "match_count": len(matches),
                "matches": [compact_match(match) for match in matches],
            }
            atomic_json(output_dir / "schedule-precheck.json", snapshot)
            if not matches:
                write_status(output_dir, "prediction", "skipped", target_date=target, reason="no LoL S Tier matches")
                print(
                    f"Prediction skipped; bo3.gg has no LoL S Tier matches in the "
                    f"{target} {window_start:%H:%M} TW window"
                )
                return 0
            write_status(output_dir, "prediction", "running", target_date=target)
            run(codex_command(REPO_ROOT, output_dir / "agent-last-message.md", prompt_for(target, output_dir)))
            notion_url = finalize_prediction(output_dir, target)
            print(f"Prediction complete: {output_dir / 'prediction.md'}")
            print(f"Notion: {notion_url}")
            return 0
    except (ConfigError, JobError, OSError, ValueError) as exc:
        return fail(output_dir, "prediction", exc)


if __name__ == "__main__":
    raise SystemExit(main())
