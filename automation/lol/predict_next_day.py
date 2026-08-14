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
from datetime import date as date_type, datetime, timedelta, timezone
from pathlib import Path

AUTOMATION_DIR = Path(__file__).resolve().parents[1]
if str(AUTOMATION_DIR) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_DIR))
os.environ["AUTOMATION_MODULE"] = "lol"

from common import (
    REPO_ROOT, STATE_ROOT, TAIPEI, JobError, atomic_json, assert_nonempty,
    cleanup_old_reports, codex_command, codex_timeout_seconds, fail, job_lock, load_jsonl,
    recreate_dated_output_dir, run, send_email, target_date, write_status,
)
from config import ConfigError, module_schedule_time


SOURCE_URL = "https://bo3.gg/lol/matches/current?tiers=s"
API_URL = "https://api.bo3.gg/api/v1/matches"
RIOT_SCHEDULE_URL = (
    "https://lolesports.com/en-SG/leagues/lck%2Clcp%2Clcs%2Clec%2Clpl"
)
SCORE_KEYS = {
    1: {"1-0", "0-1"},
    3: {"2-0", "2-1", "1-2", "0-2"},
    5: {"3-0", "3-1", "3-2", "2-3", "1-3", "0-3"},
}
CONFIDENCE_COMPONENT_WEIGHTS = {
    "data_completeness": 0.25,
    "freshness": 0.20,
    "lineup_certainty": 0.25,
    "regime_relevance": 0.20,
    "model_stability": 0.10,
}
BO3_MATCH_KEY = re.compile(r"bo3:([1-9]\d*)\Z")
CANONICAL_MATCH_KEY = re.compile(
    r"lol:[a-z0-9-]+:\d{8}T\d{4}\+0800:[a-z0-9-]+:[a-z0-9-]+\Z"
)
RIOT_EVENT_PATTERN = re.compile(
    r'\{"__typename":"EventMatch","id":"(?P<id>\d+)",'
    r'"blockName":"(?P<block>[^"]*)","startTime":"(?P<start>[^"]+)"'
    r'.{0,2500}?"league":\{.{0,1000}?"name":"(?P<league>[^"]+)"'
    r'.{0,1000}?\},"tournament":\{.{0,500}?"name":"(?P<tournament>[^"]+)"'
    r'\},"matchTeams":\[\{.{0,1000}?"name":"(?P<team1>[^"]+)"'
    r'.{0,1500}?\},\{.{0,1000}?"name":"(?P<team2>[^"]+)"',
    re.DOTALL,
)


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


def _valid_match_key(value: object) -> bool:
    return isinstance(value, str) and bool(
        BO3_MATCH_KEY.fullmatch(value) or CANONICAL_MATCH_KEY.fullmatch(value)
    )


def _round_probability_percent(value: float) -> int:
    """用與 JavaScript Math.round 相同的非負百分比四捨五入。"""
    return int(value * 100 + 0.5)


def _round_confidence(value: float) -> float:
    return _round_probability_percent(value) / 100


def _is_valid_global_schedule_url(url: str) -> bool:
    """拒絕把單一 LoL Esports 聯賽頁誤標成全域覆蓋。"""
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    path = urllib.parse.unquote(parsed.path)
    if host == "lolesports.com" or host.endswith(".lolesports.com"):
        marker = "/leagues/"
        if marker in path:
            selected = path.split(marker, 1)[1].strip("/")
            return len([item for item in selected.split(",") if item]) >= 2
    return True


def _is_bo3_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    return host == "bo3.gg" or host.endswith(".bo3.gg")


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
        # bo3.gg compares offset-bearing timestamps by their displayed clock time
        # instead of normalizing the offset first. Always send UTC boundaries so
        # early UTC matches inside the Taipei window are not silently excluded.
        "filter[matches.start_date][gt]": (
            start - timedelta(seconds=1)
        ).astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "filter[matches.start_date][lt]": (
            end.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        ),
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


