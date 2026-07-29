# LoL S Tier 自動排程

`predict_next_day.py` 先以 bo3.gg 公開 API 預查從 `automation/modules.json` 的 `lol.schedule.prediction` 起算、起點含且終點不含的 24 小時視窗。它會分別保存「API 伺服器端 S-tier 篩選」與「未套 tier 後在本地篩選」的原始回應，並合併兩者候選，避免單一篩選索引漏場。

bo3.gg 清單只作候選。Codex 必須再用涵蓋完整視窗的 Riot／賽區官方全域賽程列出 S-Tier `match_key` 集合；獨立側可用全域來源，或以逐聯賽頁面組成 coverage group，其聯集必須精確等於官方集合。聯賽專頁只能貢獻自身子集合，不能單獨證明跨賽區完整。bo3.gg 有 provider ID 時使用 `bo3:<id>`；上游缺場但雙來源確認時，使用由聯賽、UTC+8 時間與隊名確定性產生的 `lol:<league>:<time>:<team1>:<team2>`，不得因缺 bo3.gg ID 漏場。模型鎖定後，每場都必須依共用盤口收集契約產生 Odds-API 成功快照或分類錯誤 artifact；`market-collection.json` 的 match keys 必須與驗證清單完全一致，否則不可用一句「API 抓不到」跳過。只有官方集合與獨立聯集完全相同、沒有未解衝突，且 forecasts 與 market collection 的 match keys 都和驗證清單完全一致時，才會發布 Notion `daily-summary` 並寄送 SMTP Email。來源不一致、候選漏場尚未補齊或驗證檔缺失時一律失敗停止；空賽程仍必須由官方與獨立全域空集合確認後才會略過。

`review_today.py` 每天在 `lol.schedule.review` 鎖定前一日報告；只在報告與 JSONL 都未超過 24 小時，且 bo3.gg 上至少一場已預測賽事完賽時執行。它只檢討已完賽的 match ID。合理且通過驗證的 `lol-analysis` 修改會在隔離 worktree 中完成，送出並自動合併 GitHub PR；完成信件會附上 PR 網址與 merge commit。沒有證據支持的修改就不建立 PR。

原始報告保留 30 天。已評分預測會依不可變預測鍵去重保存到 `.automation-state/lol/history/evaluated-forecasts.jsonl` 並永久保留。此跨日 cohort 不受原始報告清理影響；每日檢討必須同時評估歷史與本批，不得只用單日結果修改模型。

報告位置：

- `.automation-state/lol/predictions/YYYY-MM-DD/prediction.md`
- `.automation-state/lol/predictions/YYYY-MM-DD/schedule-precheck.json`
- `.automation-state/lol/predictions/YYYY-MM-DD/bo3-filtered-response.json`
- `.automation-state/lol/predictions/YYYY-MM-DD/bo3-unfiltered-response.json`
- `.automation-state/lol/predictions/YYYY-MM-DD/market-collection.json`
- `.automation-state/lol/predictions/YYYY-MM-DD/odds-*.json` 或 `odds-*.error.json`
- `.automation-state/lol/predictions/YYYY-MM-DD/schedule-verification.json`
- `.automation-state/lol/reviews/YYYY-MM-DD/postmortem.md`
- Notion 網址：`.automation-state/lol/predictions/YYYY-MM-DD/notion-publish.json`

Dry-run 不會查詢賽程或啟動 Codex：

```bash
python3 automation/lol/predict_next_day.py --date 2026-07-22 --dry-run
python3 automation/lol/review_today.py --date 2026-07-22 --dry-run
```

使用 `automation/install_crontab.sh` 安裝排程。LoL 預設每天台灣時間 09:00 執行預測、08:30 檢討前一日報告；透過 `automation/modules.json` 調整模組、模型、推理強度與排程時間。修改時間後需重新執行安裝程式。

LoL 與 MLB 共用 `AUTOMATION_NOTIFICATION_EMAIL`，不需要 LoL 專屬收件信箱。賽後檢討固定從 `origin/master` 建立 `feature/LOL-MMDD` 分支，例如 `feature/LOL-0721`。
