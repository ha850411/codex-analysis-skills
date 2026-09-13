# 分析者情境估計（LoL 實驗入口）

本入口讓領域推理成為可檢查的預測輸入；不把主觀估計冒充統計校準，不取代既有 production。只在有具體局內證據、能說明機制與反證時使用。只有比分、排名、名氣或通用勝法時留在 baseline，不為了產出更鮮明的勝率而造情境。

## 預測設計

先保存獨立 canonical v2 比分基準，再鎖定分析者假設，最後取市場。情境是可能發生的比賽結構，不能命名成「A贏／B贏」再把結果塞成100%。選足以解釋主要不確定性的情境，不強迫三個模型或固定集成權重。

每個情境保存：

- `id`、`weight`（0–1）：互斥的工作假設與合計為1的權重；`weight_reason` 解釋相對權重。它是分析者估計，不是觀測頻率。
- `mechanism`：可重複的 BP／對位／物件機制，指出系列、局數與來源。
- `evidence_ids`、`counterevidence_ids`：支持與反證引用；至少一個支持引用是 `kind=match_detail`，不能只引用賽程或roster。
- `game_probabilities`：按 G1…Gbest_of 的第一隊單局勝率，全部是 fraction；`probabilities_reason` 說明與基準差異、各局變化、未知後段如何處理。不要以小數精度冒充測量；沒有G4/G5證據就寫假設，不亂配疲勞或英雄池效果。
- `invalidation`：什麼可觀察事實會推翻這條機制。

同一情境內各局率只隨局數變化，並未建模具體 W/L 歷史的適應；跨情境混合會產生共享狀態的相依性。需要真正逐路徑調整時使用已有、能生成完整條件樹的模型，不能宣稱本入口已捕捉完整局間學習。

頂層 `baseline_departure` 說明為何偏離或仍接近比分基準；`counterargument` 說明最強反證。事實足以支持機制，不表示足以唯一決定其參數；機率、權重與參數理由都屬可供日後校準的分析者假設。

## JSON 與 CLI

輸入物件為 `event`、`baseline`、`judgment`；`event` 與共用CLI相同，另將引用資料標記 `kind=match_detail|lineup|patch|schedule|context`、`teams`（該證據實際涵蓋的隊伍縮寫）。兩隊皆須有被情境引用的 `match_detail`。不要把賽程加上kind就冒充局內內容。

`baseline` 是同事件、同隊伍順序、同資料截止、同賽制的已驗證比分基準完整JSON；兩者建立時間可以不同。`judgment` 包含 `locked_at`、`baseline_departure`、`counterargument`、`scenarios`。每個 scenario 的欄位如上。`locked_at` 在資料截止之後、event 建立時間之前或相等，且必須早於開賽。資料、輸入不含市場；不得用賽後資訊生成標為賽前的估計。

```bash
python3 lol-analysis/scripts/analyst_forecast.py build analyst-input.json --output analyst-forecast.json
python3 lol-analysis/scripts/analyst_forecast.py validate analyst-forecast.json
python3 shared/forecast/cli.py validate analyst-forecast.json
python3 shared/forecast/cli.py record analyst-forecast.json
python3 shared/forecast/cli.py render analyst-forecast.json --output-dir rendered
```

腳本展開逐局樹、聚合各情境及主分布，並保存原始輸入與雜湊。LoL專用validate重新計算並比較整份預測；不能只用共用validate取代它。市場決策獨立保存，不能修改鎖定輸入；報告增補市場段落須引用獨立決策並保留分布不變。

腳本的驗證只檢查結構、時點、引用、機率與重播，不會證明來源內容正確或參數合理。發布前人工核對來源是否真的支持每項機制，是否正反證同等處理，是否以結果偏好反推權重。

## 參數敏感度附件

鎖定後、取價前執行 `python3 lol-analysis/scripts/analyst_forecast.py audit analyst-forecast.json --output analyst-audit.json`；也接受多份快照的 JSON 陣列。先對每份做完整重播，任一失敗就不產出附件；與原快照不同內容的既有輸出不可覆寫。

- 使用每對情境間轉移 ±0.10 權重、以及每個情境的全部逐局率各偏移 ±0.05 的單項壓力測試。兩類分開執行，不組合成聯合不確定性搜尋；其他參數保持原值。
- 保留合法情境，超出權重／單局率界限者列為 skipped；不截斷、補零或重新正規化。輸出完整比分、勝方／比分並列眾數、BO3 大2.5／BO5 大3.5與大4.5、機率範圍及翻轉案例。原本均勢與變成均勢使用 winner_set_changed，不冒稱確定方向翻轉。
- 附件格式 `lol-analyst-audit-v1`，含原 forecast ID、來源 canonical SHA-256、原結果、測試參數、結果與限制；不產生新 forecast ID，不改資格或原分布。範圍包含原值，並非信賴區間；這組測試沒翻轉也不證明穩健或校準。
- 批次檢查不同事件的相同／鏡像數值參數，忽略情境名稱與排列、容許浮點誤差；同事件不同版本不算跨場重複。警示只要求複查近期對手、BP、可轉移性及參數理由，不自動拒絕或強迫改數字。
- 事實更正時建立新完整快照，另存 supersedes、影響的證據與參數。若只是局次標籤更正且機制仍受其他證據支持，可維持參數並說明；不能因資料變多就機械提高勝率。

## 報告與後續驗收

標示「分析者情境估計（實驗，未實證校準）」；正文說明主判斷與反證，簡表可壓縮標示「情境估計」。保留比分基準作比較，不取兩者平均或挑有利端點。情境間的差距只描述假設差異，不是信賴區間。

`status=experiment`、`recommendation_eligible=false`、0u；不能因有來源或驗算通過就標production。日後將事前鎖定的情境預測與基準配對回收，分別檢查勝方、比分及機率校準。方法文件與程式上線只代表能實際執行情境估計，不代表命中率已改善。
