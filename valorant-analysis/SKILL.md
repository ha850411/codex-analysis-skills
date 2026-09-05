---
name: valorant-analysis
description: "分析 Valorant／特戰英豪電競賽事的賽程、陣容、版本、地圖池、veto、特務池、系列賽機率、盤口價值與賽後校準。用於 VCT、Masters、Champions、Challengers、Game Changers、BO3／BO5、至少一圖與今日決策；不要用於遊戲安裝、設定、一般玩法或非賽事問題。預設繁體中文與台灣時間。"
---

# Valorant 賽事分析

預設繁體中文、台灣時間（Asia/Taipei）。保留六人名單的逐圖輪換；零樣本或常 ban 不等於實力差。

## 執行契約

先讀 `../shared/analysis-core.md`；產生新機率再讀 `../shared/forecast/contract.md`。共用層負責時間、快照、機率、評估與輸出；本技能負責 當前賽事地圖池、逐圖名單、特務池、veto、pick owner 與選邊。

- 先確認指定賽事與台灣日期；整日請求盤點完整目標集合，不能只挑易預測場次。
- 讀 `references/source-priority.md` 查核易變事實。保存事件身分、來源內容、發布與查核時間；缺口不得用模型記憶補齊。
- 深入領域分析時讀 `references/domain-analysis.md`；只載入本場相關資料。領域推理不能直接覆寫計算結果。
- 新計算入口：`python3 shared/forecast/cli.py train|predict|validate|record|derive|evaluate|render`，輸入契約與範例見共用契約。基準、實驗與正式模型分開標示。
- 先建比分主分布，再導出勝方、比分眾數與其他市場。勝方與比分眾數方向不同時分別解釋，不手改比分。
- 正式資訊改變後新增完整快照；發布前先驗證、保存，再從相同數據渲染報告。
- 舊快照：依 `references/forecast-snapshot.md` 重播，保留原 ID；新 v2 快照使用共用 record。

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
