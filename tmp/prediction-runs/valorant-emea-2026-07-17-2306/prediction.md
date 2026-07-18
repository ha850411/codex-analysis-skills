# EF 58%、Vitality 56%；第一場僅保留為已過時效的 pre-veto 快照

## 最終結論

獨立裁決維持兩場主分布：KC–EF 偏向 Eternal Fire 2:1，VIT–NAVI 偏向 Team Vitality 2:1。第一場的資料截止已晚於原定開賽時間，因此即使機率數學一致，也不可當成即時判斷。信心度因時序、Patch 13.01 小樣本、未公布 veto 及 Sunset／Summit 資料不足，由 77% 下修至 73%。

## 賽事與資料狀態

- 賽事：VCT 2026 EMEA Stage 2 - Group Stage Week 1 Day 3｜參賽隊伍：Karmine Corp、Eternal Fire、Team Vitality、Natus Vincere
- 開始時間：2026-07-17T23:00:00+08:00（Asia/Taipei）
- 資料截止：2026-07-17T23:06:04+08:00
- 模型信心度：73% — 五項加權為 0.25×82 + 0.20×85 + 0.25×80 + 0.20×50 + 0.10×55 = 73。名單與來源接近資料截止時間，但第一場已進入原定開賽窗口；兩場正式 veto、選邊與部分 caller 分工未確認。Patch 13.01 樣本稀少，KC、Vitality 尚無同版本 Stage 2 正式地圖樣本，Sunset 與 Summit 的可用資料尤其薄弱。

| 信心度組成 | 分數 |
| --- | ---: |
| 資料完整度 | 82% |
| 資料新鮮度 | 85% |
| 名單／先發確定度 | 80% |
| 制度與樣本相關性 | 50% |
| 模型穩定性 | 55% |

## 今日 Valorant 賽程盤點（TW，UTC+8）

| 時間 | 賽事 | 對戰 | BO | 資料狀態 |
| --- | --- | --- | --- | --- |
| 2026-07-17 23:00 | VCT 2026 EMEA Stage 2 | Karmine Corp vs Eternal Fire | BO3 | 官方賽制與 VLR 賽程已確認；資料截止 23:06，已超過原定開賽時間，僅保留為失效中的歷史 pre-veto 快照 |
| 2026-07-18 02:00 | VCT 2026 EMEA Stage 2 | Team Vitality vs Natus Vincere | BO3 | 官方賽制與 VLR 賽程已確認；截至 23:06 為 pre-veto，正式 veto、地圖順序與選邊未知 |

兩場皆以 Patch 13.01 與 Ascent、Breeze、Haven、Lotus、Split、Sunset、Summit 七圖池建模。這是原資料截止時間的裁決後報告，不混入其後的實際賽果或盤口。

## Karmine Corp vs Eternal Fire 完整分析

- 預測快照：pre-veto 歷史快照；因資料截止晚於原定開賽時間，已失去即時決策效力。
- 資料截止：2026-07-17 23:06:04（UTC+8）。
- 最終方向：Eternal Fire 58%，預測 EF 2:1；此方向僅供模型稽核，不建議追單。

### 預計先發名單確認

- Karmine Corp：Avez（Initiator）、SUYGETSU（Sentinel）、dos9（Controller）、LewN（Raze／Duelist）、N4RRATE（Jett／Phoenix／Duelist）。無 stand-in 標示；雙 Duelist 分工尚未在 Patch 13.01 正式驗證。
- Eternal Fire：Izzy（Neon／主 Duelist）、audaz（Omen／Controller）、Favian（Veto／Sentinel）、echo（Viper）、nekky（Fade／Sova／Initiator）。無 stand-in 標示；同版本首戰兩圖角色結構穩定。

### 數據對比矩陣

