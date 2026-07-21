# MLB scheduled automation

This directory contains two jobs intended for macOS `crontab`, interpreted in Asia/Taipei:

- `predict_next_day.py`: at 21:00, query the MLB schedule without Codex; only when the next TW calendar date has games, forecast all of them.
- `review_today.py`: at 15:00, run only when that date's prediction artifacts are no more than 24 hours old; score the immutable forecasts, apply only evidence-backed `mlb-analysis` changes, and open a GitHub PR when justified.

Runtime reports and logs live under `.automation-state/mlb/` and are intentionally ignored by Git. The postmortem edits an isolated worktree, so the user's current branch and uncommitted changes are not touched.

## Prerequisites

1. `codex login`
2. Add `GITHUB_PAT=github_pat_...` to the repo-root `.env` (recommended), or run `gh auth login -h github.com`. The token needs repository Contents write and Pull requests write access.
3. The Mac clock/timezone must be Asia/Taipei. The crontab also sets `TZ=Asia/Taipei`, but macOS cron scheduling follows the machine timezone.
4. The repository remote must be named `origin`. The base branch defaults to `master`; override with `MLB_GIT_BASE_BRANCH` in `.env` if needed.
5. Configure Notion and SMTP in `.env`. A verified prediction is published as one `daily-summary` Notion page, then an email containing the Notion URL is sent.

The loader reads only allowlisted automation, GitHub, and SMTP keys from `.env`. It never persists passwords or tokens to crontab, Git remotes, reports, or commits.

Required publication/notification settings:

```dotenv
NOTION_TOKEN=secret_xxx
NOTION_DATA_SOURCE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MLB_NOTIFICATION_EMAIL=you@example.com
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_SECURITY=starttls
SMTP_USERNAME=you@example.com
SMTP_PASSWORD=app-password
SMTP_FROM=you@example.com
```

Use `SMTP_SECURITY=ssl` with port 465 when required by the provider. Multiple recipients may be comma-separated. If Notion succeeds but email fails, rerunning the prediction job reuses the saved Notion URL and retries only email; it does not invoke Codex again.

Never put a real token in `.env.example`; it is tracked by Git. Keep the secret only in ignored `.env` and rotate it immediately if it has ever been committed or pushed.

## Validate and install

```bash
python3 automation/mlb/predict_next_day.py --date 2026-07-22 --dry-run
python3 automation/mlb/review_today.py --date 2026-07-22 --dry-run
automation/mlb/install_crontab.sh
```

The installer preserves all unrelated cron jobs and replaces only the block between `# BEGIN CODEX MLB AUTOMATION` and `# END CODEX MLB AUTOMATION`. It is safe to rerun after moving the repository or changing Python.

Verify the installed schedule:

```bash
crontab -l
```

Remove only the managed MLB jobs:

```bash
automation/mlb/uninstall_crontab.sh
```

Removal preserves unrelated cron jobs and existing reports/logs. The Mac must be powered on and awake at the scheduled time; traditional cron does not replay a missed run after wake.
