---
name: git-commit-push
description: "自動化檢查 Git 變更狀態、產製 Conventional Commits 標準語意化（標準英文前綴＋純繁體中文說明）Commit 訊息並安全提交與推送至遠端儲存庫。專注於 Git 本身操作，不執行額外測試或建置。"
---

# Git 語意化提交與推送技能（Git Commit & Push Skill）

本技能用於標準化 Git 提交流程，快速檢視當前工作區改動、遵循 Conventional Commits 標準產製清晰之語意化提交訊息（Commit Message），並安全推送至遠端儲存庫。

**核心規則：**
1. **嚴格目標目錄鎖定（最優先）**：
   - 若使用者有傳入或指定目標路徑（例如 `/git-commit-push /path/to/dir` 或 Prompt 中指定路徑），**必須以該路徑為唯一操作目標**。
   - 若使用者未指定目標路徑，**僅允許檢查系統所屬之當前工作區（Active Workspace）或當前工作目錄（CWD）**。
   - **嚴格禁止跨目錄搜尋與猜測**：若當前目錄或工作區並非 Git 儲存庫，**嚴禁**主動掃描 `~/workspace/*` 或依據檔案修改時間（Timestamp）猜測其他專案，必須立即回報錯誤並請使用者提供明確路徑。
   - **所有 Git 指令必須明確加上 `-C <target_dir>`**（例如 `git -C <target_dir> status`、`git -C <target_dir> diff`、`git -C <target_dir> commit`），或將工具執行工作目錄嚴格鎖定在該目標路徑。
   - **嚴格禁止**在未指定 `-C` 的情況下執行全域 git 指令，**嚴格禁止**切換或操作任何其他未指定的目錄。
2. **極速兩階段批次執行（嚴格限制最多 2 輪 Tool Calls，最關鍵效能規則）**：
   - **嚴禁**拆成多輪零散指令（如：第一輪 status ➔ 第二輪 diff ➔ 第三輪 add ➔ 第四輪 commit ➔ 第五輪 branch ➔ 第六輪 push ➔ 第七輪 log ➔ 第八輪 status）。這種做法會觸發 8 次雲端 LLM 往返，累積高達 30~50 秒延遲！
   - **必須嚴格遵守「兩輪批次」原則**：
     - **第 1 輪（資訊收集）**：以單一複合指令一次性取回分支、狀態與 diff。
     - **第 2 輪（提交與推送）**：AI 產製 Conventional Commit 訊息後，以單一複合指令一次性完成暫存、提交、推送與紀錄確認。
     - 執行成功後直接輸出繁中總結，**嚴禁**再浪費一輪去執行額外的 `git status` 驗證。
3. **全中文指引**：本技能內部所有說明、流程指引與輸出回饋一律使用繁體中文。
4. **專注純粹 Git 操作，絕不做多餘動作**：
   - 僅執行 Git 本身的必要流程（`status`、`diff`、`add`、`commit`、`push`）。
   - **嚴禁**主動執行單元測試或整合測試（如 `phpunit`、`artisan test`、`npm test`、`pytest` 等）。
   - **嚴禁**執行語法檢查（Linter）、程式碼格式化工具、Docker 容器指令、依賴安裝（composer / npm install）或專案建置指令。
   - 使用者下達 commit 指令時，只要檢視改了什麼程式碼並直接進行 commit 與 push。
5. **Conventional Commits 語意化標準**：
   - **類型前綴 (Type)**：一律採用標準 ASCII 英文小寫關鍵字（如 `feat`、`fix`、`docs`、`refactor`、`perf`、`test`、`chore` 等），以確保與 Commitlint、Semantic Release、Changelog 生成器等自動化工具鏈 100% 相容。
   - **範圍 (Scope)**：以英文或小寫模組名稱標註影響範疇，如 `feat(git-commit-push)`、`fix(auth)`。
   - **摘要與內文 (Summary & Body)**：**一律使用繁體中文**精準撰寫變更意圖與細點（除程式碼識別碼、檔名、函數名等專有名詞外，所有動詞與語意描述皆須為中文）。
6. **安全防護**：
   - 提交前僅需快速過濾暫存清單中是否有敏感資訊（如 `.env`、金鑰憑證）與暫存垃圾檔案。
   - 推送時遵守非破壞原則，嚴禁未經確認使用 `--force`。

