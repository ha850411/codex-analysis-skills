#!/bin/zsh
set -eu

readonly BEGIN_MARKER="# BEGIN CODEX MLB AUTOMATION"
readonly END_MARKER="# END CODEX MLB AUTOMATION"

if ! command -v crontab >/dev/null 2>&1; then
  print -u2 "找不到 crontab。"
  exit 1
fi

current_file="$(mktemp -t codex-mlb-cron-current.XXXXXX)"
new_file="$(mktemp -t codex-mlb-cron-new.XXXXXX)"
cleanup() {
  rm -f "${current_file}" "${new_file}"
}
trap cleanup EXIT INT TERM

if ! crontab -l >"${current_file}" 2>/dev/null; then
  print "目前沒有使用者 crontab，無需移除。"
  exit 0
fi

if ! grep -Fqx "${BEGIN_MARKER}" "${current_file}"; then
  print "找不到 MLB 受管排程，無需移除。"
  exit 0
fi

awk -v begin="${BEGIN_MARKER}" -v end="${END_MARKER}" '
  $0 == begin { managed = 1; next }
  $0 == end { managed = 0; next }
  !managed { print }
' "${current_file}" >"${new_file}"

crontab "${new_file}"

print "MLB 排程已移除；其他 cron jobs 與既有報告／log 均已保留。"
