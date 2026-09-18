# 分析者情境估計（LoL 實驗入口）

本入口讓領域推理成為可檢查的預測輸入；不把主觀估計冒充統計校準，不取代既有 production。只在有具體局內證據、能說明機制與反證時使用。只有比分、排名、名氣或通用勝法時留在 baseline，不為了產出更鮮明的勝率而造情境。

## 預測設計

先保存獨立 canonical v2 比分基準，再鎖定分析者假設，最後取市場。情境是可能發生的比賽結構，不能命名成「A贏／B贏」再把結果塞成100%。選足以解釋主要不確定性的情境，不強迫三個模型或固定集成權重。

每個情境保存：

- `id`、`weight`（0–1）：互斥的工作假設與合計為1的權重；`weight_reason` 解釋相對權重。它是分析者估計，不是觀測頻率。
- `mechanism`：可重複的 BP／對位／物件機制，指出系列、局數與來源。
- `evidence_ids`、`counterevidence_ids`：支持與反證引用；至少一個支持引用是 `kind=match_detail`，不能只引用賽程或roster。
- 勝率輸入二擇一：`game_probabilities` 按 G1…Gbest_of 給第一隊單局率；`conditional_probabilities` 給完整非終止 W/L 路徑到下一局第一隊勝率的物件（`ROOT` 為首局、`W` 為首局第一隊勝後的第二局、`LL` 為連敗兩局後的第三局）。全部為 fraction，不能缺節點、放入終止節點或同時使用兩種輸入。`probabilities_reason` 說明與基準差異、各局變化、未知後段如何處理；沒有證據不亂配疲勞或英雄池效果。
- 使用 `conditional_probabilities` 時另需 `dependence_reason`、`dependence_evidence_ids`：說明哪些歷史路徑為何改變下一局條件率，並引用局內證據。引用不代表係數已被估出；區分觀測事實與主觀幅度，不能只因輸局就自動加回彈率、因贏局就加氣勢分。賽前尚未發生的 BP 是假設，不能寫成已知條件。
- `invalidation`：什麼可觀察事實會推翻這條機制。

`game_probabilities` 只隨局數變化；跨情境混合產生共享狀態相依性。`conditional_probabilities` 可以表示具體 W/L 路徑差異，但沒有自動學習、估計 BP 因果效果或實證校準。兩種情境可以混合；只含舊式輸入保存為 `lol-analyst-scenarios-v1`，包含條件樹則為 `v2`。舊快照仍按原輸入重播並保留相同 canonical 雜湊，不為新功能改寫。

## BO5 大3.5 的計算與限制

所有總局數、獨贏、讓分與至少一局均由同一完整比分分布推導：

`P(>3.5) = P(3:1)+P(3:2)+P(2:3)+P(1:3) = 1−P(3:0)−P(0:3)`。

對每個情境，第一隊橫掃為 `p(ROOT) × p(W) × p(WW)`；第二隊橫掃為 `(1−p(ROOT)) × (1−p(L)) × (1−p(LL))`，再依情境權重加總。不能先平均不同情境的單局率再乘，也不能把系列獨贏率直接代入單局公式。G4/G5 的勝率不影響能否進入G4，調整後段率無法修正大3.5。

若每個情境的前三局都使用同一 `p`，才可化簡為 `3p(1−p)`；此模型必有75%上限，中度強弱差容易集中在約72%。這是輸入結構限制，並非 BO5 真實上限。`audit` 的 `length_diagnostics` 會列出兩種橫掃的乘數、各情境大3.5、總和與結構上限；`constant_rate_length_constraint` 提醒檢查局數辨識力。即使把同一固定率填進條件樹，也不解除限制。

遇到這項限制，正文的大3.5數字旁須標「固定率基準，未納入局間調整」，不得把它當作針對本場量化 BP／Fearless 後的大小盤優勢。若使用者要求修正，先核對依賴證據；缺乏可辯護的條件率時，保留基準並明說暫無可靠修正點估計。不能為避免重複72%硬改權重、指定另一百分比，或將近幾場未橫掃比例直接套成新主預測。

頂層 `baseline_departure` 說明為何偏離或仍接近比分基準；`counterargument` 說明最強反證。事實足以支持機制，不表示足以唯一決定其參數；機率、權重與參數理由都屬可供日後校準的分析者假設。

`weight_reason` 解釋機制為何較可能在本對手面前成立，`probabilities_reason` 解釋成立後的優勢，兩者不能只重複同一批勝局。觸發 `mechanism-transfer.md` 時另存 `mechanism-transfer-audit.json`：核對正文的「未觀察／不能判定」是否被權重暗中寫成負面證據，以及不同組合是否仍共用不可重用的核心英雄。這是人工證據稽核附件，不新增必填 schema、不改原分布；現有 `audit` 不會驗證這些語意。

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
- 條件樹另作局間依賴壓力測試：ROOT 不變，前一局 W 的節點加 `delta`、前一局 L 的節點減 `delta`，`delta=±0.05`；與整體強度位移分開。這只是診斷，不能把偏移後數值當擬合係數或新主預測。
- 保留合法情境，超出權重／單局率界限者列為 skipped；不截斷、補零或重新正規化。輸出完整比分、勝方／比分並列眾數、BO3 大2.5／BO5 大3.5與大4.5、機率範圍及翻轉案例。原本均勢與變成均勢使用 winner_set_changed，不冒稱確定方向翻轉。
- 僅舊式輸入時附件格式為 `lol-analyst-audit-v1`，含條件樹時為 `v2`；含原 forecast ID、來源 canonical SHA-256、原結果、測試參數、結果與限制，不產生新 forecast ID、不改資格或原分布。範圍包含原值，並非信賴區間；這組測試沒翻轉也不證明穩健或校準。
- 批次檢查不同事件的相同／鏡像數值參數，忽略情境名稱與排列、容許浮點誤差；條件樹鏡像同時交換歷史 W/L 並將下一局機率取補數。同事件不同版本不算跨場重複。警示只要求複查近期對手、BP、可轉移性及參數理由，不自動拒絕或強迫改數字。
- `scenario_space` 另列各情境的**系列**勝率，以及固定單局率、任意重配非負權重時的勝率包絡。若所有情境都未讓某隊成為唯一較可能勝方，發出 `one_sided_scenario_space`。它指出現有情境的表達範圍，不證明偏誤；小幅擾動不翻轉，不能排除漏掉整種比賽結構。
- 收到警示時，核對最強反證到底只支持「多取一局／拉到均勢」，還是支持「該機制成立時能形成系列優勢」。已有近期證據卻未映射的機制，先作隔離候選；沒有支持則保留單側情境並記理由。不強迫兩邊各有優勢情境、固定爆冷下限或用賽後勝方倒填單局率；包絡端點也不是新預測。
- 事實更正時建立新完整快照，另存 supersedes、影響的證據與參數。若只是局次標籤更正且機制仍受其他證據支持，可維持參數並說明；不能因資料變多就機械提高勝率。

## 報告與後續驗收

標示「分析者情境估計（實驗，未實證校準）」；正文說明主判斷與反證，簡表可壓縮標示「情境估計」。保留比分基準作比較，不取兩者平均或挑有利端點。情境間的差距只描述假設差異，不是信賴區間。

`status=experiment`、`recommendation_eligible=false`、0u；不能因有來源或驗算通過就標production。日後將事前鎖定的情境預測與基準配對回收，分別檢查勝方、比分及機率校準。方法文件與程式上線只代表能實際執行情境估計，不代表命中率已改善。
