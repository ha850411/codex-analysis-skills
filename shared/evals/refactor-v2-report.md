# 預測 skills v2 工程驗收

驗收日期：2026-09-06（Asia/Taipei）。重構前 Git 基準：`8b2f38724058eac0901764ee5b471d6f260c0eff`。

## 已交付

- 七個賽事 skill 與 prediction-pipeline 精簡入口，領域細節保留在 references；共用 [預測契約](../forecast/contract.md) 與 [輸出模板](../forecast/report-template.md)。
- 七項運動的基準／實驗模型、可追溯特徵、條件式系列賽分布、統一機率衍生、不可覆寫快照，以及時間切分與配對評估工具。
- 主評估為勝方命中率，次評估為精確比分；同時檢查 Brier、log loss、涵蓋率與子群退步。實驗通過只取得人工升版審查資格，不會自動成為正式模型。
- Markdown、聊天摘要、Notion 資料與 YouTube 腳本共用數值；結論先行、五欄最終總表，信心度明確代表證據品質。Notion 自動版型保留此原生總表。
- LoL／MLB 既有自動化增加發布前原始檔封存與賽後結果接回；保留既有專用模型及舊格式相容，不自動切換成新核心模型。
- 紅隊管線可接收鎖定的計算機率，禁止文字審查任意改數字；修正 LoL 將最可能比分誤當整體勝方的驗證邏輯。

## 測試結果

所有下列測試通過：Python 149 個、Node 17 個頂層測試（部分包含多項斷言），合計 166 個；另八個 skill 通過 quick_validate，`git diff --check` 通過。

```bash
python3 -m unittest shared.forecast.test_forecast
python3 -m unittest discover -s prediction-pipeline/scripts -p 'test_*.py'
python3 -m unittest discover -s automation -p 'test_*.py'
python3 -m unittest discover -s automation/lol -p 'test_*.py'
python3 -m unittest discover -s automation/mlb -p 'test_*.py'
python3 -m unittest discover -s mlb-analysis/scripts -p 'test_*.py'
node --test lol-analysis/scripts/test_*.mjs valorant-analysis/scripts/test_*.mjs shared/notion/test_*.mjs shared/markets/test_*.mjs
```

測試使用本地 fixture／暫存目錄／模擬市場回應；未執行真實預測排程、寄信、Notion 發布或 agy 模型呼叫。

## 歷史資料稽核與限制

LoL 71 筆均可正規化：70 筆為 legacy_unverified，1 筆為 reconstructed_after_start。MLB 111 筆均可正規化且為 legacy_unverified，其中 94 筆有最終結果，原始資料未提供完整比分分布，因此不從均值捏造分布或比分命中率。

legacy_unverified 表示尚待原始賽前快照及封存證據核對，不等於預測錯誤。只有可驗證的賽前紀錄可納入正式 prospective 成效；重建回放另列，不能混入宣稱改善的樣本。

目前沒有建立真實樣本外準確率提升證據，也沒有將任何新模型升為 production。領域進階因子需要另接實際、帶時間戳的賽前資料並累積足量樣本；七項運動的通用模型只是可評估的起點，不代表完整專業模型已全部訓練完成。既有 MLB 專用 public baseline 的操作規則保留；新 canonical baseline／experiment 不具正注碼建議資格。

## 預覽與後續驗收

執行 `python3 shared/forecast/examples.py --output-dir .runs/forecast-preview` 可產生七項運動的合成排版示例；示例不是實際賽事預測或效能證據。

後續依序接入可驗證賽前資料、收集不可變快照、完成相同賽事與時點的 paired walk-forward，再人工審核升版。未更動排程啟用狀態，未提交或推送 Git。
