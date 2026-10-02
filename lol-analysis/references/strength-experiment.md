# 固定數值版本的配對實驗

新預測或系統性復盤使用。這個入口解決「已有候選計畫，卻沒有實際數值對照」的缺口；不取代領域研究，不把事後重播算成前瞻命中。

## 目前方法與使用範圍

`scripts/paired_strength.py` 的 `lol-joint-strength-v1` 是 **shadow-only** 候選。最近裁決及固定版本保存在 `.automation-state/lol/history/strength-experiment.json`，完整試驗留在該檔指向的 review。先讀裁決，再執行；開發測試未通過的候選不能因某一場算對、檔案已存在或公式可重播而成為主預測。

候選只使用原比分基準同一份 history、同一截止、同一事件／隊序；不擴大歷史時間窗、不補賽後資料、不加隊名特例。對每個系列以地圖勝率 `y = a/(a+b)` 為目標、每系列一個權重，共同估計各隊強度：

`p(A贏單局) = logistic(s_A − s_B)`

最小化所有系列的交叉熵，加 `0.5 × Σs²`；L2 係數固定為1，不按本場、賽區或當批結果調整。這是可重現的正則化 Bradley–Terry 實驗，係數1是固定設計選擇，並非已驗證的最佳值。零對手消融版以相同資料與正則化、把每隊對手強度固定為0，單獨保存。

完整 BO3／BO5 分布沿用固定單局率的系列樹。因此它只檢驗強度估計，**沒有新增 BP、輪替、Fearless 或局間解題係數，也沒有修好總局數模型**。兩隊缺樣本、對手比較網路不相連、歷史比分非法，或原 history 無法重現原基準時，記失敗及原因；不能排除該場以提高命中率。

## 新預測實際執行

新分析者情境優先一次生成主預測與配對，避免只寫計畫而漏跑：

```bash
python3 lol-analysis/scripts/analyst_forecast.py build-paired analyst-input.json \
  --history history.json --output forecast.json --pair-output-dir strength-pair
```

原主分布保持原分析者輸入，固定候選獨立保存；先驗證整包再寫出，配對失敗不留下一份看似已完成的主預測。既有有效主快照或比分基準則在取價前執行：

```bash
python3 lol-analysis/scripts/paired_strength.py pair \
  --control /absolute/run/forecast.json \
  --history /absolute/run/history.json \
  --output-dir /absolute/run/strength-pair
python3 lol-analysis/scripts/paired_strength.py verify /absolute/run/strength-pair
```

`control` 可為原分析者情境或原比分基準。工具先重播原情境與原比分基準，再保存原主預測、原基準、候選、消融版、訓練輸入、實際建立時間、資料截止與程式雜湊；不改原 forecast。市場與本場賽果不得作輸入。輸出採 create-only；內容改變另建目錄，不能覆寫舊配對。

CLI 使用真實 UTC 時間判定前瞻資格，不接受自訂建立時間。開賽後拒絕以賽前樣本保存；已有配對驗證只重播，不重新宣告發布。`forward_sample` 只標記賽前計算，正式回收仍須依 postmortem 契約核對主預測的發布證據。

若當前候選只限影子測試，繼續依原方法交付一個主方向；不得看到候選方向後，挑選較符合敘事或賽後較準者。輸出與注碼偏好維持原契約，不把新增模型當成追加買對手的理由。

## 歷史驗證與裁決

歷史重播使用相同指令加 `--replay`，保留原 cutoff、以當下真實時間建立 `historical_replay`。已看過的12場或後續用來改公式的資料，一律是開發集；不把時間截止正確的重播稱作未見樣本測試。

對照至少分開：原主預測、原比分基準、固定候選、零對手消融。以相同事件母體評勝方、比分、Brier、log loss、coverage，按賽區／BO／snapshot 分組；缺候選的場次仍留在分母。候選在被點名的兩場改善、全批退步時，必須報告全批，拒絕直接替換。

候選參數調整建立新版本、保存被否決版本與試驗次數；不在同批反覆找最佳係數後宣稱改善。只有共用配對門檻與重要 cohort 都通過，才可提出升版。工程測試通過、研究完成、前瞻精準度改善分別保存。

回收同一實驗時，先查各 run 的 `strength-pair/pair-audit.json` 與既有跨日結果；不得再以另一份文字 candidate-plan 取代實際生成的成對快照。只有確切數值配對及結果證據，才增加實驗樣本數。
