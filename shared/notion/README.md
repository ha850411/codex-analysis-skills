# Notion prediction exporter

這個共用工具把各賽事分析模組的預測結果寫入 Notion。

它會做兩件事：

- 依 Notion data source / database schema 寫入可對應的 properties。
- 把完整分析 Markdown 轉成 Notion blocks，放進該筆 page 內容。

## 環境變數

至少需要：

```bash
export NOTION_TOKEN="secret_xxx"
export NOTION_DATA_SOURCE_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

也可以直接把設定填在 repo 根目錄的 `.env`。Exporter 會自動讀取 `.env`；`.env.example` 是可提交的範本，真正的 `.env` 已被 `.gitignore` 排除。

也支援：

```bash
export NOTION_DATABASE_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
export NOTION_PAGE_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
export NOTION_VERSION="2026-03-11"
export NOTION_DRY_RUN="1"
export NOTION_TABLE_LAYOUT="auto"
```

建議優先使用 `NOTION_DATA_SOURCE_ID`。如果只提供 `NOTION_DATABASE_ID`，工具會嘗試用 Notion API 取得該 database 底下第一個 data source。

Notion 端要先把目標 page/database 分享給 integration，並給 integration `Insert Content` 權限。

## 表格呈現

Markdown 窄表會照原樣輸出成 Notion table；欄位很多或文字很長的寬表，預設會自動改成卡片式清單，避免在 Notion 裡被擠成窄欄。

可用 `NOTION_TABLE_LAYOUT` 或 `--table-layout` 控制：

- `auto`：預設值，寬表自動展成卡片，窄表保留 table。
- `cards`：所有有表頭的表格都展成卡片式清單。
- `table`：全部保留原生 Notion table。

## 建議欄位

Notion data source 欄位可自由命名；工具會自動比對常見中英文欄位。最穩的欄位配置如下：

| 欄位 | 類型 |
| --- | --- |
| Name | Title |
| Sport | Select |
| Module | Select |
| Event | Rich text |
| Match Time | Date |
| BO | Select |
| Prediction | Rich text |
| Winner | Rich text |
| Win% | Rich text |
| Recommendation | Rich text |
| Stake | Rich text |
| Confidence | Number |
| Risk | Rich text |
| Data Status | Select |
| Tags | Multi-select |

如果你的 Notion 欄位不是這些名字，可以用 `NOTION_PROPERTY_MAP` 指定對應：

```bash
export NOTION_PROPERTY_MAP='{"prediction":"預測比分","confidence":"信心度","risk":"核心風險"}'
```

## Summary JSON

各模組在分析完成後產生一份 summary JSON，再交給 exporter。

```json
{
  "title": "Team A vs Team B",
  "sport": "CS2",
  "module": "cs-analysis",
  "event": "IEM Example",
  "startTime": "2026-06-13T20:00:00+08:00",
  "bo": "BO3",
  "prediction": "Team A 2-1",
  "winner": "Team A",
  "winProbability": "Team A 58% / Team B 42%",
  "recommendation": "Team A ML 0.5u",
  "stake": "0.5u",
  "confidence": 62,
  "risk": "Map veto uncertainty",
  "sourceStatus": "HLTV/Liquipedia checked",
  "tags": ["CS2", "pre-match"]
}
```

## 指令

從 skills repo 根目錄執行：

```bash
node shared/notion/publish_prediction.mjs \
  --summary /tmp/prediction-summary.json \
  --markdown /tmp/prediction-analysis.md
```

測試不寫入 Notion：

```bash
NOTION_DRY_RUN=1 node shared/notion/publish_prediction.mjs \
  --module cs-analysis \
  --sport CS2 \
  --summary /tmp/prediction-summary.json \
  --markdown /tmp/prediction-analysis.md
```

成功時會輸出 Notion page id 與 URL。
