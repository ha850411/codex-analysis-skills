#!/usr/bin/env python3
"""依 JSON 設定的台灣時間預測未來 24 小時全部 MLB 賽事。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as date_type, datetime, timedelta
from pathlib import Path

AUTOMATION_DIR = Path(__file__).resolve().parents[1]
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))
os.environ["AUTOMATION_MODULE"] = "mlb"

from common import (
    REPO_ROOT,
    STATE_ROOT,
    TAIPEI,
    JobError,
    assert_nonempty,
    atomic_json,
    cleanup_old_reports,
    codex_command,
    fail,
    job_lock,
    load_jsonl,
    recreate_dated_output_dir,
    run,
    send_email,
    target_date,
    write_status,
)
from config import ConfigError, module_schedule_time


FORECAST_FIELDS = {
    "game_id",
    "predicted_at",
    "first_pitch",
    "snapshot",
    "model_version",
    "away_team",
    "home_team",
    "away_f5_runs_mean",
    "home_f5_runs_mean",
    "away_late_runs_mean",
    "home_late_runs_mean",
    "away_runs_mean",
    "home_runs_mean",
    "home_win_prob",
    "model_confidence",
    "sources",
}

UNMODELED_FORECAST_FIELDS = {
    "game_id",
    "predicted_at",
    "first_pitch",
    "snapshot",
    "model_version",
    "away_team",
    "home_team",
    "status",
    "missing_data",
    "sources",
}


def forecast_window(target: str) -> tuple[datetime, datetime]:
    """回傳報告日期排程時間起算、起點含且終點不含的 24 小時視窗。"""
    day = date_type.fromisoformat(target)
    start = datetime.combine(day, module_schedule_time("mlb", "prediction"), TAIPEI)
    return start, start + timedelta(days=1)


def fetch_schedule(target: str) -> list[dict[str, object]]:
    """查詢相鄰 MLB 日期，再保留落在指定 24 小時視窗的賽事。"""
    requested = date_type.fromisoformat(target)
    payloads: list[dict[str, object]] = []
    for day in (
        requested - timedelta(days=1),
        requested,
        requested + timedelta(days=1),
    ):
        query = urllib.parse.urlencode({"sportId": 1, "date": day.isoformat()})
        request = urllib.request.Request(
            f"https://statsapi.mlb.com/api/v1/schedule?{query}",
            headers={"Accept": "application/json", "User-Agent": "codex-mlb-automation/1.0"},
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                payload = json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise JobError(f"MLB schedule precheck failed for {day}: {exc}") from exc
        if not isinstance(payload, dict):
            raise JobError(f"MLB schedule precheck returned invalid data for {day}")
        payloads.append(payload)
    return extract_taipei_games(payloads, target)


def safe_date(value: str) -> str:
    """驗證日期並拒絕可能逃出 predictions 目錄的路徑字串。"""
    try:
        parsed = date_type.fromisoformat(value)
    except ValueError as exc:
        raise JobError(f"Invalid date: {value!r}") from exc
    if parsed.isoformat() != value:
        raise JobError(f"Invalid date: {value!r}")
    return value


def extract_taipei_games(
    payloads: list[dict[str, object]], target: str
) -> list[dict[str, object]]:
    start, end = forecast_window(target)
    games: dict[int, dict[str, object]] = {}
    for payload in payloads:
        for schedule_date in payload.get("dates", []):
            if not isinstance(schedule_date, dict):
                continue
            for game in schedule_date.get("games", []):
                if not isinstance(game, dict):
                    continue
                game_date = game.get("gameDate")
                game_pk = game.get("gamePk")
                if not isinstance(game_date, str) or not isinstance(game_pk, int):
                    continue
                try:
                    instant = datetime.fromisoformat(game_date.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if start <= instant.astimezone(TAIPEI) < end:
                    games[game_pk] = game
    return sorted(
        games.values(),
        key=lambda game: datetime.fromisoformat(str(game["gameDate"]).replace("Z", "+00:00")),
    )


def prompt_for(date: str, output_dir: Path) -> str:
    start, end = forecast_window(date)
    return f"""使用 `$mlb-analysis` 完成未來 24 小時全部 MLB 賽事的 daily-summary 預測。

