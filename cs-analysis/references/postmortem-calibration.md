# CS 賽後檢討與模型校準

## 1. 重建賽前快照

- 核對賽事、階段、BO、LAN/online、Active Duty map pool、veto 規則與資料截止時間。
- 核對當場五人、stand-in、IGL、AWPer、coach 與角色變動。
- 保存原獨贏、精確比分、逐圖機率、至少一圖、信心度、價格與推薦，不用賽後資訊改寫。

## 2. 重建實際內容

- 系列比分、veto／map order、pick owner、選邊、每圖比分與 OT。
- T／CT 半場、pistol、force-buy／anti-eco、opening duel、首殺後轉化、timeout 後回合與領先收尾。
- 官方賽事資料、HLTV match page、VOD 與 Liquipedia 交叉查核；資料不足時明列缺口。

## 3. 評分

- 對獨贏與精確比分分別計算 Brier score；需要比較模型時另記 log loss。
- 檢查實際結果在原精確比分分布中的機率，而不是只標記「猜中／猜錯」。
- 逐圖比較預測勝率與結果，但不把三張圖當完全獨立樣本。
- 以同賽制、同預測時點與相近信心區間累積 calibration cohort；單場只作警報。

## 4. 錯誤歸因

- 資料錯漏：陣容、stand-in、地圖池、veto 規則、場地或賽程過期。
- Veto／地圖池：permaban、comfort pick、decider 或 side selection 判錯。
- 角色與戰術：IGL／AWP、entry、anchor、T side 結構或 timeout 調整判錯。
- 轉化與經濟：pistol、force-buy、anti-eco、lead conversion 或 OT 風險漏算。
- 樣本與對手：過度相信原始地圖勝率、舊陣容 H2H、排名或明星名氣。
- 合理變異：少量 clutch、eco、pistol 或 OT；若跨圖重複出現則不能全歸因於變異。

## 5. 修正

- 流程錯誤立即修正資料來源、主分布或相依機率；純單場結果不硬設下一場勝率上限。
- 若取圖路徑或橫掃路徑漏算，從 veto 情境與逐圖勝率重建精確比分分布，不事後手動補尾端。
- 未確認 roster／veto 前，下注建議降一級；模型信心度依五項組成重算。
- 用歷史快照做 walk-forward 回測後，再判斷新權重是否優於舊流程。

## 6. 輸出順序

1. 賽果與來源。
2. 原預測快照 vs 實際。
3. Veto 與逐圖復盤。
4. 機率評分與失準類型。
5. 錯誤歸因。
6. 可執行的模型修正。

