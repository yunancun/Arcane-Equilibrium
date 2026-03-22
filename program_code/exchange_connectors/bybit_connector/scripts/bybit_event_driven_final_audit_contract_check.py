#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_final_audit_contract_check.py

Role:
- 校验 D23.9 final audit 输出结构是否合法

Purpose in system:
- 给 D23 最终总审计再加一层 contract 保护
- 防止 final audit 自身结构漂移

Upstream:
- bybit_event_driven_final_audit.py

Output:
- bybit_event_driven_final_audit_contract_latest.json
'''
"""

import json
import time
from pathlib import Path

AUDIT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_final_audit_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_driven_final_audit_contract_latest.json"
OUT_PREFIX = OUT_DIR / "bybit_event_driven_final_audit_contract_"


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
    obj = load_json(AUDIT_PATH)
    checks = []

    add_check(checks, "audit_exists", AUDIT_PATH.exists(), str(AUDIT_PATH))
    add_check(checks, "audit_type_expected", obj.get("audit_type") == "bybit_event_driven_final_audit", obj.get("audit_type"))
    add_check(checks, "audit_version_v1", obj.get("audit_version") == "v1", obj.get("audit_version"))
    add_check(checks, "overall_ok_bool", isinstance(obj.get("overall_ok"), bool), obj.get("overall_ok"))
    add_check(checks, "failed_count_int", isinstance(obj.get("failed_count"), int), obj.get("failed_count"))
    add_check(checks, "total_checks_int", isinstance(obj.get("total_checks"), int), obj.get("total_checks"))
    add_check(checks, "checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__)
    add_check(checks, "failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__)

    ts_ms = int(time.time() * 1000)
    failed = [c for c in checks if not c["ok"]]

    result = {
        "report_type": "bybit_event_driven_final_audit_contract_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    OUT_LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = Path(str(OUT_PREFIX) + f"{ts_ms}.json")
    dated.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
