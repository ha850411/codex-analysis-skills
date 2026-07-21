#!/bin/zsh
set -eu

readonly BEGIN_MARKER="# BEGIN CODEX ANALYSIS AUTOMATION"
readonly END_MARKER="# END CODEX ANALYSIS AUTOMATION"
readonly OLD_BEGIN_MARKER="# BEGIN CODEX MLB AUTOMATION"
readonly OLD_END_MARKER="# END CODEX MLB AUTOMATION"

command -v crontab >/dev/null 2>&1 || { print -u2 "找不到 crontab。"; exit 1; }
current_file="$(mktemp -t codex-analysis-cron-current.XXXXXX)"
new_file="$(mktemp -t codex-analysis-cron-new.XXXXXX)"
cleanup() { rm -f "${current_file}" "${new_file}"; }
trap cleanup EXIT INT TERM
if ! crontab -l >"${current_file}" 2>/dev/null; then
  print "目前沒有使用者 crontab，無需移除。"
  exit 0
fi

awk -v begin="${BEGIN_MARKER}" -v end="${END_MARKER}" -v old_begin="${OLD_BEGIN_MARKER}" -v old_end="${OLD_END_MARKER}" '
  $0 == begin || $0 == old_begin { managed = 1; found = 1; next }
  $0 == end || $0 == old_end { managed = 0; next }
  !managed { print }
  END { if (!found) exit 3 }
' "${current_file}" >"${new_file}" || status=$?
if [[ "${status:-0}" -eq 3 ]]; then
  print "找不到受管排程，無需移除。"
  exit 0
fi
crontab "${new_file}"
print "自動化排程已移除；其他 cron jobs、報告與 log 均保留。"
