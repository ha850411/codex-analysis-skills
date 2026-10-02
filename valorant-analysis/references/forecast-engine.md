# Valorant v3 實驗引擎

用於新計算與模型實驗；不修改 `output-template.md`、共用 schema 或其他運動模型。`scripts/valorant_forecast.py` 只執行本地計算，不抓盤、不發布、不自動升為 production。既有 v1、共用 v2 與歷史快照保留原入口。

## 能力與限制

- 對手調整：共同擬合雙方隊伍強度與 team×map 效果；每個系列的總訓練權重為一，再按時間衰減。不把系列結果與地圖資料重複加分。
- 條件特徵：可擬合 Patch×team×map、五人組合、逐圖 player→agent 配置、開局攻守方。以 ridge 收縮，缺資料或未見組合回到較上層效果。它不是完整選手能力、特務對位或 IGL 因果模型。
- 禁選：按同圖池、同 BO、同隊行動次數的 `available_before` 計算偏好，向歷史整體收縮。精確枚舉至多七圖的合法路徑，保存完整路徑質量與來源。未知首動權有該兩隊樣本時用歷史頻率估計，須標為假設；無樣本不填無依據的 50/50。
- 主分布：交叉逐圖名單與 veto 情境，生成 BO1／BO3／BO5 完整終局。系列勝方、比分與市場都從此分布導出；逐圖條件勝率按「實際走到該圖」加權，不混同被選入機率。
- 相依性：預設為獨立控制組。`fit_correlation=true` 才在訓練資料內另留時間後段選共同狀態幅度；不足 20 場完整校準系列時仍為零。這不是外層樣本外驗證。
- 暫未支援 live、讓圖起始優勢、八圖以上圖池，遇到時拒絕套用。veto 的名單交互作用、pick owner 的獨立勝率效果、高維特務對位與回合經濟尚未擬合，必須揭露。
- 預設正則化、衰減與平滑參數只是預先固定的候選設定，未宣稱最佳化。算法修改須更新 engine version；新設定使用新的 model version。不要依當場想要的選邊倒推參數。

## 資料契約

歷史輸入沿用共用契約的陣列（或 `{ "history": [...] }`）。每筆保留穩定 `event_id`、A/B `participants`、合法 `score`、`best_of`、`completed_at`、`available_at`、`result_status=final` 與 `source_url`。

可選地圖資料：

```json
{
  "map": "Map X",
  "winner": "Team A",
  "available_at": "2026-08-01T12:00:00Z",
  "context_available_at": "2026-08-02T12:00:00Z",
  "context": {
    "patch": "verified-patch",
    "lineups": [["a1", "a2", "a3", "a4", "a5"], ["b1", "b2", "b3", "b4", "b5"]],
    "a_start_side": "attack"
  }
}
```

上例為資料形狀示意，不能作正式來源。`agents` 如提供，為 A/B 兩個完整 `{player: agent}` 字典，須對應當圖五人。未知項目省略，不能填推測為已確認。`map_data_verified_at` 是舊歷史資料的地圖可用時間降級欄位；地圖時間與後補 context 時間各自檢查。只知道系列比分時仍可提供隊伍層觀測，不生成假的具名地圖。

歷史 `veto` 為 `{pool, available_at, actions}`；每個 action 保存 `{team, action: ban|pick|decider, map, available_before}`。`team` 使用 canonical 隊名，decider 為 null。需完整消耗圖池，且所選地圖與已知賽果相符。

`import-archive` 可讀既有 run 的 `history.json`、`matches-complete.json` 及 `sources/match-ID-meta.json`，校驗收據中的原始 HTML 雜湊，解析逐圖五人／特務與完整 veto。縮寫只能依傳入 `team_aliases` 對應，不自行模糊猜隊名。保留更早的地圖勝敗可知時間，新名單／Patch 等 metadata 使用封存收據時間，不能將今天取得的內容回填為當時可知。

雜湊不符時拒絕匯入，不能改寫收據使其通過。若找到同場另一個可信封存，可明示 `source_overrides: {"vlr-ID": "/absolute/older-run"}`；工具一併切換該場解析資料與原始收據，保存覆蓋來源及 hash，仍檢查可知時間。

## 本場輸入

沿用共用 event 欄位，加上：

- `map_pool`：當場具名完整圖池；`input_evidence_ids` 引用支持結構化資料的既有 evidence。
- `contexts_by_map`：每張圖的上述 `context`。它們是本場賽前假設；來源與未確認狀態須在原有分析／風險欄揭露。
- `roster_scenarios`（選用）：`id`、`weight`、`contexts_by_map`、`evidence_ids`、`weight_source`、`weight_basis`。五人／特務必須一致；六人名單以各圖五人表示。權重和為一，只允許 `confirmed`、`analyst_elicited` 或 `fitted` 的具名依據，全部保持 experiment。
- `veto` 或 `veto_scenarios` 二選一；不得以研究情境命中冒充主分布覆蓋。

由歷史估計的 veto 使用：

```json
{
  "veto": {
    "evidence_ids": ["event-rules"],
    "first_actor": null,
    "protocol": [
      {"actor": "first", "action": "ban"},
      {"actor": "second", "action": "ban"},
      {"actor": "first", "action": "pick"},
      {"actor": "second", "action": "pick"},
      {"actor": "first", "action": "ban"},
      {"actor": "second", "action": "ban"},
      {"actor": null, "action": "decider"}
    ],
    "observed": []
  }
}
```

