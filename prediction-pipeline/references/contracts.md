# 預測管線資料契約

## 標準檔案

| 檔案 | 產生者 | 使用者 | 用途 |
| --- | --- | --- | --- |
| `model-defaults.json` | 使用者 | 模型告知／管線 | agy 與 Codex 各階段的預選模型；告知後自動執行 |
| `input.json` | 資料收集器／Codex | 管線 | 含來源與完整資料的標準輸入 |
| `model-input.json` | 管線 | 主預測 Codex | 實體移除 `market_data` 的模型輸入 |
| `primary_prediction.json` | 主預測 Codex | agy、最終 Codex | 尚未接觸市場資訊、含完整分析正文的初始預測 |
| `red_team_review.json` | agy | 最終 Codex | 獨立審查意見，不是替代預測 |
| `final_prediction.json` | 最終 Codex | 驗證器／匯出器 | 已逐項裁決的最終預測 |
| `market_comparison.json` | 確定性管線 | post-market Codex | 機率鎖定後的市場價格、公允賠率與 EV 快照 |
| `post_market_decision.json` | post-market Codex | 驗證器／匯出器 | 不改機率的逐盤決策、玩法覆蓋與簡表投注建議 |
| `prediction.json` | 匯出器 | 下游程式 | 含確定性市場計算的驗證結果 |
| `prediction.md` | 匯出器 | 讀者 | 人類可讀報告 |
| `youtube-script.md` | 匯出器 | 主持人 | YouTube 口播腳本 |

所有檔案使用 UTF-8 JSON、ISO 8601 時間、十進位賠率；機率使用 0 到 100 的百分比數字。

`model-defaults.json` 必須符合 `model-defaults.schema.json`，且 `confirmation_required` 永遠為 `false`。`red_team.model` 必須是 `agy models` 的完整模型名稱，並以 `agy --model` 傳入；不得把模型名稱傳給 `--agent`。提示詞臨時指定的模型優先於設定檔；每次觸發 agy 紅隊都要先顯示實際模型計畫，然後直接執行，不等待使用者確認。

## 標準輸入

`input.json` 必須符合 `input.schema.json`。將賽事證據與市場價格分開：

- `model_data.evidence`：用於領域分析的事實。每項 claim 都要有穩定 ID、確認狀態、擷取時間與來源。
- `model_data.data_quality`：0 到 100 的完整度，以及明列的資料缺口與警告。
- `market_data`：選填的市場價格，以 outcome key 對應最終機率。`outcome_key` 代表全贏；整數盤或四分之一盤可另填 `push_outcome_key`、`half_win_outcome_key`、`half_loss_outcome_key`。沒有市場資料時使用空陣列。

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
無走盤 EV = 市場十進位賠率 × 模型機率百分比 / 100 - 1

含結算狀態 EV = Σ[各狀態機率 × 該狀態每 1 單位本金的總返還] - 1
```

全贏總返還為十進位賠率、半贏為 `(賠率 + 1) / 2`、走盤為 `1`、半輸為 `0.5`、全輸為 `0`。不得讓模型覆寫這些計算結果。

`confidence` 必須包含 `data_completeness`、`freshness`、`lineup_certainty`、`regime_relevance`、`model_stability`，並符合共用加權公式。`presentation.summary_table` 的欄位與列數由領域 skill 決定，但必須包含 `模型信心度` 欄且每列欄數一致。

`market_data` 非空時，匯出前必須先產生 `market_comparison.json` 與符合 `post-market.schema.json` 的 `post_market_decision.json`。後者不得包含機率欄位；每個市場 `bet_id` 必須且只能裁決一次，每一列簡表也必須且只能回填一次。市場已取得時，回填建議不得仍寫「待市場價格」或「待即時價格」。只取得部分玩法時，`market_coverage.status` 使用 `partial`，並列出尚未取得的玩法。

`market_data=[]` 不屬驗證失敗。匯出器在沒有可追溯即時價格時跳過 post-market artifact，仍正常輸出模型機率、公允賠率、價格門檻與0u建議；不得因 Stake 無法存取、未開盤或查無價格而中斷整份分析。

`primary_prediction.json.analysis_sections` 是 agy 實際審查的完整主報告；不得只讓主預測輸出 thesis、機率與因子。`final_prediction.json` 的 `presentation.analysis_sections` 是 agy 回饋經 Codex 裁決後的完整可讀報告，不是摘要。它必須依領域 skill 與 `input.mode` 保留仍有效的名單、數據對比、逐圖／逐場分析、veto／draft、校準檢核及情境風險；`presentation.key_points` 只供摘要，不能取代完整章節。每個章節使用唯一 `heading` 與非空白 `markdown`。來源、免責文字與 `簡表總結` 由匯出器統一附加，不得放入章節正文。裁決後正文的非空白字元不得少於主報告的 70%，避免修訂階段把全文壓成簡報式摘要。

agy 每次 stdout 都保存為 `red-team-attempt-<n>-raw.txt`；stderr 非空時另存。解析器必須檢查所有候選 JSON，拒絕 `{}` 或缺少紅隊核心欄位的物件，且正式 `red_team_review.json` 只能在完整 schema 與跨檔驗證通過後原子寫入。第一次失敗可用同一模型做一次契約修復，第二次失敗即停止並保留 `invalid.json` 與 `errors.txt` 診斷檔。

執行 red-team 時必須傳入本次使用的 `--domain-skill <.../SKILL.md>`。管線會將該技能與存在時的 `references/output-template.md` 直接嵌入 agy 的可信審查契約；因此 `domain_report_coverage` 不是只依通用印象檢查，而是能核對各運動的實際必要欄位。

## 紅隊嚴重度與裁決

- `critical`：預測無效，例如賽事或對手錯誤、已證實市場資訊洩漏。
- `high`：很可能實質改變主要機率或信心度。
- `medium`：可能影響解讀的重要限制。
- `low`：措辭、追溯性或輕微精度問題。

最終結果必須列出接受與否決的 finding ID。每個 finding 不分嚴重度都必須且只能出現在其中一邊，並在 `finding_adjudications` 逐項保存裁決、理由與最終處置。任何實際套用到最終輸出的修訂都必須在 `changes` 記錄，包括數字、thesis、正文補充或文字修正；文字類修訂的 `before`、`after` 使用簡短描述，不複製整段正文。agy 的每個 `unresolved_questions` 都必須依原順序出現在 `question_resolutions`；可標示仍未解，但必須說明缺少的證據與對預測的影響，並把會影響讀者決策的內容反映在最終正文的主要風險或尚缺資料。

`prediction.md` 的紅隊段落只以短列點簡述 `changes` 的修改欄位及修改前後；沒有修改時只寫「未修改；保留原預測。」不得渲染模型名稱、verdict／summary、接受與否決數量、九項一致性稽核、問題回覆、finding ID、理由長文或逐條裁決。`prediction.json.red_team` 與 `prediction.json.adjudication` 必須保存完整 review、逐條裁決、理由與處置，不得因對外報告精簡而刪減。

## 退出碼與修復方式

- `0`：成功。
- `2`：指令用法錯誤或缺少檔案。
- `3`：JSON、Schema 或語意驗證失敗。
- `4`：外部 CLI 失敗、逾時或回傳非 JSON。

驗證失敗時，修復產生錯誤的階段並重新產生所有下游檔案。不要只手動修改衍生的 `prediction.json`。
