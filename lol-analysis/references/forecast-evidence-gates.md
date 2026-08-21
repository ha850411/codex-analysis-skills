# 預測證據與時點資格閘門

`full` 與 `daily-summary` 在鎖定機率前執行本閘門。目標是防止跨聯賽／跨階段版本快取、舊名單覆蓋最近正式先發、近期狀態挑樣本、漏掉最可比的直接交手、隱藏模型集成權重、比分主分布與摘要漂移，並把開賽後重建混入正式賽前績效。新快照使用 schema v5；v1–v4 只供既有歷史 artifact 重播。

## 1. 保存 evidence snapshot

每場在當次輸出目錄寫入 `forecast-evidence.json`；互動式分析未指定目錄時，使用 `.automation-state/lol/manual-forecasts/<YYYY-MM-DD>/<timestamp>/`。保留：

- `match_key`、`scheduled_start`、可取得時的 `actual_start`、`predicted_at`、`snapshot`。
- `competition` 保存 league、event、stage、format；`patch_context` 的 scope 必須逐字對應，禁止用日報頂層共用版本代替逐場證據。
- `patch_context.status=confirmed` 時保存單一版本、查核時間與至少一個官方規章／公告／比賽頁來源；每個來源同時保存 league、event、stage 與 `checked_at`。只有第三方同週賽後頁不得宣告 confirmed。
- 版本來源衝突無法消解時使用 `status=scenario`，保存衝突與至少兩個版本情境、權重及證據；權重合計為 1。不得把舊週、舊 Split 或其他賽區版本快取寫成當場確認值。
- 雙方最近正式系列使用穩定 `series_key`，保存日期、實際五人、來源與 `checked_at`。
- 每隊另存 `recent_series`：scope 必須對應本場 league／event；保存查找時間、`search_complete=true`，以及同一賽事最新兩個系列的 `series_key`、日期、對手、比分、賽制、版本、實際五人、來源與 `checked_at`，按新到舊排序。不足兩場時列出全部並保存 `insufficient_reason`；不得用較早的亮眼系列跳過更晚一場。
- 本場預估／公告五人；`projected_lineup` 保存 `status=confirmed|projected`、`source_kind`、來源與 `checked_at`。`confirmed` 只接受當場官方名單／隊伍公告；`projected` 必須另存晚於快照、早於開賽的 `recheck_by`。與最近五人不同時，保存晚於最近系列且早於預測快照的 `published_at`、來源、原因與 `checked_at`；不得用重新查閱舊頁面的時間冒充新公告。
- 明列 `lineup_uncertainties`，沒有可信分歧時保存空陣列；有分歧時保存隊伍、位置、候選人、各情境權重、該情境系列賽機率、證據、`recheck_by` 與解決條件。權重合計必須為 1，`recheck_by` 必須早於開賽。
- 近 30 天直接交手搜尋結果、來源與 `checked_at`。同賽事、可比陣容的交手要保存逐局勝方、選邊、BP 與可重複機制。
- 保存 `model_ensemble`：目標隊伍、至少 `baseline_prior`、`recent_event`、`underdog_countermodel` 三個模型的具名輸出、預定權重與證據，以及由加權公式自然得到的中央點與模型 spread。`recent_event.evidence_refs` 必須引用雙方 `last_series.series_key` 與全部已保存的同賽事近期 `series_key`，避免正文只挑有利樣本。存在可比直接再戰時，另加入與 H2H artifact 輸出／權重一致的 `direct_rematch` 模型。
- 保存 `series_distribution.outcomes`：以 `teams[0]-teams[1]` 的比分方向列出該賽制全部互斥結果；`reported_mode` 必須是最高機率比分。目標隊獲勝結果之和須等於 `model_ensemble.central_probability`，並與 `probability-checks.json` 及置底簡表逐場一致。
- `evaluation_status`與投注決策。

執行：

```bash
node lol-analysis/scripts/validate_forecast_evidence.mjs <forecast-evidence.json>
```

驗證失敗時不得鎖定機率、發布 Notion 或給注碼。

