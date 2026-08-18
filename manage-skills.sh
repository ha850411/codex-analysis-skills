#!/usr/bin/env bash
# Codex Analysis Skills 管理腳本捷徑
# 用法:
#   ./manage-skills.sh         # 啟動終端機 Checkbox 互動選單 (TUI)
#   ./manage-skills.sh --web   # 啟動網頁瀏覽器管理介面 (Web UI)
#   ./manage-skills.sh --list  # 列出所有技能與掛載狀態
#   ./manage-skills.sh --help  # 查看所有參數說明

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$DIR/manage_skills.py" "$@"
