#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_transition_decision_contract_check.py

Role:
- 校验 D23.4 transition decision 输出结构与状态合法性

Purpose in system:
- 防止 transition decision contract 在维护中被改坏
- 为后续 transition engine 提供稳定决策层上游
'''
"""

import json
import time
from pathlib import Path

DECISION_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_decision_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_transition_decision_contract_latest.json"


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
    obj = load_json(DECISION_PATH)
    checks = []

    add_check(checks, "decision_exists", DECISION_PATH.exists(), str(DECISION_PATH))
    add_check(checks, "decision_type_expected", obj.get("decision_type") == "bybit_event_transition_decision", obj.get("decision_type"))
    add_check(checks, "decision_version_v1", obj.get("decision_version") == "v1", obj.get("decision_version"))
    add_check(checks, "exchange_bybit", obj.get("exchange") == "bybit", obj.get("exchange"))
    add_check(checks, "stage_d23_4", obj.get("stage") == "D23.4", obj.get("stage"))

    allowed_codes = {
        "keep_observe_only",
        "allow_transition_engine",
        "block_transition_engine",
    }
    add_check(checks, "decision_code_allowed", obj.get("decision_code") in allowed_codes, obj.get("decision_code"))
    add_check(checks, "decision_allowed_bool", isinstance(obj.get("decision_allowed"), bool), obj.get("decision_allowed"))
    add_check(checks, "decision_reason_present", isinstance(obj.get("decision_reason"), str) and bool(obj.get("decision_reason")), obj.get("decision_reason"))
    add_check(checks, "source_input_ref_present", isinstance(obj.get("source_input_ref"), dict), obj.get("source_input_ref"))
    add_check(checks, "transition_context_present", isinstance(obj.get("transition_context"), dict), obj.get("transition_context"))

    decision_code = obj.get("decision_code")
    decision_allowed = obj.get("decision_allowed")

    if decision_code == "keep_observe_only":
        add_check(checks, "keep_observe_only_consistent", decision_allowed is False, decision_allowed)
    elif decision_code == "allow_transition_engine":
        add_check(checks, "allow_transition_engine_consistent", decision_allowed is True, decision_allowed)
    elif decision_code == "block_transition_engine":
        add_check(checks, "block_transition_engine_consistent", decision_allowed is False, decision_allowed)

    failed = [c for c in checks if not c["ok"]]

    result = {
        "report_type": "bybit_event_transition_decision_contract_check",
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
