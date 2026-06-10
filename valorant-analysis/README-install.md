# 安裝 Valorant 分析模組 Skill 到 Codex

此 skill 目錄可放在：

- 全域：`$HOME/.agents/skills/valorant-analysis/`
- 單一 repo：`<repo>/.agents/skills/valorant-analysis/`

## macOS / Linux 安裝

```bash
mkdir -p ~/.agents/skills
cp -R valorant-analysis-skill ~/.agents/skills/valorant-analysis
```

或在專案內使用：

```bash
mkdir -p .agents/skills
cp -R valorant-analysis-skill .agents/skills/valorant-analysis
```

## 測試提示詞

```text
使用 valorant-analysis skill，深入分析今天倫敦大師賽的比賽，請先列出台灣時間賽程盤點，再做每場 BO 格式、先發、地圖 BP、勝率與決策總結。
```
