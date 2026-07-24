# 2026-07-24 LoL S Tier 深度分析：AL、JDG、BLG 勝方傾向，三場皆受樣本上限約束

## 最終結論

今日正式 S Tier 範圍是三場 LPL BO3，不包含 7/25 才開打的 LCP。最終模型為 AL 77%、JDG 63%、BLG 85%；最可能比分均為 2-0，但模型信心度只有55%、58%、60%，其中 WE-JDG 最接近，BLG-EDG 的先發上路仍需臨場確認。

## 賽事與資料狀態

- 賽事：LPL 2026 Split 3｜參賽隊伍：Anyone's Legend、LGD Gaming、Team WE、JD Gaming、EDward Gaming、Bilibili Gaming
- 開始時間：2026-07-24T15:00:00+08:00（Asia/Taipei）
- 資料截止：2026-07-24T10:48:00+08:00
- 模型信心度：58% — 三場平均證據品質；原始加權受完整度、近期名單與資料新鮮度支持，但所有對戰在同賽事同版本都少於三個系列且 G1 選邊未定。頂層五項採全日非補償式上限後的有效分數，逐場原始分數與上限計算保留於正文。

| 信心度組成 | 分數 |
| --- | ---: |
| 資料完整度 | 58% |
| 資料新鮮度 | 58% |
| 名單／先發確定度 | 58% |
| 制度與樣本相關性 | 58% |
| 模型穩定性 | 58% |

## 1. 賽程完整性、快照與資料狀態

- 資料截止：2026-07-24 10:48（UTC+8），快照為 `pre-lineup / pre-draft`。
- 今日正式納入：15:00 AL–LGD、17:00 WE–JDG、19:00 EDG–BLG，均為 LPL Split 3 Group Ascend BO3、Fearless Draft。
- 完整性處理：bo3.gg 與 LPL 賽程頁對三場 LPL 一致。Leaguepedia／Liquipedia 曾把 LCP Split 3 列為 7/24，但 Riot 7/13 最新官方公告明確寫 7/25 開幕，因此移除原候選的 SHG–TSW、CFO–DCG。這是已消解的來源衝突，不是遺漏。
- 版本：7/23 LPL 已使用 16.14；今日賽事頁尚未逐場填入版本，故以 16.14 作高可信推估。正式比賽頁若臨時顯示不同版本，應建立新版快照。
- 限制：未完整逐場複盤官方全長 VOD；近期判斷以實際出賽名單、局內數據、BP／版本紀錄與賽後回顧為主。三場 G1 選邊均未確認。

## 2. Patch 16.14 與今日共同 BP 主軸

26.14 對職業賽最直接的變化是 Azir 互動增強、Yunara 成長 AD 提升、Nami E 強化，以及 6／11 級後藍 Buff 提供更多技能急速；另一側是 Jayce 的跑速與抗性下修、Senna 與 Seraphine 下路體系削弱。這使今日 BP 更重視三件事：

1. **中路穩定線權與後期輸出**：Shanks、HongQ、Knight 都能從控制法師與 Azir 類結構受益；EDG 新中路 Bulldog 則仍在與隊伍磨合。
2. **ADC 大核與下路保護**：Hope、GALA、Viper 都能使用後期大核；Yunara 加強使純粹靠 ban 一個 ADC 解題更困難。Leave 也有單點 carry 路徑，但 EDG 必須先把中野與輔助死亡數壓下來。
3. **打野第一輪與藍 Buff 節奏**：Tarzan、JunJia、Xun 的中期技能循環會更有價值。對 LGD 而言，Heng 7/22 的中野連動是可重複優勢；對 JDG 而言，JunJia 7/23 的前期落後則是必須修正的警訊。

Fearless Draft 會放大第二局後的英雄池與局間調整差異；因此本模型沒有把每局視為固定同勝率。若賽事官方房間載入16.13或其他熱修版本，立即建立新版快照，回退Azir、Yunara、Nami與藍Buff權重並重算機率。

## 3. Anyone's Legend vs LGD Gaming — 15:00

**可能先發**

| 位置 | Anyone's Legend | LGD Gaming |
|---|---|---|
| Top | Flandre | Burdol |
| Jungle | Tarzan | Heng |
| Mid | Shanks | Tangyuan |
| ADC | Hope | Shaoye |
| Support | Kael | Crisp |

