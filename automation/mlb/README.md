# MLB 自動排程

本目錄包含兩個供 macOS `crontab` 使用、以台灣時區解讀的工作：

- `predict_next_day.py`：21:00 先在不啟動 Codex 的情況下查詢 MLB 賽程；報告日期 21:00（含）至隔日 21:00（不含）的 24 小時視窗有比賽時，才預測全部賽事。若資料或生產模型不足，仍發布逐場缺口完整的 `degraded` 報告，不把 N/A 冒充模型預測。
- `review_today.py`：20:30 檢查前一日報告產物是否在 24 小時內；評分不可覆寫的原始預測，只套用有證據支持的 `mlb-analysis` 修正，並在合理時建立 GitHub PR。

執行報告與 Log 位於 `.automation-state/mlb/`，且已由 Git 忽略。賽後檢討在隔離的 worktree 中修改，因此不會碰觸使用者目前分支或尚未提交的變更。

## 前置需求

1. 執行 `codex login`。
2. 建議在倉庫根目錄 `.env` 加入 `GITHUB_PAT=github_pat_...`，或執行 `gh auth login -h github.com`。Token 需要倉庫 Contents write 與 Pull requests write 權限。
3. Mac 時鐘與時區必須是 Asia/Taipei。crontab 也會設定 `TZ=Asia/Taipei`，但 macOS cron 的觸發時間仍依機器時區。
4. 倉庫 remote 必須命名為 `origin`。賽後檢討固定從 `origin/master` 建立 `feature/MLB-MMDD` 分支。
5. 在 `.env` 設定 Notion 與 SMTP。通過驗證的預測會發布成一筆 `daily-summary` Notion 頁面，再寄送包含 Notion網址的 Email。

載入器只會從 `.env` 讀取允許清單內的自動排程、GitHub 與 SMTP 鍵，不會把密碼或 Token 寫入 crontab、Git remote、報告或 commit。

必要的發布與通知設定：

```dotenv
NOTION_TOKEN=secret_xxx
NOTION_DATA_SOURCE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
AUTOMATION_NOTIFICATION_EMAIL=you@example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=you@example.com
SMTP_PASSWORD=app-password
SMTP_FROM=you@example.com
```

供應商要求時，可使用 `SMTP_SECURITY=ssl` 搭配 465 Port。多位收件者以逗號分隔。如果 Notion 成功但寄信失敗，重新執行預測工作會重用已保存的 Notion 網址，只重試寄信，不會再次啟動 Codex。

不要將真實 Token 寫入已受 Git 追蹤的 `.env.example`。秘密只可保存在已忽略的 `.env`；若秘密曾被提交或推送，請立即輪替。

## 驗證與安裝

```bash
python3 automation/mlb/predict_next_day.py --date 2026-07-22 --dry-run
python3 automation/mlb/review_today.py --date 2026-07-22 --dry-run
automation/install_crontab.sh
```

`--date` 對預測與檢討都代表報告日期；檢討未指定日期時會自動選前一日報告。

共用安裝程式會保留所有無關的 cron 工作、遷移舊 MLB 專用區塊，並只派送 `automation/modules.json` 中已啟用的模組。

查看已安裝排程：

```bash
crontab -l
```

只移除共用受管排程：

```bash
automation/uninstall_crontab.sh
```

移除時會保留無關的 cron 工作與既有報告／Log。排程時間到達時 Mac 必須維持開機且未休眠；傳統 cron 不會在喚醒後補跑錯過的工作。
