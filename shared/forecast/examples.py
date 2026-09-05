#!/usr/bin/env python3
"""Generate seven clearly synthetic report previews and reproducible comparisons."""
import argparse
import sys
from pathlib import Path

if __package__ in {None,""}:
    sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
    __package__="shared.forecast"

from .fixtures import event,history
from .models import SPORTS,train
from .cli import forecast,write,walk_forward
from .render import render,youtube,notion_summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir",required=True)
    args=parser.parse_args()
    root=Path(args.output_dir)
    for sport in sorted(SPORTS):
        e=event(sport);h=history(sport)
        m=train(h,sport,e["data_cutoff"])
        r=forecast(m,e)
        target=root/sport
        for name,value in {"event.json":e,"history.json":h,"model.json":m,"forecast.json":r,
                           "prediction.md":render([r]),"chat-summary.md":render([r],"chat"),
                           "youtube-script.md":youtube([r]),"notion-summary.json":notion_summary(r)}.items():
            write(str(target/name),value)
        e.update(actual_score="110-105" if sport=="nba" else "5-2" if sport=="mlb" else "2-1",result_status="final")
        write(str(target/"comparison.json"),walk_forward({"history":h,"events":[e]}))
    print(f"Synthetic previews only: {root}")


if __name__=="__main__": main()
