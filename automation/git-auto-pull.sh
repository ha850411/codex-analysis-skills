#!/bin/bash

# 設定排程
# * * * * * /bin/bash /home/ec2-user/.agents/skills/automation/git-auto-pull.sh >> /home/ec2-user/.agents/skills/.automation-state/logs/cron_pull.log 2>&1

HOME="/home/ec2-user"
REPO_DIR="$HOME/.agents/skills"
LOG_PATH="$REPO_DIR/.automation-state/logs/cron_pull.log"

# 限制 log 最大為 1MB (1024 KB)
MAX_SIZE=1024

if [ -f "$LOG_PATH" ]; then
    # 取得檔案大小 (KB)
    FILE_SIZE=$(du -k "$LOG_PATH" | cut -f1)
    if [ "$FILE_SIZE" -ge "$MAX_SIZE" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Log file exceeded ${MAX_SIZE}KB, truncating..." > "$LOG_PATH"
    fi
fi

cd "$REPO_DIR" || exit

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Starting git pull..." >> "$LOG_PATH"
/usr/bin/git pull >> "$LOG_PATH" 2>&1