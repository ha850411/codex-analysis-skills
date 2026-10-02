# Valorant 賽後檢討與模型校準

使用者要求檢討錯誤預測、回測賽前判斷、比較預測與實際結果、或要求「昨天失準後調整」時，使用這份流程。目標是修正流程，不是替原預測找理由。
先套用 `../../shared/postmortem-improvement.md`；只降低信心、上限、注碼或推薦等級不得視為完成修正。

## 1. 先重建事實

- 先用已發布報告內的 `forecast_id` 讀取 `.automation-state/valorant/history/forecasts/` 原快照；再查當次 run artifact 與已授權的匯出頁。保存來源檔雜湊；文字修訂版與未發布版本不能重複計分。找不到時標記 `baseline artifact missing`，不得事後重建原機率或計算 Brier／log loss。
- 核對比賽：賽事、階段、日期、賽制、Patch、場地或線上/線下、先發五人與是否有 stand-in。
- 核對結果：系列比分、每張地圖比分、pick/ban 順序、pick owner、選邊、OT、手槍局、eco/thrifty、關鍵 timeout 後回合。
- 核對內容：官方 VOD、VLR match page、RIB.gg/THESPIKE 數據、Valorant Esports match centre、官方賽後摘要。
- 若只能取得使用者截圖、部分 VOD 或社群摘要，必須標記資料限制，不得硬補未知比分或選手數據。
- 另建 `scenario coverage` 欄：逐圖實際五人、首兩輪 ban、兩張 pick、pick owner、decider 是否出現在賽前主分布的正權重情境中；完整覆蓋須由同一條情境同時成立。六人名單若只覆蓋其中一組五人，標記 `lineup_by_map coverage miss`。敏感度路徑即使完全命中，也只記研究命中，不計入主分布覆蓋。
- 分清「預估五人／特務是否正確」與「是否實際入模」。`scenario_coverage` 各維度用 `true`（覆蓋）、`false`（已建模但漏掉實際路徑）、`not_modeled`（未建模）、`unknown`（缺驗證證據）；主情境只有 `unresolved-map-order` 時使用 `not_modeled`，不能誤報臨時換人。另存敏感度與逐圖事實核對，不把兩種覆蓋相加。
- 枚舉所有合法 veto 時，另列實際完整行動路徑的原權重，以及圖序／pick owner 組合的原權重；正權重覆蓋不證明偏好估計準確。五人、player→agent 配置與起始攻守分開核對；未打決勝圖不補造實際五人／特務。用 `forecast-engine.md` 的 `audit-model-use` 區分主系列與單圖補充中的特徵使用。

## 2. 重建原預測

- 原推薦勝方、精確比分、勝率、至少一圖機率、信心度與注碼。
- 原快照保存狀態、`forecast_id`、模型版本、skill revision、資料截止與預定開賽時間；若缺失，把所有需原機率的指標填 `N/A（baseline artifact missing）`。
- 原本支撐預測的核心假設：Patch、同賽事樣本、H2H、地圖池、已公布 veto、pick owner、特務池、主 Duelist 狀態、熱手/休息。
- 分開記錄勝方／比分命中與核心論述是否成立。勝方命中仍可伴隨關鍵自選圖被禁或選圖方判錯；兩圖小比分差的2–0，也不能單憑系列比分倒推原勝率偏低。角色與經濟歸因須有逐圖數據，不能把單場首殺極端值當成持續能力。
- 若原預測是在官方 veto 公布後做出，必須檢查是否真的 post-veto 重算，或只是把已公布 veto 填進賽前模型。

## 3. 判定失準等級

| 等級 | 定義 | 處理 |
| --- | --- | --- |
| 小偏差 | 勝方正確，比分差一張圖 | 檢查精確比分分布是否過窄 |
| 中偏差 | 勝方錯誤但系列接近，例如 BO3 1:2、BO5 2:3 | 核對原勝率、取圖路徑與同類殘差，不直接拉向 50% |
| 大偏差 | 勝方錯誤且比分差至少兩張圖，或內容明顯反向 | 找可重複機制；有賽前可觀察觸發條件才建 challenger |
| 地圖分布大偏差 | 勝方方向正確，但至少一圖、+1.5 maps、3:1/3:2 分布明顯錯 | 分開檢討獨贏模型與地圖分布模型 |
| Post-veto 失準 | 已公布 veto 後仍錯估 pick/ban 訊號、選邊或 anti-strat | 強制加入 left-through 與 map order 重算 |
| 系統性偏差 | 同賽事、同隊伍、同類 BO5 或同 Patch 連續錯 | 用同類 cohort 做 paired walk-forward |
| 情境覆蓋失敗 | 實際 lineup 或關鍵 veto 路徑不在賽前主分布情境內 | 修正情境生成；即使勝方正確也算流程缺口 |
| 比分眾數集中 | 多場眾數反覆落在 2:0、2:1 或同類 BO5 比分 | 同看完整尾部機率與跨日賽果；眾數一致本身不證明失校 |

