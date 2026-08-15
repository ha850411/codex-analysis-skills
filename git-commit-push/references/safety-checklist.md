# Git 提交與推送安全檢核清單

在執行 `git commit` 與 `git push` 前，落實以下安全與規範檢查，避免機密洩漏或無效提交。

---

## 🛡️ 提交流程檢核項目

### 1. 檔案過濾與未追蹤檔案檢查
- [ ] 執行 `git status -s` 檢視所有修改與新增檔案。
- [ ] 確保無任何敏感資訊檔案（如 `.env`, `.env.local`, `id_rsa`, `*.pem`, `*.key` 等）。
- [ ] 確保無不應追蹤的臨時目錄或構建產物（如 `dist/`, `build/`, `node_modules/`, `__pycache__/`, `.tmp/`）。
- [ ] 若發現非預期的未追蹤檔案，應先評估是否需加入 `.gitignore`。

### 2. 變更內容實質審查
- [ ] 執行 `git diff` 審查即將提交的程式碼內容與目的。
- [ ] 確認改動符合單一職責原則，避免混雜不相關的修改於同一次 commit 中。

### 3. 禁止多餘操作（No Extra Tasks）
- [ ] **嚴禁**主動執行非 Git 操作，例如單元測試（`npm test`、`phpunit`、`pytest`、`artisan test` 等）、語法檢查工具（Linter）、Docker 容器指令、依賴安裝或建置命令。
- [ ] 僅單純檢視改動內容、產製提交訊息、commit 與 push。

### 4. 提交訊息純中文驗證
- [ ] 標題是否遵循 `<類型>(<範圍>): <純中文摘要>` 格式？
- [ ] 標題與內文是否皆為**繁體中文**？
- [ ] 內文是否清晰列出主要變更點與原因？

---

## 🚀 推送遠端與衝突防護機制

### 1. 遠端分支檢查
- [ ] 確認推送的目的地分支是否正確（如 `origin/master`, `origin/main` 或特定 feature branch）。

### 2. 推送失敗與衝突處理
- 若推送時出現 `rejected (non-fast-forward)` 或 `fetch first` 錯誤：
  1. 先拉取遠端最新變更並進行 rebase：
     ```bash
     git pull --rebase origin <當前分支名稱>
     ```
  2. 若無衝突，rebase 完成後再次嘗試 `git push origin <當前分支名稱>`。
  3. 若發生衝突（Conflict）：
     - 透過 `git status` 標註衝突檔案。
     - 逐一解決衝突標記（`<<<<<<<`, `=======`, `>>>>>>>`）。
     - 解決完畢後執行 `git add <衝突檔案>` 與 `git rebase --continue`。
     - **嚴禁未經確認逕行使用 `git push --force` 覆寫遠端分支！**

---

## 📋 快速執行指令彙總

| 操作目的 | 建議指令 |
| :--- | :--- |
| **檢視狀態** | `git status` / `git status -s` |
| **檢視差異** | `git diff` / `git diff --stat` |
| **加入暫存** | `git add <檔案路徑>` 或 `git add -A` |
| **執行提交** | `git commit -m "<純中文標題>" -m "<純中文內文>"` |
| **確認分支** | `git branch --show-current` |
| **推送遠端** | `git push origin <分支名稱>` |
| **確認日誌** | `git log -1 --stat` |
