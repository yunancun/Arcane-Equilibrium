#!/usr/bin/env python3
from pathlib import Path
import runpy
import sys

_REPO = Path(__file__).resolve().parents[4]
_REAL = _REPO / "helper_scripts" / "maintenance_scripts" / "bybit_connector" / "repair_i10_stage_source_aliases.py"

if not _REAL.exists():
    raise FileNotFoundError(f"Canonical script not found: {_REAL}")

if __name__ == "__main__":
    sys.path.insert(0, str(_REAL.parent))
    runpy.run_path(str(_REAL), run_name="__main__")