| 指標 | Karmine Corp | Eternal Fire | 優勢方 |
| --- | --- | --- | --- |
| 近期狀態 | 最近三場 0:2 Vitality、2:1 Paper Rex、1:2 NRG | Patch 13.01 首戰 2:0 Liquid，Split 13:6、Lotus 13:2 | EF |
| 地圖池深度 | Haven／Ascent 有取圖路徑；Split、Lotus 模型較弱 | Split、Lotus 有同版本實戰；Breeze／Sunset小優 | EF |
| 手槍局勝率 | N/A（缺少可交叉查核聚合） | N/A（缺少可交叉查核聚合） | 無法判定 |
| 首殺能力 | 缺少同版本 FK/FD 聚合 | Favian 7/4、Izzy 7/2，但僅兩圖小樣本 | EF 小樣本 |
| 攻方表現 | N/A（缺少同版本攻方拆分） | N/A（缺少同版本攻方拆分） | 無法判定 |
| 守方表現 | N/A（缺少同版本守方拆分） | N/A（缺少同版本守方拆分） | 無法判定 |
| 核心火力 | N4RRATE／LewN 分擔 Duelist，缺少 13.01 正式數據 | Favian 321 ACS、1.82 K/D；Izzy 236 ACS、1.82 K/D | EF（需強收縮） |
| 版本／Meta 適應 | 尚無 Stage 2／13.01 正式地圖 | 已用 Neon、Omen、Veto、Viper、Fade／Sova 完成 2:0 | EF |
| 同 Patch／同賽事樣本 | 0 張正式地圖 | 2 張正式地圖 | EF，但樣本極小 |

### 全地圖逐圖分析

| 地圖 | KC 狀態 | EF 狀態 | 對位重點 | 單圖傾向 | Veto 意義 |
| --- | --- | --- | --- | --- | --- |
| Ascent | 5 月 H2H 曾 13:10 取勝，但跨 Patch；同版本樣本不足 | 13.01 正式樣本不足，整體熱度較佳 | KC 舊有控圖基礎對 EF 當前火力；舊 H2H 僅弱先驗 | KC 52% / EF 48%（低至中信心） | KC 替代 pick；EF 後續 ban 候選 |
| Breeze | 對 NRG 6:13；近期防守與進攻拆分缺資料 | 對 Liquid veto 中後續 ban，未出賽 | KC 近期內容偏弱，EF 僅以整體狀態補強 | KC 45% / EF 55%（低信心） | KC 後續 ban 候選 |
| Haven | 對 NRG 7:13，但歷史基礎仍是 KC 現行池較深路徑 | 對 Liquid 為未使用 decider，近期正式樣本不足 | KC 的熟悉度對 EF 未驗證同版本準備 | KC 55% / EF 45%（中低信心） | KC 最合理 pick |
| Lotus | KC 近期有效樣本不足，原模型基準偏弱 | 13.01 以 13:2 擊敗 Liquid，角色結構已驗證 | EF 的 Viper／Initiator 結構與重奪樣本明顯較完整 | KC 36% / EF 64%（中信心） | EF 首選圖 |
| Split | KC 同版本樣本不足 | 13.01 以 13:6 擊敗 Liquid；Favian、Izzy開局火力突出 | EF 有現成攻防與角色證據，KC 缺乏反證 | KC 35% / EF 65%（中信心） | KC 首 ban |
| Sunset | 雙方近期有效正式樣本近乎空白 | 雙方近期有效正式樣本近乎空白 | 僅按整體強度與角色結構做收縮，不能視為實證圖 | KC 44% / EF 56%（低信心） | 預測 decider |
| Summit | 新圖，無頂級正式樣本 | 新圖，無頂級正式樣本 | 無方向性證據，採中性先驗 | KC 50% / EF 50%（極低信心） | EF 預測首 ban；若放行須重算 |

### 預測 Ban/Pick 流程

1. KC ban Split：EF 已有 13.01 的 13:6 實戰，而 KC 缺少同版本反證。
2. EF ban Summit：新圖準備完全不可觀測，模型主情境假設 EF 移除最大方差。
3. KC pick Haven：KC 最可驗證的取圖路徑，單圖約 55%。
4. EF pick Lotus：EF 剛以 13:2 驗證角色結構，單圖約 64%。
5. KC ban Breeze：降低 EF 以整體熱度擴張第二條取圖路徑。
6. EF ban Ascent：移除 KC 舊 H2H 仍保留的小幅優勢。
7. Sunset decider：EF 約 56%，但樣本近乎空白，屬低信心決勝圖。

