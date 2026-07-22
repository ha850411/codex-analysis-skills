#!/bin/zsh
set -eu

readonly BEGIN_MARKER="# BEGIN CODEX ANALYSIS AUTOMATION"
readonly END_MARKER="# END CODEX ANALYSIS AUTOMATION"
readonly OLD_BEGIN_MARKER="# BEGIN CODEX MLB AUTOMATION"
readonly OLD_END_MARKER="# END CODEX MLB AUTOMATION"
readonly SCRIPT_DIR="${0:A:h}"
readonly REPO_ROOT="${SCRIPT_DIR:h}"
readonly LOG_DIR="${REPO_ROOT}/.automation-state/logs"

command -v crontab >/dev/null 2>&1 || { print -u2 "找不到 crontab。"; exit 1; }
PYTHON_BIN="$(command -v python3 || true)"
[[ -n "${PYTHON_BIN}" ]] || { print -u2 "找不到 python3。"; exit 1; }
readonly PYTHON_BIN
CODEX_BIN="$(command -v codex || true)"
[[ -n "${CODEX_BIN}" ]] || { print -u2 "找不到 codex。"; exit 1; }
readonly CODEX_BIN
mkdir -p "${LOG_DIR}"

current_file="$(mktemp -t codex-analysis-cron-current.XXXXXX)"
new_file="$(mktemp -t codex-analysis-cron-new.XXXXXX)"
cleanup() { rm -f "${current_file}" "${new_file}"; }
trap cleanup EXIT INT TERM
crontab -l >"${current_file}" 2>/dev/null || :

awk -v begin="${BEGIN_MARKER}" -v end="${END_MARKER}" -v old_begin="${OLD_BEGIN_MARKER}" -v old_end="${OLD_END_MARKER}" '
  $0 == begin || $0 == old_begin { managed = 1; next }
  $0 == end || $0 == old_end { managed = 0; next }
  !managed { print }
' "${current_file}" >"${new_file}"

{
  print ""
  print -r -- "${BEGIN_MARKER}"
  print "SHELL=/bin/zsh"
  print "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
  print "TZ=Asia/Taipei"
  print -r -- "0 21 * * * cd '${REPO_ROOT}' && CODEX_BIN='${CODEX_BIN}' '${PYTHON_BIN}' automation/run_scheduled.py prediction --module mlb >> '${LOG_DIR}/mlb-prediction.log' 2>&1"
  print -r -- "30 20 * * * cd '${REPO_ROOT}' && CODEX_BIN='${CODEX_BIN}' '${PYTHON_BIN}' automation/run_scheduled.py review --module mlb >> '${LOG_DIR}/mlb-review.log' 2>&1"
  print -r -- "0 9 * * * cd '${REPO_ROOT}' && CODEX_BIN='${CODEX_BIN}' '${PYTHON_BIN}' automation/run_scheduled.py prediction --module lol >> '${LOG_DIR}/lol-prediction.log' 2>&1"
  print -r -- "30 8 * * * cd '${REPO_ROOT}' && CODEX_BIN='${CODEX_BIN}' '${PYTHON_BIN}' automation/run_scheduled.py review --module lol >> '${LOG_DIR}/lol-review.log' 2>&1"
  print -r -- "${END_MARKER}"
} >>"${new_file}"

crontab "${new_file}"
print "自動化排程已設定：MLB 每天 21:00 預測、20:30 檢討前一日報告；LoL 每天 09:00 預測、08:30 檢討前一日報告。"
print "模組開關：${SCRIPT_DIR}/modules.json"
print "Log：${LOG_DIR}"
print "可用 crontab -l 查看；Mac 必須保持開機與喚醒。"
