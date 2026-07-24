import copy
import json
import re
from pathlib import Path


RUN_DIR = Path(__file__).resolve().parent

with (RUN_DIR / "primary_prediction.json").open(encoding="utf-8") as handle:
    primary = json.load(handle)

analysis_sections = copy.deepcopy(primary["analysis_sections"])

# f3：把敘事段落中的地圖簡稱也統一成英文名（中國國服譯名）。
map_names = {
    "Breeze": "Breeze（微風島嶼）",
    "Split": "Split（霓虹町）",
    "Lotus": "Lotus（蓮華古城）",
    "Haven": "Haven（隱世修所）",
    "Sunset": "Sunset（日落之城）",
    "Ascent": "Ascent（亞海懸城）",
    "Summit": "Summit（天樞雲闕）",
}
for section in analysis_sections:
    for english, bilingual in map_names.items():
        section["markdown"] = re.sub(
            rf"\b{english}\b(?!（)",
            bilingual,
            section["markdown"],
        )

analysis_sections[-1]["markdown"] += (
    "\n\n**信心度算式核對**：整體信心度依共用契約採五項加權，"
    "0.25×84 + 0.20×96 + 0.25×83 + 0.20×68 + 0.10×62 "
    "= 80.75%，四捨五入為 81%；不是五項未加權平均。各場信心度亦以相同權重核算。"
)

