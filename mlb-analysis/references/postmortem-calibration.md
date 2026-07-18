# MLB 賽後檢討與模型校準

賽後檢討的目標是找出可重複的資料、特徵、分布或決策錯誤，不是用最終比分證明賽前某個方向「必然錯」。勝率 56% 的球隊落敗本身不是模型故障；必須檢查一批不可覆寫的機率是否校準。

## 1. 先取得原始預測紀錄

每筆紀錄至少包含：

- `game_id`、`predicted_at`、`first_pitch`、`snapshot`、`model_version` 與資料來源版本。
- 客／主隊前五局與第 6 局後 run means、情境權重、分布參數與正式打線狀態。
- 全場主隊勝率、前五局三路、所分析盤口的 win／push／loss 機率、雙方得分 80% 區間與模型信心度。
- 市場價格只作當時 EV 紀錄；去水 closing probability 只能在賽後另欄保存作 benchmark。

找不到原紀錄時，明確標註「無法做正式校準」；只能做流程稽核，不得憑先前文字摘要重建假精準機率。

## 2. 重建當時可知的快照

- 核對當時 probable／正式先發、球數或局數限制、正式打線、守位與捕手、牛棚近三日球數、天氣、屋頂、旅行與 ABS 是否適用。
- 比對資料公布時間；比賽中或賽後才出現的傷情、球速下降或臨時策略不能回填成賽前已知。
- `pre-lineup`、`post-lineup`、臨時換投、opener、bullpen game、雙重賽與延賽各自成 cohort。

## 3. 重建比賽事件，但避免結果偏誤

- 先發：實際 BF／局數、球數、球速、球種、位置、揮空、保送、被打品質、TTO 與退場原因。
- 打線：正式打序、左右投對位、bat speed／contact quality 的已知趨勢、傷後狀態、守備／跑壘與代打。
- 牛棚：預期路徑與實際路徑、高張力投手是否可用、連投、手別 matchup 與教練換投。
- 環境：實際風、溫度、屋頂與 ABS 挑戰；只有賽前可觀察部分能歸為輸入錯誤。
- 變異：BABIP、守備失誤、滿壘殘壘、單次全壘打與 walk-off 要和持續性的 contact／command 反向分開。

## 4. 批次評分

把 JSONL／JSON 預測紀錄交給：

```bash
python mlb-analysis/scripts/evaluate_forecasts.py forecasts.jsonl
python mlb-analysis/scripts/evaluate_forecasts.py forecasts.jsonl --compare old-version new-version
```

主要指標：

- 全場獨贏：Brier 與 log loss；directional accuracy 只作診斷。
- 得分：客／主隊 run MAE、總分 MAE、客／主／總分 bias。
- 分布：80% 區間 coverage 與寬度、calibration bins；不能靠把區間無限放寬取得 coverage。
- 前五局與盤口：使用各自的三路或 win／push／loss Brier；不可把平手、走盤當輸。
- 精確比分命中率只作附帶診斷，不是模型升版目標。

所有 cohort 依 `snapshot`、model version、先發狀態、球場／屋頂、ABS 制度與信心區間拆分。小樣本須保留 bootstrap 區間，不宣稱已校準。

## 5. 錯誤歸因

| 類型 | 判斷方式 | 修正 |
| --- | --- | --- |
| 資料／時序 | 先發、打線、球數限制、牛棚、屋頂或時間抓錯 | 修資料管線與 freshness gate，立即生效 |
| 基準能力 | 用近期 ERA／OPS 取代投影，或季初 run environment 未收縮 | 回到 projection prior，重新 walk-forward |
| 投手工作量 | 預期 BF、TTO、傷後限制或 hook timing 偏誤 | 分離能力與工作量模型 |
| 牛棚路徑 | 用整體 ERA 代替個別可用率、手別與 leverage | 建立 reliever-level 情境 |
| 打線／守備 | 打序 PA 權重、platoon 收縮、捕手／FRV／跑壘遺漏 | 只加入能轉成 run value 且回測有效者 |
| 環境／制度 | park、風、屋頂、旅行或 2026 ABS 係數跨制度使用 | 依手別、場地與制度版本重估 |
| 分布 | 獨立 Poisson 尾端過窄、雙方相關性、九局下或延長賽漏建 | 比較離散候選模型與 coverage |
| 市場洩漏 | 先看盤後手調模型勝率 | 丟棄污染快照，重跑純模型 |
| 合理變異 | 流程與 contact／command 方向合理，但單場結果落在尾端 | 累積樣本，不改權重 |

## 6. 升版規則

- 只在相同 game ID、相同 snapshot 的 paired walk-forward 資料比較新舊版。
- 新版至少需在 Brier／log loss 中顯示改善，且 team-run MAE、total bias 與 interval coverage 沒有具實質性的退步；改善若只出現在挑選後的場次，不得升版。
- closing line 只作外部基準：它可以揭露模型落後市場，但不能成為下一版的未標記特徵。
- 前五局正確、全場錯誤時先查牛棚與後段分布；總分均值正確但極端比分太多時先查 dispersion／尾端，不推翻全部能力估計。
- 每次升版保留舊 model version、係數、資料截止與評估報告；不得覆寫歷史紀錄。

## 7. 對使用者的檢討輸出

依序說明：可否取得正式原快照、賽果與實際事件、批次評分、可預見錯誤、合理變異、具體修正與是否通過升版條件。若只有單場資料，結論只能是「流程錯誤已確認」或「校準警報待累積」，不能宣稱模型整體已改善。
