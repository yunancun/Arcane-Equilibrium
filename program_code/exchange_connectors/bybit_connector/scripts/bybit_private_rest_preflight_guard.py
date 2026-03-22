#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_private_rest_preflight_guard.py
Role:
- 在 observer 下游步骤开始前检查 REST 侧基础输入是否完整且成功
- 这是 readonly 主链路的第一层安全闸门

Purpose in system:
- 防止坏的 REST 输入进入 snapshot / observer pipeline
- 判断 allowed_to_continue 是否为 true

Upstream:
- bybit_private_account_check.py
- bybit_private_positions_check.py
- bybit_private_order_history_check.py
- bybit_private_execution_history_check.py

Downstream:
- bybit_full_readonly_observer_cycle.py
- bybit_build_decision_packet.py
- bybit_runtime_state_resolver.py

Maintenance notes:
- preflight 通过只表示可以继续观察链路，不代表交易 readiness
- 若改字段命名，需要同步 cycle parsed_guard / runtime / audit
'''

"""

import json
import time
from pathlib import Path

ACCOUNT_PATH = Path("/home/ncyu/srv/log_files/connector_logs/bybit_private_account_check_latest.json")
POSITIONS_PATH = Path("/home/ncyu/srv/log_files/connector_logs/bybit_private_positions_check_latest.json")
ORDER_HISTORY_PATH = Path("/home/ncyu/srv/log_files/connector_logs/bybit_private_order_history_check_latest.json")
EXECUTION_HISTORY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_private_execution_history_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def main():
    now_ms = int(time.time() * 1000)

    account = load_json(ACCOUNT_PATH)
    positions = load_json(POSITIONS_PATH)
    order_history = load_json(ORDER_HISTORY_PATH)
    execution_history = load_json(EXECUTION_HISTORY_PATH)

    checks = []
    blocking_issues = []

    def add_check(name, ok, detail):
        checks.append({
            "name": name,
            "ok": bool(ok),
            "detail": detail,
        })
        if not ok:
            blocking_issues.append(name)

    add_check(
        "account_file_present",
        account is not None,
        str(ACCOUNT_PATH)
    )
    add_check(
        "positions_file_present",
        positions is not None,
        str(POSITIONS_PATH)
    )
    add_check(
        "order_history_file_present",
        order_history is not None,
        str(ORDER_HISTORY_PATH)
    )
    add_check(
        "execution_history_file_present",
        execution_history is not None,
        str(EXECUTION_HISTORY_PATH)
    )

    if account is not None:
        add_check("account_ok", account.get("ok") is True, account.get("retMsg"))
        add_check("account_retcode_zero", account.get("retCode") == 0, account.get("retCode"))

    if positions is not None:
        add_check("positions_ok", positions.get("ok") is True, positions.get("retMsg"))
        add_check("positions_retcode_zero", positions.get("retCode") == 0, positions.get("retCode"))

    if order_history is not None:
        add_check("order_history_ok", order_history.get("ok") is True, order_history.get("retMsg"))
        add_check("order_history_retcode_zero", order_history.get("retCode") == 0, order_history.get("retCode"))

    if execution_history is not None:
        spot = execution_history.get("spot") or {}
        linear = execution_history.get("linear") or {}
        add_check("execution_spot_ok", spot.get("ok") is True, spot.get("retMsg"))
        add_check("execution_spot_retcode_zero", spot.get("retCode") == 0, spot.get("retCode"))
        add_check("execution_linear_ok", linear.get("ok") is True, linear.get("retMsg"))
        add_check("execution_linear_retcode_zero", linear.get("retCode") == 0, linear.get("retCode"))

    allowed_to_continue = len(blocking_issues) == 0

    report = {
        "guard_type": "bybit_private_rest_preflight_guard",
        "guard_version": "v1",
        "ts_ms": now_ms,
        "allowed_to_continue": allowed_to_continue,
        "check_count": len(checks),
        "failed_count": sum(1 for x in checks if not x["ok"]),
        "checks": checks,
        "blocking_issues": blocking_issues,
    }

    latest_path = OUT_DIR / "bybit_private_rest_preflight_latest.json"
    dated_path = OUT_DIR / f"bybit_private_rest_preflight_{now_ms}.json"

    latest_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")

if __name__ == "__main__":
    main()