報告日期：{date}
預測視窗：{start.isoformat()}（含）至 {end.isoformat()}（不含），共 24 小時。

這是無人值守排程。必須完整讀取並遵守：
- {REPO_ROOT / 'mlb-analysis/SKILL.md'}
- skill 指定的 shared 契約與 MLB references

要求：
1. 只能分析 {output_dir / 'schedule-precheck.json'} 鎖定在上述視窗內的比賽，再用即時網路來源查核雙重賽、延賽、TBD 先發及美國跨日；不得依台灣日曆日自行增減比賽。
2. 嚴格先鎖定模型機率，再查市場；資料不足時保留 N/A／等待條件，不硬造數字。
   零場可建模時仍必須完成並交付 degraded 報告；報告失去數值不等於排程失敗。
3. 產生 pre-lineup 預測快照。只准寫入 {output_dir}，不得修改 skill、shared 檔或其他 repo 檔案。排程已在啟動前清除該日期的舊輸出；必須建立本次 prediction.md、forecasts.jsonl、probability-checks.json 與 notion-summary.json。
4. 寫入 {output_dir / 'prediction.md'}，必須符合 skill 的輸出契約，且全文最後只有一個「簡表總結」。
5. 寫入 {output_dir / 'forecasts.jsonl'}，每場一行 JSON object，至少包含：
   game_id, predicted_at, first_pitch, snapshot, model_version, away_team, home_team,
   away_f5_runs_mean, home_f5_runs_mean, away_late_runs_mean, home_late_runs_mean,
   away_runs_mean, home_runs_mean, home_win_prob（0..1）, model_confidence（0..1）, sources。
   若比賽存在但無法可靠建模，仍保留紀錄並以 status 與 missing_data 說明；不得捏造缺失值。
   這類紀錄仍須保存 game_id、時間、快照、模型狀態、主客隊、來源與非空 missing_data，數值欄位可為 null。
   若官方確認該 24 小時視窗完全無賽事，寫一筆 {{"status":"no-games","date":"{date}","sources":[...]}}。
6. 將機率檢查資料寫到 {output_dir / 'probability-checks.json'}，並實際執行
   `node shared/validate_probabilities.mjs {output_dir / 'probability-checks.json'}`。
7. 依 {REPO_ROOT / 'shared/notion/skill-instructions.md'} 建立 {output_dir / 'notion-summary.json'}，供整日賽程建立一筆 Notion daily-summary。至少包含：
   title, sport="MLB", module="mlb-analysis", event, startTime（+08:00）, prediction,
   winner, winProbability, recommendation, stake, confidence, risk, sourceStatus,
   analysisType="daily-summary", tags。