---

## 📋 極速標準執行流程（嚴格 2 輪）

```
[第 1 輪：複合指令收集變更與分支] ──> [AI 產製語意化 Commit 訊息] ──> [第 2 輪：複合指令暫存、提交、推送並驗證] ──> [輸出繁中總結]
```

### ⚡ 第 1 輪：一次性獲取狀態、分支與 Diff（單一指令）

立即執行以下複合指令（嚴禁拆解成多次 tool call）：
```bash
git -C <target_dir> branch --show-current && git -C <target_dir> status -s && git -C <target_dir> diff && git -C <target_dir> diff --cached
```

- **檢查邏輯**：
  1. 若 `git status -s` 為空，表示**工作區完全乾淨無任何變更**，直接回報使用者「目前工作目錄乾淨，無任何變更需要提交」，**流程立即結束**（僅耗時 1 輪）。
  2. 若有未追蹤的敏感檔案（如 `.env`、憑證），立即中止並提示使用者。
  3. 從輸出中確認**當前分支名稱**與**具體變更內容（Diff）**。

---

### ⚡ 第 2 輪：產製語意化 Commit 訊息並一次性提交推送（單一指令）

1. 根據變更內容，遵循 Conventional Commits 規範產製語意化 Commit 訊息：
   ```text
   <type>(<scope>): <純中文簡短摘要>

   - <模組或檔案1>: <純中文詳細變更說明與原因>
   - <模組或檔案2>: <純中文詳細變更說明與原因>
   ```

   **標準類型前綴對照**：
   - `feat`: 新增功能、新模組 (Feature)
   - `fix`: 修復缺陷、錯誤或例外狀況 (Bug fix)
   - `refactor`: 程式碼重構（不改變對外行為的代碼整理）
   - `docs`: 新增或修改說明文件、註解、README (Documentation)
   - `test`: 新增、修改或補充測試案例 (Testing)
   - `chore`: 建置流程、設定檔、依賴或工具鏈變更 (Maintenance/Tooling)
   - `style`: 排版、格式、空格等不影響程式碼邏輯之調整
   - `perf`: 效能最佳化、減少耗時或資源佔用 (Performance)
   - `ci` / `build`: CI/CD 流程、建置腳本或外部依賴設定

2. **立即以單一複合指令完成暫存、提交、推送與紀錄確認**（將所有動作串聯，嚴禁分開執行）：
   ```bash
   git -C <target_dir> add -A && git -C <target_dir> commit -m "<純中文標題>

   <純中文內文說明>" && (git -C <target_dir> push origin <當前分支名稱> || git -C <target_dir> push -u origin <當前分支名稱>) && git -C <target_dir> log -1 --stat
   ```

3. **完成回報**：
   指令執行完成後，直接根據指令輸出回傳繁體中文成功摘要（包含分支、Commit ID、變更摘要與 PR 建立提示），**嚴格禁止**再次調用工具去跑 `git status`。

---

## ⚠️ 例外狀況與防呆機制

1. **工作區無任何變更**：
   - 若 `git status -s` 為空，第 1 輪直接告知使用者「目前工作目錄乾淨，無任何變更需要提交」，不執行無效 commit。
2. **遠端有領先提交（本地版本落後於 origin）**：
   - 若 push 被拒絕（`non-fast-forward` 或提示 `fetch first`）：
     1. **自動嘗試變基整合**：在下一輪執行 `git -C <target_dir> pull --rebase origin <分支名稱> && git -C <target_dir> push origin <分支名稱>`。
     2. **情境 A（無衝突）**：自動將本機 commit 墊在遠端最新 commit 之上並推送成功，輸出完成摘要。
     3. **情境 B（有代碼衝突 Conflict）**：**嚴格禁止**未經確認使用 `--force` 或 `rebase --skip`。必須立即中止自動操作，清晰列出發生衝突的檔案清單，並引導使用者檢視與解決衝突。
3. **未設定 Git User Name / Email**：
   - 若尚未設定本機 Git 身分，提示設定 `git -C <target_dir> config user.name` 與 `git -C <target_dir> config user.email`。
