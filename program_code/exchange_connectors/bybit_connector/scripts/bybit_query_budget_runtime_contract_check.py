#!/usr/bin/env python3
# Compatibility wrapper / 兼容包装器
from pathlib import Path
import runpy
import sys

TARGET = Path(__file__).resolve().parents[3] / "ai_agents" / "bybit_thought_gate" / "bybit_query_budget_runtime_contract_check.py"

if __name__ == "__main__":
    sys.path.insert(0, str(TARGET.parent))
    runpy.run_path(str(TARGET), run_name="__main__")