**近期內容與權重仲裁**

AL 7/23 以 2-1 擊敗 JDG，證明其 BO3 決勝局的耐心與後期資源管理仍在；但決勝局拖長也顯示前中期未形成乾淨關門。LGD 7/22 對 EDG 的 2-0 更乾淨：兩局合計 41-22 擊殺、18-7 塔、5-1 巴龍，Heng–Tangyuan 的中野與 Shaoye 的輸出銜接都有效。另一方面，AL 6/5 曾在 Split 2 季後賽 3-0 LGD；因 BO5 外推 BO3，該 H2H 只當收縮先驗，權重不高於當前可比內容的一半。

**對位與取圖路徑**

- AL 路徑一：Tarzan 配合 Shanks 先取得中路線權，提早進入河道，讓 Hope 的後期輸出不必承擔逆風開戰。
- AL 路徑二：Flandre 使用弱側可自理上路，將 BP 與資源投向下半區；Fearless G2 再切換控制法師＋大核結構。
- LGD 路徑一：延續 7/22 的 Heng–Tangyuan 主動中野，搶先掌握第一輪小龍／巢蟲並迫使 Tarzan 回應。
- LGD 路徑二：Crisp 提早離線製造多打少，讓 Shaoye 在二件套前建立輸出空間。若 AL 再度把比賽拖到 40 分鐘以上，LGD 的團戰爆發仍可延伸到決勝局。

**反模型**：基準強度模型 AL 82%；同賽事近期模型 AL 74%；假設 LGD 取得有利 G1 選邊並複製中野節奏的弱方模型 AL 68%。最大差距 14 個百分點，因此點估計收在 AL 77%，敏感區間約 68%–82%。AL 為勝方傾向，但不是穩勝。

## 4. Team WE vs JD Gaming — 17:00

**可能先發**

| 位置 | Team WE | JD Gaming |
|---|---|---|
| Top | Cube | Xiaoxu |
| Jungle | Monki（Tyrion 為替補） | JunJia |
| Mid | Karis | HongQ |
| ADC | About | GALA |
| Support | Erha | Vampire |

**近期內容與權重仲裁**

WE 7/22 被 TES 2-0，About 兩局雖維持輸出量，但隊伍沒有把下路資源轉成物件控制。更早的 Split 2 季後賽，WE 曾先後 3-0 AL、3-1 BLG，之後又 0-3 TES、2-3 BLG；這組樣本說明 WE 有兩套上限：Cube 單帶／邊線壓力，以及 About 作主輸出的團戰，但系列間穩定性不足。JDG 7/23 以 1-2 輸給 AL，決勝局拖至約 56 分鐘仍未收掉，JunJia 的前期落後與中期資源轉換是明顯問題。

**對位與取圖路徑**

- JDG 路徑一：JunJia 先服務 HongQ，讓中路先動後支援 GALA；GALA 的大核收尾是全系列最穩的單一勝點。
- JDG 路徑二：Xiaoxu 以對線主動英雄迫使 Cube 留在線上，減少 WE 的邊線牽制，再由 Vampire 配合先手開團。
- WE 路徑一：Cube 在邊線取得 TP 與兵線主動，逼 JDG 分散資源，About 在正面打前排。
- WE 路徑二：Monki–Karis 利用 JDG 昨日暴露的中野前期空檔，先取得巢蟲／第一塔，把比賽縮短在 GALA 三件套前。

**為何 WE 能拿圖但仍非系列熱門**：WE 的兩條路徑都能重複，但需要 Cube 或中野至少一側先贏；JDG 即使輸掉 G1，仍有 GALA 後期與 BO3 敗方選邊兩個修正來源。基準模型 JDG 66%、同賽事模型 60%、WE 反模型下 JDG 55%，最大差距 11 個百分點；點估計 JDG 63%，敏感區間 55%–66%。這是今日最接近的一場。

## 5. EDward Gaming vs Bilibili Gaming — 19:00

**可能先發**

| 位置 | EDward Gaming | Bilibili Gaming |
|---|---|---|
| Top | Zdz | Wenbo（Bin 仍在 roster，當場待確認） |
| Jungle | Xiaohao | Xun |
| Mid | Bulldog | Knight |
| ADC | Leave | Viper |
| Support | Parukia | ON |

