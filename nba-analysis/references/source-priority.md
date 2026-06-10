# NBA 資料來源優先序

分析 NBA 時，優先使用最新且可驗證的來源。若來源衝突，先寫出衝突，再採用較權威或較接近即時狀態的資料。

## 賽程與比賽狀態

1. NBA.com schedule / game page
2. 球隊官方公告
3. ESPN scoreboard
4. 其他比分網站

NBA.com 對開賽時間、場館、主客隊、延賽與官方 box score 通常優先。

## 傷兵與出賽狀態

1. NBA 官方 Injury Report
2. 球隊官方公告與隊記/beat reporter
3. NBA.com game page / ESPN injury report
4. Rotowire / Underdog NBA / FantasyLabs 類即時傷兵來源

若球員顯示 Questionable、GTD 或未更新，不要當成確定出賽。若賽前 30 到 60 分鐘仍未確認，必須降低信心度。

## 先發與輪替

1. 球隊官方 lineup 公告
2. NBA.com game page / official box score
3. Beat reporter 或可靠 fantasy/news source
4. 最近出賽輪替推估

若先發未公布，可用近期先發與傷兵狀態推估，但必須標記 `推估`。

## 進階數據

- 官方 NBA Stats：team/player dashboards、lineups、tracking、shot dashboard。
- Basketball-Reference：賽季、game logs、on/off 與歷史資料。
- PBPStats：play-by-play、lineup、on/off、possession-level stats。
- Cleaning the Glass：garbage-time-cleaned team/lineup stats；若可取得，適合評估真實強度。
- ESPN / StatMuse 類來源可作查詢輔助，但不要單獨作為核心依據。

近幾場勝敗、場均得分、命中率只能作背景，不能取代攻防效率、節奏、Four Factors 與傷兵脈絡。

## 賽程與動機

1. NBA.com schedule 與球隊賽程頁
2. Basketball-Reference schedule
3. ESPN standings / playoff picture
4. 官方賽事說明，例如 NBA Cup、附加賽、季後賽系列賽

季末與季後賽必須核對排名動機、輪休可能性、主場優勢與淘汰壓力。

## 盤口

1. 使用者提供的 Stake 即時賠率
2. 使用者指定的 sportsbook
3. 多市場平均價格作參考

分析時以模型機率為主，再比較市場價格。不要把賠率變動直接解讀為必然資訊優勢。

## 來源衝突處理

- 傷兵：官方 Injury Report 與球隊/可靠 beat reporter 優先。
- 先發：球隊官方公布優先；未公布時以最近輪替推估並降信心。
- 數據：若 garbage-time-cleaned stats 與傳統場均數據衝突，解釋差異後優先使用更能反映真實強度的指標。
- 盤口：記錄查詢時間點。盤口快速變動時，建議使用者提供即時價格再判斷 EV。
