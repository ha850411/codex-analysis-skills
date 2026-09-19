---
name: lol-analysis
description: "分析 League of Legends／英雄聯盟電競賽事的賽程、名單、版本、BP、系列賽機率、獨贏／地圖讓分／總局數等盤口價值與賽後校準。用於 LCK、LPL、LCP、LEC、LCS、國際賽、BO3／BO5、至少一局與今日決策；不要用於遊戲安裝、一般玩法、單排或非賽事問題。預設繁體中文與台灣時間。"
---

# LoL 賽事分析

預設繁體中文、台灣時間（Asia/Taipei）。保留 established 名單分類；新公告建立新快照，不能只改摘要。

預設採非影片分析：不搜尋、下載、播放 VOD／精華，也不擷取影片影格或逐字稿；使用 BP、逐局數據、經濟／物件時間線及可追溯文字資料。沒有觀看 VOD 不構成資料缺口，不扣信心、不降級、不要求補看。僅使用者之後明確要求影片工作時才另行處理，並據實說明可核實的內容。

## 本使用者的分析與注碼偏好

每次分析先讀 `references/user-decision-preferences.md`。這是使用者明確要求的 LoL 個人偏好：近期可比內容優先、缺口具體說明、每場提供方向與相對配置，注碼以總資金百分比表示；本使用者每日最高動用資金上限為 100%，嚴禁只給予 1% 象徵性微額配置，必須依照每場優勢與信心度進行實質階梯式總資金百分比配置。涉及輸出、配置與未校準即一律 0u 的舊規則時，以此偏好為準；不改寫模型的實際校準狀態或資格欄位。

## 執行契約

先讀 `../shared/analysis-core.md`；產生新機率再讀 `../shared/forecast/contract.md`。共用層負責計算、快照與評估；本技能負責判斷兩隊怎麼贏、哪些近期機制可重複，以及哪些證據足以改變預測。計算成功不等於分析完成。

- 先確認指定賽事與台灣日期；整日請求盤點完整目標集合，不能只挑易預測場次。賽程主動查 LoL Fandom／Leaguepedia，搭配官方與其他獨立來源；Riot 漏列、TBD 或無法讀取時，依 source-priority 的多來源路徑繼續，不把官方頁完整返回當成唯一通行條件。
- 讀 `references/source-priority.md` 查核易變事實。保存事件身分、來源內容、發布與查核時間；缺口不得用模型記憶補齊。
- LCK CL／二級聯賽、已知換人或重寫既有報告時，讀 `references/roster-baseline-audit.md`；核對歷史陣容可比性、模型實際輸入與重寫前後的證據差異。
- 每次新預測先讀 `references/forecast-fallback.md` 選路：查找適用既有模型 → 完成領域證據 → 選擇正式模型、已實作挑戰版或分析者情境估計；比分基準是資料不足時的最後降級。不能因缺一項 BP／局內資料就自動結束研究。每場保留明確數值方向、勝率、比分眾數與機率、數字證據品質；接近均勢或敏感時直說，不把數值最大者包裝成有實質優勢的主推。
- 新情境預測或系統性檢討讀 `references/systematic-validation.md`：接續既有跨日帳本與候選版本，分開研究程序、實際入模假設與已驗證數值因子。檢討規則已存在卻未改善時，追查是否執行、是否改變輸入、是否有同批前瞻對照，不再疊加同義規則。
- `full`、`daily-summary` 都讀 `references/domain-analysis.md`；使用者要求深入時，先完成其證據補查與對位分析，日報不降低逐場深度。領域判斷可透過 `references/analyst-scenarios.md` 成為具名、可重播的實驗情境，不能手改已鎖定分布，也不能冒充擬合參數或已校準模型。
- 近期再戰、雙方實戰資料新鮮度不對稱，或以「多套 BP 可重複」支撐方向時，讀 `references/mechanism-transfer.md`；核對機制成立條件、對手阻斷能力及權重理由，不能只靠情境已涵蓋雙方或數值重播通過結案。
- 新計算入口：`python3 shared/forecast/cli.py train|predict|validate|record|derive|evaluate|render`，輸入契約與範例見共用契約。基準、實驗與正式模型分開標示。
- 新機率同時依 `../shared/prediction-methodology.md` 核對來源、機制與實際輸入；沿用本技能的 fallback、分析者情境、非影片研究與個人偏好，不把共用原則誤當停做 LoL 分析的理由。
- LoL 分析者情境入口：`python3 lol-analysis/scripts/analyst_forecast.py build|validate|audit`。保留獨立比分基準；發布前以 `audit` 檢查權重／單局率／局間依賴敏感度、情境是否涵蓋有證據的反向優勢，多場一併查鏡像參數。BO5 大3.5須核對兩種橫掃的條件路徑與固定率75%上限，正文標明仍受限制的基準；有證據才使用完整 W/L 條件樹，不為避免重複72%硬調數值。附件只作診斷，不改主分布；解讀依 `references/analyst-scenarios.md`。
- 先建比分主分布，再導出勝方、比分眾數與其他市場。勝方與比分眾數方向不同時分別解釋，不手改比分。
- 正式資訊改變後新增完整快照；發布前先驗證、保存，再從相同數據渲染報告。
- 報告完成或更新後，依 `../shared/report-storage.md` 自動分類歸檔：使用共用 `report_archive.py save --sport lol`，模式與日期取當次實際任務。Gemini／Codex 使用相同流程，保留輸出模板、原始路徑與歷史版本。
- 舊 LoL 自動流程：保留 `references/forecast-evidence-gates.md`、`references/recommendation-gates.md` 及既有驗證器；共用 v2 不冒充 v7 evidence。同一快照跨格式匯出須保持數字相同；基準與實驗是不同快照，允許結果不同並說明原因。

