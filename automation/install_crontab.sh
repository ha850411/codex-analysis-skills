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
  "${PYTHON_BIN}" "${SCRIPT_DIR}/render_crontab.py" \
    --repo-root "${REPO_ROOT}" \
    --python-bin "${PYTHON_BIN}" \
    --codex-bin "${CODEX_BIN}" \
    --log-dir "${LOG_DIR}"
  print -r -- "${END_MARKER}"
} >>"${new_file}"

crontab "${new_file}"
print "自動化排程已依 modules.json 設定。"
print "模組、模型與排程時間：${SCRIPT_DIR}/modules.json"
print "Log：${LOG_DIR}"
print "可用 crontab -l 查看；Mac 必須保持開機與喚醒。"
