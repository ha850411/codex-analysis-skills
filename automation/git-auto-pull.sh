#!/bin/bash

# 1. 設置專案路徑（請替換成你的實際目錄）
REPO_DIR="~/.agents/skills"
LOG_PATH="$REPO_DIR/.automation-state/logs/cron_pull.log"

# 2. 切換到專案目錄，並將執行日誌輸出到日誌檔
cd "$REPO_DIR" || exit

# 3. 執行 git pull (寫絕對路徑確保 crontab 抓得到指令)
# >> 代表 append 追加 log，2>&1 會將錯誤訊息一併紀錄
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting git pull..." >> "$LOG_PATH"
/usr/bin/git pull >> "$LOG_PATH" 2>&1