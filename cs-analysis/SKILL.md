---
name: cs-analysis
description: "分析 Counter-Strike 2／CS:GO 電競賽事的賽程、陣容、地圖池、veto、系列賽機率、盤口價值、賽中滾球（live in-play）動態重估與賽後校準。用於 CS2、Counter-Strike、HLTV 對戰、BO1／BO3／BO5、即時比分與經濟滾球、至少一圖、總地圖數與今日賽事決策；不要用於遊戲安裝、設定、一般玩法或非賽事問題。預設繁體中文與台灣時間。"
---

# Counter-Strike 賽事分析

預設繁體中文、台灣時間（Asia/Taipei）。BO1／BO3／BO5；CS:GO 歷史資料與 CS2 分開。

## 執行契約

先讀 `../shared/analysis-core.md`；產生新機率再讀 `../shared/forecast/contract.md`。共用層負責時間、快照、機率、評估與輸出；本技能負責 逐圖資料、陣容與角色、當前地圖池、veto、選邊及 LAN／Online。

- 先確認指定賽事與台灣日期；整日請求盤點完整目標集合，不能只挑易預測場次。
- 讀 `references/source-priority.md` 查核易變事實。保存事件身分、來源內容、發布與查核時間；缺口不得用模型記憶補齊。
- `full`、`daily-summary` 在建模前讀 `references/domain-analysis.md` 的適用部分；veto／陣容更新追問也須讀相關段落，不能因為是 quick 就省略補查。新機率同時讀 `../shared/prediction-methodology.md`，完成證據到實際輸入的核對與反證檢查。領域推理不能直接覆寫計算結果。
- 核對同陣容、同圖與對手強度後再比較攻守、首殺轉化及經濟局；區分選圖偏差與可重複弱點，veto 推測不能當成已公布結果。
- 使用共用 CS v2 模型時，依 `references/domain-analysis.md` 第4.1節執行 `scripts/audit_model.py`；核對實際評級更新、逐圖對手校正、資料期間與 BO 適用性，再解讀結果。稽核及消融是診斷，不會自動改變機率或升版。
- 滾球先依 `references/domain-analysis.md` 第7節核對即時比分、隊伍方向、換邊、當前規則及可用經濟狀態；用能接受該狀態的模型重建分布。共用賽前 predict 不支援回合經濟，不得僅改時間與快照名稱冒充 live。快照仍用 `live-m{X}-r{Y}`、`live-post-m{X}` 或 `live-halftime`；`data_cutoff` 為已確認回合時間，依共用契約區分 `reconstructed_after_start` 與特定局前瞻，不偽裝整場賽前 prospective。
- 新計算入口：`python3 shared/forecast/cli.py train|predict|validate|record|derive|evaluate|render`，輸入契約與範例見共用契約。基準、實驗與正式模型分開標示。
- 先建比分主分布，再導出勝方、比分眾數與其他市場。勝方與比分眾數方向不同時分別解釋，不手改比分。
- 正式資訊改變後新增完整快照；發布前先驗證、保存，再從相同數據渲染報告。
- 報告完成或更新後，依 `../shared/report-storage.md` 自動分類歸檔：使用共用 `report_archive.py save --sport cs`，模式與日期取當次實際任務。Gemini／Codex 使用相同流程，保留輸出模板、原始路徑與歷史版本。

## 模式與輸出

- 讀 `references/output-template.md` 的適用模式。單場賽前與「深入／詳細／完整分析」預設 full；賽中則用 live 並展開所問內容。聊天直接交付完整結果、逐圖判斷及支持證據，不受三項依據上限限制，也不能以報告連結代替正文。研究明細與執行紀錄才放附件。
- 單一機率追問用 quick，回答該事件的機率、組成、公允價格與關鍵限制；承接使用者正在問的市場。收到 veto／名單等新資訊時用更新格式，列出受影響的逐圖與結果前後差異，不能只重貼舊結論。
- 整日請求用 daily-summary，涵蓋完整目標集合；滾球用 live，優先交付已確認局勢、條件機率、與上一快照的變化及失效條件。精簡依據不等於省略必要數字或未知狀態。新機率仍須驗證、保存快照。
- full／daily-summary 的正文可使用逐圖、比分及市場比較表；只有總結窄表限於最末一次。單一 quick 無須重列無關的獨贏／比分總結表。
- 模型信心度是證據品質評分，與勝率分開。未知時顯示 N/A 與原因。
- 市場資料在機率鎖定後才接入；讀 `../shared/markets/collection-contract.md`。無可追溯價格或未校準基準不給正注碼。
- 使用者明確要求 agy／模型互審才啟動 `../prediction-pipeline/SKILL.md`；一般分析不額外啟動其他模型。
- Notion 匯出按 `../shared/notion/skill-instructions.md` 與現有授權執行。

## 賽後與改善

先讀 `../shared/postmortem-improvement.md` 和 `references/postmortem-calibration.md`。以勝方命中優先、比分次之，另報機率品質與覆蓋率；缺原始快照不得反造原預測。新增因子先作 candidate；沒有配對樣本外改善證據時保留 experiment-only，不以降低信心或注碼宣稱命中改善。

先盤點當日已發布報告並按賽事去重；pre-veto、post-veto、live 與開賽後重建分帳。跨日誤差帳本、evaluated records 與 `factor-registry.json` 保存在 `.automation-state/cs/history/`，每次檢討讀取同版本／同快照歷史，不能把同場更新算成另一場命中。
