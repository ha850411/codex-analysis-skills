#!/usr/bin/env python3
"""Valorant v3 offline candidate: train, predict, replay, render and evaluate."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from shared.forecast.cli import read, write
from shared.forecast.core import record_forecast
from forecast.strength import train
from forecast.series import predict, validate_forecast
from forecast.compat import render
from forecast.evaluate import evaluate, compare, walk_forward
from forecast.archive_input import import_archive
from forecast.audit import audit_model_use


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest="command", required=True)
    for name in ("import-archive", "train", "predict", "validate", "record", "render", "evaluate", "compare", "walk-forward", "audit-model-use"):
        p = subs.add_parser(name)
        p.add_argument("input")
        p.add_argument("--output")
        if name in ("train", "walk-forward"):
            persistent = ROOT / ".automation-state/valorant/history/factor-registry.json"
            bundled = ROOT / "valorant-analysis/references/forecast-factors.json"
            p.add_argument("--registry", default=str(persistent if persistent.exists() else bundled))
        if name == "train":
            p.add_argument("--cutoff", required=True)
            p.add_argument("--config")
        if name in ("predict", "validate", "record"):
            p.add_argument("--model", required=True)
        if name in ("validate", "record"):
            p.add_argument("--event", required=True)
        if name == "audit-model-use":
            p.add_argument("--model")
            p.add_argument("--event")
        if name == "record":
            p.add_argument("--root", default=str(ROOT / ".automation-state"))
        if name == "render":
            p.add_argument("--mode", choices=("full", "quick", "daily-summary"), default="full")
            p.add_argument("--report-link", default="prediction.md")
        if name == "compare":
            p.add_argument("--baseline", required=True)
            p.add_argument("--challenger", required=True)
    args = parser.parse_args(argv)
    try:
        data = read(args.input)
        command = args.command
        if command == "import-archive":
            result = import_archive(data)
        elif command == "train":
            result = train(data.get("history", data) if isinstance(data, dict) else data,
                           args.cutoff, read(args.config) if args.config else None, read(args.registry))
        elif command == "predict":
            result = predict(read(args.model), data)
        elif command in ("validate", "record"):
            result = validate_forecast(data, read(args.model), read(args.event))
            if command == "record":
                result = record_forecast(data, args.root)
        elif command == "render":
            result = render(data if isinstance(data, list) else [data], args.mode, args.report_link)
        elif command == "evaluate":
            result = evaluate(data)
        elif command == "compare":
            result = compare(data, args.baseline, args.challenger)
        elif command == "audit-model-use":
            result = audit_model_use(data, read(args.model) if args.model else None,
                                     read(args.event) if args.event else None)
        else:
            result = walk_forward(data, read(args.registry))
        if args.output:
            write(args.output, result)
        elif isinstance(result, str):
            print(result, end="")
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        print("valorant forecast error: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
