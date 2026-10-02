---
name: git-commit-push
description: "Inspect Git changes, generate Conventional Commits with standard English prefixes and purely Traditional Chinese descriptions, then safely commit and push to the remote. Use for Git 「提交」「推送」 requests. Perform Git operations only; do not run extra tests or builds."
---

# Git Commit & Push

Respond in Traditional Chinese (Taiwan). Standardize Git commits: quickly inspect workspace changes, write clear Conventional Commits messages, and safely push to the remote.

**Core rules:**
1. **Strict target-directory lock (highest priority):**
   - If the user supplies a target path, e.g. `/git-commit-push /path/to/dir` or a path in the prompt, **operate only on that path**.
   - Without a user-specified path, **inspect only the active workspace or current working directory (CWD)**.
   - **Never search across directories or guess:** if the current directory/workspace is not a Git repository, do not scan `~/workspace/*` or infer another project from modification times. Immediately report the error and request an explicit path.
   - **Every Git command must specify `-C <target_dir>`**, e.g. `git -C <target_dir> status`, `git -C <target_dir> diff`, `git -C <target_dir> commit`, or run with the tool's working directory strictly locked to that target.
   - **Never** run global Git commands without `-C`, or switch to or operate on any other unspecified directory.
2. **Two-round batching (at most two tool-call rounds for the standard workflow):**
   - **Do not** split status, diff, staging, commit, branch lookup, push and verification into separate tool-call rounds. Repeated model round trips add unnecessary latency.
   - **Strictly follow the two-round workflow:**
     - **Round 1 (inspect):** collect the branch, status and diffs in one compound command.
     - **Round 2 (commit and push):** after writing the Conventional Commits message, stage, commit, push and confirm the commit log in one compound command.
     - After success, report the result in Traditional Chinese directly from that output. **Do not** make another tool call for an extra `git status` check.
3. **Traditional Chinese responses:** write all user-facing explanations, workflow guidance and feedback in Traditional Chinese. The skill's internal instructions are written in English.
4. **Git operations only; no extra work:**
   - Perform only necessary Git steps (`git -C <target_dir> status`, `diff`, `add`, `commit`, `push`).
   - **Do not** proactively run unit or integration tests, such as `phpunit`, `artisan test`, `npm test` or `pytest`.
   - **Do not** run linters, formatters, Docker commands, dependency installation (composer / npm install), or project builds.
   - For a commit request, inspect the code changes, then proceed directly to commit and push.
5. **Conventional Commits:**
   - **Type:** use standard lowercase ASCII English keywords (`feat`, `fix`, `docs`, `refactor`, `perf`, `test`, `chore`, etc.) for full compatibility with Commitlint, Semantic Release and changelog generators.
   - **Scope:** use English or a lowercase module name, e.g. `feat(git-commit-push)`, `fix(auth)`.
   - **Summary and body:** describe intent and details precisely in **Traditional Chinese**. Except for code identifiers, filenames, function names and similar proper terms, all verbs and semantic descriptions must be Chinese.
6. **Safeguards:**
   - Before committing, quickly screen the staged list for sensitive information, such as `.env`, keys/certificates, and temporary junk files.
   - Push non-destructively; never use `--force` without confirmation.

---

## Standard workflow (two rounds)

```
[Round 1: Inspect branch, status and diffs] -> [Write Conventional Commits message] -> [Round 2: Stage, commit, push and verify] -> [Report in Traditional Chinese]
```

### Round 1: Inspect branch, status and diffs in one command

Run the following compound command without splitting it into multiple tool calls:

```bash
git -C <target_dir> branch --show-current && git -C <target_dir> status -s && git -C <target_dir> diff && git -C <target_dir> diff --cached
```

1. If `git -C <target_dir> status -s` is empty, the workspace is clean. Say 「目前工作目錄乾淨，無任何變更需要提交」 and stop after this first round.
2. If untracked sensitive files such as `.env` or certificates are present, stop and notify the user.
3. Identify the current branch and the substance and purpose of the changes from the output.

---

### Round 2: Write the message, then stage, commit, push and verify in one command

1. Write a Conventional Commits message based on the actual changes:
   ```text
   <type>(<scope>): <純中文簡短摘要>

   - <模組或檔案1>: <純中文詳細變更說明與原因>
   - <模組或檔案2>: <純中文詳細變更說明與原因>
   ```

   **Standard types:**
   - `feat`: New feature or module.
   - `fix`: Fix a defect, error or exception.
   - `refactor`: Restructure code without changing external behavior.
   - `docs`: Add or update documentation, comments or README.
   - `test`: Add, modify or supplement tests.
   - `chore`: Change build processes, configuration, dependencies or tooling.
   - `style`: Layout, formatting or whitespace changes without logic changes.
   - `perf`: Improve performance, runtime or resource use.
   - `ci` / `build`: CI/CD workflows, build scripts or external dependency settings.

   **Constraints:**
   - Do not end the subject with a period.
   - Use a standard lowercase English type; write the summary and body in Traditional Chinese.

2. **Stage, commit, push and confirm the log in one compound command; do not split these actions into separate tool calls:**
   ```bash
   git -C <target_dir> add -A && git -C <target_dir> commit -m "<純中文標題>

   <純中文內文說明>" && (git -C <target_dir> push origin <當前分支名稱> || git -C <target_dir> push -u origin <當前分支名稱>) && git -C <target_dir> log -1 --stat
   ```

3. **Report completion:** use the command output to give a Traditional Chinese success summary with the branch, commit ID, change summary and a PR creation hint. **Do not** make an additional tool call to run `git status`.

---

## Exceptions and safeguards

1. **No workspace changes:**
   - If `git -C <target_dir> status -s` is empty, say 「目前工作目錄乾淨，無任何變更需要提交」 during round 1; do not create a pointless commit.
2. **Remote has newer commits (local branch is behind origin):**
   - If push is rejected with `non-fast-forward` or `fetch first`:
     1. **Automatically try rebasing:** in the next tool-call round, run `git -C <target_dir> pull --rebase origin <分支名稱> && git -C <target_dir> push origin <分支名稱>`.
     2. **No conflicts:** replay the local commits on top of the latest remote commits, push and report completion.
     3. **Conflicts:** never use `--force` or `rebase --skip` without confirmation. Stop automatic operations, clearly list the conflicting files and guide the user through resolution.
3. **Missing Git user name/email:**
   - If local Git identity is unset, prompt to configure `git -C <target_dir> config user.name` and `git -C <target_dir> config user.email`.