def extract_riot_schedule(html: str, target: str) -> dict[str, object]:
    """從 Riot 伺服器渲染頁的事件 JSON 擷取視窗內官方賽程。

    不解析頁面上的 Today／Tomorrow 或本地化日期標題；那些標題會依渲染
    時區變動，曾導致隔日配對被錯套到當日。事件的 UTC startTime 才是邊界
    判斷依據。
    """
    start, end = forecast_window(target)
    parsed_event_ids: set[str] = set()
    matches: list[dict[str, object]] = []
    for found in RIOT_EVENT_PATTERN.finditer(html):
        event = found.groupdict()
        event_id = event["id"]
        if event_id in parsed_event_ids:
            continue
        parsed_event_ids.add(event_id)
        instant = _parse_instant(event["start"])
        if (
            instant is None
            or instant.utcoffset() is None
            or not start <= instant.astimezone(TAIPEI) < end
        ):
            continue
        matches.append(
            {
                "official_event_id": event_id,
                "start_time": instant.astimezone(TAIPEI).isoformat(),
                "start_time_utc": instant.astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "league": event["league"],
                "tournament": event["tournament"],
                "block": event["block"],
                "team1": event["team1"],
                "team2": event["team2"],
            }
        )
    if not parsed_event_ids:
        raise JobError(
            "Riot schedule page no longer contains recognizable embedded EventMatch data"
        )
    matches.sort(key=lambda item: str(item["start_time"]))
    return {
        "schema_version": "1.0",
        "source": RIOT_SCHEDULE_URL,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "window_boundary": "start-inclusive/end-exclusive",
        "parser": "riot-server-rendered-embedded-event-json",
        "parsed_event_count": len(parsed_event_ids),
        "match_count": len(matches),
        "matches": matches,
    }


