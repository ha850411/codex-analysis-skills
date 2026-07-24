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
from dataclasses import dataclass
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


@dataclass(frozen=True)
class ScheduleFetch:
    matches: list[dict[str, object]]
    filtered_payload: dict[str, object]
    unfiltered_payload: dict[str, object]
    filtered_match_ids: list[int]
    client_filtered_match_ids: list[int]


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


def _fetch_schedule_payload(target: str, *, tier_filtered: bool) -> dict[str, object]:
    start, end = forecast_window(target)
    params = {
        "filter[matches.discipline_id][eq]": "3",
        "filter[matches.start_date][gt]": (start - timedelta(seconds=1)).isoformat(),
        "filter[matches.start_date][lt]": end.isoformat(),
        "sort": "start_date",
        "page[limit]": "100",
    }
    if tier_filtered:
        params["filter[matches.tier][in]"] = "s"
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
    return payload


def _payload_records(payload: dict[str, object]) -> list[dict[str, object]]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise JobError("bo3.gg schedule precheck returned invalid data")
    return [item for item in results if isinstance(item, dict)]


def fetch_schedule(target: str) -> ScheduleFetch:
    """以伺服器端與客戶端 S-tier 篩選各查一次，合併候選並保留原始回應。"""
    filtered_payload = _fetch_schedule_payload(target, tier_filtered=True)
    unfiltered_payload = _fetch_schedule_payload(target, tier_filtered=False)
    filtered_matches = extract_taipei_s_matches(
        _payload_records(filtered_payload), target
    )
    client_filtered_matches = extract_taipei_s_matches(
        _payload_records(unfiltered_payload), target
    )
    union: dict[int, dict[str, object]] = {}
    for record in [*filtered_matches, *client_filtered_matches]:
        match_id = record.get("id")
        if isinstance(match_id, int):
            union[match_id] = record
    matches = sorted(
        union.values(),
        key=lambda item: _parse_instant(item.get("start_date"))
        or forecast_window(target)[1],
    )
    return ScheduleFetch(
        matches=matches,
        filtered_payload=filtered_payload,
        unfiltered_payload=unfiltered_payload,
        filtered_match_ids=[
            int(record["id"]) for record in filtered_matches
            if isinstance(record.get("id"), int)
        ],
        client_filtered_match_ids=[
            int(record["id"]) for record in client_filtered_matches
            if isinstance(record.get("id"), int)
        ],
    )


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
- bo3.gg 候選賽程：{output_dir / 'schedule-precheck.json'}
- bo3.gg 原始伺服器端 S-tier 回應：{output_dir / 'bo3-filtered-response.json'}
- bo3.gg 原始未套 tier 回應：{output_dir / 'bo3-unfiltered-response.json'}

要求：
1. 以 bo3.gg 與 Leaguepedia（lol.fandom.com）為主要賽程來源進行盤點與核對；將 bo3.gg 作為 role="official" 來源，Leaguepedia / Liquipedia 作為 role="independent" 獨立核對來源。
2. 建立 {output_dir / 'schedule-verification.json'}，至少包含：
   verified_at, timezone="Asia/Taipei", window_start, window_end,
   complete, no_matches, candidate_match_ids, added_match_ids,
   removed_match_ids, conflicts, sources, matches。
   sources 每筆包含 role="official" 或 role="independent"、url、checked_at；
   matches 每筆包含 match_id, start_time, tier="s", bo_type, team1, team2,
   tournament, source_urls。match_id 必須能回查 bo3.gg。