**近期內容與權重仲裁**

EDG 7/22 以新中路 Bulldog 出戰，0-2 輸給 LGD；兩局合計僅 7 塔、1 巴龍，Parukia 2/11/12，顯示問題不只是單線輸贏，而是中期站位、先手與輸出比例沒有對齊。BLG 7/23 用 Wenbo 上路以 2-1 擊敗 TT：G2 被 TT 在 28:34 拉出 9.8k 金差，證明 BLG 的替補上路／新版本首日並非無破口；但 G3 又以 27-13 擊殺、8-1 塔、4-0 龍、9k 金差收束，局間修正仍顯著優於 EDG。

6/3 BLG 曾在 Patch 16.10 以 3-0 橫掃 EDG，三局只讓 EDG 拿到 4 座塔。該 H2H 的版本與中路／上路情境不同，不能直接複製比分，卻仍支持 BLG 在中野、下路與收尾的多點優勢。

**取圖與反模型**

- BLG 路徑一：Knight–Xun 取得中路先動，讓 Viper 穩定吃下河道與下半區資源。
- BLG 路徑二：即使上路 Wenbo 只打弱側，BLG 仍可用 ON 的遊走與 Viper 的後期保底；若換回 Bin，上路主動性反而提高。
- EDG 路徑一：Leave 拿到 Yunara／高資源 ADC，Xiaohao 全程保護下半區，Zdz 用低資源前排吸收 BP。
- EDG 路徑二：利用 BLG 7/23 G2 的中期失誤，Bulldog 以控制法師先手，逼 BLG 在 Fearless 第二局進入較低熟練度組合。

EDG 的兩條路徑足以支撐單局尾端，但都依賴中輔死亡率大幅改善，尚不足以把系列爆冷抬到主要情境。基準模型 BLG 89%、同賽事模型 84%、EDG 有利選邊反模型 BLG 76%，最大差距 13 個百分點；混合分布點估計 BLG 85%，敏感區間 76%–89%。若當場確認 Bin 先發，BLG 2-0 約由55%升至58%、系列賽勝率約由85%升至87%；目前先發未定，維持原混合分布。

## 6. 系列賽主分布、公允賠率與信心度

所有勝率、至少一局、橫掃與比分均由同一精確比分主分布推導；公允賠率為 `100 ÷ 機率百分比`。

| 比賽（賽制） | 勝方 | 系列賽勝率 · 公允賠率 | 精確比分分布（比分 · 機率 · 公允賠率） |
|---|---|---:|---|
| AL–LGD（BO3） | Anyone's Legend | 77% · 1.30 | 2–0 · 45% · 2.22<br>2–1 · 32% · 3.13 |
| AL–LGD（BO3） | LGD Gaming | 23% · 4.35 | 2–0 · 8% · 12.50<br>2–1 · 15% · 6.67 |
| WE–JDG（BO3） | Team WE | 37% · 2.70 | 2–0 · 14% · 7.14<br>2–1 · 23% · 4.35 |
| WE–JDG（BO3） | JD Gaming | 63% · 1.59 | 2–0 · 34% · 2.94<br>2–1 · 29% · 3.45 |
| EDG–BLG（BO3） | EDward Gaming | 15% · 6.67 | 2–0 · 5% · 20.00<br>2–1 · 10% · 10.00 |
| EDG–BLG（BO3） | Bilibili Gaming | 85% · 1.18 | 2–0 · 55% · 1.82<br>2–1 · 30% · 3.33 |

- 至少贏一局：AL 92%／LGD 55%；WE 66%／JDG 86%；EDG 45%／BLG 95%。
- 最可能比分：AL 2-0（45%）、JDG 2-0（34%）、BLG 2-0（55%）。

**非補償式模型信心度**

- AL–LGD：原始分數 82／94／90／55／50，加權原始值 78%；觸發「同賽事有效樣本少於三個系列、G1選邊未定、關鍵VOD未完整複盤、反模型差14%」。上限為完整度82%、樣本55%、穩定性+10=60%，最終 **55%**。
- WE–JDG：82／94／91／58／57，加權原始值79%；觸發同上，反模型差11%。上限82%／58%／67%，最終 **58%**。
- EDG–BLG：82／94／70／60／57，加權原始值74%；另有BLG上路輪替不確定。上限82%／60%／67%，最終 **60%**。

