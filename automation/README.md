# 賽事分析自動排程

所有分析模組共用兩筆 cron 排程：

- 台灣時間 21:00：對每個已啟用模組執行下一日預測前置檢查。
- 台灣時間 15:00：對每個已啟用模組執行賽後檢討前置檢查。

在 `automation/modules.json` 啟用或停用模組；切換後不需要重新安裝 cron：

```json
{
  "timezone": "Asia/Taipei",
  "modules": {
    "mlb": {
      "enabled": true,
      "model": "gpt-5.6-sol",
      "reasoning_effort": "high"
    },
    "lol": {
      "enabled": false,
      "model": "gpt-5.6-sol",
      "reasoning_effort": "high",
      "schedule_source": "https://bo3.gg/lol/matches/current?tiers=s",
      "tier": "s"
    }
  }
}
```

只接受允許清單內的 `mlb` 與 `lol`。LoL 的賽程來源與等級固定為 S Tier，避免錯誤設定在未察覺時消耗 Token 分析較低層級賽事。

用 `enabled` 選擇預測模組：

- 只跑 MLB：`mlb.enabled=true`、`lol.enabled=false`
- 只跑 LoL：`mlb.enabled=false`、`lol.enabled=true`
- 兩者都跑：兩者皆設為 `true`
- 兩者都不跑：兩者皆設為 `false`；dispatcher 不會啟動 Codex

每個模組都必須設定：

- `model`：傳給 Codex CLI 的模型 ID，例如 `gpt-5.6-sol`。
- `reasoning_effort`：推理強度，可用 `none`、`minimal`、`low`、`medium`、`high`、`xhigh`、`max`、`ultra`；實際支援程度仍依模型與帳號權限而定。

## 安裝與移除 cron

```bash
automation/install_crontab.sh
crontab -l
automation/uninstall_crontab.sh
```

安裝程式會遷移舊的 MLB 專用受管區塊，並保留所有無關的 cron 工作。Log 寫入 `.automation-state/logs/`；各模組報告保留在 `.automation-state/<module>/`。

不啟動 Codex 即可測試 dispatcher：

```bash
python3 automation/run_scheduled.py prediction --dry-run
python3 automation/run_scheduled.py review --dry-run
```

兩個模組都將報告寄到唯一的 `AUTOMATION_NOTIFICATION_EMAIL`。如需多位收件者，使用逗號分隔；不提供模組專屬收件信箱設定。

## 賽後檢討分支

賽後檢討固定先抓取 `origin/master`，再從該基準建立 feature 分支：

- LoL：`feature/LOL-MMDD`，例如 `feature/LOL-0721`
- MLB：`feature/MLB-MMDD`，例如 `feature/MLB-0721`

只有檢討找到足以修改 Skill 的可重複流程問題時，才會提交、推送分支並建立以 `master` 為 base 的 PR。
