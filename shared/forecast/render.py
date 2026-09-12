"""Render all reader formats from a validated immutable distribution."""
from __future__ import annotations

from datetime import timezone,timedelta
from .core import validate, derive, score_pair


def cell(value):
    return str(value).replace("|","\\|").replace("\n"," ").replace("\r"," ")


def percentage(value):
    return f"{value*100:.1f}%"


def quantile(distribution, level):
    mass=0.
    for value,p in sorted(distribution.items(),key=lambda item:int(item[0])):
        mass+=p
        if mass>=level: return int(value)
    return int(max(distribution,key=int))


def label(r,side):
    return "和局" if side=="draw" else r["participants"][0 if side=="a" else 1]


def headline(r):
    if r["status"]=="unmodeled": return "無法產生預測"
    d=derive(r["score_distribution"])
    prefix=""
    if r["sport"]=="lol":
        if r.get("parameter_source")=="analyst_elicited": prefix="分析者情境估計："
        elif r["status"]=="baseline": prefix="基準數值方向："
    return prefix+f"{label(r,d['winner_pick'])} {percentage(d['winner_probabilities'][d['winner_pick']])}；比分眾數 {d['score_mode']}（{percentage(d['score_mode_probability'])}）"


def confidence(r):
    if r["sport"]=="lol" and r["confidence"]:
        return f"{r['confidence']['value']}/100（證據品質）"
    return f"{r['confidence']['value']}%" if r["confidence"] else "N/A（缺評分依據）"


def method_label(r):
    if r["sport"]=="lol":
        if r.get("parameter_source")=="analyst_elicited":
            return "分析者情境估計（實驗，未實證校準）"
        if r["status"]=="baseline": return "僅比分基準（未實證校準）"
    return r["status"]


def table(records):
    rows=["## 簡表總結","","| 比賽 | 核心預測 | 模型信心度 | 建議 | 核心風險 |",
          "| --- | --- | ---: | --- | --- |"]
    for r in records:
        from .core import instant
        time=instant(r["scheduled_start"]).astimezone(timezone(timedelta(hours=8))).strftime("%m/%d %H:%M")
        decision=r.get("decision",{})
        advice=decision.get("advice") or "觀察；尚無合格投注決策，0u"
        if not r.get("recommendation_eligible",False):
            advice="觀察；未通過正式模型驗證，0u"
        elif decision.get("market_expires_at"):
            from datetime import datetime
            if instant(decision["market_expires_at"])<=datetime.now(timezone.utc):
                advice="價格已過期；重新取價與決策，0u"
        risk="；".join(r.get("risks",[])[:1] or r["missing_data"][:1]) or "結果變異"
        pred=headline(r)
        if r["sport"]=="lol" and r["status"]!="unmodeled":
            d=derive(r["score_distribution"])
            bo=r.get("best_of")
            extra=""
            if bo==3:
                extra=f"｜大2.5（各贏一局）{percentage(d['both_at_least_one'])}"
            elif bo==5:
                extra=f"｜大3.5（都贏一局以上）{percentage(d['both_at_least_one'])}"
            p_a=percentage(d["winner_probabilities"]["a"])
            p_b=percentage(d["winner_probabilities"]["b"])
            prefix=""
            if r.get("parameter_source")=="analyst_elicited": prefix="情境："
            elif r["status"]=="baseline": prefix="基準："
            pred=f"{prefix}{label(r,'a')} {p_a} vs {label(r,'b')} {p_b}（眾數 {d['score_mode']} {percentage(d['score_mode_probability'])}）{extra}"
        values=[f"{time} {' vs '.join(r['participants'])}",pred,confidence(r),advice,risk]
        rows.append("| "+" | ".join(map(cell,values))+" |")
    return "\n".join(rows)