### 深度戰況分析

- KC 的系列賽生存條件是先拿 Haven，並讓 Ascent 留在後段；若實際 veto 同時失去這兩條路徑，EF 2:0 機率會上升。
- EF 的優勢集中在已展示的 Split／Lotus，而不是全面碾壓。首戰兩圖數據必須強收縮，不能直接外推為穩定 65% 以上系列優勢。
- EF 的同版本角色結構較完整；KC 的 LewN／N4RRATE 雙 Duelist 配置在新 Patch 的分工與 caller 配合仍是主要未知。
- 第一場在資料截止時已跨過原定開賽時間；任何正式 veto、選邊或首回合資訊都會使這份 pre-veto 分布失效。

### 模型校準檢核

- Patch／特務依賴：EF 有兩圖 13.01 證據，KC 沒有；已提高 EF 的近期權重，但因樣本僅兩圖而強收縮。
- 同賽事節奏：EF 已完成 Stage 2 首戰且內容強勢；KC 尚未展示同版本內容，熱手差異列為 EF 優勢。
- H2H 錨定風險：KC 2:1 EF 的舊 H2H 跨 Patch，且 Fracture、Pearl 已退出，只保留 Ascent 弱先驗。
- 已公布 veto 重算：輸入未包含實際 veto，因此沒有假裝使用 post-veto 資訊；正式 veto 出現後必須建立新版快照。
- 外部資料反證：VLR 區域排名偏向 EF；只作基準收縮，不覆蓋逐圖與同版本證據。
- 橫掃風險：KC 被 0:2 機率 28%，EF 被 0:2 機率 18%；打滿三圖 54%。
- agy 修正：接受時序失效與信心偏高批評；新圖 Summit 維持 50/50，Sunset 保留低信心方向，不用不存在的樣本硬改平均勝率。

### 賽果預測模型

| 勝方 | 直落二 | 打滿 |
| --- | ---: | ---: |
| Karmine Corp | 2:0 · 18% | 2:1 · 24% |
| Eternal Fire | 2:0 · 28% | 2:1 · 30% |

- 預測比分：Eternal Fire 2:1。
- 獨贏機率：KC 42% / EF 58%。
- 至少一圖：KC 72% / EF 82%。
- 模型信心度：73%（兩場共用的裁決後五項加權信心；本場另受時效失效限制）。
- 核心風險：實際 veto 與比賽狀態未知；不能作即時投注或賽況建議。

## Team Vitality vs Natus Vincere 完整分析

- 預測快照：截至原資料截止時間的 pre-veto 歷史快照。
- 資料截止：2026-07-17 23:06:04（UTC+8）；原定開賽為 2026-07-18 02:00。
- 最終方向：Team Vitality 56%，預測 Vitality 2:1；正式 veto 與即時價格缺失，因此只屬模型方向。

### 預計先發名單確認

- Team Vitality：Derke（Jett／主 Duelist）、Sayonara（Phoenix／Raze／Sova 彈性位）、Chronicle（Sentinel／Viper）、Jamppi（Initiator）、PROFEK（Controller）。無 stand-in 標示。
- Natus Vincere：Ruxic（Omen／Controller）、hiro（Viper／Vyse）、chloric（Skye／Sova／Initiator）、ExiT（Waylay／Yoru／主 Duelist）、CyvOph（Sage）。無 stand-in 標示；同版本首戰角色結構已確認。

### 數據對比矩陣

