# MLB 賽前得分模型與特徵契約

本文件適用於所有新 MLB 機率。目標是預測「機率分布是否校準」，不是猜中單一精確比分。若無法把證據轉成可重現的得分率或情境權重，只能把它列為風險或信心度缺口，不得憑敘事手調勝率。缺少成熟生產模型時，允許使用本文件第 2.1 節的可重現公開資料 baseline，但必須揭露未校準且禁止投注推薦。

## 1. 預測單位與版本

每場至少保存兩個互不覆寫的資訊集：

- `pre-lineup`：正式打線未公布；以可能打線情境加權。
- `post-lineup`：正式打線、捕手與守備位置已確認；重新計算，不沿用舊機率手調。

另保存 `model_version`、`as_of`、比賽 ID、先發投手狀態、屋頂／天氣狀態與資料來源。正式先發更換、球數限制、屋頂狀態或重大天氣改變時建立新版快照。

## 2. 建模順序

1. 以當季且向前收縮的聯盟每打席／每半局得分環境建立基準；季初必須混合前季與投影，不能把數週小樣本當成新常態。
2. 以可取得的 rest-of-season 投影建立打者、先發投手與後援投手真實能力先驗。
3. 依正式或情境打線、打序與預期打席數建立進攻率。
4. 將對手投球拆成先發、主要後援與尾端牛棚三段，按預期打者數而不是只按「名義局數」混合。
5. 把球場、天氣、守備／捕手、跑壘、旅行與規則環境轉成已回測的得分率修正。
6. 先得到前五局與第 6 局後的雙方期望得分，再以已校準的離散分布或模擬產生聯合比分分布。
7. 從同一批模擬推導獨贏、前五局三路、讓分、大小分與隊伍總分；不得逐項手填。
8. 鎖定模型輸出後才讀盤口並計算 EV。

可用下式理解每個階段的期望得分，但所有原始指標到 factor 的映射都必須由歷史 walk-forward 資料估計，不可把 `wRC+ 110` 直接當成固定 `1.10` 倍：

```text
log(階段期望得分) = log(聯盟基準)
                   + 打線投影修正
                   + 對手投球修正
                   + 球場／天氣修正
                   + 守備／捕手／跑壘修正
                   + 賽程／規則修正
```

### 2.1 公開資料 baseline 例外

沒有版本化生產投影時，執行 `scripts/build_public_baseline.py`，不要直接退化成全 N/A。該腳本只使用 `as_of` 前已完賽的 MLB Stats API 資料，並固定：

- 以 30 場聯盟先驗收縮球隊每場得分與失分。
- 以 40 局聯盟先驗收縮 probable starter 的 RA9，以 5 場先發先驗收縮工作量；TBD／無 MLB 樣本時回到聯盟基準。
- 由同季已完賽比分以矩估計共同／隊伍得分波動，再交給 `simulate_scores.py` 推導所有相依市場。
- 保留主客場聯盟得分環境；不假裝已有正式打線、逐投手牛棚、屋頂、天氣、球場或外部 rest-of-season projection 修正。

這些得分模型固定值屬 `mlb-public-baseline-v1.1.0` 的版本契約，不是臨場手調。輸出必須標記 `status=baseline`、`validation_status=uncalibrated`、`recommendation_eligible=false`。baseline 可以輸出得分均值、區間、勝率與公允賠率並納入賽後評分，但未通過 paired walk-forward 升版前，EV、價格門檻與注碼一律停用。

baseline 的信心度不設硬上限，也不得用「兩邊先發已列＝固定 55%／有 TBD＝固定 45%」代替逐場評分。`build_public_baseline.py` 必須依共用五項公式逐場保存分數與診斷值：資料完整度納入球隊及先發樣本覆蓋；新鮮度納入快照距開賽時間；名單／先發確定度納入 probable starter 與雙重賽第 2 場的不確定性；制度與樣本相關性納入當季球隊及先發有效樣本；模型穩定性納入樣本可靠度、相對聯盟基準的輸入敏感度、歷史分布樣本及雙重賽第 2 場風險。`uncalibrated` 與 `recommendation_eligible=false` 才是投注停用閘門，不得再以信心度上限代理驗證狀態。

## 3. 必要特徵與優先度

### A 級：缺少時不得給強結論

「不得給強結論」表示降低信心度、擴大情境範圍或停止推薦，不表示自動取消整份預測。先使用版本化生產模型；若不存在，改用第 2.1 節 baseline。只有腳本明確失敗、樣本不足或連 baseline run means 都無法重現時才把數值保留為 `N/A`。

