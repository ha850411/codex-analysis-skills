# 資料來源優先順序與驗證規則

## 優先順序

1. 賽程來源
   - 主動並查 Riot／賽區官方與 LoL Fandom／Leaguepedia（`lol.fandom.com` 的賽事、賽程或 Match History 頁），再用 Liquipedia、OP.GG Esports 或其他有事件資料的獨立來源交叉確認。Fandom 若轉址，保留實際 URL；無法讀取時記錄原因並改查其他來源，不停在 Riot 空頁。
   - 官方明確的改期、取消與賽制公告優先；官方前端漏列、TBD、空回應或快取落後不代表沒有比賽，也不自動否定已被兩個獨立來源確認的場次。可由逐聯賽頁面拼成使用者指定範圍，不要求一定有單一官方全域清單。
   - bo3.gg 提供候選賽程、provider Match ID 與比賽頁對照；官方前端更新延遲時，也可作已解析對戰索引。不得標成官方來源，也不得單獨決定完整集合。
   - 官方 bracket 與已完成前序賽果已唯一決定參賽者、bo3.gg 顯示同一對戰，且至少一個非 bo3 即時事件來源以事件 ID、時間與賽制交叉吻合時，可把 Riot 前端 placeholder 解析為 `resolved_from_bracket`。這是可稽核的降級路徑，不是把 bo3.gg 升格為官方來源。

2. 官方賽事與隊伍來源
   - Riot／賽區官方賽程、賽制、版本與公告。
   - 當場名單、隊伍公告、替補與臨時異動。
   - 官方資訊對改期、賽制、版本與當場 roster 優先。
   - 版本是逐聯賽／逐階段欄位：保存來源、擷取時間與適用日期範圍；不得把前一週或另一賽區的版本快取套到全日日報。
   - roster 登錄頁單獨只證明可用名單，不證明當場先發。逐隊另查同賽事最新兩個正式系列實際五人與近 30 天官方簽入／升降隊公告；若同一五人連續出賽、現役 roster 一致且沒有實際輪替或較新變更資訊，分類為 `established` 固定先發，不再寫「待確認」。若兩者與舊 roster 摘要衝突，使用較新且更接近當場的資訊建立先發情境。

3. 官方文字公告與賽後資料
   - 查官方賽事／隊伍的名單、版本、規則、賽後比分與文字回顧。
   - 預設不查影片頻道、VOD或精華，不以影片搜尋作為補查路徑。

4. 數據與歷史比賽參考
   - https://esports.op.gg/schedules
   - 可取得時使用官方 LoL Esports 比賽頁
   - 有幫助時使用 Oracle's Elixir、Games of Legends、Leaguepedia 衍生數據與其他可信數據網站
   - 季後賽預測時，優先查看最近兩個系列賽、同版本或相近版本的 pick/ban、每局勝方、選邊、時長、前期經濟與物件紀錄。

5. 賽後檢討資料
   - 優先使用 LoL Fandom/Leaguepedia 的結果、版本、每局勝方、選邊與 BP 紀錄。
   - 搭配官方賽後數據、逐局 BP 與事件時間線確認局間選角變化和關鍵物件；資料不能支持的操作或團戰細節不作事實描述。
   - 可用 RFT.GG、Oracle's Elixir、Games of Legends、OP.GG Esports 等數據站補足每局時間、擊殺、選角與近期戰績，但不得取代主要來源。

## 衝突處理

