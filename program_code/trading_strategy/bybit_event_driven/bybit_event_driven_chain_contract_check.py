#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_chain_contract_check.py

Role:
- 校验 D23.6 consistency check 自身输出结构是否合法

Purpose in system:
- 让 event-driven 子链除了业务一致性外，还有一层 report contract 校验
'''
"""

import json
import time
from pathlib import Path
import os

CHECK_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_chain_consistency_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_driven_chain_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def add_check(checks, name, ok, detail):
    checks.append({
        "name": name,
        "ok": bool(ok),
        "detail": detail,
    })


def main():
    obj = load_json(CHECK_PATH)
    checks = []

    add_check(checks, "report_exists", CHECK_PATH.exists(), str(CHECK_PATH))
    add_check(
        checks,
        "report_type_expected",
        obj.get("report_type") == "bybit_event_driven_chain_consistency_check",
        obj.get("report_type"),
    )
    add_check(checks, "report_version_v1", obj.get("report_version") == "v1", obj.get("report_version"))
    add_check(checks, "overall_ok_bool", isinstance(obj.get("overall_ok"), bool), obj.get("overall_ok"))
    add_check(checks, "failed_count_int", isinstance(obj.get("failed_count"), int), obj.get("failed_count"))
    add_check(checks, "checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__)
    add_check(checks, "failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__)

    failed = [c for c in checks if not c["ok"]]

    result = {
        "report_type": "bybit_event_driven_chain_contract_check",
        "report_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    OUT_LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")


if __name__ == "__main__":
    main()
