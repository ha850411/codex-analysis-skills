# Codex skills

請將 skill 放置到 ~/.agent/skills/ 底下

## Notion 匯出

所有賽事分析模組都已接上共用 Notion 匯出器：`shared/notion/publish_prediction.mjs`。

基本設定：

```bash
export NOTION_TOKEN="secret_xxx"
export NOTION_DATA_SOURCE_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

完整設定、建議欄位與 dry-run 指令見 `shared/notion/README.md`。
