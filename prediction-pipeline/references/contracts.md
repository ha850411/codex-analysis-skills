# 預測管線資料契約

## 標準檔案

| 檔案 | 產生者 | 使用者 | 用途 |
| --- | --- | --- | --- |
| `model-defaults.json` | 使用者 | 模型預檢／管線 | agy 與 Codex 各階段的預選模型；不能跳過確認 |
| `input.json` | 資料收集器／Codex | 管線 | 含來源與完整資料的標準輸入 |
| `model-input.json` | 管線 | 主預測 Codex | 實體移除 `market_data` 的模型輸入 |
| `primary_prediction.json` | 主預測 Codex | agy、最終 Codex | 尚未接觸市場資訊的初始預測 |
| `red_team_review.json` | agy | 最終 Codex | 獨立審查意見，不是替代預測 |
| `final_prediction.json` | 最終 Codex | 驗證器／匯出器 | 已逐項裁決的最終預測 |
| `prediction.json` | 匯出器 | 下游程式 | 含確定性市場計算的驗證結果 |
| `prediction.md` | 匯出器 | 讀者 | 人類可讀報告 |
| `youtube-script.md` | 匯出器 | 主持人 | YouTube 口播腳本 |

所有檔案使用 UTF-8 JSON、ISO 8601 時間、十進位賠率；機率使用 0 到 100 的百分比數字。

`model-defaults.json` 必須符合 `model-defaults.schema.json`，且 `confirmation_required` 永遠為 `true`。提示詞臨時指定的模型優先於設定檔，但每次觸發 agy 紅隊仍要顯示有效模型計畫並等待使用者確認。

## 標準輸入

`input.json` 必須符合 `input.schema.json`。將賽事證據與市場價格分開：

- `model_data.evidence`：用於領域分析的事實。每項 claim 都要有穩定 ID、確認狀態、擷取時間與來源。
- `model_data.data_quality`：0 到 100 的完整度，以及明列的資料缺口與警告。
- `market_data`：選填的市場價格，以 outcome key 對應最終機率。沒有市場資料時使用空陣列。

只要賽事、參賽者、問題或資料截止時間改變，就建立新的 `prediction_id`。大型或敏感的原始回應不要直接塞進標準輸入。

最小範例：

```json
{
  "schema_version": "1.0",
  "prediction_id": "lol-lck-t1-geng-2026-07-17",
  "created_at": "2026-07-17T09:00:00+08:00",
  "as_of": "2026-07-17T09:00:00+08:00",
  "sport": "League of Legends",
  "mode": "full",
  "question": "T1 對 Gen.G 的系列賽結果為何？",
  "event": {
    "event_id": "lck-2026-t1-geng-0717",
    "competition": "LCK",
    "start_time": "2026-07-17T17:00:00+08:00",
    "timezone": "Asia/Taipei",
    "format": "BO3",
    "participants": ["T1", "Gen.G"]
  },
  "model_data": {
    "data_quality": {
      "completeness": 80,
      "missing": ["已確認先發"],
      "warnings": []
    },
    "evidence": [{
      "id": "e1",
      "category": "roster",
      "claim": "雙方公告名單皆未變動。",
      "status": "confirmed",
      "source": {
        "title": "官方名單頁",
        "url": "https://example.com/rosters",
        "published_at": null,
        "retrieved_at": "2026-07-17T08:55:00+08:00"
      }
    }],
    "notes": []
  },
  "market_data": []
}
```

## 機率群組

每個 `probability_groups` 項目都必須是互斥且完備的分布。同一份預測內的 outcome `key` 不可重複，因為市場價格會用它對應機率。

範例：

- 勝負：`team_a`、`draw`、`team_b`
- BO3 精確比分：`a_2_0`、`a_2_1`、`b_2_1`、`b_2_0`
- 可能走盤的大小分：`over`、`push`、`under`

匯出器會拒絕合計超出 `100 ± 0.2` 的群組，並確定性計算：

```text
公允賠率 = 100 / 模型機率百分比
EV = 市場十進位賠率 × 模型機率百分比 / 100 - 1
```

不得讓模型覆寫這些計算結果。

## 紅隊嚴重度與裁決

- `critical`：預測無效，例如賽事或對手錯誤、已證實市場資訊洩漏。
- `high`：很可能實質改變主要機率或信心度。
- `medium`：可能影響解讀的重要限制。
- `low`：措辭、追溯性或輕微精度問題。

最終結果必須列出接受與否決的 finding ID。每個 `critical` 和 `high` finding 必須且只能出現在其中一邊。接受 finding 並修改數字時，還要在 `changes` 記錄修改前後值與理由。

## 退出碼與修復方式

- `0`：成功。
- `2`：指令用法錯誤或缺少檔案。
- `3`：JSON、Schema 或語意驗證失敗。
- `4`：外部 CLI 失敗、逾時或回傳非 JSON。

驗證失敗時，修復產生錯誤的階段並重新產生所有下游檔案。不要只手動修改衍生的 `prediction.json`。
