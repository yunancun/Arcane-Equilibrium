#!/usr/bin/env python3
from pathlib import Path
import runpy
import sys

TARGET = Path(__file__).resolve().parent.parent / "readonly_observer_pipeline" / "run_bybit_observer_cycle.py"
sys.path.insert(0, str(TARGET.parent))
runpy.run_path(str(TARGET), run_name="__main__")
