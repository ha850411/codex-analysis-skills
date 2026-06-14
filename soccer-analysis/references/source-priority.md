# 足球資料來源優先序

分析足球時，優先使用最新且可驗證的來源。若來源衝突，先寫出衝突，再採用較權威或較接近即時狀態的資料。

## 賽程、場地與賽制

1. FIFA / UEFA / AFC / CONMEBOL / 各國足協、聯賽或盃賽官方 match centre
2. 球隊官方賽程與公告
3. FotMob / SofaScore / ESPN / BBC / Sky Sports 等賽程頁
4. 其他比分網站

官方來源對開賽時間、主客隊、中立場、延期、賽制與正式先發通常優先。

## 正式先發與預計先發

1. 賽事官方 match centre 或球隊官方 lineup 公告
2. 球隊官方社群與可靠 beat reporters
3. FotMob / SofaScore / WhoScored 的 confirmed lineups
4. FotMob / SofaScore / WhoScored 的 predicted lineups
5. 最近出賽陣容與輪換規律推估

正式先發未公布前，只能寫 `預計` 或 `推估`。賽前約 60 分鐘若正式先發公布，必須優先更新。

## 傷停與停賽

1. 球隊官方公告、教練賽前記者會、官方 injury update
2. 聯賽/足協/UEFA/FIFA disciplinary report 或停賽公告
3. 可靠 beat reporters 與當地權威媒體
4. FotMob / SofaScore / WhoScored 傷停頁
5. Transfermarkt injury/suspension list

若球員被列為 doubtful、questionable、late fitness test 或未完整訓練，不要當成確定出賽。

## 進階數據

- FBref / StatsBomb via FBref：xG、npxG、xGA、射門、傳球、壓迫、守門員與球員數據。
- Understat：xG、xGA、shot map 與歷史模型輔助。
- FotMob / SofaScore / WhoScored：比賽事件、球員評分、預計陣型、近期 form 與即時數據。
- 官方賽事數據：控球、射門、角球、犯規、牌數與比賽報告。

近幾場勝敗、控球率與場均進球只能作背景，不能取代 xG、射門品質、對手強度與先發脈絡。

## 賽後檢討資料

1. 官方 match centre：正式比分、進球、牌、換人、先發與賽事報告。
2. FotMob / SofaScore / WhoScored：xG、射門品質、big chances、平均站位、球員評分與比賽事件。
3. FBref / StatsBomb / Understat：若已更新，優先用於 xG、shot map、npxG 與攻防內容回測。
4. 可靠賽後報導與教練/球員訪談：用於確認傷病、戰術調整與臨場計畫。
5. 盤口紀錄或使用者提供截圖：用於檢查原推薦是否有真實 EV，以及收盤是否反向。

檢討時必須區分結果運氣與流程錯誤。若原方向贏 xG 卻輸比分，可標記為合理變異；若比分、xG、射門品質與戰術內容都反向，必須視為模型錯誤並降溫。

## 戰術與近期內容

1. 最近 3 到 5 場完整比賽或官方 highlights / extended highlights
2. 主教練記者會與官方訪談
3. 可靠戰術分析、賽後報告與當地媒體
4. 數據網站的陣型、平均站位與 shot map

若無法看完整比賽，必須說明限制，並提高可驗證數據與近期報導的權重。

## 天氣、場地與裁判

1. 官方場地與賽事公告
2. 可靠天氣來源
3. 場地草皮、屋頂、海拔與中立場資訊
4. 裁判指派與歷史牌數/點球傾向

裁判與天氣只能作輔助，不可過度放大；但極端風雨、差草皮、高海拔或牌數偏高裁判可影響大小球、角球與牌數市場。

## 盤口

1. 使用者提供的 Stake 即時賠率
2. 使用者指定的 sportsbook
3. 多市場平均價格作參考

分析時以模型機率為主，再比較市場價格。不要把賠率變動直接解讀為必然資訊優勢。足球不同市場結算規則差異很大，盃賽必須先確認 90 分鐘、含延長賽、晉級或 PK。

## 來源衝突處理

- 賽程與場地：官方賽事來源優先；若比分網站時間不同，以官方或倒數時間更新較近者為準並標註。
- 先發：正式 lineup 優先於 predicted lineup；未公布時以預計先發與輪換規律推估並降信心。
- 傷停：官方與可靠隊記優先；資料互相衝突時，列出狀態差異並避免高信心下注。
- 停賽：聯賽、足協或賽事官方紀律公告優先。
- 數據：若 xG 與比分近況衝突，解釋差異後優先使用能反映機會品質的指標。
- 盤口：記錄查詢時間點。盤口快速變動時，建議使用者提供即時價格再判斷 EV。