8. 只建立本地 Notion summary，不要自行發布；外層程式會在驗證成功後發布並寄 Email。
9. 最後自行檢查 prediction.md、forecasts.jsonl 與 notion-summary.json 均已建立；不要只在最終訊息貼報告。
"""


def validate_forecasts(path: Path) -> dict[str, object]:
    records = load_jsonl(path)
    no_games = [record for record in records if record.get("status") == "no-games"]
    if no_games:
        if len(records) != 1:
            raise JobError("forecasts.jsonl cannot mix no-games with game forecasts")
        record = no_games[0]
        if not record.get("date") or not record.get("sources"):
            raise JobError("forecasts.jsonl no-games record requires date and sources")
        if not isinstance(record["sources"], list) or not all(
            isinstance(value, str) and value.strip() for value in record["sources"]
        ):
            raise JobError("forecasts.jsonl no-games sources must be non-empty strings")
        return {
            "record_count": 1,
            "modeled_count": 0,
            "unmodeled_count": 0,
            "report_quality": "no-games",
        }

    modeled_count = 0
    unmodeled_count = 0
    for index, record in enumerate(records, 1):
        if record.get("status") == "no-games":
            raise AssertionError("no-games records were handled above")
        if record.get("status", "modeled") != "modeled":
            unmodeled_count += 1
            missing = sorted(UNMODELED_FORECAST_FIELDS - record.keys())
            if missing:
                raise JobError(
                    f"forecasts.jsonl unmodeled record {index} missing: {', '.join(missing)}"
                )
            if not isinstance(record.get("missing_data"), list) or not record["missing_data"]:
                raise JobError(
                    f"forecasts.jsonl record {index} is unmodeled without non-empty missing_data"
                )
            if not all(
                isinstance(value, str) and value.strip() for value in record["missing_data"]
            ):
                raise JobError(
                    f"forecasts.jsonl record {index} missing_data values must be non-empty strings"
                )
            if not isinstance(record.get("sources"), list) or not record["sources"]:
                raise JobError(
                    f"forecasts.jsonl record {index} is unmodeled without non-empty sources"
                )
            if not all(isinstance(value, str) and value.strip() for value in record["sources"]):
                raise JobError(
                    f"forecasts.jsonl record {index} sources must be non-empty strings"
                )
            if isinstance(record["game_id"], bool) or not isinstance(
                record["game_id"], (str, int)
            ) or not str(record["game_id"]).strip():
                raise JobError(f"forecasts.jsonl record {index} has invalid game_id")
            for field in (
                "predicted_at", "first_pitch", "snapshot", "model_version",
                "away_team", "home_team", "status",
            ):
                if not isinstance(record[field], str) or not record[field].strip():
                    raise JobError(
                        f"forecasts.jsonl unmodeled record {index}: {field} must be non-empty"
                    )
            continue
        modeled_count += 1
        missing = sorted(FORECAST_FIELDS - record.keys())
        if missing:
            raise JobError(f"forecasts.jsonl record {index} missing: {', '.join(missing)}")
        model_version = record["model_version"]
        if not isinstance(model_version, str) or not model_version.strip() or model_version.strip().upper().startswith("N/A"):
            raise JobError(f"forecasts.jsonl record {index}: model_version must identify a production model")
        for field in (
            "away_f5_runs_mean", "home_f5_runs_mean", "away_late_runs_mean",
            "home_late_runs_mean", "away_runs_mean", "home_runs_mean",
        ):
            value = record[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise JobError(f"forecasts.jsonl record {index}: {field} must be a non-negative number")
        for field in ("home_win_prob", "model_confidence"):
            value = record[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise JobError(f"forecasts.jsonl record {index}: {field} must be 0..1")

    report_quality = "modeled"
    if modeled_count == 0:
        report_quality = "degraded"
    elif unmodeled_count:
        report_quality = "partial"
    return {
        "record_count": len(records),
        "modeled_count": modeled_count,
        "unmodeled_count": unmodeled_count,
        "report_quality": report_quality,
    }


def validate_notion_summary(path: Path) -> dict[str, object]:
    assert_nonempty(path)
    try:
        summary = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JobError(f"Invalid Notion summary JSON: {exc}") from exc
    if not isinstance(summary, dict):
        raise JobError("Notion summary must be a JSON object")
    required = {
        "title", "sport", "module", "event", "startTime", "prediction", "winner",
        "winProbability", "recommendation", "stake", "confidence", "risk",
        "sourceStatus", "analysisType", "tags",
    }
    missing = sorted(key for key in required if key not in summary)
    if missing:
        raise JobError(f"Notion summary missing: {', '.join(missing)}")
    if summary["sport"] != "MLB" or summary["module"] != "mlb-analysis":
        raise JobError("Notion summary must use sport=MLB and module=mlb-analysis")
    if summary["analysisType"] != "daily-summary":
        raise JobError("Notion summary must use analysisType=daily-summary")
    if not str(summary["startTime"]).endswith("+08:00"):
        raise JobError("Notion summary startTime must include the +08:00 timezone")
    if summary["confidence"] is None or not str(summary["confidence"]).strip():
        raise JobError("Notion summary confidence cannot be empty")
    return summary


def publish_to_notion(output_dir: Path) -> str:
    receipt = output_dir / "notion-publish.json"
    if receipt.is_file():
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if saved.get("ok") is True and saved.get("url"):
            return str(saved["url"])
    summary = output_dir / "notion-summary.json"
    validate_notion_summary(summary)
    result = run(
        [
            "node",
            "shared/notion/publish_prediction.mjs",
            "--summary",
            str(summary),
            "--markdown",
            str(output_dir / "prediction.md"),
        ],
        capture=True,
    )
    try:
        published = json.loads(result.stdout or "")
    except json.JSONDecodeError as exc:
        raise JobError("Notion exporter did not return valid JSON") from exc
    if published.get("ok") is not True or not published.get("url"):
        raise JobError("Notion exporter did not confirm a published page URL")
    atomic_json(receipt, published)
    return str(published["url"])


def notify_by_email(
    output_dir: Path,
    date: str,
    notion_url: str,
    report_quality: str = "modeled",
) -> None:
    receipt = output_dir / "email-notification.json"
    if receipt.is_file():
        saved = json.loads(receipt.read_text(encoding="utf-8"))
        if saved.get("sent") is True and saved.get("notion_url") == notion_url:
            return
    recipients = send_email(
        f"MLB 預測報告已完成｜{date}｜{report_quality}",
        "\n".join(
            [
                f"{date}（台灣時間）的 MLB 預測報告已完成。",
                "",
                f"Notion：{notion_url}",
                f"本地報告：{output_dir / 'prediction.md'}",
                f"報告品質：{report_quality}",
                "",
                "此信由 MLB 自動排程寄出。",
            ]
        ),
    )
    atomic_json(
        receipt,
        {
            "sent": True,
            "sent_at": datetime.now(TAIPEI).isoformat(),
            "recipients": recipients,
            "notion_url": notion_url,
            "report_quality": report_quality,
        },
    )


def finalize_prediction(output_dir: Path, date: str) -> str:
    prediction = output_dir / "prediction.md"
    forecasts = output_dir / "forecasts.jsonl"
    assert_nonempty(prediction)
    assert_nonempty(forecasts)
    assert_nonempty(output_dir / "probability-checks.json")
    validation = validate_forecasts(forecasts)
    validate_notion_summary(output_dir / "notion-summary.json")
    run(["node", "shared/validate_probabilities.mjs", str(output_dir / "probability-checks.json")])
    notion_url = publish_to_notion(output_dir)
    report_quality = str(validation["report_quality"])
    notify_by_email(output_dir, date, notion_url, report_quality)
    write_status(
        output_dir,
        "prediction",
        "complete",
        target_date=date,
        notion_url=notion_url,
        email_notified=True,
        report_quality=report_quality,
        modeled_forecasts=validation["modeled_count"],
        unmodeled_forecasts=validation["unmodeled_count"],
    )
    return notion_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="覆寫台灣時間目標日期（YYYY-MM-DD）")
    parser.add_argument("--force", action="store_true", help="相容舊呼叫；排程現在預設就會重跑")
    parser.add_argument("--dry-run", action="store_true", help="只顯示工作內容，不啟動 Codex")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cleanup_old_reports(days=3, dry_run=args.dry_run)
    date = safe_date(args.date or target_date())
    output_dir = STATE_ROOT / "predictions" / date
    prediction = output_dir / "prediction.md"

    try:
        with job_lock("prediction"):
            prompt = prompt_for(date, output_dir)
            if args.dry_run:
                print(prompt)
                return 0
            if recreate_dated_output_dir(output_dir, STATE_ROOT / "predictions"):
                print(f"[reset] Removed existing prediction directory: {output_dir}", flush=True)
            games = fetch_schedule(date)
            window_start, window_end = forecast_window(date)
            schedule_snapshot = {
                "report_date": date,
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "window_boundary": "start-inclusive/end-exclusive",
                "checked_at": datetime.now(TAIPEI).isoformat(),
                "source": "MLB Stats API",
                "game_count": len(games),
                "game_ids": sorted(game["gamePk"] for game in games),
            }
            atomic_json(output_dir / "schedule-precheck.json", schedule_snapshot)
            if not games:
                write_status(output_dir, "prediction", "skipped", target_date=date, reason="no MLB games")
                print(
                    f"Prediction skipped; MLB schedule has no games in the "
                    f"{date} {window_start:%H:%M} TW window"
                )
                return 0
            write_status(output_dir, "prediction", "running", target_date=date)
            run(codex_command(REPO_ROOT, output_dir / "agent-last-message.md", prompt))
            notion_url = finalize_prediction(output_dir, date)
            print(f"Prediction complete: {prediction}")
            print(f"Notion: {notion_url}")
            return 0
    except (ConfigError, JobError, OSError) as exc:
        return fail(output_dir, "prediction", exc)


if __name__ == "__main__":
    raise SystemExit(main())
