---
name: mlb-analysis
description: "分析 MLB／美國職棒賽事的賽程、先發投手、打線、牛棚、傷兵、天氣、球場、模型機率、盤口價值與賽後校準。用於 probable pitchers、前五局、獨贏、讓分、大小分、球員盤與今日決策；不要用於其他棒球聯盟、遊戲或一般規則問題。預設繁體中文與台灣時間。"
---

# MLB 賽事分析

預設繁體中文、台灣時間（Asia/Taipei）。優先沿用公開資料 baseline 與分階段模擬；前五局和全場分開結算。

## 執行契約

先讀 `../shared/analysis-core.md`；產生新機率再讀 `../shared/forecast/contract.md`。共用層負責時間、快照、機率、評估與輸出；本技能負責 先發投手、打線、牛棚工作量、場地與天氣、前五局與全場。

- 先確認指定賽事與台灣日期；整日請求盤點完整目標集合，不能只挑易預測場次。
- 讀 `references/source-priority.md` 查核易變事實。保存事件身分、來源內容、發布與查核時間；缺口不得用模型記憶補齊。
- `full`、`daily-summary` 在建模前讀 `references/domain-analysis.md` 的適用部分；新機率同時讀 `../shared/prediction-methodology.md`，完成證據到實際輸入的核對與反證檢查。領域推理不能直接覆寫計算結果。
- 先分辨先發能力、預期工作量與接手牛棚，再看打線及得分環境；相同投手的 ERA、FIP、xERA 不重複加分。缺完整投影時沿用公開 baseline，保留未建模的打線／牛棚影響。
- 新計算入口：`python3 shared/forecast/cli.py train|predict|validate|record|derive|evaluate|render`，輸入契約與範例見共用契約。基準、實驗與正式模型分開標示。
- 先建比分主分布，再導出勝方、比分眾數與其他市場。勝方與比分眾數方向不同時分別解釋，不手改比分。
- 正式資訊改變後新增完整快照；發布前先驗證、保存，再從相同數據渲染報告。
- 報告完成或更新後，依 `../shared/report-storage.md` 自動分類歸檔：使用共用 `report_archive.py save --sport mlb`，模式與日期取當次實際任務。Gemini／Codex 使用相同流程，保留輸出模板、原始路徑與歷史版本。
- MLB 詳細建模與現有模擬：讀 `references/modeling-framework.md`，保留原公開 baseline 的版本與禁投注狀態。

## 模式與輸出

- 單一追問預設 quick；新機率仍須驗證與快照，只壓縮文字。
- 單場預設 full；整日預設 daily-summary。讀 `references/output-template.md`。
- 聊天提供結論、最多三項依據、主要風險、完整報告連結及唯一置底窄表；詳情保存在完整報告。
- 模型信心度是證據品質評分，與勝率分開。未知時顯示 N/A 與原因。
- 市場資料在機率鎖定後才接入；讀 `../shared/markets/collection-contract.md`。無可追溯價格或未校準基準不給正注碼。
- 使用者明確要求 agy／模型互審才啟動 `../prediction-pipeline/SKILL.md`；一般分析不額外啟動其他模型。
- Notion 匯出按 `../shared/notion/skill-instructions.md` 與現有授權執行。

## 賽後與改善

先讀 `../shared/postmortem-improvement.md` 和 `references/postmortem-calibration.md`。以勝方命中優先、比分次之，另報機率品質與覆蓋率；缺原始快照不得反造原預測。新增因子先作 candidate；沒有配對樣本外改善證據時保留 experiment-only，不以降低信心或注碼宣稱命中改善。
