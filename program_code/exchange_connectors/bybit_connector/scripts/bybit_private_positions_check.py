#!/usr/bin/env python3
from pathlib import Path
import runpy
import sys

_REAL = Path(__file__).resolve().parents[3] / "exchange_connectors" / "bybit_connector" / "io_and_persistence" / "bybit_private_positions_check.py"
if not _REAL.exists():
    raise FileNotFoundError(f"Canonical script not found: {_REAL}")

if __name__ == "__main__":
    sys.path.insert(0, str(_REAL.parent))
    runpy.run_path(str(_REAL), run_name="__main__")