原始模型穩定性已因agy未逐場獨立呈現兩條弱方取勝反模型而各下修10點；三場最終值原本已受樣本上限約束，因此不再重複扣分。以上信心度是證據品質，不是勝率或投注把握。

## 7. 推薦閘門與風險

**閘門結果（機率鎖定前不讀價格）**

- AL–LGD：AL 勝方方向成立，但 LGD 已有中野節奏與下路收尾兩條取圖路徑，因此不把 AL -1.5 當高信心方向；LGD 至少一局 55%，不足以主推。
- WE–JDG：WE 有兩條可重複取圖路徑，JDG 也有 GALA 後期與敗方選邊修正；打滿三局機率為 52%（WE 2-1 23% + JDG 2-1 29%），只屬五五附近，不足以在沒有價格時推薦 Over 2.5。
- EDG–BLG：BLG 2-0 為單一最高結果，但 BLG 7/23 G2 失控與上路輪替讓 EDG 仍有 45% 至少一局；EDG 的兩條路徑都需要執行顯著改善，因此不推薦 EDG +1.5，只保留 live 觀察。

**主要風險**

- 當場先發：BLG 可能在 Wenbo／Bin 間輪替；WE 另有 Tyrion 打野選項；正式名單公布後需重算。
- G1 選邊與 Fearless：BO3 的第一局權重高，敗方選邊與第二局英雄池會顯著改變打滿機率。
- 版本推估：今日暫採16.14；若賽事房載入16.13或其他熱修版本，立即重建版本、BP與機率快照。
- 樣本：每隊在 Split 3 只有一個系列，近期數據極易受單一 draft、對手與長局影響。
- 賽程與疲勞：AL、JDG、BLG 昨日剛打過系列；這同時帶來疲勞與更高版本資訊量，不能單向扣分。
- 盤中波動：LGD、WE、EDG 都可能靠前期線權或單次巴龍建立優勢，但其系列收尾穩定度不同；不應用單局領先直接外推整個 BO3。
- 紅隊覆蓋：agy 完成資料、算術與呈現審查，但未在審查檔逐場獨立重建兩條弱方系列取勝路徑；最終裁決保留主模型中的六條弱方路徑並下修原始模型穩定性。

## 最終機率

### AL vs LGD 系列賽勝方

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Anyone's Legend | 77% | 1.30 |
| LGD Gaming | 23% | 4.35 |

### AL vs LGD 精確比分

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| AL 2-0 | 45% | 2.22 |
| AL 2-1 | 32% | 3.12 |
| LGD 2-1 | 15% | 6.67 |
| LGD 2-0 | 8% | 12.50 |

### WE vs JDG 系列賽勝方

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team WE | 37% | 2.70 |
| JD Gaming | 63% | 1.59 |

### WE vs JDG 精確比分

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| WE 2-0 | 14% | 7.14 |
| WE 2-1 | 23% | 4.35 |
| JDG 2-1 | 29% | 3.45 |
| JDG 2-0 | 34% | 2.94 |

### EDG vs BLG 系列賽勝方

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| EDward Gaming | 15% | 6.67 |
| Bilibili Gaming | 85% | 1.18 |

### EDG vs BLG 精確比分

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| EDG 2-0 | 5% | 20.00 |
| EDG 2-1 | 10% | 10.00 |
| BLG 2-1 | 30% | 3.33 |
| BLG 2-0 | 55% | 1.82 |

## 判斷重點

- 今日S Tier正式集合為三場LPL，不含7/25開幕的LCP。
- AL 77%、JDG 63%、BLG 85%；WE-JDG是最接近的一場。
- BLG若確認Bin先發，2-0情境約增加3個百分點。
- 三場模型信心度55%／58%／60%，均受同版本小樣本上限約束。

## agy 紅隊審查（精簡）

- thesis：主模型依序選 AL、JDG、BLG → 最終模型依序選 AL、JDG、BLG
- presentation.analysis_sections[4]：只以文字說明Wenbo／Bin輪替風險 → 新增Bin先發時BLG 2-0約55%→58%、系列勝率約85%→87%的敏感分支
- presentation.analysis_sections[1]：版本不同時建立新版快照 → 明示賽事房若載入16.13或其他熱修版本，立即重建版本、BP與機率快照
- presentation.analysis_sections[5]：逐場原始模型穩定性為60／67／67 → 因agy未逐場獨立重建弱方兩條取勝路徑，原始模型穩定性下修為50／57／57；最終信心仍受55／58／60樣本上限約束