3. 以 bo3.gg 與 Leaguepedia / Liquipedia 雙來源核對；發現候選外賽事時補入，候選誤列時移除並說明。雙來源支持相同集合、所有 match ID 已取得且 conflicts 為空時寫 complete=true。無賽事也須雙來源確認。
4. 若來源不一致或有未解場次，寫 complete=false 與 conflicts 後停止；不要建立預測、Notion summary 或可發布報告。外層會以失敗狀態停止發布與寄信。
5. 通過賽程驗證後，`schedule-verification.json` 的 matches 才是唯一預測集合。不得加入 A/B/C Tier或視窗外賽事，並在 prediction.md 揭露候選／新增／移除場次及驗證來源。
6. 查核賽制、名單、版本、近期樣本、BP/英雄池與可用 VOD。先鎖模型機率，再查市場；缺資料保留 N/A，不捏造。
7. 只准寫入 {output_dir}，不得修改 skill、shared 或其他 repo 檔案。排程已在啟動前清除該日期的舊輸出。若 no_matches=true，只建立 schedule-verification.json；否則必須建立本次 prediction.md、forecasts.jsonl、probability-checks.json 與 notion-summary.json。
8. 寫入 {output_dir / 'prediction.md'}，符合 skill 契約，全文最後只有一個「簡表總結」。
9. 寫入 {output_dir / 'forecasts.jsonl'}，每場一行 JSON object，至少包含：
   match_id, predicted_at, start_time, snapshot, model_version, team1, team2,
   tournament, tier="s", bo_type, exact_score_probabilities, team1_win_prob,
   team2_win_prob, team1_at_least_one_prob, team2_at_least_one_prob,
   model_confidence, sources。所有機率均用 0..1。
10. BO3 精確比分鍵必須為 2-0/2-1/1-2/0-2；BO5 為 3-0/3-1/3-2/2-3/1-3/0-3；總和為 1。系列勝率必須等於對應精確比分總和，「至少一局」必須是被橫掃機率的補數，model_confidence 不得冒充勝率。
11. 將上述檢查以百分比寫入 {output_dir / 'probability-checks.json'}，並執行
   `node shared/validate_probabilities.mjs {output_dir / 'probability-checks.json'}`。
