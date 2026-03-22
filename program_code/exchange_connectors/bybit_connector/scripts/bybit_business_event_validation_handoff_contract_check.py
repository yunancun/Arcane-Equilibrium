#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_validation_handoff_contract_check.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G4.3 contract check
- 这一层的白话解释:
  校验 G 章 handoff 输出结构是否稳定，防止交接层本身漂移。

Role:
- 对 bybit_business_event_validation_handoff.py 的输出做结构合同校验
'''
"""

import json
import time
from pathlib import Path

CHECK_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_validation_handoff_latest.json")

OUT_DIR = CHECK_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_business_event_validation_handoff_contract_latest.json"


def add_check(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def main():
    ts_ms = int(time.time() * 1000)
    checks = []

    exists = CHECK_PATH.exists()
    add_check(checks, "handoff_exists", exists, str(CHECK_PATH))

    obj = {}
    if exists:
        obj = json.loads(CHECK_PATH.read_text(encoding="utf-8"))
        add_check(checks, "handoff_type_expected", obj.get("handoff_type") == "bybit_business_event_validation_handoff", obj.get("handoff_type"))
        add_check(checks, "handoff_version_v1", obj.get("handoff_version") == "v1", obj.get("handoff_version"))
        add_check(checks, "stage_g4_3", obj.get("stage") == "G4.3", obj.get("stage"))
        add_check(checks, "handoff_ok_bool", isinstance(obj.get("handoff_ok"), bool), obj.get("handoff_ok"))
        add_check(checks, "current_status_present", isinstance(obj.get("current_status"), dict), type(obj.get("current_status")).__name__)
        add_check(checks, "g_validation_summary_present", isinstance(obj.get("g_validation_summary"), dict), type(obj.get("g_validation_summary")).__name__)
        add_check(checks, "runtime_safety_context_present", isinstance(obj.get("runtime_safety_context"), dict), type(obj.get("runtime_safety_context")).__name__)
        add_check(checks, "hard_safety_boundaries_list", isinstance(obj.get("hard_safety_boundaries"), list), type(obj.get("hard_safety_boundaries")).__name__)
        add_check(checks, "recommended_next_build_order_list", isinstance(obj.get("recommended_next_build_order"), list), type(obj.get("recommended_next_build_order")).__name__)
        add_check(checks, "important_strategy_note_present", isinstance(obj.get("important_strategy_note"), dict), type(obj.get("important_strategy_note")).__name__)

    report = {
        "report_type": "bybit_business_event_validation_handoff_contract_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": all(x["ok"] for x in checks),
        "failed_count": sum(1 for x in checks if not x["ok"]),
        "checks": checks,
        "failed_checks": [x for x in checks if not x["ok"]],
    }

    OUT_LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_business_event_validation_handoff_contract_{ts_ms}.json"
    dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
