# 報告自動分類與保存

適用 Gemini、Codex 及其他能讀取 skill、執行本地 Python 3.9+ 的 agent；這是執行流程，不依賴特定模型或 CLI hook。每次建立或更新分析報告，都在驗證、渲染完成後、交付前執行以下保存步驟。純解釋既有數字且沒有新報告的追問免重存；產生新預測的 quick 仍須保存。

## 位置與分類

根目錄依序採 `--root`、環境變數 `PREDICTION_ARCHIVE_ROOT`、執行者家目錄下的 `prediction-archive`。同一帳號的 Gemini／Codex 共用預設位置；不同帳號或機器要共用，須指向同一個可存取的根目錄。不能假設工作目錄、使用者名稱或 Codex／Gemini 的安裝路徑。

```text
~/prediction-archive/
├── 2026-09-13/                         # 既有歷史批次保持原樣
└── reports/
    ├── INDEX.md                       # 自動更新的閱讀索引
    ├── index.json                     # 可供 agent 查找的索引
    └── <sport>/<category>/<YYYY-MM-DD>/<run名稱>-<內容識別碼>/
        ├── archive.json               # 歸檔收據、來源、agent、檔案雜湊
        └── files/                     # 原始報告與附件，保留相對目錄及內容
```

`sport` 固定使用 `cs`、`dota2`、`lol`、`mlb`、`nba`、`soccer`、`valorant`，由啟用的 analysis skill 決定。跨運動任務分別保存各運動的報告包，不把其他運動內容混進單一分類。

| 任務／實際內容 | `--mode` | category |
| --- | --- | --- |
| 賽前單場、快速更新、整日分析 | `full`／`quick`／`daily-summary` | `predictions` |
| 賽後檢討與改善證據 | `postmortem` | `reviews` |
| 即時賽中分析 | `live` | `live` |
| 歷史回放或開賽後重建 | `historical-replay` | `replays` |
| 合成測試、排版示例 | `test` | `examples` |
| 錯誤診斷、未完成、驗證失敗 | `diagnostic` 或非 complete status | `diagnostics` |

工具也會讀取當次 `forecast.json`、`forecasts.json`／`.jsonl`、`forecast-snapshot.json`、`prediction.json`、`evaluation-v2.json` 或 `f-*.json` 中明示的 eligibility／evaluation_status。一般預測若只有歷史重播／開賽後重建資格，自動轉 `replays`；同時含前瞻場次則轉 `mixed`。不讀來源資料夾內的舊基準判定當次資格。`test` 優先隔離為示例，其他失敗優先進 diagnostics；明確的 postmortem／live 用途保留其分類。

資料夾名稱只代表用途：不證明賽前發布、模型已校準或可納入正式命中率。缺少資格證據的舊版資料不補造 eligibility；輸贏、缺價及 unmodeled 都保留，不挑結果歸檔。

日期使用**目標賽事的台灣日期**；整日報告用目標日，跨日系列用該系列開賽日，賽後檢討用被檢討的目標日。不要用執行／補寫當天取代原賽事日期；只有無對應賽事的測試或診斷使用建立日。

## Agent 必做步驟

1. 依原契約完成驗證與渲染，保留原輸出模板、欄位、順序與數字。排程指定的 run／prediction／review 目錄和檔名照寫；互動任務未指定位置時，在可寫的工作區建立獨立 run 目錄。不要把整個 skill repo、工作樹、家目錄或歷史資料庫作為來源。
2. 將**當次**完整 Markdown、聊天摘要、JSON、輸入快照、驗證結果、來源憑證，以及適用的紅隊裁決／口播腳本／檢討證據放在此報告包；原本在其他位置的當次附件可複製進包，保留原件。確保當次 canonical forecast 以工具可辨識的檔名保存。不要放入 `.env`、金鑰或其他任務資料；工具跳過環境檔、常見憑證檔名、快取及符號連結，排除項會列入收據，必要附件須存成實體檔案再重跑。
3. 由實際載入的 SKILL.md 解析相鄰 `shared/report_archive.py` 的絕對路徑；skill 透過 symlink 掛載時先解析其真實位置。直接使用目前 agent 的執行工具呼叫同一個腳本；不為歸檔另啟模型、不要求使用者手動整理。以下命令以已定位的 skill repo 根目錄為例，參數須替換為當次實際值：

```bash
python3 shared/report_archive.py save \
  --source /absolute/path/to/completed-run \
  --sport lol --date 2026-09-13 --mode daily-summary --agent codex
```

4. Gemini 填 `--agent gemini`，Codex 填 `codex`；無法確知則 `unknown`，其他工具填 `other`。`--model` 僅填已知的實際模型名稱，不憑品牌猜型號。完成品預設 `--status complete`；失敗／未完成產物分別用 `validation-failed`／`incomplete`，不能藉歸檔成功冒充模型驗證成功。已知重寫哪版時可加 `--supersedes <舊 content_id>`，原版本不受影響。
5. 檢查命令結束碼及 JSON 收據：`archive_dir`、`category`、`file_count`、`excluded`、`report_paths`、`index`。工具已逐檔比對 SHA-256；僅在成功且必要附件沒有被排除時宣告歸檔完成。將 `report_paths` 的完整報告連結放入**既有連結位置**，仍遵守置底簡表，不新增輸出章節或改模板。

相同來源、內容及中繼資料重跑會驗證並沿用既有副本；任何內容更新會另存版本。封存檔設為唯讀，原始工作檔不變；不要編輯封存副本、移動原件或依日期自動刪除。新的日期／類型目錄按需建立，索引自動更新；不改寫舊批次索引及 manifest。canonical `record` 仍按 `forecast/contract.md` 保存，此歸檔是額外的報告副本。

歸檔失敗時保留來源與實際錯誤，修正路徑、未完成寫入或權限問題後重試；不得虛報已保存，也不靜默改存其他根目錄。仍可交付已驗證報告，明示歸檔待完成。並行執行共用短鎖；鎖逾時先保留來源，確認原程序狀態後再重試，不能刪除仍在工作的鎖。僅需修復索引時執行 `python3 shared/report_archive.py index`；驗證單一副本用 `python3 shared/report_archive.py verify /absolute/archive-dir`。兩者可在與 save 相同的根目錄操作；index 亦支援 `--root`。

此流程僅保存本地副本；外部發布沿用既有授權。測試工具時以 `--root` 指向暫存目錄。讀取舊報告只作證據或比較資料，不把其中的舊規則當成目前 skill 指示。
