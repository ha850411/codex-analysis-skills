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
    "f5_away_win_prob",
    "f5_tie_prob",
    "f5_home_win_prob",
    "away_runs_p10",
    "away_runs_p90",
    "home_runs_p10",
    "home_runs_p90",
    "total_runs_p10",
    "total_runs_p90",
    "model_confidence",
    "status",
    "model_tier",
    "validation_status",
    "recommendation_eligible",
    "sources",
}

BASELINE_CONFIDENCE_FIELDS = {
    "confidence_components",
    "confidence_diagnostics",
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
        query = urllib.parse.urlencode({
            "sportId": 1,
            "date": day.isoformat(),
            "hydrate": "probablePitcher,team,venue",
        })
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
2. 先讀取排程已確定性建立的 {output_dir / 'public-baseline.json'}。逐場保留其中的
   model_version、status=baseline、run means、主隊勝率、前五局三路、區間、逐場信心度、
   五項信心組成、信心診斷值與 validation_status，不得改成 N/A，也不得用市場價格修改。
   信心度不設硬上限，禁止以模型層級或全日摘要數字把逐場信心度改成同一值。可用即時資料補充風險與等待條件。
   public baseline 是未完成 walk-forward 校準的方向性數值層：可報機率與公允價格，
   但 recommendation_eligible=false，全部注碼固定 0u，不得寫主推或可打。
3. 嚴格先鎖定模型機率，再查市場。只有 public-baseline.json 明確缺少某 game ID 時，
   才能把該場標成 unmodeled；不得因缺少付費投影或正式打線，把已存在的 baseline 整場清空。
4. 產生 pre-lineup 預測快照。只准寫入 {output_dir}，不得修改 skill、shared 檔或其他 repo 檔案。排程已在啟動前清除該日期的舊輸出；必須建立本次 prediction.md、forecasts.jsonl、probability-checks.json 與 notion-summary.json。
5. 寫入 {output_dir / 'prediction.md'}，必須符合 skill 的 daily-summary 輸出契約：不要為 17 場重複完整單場模板；先給全日結論與賽程盤點，再以一張數值比較表列全場，只展開最多 3 場觀察名單，且全文最後只有一個「簡表總結」。
6. 寫入 {output_dir / 'forecasts.jsonl'}，每場一行 JSON object，至少包含：
   game_id, predicted_at, first_pitch, snapshot, model_version, away_team, home_team,
   away_f5_runs_mean, home_f5_runs_mean, away_late_runs_mean, home_late_runs_mean,
   away_runs_mean, home_runs_mean, home_win_prob（0..1）, model_confidence（0..1）,
   confidence_components, confidence_diagnostics,
   f5_away_win_prob, f5_tie_prob, f5_home_win_prob, away/home/total_runs_p10/p90,
   status, model_tier, validation_status, recommendation_eligible, sources。
   以上模型欄位必須逐字／逐值沿用 public-baseline.json；不得自行重算或四捨五入 JSON。
   若比賽存在但無法可靠建模，仍保留紀錄並以 status 與 missing_data 說明；不得捏造缺失值。
   這類紀錄仍須保存 game_id、時間、快照、模型狀態、主客隊、來源與非空 missing_data，數值欄位可為 null。
   若官方確認該 24 小時視窗完全無賽事，寫一筆 {{"status":"no-games","date":"{date}","sources":[...]}}。
7. 將機率檢查資料寫到 {output_dir / 'probability-checks.json'}，並實際執行
   `node shared/validate_probabilities.mjs {output_dir / 'probability-checks.json'}`。
   每一場 baseline 都必須包含 `weighted_confidence` 檢查，使用 public-baseline.json 的
   model_confidence（轉為整數百分比）與五項 confidence_components 回算。
8. 依 {REPO_ROOT / 'shared/notion/skill-instructions.md'} 建立 {output_dir / 'notion-summary.json'}，供整日賽程建立一筆 Notion daily-summary。至少包含：
   title, sport="MLB", module="mlb-analysis", event, startTime（+08:00）, prediction,
   winner, winProbability, recommendation, stake, confidence, risk, sourceStatus,
   analysisType="daily-summary", tags。confidence 必須寫逐場實際最小值–最大值；若剛好相同才寫單一值，
   不得寫成「baseline 上限」。
9. 只建立本地 Notion summary，不要自行發布；外層程式會在驗證成功後發布並寄 Email。
10. 最後自行檢查 prediction.md、forecasts.jsonl 與 notion-summary.json 均已建立；不要只在最終訊息貼報告。
"""


def build_public_baseline(output_dir: Path) -> None:
    """在啟動生成式報告前，先確定性建立可稽核的官方資料基準。"""
    run(
        [
            sys.executable,
            "mlb-analysis/scripts/build_public_baseline.py",
            str(output_dir / "schedule-precheck.json"),
            "--output",
            str(output_dir / "public-baseline.json"),
        ]
    )


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
            "baseline_count": 0,
            "unmodeled_count": 0,
            "report_quality": "no-games",
        }

    modeled_count = 0
    baseline_count = 0
    unmodeled_count = 0
    for index, record in enumerate(records, 1):
        if record.get("status") == "no-games":
            raise AssertionError("no-games records were handled above")
        status = record.get("status", "modeled")
        if status not in {"modeled", "baseline"}:
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
        if status == "modeled":
            modeled_count += 1
        else:
            baseline_count += 1
        missing = sorted(FORECAST_FIELDS - record.keys())
        if missing:
            raise JobError(f"forecasts.jsonl record {index} missing: {', '.join(missing)}")
        model_version = record["model_version"]
        if not isinstance(model_version, str) or not model_version.strip() or model_version.strip().upper().startswith("N/A"):
            raise JobError(f"forecasts.jsonl record {index}: model_version must identify a numeric model")
        if status == "baseline":
            if record.get("model_tier") != "public-data-baseline":
                raise JobError(f"forecasts.jsonl record {index}: baseline model_tier mismatch")
            if record.get("validation_status") != "uncalibrated":
                raise JobError(f"forecasts.jsonl record {index}: baseline must remain uncalibrated")
            if record.get("recommendation_eligible") is not False:
                raise JobError(f"forecasts.jsonl record {index}: baseline cannot be recommendation eligible")
            missing_confidence = sorted(BASELINE_CONFIDENCE_FIELDS - record.keys())
            if missing_confidence:
                raise JobError(
                    f"forecasts.jsonl baseline record {index} missing: "
                    + ", ".join(missing_confidence)
                )
            components = record["confidence_components"]
            expected_component_keys = {
                "dataCompleteness", "freshness", "lineupCertainty",
                "regimeRelevance", "modelStability",
            }
            if not isinstance(components, dict) or set(components) != expected_component_keys:
                raise JobError(
                    f"forecasts.jsonl baseline record {index}: invalid confidence_components"
                )
            if any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not 0 <= value <= 100
                for value in components.values()
            ):
                raise JobError(
                    f"forecasts.jsonl baseline record {index}: confidence components must be 0..100"
                )
            weighted_score = (
                0.25 * components["dataCompleteness"]
                + 0.20 * components["freshness"]
                + 0.25 * components["lineupCertainty"]
                + 0.20 * components["regimeRelevance"]
                + 0.10 * components["modelStability"]
            )
            weighted_confidence = int(weighted_score + 0.5) / 100.0
            if record["model_confidence"] != weighted_confidence:
                raise JobError(
                    f"forecasts.jsonl baseline record {index}: model_confidence does not match components"
                )
            diagnostics = record["confidence_diagnostics"]
            if not isinstance(diagnostics, dict) or diagnostics.get("hard_cap", "missing") is not None:
                raise JobError(
                    f"forecasts.jsonl baseline record {index}: confidence must not have a hard cap"
                )
        for field in (
            "away_f5_runs_mean", "home_f5_runs_mean", "away_late_runs_mean",
            "home_late_runs_mean", "away_runs_mean", "home_runs_mean",
        ):
            value = record[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
                raise JobError(f"forecasts.jsonl record {index}: {field} must be a non-negative number")
        for field in (
            "home_win_prob", "model_confidence", "f5_away_win_prob",
            "f5_tie_prob", "f5_home_win_prob",
        ):
            value = record[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 1:
                raise JobError(f"forecasts.jsonl record {index}: {field} must be 0..1")
        f5_sum = sum(record[field] for field in (
            "f5_away_win_prob", "f5_tie_prob", "f5_home_win_prob"
        ))
        if abs(f5_sum - 1.0) > 0.002:
            raise JobError(f"forecasts.jsonl record {index}: F5 probabilities must sum to 1")
        for lower, upper in (
            ("away_runs_p10", "away_runs_p90"),
            ("home_runs_p10", "home_runs_p90"),
            ("total_runs_p10", "total_runs_p90"),
        ):
            if any(
                isinstance(record[field], bool) or not isinstance(record[field], (int, float))
                for field in (lower, upper)
            ):
                raise JobError(
                    f"forecasts.jsonl record {index}: {lower}/{upper} must be numeric"
                )
            if record[lower] > record[upper]:
                raise JobError(f"forecasts.jsonl record {index}: {lower} exceeds {upper}")

    report_quality = "modeled"
    numeric_count = modeled_count + baseline_count
    if numeric_count == 0:
        report_quality = "degraded"
    elif baseline_count and not modeled_count and not unmodeled_count:
        report_quality = "baseline"
    elif baseline_count or unmodeled_count:
        report_quality = "partial"
    return {
        "record_count": len(records),
        "modeled_count": modeled_count,
        "baseline_count": baseline_count,
        "unmodeled_count": unmodeled_count,
        "report_quality": report_quality,
    }


def validate_against_public_baseline(forecasts_path: Path, baseline_path: Path) -> None:
    """防止生成式報告把已算出的 baseline 清空、改寫或市場洩漏。"""
    try:
        baseline_payload = json.loads(baseline_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JobError(f"Invalid public baseline JSON: {exc}") from exc
    expected_rows = baseline_payload.get("forecasts")
    if not isinstance(expected_rows, list) or not expected_rows:
        raise JobError("public-baseline.json has no forecasts")
    actual_rows = load_jsonl(forecasts_path)
    expected = {str(row.get("game_id")): row for row in expected_rows if isinstance(row, dict)}
    actual = {str(row.get("game_id")): row for row in actual_rows}
    if set(expected) != set(actual):
        raise JobError("forecasts.jsonl game IDs do not match public-baseline.json")
    locked_fields = {
        "model_version", "status", "model_tier", "validation_status",
        "recommendation_eligible", "away_f5_runs_mean", "home_f5_runs_mean",
        "away_late_runs_mean", "home_late_runs_mean", "away_runs_mean",
        "home_runs_mean", "home_win_prob", "model_confidence",
        "confidence_components", "confidence_diagnostics",
        "f5_away_win_prob", "f5_tie_prob", "f5_home_win_prob",
        "away_runs_p10", "away_runs_p90", "home_runs_p10", "home_runs_p90",
        "total_runs_p10", "total_runs_p90",
    }
    for game_id, expected_row in expected.items():
        actual_row = actual[game_id]
        changed = sorted(
            field for field in locked_fields
            if actual_row.get(field) != expected_row.get(field)
        )
        if changed:
            raise JobError(
                f"forecasts.jsonl game {game_id} changed locked baseline fields: "
                + ", ".join(changed)
            )


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
    validate_against_public_baseline(forecasts, output_dir / "public-baseline.json")
    if int(validation["modeled_count"]) + int(validation["baseline_count"]) == 0:
        raise JobError("refusing to publish an all-N/A MLB report")
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
        baseline_forecasts=validation["baseline_count"],
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
            build_public_baseline(output_dir)
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
