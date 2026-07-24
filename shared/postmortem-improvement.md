# 賽後檢討與預測改善契約

所有 `*-analysis` 的 `postmortem` 都必須套用本契約，再套用各項目的事件重建與領域歸因規則。

## 1. 目標與非目標

檢討的第一目標是提升未來樣本的機率品質與預測精準度，依序檢查 Brier score、log loss、領域主分布誤差與方向命中率。方向命中率只能輔助診斷，不可取代機率評分。

降低模型信心度、注碼、推薦等級或輸出語氣是風險控制，不是預測模型修正。單獨做這些調整不得宣稱精準度已提升，也不得作為 postmortem PR 的唯一內容。

## 2. 每次檢討的強制閉環

1. **鎖定基準版**：保存原快照、模型／skill 版本、原機率、主分布、信心度與當時可知資料；不得用賽後資訊重建假預測。
2. **建立誤差帳本**：逐場記錄實際結果、Brier／log loss 貢獻、實際結果原機率、方向命中、主分布殘差、情境覆蓋與資料缺口。
3. **找可重複機制**：把問題歸為資料／時序、特徵、權重、情境、相依分布、結算、實作或合理變異，並指出同類樣本如何再次觸發。隊名、單一比賽敘事或「爆冷」不是機制。
4. **做因子稽核**：每次都深查是否漏掉賽前可觀察、具合理機制且可能解釋重複誤差的因子；同時檢查既有因子或參考來源是否無增量預測力、重複計數、洩漏賽後資訊或只增加判斷噪音。不得因「資料越多越好」而直接加入。
5. **提出可否證假設**：每個候選修正都寫成「改變哪個輸入或計算 → 預期改善哪個 cohort／指標 → 可能傷害什麼 → 如何否決」。
6. **建立挑戰版**：實際修改資料管線、特徵、情境生成、權重、分布或計算；若證據不足以改生產規則，至少建立可重現的 challenger、測試或評估資料，不用降信心代替。
7. **同批比較**：以相同賽事 ID、相同預測時點、相同可用資料做 paired walk-forward／時間序列回測。新增因子用 add-one／challenger 檢查增量效益，既有因子用 leave-one-factor-out／ablation 檢查移除後是否改善；不得挑選新版有利場次，也不得讓賽後資訊進入特徵。
8. **裁決**：只有通過下節門檻才升版；未通過就拒絕 challenger，保留診斷與下一個資料需求。不得因已投入時間而合併。

誤差帳本與 evaluated forecasts 必須跨日持久保存，不得和短期報告一起清除。每日檢討先讀同版本、同 snapshot 的歷史 cohort，再加入本批；只評單日資料不得宣稱已完成模型校準或精準度改善。

## 3. 修正與升版門檻

- 資料、時序、結算、相依機率或程式實作錯誤可立即修正，但必須加入能在舊版失敗、新版通過的回歸測試或固定稽核案例。
- 特徵、權重、先驗、情境機率或分布變更必須做 paired walk-forward。主要指標需改善，且重要 cohort、次要指標、coverage 與預測可用率不得出現實質退步。
- 樣本足夠時報告 paired 差值與 bootstrap 區間；樣本不足時不得宣稱已提升精準度，只能標記 `experiment-only` 並累積 forward sample。
- 新版若只是把機率拉向 50%、壓低信心、加寬區間或減少推薦，必須證明 Brier／log loss 或分布 coverage 在相同樣本改善；否則拒絕。
- 修正不得只記住某隊、某球員或某次比分。規則必須以賽前可觀察條件觸發，並能套用到未見樣本。

## 4. 因子與參考資料生命週期

因子治理只適用於可選的預測因子與預測性參考來源。賽事身分、賽程、正式名單／先發、版本、結算與實際賽果等完整性資料，即使本身不提供增量預測力，仍須保留供快照、驗證與結算使用，不得誤判為噪音而移除。

每次正式檢討都要完成兩個方向的搜尋：

1. **漏項搜尋**：從資料缺口、交互作用、制度／版本變化、情境權重與分布殘差檢查可能漏掉的機制。新想法先列為 `candidate`；只有具賽前可觀察觸發條件、可重現定義，且 add-one 挑戰版在樣本外帶來增量改善時才改為 `active`。
2. **噪音搜尋**：檢查 `active` 因子是否無增量效益、與其他因子重複、來源不穩定、容易造成過度反應或產生洩漏。只有 ablation／paired walk-forward 顯示移除後主要指標改善且重要 cohort 無實質退步，或證實資料／時序／洩漏錯誤時，才改為 `retired`。

