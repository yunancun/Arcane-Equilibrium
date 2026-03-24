#!/usr/bin/env python3
# Compatibility wrapper / 兼容包装器
# Canonical implementation has moved to:
# /home/ncyu/BybitOpenClaw/srv/program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_issue.py

from pathlib import Path
import runpy
import sys

TARGET = Path(r"/home/ncyu/BybitOpenClaw/srv/program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_issue.py")

if __name__ == "__main__":
    if not TARGET.exists():
        raise FileNotFoundError(f"Canonical target missing: {TARGET}")
    sys.path.insert(0, str(TARGET.parent))
    runpy.run_path(str(TARGET), run_name="__main__")
