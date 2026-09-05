"""Preserve validated legacy scheduled output and expose common audit artifacts."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if __package__ in {None,""}:
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    __package__="shared.forecast"

from .adapters import audit,adapt_evaluation
from .core import digest,instant
from .cli import write


def archive(run_dir, sport, state_root, module_state_dir=None):
    directory=Path(run_dir)
    raw=directory.joinpath("forecasts.jsonl").read_text(encoding="utf8")
    rows=[json.loads(line) for line in raw.splitlines() if line.strip()]
    if not rows: raise ValueError("no forecasts to archive")
    source=f"{sport}-history-v1"
    report=audit(rows,source)
    if report["errors"]:
        raise ValueError(f"legacy adapter failed: {report['errors']}")
    # Preserve evidence and probability checks alongside the original predictions.
    files={"forecasts.jsonl":raw}
    for name in ("prediction.md","probability-checks.json","forecast-evidence.json",
                 "schedule-verification.json","public-baseline.json","decision-slate.json"):
        file=directory/name
        if file.is_file(): files[name]=file.read_text(encoding="utf8")
    identity=digest(files)
    module_root=Path(module_state_dir) if module_state_dir else Path(state_root)/sport
    target=module_root/"history"/"source-runs"/identity
    receipt=target/"receipt.json"
    archived_at=json.loads(receipt.read_text())["archived_at"] if receipt.exists() else datetime.now(timezone.utc).isoformat()
    for name,content in files.items(): write(str(target/name),content)
    write(str(receipt),{"source_hash":identity,"archived_at":archived_at})
    normalized=[adapt_evaluation(r,source) for r in rows]
    for original,record in zip(rows,normalized):
        start=original.get("actual_start") or original.get("start_time") or original.get("first_pitch")
        if (start and instant(record["created_at"])<=instant(archived_at)<instant(start)
                and record["exclusion_reason"].startswith("timestamps precede start")
                and instant(record["data_cutoff"])<=instant(record["created_at"])):
            record["eligibility"]="prospective"
            record.pop("exclusion_reason",None)
        record["archived_at"]=archived_at
    write(str(target/"evaluation-v2.json"),normalized)
    report["source_archive"]=str(target)
    report["source_hash"]=identity
    report["original_artifacts"]=list(files)
    write(str(directory/"forecast-audit.json"),report)
    write(str(directory/"evaluation-v2.json"),normalized)
    return report


def join_results(path,sport,state_root,module_state_dir=None):
    """Join only result fields onto the archived forecast, preserving locked numbers."""
    rows=[json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    originals={}
    root=(Path(module_state_dir) if module_state_dir else Path(state_root)/sport)/"history"
    identity=lambda r:tuple(r[k] for k in ("event_id","snapshot","data_cutoff","model_version"))
    for file in sorted((root/"source-runs").glob("*/evaluation-v2.json")):
        for r in json.loads(file.read_text()):
            key=identity(r)
            if key in originals and originals[key]["source_hash"]!=r["source_hash"]:
                raise ValueError("conflicting immutable legacy forecast identity")
            if key not in originals or instant(r["archived_at"])<instant(originals[key]["archived_at"]):
                originals[key]=r
    evaluated=[]
    for row in rows:
        result=adapt_evaluation(row,f"{sport}-history-v1")
        original=originals.get(identity(result))
        if original:
            joined=dict(original)
            for key in ("actual_score","result_status"):
                joined[key]=result[key]
            # Verify that the review did not change locked inputs/probabilities.
            for key in ("score_distribution","winner_probabilities","means"):
                if original.get(key)!=result.get(key):
                    raise ValueError(f"review changed locked forecast {key}")
            result=joined
        evaluated.append(result)
    from .evaluation import evaluate
    report=evaluate(evaluated)
    write(str(root/"evaluations"/(digest(evaluated)+".json")),evaluated)
    write(str(Path(path).parent/"evaluation-v2.json"),evaluated)
    write(str(Path(path).parent/"evaluation-report-v2.json"),report)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir")
    parser.add_argument("--results",help="join a reviewed JSONL to prestart archives")
    parser.add_argument("--sport",required=True,choices=["lol","mlb"])
    parser.add_argument("--state-root",default=str(Path(__file__).resolve().parents[2]/".automation-state"))
    parser.add_argument("--module-state-dir",help="preserve an existing custom module state directory")
    args=parser.parse_args()
    try:
        if bool(args.run_dir)==bool(args.results): raise ValueError("choose --run-dir or --results")
        result=join_results(args.results,args.sport,args.state_root,args.module_state_dir) if args.results else archive(args.run_dir,args.sport,args.state_root,args.module_state_dir)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except (ValueError,KeyError,OSError) as exc:
        print(f"archive error: {exc}",file=sys.stderr);return 2


if __name__=="__main__": raise SystemExit(main())
