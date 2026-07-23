# Codex Analysis Skills

AI 驅動的體育賽事與電競分析技能集（Sports & Esports Analytics Skills Repository）。提供專業賽事數據分析、預測模型、雙模型紅隊審查機制、自動化排程與 Notion 報告發布整合。

## 📌 專案目錄結構

```text
.agents/skills/
├── mlb-analysis/          # MLB 美國職棒分析模組
├── nba-analysis/          # NBA 美國職籃分析模組
├── soccer-analysis/       # FIFA 世界盃與國際足球賽事分析模組
├── lol-analysis/          # LoL 英雄聯盟電競賽事分析模組
├── cs-analysis/           # CS2 / CS:GO 電競賽事分析模組
├── dota2-analysis/        # Dota 2 電競賽事分析模組
├── valorant-analysis/     # Valorant 特戰英豪電競賽事分析模組
├── prediction-pipeline/   # 可稽核預測管線 (支援 agy 紅隊複核與雙模型審查)
├── automation/            # 自動化定時分析與報告郵件/Crontab 觸發器
└── shared/                # 共用分析架構、機率校驗與 Notion 匯出工具
    ├── notion/            # Notion 賽事報告自動發布工具
    ├── evals/             # 預測歷史精準度與期望值評估系統
    ├── analysis-core.md   # 核心分析流程規範
    ├── prediction-methodology.md # 預測與價值盤算演算法說明
    └── validate_probabilities.mjs # 機率合法性驗證工具
```

---

## 🚀 核心功能與分析模組

### 1. 體育賽事分析 (Sports Analytics)
- ⚾ **[mlb-analysis](file:///Users/eason.lee/.agents/skills/mlb-analysis/SKILL.md)**: 涵蓋 MLB 先發投手、對戰數據、牛棚負擔、打線狀態、球場因子與天氣，進行前五局、獨贏、讓分與大小分分析。
- 🏀 **[nba-analysis](file:///Users/eason.lee/.agents/skills/nba-analysis/SKILL.md)**: 評估 NBA 輪替陣容、傷兵名單、對戰節奏、攻防效率、半場/首節與球員個人盤口。
- ⚽ **[soccer-analysis](file:///Users/eason.lee/.agents/skills/soccer-analysis/SKILL.md)**: 專注於 FIFA 世界盃決賽圈與國際頂級賽事，分析預期進球 (xG)、陣容傷停、90分鐘結算與晉級盤口。

### 2. 電競賽事分析 (Esports Analytics)
- ⚔️ **[lol-analysis](file:///Users/eason.lee/.agents/skills/lol-analysis/SKILL.md)**: 支援 LCK、LPL、LEC、LCS 及國際賽事，結合 Ban/Pick 陣容分析、版本適應力與中後期決策能力。
- 🎯 **[cs-analysis](file:///Users/eason.lee/.agents/skills/cs-analysis/SKILL.md)**: 針對 CS2 電競賽事分析地圖池 (Map Pool)、Veto 策略、槍位對戰與 BO3/BO5 賽制推演。
- 🛡️ **[dota2-analysis](file:///Users/eason.lee/.agents/skills/dota2-analysis/SKILL.md)**: 分析 Draft/BP 陣容相剋、分路開局、版本英雄池與中期轉折點。
- 🔫 **[valorant-analysis](file:///Users/eason.lee/.agents/skills/valorant-analysis/SKILL.md)**: VCT / Masters / Champions 賽事地圖選擇、特務組合 (Comp) 與關鍵回合分析。

### 3. 雙模型預測管線 (Prediction Pipeline)
- 🔄 **[prediction-pipeline](file:///Users/eason.lee/.agents/skills/prediction-pipeline/SKILL.md)**: 協調可稽核的預測流程。支援 `agy` 紅隊審查與雙模型（Codex 主預測 + agy 紅隊複核）互相質詢，最終產出具備風險對沖與校準依據的分析報告。

### 4. 自動化與工具鏈 (Automation & Shared Tools)
- 🤖 **[automation](file:///Users/eason.lee/.agents/skills/automation/README.md)**: 自動化 Crontab 觸發與郵件通知發送（支援 MLB 與 LoL 定時預測任務）。
- 📝 **[shared/notion](file:///Users/eason.lee/.agents/skills/shared/notion/README.md)**: 自動將預測分析結果解析並匯入 Notion Database / Data Source。

---

## 🛠️ 安裝與環境設定

### 1. Skill 安裝路徑
請確保此儲存庫中的 Skill 放置或連結於使用者家目錄的 agents skills 目錄：

```bash
mkdir -p ~/.agents/skills
# 將技能放置於 ~/.agents/skills/
```

### 2. 環境變數設定 (`.env`)
複製 `.env.example` 並設置相應的 Token 與通知金鑰：

```bash
cp .env.example .env
```

`.env` 關鍵變數說明：

- **Notion 整合**：
  ```env
  NOTION_TOKEN="secret_xxx"
  NOTION_DATA_SOURCE_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
  ```
- **郵件自動化通知**：
  ```env
  AUTOMATION_NOTIFICATION_EMAIL="you@gmail.com"
  SMTP_HOST="smtp.gmail.com"
  SMTP_PORT=465
  SMTP_PASSWORD="your_app_password"
  ```

---

## 📊 Notion 發布工具使用說明

所有賽事分析模組均整合共用 Notion 匯出器 `shared/notion/publish_prediction.mjs`。

### 測試與發布指令

```bash
# 測試發布 (Dry run)
node shared/notion/publish_prediction.mjs --dry-run path/to/prediction.json

# 正式發布至 Notion Database
node shared/notion/publish_prediction.mjs path/to/prediction.json
```

詳細發布欄位映射與進階設定請參考 [shared/notion/README.md](file:///Users/eason.lee/.agents/skills/shared/notion/README.md)。

---

## ⚙️ 自動化定時任務 (Automation & Crontab)

位於 `automation/` 目錄下的自動化模組支援定時抓取賽程、生成分析報告並發送至指定 Email 或 Notion。

```bash
# 安裝 Crontab 排程
bash automation/install_crontab.sh

# 移除 Crontab 排程
bash automation/uninstall_crontab.sh
```

詳細說明請見 [automation/README.md](file:///Users/eason.lee/.agents/skills/automation/README.md)。

---

## 📜 規範與開發注意事項

1. **時區與語言**：預設輸出繁體中文 (`zh-TW`) 與台灣時間 (`UTC+8`)。
2. **數據嚴謹性**：禁止捏造數據或假機率，須配合 `shared/validate_probabilities.mjs` 確保勝率與盤口 EV 計算正確。
3. **Commit 規範**：Git Commit Message 須符合 Conventional Commits 格式並使用繁體中文。
