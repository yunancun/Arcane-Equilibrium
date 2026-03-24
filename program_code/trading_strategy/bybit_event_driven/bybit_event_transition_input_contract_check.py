#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_transition_input_contract_check.py

Role:
- 校验 D23.3 transition input 输出结构与状态合法性

Purpose in system:
- 防止 transition input contract 在维护中被改坏
- 为后续 transition engine 提供稳定上游
'''
"""

import json
import time
from pathlib import Path

INPUT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_input_latest.json")
OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_transition_input_contract_latest.json"


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
    obj = load_json(INPUT_PATH)
    checks = []

    add_check(checks, "input_exists", INPUT_PATH.exists(), str(INPUT_PATH))
    add_check(checks, "input_type_expected", obj.get("input_type") == "bybit_event_transition_input", obj.get("input_type"))
    add_check(checks, "input_version_v1", obj.get("input_version") == "v1", obj.get("input_version"))
    add_check(checks, "exchange_bybit", obj.get("exchange") == "bybit", obj.get("exchange"))
    add_check(checks, "stage_d23_3", obj.get("stage") == "D23.3", obj.get("stage"))

    allowed = {
        "input_ready_but_empty",
        "input_ready_for_transition_engine",
        "input_not_ready",
    }
    add_check(checks, "transition_readiness_allowed", obj.get("transition_readiness") in allowed, obj.get("transition_readiness"))
    add_check(checks, "transition_allowed_bool", isinstance(obj.get("transition_allowed"), bool), obj.get("transition_allowed"))
    add_check(checks, "transition_reason_present", isinstance(obj.get("transition_reason"), str) and bool(obj.get("transition_reason")), obj.get("transition_reason"))
    add_check(checks, "source_refs_present", isinstance(obj.get("source_refs"), dict), obj.get("source_refs"))
    add_check(checks, "runtime_context_present", isinstance(obj.get("runtime_context"), dict), obj.get("runtime_context"))
    add_check(checks, "business_event_context_present", isinstance(obj.get("business_event_context"), dict), obj.get("business_event_context"))
    add_check(checks, "event_driven_state_context_present", isinstance(obj.get("event_driven_state_context"), dict), obj.get("event_driven_state_context"))
    add_check(checks, "event_driven_phase_context_present", isinstance(obj.get("event_driven_phase_context"), dict), obj.get("event_driven_phase_context"))

    readiness = obj.get("transition_readiness")
    allowed_flag = obj.get("transition_allowed")

    if readiness == "input_ready_but_empty":
        add_check(checks, "ready_but_empty_consistent", allowed_flag is False, allowed_flag)
    elif readiness == "input_ready_for_transition_engine":
        add_check(checks, "ready_for_transition_consistent", allowed_flag is True, allowed_flag)

    failed = [c for c in checks if not c["ok"]]

    result = {
        "report_type": "bybit_event_transition_input_contract_check",
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