| 指標 | Team Vitality | Natus Vincere | 優勢方 |
| --- | --- | --- | --- |
| 近期狀態 | 最近五場 2:0 FUT、0:2 Leviatan、2:0 KC、2:1 NRG、1:2 Nongshim | Patch 13.01 首戰 2:0 FUT，Split 13:6、Ascent 13:9 | NAVI 熱手；Vitality 長窗較穩 |
| 地圖池深度 | Ascent、Haven、Lotus有小優基準；Split近期偏弱 | Split已有同版本驗證；Ascent也完成13:9 | Vitality深度 / NAVI Split |
| 手槍局勝率 | N/A（缺少可交叉查核聚合） | N/A（缺少可交叉查核聚合） | 無法判定 |
| 首殺能力 | 缺少 13.01 FK/FD 聚合 | ExiT 10/7，但僅兩圖小樣本 | NAVI 小樣本 |
| 攻方表現 | N/A（缺少同版本攻方拆分） | N/A（缺少同版本攻方拆分） | 無法判定 |
| 守方表現 | N/A（缺少同版本守方拆分） | N/A（缺少同版本守方拆分） | 無法判定 |
| 核心火力 | Derke 提供單點上限；尚無 Stage 2 數據 | hiro 280 ACS、1.68 K/D；ExiT 260 ACS | NAVI 當前樣本 / Vitality 長窗 |
| 版本／Meta 適應 | 尚無 Stage 2／13.01 正式地圖 | Waylay／Yoru、Omen、Viper／Vyse、Skye／Sova 已完成 2:0 | NAVI |
| 同 Patch／同賽事樣本 | 0 張正式地圖 | 2 張正式地圖 | NAVI，但樣本極小 |

### 全地圖逐圖分析

| 地圖 | Vitality 狀態 | NAVI 狀態 | 對位重點 | 單圖傾向 | Veto 意義 |
| --- | --- | --- | --- | --- | --- |
| Ascent | 最近一場自選圖 13:10，長窗基準較穩 | 13.01 在 FUT 自選圖以 13:9 取勝 | Vitality 基準深度對 NAVI 同版本熱度 | Vitality 55% / NAVI 45%（中低信心） | Vitality 預測 pick |
| Breeze | 長窗基準尚可，但最近曾 2:13 落敗 | 前場首輪被 FUT ban，近期實戰不足 | Vitality 波動大，NAVI 可作針對性選圖 | Vitality 52% / NAVI 48%（低信心） | NAVI 預測 pick |
| Haven | Vitality 有可用歷史基礎 | NAVI 前場首 ban，近期正式樣本不足 | Vitality 熟悉度較佳，NAVI可能直接移除 | Vitality 58% / NAVI 42%（中低信心） | NAVI 首 ban |
| Lotus | Vitality 長窗深度略佳但近期走弱 | NAVI 前場後續 ban，沒有同版本實戰 | 雙方都缺當前版本證據，Vitality僅基準小優 | Vitality 54% / NAVI 46%（低信心） | NAVI 後續 ban 候選 |
| Split | 最近一場 7:13，內容偏弱 | 13.01 自選圖 13:6，角色與火力已驗證 | NAVI 的 ExiT／hiro熱度對 Vitality近期弱點 | Vitality 40% / NAVI 60%（中信心） | Vitality 必須優先 ban |
| Sunset | 雙方正式樣本不足；只按整體基準微調 | 前場僅成為未使用 decider | 缺乏方向性實證，臨場 BP 與選邊影響大 | Vitality 52% / NAVI 48%（低信心） | 預測 decider |
| Summit | 新圖，無頂級正式樣本 | 新圖，無頂級正式樣本 | 無方向性證據，採中性先驗 | Vitality 50% / NAVI 50%（極低信心） | Vitality 後續 ban；若放行須重算 |

### 預測 Ban/Pick 流程

1. Vitality ban Split：NAVI 已在同版本以 13:6 驗證，而 Vitality 最近以 7:13 落敗。
2. NAVI ban Haven：NAVI 前場即採首 ban，且 Vitality 在此圖有較深基準。
3. Vitality pick Ascent：Vitality 最近自選圖 13:10，模型約 55%。
4. NAVI pick Breeze：以 Vitality 最近 2:13 的波動作為針對點；模型仍接近五五開。
5. Vitality ban Summit：移除新圖不可觀測方差。
6. NAVI ban Lotus：延續前場移除傾向，避免 Vitality 長窗小優。
7. Sunset decider：Vitality 約 52%，但屬低信心圖。

