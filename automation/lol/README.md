# LoL S Tier 自動排程

`predict_next_day.py` 使用 bo3.gg 公開 API 預查下一個台灣日曆日。只有設定來源至少包含一場等級恰好為 `s` 的 LoL 賽事時，才會啟動 Codex。通過驗證的產物會發布為一筆 Notion `daily-summary`，接著寄送 SMTP Email。

`review_today.py` 只在報告與 JSONL 都未超過 24 小時，且 bo3.gg 上至少一場已預測賽事完賽時執行。它只檢討已完賽的 match ID。合理的 `lol-analysis` 修改會在隔離 worktree 中完成，並送出 GitHub PR；沒有證據支持的修改就不建立 PR。

報告位置：

- `.automation-state/lol/predictions/YYYY-MM-DD/prediction.md`
- `.automation-state/lol/reviews/YYYY-MM-DD/postmortem.md`
- Notion 網址：`.automation-state/lol/predictions/YYYY-MM-DD/notion-publish.json`

Dry-run 不會查詢賽程或啟動 Codex：

```bash
python3 automation/lol/predict_next_day.py --date 2026-07-22 --dry-run
python3 automation/lol/review_today.py --date 2026-07-22 --dry-run
```

使用 `automation/install_crontab.sh` 安裝排程：LoL 每天台灣時間 09:00 執行預測、22:30 執行賽後檢討。透過 `automation/modules.json` 切換模組、模型與推理強度。

LoL 與 MLB 共用 `AUTOMATION_NOTIFICATION_EMAIL`，不需要 LoL 專屬收件信箱。賽後檢討固定從 `origin/master` 建立 `feature/LOL-MMDD` 分支，例如 `feature/LOL-0721`。