## 4. 錯誤歸因框架

逐項判斷，不要只用「槍法爆發」或「冷門」帶過。

- 資料錯漏：先發、stand-in、Patch、地圖池、官方 veto、選邊、賽制或時間是否過期。
- 近期權重錯配：是否過度相信跨 Patch H2H、整季名氣、區域強度或舊地圖勝率，而低估同賽事近兩週樣本。
- Post-veto 訊號誤判：對手主動放出熱門方強圖、近期少打圖或過去常 ban 圖時，是否被錯當成熱門方免費優勢。
- Anti-strat 誤判：近期同圖曝光多的一方是否被針對；pick 方是否因公開樣本過多被讀透開局、站位、重奪與默認節奏。
- BO5 地圖分布誤判：是否把三張 52–56% 小優圖加總成穩定 3:1；是否忽略 0:2 開局、第五圖、反掃或 underdog 兩條取圖路徑。
- 特務陣容誤判：是否高估 star duelist 的硬解能力，低估對手的 sentinel/controller 節奏、retake utility、anti-dive 或 post-plant。
- 手槍與經濟誤判：是否低估手槍局、bonus、eco/thrifty 對 Valorant 小樣本地圖的放大效果。
- 教練組與 timeout 誤判：是否低估勝方局間修正、暫停後回合成功率、或敗方連續被同一弱點打穿。
- 市場/品牌偏誤：是否因 PRX、SEN、Fnatic、DRX、G2、LEV 等隊名或人氣敘事提高信心。
- 合理變異：以逐回合或 VOD 證據判斷 OT、eco、clutch 等影響；多圖重複只能形成待驗證假設，不能直接判定模型錯誤或推論教練準備。
- 未展示誤當弱圖：是否把零樣本、常 ban 或未被選到誤當成負面戰績，忽略 veto 的選擇偏差。
- 情境有寫但未入模：是否在正文寫出「若 X 則翻盤」，卻沒有給情境權重，也沒有混入精確比分主分布。
- 信心度可用性錯配：是否因資料新鮮就給高信心，卻沒有讓未確認 veto、pick owner、map order 或交叉名單組合進入 `名單／先發確定度` 與 `模型穩定性`。
- 盃賽名單異動與練兵折扣（cup_lineup_turnover_discount）：一線名門隊伍在非聯賽正賽之次級盃賽若輪換核心指揮（IGL）或 2 名以上選手，是否因防守體系瓦解與戰意落差被次級全主力隊伍針對突破。

## 5. 大偏差後的校準規則

- 將該場納入 Brier／log loss 與同類 calibration cohort。找到可重複的資料、Patch、veto、anti-strat 或分布流程錯誤時，修正實際產生機率的流程；不因單場結果固定扣信心。
- 候選修正必須寫出賽前可觀察觸發條件，並以相同 Patch、賽制與 pre/post-veto 快照做 paired walk-forward；只做風控降級的版本直接拒絕。
- 若偏差涉及盃賽輪換或 IGL 缺席，查核是否為賽前可知資訊，建立 roster 情境 challenger 並做配對驗證；不再啟動固定扣勝率或橫掃機率下限。
- 若失準集中在 BO5 精確比分，下一次 BO5 必須列出 3:0、3:1、3:2、反向 3:2 的機率分布，不可只給單一比分。
- 若原模型把落敗方至少一圖給到高機率但實際被橫掃，重建精確比分主分布並檢查取圖路徑與 map order；只有確認流程錯誤才調整，不能因一次賽果硬設 65–70% 上限。
- 若高機率熱門方實際輸掉，檢查逐圖相關性、veto 與同 Patch 樣本；下一場機率仍由新快照證據計算，不硬設 58–60% 上限。
- 若官方 veto 已公布後仍失準，下一次分析要先寫「post-veto 重新校準」小節，再輸出模型機率。
- 若實際 lineup / veto 未進主分布，先分辨漏掉有證據路徑、研究未入模與原證據不足。資料映射錯誤可修復；新增路徑權重或角色效果須隔離驗證，不憑這次賽果補權重，也不直接調整隊伍強度。
- 若同批至少四場 BO3，對稱檢查 2-0 與 2-1 眾數比例、整批預期橫掃與實際橫掃。共同狀態、尾部或收縮參數僅可作 challenger，不因眾數集中就自動加入或加重；原模型已有共同狀態時避免重複計算。

