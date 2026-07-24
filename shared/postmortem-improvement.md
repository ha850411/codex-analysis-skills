# 賽後檢討與預測改善契約

所有 `*-analysis` 的 `postmortem` 都必須套用本契約，再套用各項目的事件重建與領域歸因規則。

## 1. 目標與非目標

檢討的第一目標是提升未來樣本的機率品質與預測精準度，依序檢查 Brier score、log loss、領域主分布誤差與方向命中率。方向命中率只能輔助診斷，不可取代機率評分。

降低模型信心度、注碼、推薦等級或輸出語氣是風險控制，不是預測模型修正。單獨做這些調整不得宣稱精準度已提升，也不得作為 postmortem PR 的唯一內容。

## 2. 每次檢討的強制閉環

1. **鎖定基準版**：保存原快照、模型／skill 版本、原機率、主分布、信心度與當時可知資料；不得用賽後資訊重建假預測。
2. **建立誤差帳本**：逐場記錄實際結果、Brier／log loss 貢獻、實際結果原機率、方向命中、主分布殘差、情境覆蓋與資料缺口。
3. **找可重複機制**：把問題歸為資料／時序、特徵、權重、情境、相依分布、結算、實作或合理變異，並指出同類樣本如何再次觸發。隊名、單一比賽敘事或「爆冷」不是機制。
4. **提出可否證假設**：每個候選修正都寫成「改變哪個輸入或計算 → 預期改善哪個 cohort／指標 → 可能傷害什麼 → 如何否決」。
5. **建立挑戰版**：實際修改資料管線、特徵、情境生成、權重、分布或計算；若證據不足以改生產規則，至少建立可重現的 challenger、測試或評估資料，不用降信心代替。
6. **同批比較**：以相同賽事 ID、相同預測時點、相同可用資料做 paired walk-forward／時間序列回測。不得挑選新版有利場次，也不得讓賽後資訊進入特徵。
7. **裁決**：只有通過下節門檻才升版；未通過就拒絕 challenger，保留診斷與下一個資料需求。不得因已投入時間而合併。

誤差帳本與 evaluated forecasts 必須跨日持久保存，不得和短期報告一起清除。每日檢討先讀同版本、同 snapshot 的歷史 cohort，再加入本批；只評單日資料不得宣稱已完成模型校準或精準度改善。

## 3. 修正與升版門檻

- 資料、時序、結算、相依機率或程式實作錯誤可立即修正，但必須加入能在舊版失敗、新版通過的回歸測試或固定稽核案例。
- 特徵、權重、先驗、情境機率或分布變更必須做 paired walk-forward。主要指標需改善，且重要 cohort、次要指標、coverage 與預測可用率不得出現實質退步。
- 樣本足夠時報告 paired 差值與 bootstrap 區間；樣本不足時不得宣稱已提升精準度，只能標記 `experiment-only` 並累積 forward sample。
- 新版若只是把機率拉向 50%、壓低信心、加寬區間或減少推薦，必須證明 Brier／log loss 或分布 coverage 在相同樣本改善；否則拒絕。
- 修正不得只記住某隊、某球員或某次比分。規則必須以賽前可觀察條件觸發，並能套用到未見樣本。

## 4. PR 證據契約

每次自動檢討都產生 `improvement-plan.json`，至少包含：

```json
{
  "objective": "out_of_sample_predictive_accuracy",
  "change_type": "data_pipeline|feature_model|distribution|calibration|evaluation_infra|none",
  "decision": "merge|experiment-only|no-change",
  "production_change": false,
  "confidence_or_stake_only": false,
  "predictive_mechanism": "修正如何影響未來賽前機率；無修正時說明缺少什麼證據",
  "baseline": {"model_version": "版本或 N/A", "sample_size": 0, "metrics": {}},
  "challenger": {"model_version": "版本或 N/A", "sample_size": 0, "metrics": {}},
  "validation": {"method": "paired_walk_forward|regression_test|forward_test|none", "passed": false},
  "evidence": ["可追溯證據或評估產物"],
  "rollback": "回退條件或 N/A"
}
```

建立 PR 時：

- `decision` 必須是 `merge`，`change_type` 不得是 `none`，`confidence_or_stake_only` 必須是 `false`。
- `predictive_mechanism`、`evidence` 與 `rollback` 不得為空，且 `validation.passed` 必須為 `true`。
- 生產特徵、權重、先驗或分布變更使用 `paired_walk_forward`；資料／結算／實作 bug 可使用 `regression_test`。
- PR 摘要必須回答：舊版錯誤機制、實際修正、基準版 vs 挑戰版、驗證範圍、已知退步與回退條件。

差異應是「最小充分修改」，不是追求行數，也不是預設越小越好。沒有證據支持生產修改時，不建立裝飾性 PR；建立 experiment-only 產物並清楚說明尚未提升精準度。

## 5. 禁止的替代品

以下內容可以作附帶風控，但不能取代模型改善：

- 因為猜錯就固定扣信心、設勝率上限或把機率往 50% 拉。
- 只降低注碼、取消推薦、提高 EV 門檻或改成保守措辭。
- 不重建主分布，只手動加寬尾端、提高爆冷或橫掃機率。
- 只新增賽後故事、隊伍特例、VOD 描述或輸出章節，沒有可執行的賽前觸發條件。
- 只報修改行數、命中數或單日 ROI，沒有同快照基準版與挑戰版比較。
