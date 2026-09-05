#!/usr/bin/env python3
"""Explicit local entrypoint for all seven modules; does not install a schedule."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from shared.forecast.cli import main

if __name__=="__main__": raise SystemExit(main())