def fetch_riot_schedule(target: str) -> dict[str, object]:
    """擷取 Riot 多賽區官方頁並保存可稽核的精確事件時間與配對。"""
    request = urllib.request.Request(
        RIOT_SCHEDULE_URL,
        headers={
            "Accept": "text/html",
            "User-Agent": "codex-lol-automation/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            html = response.read().decode("utf-8")
    except (OSError, urllib.error.URLError, UnicodeDecodeError) as exc:
        raise JobError(f"Riot official schedule precheck failed: {exc}") from exc
    result = extract_riot_schedule(html, target)
    result["checked_at"] = datetime.now(TAIPEI).isoformat()
    return result


def compact_match(record: dict[str, object]) -> dict[str, object]:
    bets = record.get("bet_updates") if isinstance(record.get("bet_updates"), dict) else {}
    team1 = bets.get("team_1") if isinstance(bets.get("team_1"), dict) else {}
    team2 = bets.get("team_2") if isinstance(bets.get("team_2"), dict) else {}
    slug = str(record.get("slug", ""))
    match_id = record.get("id")
    return {
        "match_key": f"bo3:{match_id}" if isinstance(match_id, int) else None,
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
- Riot 多賽區官方事件預查：{output_dir / 'riot-schedule-precheck.json'}
- 歷史因子登錄檔：{STATE_ROOT / 'history/factor-registry.json'}（若存在）

要求：
1. bo3.gg 只作候選與 provider Match ID，不得標成官方來源。必須另外取得：
   (a) 涵蓋整個視窗與所有 S-Tier 賽區的 Riot／LoL Esports 全域或多賽區官方賽程；
   (b) Leaguepedia／Liquipedia／OP.GG Esports 的獨立全域賽程，或由逐聯賽獨立頁面
   組成的 coverage group。聯賽專頁只能貢獻該聯賽子集合，不能單獨證明跨賽區完整；
   獨立 coverage group 的 match_keys 聯集必須等於官方全域集合，否則停止。
   bo3.gg 不得出現在 coverage_sources，也不得作為 matches.source_urls
   的獨立賽程證明；其原始回應只保存在候選 precheck artifacts。
   Leaguepedia、Liquipedia、OP.GG 或其他不同營運方記為
   role="independent"；只有 Riot／賽區主辦方記為 role="official"。
   `riot-schedule-precheck.json` 是直接從上述 Riot 多賽區官方頁的伺服器渲染
   EventMatch JSON 確定性擷取；其 `start_time_utc`／`start_time` 與同一事件的
   team1/team2 是官方頁的原始綁定，必須作為官方集合的基礎。禁止改用頁面上的
   Today／Tomorrow／星期幾等相對標題重新配對，也禁止把視窗外下一日的隊伍套到
   視窗內同一開賽時刻。若它與 bo3.gg 候選及另一個當前獨立來源一致，不得只因
   相鄰日期區塊還列有其他隊伍就宣告衝突；仍須查核是否有官方預查未涵蓋的賽區。
2. 建立 {output_dir / 'schedule-verification.json'}，至少包含：
   verified_at, timezone="Asia/Taipei", window_start, window_end,
   complete, no_matches, candidate_match_keys, added_match_keys,
   removed_match_keys, conflicts, coverage_sources, sources, matches。
   coverage_sources 必須至少有一筆 role="official"、scope="global-s-tier"，
   match_keys 等於完整集合。獨立側可有一筆 scope="global-s-tier"，或多筆
   scope="competition-s-tier" 且各自另含 competition；每筆包含 url, checked_at,
   match_keys。每個 competition 子集合可只含該聯賽，但同一 role 的 match_keys
   聯集必須等於最終 matches 完整集合。no_matches=true 時，官方與獨立側都必須各有
   scope="global-s-tier" 的空集合，不能用聯賽頁拼接證明無賽事。
   sources 每筆包含 role="official" 或 role="independent"、url、checked_at；
   matches 每筆包含 match_key, bo3_match_id, start_time, tier="s", bo_type,
   team1, team2, tournament, source_urls。每場 source_urls 內用來證明 official 與
   independent 支持的 URL，必須逐字登錄在頂層 sources，且角色一致；coverage_sources
   不能代替頂層 sources 的逐場來源索引。
   有 bo3.gg ID 時 match_key=`bo3:<id>` 且 bo3_match_id 為該整數；bo3.gg 缺場時，
   match_key 使用
   `lol:<league-slug>:<YYYYMMDDTHHMM+0800>:<team1-slug>:<team2-slug>`，
   bo3_match_id=null。slug 只用小寫英數與連字號，必須由已確認資料確定性產生。
3. 完整集合須至少由一個當前官方來源與一個當前獨立來源支持。發現候選外賽事時補入，
   候選誤列時移除並說明。若 Liquipedia／Leaguepedia 的舊頁面與較新的 Riot 官方賽程
   衝突，依 source-priority 契約採用較新且更接近當場的 Riot 資訊；再以另一個當前獨立
   來源交叉確認。不得要求每一個第三方 wiki 都一致，也不得讓已確認過期的 wiki 單獨
   阻擋流程。被較新官方資訊消解的差異要記錄來源與裁決，但不是未解 conflicts。
   當前官方全域集合與獨立 coverage group 聯集相同且沒有未解衝突時寫
   complete=true。無賽事也須雙來源確認。
4. 只有來源不一致且依上述優先序仍無法消解，或仍有未解場次時，才寫 complete=false
   與 conflicts 後停止；不要建立預測、Notion summary 或可發布報告。外層會以失敗狀態
   停止發布與寄信。
5. 通過賽程驗證後，`schedule-verification.json` 的 matches 才是唯一預測集合。不得加入 A/B/C Tier或視窗外賽事，並在 prediction.md 揭露官方全域集合、獨立 coverage group 各子集合與聯集、候選／新增／移除場次及驗證來源。
6. 查核賽制、名單、版本、近期樣本、BP/英雄池與可用 VOD。因子登錄檔存在時，只讓 status=active 且 used_for_prediction=true 的項目影響機率；candidate 只可作 shadow 記錄，retired 不得再抓取、判斷、報告或影響機率。若 retired 的 revisit_trigger 明確成立，只記錄供下次 postmortem 驗證，不得在本次自行恢復。先鎖模型機率，再依 `shared/markets/collection-contract.md` 逐場執行 `shared/markets/collect_odds_api.mjs --sport esports`。每場傳入獨立 `--output`、`--error-output` 與 `--events-output`；event 名稱無法唯一解析時讀 pending event artifact，確認後以 `--event-id` 重跑。不得因一場或第一次網路錯誤跳過其餘場次，也不得在沒有當次錯誤 artifact 時寫「API 無法擷取」。缺價格不改寫模型機率或信心度。
7. 建立 {output_dir / 'market-collection.json'}，至少包含 schema_version、generated_at、attempts；attempts 必須逐場且與已驗證 match_key 一一對應，每筆包含 match_key、status=`success|failed`、artifact（{output_dir} 內的相對路徑）。success artifact 必須是收集器的 `status=success` 快照；failed artifact 必須是收集器的 `status=failed` 分類錯誤憑證。只有每場都有 artifact 才算完成市場收集。
8. 只准寫入 {output_dir}，不得修改 skill、shared 或其他 repo 檔案。排程已在啟動前清除該日期的舊輸出。若 no_matches=true，只建立 schedule-verification.json；否則必須建立本次 prediction.md、forecasts.jsonl、probability-checks.json、market-collection.json 與 notion-summary.json。
9. 寫入 {output_dir / 'prediction.md'}，符合 skill 契約，全文最後只有一個「簡表總結」。
10. 寫入 {output_dir / 'forecasts.jsonl'}，每場一行 JSON object，至少包含：
   match_key, bo3_match_id, predicted_at, start_time, snapshot, model_version, team1, team2,
   tournament, tier="s", bo_type, exact_score_probabilities, team1_win_prob,
   team2_win_prob, team1_at_least_one_prob, team2_at_least_one_prob,
   both_at_least_one_prob, model_confidence, confidence_components,
   fragility_triggers, sources。所有機率均用 0..1。confidence_components 必須包含
   data_completeness, freshness, lineup_certainty, regime_relevance,
   model_stability, raw_weighted, final_after_non_compensatory_cap。
11. BO3 精確比分鍵必須為 2-0/2-1/1-2/0-2；BO5 為 3-0/3-1/3-2/2-3/1-3/0-3；總和為 1。系列勝率必須等於對應精確比分總和，各自／雙方至少一局都從同一分布推導。model_confidence 必須等於 final_after_non_compensatory_cap；fragility_triggers 非空時，套用 LoL 非補償式上限，空陣列時最終值等於 raw_weighted。
12. 將上述檢查以百分比寫入 {output_dir / 'probability-checks.json'}。每場 weighted_confidence 檢查必須帶 match_key、rawWeighted、applyNonCompensatoryCap 與 fragilityTriggers；value 使用上限後最終值，不得改驗證 raw weighted。執行
   `node shared/validate_probabilities.mjs {output_dir / 'probability-checks.json'}`。
13. 依 {REPO_ROOT / 'shared/notion/skill-instructions.md'} 寫入 {output_dir / 'notion-summary.json'}；使用 sport="LoL", module="lol-analysis", analysisType="daily-summary"，startTime 帶 +08:00。
14. 只建立本地 Notion summary；外層程式驗證賽程、機率與逐場市場 artifact 後才會發布並寄 Email。最後確認所有檔案確實存在。
"""


def validate_forecasts(path: Path) -> None:
    required = {
        "match_key", "bo3_match_id", "predicted_at", "start_time", "snapshot", "model_version",
        "team1", "team2", "tournament", "tier", "bo_type",
        "exact_score_probabilities", "team1_win_prob", "team2_win_prob",
        "team1_at_least_one_prob", "team2_at_least_one_prob",
        "both_at_least_one_prob", "model_confidence", "confidence_components",
        "fragility_triggers", "sources",
    }
    seen_match_keys: set[str] = set()
    for index, record in enumerate(load_jsonl(path), 1):
        missing = sorted(required - record.keys())
        if missing:
            raise JobError(f"forecasts.jsonl record {index} missing: {', '.join(missing)}")
        match_key = record["match_key"]
        bo3_match_id = record["bo3_match_id"]
        if (
            not _valid_match_key(match_key)
            or match_key in seen_match_keys
        ):
            raise JobError(
                f"forecasts.jsonl record {index}: match_key must be unique and valid"
            )
        bo3_key = BO3_MATCH_KEY.fullmatch(match_key)
        if (
            (bo3_key and bo3_match_id != int(bo3_key.group(1)))
            or (
                not bo3_key
                and bo3_match_id is not None
            )
        ):
            raise JobError(
                f"forecasts.jsonl record {index}: bo3_match_id disagrees with match_key"
            )
        seen_match_keys.add(match_key)
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
        for field in (
            "team1_win_prob", "team2_win_prob", "team1_at_least_one_prob",
            "team2_at_least_one_prob", "both_at_least_one_prob",
            "model_confidence",
        ):
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
        both_at_least_one = 1 - t1_swept - t2_swept
        if abs(record["both_at_least_one_prob"] - both_at_least_one) > 0.002:
            raise JobError(
                f"forecasts.jsonl record {index}: both-at-least-one probability is inconsistent"
            )
        components = record["confidence_components"]
        component_fields = {
            *CONFIDENCE_COMPONENT_WEIGHTS,
            "raw_weighted",
            "final_after_non_compensatory_cap",
        }
        if not isinstance(components, dict) or component_fields - components.keys():
            raise JobError(
                f"forecasts.jsonl record {index}: confidence_components are incomplete"
            )
        if any(
            isinstance(components[field], bool)
            or not isinstance(components[field], (int, float))
            or not 0 <= components[field] <= 1
            for field in component_fields
        ):
            raise JobError(
                f"forecasts.jsonl record {index}: confidence components must be 0..1"
            )
        raw_weighted = _round_confidence(sum(
            components[field] * weight
            for field, weight in CONFIDENCE_COMPONENT_WEIGHTS.items()
        ))
        if abs(components["raw_weighted"] - raw_weighted) > 0.0001:
            raise JobError(
                f"forecasts.jsonl record {index}: raw weighted confidence is inconsistent"
            )
        triggers = record["fragility_triggers"]
        if (
            not isinstance(triggers, list)
            or any(not isinstance(value, str) or not value.strip() for value in triggers)
        ):
            raise JobError(
                f"forecasts.jsonl record {index}: fragility_triggers must be a string list"
            )
        expected_final = raw_weighted
        if triggers:
            expected_final = min(
                raw_weighted,
                components["data_completeness"],
                components["regime_relevance"],
                components["model_stability"] + 0.10,
            )
            expected_final = _round_confidence(expected_final)
        final_confidence = components["final_after_non_compensatory_cap"]
        if (
            abs(final_confidence - expected_final) > 0.0001
            or abs(record["model_confidence"] - final_confidence) > 0.0001
        ):
            raise JobError(
                f"forecasts.jsonl record {index}: final confidence does not apply the LoL cap"
            )


def validate_probability_checks(
    checks_path: Path, forecasts_path: Path
) -> None:
    """確保機率檢查驗證的是對外使用的上限後信心度。"""
    assert_nonempty(checks_path)
    try:
        payload = json.loads(checks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JobError(f"Invalid probability checks JSON: {exc}") from exc
    checks = payload.get("checks") if isinstance(payload, dict) else None
    if not isinstance(checks, list):
        raise JobError("probability-checks.json must contain checks")
    forecasts = {
        record["match_key"]: record for record in load_jsonl(forecasts_path)
    }
    confidence_checks: dict[str, dict[str, object]] = {}
    for check in checks:
        if not isinstance(check, dict) or check.get("type") != "weighted_confidence":
            continue
        match_key = check.get("match_key")
        if match_key not in forecasts or match_key in confidence_checks:
            raise JobError(
                "weighted confidence checks require a unique forecast match_key"
            )
        confidence_checks[str(match_key)] = check
    if set(confidence_checks) != set(forecasts):
        raise JobError(
            "weighted confidence checks must cover every forecast exactly once"
        )
    component_names = {
        "dataCompleteness": "data_completeness",
        "freshness": "freshness",
        "lineupCertainty": "lineup_certainty",
        "regimeRelevance": "regime_relevance",
        "modelStability": "model_stability",
    }
    for match_key, forecast in forecasts.items():
        check = confidence_checks[match_key]
        components = forecast["confidence_components"]
        expected_components = {
            public: _round_probability_percent(float(components[stored]))
            for public, stored in component_names.items()
        }
        expected_triggers = forecast["fragility_triggers"]
        if (
            check.get("value")
            != _round_probability_percent(float(forecast["model_confidence"]))
            or check.get("components") != expected_components
            or check.get("rawWeighted")
            != _round_probability_percent(float(components["raw_weighted"]))
            or check.get("applyNonCompensatoryCap") != bool(expected_triggers)
            or check.get("fragilityTriggers") != expected_triggers
        ):
            raise JobError(
                f"probability-checks.json confidence disagrees with forecast {match_key}"
            )


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
        "no_matches", "candidate_match_keys", "added_match_keys",
        "removed_match_keys", "conflicts", "coverage_sources", "sources", "matches",
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
        if _is_bo3_url(url):
            raise JobError(
                f"Schedule source {index}: bo3.gg is candidate-only and cannot prove coverage"
            )
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

    candidate_keys = {
        item.get("match_key")
        for item in precheck.get("matches", [])
        if isinstance(item, dict) and _valid_match_key(item.get("match_key"))
    }
    declared_candidate_keys = verification["candidate_match_keys"]
    if (
        not isinstance(declared_candidate_keys, list)
        or any(
            not _valid_match_key(value)
            for value in declared_candidate_keys
        )
        or set(declared_candidate_keys) != candidate_keys
    ):
        raise JobError("Schedule verification candidate match keys disagree with precheck")

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
    verified_keys: set[str] = set()
    match_required = {
        "match_key", "bo3_match_id", "start_time", "tier", "bo_type", "team1", "team2",
        "tournament", "source_urls",
    }
    for index, match in enumerate(matches, 1):
        if not isinstance(match, dict) or match_required - match.keys():
            raise JobError(f"Verified match {index} is missing required fields")
        match_key = match["match_key"]
        bo3_match_id = match["bo3_match_id"]
        instant = _parse_instant(match["start_time"])
        bo_type = match["bo_type"]
        if (
            not _valid_match_key(match_key)
            or match_key in verified_keys
        ):
            raise JobError(f"Verified match {index} has invalid or duplicate match key")
        bo3_key = BO3_MATCH_KEY.fullmatch(match_key)
        if (
            (bo3_key and bo3_match_id != int(bo3_key.group(1)))
            or (not bo3_key and bo3_match_id is not None)
        ):
            raise JobError(
                f"Verified match {match_key} has inconsistent bo3_match_id"
            )
        if (
            instant is None
            or instant.utcoffset() is None
            or not start <= instant.astimezone(TAIPEI) < end
        ):
            raise JobError(f"Verified match {match_key} is outside forecast window")
        if str(match["tier"]).lower() != "s" or bo_type not in SCORE_KEYS:
            raise JobError(f"Verified match {match_key} has invalid tier or BO")
        if any(
            not isinstance(match[field], str) or not str(match[field]).strip()
            for field in ("team1", "team2", "tournament")
        ):
            raise JobError(f"Verified match {match_key} has incomplete names")
        refs = match["source_urls"]
        if not isinstance(refs, list):
            raise JobError(f"Verified match {match_key} source_urls must be a list")
        roles = {source_roles.get(ref) for ref in refs}
        if not {"official", "independent"} <= roles:
            raise JobError(
                f"Verified match {match_key} lacks official and independent support"
            )
        verified_keys.add(match_key)

    no_matches = verification["no_matches"]
    if not isinstance(no_matches, bool) or no_matches != (not verified_keys):
        raise JobError("Schedule verification no_matches is inconsistent")

    coverage_sources = verification["coverage_sources"]
    if not isinstance(coverage_sources, list):
        raise JobError("Schedule verification coverage_sources must be a list")
    coverage_roles: set[str] = set()
    coverage_hosts: dict[str, set[str]] = {"official": set(), "independent": set()}
    coverage_unions: dict[str, set[str]] = {
        "official": set(),
        "independent": set(),
    }
    global_roles: set[str] = set()
    for index, source in enumerate(coverage_sources, 1):
        if not isinstance(source, dict):
            raise JobError(f"Coverage source {index} must be an object")
        role = source.get("role")
        url = source.get("url")
        checked_at = _parse_instant(source.get("checked_at"))
        match_keys = source.get("match_keys")
        scope = source.get("scope")
        source_keys = set(match_keys) if isinstance(match_keys, list) else set()
        if (
            role not in coverage_hosts
            or scope not in {"global-s-tier", "competition-s-tier"}
            or not isinstance(url, str)
            or checked_at is None
            or checked_at.utcoffset() is None
            or not isinstance(match_keys, list)
            or any(not _valid_match_key(value) for value in match_keys)
            or not source_keys <= verified_keys
            or (
                scope == "competition-s-tier"
                and (
                    not isinstance(source.get("competition"), str)
                    or not source["competition"].strip()
                )
            )
            or (scope == "global-s-tier" and source_keys != verified_keys)
            or (
                scope == "global-s-tier"
                and not _is_valid_global_schedule_url(url)
            )
            or source_roles.get(url) != role
        ):
            raise JobError(
                f"Coverage source {index} has invalid scope or match-key coverage"
            )
        if abs(verified_at - checked_at) > timedelta(hours=6):
            raise JobError(f"Coverage source {index} is stale")
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise JobError(f"Coverage source {index} has invalid URL")
        coverage_roles.add(str(role))
        coverage_hosts[str(role)].add(parsed.hostname.lower())
        coverage_unions[str(role)].update(source_keys)
        if scope == "global-s-tier":
            global_roles.add(str(role))
    if coverage_roles != {"official", "independent"}:
        raise JobError(
            "Schedule verification requires official and independent global coverage"
        )
    if coverage_hosts["official"] & coverage_hosts["independent"]:
        raise JobError(
            "Official and independent global coverage must use different hosts"
        )
    if coverage_unions["official"] != verified_keys or coverage_unions["independent"] != verified_keys:
        raise JobError(
            "Official coverage and independent coverage union must equal the verified schedule"
        )
    required_global_roles = (
        {"official", "independent"} if not verified_keys else {"official"}
    )
    if not required_global_roles <= global_roles:
        raise JobError(
            "Schedule coverage lacks the required global source role"
        )

    for field, expected in (
        ("added_match_keys", verified_keys - candidate_keys),
        ("removed_match_keys", candidate_keys - verified_keys),
    ):
        values = verification[field]
        if (
            not isinstance(values, list)
            or any(not _valid_match_key(value) for value in values)
            or set(values) != expected
        ):
            raise JobError(f"Schedule verification {field} is inconsistent")
    return verification


def validate_forecast_schedule(
    forecasts_path: Path, verification: dict[str, object]
) -> None:
    forecast_keys = {
        record.get("match_key")
        for record in load_jsonl(forecasts_path)
        if _valid_match_key(record.get("match_key"))
    }
    verified_keys = {
        match.get("match_key")
        for match in verification.get("matches", [])
        if isinstance(match, dict) and _valid_match_key(match.get("match_key"))
    }
    if forecast_keys != verified_keys:
        raise JobError(
            "Forecast match keys must exactly equal the verified schedule"
        )


def validate_market_collection(
    path: Path, output_dir: Path, verification: dict[str, object]
) -> dict[str, object]:
    assert_nonempty(path)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise JobError(f"Invalid market collection JSON: {exc}") from exc
    attempts = manifest.get("attempts") if isinstance(manifest, dict) else None
    if (
        not isinstance(manifest, dict)
        or not isinstance(manifest.get("schema_version"), str)
        or not isinstance(manifest.get("generated_at"), str)
        or not isinstance(attempts, list)
    ):
        raise JobError("Market collection manifest is missing required fields")

    verified_keys = {
        match.get("match_key")
        for match in verification.get("matches", [])
        if isinstance(match, dict) and _valid_match_key(match.get("match_key"))
    }
    seen: set[str] = set()
    output_root = output_dir.resolve()
    for index, attempt in enumerate(attempts, 1):
        if not isinstance(attempt, dict):
            raise JobError(f"Market collection attempt {index} must be an object")
        match_key = attempt.get("match_key")
        status = attempt.get("status")
        artifact_name = attempt.get("artifact")
        if (
            not _valid_match_key(match_key)
            or match_key in seen
            or status not in {"success", "failed"}
            or not isinstance(artifact_name, str)
            or not artifact_name.strip()
        ):
            raise JobError(f"Market collection attempt {index} is invalid")
        artifact_path = (output_dir / artifact_name).resolve()
        try:
            artifact_path.relative_to(output_root)
        except ValueError as exc:
            raise JobError(
                f"Market collection artifact for {match_key} escapes output directory"
            ) from exc
        assert_nonempty(artifact_path)
        try:
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise JobError(
                f"Market collection artifact for {match_key} is invalid JSON"
            ) from exc
        if not isinstance(artifact, dict):
            raise JobError(
                f"Market collection artifact for {match_key} must be an object"
            )
        if artifact.get("status") != status:
            raise JobError(
                f"Market collection artifact for {match_key} disagrees with manifest"
            )
        if status == "success":
            if (
                artifact.get("source", {}).get("provider") != "Odds-API.io"
                or artifact.get("event", {}).get("provider_event_id") is None
                or not isinstance(artifact.get("collection"), dict)
            ):
                raise JobError(
                    f"Successful market artifact for {match_key} lacks audit fields"
                )
        else:
            error = artifact.get("error")
            if (
                not isinstance(artifact.get("attempted_at"), str)
                or not isinstance(error, dict)
                or not isinstance(error.get("kind"), str)
                or not error.get("kind")
            ):
                raise JobError(
                    f"Failed market artifact for {match_key} lacks classified error"
                )
        seen.add(match_key)
    if seen != verified_keys:
        raise JobError(
            "Market collection match keys must exactly equal the verified schedule"
        )
    return manifest


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
    validate_probability_checks(
        output_dir / "probability-checks.json", output_dir / "forecasts.jsonl"
    )
    validate_forecast_schedule(output_dir / "forecasts.jsonl", verification)
    validate_market_collection(
        output_dir / "market-collection.json", output_dir, verification
    )
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
        added_match_keys=verification["added_match_keys"],
        removed_match_keys=verification["removed_match_keys"],
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
            riot_schedule = fetch_riot_schedule(target)
            atomic_json(
                output_dir / "riot-schedule-precheck.json",
                riot_schedule,
            )
            write_status(output_dir, "prediction", "running", target_date=target)
            run(
                codex_command(REPO_ROOT, output_dir / "agent-last-message.md", prompt_for(target, output_dir)),
                timeout=codex_timeout_seconds(),
            )
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