def render(records,mode="full",report_link="prediction.md"):
    if not records: raise ValueError("at least one forecast required")
    for r in records: validate(r)
    if len({r["forecast_id"] for r in records})!=len(records):
        raise ValueError("duplicate forecast in report")
    lines=["# 賽事預測","", "模型信心度是證據品質評分，不是命中機率。",""]
    for r in records:
        lines.extend([f"## {r['competition']}｜{' vs '.join(r['participants'])}","",headline(r),"",
                      f"方法：{method_label(r)}｜快照：{r['snapshot']}｜資料截止：{r['data_cutoff']}",""])
        for point in r.get("key_points",[])[:3]: lines.append(f"- {point}")
        lines.append("")
        if r["status"]!="unmodeled":
            d=derive(r["score_distribution"])
            if max(d["winner_probabilities"].values())-sorted(d["winner_probabilities"].values())[-2]<.001:
                lines.extend(["勝負差距小於 0.1 個百分點，視為接近均勢。",""])
            elif r["sport"]=="lol" and abs(d["winner_probabilities"]["a"]-d["winner_probabilities"]["b"])<.02:
                # A presentation warning, not a calibration rule or a change to probabilities.
                lines.extend(["兩隊勝率差距小於 2 個百分點，接近均勢；數值方向不代表已證明實質優勢。",""])
            a,b=score_pair(d["score_mode"])
            score_winner="a" if a>b else "b" if b>a else "draw"
            if score_winner!=d["winner_pick"]:
                lines.extend(["勝方與比分眾數方向不同：分別由勝負總機率與單一比分峰值決定。",""])
            if len(d["score_ties"])>1 or len(d["winner_ties"])>1:
                lines.extend(["存在並列最高結果；顯示值依固定順序選取，不代表唯一優勢。",""])
            elif r["sport"]=="lol" and len(d["score_top3"])>1:
                first,second=d["score_top3"][:2]
                gap=r["score_distribution"][first]-r["score_distribution"][second]
                if gap<.002:
                    lines.extend([f"比分峰值接近：{first} 只比 {second} 高 {gap*100:.2f} 個百分點，不宜強調單一比分。",""])
            if mode=="full":
                for section in r.get("analysis_sections",[]):
                    if "簡表總結" in section["heading"]+section["markdown"]:
                        raise ValueError("summary belongs to renderer")
                    lines.extend([f"### {section['heading']}","",section["markdown"],""])
                if r["sport"]=="lol" and r.get("baseline_comparison"):
                    base=r["baseline_comparison"]["derived"]
                    lines.extend(["比分基準比較："+"；".join(
                        f"{label(r,side)} {percentage(base['winner_probabilities'][side])}" for side in ("a","b"))+
                        "。主情境估計另列如下；兩者未混合，也不以差距作為校準證據。",""])
                lines.extend(["### 結果分布","","| 結果 | 機率 | 公允賠率 |","| --- | ---: | ---: |"])
                for side,p in d["winner_probabilities"].items():
                    if p: lines.append(f"| {cell(label(r,side))} | {percentage(p)} | {1/p:.2f} |")
                lines.extend(["","| 比分（A–B） | 機率 |","| --- | ---: |"])
                # Esports complete support; count sports top three + remainder.
                scores=r["score_distribution"]
                keys=sorted(scores,key=lambda k:(-scores[k],k))
                shown=keys if r["sport"] in {"lol","cs","valorant","dota2"} else keys[:3]
                for key in shown: lines.append(f"| {key} | {percentage(scores[key])} |")
                if len(shown)<len(keys): lines.append(f"| 其他比分 | {percentage(1-sum(scores[k] for k in shown))} |")
                lines.append("")
                if r["sport"] in {"lol","cs","valorant","dota2"} and r.get("best_of",1)>1:
                    bo=r.get("best_of")
                    both_label="雙方皆至少一局／圖"
                    if r["sport"]=="lol":
                        if bo==3:
                            both_label="雙方各贏一場（大於 2.5 局／打滿三局）"
                        elif bo==5:
                            both_label="雙方皆贏一局以上（大於 3.5 局／拒絕橫掃）"
                    lines.extend(["| 衍生結果 | 機率 |","| --- | ---: |",
                                  f"| {cell(r['participants'][0])} 至少一局／圖 | {percentage(d['a_at_least_one'])} |",
                                  f"| {cell(r['participants'][1])} 至少一局／圖 | {percentage(d['b_at_least_one'])} |",
                                  f"| {both_label} | {percentage(d['both_at_least_one'])} |"])
                    if r["sport"]=="lol" and bo==5:
                        p_over_4_5=d["total_distribution"].get("5",0.0)
                        lines.append(f"| 雙方皆贏兩局以上（大於 4.5 局／戰滿五局） | {percentage(p_over_4_5)} |")
                    lines.extend(["","| 系列總局數 | 機率 |","| --- | ---: |"])
                    for total,p in sorted(d["total_distribution"].items(),key=lambda item:int(item[0])):
                        extra=""
                        if r["sport"]=="lol":
                            if bo==3 and total=="3": extra="（大 2.5／各贏一局）"
                            elif bo==5 and total=="4": extra="（大 3.5）"
                            elif bo==5 and total=="5": extra="（大 4.5／打滿五局）"
                        lines.append(f"| {total}{extra} | {percentage(p)} |")
                elif r["sport"] in {"mlb","nba","soccer"}:
                    total=d["total_distribution"];margin=d["margin_distribution"]
                    lines.extend(["| 得分指標 | 模型估計 |","| --- | ---: |",
                                  f"| A／B 得分均值 | {d['means'][0]:.1f}／{d['means'][1]:.1f} |",
                                  f"| 總分中位數／80%區間 | {quantile(total,.5)}／{quantile(total,.1)}–{quantile(total,.9)} |",
                                  f"| A−B 分差80%區間 | {quantile(margin,.1)}–{quantile(margin,.9)} |"])
                if r.get("scenarios"):
                    lines.extend(["","### 替代情境","","| 情境 | 權重 | 勝方機率 | 比分眾數 |","| --- | ---: | --- | --- |"])
                    for scenario in r["scenarios"]:
                        sd=derive(scenario["score_distribution"])
                        lines.append(f"| {cell(scenario['id'])} | {percentage(scenario['weight'])} | {cell(label(r,sd['winner_pick']))} {percentage(sd['winner_probabilities'][sd['winner_pick']])} | {sd['score_mode']} |")
                lines.extend(["",f"模型版本：{r['model_version']}；快照 ID：{r['forecast_id']}",""])
        risks=r.get("risks",[])+r["missing_data"]
        if risks: lines.extend(["主要風險／缺口："+"；".join(risks if mode=="full" else risks[:2]),""])
        if mode=="full":
            lines.extend(["### 來源",""])
            for e in r["evidence"]:
                lines.append(f"- [{e['id']}]({e['url']})：{e['claim']}（查核 {e['retrieved_at']}）")
            lines.append("")
    if mode=="chat": lines.extend([f"[完整報告]({report_link})",""])
    lines.append(table(records))
    text="\n".join(lines).strip()+"\n"
    if text.count("簡表總結")!=1: raise ValueError("exactly one final summary required")
    return text


def notion_summary(r):
    validate(r)
    return {"title":" vs ".join(r["participants"]),"module":r["sport"]+"-analysis",
            "sport":r["sport"],"event":r["competition"],"startTime":r["scheduled_start"],
            "prediction":headline(r),"confidence":confidence(r),"analysisType":"pre-match",
            "winner":label(r,derive(r["score_distribution"])["winner_pick"]) if r["status"]!="unmodeled" else "N/A",
            "recommendation":r.get("decision",{}).get("advice","觀察；未校準模型，0u"),
            "sourceStatus":r["status"],"risk":"；".join(r.get("risks",[])+r["missing_data"])}


def youtube(records):
    for r in records: validate(r)
    return "# 口播腳本\n\n"+"\n\n".join(
        f"{' 對 '.join(r['participants'])}。{headline(r)}。主要限制："+
        "；".join(r["missing_data"][:2] or ["結果仍有變異"])+"。" for r in records)+"\n"