### 深度戰況分析

- Vitality 的 56% 小優主要來自較高的區域基準與 Ascent／Haven／Lotus 三條可執行路徑，不是當前 Patch 熱度。
- NAVI 的翻轉核心是 Split。若 Vitality沒有首 ban Split，NAVI 的取圖、至少一圖與系列爆冷機率都應上修，原 56/44 方向可能接近翻轉。
- NAVI 已用 ExiT、hiro、Ruxic 的同版本角色結構完成 2:0；Vitality雖有 Derke上限與多角色彈性，但尚未在 Stage 2 驗證。
- Breeze 與 Sunset 都接近五五開，因此系列分布將三圖機率放到 60%，不把 Vitality小優誤寫成穩定橫掃。

### 模型校準檢核

- Patch／特務依賴：NAVI 有兩圖 13.01 證據，Vitality沒有；已納入熱手情境並對兩圖小樣本強收縮。
- 同賽事節奏：NAVI 2:0 FUT 的內容支持當前即戰力；Vitality的休息與長窗基準不能直接抵銷實戰缺口。
- H2H 錨定風險：本場沒有用舊 H2H 主導方向，主要依逐圖路徑與同版本樣本。
- 已公布 veto 重算：原輸入尚未含正式 veto；正式地圖順序出現後必須建立新快照，尤其檢查 Split 是否被放行。
- 外部資料反證：VLR 區域排名偏向 Vitality；只作基準先驗，未覆蓋 NAVI 的同版本 Split／Ascent 表現。
- 橫掃／反掃風險：Vitality被 0:2 為 18%，NAVI被 0:2 為 22%；打滿三圖 60%。
- agy 修正：整體信心由 77% 降為 73%；Sunset與Summit列為低／極低信心，Summit維持50/50中性先驗。

### 賽果預測模型

| 勝方 | 直落二 | 打滿 |
| --- | ---: | ---: |
| Team Vitality | 2:0 · 22% | 2:1 · 34% |
| Natus Vincere | 2:0 · 18% | 2:1 · 26% |

- 預測比分：Team Vitality 2:1。
- 獨贏機率：Vitality 56% / NAVI 44%。
- 至少一圖：Vitality 82% / NAVI 78%。
- 打滿三圖：60%，公允賠率 1.67。
- Vitality獨贏公允賠率：1.79。
- 模型信心度：73%（裁決後五項加權）。
- 核心風險：Vitality若放出 Split，NAVI取圖與系列翻轉機率會明顯上升；沒有即時盤價，不能確認 EV。

## 最終機率

### KC–EF：Ascent 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 勝圖 | 52% | 1.92 |
| Eternal Fire 勝圖 | 48% | 2.08 |

### KC–EF：Breeze 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 勝圖 | 45% | 2.22 |
| Eternal Fire 勝圖 | 55% | 1.82 |

### KC–EF：Haven 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 勝圖 | 55% | 1.82 |
| Eternal Fire 勝圖 | 45% | 2.22 |

### KC–EF：Lotus 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 勝圖 | 36% | 2.78 |
| Eternal Fire 勝圖 | 64% | 1.56 |

### KC–EF：Split 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 勝圖 | 35% | 2.86 |
| Eternal Fire 勝圖 | 65% | 1.54 |

### KC–EF：Sunset 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 勝圖 | 44% | 2.27 |
| Eternal Fire 勝圖 | 56% | 1.79 |

### KC–EF：Summit 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 勝圖 | 50% | 2.00 |
| Eternal Fire 勝圖 | 50% | 2.00 |

### KC–EF：BO3 精確比分主分布

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 2:0 | 18% | 5.56 |
| Karmine Corp 2:1 | 24% | 4.17 |
| Eternal Fire 2:0 | 28% | 3.57 |
| Eternal Fire 2:1 | 30% | 3.33 |

