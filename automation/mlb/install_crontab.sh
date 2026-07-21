#!/bin/zsh
set -eu

readonly BEGIN_MARKER="# BEGIN CODEX MLB AUTOMATION"
readonly END_MARKER="# END CODEX MLB AUTOMATION"
readonly SCRIPT_DIR="${0:A:h}"
readonly REPO_ROOT="${SCRIPT_DIR:h:h}"
readonly LOG_DIR="${REPO_ROOT}/.automation-state/mlb/logs"

if ! command -v crontab >/dev/null 2>&1; then
  print -u2 "找不到 crontab。"
  exit 1
fi

PYTHON_BIN="$(command -v python3 || true)"
if [[ -z "${PYTHON_BIN}" ]]; then
  print -u2 "找不到 python3。"
  exit 1
fi
readonly PYTHON_BIN

mkdir -p "${LOG_DIR}"

current_file="$(mktemp -t codex-mlb-cron-current.XXXXXX)"
new_file="$(mktemp -t codex-mlb-cron-new.XXXXXX)"
cleanup() {
  rm -f "${current_file}" "${new_file}"
}
trap cleanup EXIT INT TERM

crontab -l >"${current_file}" 2>/dev/null || :

# 移除舊版受管區塊，保留使用者的其他 cron jobs。
awk -v begin="${BEGIN_MARKER}" -v end="${END_MARKER}" '
  $0 == begin { managed = 1; next }
  $0 == end { managed = 0; next }
  !managed { print }
' "${current_file}" >"${new_file}"

{
  print ""
  print -r -- "${BEGIN_MARKER}"
  print "SHELL=/bin/zsh"
  print "PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
  print "TZ=Asia/Taipei"
  print -r -- "0 21 * * * cd '${REPO_ROOT}' && '${PYTHON_BIN}' automation/mlb/predict_next_day.py >> '${LOG_DIR}/predict.log' 2>&1"
  print -r -- "0 15 * * * cd '${REPO_ROOT}' && '${PYTHON_BIN}' automation/mlb/review_today.py >> '${LOG_DIR}/review.log' 2>&1"
  print -r -- "${END_MARKER}"
} >>"${new_file}"

crontab "${new_file}"

print "MLB 排程已設定："
print "  每天 21:00：檢查隔日賽程，有比賽才執行預測"
print "  每天 15:00：有 24 小時內預測報告才執行復盤"
print "  Log：${LOG_DIR}"
print ""
print "可用 crontab -l 查看；Mac 必須在排程時間保持開機與喚醒。"