| 區塊 | 必要輸入 | 處理方式 |
| --- | --- | --- |
| 聯盟基準 | 當季 R/PA、HR、BB、K 與球的環境 | 依日期向前計算；季初向前季與投影收縮 |
| 打線 | 正式／情境打線、打序、手別、rest-of-season 投影 | 依預期 PA 加權；替補與代打另建情境 |
| 先發 | 投影能力、預期 BF／局數、球數限制、休息、傷後狀態 | 先發強度與工作量分開；工作量用分布而非單一局數 |
| 牛棚 | 個別投手投影、最近 3 日球數、連投、角色與可用率 | 建立可能接手路徑；不可只用整季 bullpen ERA |
| 球場／環境 | 多年滾動且分左右打的 park factor、溫度、風、濕度、屋頂 | 單季 park factor 要收縮；未知屋頂用情境混合 |
| 資料時點 | `as_of`、pre/post-lineup、來源與更新時間 | 不同快照分開評分與回測 |

### B 級：優先提升得分率與尾端分布

- **投手球質與健康訊號**：Stuff+、Location+、Pitching+ 或等價 pitch model；四縫線／伸卡球速變化、release point、extension、IVB／水平位移、pitch mix 與單場球數。近期修正必須有球質、角色或健康機制，不能只因 ERA 連續兩場變好。
- **打者接觸品質**：投影 xwOBA／wOBA、K%、BB%、Barrel、EV50、Squared-Up、Blast、bat speed 與 swing length。高度共線的指標視為同一證據群，不得重複加權。
- **球種對位**：把對手打線對實際球種、速度帶、移動方向與投手臂角的能力作小幅修正；原始 batter-vs-pitcher 對戰紀錄不作主要特徵。
- **守備與捕手**：正式守位的 Fielding Run Value／OAA、外野臂力、捕手 blocking、throwing 與 framing，換算為每場小幅 run adjustment 並強收縮。
- **跑壘**：Baserunning Run Value、盜壘／額外壘包能力與對手捕手、投手控跑組合；主要影響一分差與尾端分布。
- **先發退場機制**：預期打者數、TTO、左右打序、教練換投傾向與下一層後援品質；前五局也可能含牛棚，不能假設先發必投滿五局。

### C 級：只在資料可靠且回測有效時納入

- 東向跨時區旅行、抵達後休息日、夜賽後日賽與長途客場尾段。
- 主審好球帶、壘上判決傾向與場地細節。
- 2026 起的 ABS 挑戰能力與剩餘挑戰策略。ABS 會修正部分高張力好球帶錯判，因此主審與 framing 權重不得直接沿用 2025 前資料；應分制度版本回測。
- 教練戰術、代打深度、守備替換與延長賽自動跑者策略。

## 4. 收縮與禁止項目

- 以投影先驗為主，近期資料只修正可觀察的能力／角色改變。取消固定的「近 14 天 25%、第 15–30 天 15%」全域權重。
- 左右投拆分使用投影或階層收縮；少量對左投 PA 不得直接當真實能力。
- xERA、xwOBA、Barrel、HardHit 與 EV 同屬接觸品質家族；FIP、xFIP、K-BB% 也高度重疊。每個家族只在模型中保留經驗證的表示方式。
- 不使用近期勝敗、投手勝投、未調整對手強度的 ERA、單場得失分、星期幾拆分、原始 BvP 或搜尋摘要作主要特徵。
- 市場價格不得進入生產模型；賽後可用去水 closing line 作獨立 benchmark，但不得回填到原預測。

## 5. 分布與模擬

- 前五局與後四局分開建模；後四局加入先發提前退場與牛棚路徑。
- 不預設獨立 Poisson 足夠。用歷史 walk-forward 比較 Poisson、negative binomial、Poisson-lognormal 或其他離散模型，依 log loss、得分分布校準與區間覆蓋選擇。
- 模型需容許共同天氣／球場環境造成雙方得分正相關，並納入主隊領先時不打九局下、延長賽自動跑者與 walk-off 截尾。
- 使用 `scripts/simulate_scores.py` 時，validated-production 的各階段期望得分與波動參數必須來自回測；public baseline 則必須由 `build_public_baseline.py` 依同季已完賽資料確定性估計。兩者都不得臨場猜值。模擬器只負責把已建立的 run means 轉成一致的市場機率。
- `f5_mean` 是前五局均值；`late_mean_6_to_9` 是假設四個後段半局都完整進行時的排程均值。腳本再處理九局下省略與 walk-off，因此輸出的實際全場均值通常略低於兩段直接相加。
- 先以 `python mlb-analysis/scripts/simulate_scores.py --demo` 檢查輸入結構；demo 參數只供 smoke test，禁止拿來預測真實比賽。
- 輸出雙方期望得分、總分中位數、50%／80% 區間與主要機率。精確比分只在使用者要求時列出最可能的 1–3 個比分及其個別機率，不得把 modal score 寫成高信心「預測比分」。