### KC–EF：系列賽勝率

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 勝 | 42% | 2.38 |
| Eternal Fire 勝 | 58% | 1.72 |

### KC–EF：Karmine Corp 至少一圖

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 至少取得一圖 | 72% | 1.39 |
| Karmine Corp 被 0:2 橫掃 | 28% | 3.57 |

### KC–EF：Eternal Fire 至少一圖

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Eternal Fire 至少取得一圖 | 82% | 1.22 |
| Eternal Fire 被 0:2 橫掃 | 18% | 5.56 |

### KC–EF：橫掃狀態

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Karmine Corp 被橫掃 | 28% | 3.57 |
| Eternal Fire 被橫掃 | 18% | 5.56 |
| 無橫掃、系列賽打滿 | 54% | 1.85 |

### KC–EF：總地圖數

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| 兩圖結束 | 46% | 2.17 |
| 三圖打滿 | 54% | 1.85 |

### VIT–NAVI：Ascent 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 勝圖 | 55% | 1.82 |
| Natus Vincere 勝圖 | 45% | 2.22 |

### VIT–NAVI：Breeze 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 勝圖 | 52% | 1.92 |
| Natus Vincere 勝圖 | 48% | 2.08 |

### VIT–NAVI：Haven 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 勝圖 | 58% | 1.72 |
| Natus Vincere 勝圖 | 42% | 2.38 |

### VIT–NAVI：Lotus 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 勝圖 | 54% | 1.85 |
| Natus Vincere 勝圖 | 46% | 2.17 |

### VIT–NAVI：Split 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 勝圖 | 40% | 2.50 |
| Natus Vincere 勝圖 | 60% | 1.67 |

### VIT–NAVI：Sunset 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 勝圖 | 52% | 1.92 |
| Natus Vincere 勝圖 | 48% | 2.08 |

### VIT–NAVI：Summit 條件式單圖勝率（若進入系列賽）

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 勝圖 | 50% | 2.00 |
| Natus Vincere 勝圖 | 50% | 2.00 |

### VIT–NAVI：BO3 精確比分主分布

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 2:0 | 22% | 4.55 |
| Team Vitality 2:1 | 34% | 2.94 |
| Natus Vincere 2:0 | 18% | 5.56 |
| Natus Vincere 2:1 | 26% | 3.85 |

### VIT–NAVI：系列賽勝率

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 勝 | 56% | 1.79 |
| Natus Vincere 勝 | 44% | 2.27 |

### VIT–NAVI：Team Vitality 至少一圖

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 至少取得一圖 | 82% | 1.22 |
| Team Vitality 被 0:2 橫掃 | 18% | 5.56 |

### VIT–NAVI：Natus Vincere 至少一圖

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Natus Vincere 至少取得一圖 | 78% | 1.28 |
| Natus Vincere 被 0:2 橫掃 | 22% | 4.55 |

### VIT–NAVI：橫掃狀態

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| Team Vitality 被橫掃 | 18% | 5.56 |
| Natus Vincere 被橫掃 | 22% | 4.55 |
| 無橫掃、系列賽打滿 | 60% | 1.67 |

### VIT–NAVI：總地圖數

| 結果 | 機率 | 公允賠率 |
| --- | ---: | ---: |
| 兩圖結束 | 40% | 2.50 |
| 三圖打滿 | 60% | 1.67 |

## 判斷重點

- KC–EF：EF 58%、KC 42%；EF 2:1 為單一最高比分結果 30%，KC 被橫掃機率 28%。
- VIT–NAVI：Vitality 56%、NAVI 44%；Vitality 2:1 為單一最高比分結果 34%，三圖機率 60%。
- KC 最清楚的取圖路徑是 Haven；EF 的主要優勢圖為 Lotus 與 Split。
- Vitality 必須優先處理 NAVI 的 Split；若放行，系列賽可能接近翻轉。
- Summit 採中性先驗；Sunset 的小幅傾向只代表基準估計，兩圖均需視為低信心。

## 紅隊與最終裁決

