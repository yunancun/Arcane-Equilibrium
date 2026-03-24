#!/usr/bin/env python3
# Compatibility wrapper / 兼容包装器
# Canonical implementation has moved to:
# /home/ncyu/BybitOpenClaw/srv/program_code/trade_executor/bybit_decision_lease/bybit_execution_authority_aggregator_contract_check.py

from pathlib import Path
import runpy
import sys

TARGET = Path(__file__).resolve().parents[3] / "trade_executor" / "bybit_decision_lease" / "bybit_execution_authority_aggregator_contract_check.py"
sys.path.insert(0, str(TARGET.parent))
runpy.run_path(str(TARGET), run_name="__main__")
