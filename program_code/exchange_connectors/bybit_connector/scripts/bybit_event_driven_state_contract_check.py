#!/usr/bin/env python3
from pathlib import Path
import runpy
import sys

_REPO = Path(__file__).resolve().parents[4]
_REAL = _REPO / "program_code" / "trading_strategy" / "bybit_event_driven" / "bybit_event_driven_state_contract_check.py"

if not _REAL.exists():
    raise FileNotFoundError(f"Canonical script not found: {_REAL}")

if __name__ == "__main__":
    sys.path.insert(0, str(_REAL.parent))
    runpy.run_path(str(_REAL), run_name="__main__")
