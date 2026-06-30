# CS 資料來源優先序

分析 Counter-Strike 賽事時，優先使用最新且可驗證的來源。若來源衝突，先寫出衝突，再採用較接近賽事官方或比賽頁面的資料。

## 賽程與 Match Page

1. HLTV.org match page
2. Liquipedia Counter-Strike tournament page
3. 主辦方官方賽程或 rulebook
4. 其他比分網站

HLTV 通常優先用於開賽時間、match page、隊伍近期戰績與地圖紀錄。Liquipedia 用於賽制、賽事階段與分組補充。

## 陣容與 stand-in

1. HLTV match page 或 team page
2. Team official announcement
3. Liquipedia roster / tournament page
4. 最近一場正式賽出場五人

若 HLTV 與 Liquipedia 不一致，查看官方公告與最近 match page。仍無法確認時，標註為推估。

## 賽制與地圖規則

1. 主辦方 rulebook 或官方賽事頁
2. Liquipedia tournament format
3. HLTV match page

必須確認 BO1 / BO3 / BO5、是否有 advantage、是否有特殊 veto 規則、是否同日連戰。

## 地圖池與 Veto

1. 官方 Active Duty map pool / patch note
2. HLTV map statistics and recent maps
3. Liquipedia tournament notes

不要假設舊地圖池仍然有效。若 map pool 剛變，舊地圖勝率要降權。

## 團隊與選手數據

- HLTV team stats：近期戰績、map stats、ranking。
- HLTV player stats：Rating、ADR、KAST、K-D diff、opening duels。
- Liquipedia：賽事脈絡、歷史名單、賽事階段。

低 tier 或 academy 賽事樣本容易偏少，需提高不確定性。

## LAN / Online 脈絡

1. 官方賽事頁確認地點與賽制。
2. Liquipedia venue / region。
3. HLTV event page。

LAN 表現、online ping、跨洲旅行、簽證與時差都可能影響判斷。

## 盤口

1. 使用者提供的 Stake 即時賠率
2. 使用者指定的 sportsbook
3. 多市場平均價格作參考

必須先以賽事證據獨立完成模型機率，再比較市場價格。盤口升降只能用於記錄價格變化與投注時機風險，不得作為勝負訊號、反證、模型機率或模型信心度的校準依據。

報告輸出的賠率只允許十進位。若來源提供美式、分數、香港盤、馬來盤、印尼盤或其他格式，先內部轉換；無法可靠轉換時，不輸出原始賠率，只保留模型機率、公允十進位賠率與價格門檻。
