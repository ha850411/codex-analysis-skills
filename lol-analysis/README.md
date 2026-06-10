# lol-esports-match-analysis

這是一個相容 Codex / Agent Skills 的工作流程，用於繁體中文 League of Legends 英雄聯盟電競賽事分析。

## 在 Codex 本機安裝

將此資料夾複製到 Codex 的技能探索位置，例如：

```bash
mkdir -p ~/.agents/skills
cp -R lol-esports-match-analysis ~/.agents/skills/
```

或放在專案 repository 內：

```bash
mkdir -p .agents/skills
cp -R lol-esports-match-analysis .agents/skills/
```

接著在 Codex 中明確呼叫：

```text
$lol-esports-match-analysis 深入分析今天 LCK 的比賽
```

## 檔案

- `SKILL.md`：必要的技能清單與使用指令。
- `references/source-priority.md`：資料來源優先順序與衝突規則。
- `references/output-template.md`：最終回答結構。
- `references/video-review-checklist.md`：VOD 複盤檢查清單。
- `agents/openai.yaml`：選用的 OpenAI/Codex UI 中繼資料。
