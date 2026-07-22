# 賽事分析自動排程

分析模組使用各自的 cron 排程（台灣時間）。預設值為：

- MLB 21:00：預測當日 21:00（含）至隔日 21:00（不含）的全部賽事。
- MLB 20:30：檢討前一日 21:00 產生的報告。
- LoL 09:00：預測當日 09:00（含）至隔日 09:00（不含）的全部 S Tier 賽事。
- LoL 08:30：檢討前一日 09:00 產生的報告。

每次預測排程也會自動清理三天以前的舊報告與產物。

在 `automation/modules.json` 啟用或停用模組，並管理模型與排程時間：

```json
{
  "timezone": "Asia/Taipei",
  "modules": {
    "mlb": {
      "enabled": true,
      "model": "gpt-5.6-sol",
      "reasoning_effort": "high",
      "schedule": {
        "prediction": "21:00",
        "review": "20:30"
      }
    },
    "lol": {
      "enabled": false,
      "model": "gpt-5.6-sol",
      "reasoning_effort": "high",
      "schedule": {
        "prediction": "09:00",
        "review": "08:30"
      },
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
- `schedule.prediction`：每天執行預測的台灣時間，必須是補零的 24 小時制 `HH:MM`。
- `schedule.review`：每天檢討前一日報告的台灣時間，格式同上，而且必須早於 `prediction`。

修改 `enabled`、模型或推理強度後不必重裝 cron，dispatcher 會在每次執行時重新讀取設定。修改 `schedule` 後則必須重新套用一次，讓 macOS crontab 更新：

```bash
automation/install_crontab.sh
```

預測程式的 24 小時賽事視窗會同步使用 `schedule.prediction`，不會停留在舊的固定時間。若 JSON 格式、時間格式或先後順序無效，安裝程式會拒絕覆寫現有 crontab。

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
python3 automation/run_scheduled.py prediction --module lol --dry-run
python3 automation/run_scheduled.py review --module lol --dry-run
```

兩個模組都將報告寄到唯一的 `AUTOMATION_NOTIFICATION_EMAIL`。如需多位收件者，使用逗號分隔；不提供模組專屬收件信箱設定。

## 賽後檢討分支

賽後檢討固定先抓取 `origin/master`，再從該基準建立 feature 分支：

- LoL：`feature/LOL-MMDD`，例如 `feature/LOL-0721`
- MLB：`feature/MLB-MMDD`，例如 `feature/MLB-0721`

只有檢討找到足以修改 Skill 的可重複流程問題時，才會提交、推送分支並建立以 `master` 為 base 的 PR。
