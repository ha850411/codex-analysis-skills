# Dota 2 賽後檢討與模型校準

使用者要求檢討錯誤預測、回測賽前判斷、或比較預測與實際結果時，使用這份流程。
先套用 `../../shared/postmortem-improvement.md`；單純降信心、注碼或推薦等級不算模型修正。

## 1. 先重建事實

- 核對比賽：賽事、階段、日期、賽制、patch、先發與 stand-in。
- 核對結果：系列比分、每局勝方、Radiant/Dire、每局 draft、每局時長。
- 核對關鍵內容：分路結果、first blood、tower timing、Roshan/Aegis、核心 item timing、buyback、高地、決勝團。
- 來源優先：官方賽事資料、Liquipedia、STRATZ/DatDota/DOTABUFF/OpenDota、官方 VOD 或 DotaTV replay。
- 若只能取得部分 VOD 或摘要，需標記限制。

## 2. 重建原預測

- 原推薦勝方與精確比分。
- 原始勝率、精確比分分布、信心度、建議注碼。
- 原本支撐預測的核心假設：patch、英雄池、BP 優勢、分路、Roshan、late game、賽程、stand-in。
- 原本推薦的盤口：獨贏、+1.5、總局數、BO2 平局、精確比分。

## 3. 判定失準等級

| 等級 | 定義 | 處理 |
| --- | --- | --- |
| 小偏差 | 勝方正確，比分差 1 局 | 檢查精確比分分布是否過窄 |
| 中偏差 | 勝方錯誤，但系列接近，例如 1-2 / 2-3 | 檢查勝率是否過度集中 |
| 大偏差 | 勝方錯誤，且比分相差至少 2 局 | 建立可否證的權重／情境 challenger |
| 局數分布大偏差 | 勝方正確，但主推大分/敗方 +1.5/雙方取局，實際橫掃 | 重建取局與橫掃路徑並回測分布 |
| Draft 判斷大偏差 | 賽前 BP 假設被 Game 1/2 draft 明確推翻 | 修正賽前 draft 情境生成與 draft 後重算 |
| 系統性偏差 | 同類隊伍、同 patch 或同賽區連續錯誤 | 重新檢查來源、權重與模型假設 |

## 4. 錯誤歸因框架

逐項判斷，不要只用「爆冷」帶過。

- 資料錯漏：patch、stand-in、角色對調、賽制、賽程或 BO2 規則是否錯。
- 版本/BP 誤判：是否低估版本 OP、signature hero、ban pressure、flex pick 或 last pick cheese。
- 分路誤判：哪一路被打穿，support rotation 或 rune 控制是否與賽前假設相反。
- Timing 誤判：BKB/Blink/Orchid/Pipe/Mek/Aegis timing 是否推翻原模型。
- Roshan 誤判：第一盾、第二盾、視野與 pit 控制是否決定比賽。
- 高地與 buyback 誤判：是否高估收尾，或低估守高、買活二次團與 throw 風險。
- 近期權重錯配：是否過度相信整季戰績、舊 H2H 或隊伍名氣，而低估同 patch 近期內容。
- 市場/品牌偏誤：是否因人氣隊、明星選手或長期排名高估穩定性。
- 合理變異：若主要來自單次偷盾、極端暴斃或罕見 throw，標記為變異；但不能用變異掩蓋多局重複問題。

## 5. 大偏差後的校準規則

- 將該場納入 Brier／log loss 與同類 calibration cohort；找到可重複的資料、patch、draft、分路或分布流程錯誤時，優先修正產生機率的流程，不因單場冷門機械扣信心。
- 重建精確比分主分布；若原模型確實漏掉可驗證情境，再提高橫掃或反向比分機率，不為了配合賽果任意加寬。
- 候選修正要以相同 patch、賽制與預測時點做 paired walk-forward；未驗證時標記 experiment-only，不得用降低注碼宣稱已改善。
- 下一次同類 matchup 套用已通過驗證的賽前觸發條件；不得只記住該隊上一場結果。

## 6. Draft 後校準

若實際 draft 和賽前預測差距很大，檢討時要回答：

- 哪些 first phase ban/pick 改變了整個系列賽？
- 是否有未預期的 flex、角色對調或 cheese hero？
- 哪一個 last pick 直接改變 mid/carry/offlane 對位？
- 賽前是否低估某隊第二、第三套 draft 方案？
- 未看到 draft 前，是否應增加替代 BP 情境或重分配情境權重？

## 7. 檢討輸出格式

1. 賽果確認與資料來源。
2. 原預測 vs 實際結果。
3. 每局 draft 與關鍵轉折。
4. 被推翻的賽前假設。
5. 主要錯誤歸因。
6. 可否證修正假設。
7. 基準版、挑戰版、驗證結果與裁決。