## 市場比較（模型固定後）

| 結果 | 全贏機率 | 其他結算 | 公允賠率 | 市場賠率 | EV | 來源 / 擷取時間 |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| Anyone's Legend 系列賽獨贏 | 77% | 無 | 1.2987 | 1.1300 | -12.99% | Stake / 2026-07-24T10:48:00+08:00 |
| LGD Gaming 系列賽獨贏 | 23% | 無 | 4.3478 | 6.0000 | +38.00% | Stake / 2026-07-24T10:48:00+08:00 |
| Team WE 系列賽獨贏 | 37% | 無 | 2.7027 | 3.1000 | +14.70% | Stake / 2026-07-24T10:48:00+08:00 |
| JD Gaming 系列賽獨贏 | 63% | 無 | 1.5873 | 1.3800 | -13.06% | Stake / 2026-07-24T10:48:00+08:00 |
| EDward Gaming 系列賽獨贏 | 15% | 無 | 6.6667 | 7.0000 | +5.00% | Stake / 2026-07-24T10:48:00+08:00 |
| Bilibili Gaming 系列賽獨贏 | 85% | 無 | 1.1765 | 1.1000 | -6.50% | Stake / 2026-07-24T10:48:00+08:00 |

## 市場決策（機率鎖定後）

三支模型熱門在 Stake 現價均為負 EV。LGD 與 WE 的弱方獨贏雖顯示正 EV，但模型與市場分歧超過 10 個百分點，且 G1 選邊、同版本樣本及紅隊弱方反模型仍不完整；三場目前全部 0u。

- 市場覆蓋：部分；來源：Stake
- 已取得玩法：系列賽獨贏
- 未取得玩法：地圖讓分、總局數、精確比分、首局
- 覆蓋說明：本次快照只取得 Stake 六個系列賽獨贏價格；其餘玩法沒有可追溯價格，因此不得視為完整盤口分析。

| 市場 | 決策 | 注碼 | 理由 |
| --- | --- | ---: | --- |
| Anyone's Legend 系列賽獨贏 @ 1.1300 | 不下注 | 0u | AL 1.13 對應模型 EV -12.99%，價格低於1.30公允賠率。 |
| LGD Gaming 系列賽獨贏 @ 6.0000 | 不下注 | 0u | LGD 6.00 的表面 EV +38.00%，但市場分歧過大、模型信心僅55%，且選邊與同版本樣本不足，未通過分歧閘門。 |
| Team WE 系列賽獨贏 @ 3.1000 | 不下注 | 0u | WE 3.10 的表面 EV +14.70%，但近期系列波動與G1選邊未定使優勢不足以轉成注碼。 |
| JD Gaming 系列賽獨贏 @ 1.3800 | 不下注 | 0u | JDG 1.38 對應模型 EV -13.06%，不追低賠熱門。 |
| EDward Gaming 系列賽獨贏 @ 7.0000 | 不下注 | 0u | EDG 7.00 僅有 +5.00% 表面 EV，不足覆蓋新中輔磨合、先發與版本不確定性。 |
| Bilibili Gaming 系列賽獨贏 @ 1.1000 | 不下注 | 0u | BLG 1.10 對應模型 EV -6.50%，且上路先發仍未確認。 |

**市場決策風險**

- Stake 快照只涵蓋系列賽獨贏，地圖讓分、總局數、精確比分與首局均未取得。
- 正式先發、G1選邊或比賽版本確認後，現有市場決策需重新建立快照。
- 市場價格會變動；本決策只適用於2026-07-24 10:48（UTC+8）的價格。

## 主要風險

- 三場 Game 1 選邊未確認，會影響 BO3 首局與敗方修正。
- BLG 今日上路可能在 Wenbo 與 Bin 間輪替。
- 同版本同賽事只有一個系列，模型對單一 draft 與長局敏感。
- 官方全長 VOD 未逐場完整複盤，BP與局內數據權重高於主觀影像判讀。
- 正式版本若不是16.14需建立新版快照。
- agy審查未逐場獨立呈現兩條弱方取勝反模型，領域審查標記為不完整。