範例不代表所有賽事規則。先查該場正式規則；`first_actor` 為 a／b／null。已公布前綴填入 `observed: [{actor: a|b|null, action, map}]`。`post-veto` 必須有完整已知路徑，不能回退為地圖未定。

明示的 `veto_scenarios` 每條需 `id`、`weight`、完整 `maps`、`pick_owners`（a／b／null）、`evidence_ids`、`weight_source`、`weight_basis`。官方確認的 post-veto 僅一條、權重一、來源 confirmed。主觀權重仍是可重播的主觀實驗，不能寫成資料擬合。

缺少可推估 veto 的證據時：保存 `unresolved` 降級、隊伍層系列分布及另行估計的具名圖率，明確標示兩者未整合；不能假稱已建完整模型。零樣本圖回到已擬合隊伍效果，不把它當弱圖。原模板仍保留每張圖。

## 指令與保存

從 repo 根目錄執行。以下路徑皆為當次 run 的實際檔案，輸出為 create-only；內容變更須換新檔／目錄。

```bash
python3 valorant-analysis/scripts/valorant_forecast.py train history.json --cutoff <ISO-8601> --output model.json
python3 valorant-analysis/scripts/valorant_forecast.py predict event.json --model model.json --output forecast.json
python3 valorant-analysis/scripts/valorant_forecast.py validate forecast.json --model model.json --event event.json
python3 valorant-analysis/scripts/valorant_forecast.py record forecast.json --model model.json --event event.json
python3 valorant-analysis/scripts/valorant_forecast.py render forecast.json --mode full --report-link prediction.md --output prediction.md
```

`render` 也接受預測陣列、`quick` 與 `daily-summary`，保留現有必填數字與唯一五欄底表。資料取得、證據品質評分、獨立價格收集與歸檔仍依原 skill；本入口不代替研究或市場收集。市場資料不能傳入 train/predict，可另保存決策附件並在原模板「價格與狀態」位置呈現。

`train --config config.json` 可指定固定消融設定，例如 `{"layers":["team","map"],"fit_correlation":false}`。支持層為 team、map、patch、roster、agents、side。`--registry` 預設優先讀 `.automation-state/valorant/history/factor-registry.json`；初次環境降級使用本目錄 `forecast-factors.json` 的隔離候選。正式累積需把候選定義保存至持久 registry，不覆蓋既有 active／retired 決策；缺少登錄或已 retired 者拒絕擬合。

v3 forecast 是 canonical v2 加 `valorant` 附加資料，保存逐圖率、完整禁選路徑、特徵使用、input/model hash。務必連同原 event、model、訓練資料及 registry 保存。獨立逐圖一致性驗證不能取代 `validate --model --event` 的完整重播。

### 發布前核對實際入模

```bash
python3 valorant-analysis/scripts/valorant_forecast.py audit-model-use forecast.json --output model-use-audit.json
```

可附 `--model model.json --event event.json` 同時重播；不修改模型或原快照。工具沿正權重主情境比對特徵軌跡，分開列出 `fitted_input`（有可用擬合參數）、`input_only`（有輸入但未擬合）、`not_modeled` 與 `unknown`，以及只用於補充圖率的軌跡。舊 v2 無特徵軌跡時不猜測效果；明示 unresolved 路徑仍可確認逐圖情境未整合。

逐圖 `input_weight` 是選入情境的質量，並非該圖開打機率。`fitted_input` 不代表係數非零、全圖已覆蓋或樣本外有效；需配合逐圖行與原模型驗證。將報告用到的戰術理由對照此結果，未進主分布者保留為條件分析。另存本次實際載入的 skill／reference 路徑與 SHA-256，供日後還原指令版本，不回填舊預測。

## 配對評估

`walk-forward` 讀 `{history, config?, targets:[{event, outcome?, cohort?}]}`。`outcome` 獨立保存 `actual_score`、`result_status`、`result_source_url`、`result_observed_at`；不能混入 event。每場僅一個事前指定快照，按截止重新訓練 v2 challenger 控制組與 v3 候選；任何一方失敗仍保留該場為 unmodeled。

```bash
python3 valorant-analysis/scripts/valorant_forecast.py walk-forward experiment.json --output comparison.json
python3 valorant-analysis/scripts/valorant_forecast.py evaluate evaluated-forecasts.json --output metrics.json
python3 valorant-analysis/scripts/valorant_forecast.py compare paired-forecasts.json --baseline <version> --challenger <version> --output paired.json
```

對已保存預測的副本附加賽果，不改原檔。比較先驗證 A/B、BO、快照及截止，沿用共用 30 日期區塊、2000 次 block bootstrap 的升版門檻，另檢查讓圖／大小 Brier 與 BO／Patch／名單群組。互補市場不重複當獨立樣本。看過結果的區段只能作開發資料；參數選擇與校準另留內層時間資料，不使用外層測試集選最好設定。

`eligible-for-review` 不會自動升版；勝方、比分與市場品質各自提供證據，單元測試、工程改善或小樣本重播皆不能證明命中提高。需新增版參數時保留原模型與全部試驗，不依單場結果來回切換。
