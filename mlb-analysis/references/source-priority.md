# MLB 資料來源優先序

分析 MLB 時，優先使用最新且可驗證的來源。若來源衝突，先寫出衝突，再採用較權威或較接近即時狀態的資料。

## 賽程與比賽狀態

1. MLB.com schedule / game page / Gameday
2. 球隊官方公告
3. ESPN / Baseball-Reference scoreboard
4. 其他比分網站

MLB.com 對延賽、補賽、雙重賽與 probable pitchers 通常優先。

## 先發投手

1. MLB.com Probable Pitchers
2. 球隊官方或 beat reporter 當日公告
3. RotoWire / FanGraphs probable starters
4. 其他媒體推估

若顯示 TBD，不要自行指定，除非清楚標註為推估。

## 先發打線與傷兵

1. MLB.com lineups / team official lineup card
2. 球隊官方社群或 beat reporter
3. RotoWire confirmed lineups
4. ESPN / CBS / FantasyLabs 類來源

若賽前打線未公布，可用最近打線推估，但必須標記 `推估`。

## 進階數據

- 投手與打者 Statcast：Baseball Savant
- wRC+、FIP、xFIP、K-BB%、Depth Charts：FanGraphs
- Game logs、歷史紀錄：Baseball-Reference
- 球隊近期 box score：MLB.com / ESPN

ERA、打擊率與近幾場勝敗只能作輔助，不能作為核心依據。

## 牛棚

1. MLB.com / ESPN 最近 box scores
2. FanGraphs bullpen stats
3. Baseball Savant pitcher logs
4. 球隊或 beat reporter 的 availability notes

最近 3 天用量比賽季總 ERA 更重要，尤其對全場盤與大小分。

## 天氣與球場

1. Weather.gov 或可靠天氣來源
2. 球場屋頂官方狀態
3. Park factor 資料來源，例如 FanGraphs、Statcast、Baseball Savant 或其他可信彙整

風向要說明是往外野、往內野、左外野或右外野，不要只寫有風。

## 盤口

1. 使用者提供的 Stake 即時賠率
2. 使用者指定的 sportsbook
3. 多市場平均價格作參考

分析時以模型機率為主，再比較市場價格。不要把賠率變動直接解讀為必然資訊優勢。

報告輸出的賠率只允許十進位。若來源提供美式、分數、香港盤、馬來盤、印尼盤或其他格式，先內部轉換；無法可靠轉換時，不輸出原始賠率，只保留模型機率、公允十進位賠率與價格門檻。
