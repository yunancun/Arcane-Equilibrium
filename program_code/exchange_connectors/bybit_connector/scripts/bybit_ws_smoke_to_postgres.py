#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_ws_smoke_to_postgres.py
Role:
- 执行私有 WebSocket smoke test
- 验证 auth / subscribe / 基本联通性
- 将结果写 latest / dated 文件并落库

Purpose in system:
- 用于验证 WS 通道可用性
- 不是 business-event readiness 的充分条件

Upstream:
- Bybit private WebSocket

Downstream:
- bybit_build_decision_packet.py
- bybit_observer_acceptance_check.py
- bybit_runtime_state_resolver.py

Maintenance notes:
- 当前只看到 control-plane 消息也可以是正常现象
- smoke 成功 ≠ 已经有业务事件
'''

"""

import json
import subprocess
import sys
from pathlib import Path

WS_SMOKE_SCRIPT = Path("/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_private_ws_smoke_test_v2.py")
WS_LOAD_SCRIPT = Path("/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_load_ws_jsonl_to_postgres.py")
PYTHON_VENV = Path("/home/ncyu/srv/venvs/trading_ws/bin/python")

def run_cmd(cmd):
    proc = subprocess.run(cmd, text=True, capture_output=True)
    return {
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }

def main():
    smoke = run_cmd([
        str(PYTHON_VENV),
        str(WS_SMOKE_SCRIPT),
        "--run-seconds", "20",
        "--topics", "wallet", "position", "order", "execution",
    ])

    load = run_cmd([
        sys.executable,
        str(WS_LOAD_SCRIPT),
    ])

    result = {
        "smoke_test": smoke,
        "load_to_postgres": load,
        "overall_ok": smoke["ok"] and load["ok"],
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
