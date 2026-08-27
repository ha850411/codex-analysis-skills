---
name: git-commit-push
description: "自動化檢查 Git 變更狀態、產製 Conventional Commits 標準語意化（標準英文前綴＋純繁體中文說明）Commit 訊息並安全提交與推送至遠端儲存庫。專注於 Git 本身操作，不執行額外測試或建置。"
---

# Git 語意化提交與推送技能（Git Commit & Push Skill）

本技能用於標準化 Git 提交流程，快速檢視當前工作區改動、遵循 Conventional Commits 標準產製清晰之語意化提交訊息（Commit Message），並安全推送至遠端儲存庫。

**核心規則：**
1. **嚴格目標目錄鎖定（最優先）**：
   - 若使用者有傳入或指定目標路徑（例如 `/git-commit-push /path/to/dir` 或 Prompt 中指定路徑），**必須以該路徑為唯一操作目標**。
   - **所有 Git 指令必須明確加上 `-C <target_dir>`**（例如 `git -C <target_dir> status`、`git -C <target_dir> diff`、`git -C <target_dir> commit`），或將工具執行工作目錄嚴格鎖定在該目標路徑。
   - **嚴格禁止**在未指定 `-C` 的情況下執行全域 git 指令，**嚴格禁止**切換或操作任何其他未指定的目錄。
2. **全中文指引**：本技能內部所有說明、流程指引與輸出回饋一律使用繁體中文。
3. **專注純粹 Git 操作，絕不做多餘動作**：
   - 僅執行 Git 本身的必要流程（`git -C <target_dir> status`、`diff`、`add`、`commit`、`push`）。
   - **嚴禁**主動執行單元測試或整合測試（如 `phpunit`、`artisan test`、`npm test`、`pytest` 等）。
   - **嚴禁**執行語法檢查（Linter）、程式碼格式化工具、Docker 容器指令、依賴安裝（composer / npm install）或專案建置指令。
   - 使用者下達 commit 指令時，只要檢視改了什麼程式碼並直接進行 commit 與 push。
4. **Conventional Commits 語意化標準**：
   - **類型前綴 (Type)**：一律採用標準 ASCII 英文小寫關鍵字（如 `feat`、`fix`、`docs`、`refactor`、`perf`、`test`、`chore` 等），以確保與 Commitlint、Semantic Release、Changelog 生成器等自動化工具鏈 100% 相容。
   - **範圍 (Scope)**：以英文或小寫模組名稱標註影響範疇，如 `feat(git-commit-push)`、`fix(auth)`。
   - **摘要與內文 (Summary & Body)**：**一律使用繁體中文**精準撰寫變更意圖與細點（除程式碼識別碼、檔名、函數名等專有名詞外，所有動詞與語意描述皆須為中文）。
5. **安全防護**：
   - 提交前僅需快速過濾暫存清單中是否有敏感資訊（如 `.env`、金鑰憑證）與暫存垃圾檔案。
   - 推送時遵守非破壞原則，嚴禁未經確認使用 `--force`。

---

## 📋 標準執行流程

```
[1. 檢查變更 (git status & diff)] ──> [2. 產製語意化 Commit 訊息] ──> [3. 暫存與提交 (git add & commit)] ──> [4. 推送遠端 (git push)]
```

### 步驟一：檢查工作區變更 (Git Status & Diff)
1. 執行 `git -C <target_dir> status` 與 `git -C <target_dir> diff --stat`，掌握修改（Modified）、新增（Untracked）、刪除（Deleted）與已暫存（Staged）之檔案清單。
2. 檢視變更內容細節（`git -C <target_dir> diff`），理解本次變更的核心內容與目的。
3. 確認無敏感資訊（如 `.env`、金鑰等）。若有未追蹤的臨時檔案，提醒或加入 `.gitignore`。

### 步驟二：產製標準語意化 Commit 訊息
1. 根據實際變更內容，遵循 Conventional Commits 規範產製語意化 Commit 訊息。
2. **格式標準**：
   ```text
   <type>(<scope>): <純中文簡短摘要>

   - <模組或檔案1>: <純中文詳細變更說明與原因>
   - <模組或檔案2>: <純中文詳細變更說明與原因>
   - <補充說明/影響評估>（選填）
   ```
3. **標準類型前綴對照**：
   - `feat`: 新增功能、新模組 (Feature)
   - `fix`: 修復缺陷、錯誤或例外狀況 (Bug fix)
   - `refactor`: 程式碼重構（不改變對外行為的代碼整理）
   - `docs`: 新增或修改說明文件、註解、README (Documentation)
   - `test`: 新增、修改或補充測試案例 (Testing)
   - `chore`: 建置流程、設定檔、依賴或工具鏈變更 (Maintenance/Tooling)
   - `style`: 排版、格式、空格等不影響程式碼邏輯之調整
   - `perf`: 效能最佳化、減少耗時或資源佔用 (Performance)
   - `ci` / `build`: CI/CD 流程、建置腳本或外部依賴設定

4. **規範限制**：
   - 標題句末不加句號。
   - 類型必須為標準英文小寫前綴，摘要與內文一律以繁體中文撰寫。

### 步驟三：暫存與安全提交 (Stage & Commit)
1. 依據變更範圍將檔案加入暫存區（`git -C <target_dir> add <檔案路徑>` 或 `git -C <target_dir> add -A`）。
2. 執行提交：
   ```bash
   git -C <target_dir> commit -m "<純中文標題>

   <純中文內文說明>"
   ```

### 步驟四：確認分支與推送遠端 (Push & Verify)
1. 確認當前所在分支：`git -C <target_dir> branch --show-current`。
2. 推送變更至遠端分支：
   ```bash
   git -C <target_dir> push origin <當前分支名稱>
   ```
   *若為首次推送新分支，使用 `git -C <target_dir> push -u origin <當前分支名稱>` 建立追蹤。*
3. 驗證最終狀態：
   - 執行 `git -C <target_dir> log -1` 確認最新提交記錄。
   - 執行 `git -C <target_dir> status` 確認工作目錄已乾淨（`working tree clean`）且與遠端同步。

---

## ⚠️ 例外狀況與防呆機制

1. **工作區無任何變更**：
   - 若 `git -C <target_dir> status` 顯示無變更，直接告知使用者「目前工作目錄乾淨，無任何變更需要提交」，不執行無效 commit。
2. **遠端有衝突或領先提交**：
   - 若 push 被拒絕（non-fast-forward），先執行 `git -C <target_dir> pull --rebase origin <分支名稱>`，若發生衝突則清晰列出衝突檔案並引導使用者解決，嚴禁未經確認使用 `--force`。
3. **未設定 Git User Name / Email**：
   - 若尚未設定本機 Git 身分，提示設定 `git -C <target_dir> config user.name` 與 `git -C <target_dir> config user.email`。
