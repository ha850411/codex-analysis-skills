#!/usr/bin/env bash
# Codex Analysis Skills 管理腳本捷徑
# 用法:
#   ./manage-skills.sh         # 啟動終端機 Checkbox 互動選單 (TUI)
#   ./manage-skills.sh --web   # 啟動網頁瀏覽器管理介面 (Web UI)
#   ./manage-skills.sh --cli   # 啟動命令列 Checkbox 互動選單 (無 curses 相容模式)
#   ./manage-skills.sh --list  # 列出所有技能與掛載狀態
#   ./manage-skills.sh --help  # 查看所有參數說明

# 自動偵測並修正無效的 locale，避免 bash warning 與 Python curses / CJK 字符寬度編碼問題
if [ -z "$LC_ALL" ] || [ "$LC_ALL" = "en_US.UTF-8" ]; then
    if ! locale -a 2>/dev/null | grep -qi "^en_US\.utf"; then
        export LC_ALL=C.UTF-8 2>/dev/null || export LC_ALL=C.utf8 2>/dev/null || true
    fi
fi
export LANG=${LANG:-C.UTF-8}
export PYTHONIOENCODING=utf-8

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$DIR/manage_skills.py" "$@"
