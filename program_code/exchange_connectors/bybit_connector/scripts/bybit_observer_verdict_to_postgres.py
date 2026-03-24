#!/usr/bin/env python3
from pathlib import Path
import runpy
import sys

TARGET = Path(__file__).resolve().parent.parent / "readonly_observer_pipeline" / "bybit_observer_verdict_to_postgres.py"
sys.path.insert(0, str(TARGET.parent))
runpy.run_path(str(TARGET), run_name="__main__")
