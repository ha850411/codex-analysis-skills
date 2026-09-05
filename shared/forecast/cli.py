#!/usr/bin/env python3
"""Local-only forecasting CLI; never publishes, emails, or changes model status."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None,""}:
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    __package__="shared.forecast"

from .core import validate,derive,record_forecast,canonical,digest,instant
from .models import train,predict,SPORTS
from .evaluation import evaluate,compare
from .adapters import audit,adapt_evaluation
from .render import render,youtube,notion_summary


def read(path):
    text=Path(path).read_text(encoding="utf8")
    if path.endswith(".jsonl"):
        return [json.loads(line) for line in text.splitlines() if line.strip()]
    return json.loads(text)


def write(path,value):
    target=Path(path); target.parent.mkdir(parents=True,exist_ok=True)
    text=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+"\n"
    # Artifacts are create-only. A rerun needs a new run directory if data changed.
    try:
        with target.open("x",encoding="utf8") as stream: stream.write(text)
    except FileExistsError:
        if target.read_text(encoding="utf8")!=text:
            raise ValueError(f"artifact already exists with different content: {target}")


def forecast(model,event):
    result=predict(model,event)
    fields=("event_id","sport","competition","snapshot","created_at","data_cutoff","scheduled_start",
            "participants","evidence","confidence","scope","best_of","actual_start","key_points","risks","analysis_sections")
    out={k:event[k] for k in fields if k in event}
    out.update(schema_version="2.0",probability_unit="fraction",model_version=model["model_version"],
               parameter_version=model["parameter_version"],status=model["status"],
               eligibility=event.get("eligibility","prospective"),recommendation_eligible=False,
               missing_data=event.get("missing_data",[])+result["missing_data"],
               score_distribution=result["score_distribution"],model_artifact_hash=digest(model))
    if "scenarios" in result: out["scenarios"]=result["scenarios"]
    if not out.get("analysis_sections"):
        out["analysis_sections"]=[{"heading":"模型與可用資料",
            "markdown":f"使用 {model['model_version']}，訓練樣本 {model['n']} 場。訓練資料與參數均保存雜湊，所有衍生結果來自同一主分布。這是尚待樣本外驗證的模型輸出；未建模的領域因素列於缺口。"}]
    out["forecast_id"]=event.get("forecast_id") or "f-"+digest(out)[:32]
    out["derived"]=derive(out["score_distribution"])
    validate(out)
    return out


def walk_forward(payload):
    """Fixed outer events, strict earlier-result training; never optimize on holdout."""
    history=payload["history"]; events=payload["events"]
    if len({e["event_id"] for e in events})!=len(events):
        raise ValueError("walk-forward accepts one snapshot per event per experiment")
    rows=[]
    for event in sorted(events,key=lambda e:instant(e["data_cutoff"])):
        for variant in ("baseline","challenger"):
            base={"sport":event["sport"],"event_id":event["event_id"],"competition":event["competition"],
                  "snapshot":event["snapshot"],"data_cutoff":event["data_cutoff"],
                  "model_version":f"{event['sport']}-{variant}-v2.0","eligibility":"historical_replay",
                  "actual_score":event.get("actual_score"),"result_status":event.get("result_status","unknown")}
            try:
                m=train(history,event["sport"],event["data_cutoff"],variant,payload.get("factor_registry"))
                p=predict(m,event)
                base.update(status=m["status"],score_distribution=p["score_distribution"],
                            model_artifact_hash=digest(m))
            except (ValueError,KeyError) as exc:
                base.update(status="unmodeled",exclusion_reason=str(exc))
            rows.append(base)
    return {"experiment_hash":digest(payload),"records":rows,"evaluation":evaluate(rows),
            "comparisons":{sport:compare([r for r in rows if r["sport"]==sport],
                f"{sport}-baseline-v2.0",f"{sport}-challenger-v2.0") for sport in sorted({e["sport"] for e in events})}}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest="command",required=True)
    for name in ("validate","derive","record","render","evaluate","audit","adapt","train","predict","walk-forward","pipeline-input"):
        p=sub.add_parser(name); p.add_argument("input")
        p.add_argument("--output")
        if name in {"audit","adapt"}: p.add_argument("--source",required=True,choices=["lol-history-v1","mlb-history-v1","valorant-snapshot-v1"])
        if name=="record": p.add_argument("--root",default=str(Path(__file__).resolve().parents[2]/".automation-state"))
        if name=="render": p.add_argument("--output-dir",required=True)
        if name=="train":
            p.add_argument("--sport",required=True,choices=sorted(SPORTS));p.add_argument("--cutoff",required=True)
            p.add_argument("--variant",choices=["baseline","challenger"],default="baseline")
            p.add_argument("--registry",help="versioned active/candidate numeric factor registry")
        if name=="predict": p.add_argument("--model",required=True)
        if name=="evaluate":
            p.add_argument("--baseline"); p.add_argument("--challenger")
    args=parser.parse_args()
    try:
        data=read(args.input); cmd=args.command
        if cmd=="validate": validate(data); result={"valid":True,"sha256":digest(data)}
        elif cmd=="pipeline-input":
            from .pipeline_adapter import pipeline_input
            result=pipeline_input(data)
        elif cmd=="derive": result=derive(data)
        elif cmd=="record": result=record_forecast(data,args.root)
        elif cmd=="audit": result=audit(data if isinstance(data,list) else [data],args.source)
        elif cmd=="adapt": result=[adapt_evaluation(r,args.source) for r in (data if isinstance(data,list) else [data])]
        elif cmd=="train": result=train(data,args.sport,args.cutoff,args.variant,read(args.registry) if args.registry else None)
        elif cmd=="predict": result=forecast(read(args.model),data)
        elif cmd=="walk-forward": result=walk_forward(data)
        elif cmd=="evaluate":
            if bool(args.baseline)!=bool(args.challenger): raise ValueError("both comparison versions required")
            result=compare(data,args.baseline,args.challenger) if args.baseline else evaluate(data)
        elif cmd=="render":
            records=data if isinstance(data,list) else [data]
            # Prepare all formats before any write; no partial output on validation error.
            summaries=[notion_summary(r) for r in records]
            notion=summaries[0] if len(summaries)==1 else {
                "title":"每日賽事預測","sport":"multiple","module":"daily-summary",
                "analysisType":"daily-summary","confidence":"N/A（逐場分數見正文）",
                "prediction":"；".join(s["title"]+"："+s["prediction"] for s in summaries)}
            artifacts={"prediction.md":render(records),"chat-summary.md":render(records,"chat"),
                       "youtube-script.md":youtube(records),"prediction.json":records,
                       "notion-summary.json":notion,"notion-events.json":summaries}
            for filename,value in artifacts.items(): write(str(Path(args.output_dir)/filename),value)
            result={"output_dir":args.output_dir,"files":list(artifacts)}
        if args.output: write(args.output,result)
        else: print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
        return 0
    except (ValueError,KeyError,TypeError,OSError) as exc:
        print(f"forecast error: {exc}",file=sys.stderr);return 2


if __name__=="__main__": raise SystemExit(main())
