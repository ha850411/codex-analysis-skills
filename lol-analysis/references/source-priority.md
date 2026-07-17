# 資料來源優先順序與驗證規則

## 優先順序

1. 官方賽事與隊伍來源
   - Riot／賽區官方賽程、賽制、版本與公告。
   - 當場名單、隊伍公告、替補與臨時異動。
   - 官方資訊對改期、賽制、版本與當場 roster 優先。

2. Leaguepedia 與 Liquipedia
   - Leaguepedia（`lol.fandom.com`）與 Liquipedia League of Legends 用於賽程、階段、版本、名單、Fearless Draft 與歷史資料交叉查核。
   - 兩者衝突時，不預設任一社群 wiki 永遠正確；比較更新時間並回到官方來源。

3. 官方賽區頻道與比賽 VOD
   - LCK: https://www.youtube.com/@LCKglobal
   - LPL: https://space.bilibili.com/50329118
   - LCP: https://www.youtube.com/@lolesportstw/videos
   - LEC: https://www.youtube.com/@LEC
   - LCS: https://www.youtube.com/@LCS

4. 數據與歷史比賽參考
   - https://esports.op.gg/schedules
   - 可取得時使用官方 LoL Esports 比賽頁
   - 有幫助時使用 Oracle's Elixir、Games of Legends、Leaguepedia 衍生數據與其他可信數據網站
   - 季後賽預測時，優先查看最近兩個系列賽、同版本或相近版本的 pick/ban、每局勝方、選邊、時長、前期經濟與物件紀錄。

5. 賽後檢討資料
   - 優先使用 LoL Fandom/Leaguepedia 的結果、版本、每局勝方、選邊與 VOD 連結。
   - 搭配官方 VOD 或官方精華確認 BP、局間調整、關鍵物件與團戰。
   - 可用 RFT.GG、Oracle's Elixir、Games of Legends、OP.GG Esports 等數據站補足每局時間、擊殺、選角與近期戰績，但不得取代主要來源。

## 衝突處理

- 如果陣容或先發資料衝突，採用時間較新且更接近當場的官方公告；若只有社群 wiki，列出差異並降低信心度。
- 如果賽程時間衝突，全部轉換為台灣時間，並說明採用的來源。
- 如果版本資料缺失，只能謹慎根據賽事規則/日期推論，並標記為未確認。
- 永遠不要捏造先發。必要時使用「尚未確認」或「LoL Fandom 未列明先發」。

## 時效性

- 當日與未來比賽分析必須使用最新網路資料。
- 優先分析最近 1–2 週比賽。
- 一個月資料只作為背景脈絡。
- 賽後檢討若發生在比賽隔天或更近，必須重新查證實際結果與版本，不能只依使用者記憶或前次預測紀錄。

## 盤口

- 使用者提供的 Stake 即時賠率優先，其次才參考使用者指定 sportsbook 或多市場平均價格。
- 報告輸出的賠率只允許十進位。若來源提供美式、分數、香港盤、馬來盤、印尼盤或其他格式，先內部轉換；無法可靠轉換時，不輸出原始賠率，只保留模型機率、公允十進位賠率與價格門檻。
- 分析時以模型機率為主，再比較市場價格。不要把賠率變動直接解讀為必然資訊優勢。

## 推薦閘門資料

- 推薦地圖大分、打滿、+1.5 或至少贏一局前，必須取得能支撐兩隊取圖路徑的資料：近期 BP、選邊、早期物件、對位線權、局間調整與收尾能力。
- 若只能取得比分而缺少 BP/VOD/局內資料，相關市場信心度上限為中低，且注碼必須下修。
- 舊 H2H 只能作為背景。若舊 H2H 與最近季後賽內容衝突，優先採用最近季後賽內容。