12. 依 {REPO_ROOT / 'shared/notion/skill-instructions.md'} 寫入 {output_dir / 'notion-summary.json'}；使用 sport="LoL", module="lol-analysis", analysisType="daily-summary"，startTime 帶 +08:00。
13. 只建立本地 Notion summary；外層程式驗證賽程與機率後才會發布並寄 Email。最後確認所有檔案確實存在。
"""


def validate_forecasts(path: Path) -> None:
    required = {
        "match_id", "predicted_at", "start_time", "snapshot", "model_version",
        "team1", "team2", "tournament", "tier", "bo_type",
        "exact_score_probabilities", "team1_win_prob", "team2_win_prob",
        "team1_at_least_one_prob", "team2_at_least_one_prob",
        "model_confidence", "sources",
    }
    seen_match_ids: set[int] = set()
    for index, record in enumerate(load_jsonl(path), 1):
        missing = sorted(required - record.keys())
        if missing:
            raise JobError(f"forecasts.jsonl record {index} missing: {', '.join(missing)}")
        match_id = record["match_id"]
        if (
            isinstance(match_id, bool)
            or not isinstance(match_id, int)
            or match_id in seen_match_ids
        ):
            raise JobError(
                f"forecasts.jsonl record {index}: match_id must be a unique integer"
            )
        seen_match_ids.add(match_id)
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


def validate_schedule_verification(
    path: Path, precheck_path: Path
) -> dict[str, object]:
    """驗證雙來源賽程閘門與候選集合差異，未完成時一律拒絕發布。"""
    assert_nonempty(path)
    assert_nonempty(precheck_path)
    try:
        verification = json.loads(path.read_text(encoding="utf-8"))
        precheck = json.loads(precheck_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JobError(f"Invalid schedule verification JSON: {exc}") from exc
    if not isinstance(verification, dict) or not isinstance(precheck, dict):
        raise JobError("Schedule verification and precheck must be JSON objects")
    required = {
        "verified_at", "timezone", "window_start", "window_end", "complete",
        "no_matches", "candidate_match_ids", "added_match_ids",
        "removed_match_ids", "conflicts", "sources", "matches",
    }
    missing = sorted(required - verification.keys())
    if missing:
        raise JobError(
            f"Schedule verification missing fields: {', '.join(missing)}"
        )
    if verification["complete"] is not True:
        conflicts = verification.get("conflicts")
        detail = json.dumps(conflicts, ensure_ascii=False)
        raise JobError(f"Schedule verification incomplete: {detail}")
    if verification["timezone"] != "Asia/Taipei":
        raise JobError("Schedule verification timezone must be Asia/Taipei")
    verified_at = _parse_instant(verification["verified_at"])
    if verified_at is None or verified_at.utcoffset() is None:
        raise JobError("Schedule verification verified_at must include timezone")
    if (
        verification["window_start"] != precheck.get("window_start")
        or verification["window_end"] != precheck.get("window_end")
    ):
        raise JobError("Schedule verification window disagrees with precheck")
    if not isinstance(verification["conflicts"], list) or verification["conflicts"]:
        raise JobError("Complete schedule verification must have no conflicts")

    sources = verification["sources"]
    if not isinstance(sources, list):
        raise JobError("Schedule verification sources must be a list")
    source_roles: dict[str, str] = {}
    source_hosts: dict[str, set[str]] = {"official": set(), "independent": set()}
    for index, source in enumerate(sources, 1):
        if not isinstance(source, dict):
            raise JobError(f"Schedule source {index} must be an object")
        role = source.get("role")
        url = source.get("url")
        checked_at = _parse_instant(source.get("checked_at"))
        if (
            role not in source_hosts
            or not isinstance(url, str)
            or checked_at is None
            or checked_at.utcoffset() is None
        ):
            raise JobError(
                f"Schedule source {index} requires role, URL and checked_at"
            )
        if abs(verified_at - checked_at) > timedelta(hours=6):
            raise JobError(f"Schedule source {index} is stale")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise JobError(f"Schedule source {index} has invalid URL")
        source_roles[url] = str(role)
        source_hosts[str(role)].add(parsed.hostname.lower())
    if not source_hosts["official"] or not source_hosts["independent"]:
        raise JobError(
            "Schedule verification requires official and independent sources"
        )
    if source_hosts["official"] & source_hosts["independent"]:
        raise JobError(
            "Official and independent schedule sources must use different hosts"
        )

    candidate_ids = {
        item.get("match_id")
        for item in precheck.get("matches", [])
        if isinstance(item, dict) and isinstance(item.get("match_id"), int)
    }
    declared_candidate_ids = verification["candidate_match_ids"]
    if (
        not isinstance(declared_candidate_ids, list)
        or any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in declared_candidate_ids
        )
        or set(declared_candidate_ids) != candidate_ids
    ):
        raise JobError("Schedule verification candidate IDs disagree with precheck")

    matches = verification["matches"]
    if not isinstance(matches, list):
        raise JobError("Schedule verification matches must be a list")
    start = _parse_instant(precheck.get("window_start"))
    end = _parse_instant(precheck.get("window_end"))
    if (
        start is None
        or end is None
        or start.utcoffset() is None
        or end.utcoffset() is None
    ):
        raise JobError("Precheck has invalid forecast window")
    verified_ids: set[int] = set()
    match_required = {
        "match_id", "start_time", "tier", "bo_type", "team1", "team2",
        "tournament", "source_urls",
    }
    for index, match in enumerate(matches, 1):
        if not isinstance(match, dict) or match_required - match.keys():
            raise JobError(f"Verified match {index} is missing required fields")
        match_id = match["match_id"]
        instant = _parse_instant(match["start_time"])
        bo_type = match["bo_type"]
        if (
            isinstance(match_id, bool)
            or not isinstance(match_id, int)
            or match_id in verified_ids
        ):
            raise JobError(f"Verified match {index} has invalid or duplicate ID")
        if (
            instant is None
            or instant.utcoffset() is None
            or not start <= instant.astimezone(TAIPEI) < end
        ):
            raise JobError(f"Verified match {match_id} is outside forecast window")
        if str(match["tier"]).lower() != "s" or bo_type not in SCORE_KEYS:
            raise JobError(f"Verified match {match_id} has invalid tier or BO")
        if any(
            not isinstance(match[field], str) or not str(match[field]).strip()
            for field in ("team1", "team2", "tournament")
        ):
            raise JobError(f"Verified match {match_id} has incomplete names")
        refs = match["source_urls"]
        if not isinstance(refs, list):
            raise JobError(f"Verified match {match_id} source_urls must be a list")
        roles = {source_roles.get(ref) for ref in refs}
        if not {"official", "independent"} <= roles:
            raise JobError(
                f"Verified match {match_id} lacks official and independent support"
            )
        verified_ids.add(match_id)

    no_matches = verification["no_matches"]
    if not isinstance(no_matches, bool) or no_matches != (not verified_ids):
        raise JobError("Schedule verification no_matches is inconsistent")
    for field, expected in (
        ("added_match_ids", verified_ids - candidate_ids),
        ("removed_match_ids", candidate_ids - verified_ids),
    ):
        values = verification[field]
        if (
            not isinstance(values, list)
            or any(
                isinstance(value, bool) or not isinstance(value, int)
                for value in values
            )
            or set(values) != expected
        ):
            raise JobError(f"Schedule verification {field} is inconsistent")
    return verification


def validate_forecast_schedule(
    forecasts_path: Path, verification: dict[str, object]
) -> None:
    forecast_ids = {
        record.get("match_id")
        for record in load_jsonl(forecasts_path)
        if isinstance(record.get("match_id"), int)
    }
    verified_ids = {
        match.get("match_id")
        for match in verification.get("matches", [])
        if isinstance(match, dict) and isinstance(match.get("match_id"), int)
    }
    if forecast_ids != verified_ids:
        raise JobError(
            "Forecast match IDs must exactly equal the verified schedule"
        )


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
    verification = validate_schedule_verification(
        output_dir / "schedule-verification.json",
        output_dir / "schedule-precheck.json",
    )
    if verification["no_matches"] is True:
        raise JobError("Cannot publish a no-match schedule")
    assert_nonempty(output_dir / "prediction.md")
    assert_nonempty(output_dir / "forecasts.jsonl")
    assert_nonempty(output_dir / "probability-checks.json")
    validate_forecasts(output_dir / "forecasts.jsonl")
    validate_forecast_schedule(output_dir / "forecasts.jsonl", verification)
    validate_notion_summary(output_dir / "notion-summary.json")
    run(["node", "shared/validate_probabilities.mjs", str(output_dir / "probability-checks.json")])
    notion_url = publish_to_notion(output_dir)
    notify_by_email(output_dir, target, notion_url)
    write_status(
        output_dir,
        "prediction",
        "complete",
        target_date=target,
        notion_url=notion_url,
        email_notified=True,
        schedule_verified=True,
        verified_match_count=len(verification["matches"]),
        added_match_ids=verification["added_match_ids"],
        removed_match_ids=verification["removed_match_ids"],
    )
    return notion_url


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="覆寫台灣時間目標日期（YYYY-MM-DD）")
    parser.add_argument("--force", action="store_true", help="相容舊呼叫；排程現在預設就會重跑")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cleanup_old_reports(days=30, dry_run=args.dry_run)
    target = safe_date(args.date or target_date())
    output_dir = STATE_ROOT / "predictions" / target
    try:
        with job_lock("prediction"):
            if args.dry_run:
                print(prompt_for(target, output_dir))
                return 0
            if recreate_dated_output_dir(output_dir, STATE_ROOT / "predictions"):
                print(f"[reset] Removed existing prediction directory: {output_dir}", flush=True)
            schedule = fetch_schedule(target)
            matches = schedule.matches
            window_start, window_end = forecast_window(target)
            atomic_json(
                output_dir / "bo3-filtered-response.json",
                schedule.filtered_payload,
            )
            atomic_json(
                output_dir / "bo3-unfiltered-response.json",
                schedule.unfiltered_payload,
            )
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
                "server_filtered_match_ids": schedule.filtered_match_ids,
                "client_filtered_match_ids": schedule.client_filtered_match_ids,
                "bo3_filter_consistent": (
                    set(schedule.filtered_match_ids)
                    == set(schedule.client_filtered_match_ids)
                ),
                "matches": [compact_match(match) for match in matches],
            }
            atomic_json(output_dir / "schedule-precheck.json", snapshot)
            write_status(output_dir, "prediction", "running", target_date=target)
            run(codex_command(REPO_ROOT, output_dir / "agent-last-message.md", prompt_for(target, output_dir)))
            verification = validate_schedule_verification(
                output_dir / "schedule-verification.json",
                output_dir / "schedule-precheck.json",
            )
            if verification["no_matches"] is True:
                write_status(
                    output_dir,
                    "prediction",
                    "skipped",
                    target_date=target,
                    reason="no LoL S Tier matches after official and independent verification",
                    schedule_verified=True,
                )
                print(
                    f"Prediction skipped; official and independent sources verified "
                    f"no LoL S Tier matches in the {target} {window_start:%H:%M} TW window"
                )
                return 0
            notion_url = finalize_prediction(output_dir, target)
            print(f"Prediction complete: {output_dir / 'prediction.md'}")
            print(f"Notion: {notion_url}")
            return 0
    except Exception as exc:
        return fail(output_dir, "prediction", exc)


if __name__ == "__main__":
    raise SystemExit(main())