final = {
    "schema_version": "1.0",
    "prediction_id": primary["prediction_id"],
    "stage": "final",
    "generated_at": "2026-07-23T13:23:17+08:00",
    "model": "current-session-gpt-5",
    "reasoning_effort": None,
    "accepted_findings": ["f1", "f3", "f4"],
    "rejected_findings": ["f2"],
    "finding_adjudications": [
        {
            "finding_id": "f1",
            "decision": "accept",
            "rationale": "daily-summary 模式依 Valorant 輸出模板必須含涵蓋全部六場的決策總結表；主預測確實尚未提供。",
            "resulting_action": "在 presentation.summary_table 新增九欄、六列的今日 Valorant 賽事決策總結表；由 exporter 保證它是全文最後一個區塊。",
        },
        {
            "finding_id": "f2",
            "decision": "reject",
            "rationale": "紅隊誤用未加權平均。共用方法契約明定權重為完整度25%、新鮮度20%、名單25%、制度樣本20%、穩定性10%；84、96、83、68、62 的加權值為 80.75%，四捨五入正是 81%。六場個別信心度亦逐一符合此公式。",
            "resulting_action": "不更動任何信心度數值；在模型校準段新增公式與算術核對，避免讀者誤解。",
        },
        {
            "finding_id": "f3",
            "decision": "accept",
            "rationale": "正式逐圖表與 veto 已使用雙語名稱，但部分數據矩陣與敘事仍只寫英文簡稱，未完全符合統一標註規則。",
            "resulting_action": "將所有分析段落內的七張地圖統一為英文名稱（中國國服譯名）。",
        },
        {
            "finding_id": "f4",
            "decision": "accept",
            "rationale": "現有證據只能確認賽前頁與前一場實際五人有差異，以及 Spear 將首秀；沒有官方當場五人與角色分工公告。",
            "resulting_action": "保留 pre-lineup 限制、T1/VARREL 情境帶與 EF 換人折價，不憑空確認名單；正式公告後必須建立新版快照重算。",
        },
    ],
    "question_resolutions": [
        {
            "question": "Will stax or DH start for T1, and will Klaus or Foxy9 start for VARREL in their match?",
            "status": "unresolved",
            "response": "截至預測快照沒有可追溯的官方當場五人公告；賽前頁與上一場實際陣容不一致，不能替任一組合下定論。",
            "impact": "T1 62% 是兩種五人情境的混合估計；DH 延續且 Foxy9 缺席可使 T1 約上修 2–3 個百分點，反向組合則約降至 58–59%，正式名單後重算。",
        },
        {
            "question": "How will Spear's VCT debut on Eternal Fire impact team communication and role allocations against Team Heretics?",
            "status": "unresolved",
            "response": "只有換人與首秀事實，沒有 Spear 與四名隊友的 Tier 1 同陣容樣本或正式特務分配。",
            "impact": "已把 EF/TH 的制度樣本相關性與模型穩定性降至 45/50，維持 TH 57%；若 EF 無須重配 Controller/Initiator 且 Spear 首殺順利，對局可回到近五五開。",
        },
        {
            "question": "How will the Summit（天樞雲闕） permaban collision resolve in official vetoes for TYLOO vs Nova Esports and FPX vs EDward Gaming?",
            "status": "unresolved",
            "response": "pre-veto 證據不足以確認誰改變慣例。主情境是假設 TYLOO 先禁 Summit（天樞雲闕）、NOVA 攬下針對 Sunset（日落之城）的責任；另一場則由 EDG 禁 Summit（天樞雲闕）。",
            "impact": "若 NOVA 仍禁 Haven（隱世修所），TYLOO 可翻成 52–54% 小幅優勢；若 EDG 放 Summit（天樞雲闕）改禁 Sunset（日落之城），FPX 54% 的 veto 優勢需下修並重建分布。",
        },
        {
            "question": "What will be the official map pick/ban orders, side selections, and pistol/eco conversion rates across all six matches once vetoes conclude?",
            "status": "unresolved",
            "response": "六場均尚未完成正式 veto；現有來源也沒有一致口徑的 pistol/eco 與選邊資料。",
            "impact": "現階段只發布 pre-veto 主分布與價格門檻，不給注碼；正式 veto、選邊與可核對數據出現後建立 post-veto 快照。",
        },
    ],
    "changes": [
        {
            "path": "presentation.summary_table",
            "before": "缺少 daily-summary 決策表",
            "after": "新增六場、九欄決策總結表",
            "reason": "符合 Valorant daily-summary 輸出契約，並讓每場的比分、勝率、至少一圖、門檻、信心與風險可快速核對。",
            "finding_ids": ["f1"],
        },
        {
            "path": "presentation.analysis_sections[*].markdown",
            "before": "部分敘事只使用英文地圖簡稱",
            "after": "所有地圖引用均採英文名稱（中國國服譯名）",
            "reason": "統一地圖命名格式。",
            "finding_ids": ["f3"],
        },
        {
            "path": "presentation.analysis_sections[7].markdown",
            "before": "列出信心度組成但未展開加權算式",
            "after": "補上 80.75% 四捨五入為 81% 的完整加權算式",
            "reason": "駁回紅隊未加權平均算法，同時提升算術可稽核性。",
            "finding_ids": ["f2"],
        },
        {
            "path": "risks / missing_data",
            "before": "已標示五人、首秀與 veto 未確認",
            "after": "保留限制並在裁決中明定公告後重算，不臆測未公布資訊",
            "reason": "名單與角色不確定性是真實限制，但目前不足以改寫鎖定分布。",
            "finding_ids": ["f4"],
        },
    ],
    "thesis": primary["thesis"],
    "probability_groups": primary["probability_groups"],
    "confidence": primary["confidence"],
    "key_factors": primary["key_factors"],
    "risks": primary["risks"],
    "missing_data": primary["missing_data"],
    "presentation": {
        "headline": "VCT 2026-07-23 Pacific／China／EMEA 六場深度分析：六場全是 pre-veto，小邊只看價格",
        "executive_summary": "市場盲模型預測 Global Esports 53%、T1 62%、Nova Esports 54%、FunPlus Phoenix 54%、Team Heretics 57%、Natus Vincere 55% 勝出；最可能比分全部為 2-1。除 T1 外都只是小邊，且六場正式 veto 尚未公布、T1/VARREL 五人待確認、Eternal Fire 由 Spear 當日首秀，因此沒有可追溯即時價格時不給注碼。agy 紅隊要求補上決策表與統一地圖雙語名稱；它對信心度的未加權平均質疑被 Codex 依 25/20/25/20/10 契約駁回。",
        "analysis_sections": analysis_sections,
        "key_points": [
            "全日最大系列賽優勢是 T1 62%，但當場五人未確認，仍需等 lineup。",
            "TYLOO/NOVA 與 FPX/EDG 的主勝率只有 54%，核心資訊在 Summit（天樞雲闕）禁圖碰撞。",
            "Eternal Fire 當日換上 Spear，Team Heretics 的 57% 主要來自 roster continuity，不是追逐上一場勝負。",
            "沒有一致、可追溯且結算明確的即時市場價格，因此只給公允價與進場門檻，不給投注建議或注碼。",
        ],
        "disclaimer": "本報告是 2026-07-23 12:55（Asia/Taipei）的 pre-veto、pre-lineup 機率快照，不保證獲利。正式五人、veto、選邊、Patch 或可追溯市場價格更新後，應建立新快照重算；請自行控管風險並遵守所在地法規。",
        "summary_table": {
            "columns": [
                "時間 (UTC+8)",
                "對戰組合",
                "賽制（BO?）",
                "預測比分",
                "獨贏機率（Win%）",
                "受讓/破蛋機率（+1.5 maps / 至少一圖）",
                "推薦",
                "模型信心度",
                "核心風險（Key Risk）",
            ],
            "rows": [
                [
                    "2026-07-23 16:00",
                    "Global Esports vs FULL SENSE",
                    "BO3",
                    "GE 2-1",
                    "GE 53% / FS 47%",
                    "GE 80% / FS 78%",
                    "觀望；正式五人與 veto 後 GE 價格 ≥2.00 才重評",
                    "76%",
                    "FS 自選圖上限；GE 的 2-0 含延長賽，優勢很薄",
                ],
                [
                    "2026-07-23 17:00",
                    "TYLOO vs Nova Esports",
                    "BO3",
                    "NOVA 2-1",
                    "TYLOO 46% / NOVA 54%",
                    "TYLOO 84% / NOVA 85%",
                    "觀望；veto 後 NOVA 價格 ≥2.00 才重評",
                    "89%",
                    "Summit（天樞雲闕）permaban 碰撞；NOVA 若仍禁 Haven（隱世修所）會翻盤",
                ],
                [
                    "2026-07-23 19:00",
                    "T1 vs VARREL",
                    "BO3",
                    "T1 2-1",
                    "T1 62% / VARREL 38%",
                    "T1 86% / VARREL 71%",
                    "等五人；確認後 T1 價格 ≥1.72 才重評",
                    "70%",
                    "stax/DH 與 Klaus/Foxy9 尚未官方確認",
                ],
                [
                    "2026-07-23 20:00",
                    "FunPlus Phoenix vs EDward Gaming",
                    "BO3",
                    "FPX 2-1",
                    "FPX 54% / EDG 46%",
                    "FPX 83% / EDG 81%",
                    "觀望；veto 後 FPX 價格 ≥2.00 才重評",
                    "89%",
                    "EDG 若放 Summit（天樞雲闕）改禁 Sunset（日落之城），主情境失效",
                ],
                [
                    "2026-07-23 23:00",
                    "Eternal Fire vs Team Heretics",
                    "BO3",
                    "TH 2-1",
                    "EF 43% / TH 57%",
                    "EF 76% / TH 84%",
                    "等 EF 正式分工；TH 價格 ≥1.92 才重評",
                    "74%",
                    "Spear VCT 首秀，溝通與角色分配沒有 Tier 1 樣本",
                ],
                [
                    "2026-07-24 02:00",
                    "Gentle Mates vs Natus Vincere",
                    "BO3",
                    "NAVI 2-1",
                    "M8 45% / NAVI 55%",
                    "M8 79% / NAVI 84%",
                    "觀望；veto 後 NAVI 價格 ≥1.96 才重評",
                    "84%",
                    "M8 的 Lotus（蓮華古城）優勢通常會被 NAVI 首禁；舊 H2H 已跨 Patch",
                ],
            ],
        },
        "youtube": {
            "title": "VCT 今日六場全拆：Pacific、CN、EMEA 誰是真優勢？｜agy 紅隊複核",
            "hook": "今天六場最可能比分竟然全部是 2-1，但這不代表六場都值得碰；真正決勝的是兩組 Summit 禁圖碰撞、T1 的五人名單，以及 Spear 的 VCT 首秀。",
            "sections": [
                {
                    "heading": "Pacific：GE/FS 與 T1/VARREL",
                    "script": "GE 只以 53% 小幅領先 FULL SENSE，關鍵是 GE 的 Summit（天樞雲闕）實戰路徑與 FS 在 Haven（隱世修所）的下限；這場不該被 2-0 戰績騙成大邊。T1 是全日最大優勢 62%，但 stax 或 DH、Klaus 或 Foxy9 尚未確認，因此必須等正式五人再定價。",
                },
                {
                    "heading": "China：兩場都由 veto 幾何主導",
                    "script": "TYLOO 和 NOVA 都是四勝零敗，NOVA 的 54% 完全建基於它願意把首禁從 Haven（隱世修所）移去 Sunset（日落之城）。FPX 對 EDG 同樣是 54%，因為 FPX 可先禁 Haven（隱世修所），逼 EDG 處理 Summit（天樞雲闕），讓 Sunset（日落之城）留成決勝圖。",
                },
                {
                    "heading": "EMEA：換人風險與地圖深度",
                    "script": "Team Heretics 的 57% 來自陣容延續性；Eternal Fire 當日讓 Spear 首秀，個人槍法可能打穿模型，但溝通與角色分配沒有樣本。NAVI 以 55% 領先 Gentle Mates，因為 Split（霓虹町）、Ascent（亞海懸城）、Sunset（日落之城）都有可走的路，而 M8 最清楚的 Lotus（蓮華古城）優勢通常會先被禁掉。",
                },
                {
                    "heading": "決策與紅隊裁決",
                    "script": "agy 紅隊正確抓到決策表缺漏與地圖命名不一致；但它用未加權平均挑戰 81% 信心度是錯的。契約權重是二十五、二十、二十五、二十、十，加權結果八十點七五，四捨五入就是八十一。",
                },
            ],
            "closing": "這份是 pre-veto 快照，不是賽前最後一秒答案。等正式五人與 veto，再用 GE 2.00、T1 1.72、NOVA 2.00、FPX 2.00、TH 1.92、NAVI 1.96 的折價門檻重算；沒有達價就跳過。",
        },
    },
}

with (RUN_DIR / "final_prediction.json").open("w", encoding="utf-8") as handle:
    json.dump(final, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
