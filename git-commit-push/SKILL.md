---
name: git-commit-push
description: "自動化檢查 Git 狀態、產製高質量純中文 Commit 訊息並推送至遠端儲存庫。用於 Git 變更檢查、純中文提交訊息撰寫、暫存、安全提交與推送程式碼；不要用於非 Git 專案或未經確認的破壞性覆寫操作。預設繁體中文。"
---

# Git 純中文提交與推送技能（Git Commit & Push Skill）

本技能用於標準化 Git 提交流程，確保所有 Git 狀態檢查、品質驗證、提交訊息（Commit Message）產製及遠端推送（Push）均符合嚴格的安全規範與高語意化標準。

**核心規則：**
1. **全中文規範**：本技能內部所有說明、流程指引與輸出內容一律使用繁體中文。
2. **純中文 Commit 訊息**：所有產生的 Git Commit 標題與內文**一律只能使用繁體中文**（除程式碼識別碼、檔名、函數名等專有名詞外，所有動詞與語意描述皆須為中文）。
3. **安全第一**：提交前必須嚴格排查敏感資訊（`.env`、金鑰、憑證）、暫存垃圾檔案與未通過之測試。

---

## 📋 標準執行流程

```
[1. 檢查狀態] ──> [2. 安全與測試驗證] ──> [3. 產製純中文 Commit 訊息] ──> [4. 暫存與提交] ──> [5. 推送遠端與驗證]
```

### 步驟一：檢查工作區狀態 (Git Status)
1. 執行 `git status` 與 `git diff --stat`，掌握所有修改檔案（Modified）、新增檔案（Untracked）、刪除檔案（Deleted）與已暫存檔案（Staged）。
2. 若有未追蹤檔案，確認是否屬於專案正式檔案；若是臨時檔案、快取或本機設定檔，先協助加入 `.gitignore`。
3. 檢視變更內容細節（`git diff`），理解本次變更的核心目的與影響範圍。

### 步驟二：安全與品質驗證 (Pre-commit Verification)
1. **敏感資訊過濾**：確認沒有包含金鑰、密碼、Token 或未被忽略的 `.env` 檔案。
2. **測試與語法檢查**：若專案中包含測試套件（如 `npm test`、`python3 -m unittest` 等）或語法檢查工具，應在提交前執行並確認全數通過。
3. 參考 [`references/safety-checklist.md`](file:///home/ec2-user/.agents/skills/git-commit-push/references/safety-checklist.md) 進行完整安全檢核。

### 步驟三：產製純中文結構化 Commit 訊息
1. 根據變更內容與目的，遵循 [`references/commit-conventions.md`](file:///home/ec2-user/.agents/skills/git-commit-push/references/commit-conventions.md) 規範產製純中文 Commit 訊息。
2. **格式標準**：
   ```text
   <類型>(<範圍>): <純中文簡短摘要>

   - <模組或檔案1>: <純中文詳細變更說明與原因>
   - <模組或檔案2>: <純中文詳細變更說明與原因>
   - <補充說明/影響評估>（選填）
   ```
3. **中文類型前綴對照**：
   - `功能(feat)` 或 `【功能】`：新增功能、新模組、新技能
   - `修復(fix)` 或 `【修復】`：修復缺陷、錯誤或例外狀況
   - `重構(refactor)` 或 `【重構】`：程式碼重構（不改變對外行為）
   - `文件(docs)` 或 `【文件】`：新增或修改說明文件、註解
   - `測試(test)` 或 `【測試】`：新增、修改或補充測試案例
   - `維護(chore)` 或 `【維護】`：建置流程、設定檔、依賴或工具鏈變更
   - `樣式(style)` 或 `【樣式】`：排版、格式、空格等不影響程式碼邏輯之調整
   - `效能(perf)` 或 `【效能】`：效能最佳化、減少耗時或資源佔用

4. **規範限制**：
   - 標題句末不加句號。
   - 標題與內文一律以繁體中文撰寫，嚴禁使用英文撰寫說明。

### 步驟四：暫存與安全提交 (Stage & Commit)
1. 依據變更範圍將檔案加入暫存區（`git add <檔案路徑>` 或 `git add -A`）。
2. 再次確認 `git status` 確認暫存清單正確無誤。
3. 執行提交：
   ```bash
   git commit -m "<純中文標題>

   <純中文內文說明>"
   ```

### 步驟五：確認分支與推送遠端 (Push & Verify)
1. 確認當前所在分支：`git branch --show-current`。
2. 檢查遠端設定：`git remote -v`。
3. 推送變更至遠端分支：
   ```bash
   git push origin <當前分支名稱>
   ```
   *若為首次推送新分支，使用 `git push -u origin <當前分支名稱>` 建立追蹤。*
4. 驗證最終狀態：
   - 執行 `git log -1` 確認最新提交記錄與訊息。
   - 執行 `git status` 確認工作目錄已乾淨（`working tree clean`）且與遠端同步。

---

## ⚠️ 例外狀況與防呆機制

1. **工作區無任何變更**：
   - 若 `git status` 顯示無變更，直接告知使用者「目前工作目錄乾淨，無任何變更需要提交」，不執行無效 commit。
2. **遠端有衝突或領先提交**：
   - 若 push 被拒絕（non-fast-forward），先執行 `git pull --rebase origin <分支名稱>`，若發生衝突則清晰列出衝突檔案並引導使用者解決，嚴禁未經確認使用 `--force`。
3. **未設定 Git User Name / Email**：
   - 若尚未設定本機 Git 身分，提示設定 `git config user.name` 與 `git config user.email`。