`daily-summary` 不得以逐個 CLI 曾經成功或對話中的文字宣告代替整批驗證。完成 `prediction.md` 與 post-market 決策後，必須讓同一 artifact 目錄通過 `validate_daily_run.mjs`；它會重新驗證 schema v5 evidence，並核對 schedule、probability checks、decision slate、比分主峰與報告的逐場集合及信心度。任一隊 `projected_lineup.status=projected` 或仍有未解 `lineup_uncertainties` 時，對應決策不得為 `bet_now`；先發布條件版，正式先發落定後建立 post-lineup 新快照。

## 2. 版本溯源閘門

- 版本是「聯賽 × 賽事 × 階段」欄位，不是日期或整份日報的單一常數。即使同一天其他賽區仍用舊版，也不能推定本場相同。
- 官方來源仍顯示舊版、同階段新比賽卻顯示新版時，先查改版生效公告；無法消解即建立版本情境，停止所有依賴單一版本的英雄優先級加減分。
- v3 驗證器只證明來源角色、scope、時間與情境權重可重播，不會替來源內容背書；產生 artifact 的流程仍須實際打開來源核對。

## 3. 名單溯源閘門

- 最近正式系列的實際五人是 `pre-lineup` 的預設主情境；另搜尋過去 30 天同賽事實際使用過的同位置先發與已登錄核心替補。近期曾上場者不得因不在最新兩個系列就從候選集合消失。
- 預估五人不同時，只接受發布時間晚於最近正式系列、早於快照的當場公告、隊伍／賽區輪替公告，或更新且可追溯的當場資料。
- 只有賽季 roster、較舊交手、限制名單或無來源印象時，維持最近實際五人；如果仍存在真實分歧，建立先發情境而不單點覆寫。
- 不得只在正文寫「某人上場上修 3–4%」。可行替代先發必須進入可重播情境；正式資訊落定後依 `recheck_by` 建立 `post-lineup` 新快照。未完成重查時，舊 `pre-lineup` 版只能標為條件版，不得冒充最終先發版。

## 4. 直接再戰閘門

近 30 天內同一賽事、核心陣容可比的 H2H 是必要證據，不是可選叙事。

1. 逐局檢查勝方、藍紅方、關鍵 BP、前期起手與收尾。
2. 把弱方已成功的結構拆成可重複與不可重複；不把單次重擊／偷巴龍當成穩定路徑。
3. 建立具名 `direct-rematch` 反模型，明示機率所屬隊伍，並保存輸出與預定集成權重。本閘門不預設 H2H 權重或機械調整機率。
4. 找到可比 H2H 卻沒有逐局證據時，停止新預測；來源無法存取時標記缺口、觸發非補償式信心上限，且不得宣稱高完整度。
5. `factor-registry.json` 若仍把 `direct-rematch-mechanism-persistence` 列為 `candidate`，正式模型可把 H2H 作為收縮先驗，但不得以「上次成功機制必然延續」另加權；重賽後是否仍有效只進 shadow challenger，直到 paired walk-forward 通過升版門檻。

## 5. 集成可重播閘門

- 中央機率必須等於保存模型的加權和，權重合計為 1；spread 必須等於同一組模型的最大值減最小值。
- 直接再戰模型不得只存在於 H2H 區塊或正文，卻從中央集成消失；反之也不得在集成中使用無逐局證據的 `direct_rematch`。
- 驗證器只證明 artifact 與計算可重播，不證明權重有樣本外增量。權重變更仍須 paired walk-forward；資料／時序與計算落盤缺失可用固定回歸案例立即修正。

## 6. 預測時點資格

- `predicted_at < actual_start`且未接觸 live 資訊：`prospective_pre_match`，可進入 Brier、log loss、ROI 與 calibration cohort。
- 開賽後才產生或重建：`reconstructed_after_start`，只做定性檢討，注碼必須為 0u，不得與正式賽前績效合併。
- `actual_start` 未取得時暫以排定時間分類；賽後取得實際開賽時間後要重新結算資格。
- 尚未完賽或結果未確認時標記 `pending_result`，不得以當前 live 比分計入方向、Brier、log loss、ROI 或校準。

## 7. 賽後回收

賽後同時輸出「對外發布集」與「正式賽前評分集」的 N。若兩者不同，明列排除的 `match_key`與原因；不得因為開賽後重建命中而改善正式指標。
