#!/usr/bin/env python3
# Auto-generated compatibility wrapper
# 自动生成的兼容包装器
#
# Legacy path kept alive temporarily:
# 临时保留旧路径入口：
#   /home/ncyu/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_business_event_state_contract_check.py
#
# Real implementation now lives at:
# 真正实现现在位于：
#   /home/ncyu/BybitOpenClaw/srv/program_code/market_data_processor/bybit_business_events/bybit_business_event_state_contract_check.py

from pathlib import Path
import sys

CURRENT = Path(__file__).resolve()
REPO_ROOT = CURRENT.parents[4]
TARGET = REPO_ROOT / "program_code/market_data_processor/bybit_business_events/bybit_business_event_state_contract_check.py"

if not TARGET.exists():
    raise FileNotFoundError(f"Compatibility target missing: {TARGET}")

OLD_SCRIPT_DIR = CURRENT.parent
TARGET_DIR = TARGET.parent

for p in (str(OLD_SCRIPT_DIR), str(TARGET_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

code = TARGET.read_text(encoding="utf-8")
globals_dict = {
    "__name__": "__main__",
    "__file__": str(CURRENT),
    "__package__": None,
    "__cached__": None,
}
exec(compile(code, str(CURRENT), "exec"), globals_dict, globals_dict)
