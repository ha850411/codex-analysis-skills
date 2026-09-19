# CS 賽後檢討與模型校準

先套用 `../../shared/postmortem-improvement.md`。本文件補充 CS 的事件重建與領域歸因；單純降信心或注碼不算完成修正。

## 1. 重建賽前快照

- 核對賽事、階段、BO、LAN/online、Active Duty map pool、veto 規則與資料截止時間。
- 核對當場五人、stand-in、IGL、AWPer、coach 與角色變動。
- 保存原獨贏、精確比分、逐圖機率、至少一圖、信心度、價格與推薦，不用賽後資訊改寫。
- 從 canonical forecasts、報告索引及原始 run 建立完整當日清單；報告副本按 forecast ID／內容雜湊去重，獨立樣本按賽事計數。原版與更新版保存各自時間資格，不把重建改列 prospective。同版本、同快照無歷史 cohort 時明列0，不混入其他模型或賽制湊樣本。

## 2. 重建實際內容

- 系列比分、veto／map order、pick owner、選邊、每圖比分與 OT。
- T／CT 半場、pistol、force-buy／anti-eco、opening duel、首殺後轉化、timeout 後回合與領先收尾。
- 官方賽事資料、HLTV match page、VOD 與 Liquipedia 交叉查核；資料不足時明列缺口。

## 3. 評分

- 獨贏沿共用 `evaluate` 的 a/draw/b 三分類平方誤差和；二路賽事等於二元 Brier 的兩倍，須標定義。精確比分另算完整比分分類的平方誤差和，並保存兩者 log loss；大小圖／至少一圖另以二元 Brier 評分，不混平均成同一指標。
- 檢查實際結果在原精確比分分布中的機率，而不是只標記「猜中／猜錯」。
- 保存並分別核對報告中的勝方選擇、看好方代表比分與全分布比分眾數。共用比分 Top-1 仍按原眾數計分；代表比分及同率時的定性選邊另列命中，不混入原模型指標，也不能挑賽後命中的一個當原主推。
- 逐圖比較預測勝率與結果，但不把三張圖當完全獨立樣本。
- 未打到的圖標未進行，不記為預測失敗；單圖率按地圖名稱及隊伍方向配對，不能因實際圖序不同拿預測M1比較另一張實際M1。以原勝率評分，賽後已知首殺、半場與Rating只作結果／歸因，不能回填特徵。
- 以同賽制、同預測時點與相近信心區間累積 calibration cohort；單場只作警報。
- 同時報告賽事覆蓋、可評分快照數與資格排除原因；0u 的損益為0、ROI為N/A，不能把避下注算成預測命中。實際橫掃落在原分布內，既不代表比分眾數命中，也不能僅憑一次出現宣稱原機率太低。

## 4. 錯誤歸因

- 資料錯漏：陣容、stand-in、地圖池、veto 規則、場地或賽程過期。
- Veto／地圖池：permaban、comfort pick、decider 或 side selection 判錯。
- 角色與戰術：IGL／AWP、entry、anchor、T side 結構或 timeout 調整判錯。
- 轉化與經濟：pistol、force-buy、anti-eco、lead conversion 或 OT 風險漏算。
- 樣本與對手：過度相信原始地圖勝率、舊陣容 H2H、排名或明星名氣。
- 合理變異：少量 clutch、eco、pistol 或 OT；若跨圖重複出現則不能全歸因於變異。

## 5. 修正

- 流程錯誤立即修正資料來源、主分布或相依機率；純單場結果不硬設下一場勝率上限。
- 按 `domain-analysis.md` 第4.1節核對原模型的實際更新單位、逐圖特徵及共同狀態；報告描述錯誤用固定案例修正，保留原文與原數字。模型權重問題先存同輸入消融，再決定是否有資格建立候選模型；多因素一起移除不能歸因為某一因素改善。
- 若取圖路徑或橫掃路徑漏算，從 veto 情境與逐圖勝率重建精確比分分布，不事後手動補尾端。
- 每個候選修正必須指出賽前可觀察觸發條件、受影響的地圖／系列賽機率與預期改善 cohort；未確認 roster／veto 只形成情境，不得以降信心取代情境建模。
- 用相同賽事、相同 pre/post-veto 快照做 paired walk-forward；只有 Brier／log loss 改善且精確比分分布未實質退步才採用新權重。
- 上項亦須通過共用的勝方命中主要門檻及重要 cohort／覆蓋率檢查，Brier改善本身不構成升版。只有共同完賽上界的舊資料不能依序切分冒充當時可用的 walk-forward；記錄缺失並開始保存未來前瞻輸入。
- 候選因子保存可重現定義、輸入欄位、未見測試區段、add-one／ablation 設計及否決條件；同一場的勝方、比分和取圖錯誤只算一個賽事樣本。`factor-registry.json` 與逐次 `postmortems/<目標日>/<run>/` 中的 error-ledger、evaluated-records、improvement-plan 跨日保留，歸檔只複製本次證據。

## 6. 輸出順序

正文依 output-template.md：原選擇與賽果短表 → 勝方／比分分開評分 → 一至三項誤差原因 → 可驗證改善與裁決。來源就近保留；veto 逐圖復盤、完整機率評分與基準／挑戰版比較存附件，要求深入時再展開。