## 尚缺資料

- 當場正式先發與 G1 選邊
- 今日逐場正式比賽版本
- 近期每支隊伍的完整官方全長 VOD 複盤

## 來源

- [bo3.gg LoL Match Center](https://bo3.gg/lol/matches/current)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [LPL 2026 Split 3 Regular Season Week 1-2](https://liquipedia.net/leagueoflegends/LPL/2026/Split_3/Regular_Season/Week_1-2)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [LCP 2026 Split 3 Everything You Need To Know](https://lolesports.com/en-au/news/lcp-2026-split-3-everything-you-need-to-know)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [League of Legends Patch 26.14 Notes](https://www.leagueoflegends.com/en-us/news/game-updates/league-of-legends-patch-26-14-notes/)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [Anyone's Legend - Leaguepedia](https://lol.fandom.com/wiki/Anyone%27s_Legend)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [LGD Gaming vs EDG summary - Games of Legends](https://gol.gg/game/stats/80183/page-summary/)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [LPL Split 3 Week 1 Match AL vs LGD - Liquipedia](https://liquipedia.net/leagueoflegends/Match%3AID_26LPLS3RS1_0005)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [Team WE - Leaguepedia](https://lol.fandom.com/wiki/Team_WE)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [JD Gaming - Leaguepedia](https://lol.fandom.com/wiki/JD_Gaming)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [JDG vs AL Post-Match Discussion](https://www.reddit.com/r/leagueoflegends/comments/1v4byz6/jd_gaming_vs_anyones_legend_lpl_2026_split_3/)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [Team WE vs JD Gaming - bo3.gg](https://bo3.gg/lol/matches/team-we-vs-jd-gaming-lol-24-07-2026)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [BLG vs TT summary - Games of Legends](https://gol.gg/game/stats/80192/page-summary/)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [EDG vs BLG game 3 - Games of Legends](https://gol.gg/game/stats/79119/page-game/)（confirmed；擷取 2026-07-24T10:48:00+08:00）
- [BLG vs Dplus KIA EWC Post-Match Discussion](https://www.reddit.com/r/leagueoflegends/comments/1uz3i6s/bilibili_gaming_vs_dplus_kia_esports_world_cup/)（confirmed；擷取 2026-07-24T10:48:00+08:00）

本分析為賽前機率估計，不保證賽果或獲利。正式先發、選邊、版本或即時價格變動後，原結論可能失效；請限制風險並避免追損。

## 簡表總結

| 時間 (UTC+8) | 比賽 | 先發 | 版本 | 推薦方向 | 最可能比分 | 雙方至少贏一局 | 模型信心度 | 投注建議 | 主要風險 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-24 15:00 | Anyone's Legend–LGD Gaming | AL：Flandre/Tarzan/Shanks/Hope/Kael；LGD：Burdol/Heng/Tangyuan/Shaoye/Crisp | 16.14（高可信推估） | AL 勝方傾向 | AL 2-0（45%） | AL 92%；LGD 55% | 55% | AL 1.13 負EV；LGD 6.00雖有表面價值但分歧閘門未過，0u | G1選邊、LGD首戰中野節奏、單一同版本系列 |
| 2026-07-24 17:00 | Team WE–JD Gaming | WE：Cube/Monki/Karis/About/Erha；JDG：Xiaoxu/JunJia/HongQ/GALA/Vampire | 16.14（高可信推估） | JDG 小優 | JDG 2-0（34%） | WE 66%；JDG 86% | 58% | JDG 1.38 負EV；WE 3.10僅觀察，樣本與選邊不足，0u | WE波動、JDG昨日長局、G1選邊 |
| 2026-07-24 19:00 | EDward Gaming–Bilibili Gaming | EDG：Zdz/Xiaohao/Bulldog/Leave/Parukia；BLG：Wenbo或Bin/Xun/Knight/Viper/ON | 16.14（高可信推估） | BLG 勝方傾向 | BLG 2-0（55%） | EDG 45%；BLG 95% | 60% | BLG 1.10負EV；EDG 7.00優勢不足覆蓋不確定性，0u | BLG上路未定、EDG新中輔磨合、版本待正式落頁 |