- agy 結論：revise — The primary prediction is internally consistent and the probability math is coherent. However, there is a temporal misalignment: the prediction was generated 19 minutes after the scheduled start time of the first match (Karmine Corp vs Eternal Fire), meaning it relies on a pre-veto simulation when real-time vetoes were already available. Additionally, the win rate models for the new maps Sunset and Summit introduce high uncertainty due to a total lack of historical data, which is not fully reflected in the final confidence score.
- 接受：f1, f3
- 否決：f2

| 修正欄位 | 原值 | 新值 | 理由 |
| --- | --- | --- | --- |
| thesis | 市場盲、Patch 13.01、pre-veto 快照。KC–EF 偏向 EF 2:1、EF 58%；VIT–NAVI 偏向 Vitality 2:1、Vitality 56%。 | 市場盲、Patch 13.01 快照。KC–EF 維持 EF 2:1、58%，但資料截止已晚於原定開賽時間，只能視為失效中的 pre-veto 歷史快照，不可作即時判斷；VIT–NAVI 維持 Vitality 2:1、56%。 | 接受 f1 的時序缺陷：第一場資料截止與產生時間均晚於原定開賽時間。輸入未證實實際 veto 內容，因此不以未知的 post-veto 資訊重寫機率，只明確限制快照用途。 |
| confidence.components.freshness | 95 | 85 | 第一場已進入原定開賽窗口，pre-veto 資訊可能在數分鐘內失效；第二場資料仍屬賽前新鮮資料。 |
| confidence.components.regime_relevance | 55 | 50 | Patch 13.01 樣本極少，KC、Vitality 尚無同版本 Stage 2 正式地圖樣本，且缺少近期 pistol%、thrifty% 與 clutch% 聚合。 |
| confidence.components.model_stability | 63 | 55 | 兩場均對未公布 veto 敏感，Sunset 可能成為決勝圖且有效樣本近乎空白；Summit 放行時的準備差異亦不可觀測。 |
| confidence.value | 77 | 73 | 依五項固定權重重算：0.25×82 + 0.20×85 + 0.25×80 + 0.20×50 + 0.10×55 = 73。 |

## 主要風險

- KC–EF 的資料截止時間為 23:06，晚於 23:00 原定開賽時間；若正式 veto、選邊或比賽內容已出現，本快照已失效，不能作即時建議。
- Patch 13.01 樣本極少；EF 與 NAVI 的同版本證據各僅兩張正式地圖，存在顯著小樣本與對手情境偏差。
- Summit 為新圖，四隊均無可用的頂級正式賽樣本；若意外放行，50% 中性先驗可能快速失效。
- Sunset 在四隊近期有效樣本中同樣近乎空白，卻可能成為兩場預測 veto 的決勝圖，增加比分分布的不穩定性。
- KC 與 Vitality 尚無 Patch 13.01／Stage 2 正式地圖內容，跨賽事基準可能高估版本適應速度。
- VIT–NAVI 對 veto 特別敏感；Vitality 放出 Split 是 NAVI 翻轉系列方向的主要條件。
- 全程未使用或推測市場價格，因此不能評估價格價值、EV 或注碼。

## 尚缺資料

- 兩場正式 map veto、地圖順序、pick owner 與選邊。
- KC–EF 在資料截止時是否已實際開始，以及 veto 是否已正式公布。
- Karmine Corp 與 Team Vitality 的 Patch 13.01／Stage 2 正式地圖樣本。
- 四隊在 Summit 的頂級正式賽樣本，以及 Sunset 的充分近期樣本。
- 可交叉查核的近期 pistol%、thrifty%、clutch% 與 KAST 聚合。
- 部分隊伍經當日官方確認的 IGL／caller 分工。

## 來源