## 6. 因素帳本

每次建模在內部保存下列欄位；找不到可靠映射時填 `N/A`，不要補數字：

| 階段 | 聯盟基準 | 打線投影 | 先發／牛棚修正 | 球場天氣 | 守備捕手跑壘 | 旅行規則 | 最終均值 | 來源／版本 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| 客隊前五局 | ... | ... | ... | ... | ... | ... | ... | ... |
| 主隊前五局 | ... | ... | ... | ... | ... | ... | ... | ... |
| 客隊第 6 局後 | ... | ... | ... | ... | ... | ... | ... | ... |
| 主隊第 6 局後 | ... | ... | ... | ... | ... | ... | ... | ... |

任何人為修正都要記錄「改了多少 run mean、依據、有效期限」。若只能寫「高溫有利打者」卻沒有已驗證的轉換，保留為情境／不確定性，不改點估計。

## 7. 推薦閘門

- 正式打線未公布：只可在所有合理打線情境方向一致且價格優勢仍存在時給小注；其餘等待 `post-lineup`。
- 勝利組可用性未核對：不得主推全場獨贏、讓分或全場大小；可分析前五局。
- 先發球數／傷後限制未核對：不得主推前五局或全場。
- 屋頂、強風或降雨情境會翻轉大小分：不得主推大小分。
- 未有 validated-production，但 public baseline 可重現：可給標記為未校準的方向性勝率與區間；不得給 EV、投注推薦或正注碼。
- public baseline 也無法重現：數值填 N/A，逐場列出具體失敗原因。
- 合理情境的差異足以翻轉推薦或明顯改變 EV 時，對投注使用較保守端，不用點估計的完整優勢。

上述閘門只控制模型層級與投注推薦，不控制報告交付。排程確認有賽事時必須先嘗試 public baseline；自動流程不得發布「baseline 已成功但被報告清空」的全 N/A 版本。確實零場可產生數值時，只保存本地 `degraded` 產物與失敗狀態，不發布成正常每日預測；逐場保留 `status`、`missing_data`、`sources` 與資料截止時間，且不得納入機率評分。

## 8. 回測與升版

- 每場預測寫入不可覆寫紀錄：`game_id`、`predicted_at`、`first_pitch`、`snapshot`、`model_version`、主隊勝率、雙方 run means、分布區間、資料缺口與賽果。
- 使用 `scripts/evaluate_forecasts.py` 評估 Brier、log loss、雙方得分 MAE、總分 bias、區間 coverage 與 calibration bins。
- 舊版與新版只在同一批 game ID、同一 snapshot 做 paired walk-forward 比較。不得隨機切分後讓未來賽事資訊進入訓練。
- 去水 closing probability 只作賽後 benchmark。若新版只提高命中率但 Brier／log loss、得分 bias 或區間 coverage 變差，不得升版。
- 樣本少時報告 bootstrap 區間與不確定性；不因短期連勝或連敗改權重。

## 9. 資料與方法參考

- [FanGraphs Depth Charts](https://library.fangraphs.com/depth-charts/)：Steamer／ZiPS 與預期上場時間的 rest-of-season 基準。
- [FanGraphs Stuff+／Location+／Pitching+ primer](https://library.fangraphs.com/pitching/stuff-location-and-pitching-primer/)：pitch-level 球質與位置模型。
- [Baseball Savant Statcast Metrics Context](https://baseballsavant.mlb.com/statcast-metrics-context)：xwOBA、Barrel、EV50、Squared-Up、Blast 與 bat tracking 定義。
- [Baseball Savant Statcast Park Factors](https://baseballsavant.mlb.com/leaderboard/statcast-park-factors)：控制球員與手別的多年 park effects。
- [MLB Statcast Fielding Run Value](https://www.mlb.com/glossary/statcast/fielding-run-value)：把 range、throwing、framing、blocking 等轉為 run scale。
- [Baseball Savant ABS Dashboard](https://baseballsavant.mlb.com/abs)：2026 ABS 制度與挑戰指標。
- [MLB run-distribution 研究](https://journals.sagepub.com/doi/10.3233/JSA-140001)與 [travel／circadian 研究](https://pmc.ncbi.nlm.nih.gov/articles/PMC5307448/)只作建模候選；是否採用仍以本資料集的 walk-forward 表現決定。
