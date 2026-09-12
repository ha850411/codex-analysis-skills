---
name: lol-analysis
description: "分析 League of Legends／英雄聯盟電競賽事的賽程、名單、版本、BP、系列賽機率、獨贏／地圖讓分／總局數等盤口價值與賽後校準。用於 LCK、LPL、LCP、LEC、LCS、國際賽、BO3／BO5、至少一局與今日決策；不要用於遊戲安裝、一般玩法、單排或非賽事問題。預設繁體中文與台灣時間。"
---

# LoL 賽事分析

預設繁體中文、台灣時間（Asia/Taipei）。保留 established 名單分類；新公告建立新快照，不能只改摘要。

預設採非影片分析：不搜尋、下載、播放 VOD／精華，也不擷取影片影格或逐字稿；使用 BP、逐局數據、經濟／物件時間線及可追溯文字資料。沒有觀看 VOD 不構成資料缺口，不扣信心、不降級、不要求補看。僅使用者之後明確要求影片工作時才另行處理，並據實說明可核實的內容。

## 本使用者的分析與注碼偏好

每次分析先讀 `references/user-decision-preferences.md`。這是使用者明確要求的 LoL 個人偏好：近期可比內容優先、缺口具體說明、每場提供方向與相對配置，注碼以總資金百分比表示。涉及輸出、配置與未校準即一律 0u 的舊規則時，以此偏好為準；不改寫模型的實際校準狀態或資格欄位。

## 執行契約

先讀 `../shared/analysis-core.md`；產生新機率再讀 `../shared/forecast/contract.md`。共用層負責計算、快照與評估；本技能負責判斷兩隊怎麼贏、哪些近期機制可重複，以及哪些證據足以改變預測。計算成功不等於分析完成。

- 先確認指定賽事與台灣日期；整日請求盤點完整目標集合，不能只挑易預測場次。賽程主動查 LoL Fandom／Leaguepedia，搭配官方與其他獨立來源；Riot 漏列、TBD 或無法讀取時，依 source-priority 的多來源路徑繼續，不把官方頁完整返回當成唯一通行條件。
- 讀 `references/source-priority.md` 查核易變事實。保存事件身分、來源內容、發布與查核時間；缺口不得用模型記憶補齊。
- LCK CL／二級聯賽、已知換人或重寫既有報告時，讀 `references/roster-baseline-audit.md`；核對歷史陣容可比性、模型實際輸入與重寫前後的證據差異。
- 每次新預測先讀 `references/forecast-fallback.md` 選路：查找適用既有模型 → 完成領域證據 → 選擇正式模型、已實作挑戰版或分析者情境估計；比分基準是資料不足時的最後降級。不能因缺一項 BP／局內資料就自動結束研究。每場保留明確數值方向、勝率、比分眾數與機率、數字證據品質；接近均勢或敏感時直說，不把數值最大者包裝成有實質優勢的主推。
- `full`、`daily-summary` 都讀 `references/domain-analysis.md`；使用者要求深入時，先完成其證據補查與對位分析，日報不降低逐場深度。領域判斷可透過 `references/analyst-scenarios.md` 成為具名、可重播的實驗情境，不能手改已鎖定分布，也不能冒充擬合參數或已校準模型。
- 新計算入口：`python3 shared/forecast/cli.py train|predict|validate|record|derive|evaluate|render`，輸入契約與範例見共用契約。基準、實驗與正式模型分開標示。
- LoL 分析者情境入口：`python3 lol-analysis/scripts/analyst_forecast.py build|validate`。同時保留獨立比分基準，寫清楚哪些證據改變了情境及為何仍可能錯；不得為了遠離 50% 或迎合市場而使用此路徑。
- 先建比分主分布，再導出勝方、比分眾數與其他市場。勝方與比分眾數方向不同時分別解釋，不手改比分。
- 正式資訊改變後新增完整快照；發布前先驗證、保存，再從相同數據渲染報告。
- 舊 LoL 自動流程：保留 `references/forecast-evidence-gates.md`、`references/recommendation-gates.md` 及既有驗證器；共用 v2 不冒充 v7 evidence。同一快照跨格式匯出須保持數字相同；基準與實驗是不同快照，允許結果不同並說明原因。

## 模式與輸出

- 單一追問預設 quick；新機率仍須驗證與快照，只壓縮文字。
- 單場預設 full；整日預設 daily-summary。讀 `references/output-template.md`。
- 輸出採「結果詳盡、分析精簡」：聊天依序直出雙方勝負機率（A vs B）、兩邊各贏一場／兩邊都贏一場以上（BO3 >2.5、BO5 >3.5 及 >4.5）機率、單隊至少一局、完整系列比分與價格決策，再用最多三個短論點交代關鍵對位、雙方勝法與 BP 翻轉條件；欄位與 BO3／BO5 格式依 `references/output-template.md`。深入請求增加證據查核與結果解讀，不自動增加過程敘述；查核、重試與模型稽核細節留在附件。
- 分開標示「分析完成度」「機率來源／校準狀態」「投注資格」。0u 不免除分析交付；缺資料要交代查了哪裡、能支持什麼結論、還缺什麼，不能重複「未校準」代替分析。完整交付標準見 `references/output-template.md`。
- 模型信心度是證據品質評分，與勝率分開。每場按五項證據獨立評分；資料缺失是低分的依據，不等於無法評分。只有符合降級契約的真正未建模場次才顯示 N/A 與具體原因。
- 市場資料在機率鎖定後才接入；讀 `../shared/markets/collection-contract.md`。執行盤口收集前必須優先確認並讀取 repo 根目錄之 `.env`（含 `ODDS_API_KEY` 等環境變數），嚴禁在未檢查或未載入 `.env` 前逕行判定無金鑰或宣告缺價。無可追溯價格不提供該玩法的可執行注碼；未校準模型的資格與使用者主觀預算配置依 `references/user-decision-preferences.md` 分開處理。
- 使用者明確要求 agy／模型互審才啟動 `../prediction-pipeline/SKILL.md`；一般分析不額外啟動其他模型。
- Notion 匯出按 `../shared/notion/skill-instructions.md` 與現有授權執行。

## 賽後與改善

先讀 `../shared/postmortem-improvement.md` 和 `references/postmortem-calibration.md`。以勝方命中優先、比分次之，另報機率品質與覆蓋率；缺原始快照不得反造原預測。新增因子先作 candidate；沒有配對樣本外改善證據時保留 experiment-only，不以降低信心或注碼宣稱命中改善。

終場尚未核實時先交付原快照與流程稽核，結果指標留空並保存待補項；不把網站 Live／0:0 占位符當終場，也不把單場低機率結果直接判為校準失敗。各版 schema 的信心與模型規則分開套用。