## 模式與輸出

- 單一追問預設 quick；新機率仍須驗證與快照，只壓縮文字。
- 單場預設 full；整日預設 daily-summary。讀 `references/output-template.md`。
- 輸出採「結果詳盡、分析精簡」：聊天依序直出雙方勝負機率（A vs B）、兩邊各贏一場／兩邊都贏一場以上（BO3 >2.5、BO5 >3.5 及 >4.5）機率、單隊至少一局、完整系列比分與價格決策；分析理由、名單影響與重要缺口整合為一段二至三句，依序交代支持判斷、主要反證與翻轉條件，格式見 `references/output-template.md`。深入請求增加研究深度，不自動拉長正文；逐局證據與查核細節留附件。
- 「分析完成度」「機率來源／校準狀態」「投注資格」分欄保存；聊天用短標籤標示機率來源／校準與資格，影響方向、玩法或配置的缺口融入分析短段，其餘完成度與查核記錄放附件。0u 不免除分析交付，不能重複「未校準」代替分析。完整交付標準見 `references/output-template.md`。
- 模型信心度是證據品質評分，與勝率分開。每場按五項證據獨立評分；資料缺失是低分的依據，不等於無法評分。依 `references/forecast-fallback.md` 的信心更新規則保存逐項理由、已解決與仍存在的缺口；研究次數、風險條數與剛發生的失誤不自動扣分。只有符合降級契約的真正未建模場次才顯示 N/A 與具體原因。
- 市場資料在機率鎖定後才接入；讀 `../shared/markets/collection-contract.md`。執行盤口收集前必須優先確認並讀取 repo 根目錄之 `.env`（含 `ODDS_API_KEY` 等環境變數），嚴禁在未檢查或未載入 `.env` 前逕行判定無金鑰或宣告缺價。無可追溯價格不提供該玩法的可執行注碼；未校準模型的資格與使用者主觀預算配置依 `references/user-decision-preferences.md` 分開處理。
- 情境模型的 BO3／BO5 獨贏價格決策，鎖定後執行 `python3 lol-analysis/scripts/audit_decision.py <forecast.json> <quote.json> --output <decision-audit.json>`。同時檢查報價與自行提出的進場底價；格式見 `references/systematic-validation.md`。單參數敏感度不是安全下界，診斷端點不替代主機率、不自動改方向或注碼。
- 使用者明確要求 agy／模型互審才啟動 `../prediction-pipeline/SKILL.md`；一般分析不額外啟動其他模型。
- Notion 匯出按 `../shared/notion/skill-instructions.md` 與現有授權執行。

## 賽後與改善

先讀 `../shared/postmortem-improvement.md` 和 `references/postmortem-calibration.md`。先核對原快照、manifest 與發布證據，再以每事件最後一份可證明已發布的賽前快照計分；改寫報告不得冒充原推薦。以勝方命中優先、比分次之，另報機率品質與覆蓋率；缺原始快照不得反造原預測。新增因子先作 candidate；沒有配對樣本外改善證據時保留 experiment-only，不以降低信心或注碼宣稱命中改善。

找歷史失誤共通點時，同時列出相同觸發條件的命中與未命中案例；依模型／賽區／賽制分組，區分機制未蒐集、已蒐集未入模、已入模但權重待驗證及合理變異。不能只數失敗案例便宣稱某因子無效。

系統性檢討另外交付完整事件母體、舊修正的落實稽核、原情境對原比分基準的配對差值，以及獨立的價格決策帳本。被看過的結果列開發集；沒有賽前鎖定的 challenger，就直說「尚無改善實驗」，不能把新增文件、audit 通過或原模型間比較寫成新 skill 命中改善。

終場尚未核實時先交付原快照與流程稽核，結果指標留空並保存待補項；不把網站 Live／0:0 占位符當終場，也不把單場低機率結果直接判為校準失敗。各版 schema 的信心與模型規則分開套用。