- 如果陣容或先發資料衝突，採用時間較新且更接近當場的官方公告；若只有社群 wiki，列出差異並降低信心度。
- 如果賽程時間衝突，全部轉換為台灣時間，並說明採用的來源。
- 賽程 schema v2 支援兩條驗證路徑。`verification_mode=official_crosscheck`（舊檔省略此欄亦同）保留 `official_sets` 與 `independent_coverage` 的聯集比對。`verification_mode=multi_source_crosscheck` 以 `primary_sets` 與 `independent_coverage` 的聯集比對；優先以 Leaguepedia 為主集合，另一側用不同營運方且不同資料上游的來源。兩側都須逐一覆蓋 `target_leagues` 及完整台灣日期視窗。只有使用者指定 LPL 時就只驗證 LPL，不擴張為所有賽區。
- 多來源路徑不要求 Riot 完整集合，也不把社群站標成官方。`primary_sets[]` 使用 `role=primary_league`；與 `independent_coverage[]` 一樣保存 `league`、`source`、`checked_at`、`coverage_start`、`coverage_end`、`provider_ids`、`evidence_note`、`matches`。`provider_ids` 列所有已知資料上游的固定小寫 ID，例如 `leaguepedia`、`liquipedia`、`pandascore`；直接自採來源列自身營運方。`evidence_note` 說明資料來自何處、頁面覆蓋及去重方式；無法判定上游獨立性時補查另一來源。Leaguepedia 的鏡像、轉載或引用其資料的聚合站不能算第二份獨立證據。來源標籤及算術驗證不能替代實際讀取。
- 多來源路徑保存 `official_checks[]`：每個目標聯賽至少一筆 `league`、`source`、`checked_at`、`status`、`note`，狀態為 `consistent`、`missing`、`unavailable`、`stale` 或 `conflict`。有可讀的明確官方改期／取消衝突時，先消解並重新建集合；不得把此類衝突寫成 stale 來繞過。單純缺場記為 missing，可在雙獨立集合一致後繼續。發布／更新時間未知時留 null，查核時間不能冒充公告時間。
- 兩側集合都保存逐場身分，不得只保存 URL 或場數。每筆包含 `match_key`、UTC+8 `start`、`league`、`stage`、`format`、`team1`、`team2` 與 `participant_status`。兩個獨立來源已明確列出相同雙方時使用 `confirmed`，意指賽程身分已交叉確認，不等同官方先發確認。仍需由 bracket 推導時沿用 `resolved_from_bracket` 與解析證據；未能唯一解出雙方則保留候選，不猜隊名。
- bo3.gg 保留候選與比賽索引用途，不計入任一完整性驗證側。兩側聯集與最終去重集合必須一致，且不可漏掉目標聯賽；同場不同 provider ID、隊名順序或輪次翻譯先正規化，保留原值及映射，不重複計場。真正的時間、隊伍或賽制衝突未消解時，才停止鎖定預測。
- 外層預查清單只是候選集合。交叉來源找到額外目標賽事時必須補入；若無法建立可重現的 `match_key`，標記驗證失敗並等待重查。
- bo3.gg 沒有 Match ID 但任一驗證路徑已確認場次時，不得漏場；改用穩定 `lol:<league>:<YYYYMMDDTHHMM+0800>:<team1>:<team2>`，並明示 `bo3_match_id=null` 與上游資料缺口。
- 「沒有比賽」也須由所選路徑兩側的完整日期覆蓋支持。錯誤、載入中、空回應不能當作已確認的空賽程；跨聯賽逐一驗證，不能以某聯賽休賽代表全日休賽。
- 新日報使用 schedule schema v2 並執行 `node lol-analysis/scripts/validate_schedule_completeness.mjs <schedule-verification.json>`；legacy schema 只可做歷史稽核，不得支撐新的 `complete=true`。
- 如果版本資料缺失，只能謹慎根據賽事規則/日期推論，並標記為未確認。
- 永遠不要捏造先發。只有存在可信輪替候選、近期實際換人或來源缺口時才使用「尚未確認」；通過 `established` 閘門者統一寫「固定先發（已核實；非臨場公告）」。LoL Fandom／Leaguepedia roster 單獨不足以確認，但也不得忽略最近兩個正式系列的固定實戰五人。

## 時效性

- 當日與未來比賽分析必須使用最新網路資料。
- 每場版本與名單查核都要有獨立 `checked_at`。沿用先前日報的版本／名單快取前，必須重新核對同週官方賽事或公告；無法證明仍適用時視為未確認，不得沿用為事實。
- 優先分析最近 1–2 週比賽。
- 一個月資料只作為背景脈絡。
- 賽後檢討若發生在比賽隔天或更近，必須重新查證實際結果與版本，不能只依使用者記憶或前次預測紀錄。

## 盤口

- 盤口優先使用 Odds-API.io 的 bookmaker 指定快照；執行 `shared/markets/collect_odds_api.mjs --sport esports`，預設只收帳戶已選的 `Stake` 價格，保存 provider event ID、Stake 深連結、擷取時間、原始回應 SHA-256、事件名稱、玩法與十進位價格。不得把其他 bookmaker 的價格標成 Stake。
- API 金鑰優先由 repo 根目錄之 `.env` 讀取 `ODDS_API_KEY`（或 process.env），執行收集前必須優先查核並載入該檔，嚴禁未讀取 `.env` 便宣稱缺金鑰；不得傳入 CLI、寫進程式、測資、輸出、日誌或版控。API 401、403、429、找不到事件、未開盤／未覆蓋玩法都必須明確失敗或標記缺失。
- 收集器支援 `ML`、`Spread`、`Totals`，逐場依 `../../shared/markets/collection-contract.md` 請求並查核必要盤線。API市場名稱存在不等於價格已安全映射；首局、精確比分等未映射玩法不得納入EV或宣稱完整覆蓋。
- 主預測鎖定後才附加 `market_data` 並形成獨立決策；使用者有觸發agy時，等主預測、agy與最終裁決全部鎖定後再由pipeline處理。一般分析不因取盤口而啟動agy；不得為取得新價格重跑機率模型。
- 報告輸出的賠率只允許十進位。若來源提供美式、分數、香港盤、馬來盤、印尼盤或其他格式，先內部轉換；無法可靠轉換時，不輸出原始賠率，只保留模型機率、公允十進位賠率與價格門檻。
- 分析時以模型機率為主，再比較市場價格。不要把賠率變動直接解讀為必然資訊優勢。

## 推薦閘門資料

- 推薦地圖大分、打滿、+1.5 或至少贏一局前，必須取得能支撐兩隊取圖路徑的資料：近期 BP、選邊、早期物件、對位線權、局間調整與收尾能力。
- 若只能取得比分而缺少 BP／局內資料，相關市場信心度上限為中低，且注碼必須下修。
- 舊 H2H 只能作為背景。若舊 H2H 與最近季後賽內容衝突，優先採用最近季後賽內容。
