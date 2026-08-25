# 即時盤口收集契約

本契約適用於所有賽事預測 skill。市場資料只可在模型機率與模型信心度鎖定後收集，不得回寫模型。

## 每場必做

1. 對報告範圍內每一場尚未開賽的比賽，執行一次 `shared/markets/collect_odds_api.mjs`。不可因前一場失敗就跳過後續場次。
2. 每次都傳入獨立 `--output` 與 `--error-output` 路徑。成功必須有 `status=success` 的快照；失敗必須有 `status=failed` 的錯誤憑證。
3. 收集器預設對網路錯誤、HTTP 429 與可重試 5xx 最多嘗試三次。不可在第一次短暫錯誤後直接宣稱 API 無法使用。
4. 先以 `--event` 查詢，並傳入 `--events-output` 保存該次 pending event 清單。收集器會處理空白、標點及保守的贊助商／隊名別名，例如 `DRX` 對 `Kiwoom DRX`。若回傳 `event_not_found` 或 `event_ambiguous`，讀取 pending event artifact，確認供應商場次後以 `--event-id` 重跑；不得自行猜測 event ID。
5. 多場日報逐場保存成功／失敗狀態、provider event ID（若有）、擷取時間、嘗試次數與 artifact 路徑。只有當日每場都有其中一種 artifact，才能宣稱盤口收集階段完成。

### LoL BO3／BO5 最低市場覆蓋

LoL 的投注決策不得只請求預設 ML。逐場重複傳入 `--market`：

- BO3：至少請求 `ML`、`Spread`、`Totals`，再確認 `Spread` 是否包含絕對值 1.5、`Totals` 是否包含 2.5。
- BO5：至少請求 `ML`、`Spread`、`Totals`，再確認 `Spread` 是否包含絕對值 1.5 與 2.5、`Totals` 是否包含 3.5 與 4.5。

收集器會映射 `ML`、`Spread` 與 `Totals`，並輸出每個已開 row 的雙邊價格。Spread 的 API `hdp` 是事件第一隊的盤線，第二隊使用相反號；Totals 盤線兼容 API 的 `hdp` 或 `max` 欄位。若同時請求多個市場但只有部分有開盤，成功 artifact 使用 `coverage.status=partial`，並在 `requested_but_unavailable` 列出缺少的市場；只有全部指定市場都不存在時才把整次收集分類為 `market_unavailable`。

市場名稱存在不代表必要盤線存在。post-market 層仍須把每一條必要盤線記入 `decision-slate.json.market_coverage.market_checks`，使用 `priced`、`unavailable`、`unmapped` 或 `failed`，並指向本次成功／失敗 artifact。不得以同一市場家族的其他線替代，例如 BO5 有 O/U 4.5 不能視為已查 O/U 3.5。

## 失敗分類與輸出

- `authentication`：金鑰缺少、401 或 403。先確認執行目錄能讀到被忽略的 `.env`；不得輸出金鑰。
- `rate_limit`：429。收集器重試後仍失敗才可標記，並保留錯誤憑證。
- `network`／`provider_unavailable`：重試耗盡的網路或 5xx 錯誤。
- `event_not_found`／`event_ambiguous`：必須完成 pending event 查核與 `--event-id` 重跑後，才可列為無法配對。
- `market_unavailable`：事件存在但 Stake 未開盤，或所有指定玩法都不存在。多市場請求只缺部分玩法時保留成功快照並標 partial。
- `market_not_mapped`：API 有價格，但目前尚未能安全映射到 pipeline outcome key；屬部分覆蓋，不是 API 取價失敗。

報告不得只寫「Odds-API 抓不到」「網路失敗」而沒有當次 artifact。無價時仍完成模型報告，列公允賠率、價格門檻與 0u；盤口失敗不改變模型勝率或模型信心度。

## 範例

```bash
node shared/markets/collect_odds_api.mjs \
  --sport esports \
  --event "DRX - Nongshim RedForce" \
  --home-outcome drx_ml \
  --away-outcome ns_ml \
  --home-prefix drx \
  --away-prefix ns \
  --market ML \
  --market Spread \
  --market Totals \
  --events-output <run-dir>/odds-pending-events.json \
  --output <run-dir>/odds-drx-ns.json \
  --error-output <run-dir>/odds-drx-ns.error.json
```
