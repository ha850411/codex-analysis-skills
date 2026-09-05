# 可重播預測契約 v2

## 分工與狀態

`core.py` 是機率、時間與快照驗證的唯一來源；`models.py` 建立可重現基準及挑戰版；`evaluation.py` 評分；`render.py` 產生閱讀版本。均使用 Python 標準庫，無額外 API 或套件依賴。

- baseline：可計算但未校準；experiment：候選方法，不能給投注推薦。
- production：只有配對樣本外證據通過、經裁決才可升版。CLI 不自動將模型改為 production。
- unmodeled：保存缺口與賽事，沒有機率；仍計入預測覆蓋的分母。
- 現有 MLB `build_public_baseline.py`／`simulate_scores.py` 保持原始分階段模型；共用 MLB 聚合基準只用於比較，不取代牛棚、前五局及 walk-off 模擬。

目前共用基準是隊伍強度與得分環境模型，不代表已擁有完整選手、draft、傷兵或牛棚特徵。未實作的特徵列入 missing_data；資料到位後新增 candidate 並配對比較。不能用手工加減百分點填補模型缺口。

挑戰版可用 `train --registry factor-registry.json` 擬合可觀察的數值因子。歷史列須有 started_at 與 feature_snapshot（available_at、evidence_ids、values）；時間必須早於開賽。event 的特徵引用必須對應 evidence。只使用 active/candidate，拒絕 retired 及市場因子；樣本不足則不擬合。參數、標準化與 registry hash 均寫入模型。候選參數只進 experiment，不影響正式版本。

電競挑戰版另以歷史系列比分的訓練期 likelihood 選共同狀態幅度；以三點混合及逐路徑後驗生成條件樹。未知 best_of 或不足20場有效系列時維持獨立基準並揭露限制，不能用手工橫掃下限替代。

## 輸入與公開入口

從 repo 根目錄執行 `python3 shared/forecast/cli.py <command>`。命令輸入為 UTF-8 JSON；歷史陣列也接受 `.jsonl`。`--output` 保存新 artifact，相同內容可重跑，不同內容必須使用新 run 目錄。

| 命令 | 輸入與參數 | 輸出 |
| --- | --- | --- |
| train | 歷史結果陣列；--sport、--cutoff、--variant baseline/challenger | 模型與訓練 ID、參數及資料 hash |
| predict | event JSON；--model 模型 JSON | canonical forecast v2 |
| validate | canonical forecast | 契約結果與 hash |
| derive | A-B 比分機率字典 | 勝方、比分眾數、總分與分差分布 |
| record | canonical forecast；選填 --root | 不可覆寫快照與 SHA-256 |
| render | canonical forecast 或陣列；--output-dir | Markdown、聊天摘要、JSON、Notion summary、口播腳本 |
| audit / adapt | 舊資料；--source 明確來源格式 | 資格稽核／評估格式；不覆寫原始資料 |
| evaluate | 評估紀錄陣列；選填 --baseline 與 --challenger | 分群指標／配對比較 |
| walk-forward | history 與 events 陣列 | 同時訓練基準／挑戰版、逐場預測、比較 |
| pipeline-input | canonical forecast | pipeline v1 輸入及鎖定的 computed_probability_groups |

訓練結果最少包含 event_id、sport、participants（A/B）、score（整數二元陣列）、completed_at、available_at、result_status=final、source_url。主客隊使用 home_index=0/1/null。電競可附 games（逐局 map、winner），沒有則不估地圖特徵。任何已完成時間或可用時間晚於 cutoff 的結果不得進訓練；拒絕重複賽事。

Event 包含 event_id、sport、competition、snapshot、created_at、data_cutoff、scheduled_start、participants、scope、evidence、confidence；電競另填 best_of。veto_scenarios 選填，內容為 id、weight（0–1）、maps；每條路徑都有證據才使用，權重總和為1。沒有可信路徑時以基準標記地圖未知，不偽裝完整 veto 預測。

## Canonical forecast

- schema_version 固定 `2.0`、probability_unit 固定 `fraction`。機率全部使用 0–1；信心度 components 與 value 使用 0–100。不可依數值猜單位。
- forecast_id 是安全檔名；event_id 為穩定識別；另保存 model_version、parameter_version、model_artifact_hash、snapshot、scope。
- score_distribution 使用 A-B 比分字串到機率的映射。電競須完備；大量得分結果可保存矩陣，正文只展示前三名及其餘機率。
- evidence 每項保存 id、url、claim、available_at、retrieved_at。available_at 表示內容當時可知的時間，不可用今天重新開啟舊頁的時間冒充發布時間。
- eligibility 分 prospective、historical_replay、reconstructed_after_start、legacy_unverified。正式賽前紀錄必須早於 actual_start，未知則保守使用 scheduled_start；歷史重播獨立列帳。
- confidence=null 時必須有缺口原因；非空時五項加權後四捨五入，不允許未揭露上限覆蓋加權值。
- status=unmodeled 必須保存 missing_data；不得填主分布。未校準模型 recommendation_eligible=false。
- scenarios 若存在，主分布必須等於加權和。derived 若存在，必須精確等於共用計算結果。

既有 LoL v7／Valorant v1／pipeline v1 保留原 CLI。adapter 必須明確指定格式，保留 source_hash；舊資料缺少原始快照證據時標 legacy_unverified，不能因存在賽前時間字串自動宣稱已通過當時資訊稽核。

新紅隊流程先以 pipeline-input 匯出 input.json。computed_probability_groups 是由主分布確定性換算的百分比；主預測及最終裁決必須保持一致。紅隊若發現新事實，重建上游 canonical forecast 再重跑，不能在裁決 JSON 手改數字。舊 input.json 沒有此欄位時仍走既有相容模式，不宣稱具 v2 計算溯源。

## 評估與升版

評估紀錄按 sport、event_id、snapshot、data_cutoff、model_version 唯一。賽果獨立接回 actual_score、result_status；未完賽不計機率分數。Brier 採完整三分類平方誤差和，二路賽事 draw=0；勿直接混比其他二元 Brier 定義。

勝方命中為主要指標，比分 Top-1 為次要；NBA／MLB 同時看得分及分差 MAE。Top-3、log loss、校準分箱與 coverage 另報。未產生數字的賽事不從發布集合刪除。

配對鍵包括相同資訊截止；以日期區塊 bootstrap 2000 次、固定 seed，最少30個日期區塊才准通過自動檢查。勝方命中差值95%區間下界須>0；任何已測次要指標點估退步、運動分群退步、場次不一致或可用率降低即 experiment-only。達標只表示 eligible-for-review，仍不自動升版。最少區塊數不是充分統計保證，仍須檢查聯賽、賽制與制度變動。

walk-forward 為固定外層測試，每事件僅一個預先指定快照；不使用本批測試結果調整參數。不具備當時輸入者只累積前瞻樣本，不能回填假資料。

## 權限與保存

record 保存於 `.automation-state/<sport>/history/forecasts/`。history 不受短期報告清理影響。CLI 只建立本地 artifact，不寄信、不取市場、不發布、不改 production。外部發布仍由既有排程或明確授權的 exporter 執行。