## 6. Post-veto 重算檢查

官方 veto 公布後，逐圖回答：

- 這張圖是誰 pick，是否符合最近三場/同 Patch 傾向？
- 對手為何願意放出這張圖？是沒有 ban 權、另有更高優先級，還是可能準備 anti-strat？
- pick 方近期同圖樣本是否太公開，是否容易被針對固定開局、重奪路線或 ult economy？
- 選邊是否放大 pistol/defense/attack 的優勢？
- 若前兩圖輸贏反向，後面第 3–5 圖的心理、timeout、coach prep 與 agent pool 是否會改變？

## 7. 批次機率診斷

先以共用 `shared/forecast/cli.py evaluate` 評分原 v2 快照的副本，只附加實際結果、來源與觀察時間，不改賽前欄位。實際比分按原 `participants` 的 A/B 順序重排。將 evaluated forecasts 與逐場誤差帳本保存至 `.automation-state/valorant/history/`；先讀同 model／parameter version、snapshot 的歷史 cohort，再加入本批。不同版本、條件單圖、敏感度與事後重算分開；同場修訂版本只選實際發布者。

四場以上的同批／跨日同類 BO3 使用 `../scripts/audit_batch.mjs`，小批亦可用於診斷。輸入 `{ "matches": [...] }`：v2 保留 fraction 主分布、`actual_score`（如 `2-1`）、五維 `scenario_coverage`，全部維度為 true 時另附 `joint_scenario_covered`；legacy 百分比與 `a_2_1` 格式仍相容。至少記錄：

- 勝方命中為主要指標、比分命中為次要；Brier score、log loss、情境覆蓋與預測可用率同步評估，不以單一指標宣稱改善。
- 精確比分使用 multiclass log loss，並列出模型給實際比分的機率。
- 預期橫掃場數為 `Σ[P(A 2-0)+P(B 2-0)]`；與實際橫掃場數比較。
- 共用 `brier` 採 A/B/draw 誤差平方加總（無和局時等於二元 Brier 的兩倍）。批次工具保留舊 `winner_brier`，並以 `winner_brier_sum` 對齊 v2；比較時不可混用。
- 用 Poisson-binomial 同時列「至多／至少／恰好」實際橫掃數；零橫掃時只看至少零場必為 100%，沒有診斷力。註明系列間獨立假設，不能把此尾機率當校準證明。
- 同時計算 2-0 與 2-1 眾數比例；≥80% 只觸發檢查。比較的是總橫掃機率和賽果，而非把 27% 的比分眾數誤讀成 100% 橫掃預測。
- 分別統計五維 verified miss、not_modeled、unknown 與 joint coverage；這是流程品質指標，不受勝方是否猜對影響。`scenario_covered` 只供舊快照相容。

單批樣本不足以宣稱模型已失校。只有同類 cohort 或 walk-forward 回測重複出現，才調整長期先驗；但資料漏列、情境未入模、相依機率不一致可立即修正。

## 8. 檢討輸出格式

1. 賽果確認與資料來源。
2. 原快照可用性、原預測 vs 實際結果；快照缺失時列出已搜尋位置與不可計算欄位。
3. 批次機率診斷：Brier / log loss、精確比分、預期 vs 實際橫掃、眾數集中度。
4. 情境覆蓋：實際 lineup、veto、pick owner 與 decider 是否進入賽前主分布。
5. 被推翻的賽前假設。
6. 地圖逐張復盤：pick owner、比分、關鍵內容、原本誤判點。
7. 主要錯誤歸因。
8. 可否證修正假設。
9. 基準版、挑戰版、驗證結果與裁決。
