# 預測 skill 的配對驗收

供 skill／提示變更及賽後改善使用，不改正式報告模板。這份驗收將「指令與工具正常」「分析行為正確」「未來預測更準」分別記錄；任何一項不能代替另一項。

## 固定比較條件

修改前保存 skill、共用指引與相關 references 的內容及 SHA-256；保留使用者未提交變更作為本次基準。對 output-template、report-template、SKILL 內輸出區段、JSON schema 及渲染器建立雜湊。沒有使用者確認時，改後必須相同；不能透過共用指令繞過模板保護。

比較同一批問題、賽事、資料截止與來源封包。主比較固定模型 ID、reasoning 設定、工具能力與輸出模板，只改 skill 版本；同時換模型時另開一個比較，避免把差異歸錯原因。可重現的計算使用固定 seed；語言模型多次執行需事前固定次數並保留全部結果，不選最好的一次。

資料封包保留發布／查核時間、事件／局次定位及已知缺口。除非測試本身是查詢策略，使用封存來源並禁用網路；涉及查詢策略時另測工具回應，不能讓後來更新的賽果污染預測。測試不呼叫真實盤口、agy、寄信、Notion 或正式排程。

## 行為案例

案例在 [prediction-quality-cases.json](prediction-quality-cases.json)。`input` 是給受測版本的合成問題／證據；`expected` 僅供評分者，不能一起餵給受測版本。這些固定開發案例沒有真實賽事成效，不可充當樣本外資料。

按實際判斷、工具呼叫及產物核對，不能只搜尋關鍵詞或標題就算通過：

- 事實及時序：是否依最新有效內容裁決衝突、識別轉載與局次錯配、保留未解項。
- 領域到模型：是否分清實際特徵、分析者假設與未量化風險；是否仍完成可得研究。
- 機率與狀態：是否有同一主分布、合法終局、對應條件率、正確快照資格與市場隔離。
- 更新與裁決：是否有新事實／可重現錯誤才改數字；敏感度、模型共識與單場失準不冒充校準證據。
- 交付相容：是否保留使用者現有格式、數字與專用偏好，缺價不清空分析。

逐例保存 `pass`／`fail`／`not-run`、實際產物位置及原因。算術可交給既有 `shared.forecast.core` 驗算；這只驗證計算，不證明 GPT-6 在新提示下會正確採取行動。行為未實際執行時明列 not-run，不用單元測試數量代替。

## 真實成效

在看結果前鎖定測試日期、聯賽／賽制、快照選擇、主要指標及候選方案。兩版本使用相同當時資訊、完整目標集合，各自保存不可覆寫預測；缺機率場次仍在分母。無可稽核歷史資料時累積前瞻紀錄，不重建假的賽前優勢。

已有可評分紀錄時使用原入口：

```bash
python3 shared/forecast/cli.py evaluate paired-records.json \
  --baseline baseline-version --challenger challenger-version \
  --output comparison.json
```

先用 `evaluate --help` 核對實際介面。配對版本、事件、snapshot、截止與 eligibility 應一致；同場多快照分開分析，不把它們視為多場獨立比賽。若一版只有 historical_replay、另一版為 prospective，先分開整理資格，不能直接比較。

保留勝方命中為主要指標、比分為次要，另看 Brier、log loss、NBA／MLB 的得分／分差 MAE、覆蓋率及可用率。分聯賽、版本／賽制、預測時點與模型層級檢查，不用高信心子集替代完整集合，也不把一次推薦勝負或 ROI 當成模型品質。

採 [forecast/contract.md](../forecast/contract.md) 的原升版門檻；CLI 通過只取得 eligible-for-review。樣本不足或重要群組退步時保留 experiment-only；測試結果用來調參後，下一次須使用未看過的時間區段。skill 行為改善可據實記錄，只有配對成效成立才宣稱準確率提升。

GPT-6 指令整理依據：[官方 prompting best practices](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra#prompting-best-practices)。本流程把官方對指令衝突、主動完成與適量驗證的建議應用到既有預測系統；官方指南本身不證明體育預測準確率。