因子狀態必須跨日保存於 `factor-registry.json`：

- `active`：可抓取、判斷並影響機率。
- `candidate`：只在隔離 challenger／shadow 評估，不影響正式機率或對外判斷。
- `retired`：停止抓取、判斷、報告與影響機率；保留原定義、停用證據、決策日期及 `revisit_triggers`，不得刪除紀錄。

登錄檔使用以下最小結構；既有紀錄只能轉換狀態，不得整筆刪除：

```json
{
  "schema_version": 1,
  "updated_at": "ISO-8601",
  "factors": [{
    "factor_id": "穩定且唯一的-kebab-id",
    "name": "人類可讀名稱",
    "kind": "predictive_factor|predictive_source",
    "status": "active|candidate|retired",
    "used_for_prediction": false,
    "mechanism": "為何可能影響賽前分布",
    "pre_match_observable": "不含賽後資訊的可重現定義",
    "evidence": ["回測、ablation 或資料品質證據"],
    "decision_reason": "保留、候選或停用原因",
    "revisit_triggers": ["只有 retired 必須非空"],
    "last_reviewed": "ISO-8601"
  }]
}
```

只有 `active` 的 `used_for_prediction` 可為 `true`；其他狀態固定為 `false`。新項目一律先進 `candidate`。初次建立登錄檔時，可把已存在於正式流程的因子盤點為 `active`，但不得藉初始化偷偷加入新因子。

不得每天無條件重審所有 `retired` 因子，也不得為了找重啟訊號而恢復專屬抓取或日常判讀。只有既有 active／完整性資料、外部新證據或使用者提供資訊顯示其預先記錄的可觀察重啟條件成立，例如資料品質修復、樣本門檻達成、版本／制度切換、交互作用假設出現新證據，才重新開為 challenger。`retired → active` 必須重新做不含賽後洩漏的 paired walk-forward，證明樣本外增量改善；不能因單場結果或事後故事撿回。

若證據不足，保持原狀並記錄下一個可否證資料需求。沒有因子異動也必須在 postmortem 說明本次漏項搜尋與噪音搜尋的結論。

## 5. PR 證據契約

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
  "factor_audit": {
    "omission_search": "本次如何搜尋漏掉的因子與結論",
    "noise_review": "本次如何檢查無效／有害因子與結論",
    "new_candidates": [],
    "activated": [],
    "retired": [],
    "restored": []
  },
  "evidence": ["可追溯證據或評估產物"],
  "rollback": "回退條件或 N/A"
}
```

建立 PR 時：

- `decision` 必須是 `merge`，`change_type` 不得是 `none`，`confidence_or_stake_only` 必須是 `false`。
- `predictive_mechanism`、`evidence` 與 `rollback` 不得為空，且 `validation.passed` 必須為 `true`。
- 生產特徵、權重、先驗或分布變更使用 `paired_walk_forward`；資料／結算／實作 bug 可使用 `regression_test`。
- 新增、停用或恢復正式因子都是生產模型變更，必須使用 paired walk-forward；只新增 `candidate` 不算生產變更。
- PR 摘要必須回答：舊版錯誤機制、實際修正、基準版 vs 挑戰版、驗證範圍、已知退步與回退條件。

差異應是「最小充分修改」，不是追求行數，也不是預設越小越好。沒有證據支持生產修改時，不建立裝飾性 PR；建立 experiment-only 產物並清楚說明尚未提升精準度。

## 6. 禁止的替代品

以下內容可以作附帶風控，但不能取代模型改善：

- 因為猜錯就固定扣信心、設勝率上限或把機率往 50% 拉。
- 只降低注碼、取消推薦、提高 EV 門檻或改成保守措辭。
- 不重建主分布，只手動加寬尾端、提高爆冷或橫掃機率。
- 只新增賽後故事、隊伍特例、VOD 描述或輸出章節，沒有可執行的賽前觸發條件。
- 因單場猜錯就新增因子，或因單場猜對就恢復已停用因子。
- 直接刪除無效因子的歷史紀錄，導致日後無法辨識重啟條件或重做樣本外驗證。
- 只報修改行數、命中數或單日 ROI，沒有同快照基準版與挑戰版比較。
