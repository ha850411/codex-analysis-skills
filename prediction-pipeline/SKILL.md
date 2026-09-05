---
name: prediction-pipeline
description: 協調可稽核的預測流程：使用者觸發 agy 紅隊時，先告知 Codex 主預測、agy 紅隊審查、Codex 最終裁決與條件式 post-market 決策使用的模型，無須等待確認便建立標準 input.json、執行主預測、紅隊審查、最終裁決、驗證並輸出 Markdown、JSON 與 YouTube 腳本。當預測或 *-analysis 請求提到「啟用 agy 紅隊」、「agy 紅隊審查」、「交給 agy 複核」、「雙模型審查」、agy、agy-cli 或模型互審時使用；一般單模型預測不得顯示模型計畫。
---

# Codex × agy 預測管線

只處理明確要求 agy、紅隊或模型互審的預測；一般單模型分析不額外啟動模型。領域分析依對應的 `*-analysis` skill。

## 啟動與資料

1. 讀 `references/model-defaults.json`，以使用者當次指定值優先；執行 `agy models` 驗證可用模型。設定無效或模型不可用時回報，不靜默換模型。
2. 告知本次主預測、紅隊、最終裁決與條件式市場決策模型，隨即執行；不等待再次確認。一般對話預設沿用目前會話模型，只有設定要求時才啟動 Codex CLI。
3. 讀 `references/runbook.md` 與 `references/contracts.md`，依對應 schema 建立 input 與 run 目錄；使用者不必自行提供 JSON 或 CLI。
4. 新計算使用 `../shared/forecast/contract.md` 的 canonical forecast，再以 `pipeline-input` 轉為既有 v1 輸入。主預測、紅隊與最終裁決只看市場隔離輸入。

## 審查與裁決

- 主報告必須先包含領域必要分析，讓 agy 審查全文。紅隊意見是待裁決的證據，不是替代預測。
- 主預測與最終裁決必須保留 `computed_probability_groups` 的計算值；需要更改機率時，先重建上游 canonical forecast，再重跑下游。舊 input 沒有此欄位時保留 legacy 模式並揭露計算溯源限制。
- 每個 finding 都須接受或否決，附理由與處置；每個 unresolved question 都須回覆或說明缺口及影響。實際數字與文字修改全部記入 changes。
- 以主報告的章節標題維持覆蓋；各節提供答案、缺口或不適用原因。刪除重複文字不受字數比例限制。
- agy 格式失敗先保存 raw 與錯誤，只允許同模型一次格式修復；再次失敗即停止該流程，不偽造成功 artifact。

## 市場與交付

- 機率鎖定後才按 `../shared/markets/collection-contract.md` 逐場收集價格、重試與保存成功／失敗憑證。市場不能回寫機率。
- 有價格才建立獨立 post-market 決策，覆蓋每個 bet_id 與簡表列；無價格仍完成模型報告並標 0u。玩法覆蓋不完整須明示。
- 執行管線 export 完成 schema、跨階段、信心度、機率、裁決與市場算術驗證；失敗回到上游修正。
- 依 `../shared/forecast/report-template.md` 輸出完整 prediction.md、prediction.json、chat-summary.md，按需求輸出口播腳本。聊天與完整報告均以唯一五欄簡表收尾，連結和來源放在簡表之前。
- 完整紅隊 finding 與裁決留在 JSON；正文只列會影響結論的修改。外部發布沿用既有授權，不因啟用 agy 自動取得發布授權。
