"""Render the EXISTING Valorant template; no edits to shared output contracts."""
from __future__ import annotations

from datetime import timedelta, timezone

from shared.forecast.core import derive, instant, score_pair
from shared.forecast.render import cell
from .series import validate_forecast


def pct(p):
    return f"{100 * p:.1f}%"


def fair(p):
    return f"{1 / p:.2f}" if p else "N/A（機率為零）"


def quoted(p):
    return f"{pct(p)}（公允 {fair(p)}）"


def confidence(record):
    return f"{record['confidence']['value']}/100（證據品質，非勝率）" if record["confidence"] else "N/A（未提供五項證據品質評分）"


def summary_text(r):
    d = derive(r["score_distribution"])
    winner = r["participants"][0 if d["winner_pick"] == "a" else 1]
    a, b = score_pair(d["score_mode"])
    owner = r["participants"][0 if a > b else 1]
    return f"勝方 {winner}，勝率 {pct(d['winner_probabilities'][d['winner_pick']])}；比分眾數 {owner} {max(a,b)}–{min(a,b)}，該比分機率 {pct(d['score_mode_probability'])}"


def render(records, mode="full", report_link="prediction.md"):
    if not records or mode not in ("full", "quick", "daily-summary"):
        raise ValueError("records and an existing Valorant report mode required")
    if len({r["forecast_id"] for r in records}) != len(records):
        raise ValueError("duplicate forecast in report")
    for record in records:
        validate_forecast(record)
    tw = timezone(timedelta(hours=8))
    cutoff = max(instant(r["data_cutoff"]) for r in records).astimezone(tw).isoformat()
    replay_label = "歷史重播／開發診斷，非當時發布的賽前預測。" if any(r["eligibility"] != "prospective" for r in records) else ""
    lines = ["整體結論：" + replay_label + "；".join(summary_text(r) for r in records) + "。", "", f"資料截止時間：{cutoff}（台灣時間）；公允賠率均為模型估計。", ""]
    for r in records:
        a, b = r["participants"]
        d, scores, bo = derive(r["score_distribution"]), r["score_distribution"], r["best_of"]
        need = bo // 2 + 1
        p_a, p_b = d["winner_probabilities"]["a"], d["winner_probabilities"]["b"]
        at = instant(r["scheduled_start"]).astimezone(tw).strftime("%H:%M")
        lines += [f"**{at}｜{a} vs {b}｜BO{bo}**", "", f"- **預測結論**：{summary_text(r)}。",
                  f"- **獨贏**：{a} {quoted(p_a)}；{b} {quoted(p_b)}。"]
        labels = [f"{a} {need}–{i} {pct(scores[f'{need}-{i}'])}" for i in range(need)]
        labels += [f"{b} {need}–{i} {pct(scores[f'{i}-{need}'])}" for i in range(need)]
        lines.append("- **完整比分分布**：" + "、".join(labels) + "。")
        if bo > 1:
            spread = need - .5
            lines += [f"- **至少一圖／受讓 +{spread:.1f} 圖**：{a} {quoted(d['a_at_least_one'])}；{b} {quoted(d['b_at_least_one'])}。",
                      f"- **橫掃／讓 -{spread:.1f} 圖**：{a} {quoted(scores[f'{need}-0'])}；{b} {quoted(scores[f'0-{need}'])}。"]
            if bo == 5:
                for handicap in (-1.5, 1.5):
                    pa = sum(p for s, p in scores.items() if score_pair(s)[0] - score_pair(s)[1] + handicap > 0)
                    pb = sum(p for s, p in scores.items() if score_pair(s)[1] - score_pair(s)[0] + handicap > 0)
                    lines.append(f"- **{'讓' if handicap < 0 else '受讓'} {handicap:+.1f} 圖**：{a} {quoted(pa)}；{b} {quoted(pb)}。")
            for total in ([2.5] if bo == 3 else [3.5, 4.5]):
                over = sum(p for s, p in scores.items() if sum(score_pair(s)) > total)
                over_label = "／打滿三圖" if bo == 3 else ("／打滿五圖" if total == 4.5 else "")
                under_label = "／任一方橫掃" if total == need + .5 else ""
                lines += [f"- **大於 {total:.1f} 圖{over_label}**：{quoted(over)}。", f"- **小於 {total:.1f} 圖{under_label}**：{quoted(1-over)}。"]
        lines += [f"- **預期總圖數**：{sum(d['means']):.2f} 圖；**模型信心度**：{confidence(r)}。", "", "**逐圖勝率預測**", ""]
        v = r["valorant"]
        lines += ["當前賽事地圖池：" + "、".join(v["map_pool"]) + f"。veto 狀態：{r['snapshot']}／{v['veto']['mode']}；名單與選邊依保存情境，未知效果未補造。", ""]
        all_contexts = [x["context"] for x in v["feature_audit"].values() if x["map"] is not None]
        lineups = {tuple(tuple(players) for players in c["lineups"]) for c in all_contexts if c.get("lineups")}
        if len(lineups) == 1:
            la, lb = next(iter(lineups))
            lines += [f"共同五人假設：{a} {'、'.join(la)}；{b} {'、'.join(lb)}。", ""]
        fixed = r["scenarios"] if len({tuple(s["maps"]) for s in r["scenarios"]}) == 1 else []
        for mp in v["map_pool"]:
            row = v["maps"][mp]
            contexts = [x["context"] for x in v["feature_audit"].values() if x["map"] == mp]
            sides = {c.get("a_start_side") for c in contexts}
            side_note = "A 開局進攻" if sides == {"attack"} else ("A 開局防守" if sides == {"defense"} else "開局選邊未知／混合情境")
            lineup_note = "沿用共同五人" if len(lineups) == 1 else ("逐圖五人輪替情境，組合見快照" if lineups else "五人組合未量化")
            text = f"{a} **{pct(row['a'])}**｜{b} **{pct(row['b'])}**" if row["a"] is not None else f"{a} **N/A**｜{b} **N/A**"
            state = "已 ban" if row["status"] == "excluded" else "未定"
            if fixed and mp in fixed[0]["maps"]:
                i = fixed[0]["maps"].index(mp)
                owners = {s["pick_owners"][i] for s in fixed}
                owner = next(iter(owners)) if len(owners) == 1 else "unknown"
                owner_label = "決勝圖" if owner is None else ("選圖方未定" if owner == "unknown" else r["participants"][0 if owner == "a" else 1] + " pick")
                state = ("已確認" if r["snapshot"] == "post-veto" else "預估") + f"第 {i+1} 圖，{owner_label}"
            lines.append(f"- **{mp}**：{text}；{state}；{lineup_note}，{side_note}；{row['reason']}")
        lines += ["", "**判讀與風險**：", ""]
        lines += ["- " + x for x in r.get("key_points", [])[:3]]
        mode_a, mode_b = score_pair(d["score_mode"])
        if ("a" if mode_a > mode_b else "b") != d["winner_pick"]:
            lines.append("勝方與比分眾數方向不同：分別由勝負總機率與單一比分峰值決定。")
        if len(d["winner_ties"]) > 1 or len(d["score_ties"]) > 1:
            lines.append("存在並列最高結果；固定順序顯示不代表唯一優勢。")
        elif len(d["score_top3"]) > 1:
            first, second = d["score_top3"][:2]
            gap = scores[first] - scores[second]
            if gap < .01:
                lines.append(f"前兩個比分結果 {first}／{second} 接近，機率僅差 {gap*100:.2f} 個百分點。")
        lines.append("主要翻轉條件：" + (r.get("risks") or ["未確認名單／veto 與小樣本地圖效果改變。"])[0])
        lines += ["", f"**價格與狀態**：{r['model_version']}／實驗模型；資料截止 {r['data_cutoff']}；快照 `{r['forecast_id']}`。未校準，0u；公允賠率不等於建議進場價。",
                  "限制：" + "；".join(r["missing_data"]), ""]
        if mode == "full":
            for section in r.get("analysis_sections", []):
                lines += [f"**{section['heading']}**", "", section["markdown"], ""]
        lines += [f"來源：[{e['id']}]({e['url']})（查核 {e['retrieved_at']}）" for e in r["evidence"]]
        lines.append("")
    lines += [f"[完整報告與附件]({report_link})", "", "| 比賽 | 核心預測 | 模型信心度 | 建議 | 核心風險 |", "| --- | --- | ---: | --- | --- |"]
    for r in records:
        at = instant(r["scheduled_start"]).astimezone(tw).strftime("%m/%d %H:%M")
        values = [at + "／" + " vs ".join(r["participants"]), summary_text(r), confidence(r), "觀察；實驗模型，0u", (r.get("risks") or r["missing_data"])[0]]
        lines.append("| " + " | ".join(cell(v) for v in values) + " |")
    return "\n".join(lines).strip() + "\n"
