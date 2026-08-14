# Valorant 不可變預測快照

每份含新機率的輸出都先建立一個 JSON 快照，通過驗證後才可送出。快照用於賽後評分，不是市場或 Notion 匯出檔。

## 保存流程

1. 在當次 run 目錄建立 `forecast-snapshot.json`。
2. 只放當時可知的資料；`market_data_visibility` 固定為 `withheld_from_probability_stages`。
3. 執行：

   ```bash
   node valorant-analysis/scripts/record_forecast.mjs <run-dir>/forecast-snapshot.json
   ```

4. 指令會驗證時序、情境權重、逐圖五人、主分布混合與信心度，並以 `wx` 模式保存到 `.automation-state/valorant/history/forecasts/<TW-date>/`。相同 `forecast_id` 不可覆寫；正式名單或 veto 更新時建立新的 ID 與快照。
5. 報告內保留 `forecast_id` 與保存路徑。保存失敗就停止發布並修正上游資料。

## 最小結構

```json
{
  "schema_version": 1,
  "forecast_id": "vct-pac-20260809-vl-prx-post-veto-v1",
  "event_id": "vlr-698914",
  "snapshot": "post-veto",
  "veto_status": "post-veto",
  "created_at": "2026-08-09T14:00:00+08:00",
  "data_cutoff": "2026-08-09T13:55:00+08:00",
  "scheduled_start": "2026-08-09T16:00:00+08:00",
  "model_version": "valorant-model-v1",
  "skill_revision": "git-commit-or-content-hash",
  "format": "BO3",
  "teams": {"a": "VARREL", "b": "Paper Rex"},
  "market_data_visibility": "withheld_from_probability_stages",
  "scenarios": [{
    "id": "regular-veto-map-sub",
    "weight": 100,
    "veto": {
      "bans": ["Breeze", "Haven", "Summit", "Ascent"],
      "map_order": ["Split", "Sunset", "Lotus"],
      "pick_owners": ["a", "b", "decider"]
    },
    "lineups_by_map": {
      "Split": {"a": ["p1", "p2", "p3", "p4", "p5"], "b": ["q1", "q2", "q3", "q4", "q5"]},
      "Sunset": {"a": ["p1", "p2", "p3", "p4", "p6"], "b": ["q1", "q2", "q3", "q4", "q5"]},
      "Lotus": {"a": ["p1", "p2", "p3", "p4", "p6"], "b": ["q1", "q2", "q3", "q4", "q5"]}
    },
    "score_distribution": {"a_2_0": 20, "a_2_1": 25, "b_2_1": 30, "b_2_0": 25}
  }],
  "main_score_distribution": {"a_2_0": 20, "a_2_1": 25, "b_2_1": 30, "b_2_0": 25},
  "model_confidence": {
    "value": 70,
    "components": {
      "dataCompleteness": 75,
      "freshness": 80,
      "lineupCertainty": 60,
      "regimeRelevance": 70,
      "modelStability": 65
    }
  },
  "evidence": [{
    "id": "match-page",
    "url": "https://www.vlr.gg/698914/...",
    "retrieved_at": "2026-08-09T13:55:00+08:00",
    "claim": "賽事身分、預計名單與賽制"
  }]
}
```

`pre-veto` 至少保存兩個加權情境。每個情境必須是完整的 roster × veto 路徑；若整個系列固定同一五人，可用 `lineups_by_map."*"` 代表所有地圖。BO1、BO3、BO5 分別使用 `a_1_0/b_1_0`、四項 BO3、六項 BO5 精確比分分布。

範例只示意欄位，不提供真實機率。正式快照的 `main_score_distribution` 必須等於各情境加權混合，模型信心度必須等於五項加權後的整數值。
