# Dota 2 資料來源優先順序與驗證規則

## 絕對優先順序

1. 官方賽事來源與主辦方公告
   - 賽程異動、賽制、rulebook、patch、stand-in 核准、伺服器與延賽。
   - 包含 ESL、PGL、BLAST、FISSURE、EWC/Riyadh、Valve / Dota 2 official、各賽事官方社群。

2. Liquipedia Dota 2
   - 賽程、賽事階段、BO 格式、隊伍 roster、stand-in、分組、結果。
   - 若官方與 Liquipedia 衝突，採官方來源，但需標註差異。

3. 數據站與 match/replay 資料
   - STRATZ、DatDota、DOTABUFF Esports、OpenDota。
   - 用於英雄池、BP、分路、KDA/GPM/XPM、Roshan、塔、道具 timing、近期對手強度。

4. 官方 VOD / Twitch / YouTube / DotaTV replay
   - 用於確認 draft、分路、rune、stack、smoke、Roshan、buyback、高地與關鍵團戰。

5. 盤口
   - Stake 或使用者提供的即時賠率優先；其他市場只作參考。
   - 盤口只用於 EV 與價格門檻，不得用來反推勝率或賽果方向。

## 衝突處理

- 賽程時間衝突時，全部轉換成台灣時間 UTC+8，並說明採用來源。
- Roster 或 stand-in 衝突時，官方公告優先，其次 Liquipedia，再其次最近正式賽出賽五人。
- Patch 不明時，先查官方賽事規則、賽事頁與近期同賽事 match page；仍不明時標記 `patch 未確認`，降低信心。
- 數據站英雄勝率與近期 VOD 印象衝突時，優先同 patch、同陣容、同層級對手的近期 VOD/BP。
- 不可捏造 draft、每局比分、英雄、選手數據或賽後內容。

## 時效性

- 當日與未來比賽分析必須使用最新網路資料。
- 最近 1-2 週與同賽事樣本優先於整季統計。
- 跨 patch、跨 roster、跨 captain/coach 的 H2H 只能作背景，不能主導結論。
- 賽後檢討必須重新查證實際結果、每局 draft、每局勝方與可取得 VOD/replay。

## 盤口格式

- 報告輸出的市場賠率、公允賠率與價格門檻只允許十進位。
- 若來源提供美式、分數、香港盤、馬來盤、印尼盤或其他格式，只能內部轉換；無法可靠轉換時，不輸出原始賠率。
- 若沒有可查即時盤口，先輸出模型機率、公允賠率與可接受價格，再請使用者提供即時賠率。
