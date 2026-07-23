# LoL S Tier 自動排程

`predict_next_day.py` 先以 bo3.gg 公開 API 預查從 `automation/modules.json` 的 `lol.schedule.prediction` 起算、起點含且終點不含的 24 小時視窗。它會分別保存「API 伺服器端 S-tier 篩選」與「未套 tier 後在本地篩選」的原始回應，並合併兩者候選，避免單一篩選索引漏場。

bo3.gg 清單只作候選。Codex 必須再用一個官方來源與一個不同營運方的獨立來源驗證完整賽程，寫入 `schedule-verification.json`。只有雙來源支持相同集合、所有場次具備 bo3.gg match ID、沒有未解衝突，且 forecasts 的 match IDs 與驗證清單完全一致時，才會發布 Notion `daily-summary` 並寄送 SMTP Email。來源不一致、候選漏場尚未補齊或驗證檔缺失時一律失敗停止；空賽程也必須雙來源確認後才會略過。

`review_today.py` 每天在 `lol.schedule.review` 鎖定前一日報告；只在報告與 JSONL 都未超過 24 小時，且 bo3.gg 上至少一場已預測賽事完賽時執行。它只檢討已完賽的 match ID。合理的 `lol-analysis` 修改會在隔離 worktree 中完成，並送出 GitHub PR；沒有證據支持的修改就不建立 PR。

報告位置：

- `.automation-state/lol/predictions/YYYY-MM-DD/prediction.md`
- `.automation-state/lol/predictions/YYYY-MM-DD/schedule-precheck.json`
- `.automation-state/lol/predictions/YYYY-MM-DD/bo3-filtered-response.json`
- `.automation-state/lol/predictions/YYYY-MM-DD/bo3-unfiltered-response.json`
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
