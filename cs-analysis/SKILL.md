---
name: cs-analysis
description: "分析 Counter-Strike 2／CS:GO 電競賽事，明確選出看好勝方，以精簡表格提供比分、逐圖、總圖數與盤口預測。適用 CS2、HLTV 對戰、BO1／BO3／BO5、veto 更新、即時比分與經濟滾球、整日賽事及賽後校準；不適用遊戲安裝、設定或一般玩法。預設繁體中文與台灣時間。"
---

# Counter-Strike 賽事分析

預設繁體中文、台灣時間（Asia/Taipei）。BO1／BO3／BO5；CS:GO 歷史資料與 CS2 分開。

## 結論原則

- 第一行直接回答「**我看好 {隊名} 贏。**」，緊接勝率與看好方的代表比分。預設選同一主分布中系列勝率較高的一方；接近均勢仍選較高方，只補「小幅優勢」，不以「雙方都有機會」「等 veto 再說」代替答案。
- 勝率完全相同時，用已查證的本場對位作定性取捨，標明「模型同率，定性選 X」，不改百分比。無法量化但仍有可比較證據時，給定性勝方並標「勝率未量化」；連選邊依據也沒有時才明列無法判定及缺口，不任意選隊或捏造 50%。
- 看好方代表比分取該隊獲勝結果中機率最高者；與全分布比分眾數不同時，另用一行列出真正眾數與機率，不把代表比分稱為全場最可能結果。計算規則見 `references/prediction-data.md`。
- 「看好誰贏」與「是否下注」分開。缺價、0u、基準／實驗狀態不取代勝方判斷；明確選邊不表示保證獲勝，也不提高原始勝率。
- 預設結果多、說明少：數據用表格；優勢理由最多三點、每點一句，直接連結可比數據與本場地圖／角色。只留一個最重要翻轉條件，完整研究與稽核存附件。使用者要求深入時才展開推理。

## 執行契約

先讀 `../shared/analysis-core.md`；產生新機率再讀 `../shared/forecast/contract.md`。共用層負責時間、快照、機率與評估；本技能負責逐圖資料、陣容與角色、當前地圖池、veto、選邊及 LAN／Online。呈現採本技能的精簡結果模板。

- 先確認指定賽事與台灣日期；整日請求盤點完整目標集合，不能只挑易預測場次。
- 讀 `references/source-priority.md` 查核易變事實。保存事件身分、來源內容、發布與查核時間；缺口不得用模型記憶補齊。
- `full`、`daily-summary` 在建模前讀 `references/domain-analysis.md` 的適用部分；veto／陣容更新追問也須讀相關段落，不能因為是 quick 就省略補查。新機率同時讀 `../shared/prediction-methodology.md`，完成證據到實際輸入的核對與反證檢查。領域推理不能直接覆寫計算結果。
- 核對同陣容、同圖與對手強度後再比較攻守、首殺轉化及經濟局；區分選圖偏差與可重複弱點，veto 推測不能當成已公布結果。
- 使用共用 CS v2 模型時，依 `references/domain-analysis.md` 第4.1節執行 `scripts/audit_model.py`；核對實際評級更新、逐圖對手校正、資料期間與 BO 適用性，再解讀結果。稽核及消融是診斷，不會自動改變機率或升版。
- 滾球先依 `references/domain-analysis.md` 第7節核對即時比分、隊伍方向、換邊、當前規則及可用經濟狀態；用能接受該狀態的模型重建分布。共用賽前 predict 不支援回合經濟，不得僅改時間與快照名稱冒充 live。快照仍用 `live-m{X}-r{Y}`、`live-post-m{X}` 或 `live-halftime`；`data_cutoff` 為已確認回合時間，依共用契約區分 `reconstructed_after_start` 與特定局前瞻，不偽裝整場賽前 prospective。
- 新計算入口：`python3 shared/forecast/cli.py train|predict|validate|record|derive|evaluate|render`，輸入契約與範例見共用契約。基準、實驗與正式模型分開標示。
- 先建比分主分布，再依 `references/prediction-data.md` 執行 `scripts/summarize_forecast.py`，導出勝方、比分、預期圖數／圖差與逐圖條件機率。不另估一套展示數字，不由系列勝率反推回合比分。
- 正式資訊改變後新增完整快照；發布前先驗證、保存，再從相同數據渲染報告。
- 報告完成或更新後，依 `../shared/report-storage.md` 自動分類歸檔：使用共用 `report_archive.py save --sport cs`，模式與日期取當次實際任務。Gemini／Codex 使用相同流程，保留輸出模板、原始路徑與歷史版本。

## 模式與輸出

- 讀 `references/output-template.md` 的適用模式。單場賽前用 full：結論、數據、逐圖短表、最多三點理由；「完整分析」保留所有適用數據，「深入／詳細／展開原因」才增加說明。聊天直接交付結果，不以附件取代答案。
- 單一機率追問用 quick，回答該事件的機率、組成、公允價格與關鍵限制；承接使用者正在問的市場。收到 veto／名單等新資訊時用更新格式，列出受影響的逐圖與結果前後差異，不能只重貼舊結論。
- 整日請求用 daily-summary，涵蓋完整目標集合；滾球用 live，優先交付已確認局勢、條件機率、與上一快照的變化及失效條件。精簡依據不等於省略必要數字或未知狀態。新機率仍須驗證、保存快照。
- 單場不再重複置底五欄總結；daily-summary 直接用一張賽事預測總表搭配逐場短卡。這是 CS 專用呈現規則，其他運動維持原模板。
- 每場必列「預測信心度（證據品質）x/100」，與勝率分開；沿用 canonical forecast 的評分，不把它當作勝方命中率。未知時顯示 N/A 與原因；重大資料限制集中一行，不逐段重複。
- full 與 daily-summary 的聊天正文均須列每張預測地圖的雙方勝率，以實際隊名分欄；BO1／BO3／BO5 分別涵蓋 1／3／5 個可能圖序。整日分析不能只在附件提供逐圖機率。註明正式／推測 veto，後續圖勝率以「該圖開打時」為條件，並另列開打機率；缺少可計算資料明列缺口，不用歷史勝率代替。
- 市場資料在機率鎖定後才接入；讀 `../shared/markets/collection-contract.md`。無可追溯價格或未校準基準不給正注碼。
- 使用者明確要求 agy／模型互審才啟動 `../prediction-pipeline/SKILL.md`；一般分析不額外啟動其他模型。
- Notion 匯出按 `../shared/notion/skill-instructions.md` 與現有授權執行。

## 賽後與改善

先讀 `../shared/postmortem-improvement.md` 和 `references/postmortem-calibration.md`。以勝方命中優先、比分次之，另報機率品質與覆蓋率；缺原始快照不得反造原預測。新增因子先作 candidate；沒有配對樣本外改善證據時保留 experiment-only，不以降低信心或注碼宣稱命中改善。

先盤點當日已發布報告並按賽事去重；pre-veto、post-veto、live 與開賽後重建分帳。跨日誤差帳本、evaluated records 與 `factor-registry.json` 保存在 `.automation-state/cs/history/`，每次檢討讀取同版本／同快照歷史，不能把同場更新算成另一場命中。
