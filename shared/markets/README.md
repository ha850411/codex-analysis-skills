# Odds-API.io Stake 賽前盤收集

`collect_odds_api.mjs` 透過 Odds-API.io 收取指定 bookmaker 的十進位賽前盤；預設 bookmaker 是 Stake，適用於所有目前的賽事分析模組。它輸出可附加至 prediction pipeline 的 JSON 快照。金鑰只從被 Git 忽略的 `.env` 讀取，不會出現在輸出、日誌或程式碼中。舊的 `collect_odds_api_lol.mjs` 保留為相容入口。

## 收集順序

1. 在機率鎖定後，直接依事件名稱查詢 Odds-API.io；收集器會先找指定 sport 的待開賽事件，再取該場的 Stake 盤。模組 sport：CS2／Dota 2／LoL／Valorant 使用 `esports`，MLB 使用 `mlb`，NBA 使用 `nba`，世界盃使用 `football`：

   ```bash
  node shared/markets/collect_odds_api.mjs --sport esports \
     --event "LNG Esports - Ninjas in Pyjamas" \
     --home-outcome lng_ml --away-outcome nip_ml \
     --output odds-snapshot.json
   ```

2. 事件名稱有別名時，改用 provider event ID，可避免錯配：

   ```bash
  node shared/markets/collect_odds_api.mjs --sport football \
    --event-id 4242135875 --bookmaker Stake \
    --home-outcome home_ml --draw-outcome draw_ml --away-outcome away_ml \
     --output odds-snapshot.json
   ```

3. 掛載市場與進行市場決策：

   ```bash
   python3 prediction-pipeline/scripts/pipeline.py attach-market --run-dir <run-dir> --snapshot odds-snapshot.json
   python3 prediction-pipeline/scripts/pipeline.py post-market --run-dir <run-dir> --domain-skill lol-analysis/SKILL.md
   python3 prediction-pipeline/scripts/pipeline.py export --run-dir <run-dir>
   ```

   多場日報先逐場產生快照，再合併為單一 pipeline 輸入：

   ```bash
   node shared/markets/merge_odds_api_snapshots.mjs event-1.json event-2.json --output odds-snapshot.json
   ```

`attach-market` 不重跑主預測、agy 或最終裁決；它只重建市場盲 input 與市場比較。收集器目前將 `ML` 映射為 pipeline `market_data`（二路或足球三路）；其他 API 可見玩法會列入快照覆蓋資訊，但在建立相應機率 outcome key 前不得納入 EV，也不得將這種部分覆蓋宣稱為完整盤口分析。

`.env` 需有 `ODDS_API_KEY`；`.env.example` 只保留空白範本。不要將金鑰傳為 CLI 參數、寫進測資或放進 Git。Odds-API.io 同時回傳指定 bookmaker 的深連結、來源擷取時間與原始回應雜湊，供事後稽核。

## 測試

```bash
node shared/markets/test_collect_odds_api_lol.mjs
```

測試只傳入 `testdata/` 下的 `--events-response` 與 `--response` 本地 mock；這兩個旗標完全繞過 `.env`、認證與網路，禁止以真實 Odds-API.io 呼叫替代測試。
