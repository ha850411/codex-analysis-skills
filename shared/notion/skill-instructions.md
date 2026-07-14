# Skill Notion export instructions

使用者在當前請求明確要求「寫到 Notion」、「同步 Notion」或「跑完預測後上傳 Notion」時，完整分析完成後執行 Notion 匯出。

若只有環境變數 `NOTION_AUTO_PUBLISH=1`、但當前請求未提及外部發布，先建立本地 Markdown 與 summary JSON，告知已準備完成並取得確認後才執行發布。賽後測試、回測與 skill 驗證不得因環境變數自動發布。遵循 `../analysis-core.md` 的外部寫入邊界。

## 流程

1. 先正常完成該模組的查證、分析與最終 Markdown。
2. 建立一份 summary JSON，欄位使用下方 schema。
3. 將完整分析 Markdown 存成暫存檔。
4. 從 skills repo 根目錄執行：

```bash
node shared/notion/publish_prediction.mjs \
  --summary <summary.json> \
  --markdown <analysis.md>
```

5. 若成功，回覆使用者 Notion page URL。
6. 若缺少 `NOTION_TOKEN`、`NOTION_DATA_SOURCE_ID`、`NOTION_DATABASE_ID` 或 `NOTION_PAGE_ID`，不要假裝成功；保留分析結果，並明確告知缺少哪個設定。

## 表格輸出

Exporter 預設使用 `NOTION_TABLE_LAYOUT=auto`：窄表維持 Notion table，欄位很多或文字很長的寬表會自動展成卡片式清單，避免 Notion 欄寬把文字擠在一起。

如果使用者明確要求保留表格，可執行時加上 `--table-layout table`；如果想所有有表頭的表格都展成清單，可用 `--table-layout cards`。

## Summary schema

`startTime` 必須填分析的比賽時間，使用台灣時間 UTC+8；ISO-8601 格式需帶 `+08:00`。

`confidence` 必須填模型信心度百分比，例如 `64%`；資料不足時填 `N/A（原因）`，不得省略欄位，也不得填入勝率或投注價值。

```json
{
  "title": "string",
  "sport": "string",
  "module": "string",
  "event": "string",
  "startTime": "ISO-8601 string in Taiwan time (+08:00) if available",
  "bo": "string",
  "prediction": "string",
  "winner": "string",
  "winProbability": "string",
  "recommendation": "string",
  "stake": "string",
  "confidence": "number or percent string",
  "risk": "string",
  "sourceStatus": "string",
  "analysisType": "pre-match | postmortem | daily-summary",
  "tags": ["string"]
}
```

## 模組值

| Module | Sport |
| --- | --- |
| `cs-analysis` | `CS2` |
| `dota2-analysis` | `Dota 2` |
| `valorant-analysis` | `Valorant` |
| `lol-analysis` | `LoL` |
| `mlb-analysis` | `MLB` |
| `nba-analysis` | `NBA` |
| `soccer-analysis` | `Soccer` |

如果單次分析有多場比賽，可以選擇：

- 每場建立一筆 Notion page。
- 或將 `analysisType` 設為 `daily-summary`，用一筆 page 保存整份今日決策總結。

預設偏好：單場深度分析每場一筆；今日多場總結用一筆。