- [2026 VCT EMEA Stage 2](https://valorantesports.com/en-GB/news/2026-vct-emea-stage-2)（confirmed；擷取 2026-07-17T22:37:00+08:00）
- [VCT 2026 EMEA Stage 2 event page](https://www.vlr.gg/event/2976/vct-2026-emea-stage-2)（confirmed；擷取 2026-07-17T23:06:00+08:00）
- [FUT Esports vs Natus Vincere - VCT 2026 EMEA Stage 2](https://www.vlr.gg/712803/fut-esports-vs-natus-vincere-vct-2026-emea-stage-2-w1)（confirmed；擷取 2026-07-17T22:48:00+08:00）
- [VALORANT Patch Notes 13.00](https://playvalorant.com/en-us/news/game-updates/valorant-patch-notes-13-00/)（confirmed；擷取 2026-07-17T22:59:00+08:00）
- [Karmine Corp vs Eternal Fire - VCT 2026 EMEA Stage 2](https://www.vlr.gg/712807/karmine-corp-vs-eternal-fire-vct-2026-emea-stage-2-w1)（confirmed；擷取 2026-07-17T23:06:00+08:00）
- [Team Vitality vs Natus Vincere - VCT 2026 EMEA Stage 2](https://www.vlr.gg/712808/team-vitality-vs-natus-vincere-vct-2026-emea-stage-2-w1)（confirmed；擷取 2026-07-17T23:06:00+08:00）
- [Team Liquid vs Eternal Fire - VCT 2026 EMEA Stage 2](https://www.vlr.gg/712804/team-liquid-vs-eternal-fire-vct-2026-emea-stage-2-w1)（confirmed；擷取 2026-07-17T22:48:00+08:00）
- [VCT 2026 EMEA Stage 2 player stats](https://www.vlr.gg/event/stats/2976?dir=desc&sort=rating2)（confirmed；擷取 2026-07-17T22:52:00+08:00）
- [Karmine Corp team profile](https://www.vlr.gg/team/8877/karmine-corp)（confirmed；擷取 2026-07-17T22:42:00+08:00）
- [NRG vs Karmine Corp - EWC 2026](https://www.vlr.gg/706763/nrg-vs-karmine-corp-esports-world-cup-2026-decider-b)（confirmed；擷取 2026-07-17T23:03:00+08:00）
- [KC vs EF - EWC 2026 EMEA Qualifier](https://liquipedia.net/valorant/Match%3AID_EWC26EMAQ2_R01-M004)（confirmed；擷取 2026-07-17T22:32:00+08:00）
- [Team Vitality team profile](https://www.vlr.gg/team/2059/team-vitality)（confirmed；擷取 2026-07-17T22:42:00+08:00）
- [Team Vitality vs Nongshim RedForce - EWC 2026](https://www.vlr.gg/708421/team-vitality-vs-nongshim-redforce-esports-world-cup-2026-qf)（confirmed；擷取 2026-07-17T22:48:00+08:00）
- [VLR Europe rankings](https://www.vlr.gg/rankings/europe?active=0)（reported；擷取 2026-07-17T22:33:00+08:00）

本裁決是市場盲模型輸出，不含市場價格、EV、賠率門檻或注碼。KC–EF 已超過原定開賽時間，不能作即時投注或賽況建議；VIT–NAVI 亦須在正式 veto 公布後建立新快照。

## 簡表總結

| 時間 (UTC+8) | 對戰組合 | 賽制（BO?） | 預測比分 | 獨贏機率（Win%） | 受讓/破蛋機率（+1.5 maps / 至少一圖） | 推薦 | 模型信心度 | 核心風險（Key Risk） |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-07-17 23:00 | Karmine Corp vs Eternal Fire | BO3 | Eternal Fire 2:1 | KC 42% / EF 58% | KC 72% / EF 82% | 不下注 | 73%（整體；該場時效較低） | 資料截止晚於原定開賽時間；實際 veto 未知 |
| 2026-07-18 02:00 | Team Vitality vs Natus Vincere | BO3 | Team Vitality 2:1 | Vitality 56% / NAVI 44% | Vitality 82% / NAVI 78% | 模型傾向：Team Vitality；待即時價格 | 73% | Vitality 若放出 Split，NAVI 可明顯提高取圖與翻盤機率 |

預測使用模型：gpt-5.6-sol high
