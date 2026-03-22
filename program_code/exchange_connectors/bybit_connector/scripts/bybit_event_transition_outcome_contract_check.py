#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_transition_outcome_contract_check.py

Role:
- 校验 D23.5 transition outcome 的结构与状态合法性

Purpose in system:
- 确保 outcome 层 contract 稳定
- 防止后续 transition engine / demo gate 接口被改坏
'''
"""

import json
import time
from pathlib import Path

OUTCOME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_outcome_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_transition_outcome_contract_latest.json"


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
    obj = load_json(OUTCOME_PATH)
    checks = []

    add_check(checks, "outcome_exists", OUTCOME_PATH.exists(), str(OUTCOME_PATH))
    add_check(checks, "outcome_type_expected", obj.get("outcome_type") == "bybit_event_transition_outcome", obj.get("outcome_type"))
    add_check(checks, "outcome_version_v1", obj.get("outcome_version") == "v1", obj.get("outcome_version"))
    add_check(checks, "exchange_bybit", obj.get("exchange") == "bybit", obj.get("exchange"))
    add_check(checks, "stage_d23_5", obj.get("stage") == "D23.5", obj.get("stage"))

    allowed_codes = {
        "observe_only_retained",
        "transition_engine_entry_allowed",
        "transition_engine_blocked",
    }
    add_check(checks, "outcome_code_allowed", obj.get("outcome_code") in allowed_codes, obj.get("outcome_code"))
    add_check(checks, "outcome_ok_bool", isinstance(obj.get("outcome_ok"), bool), obj.get("outcome_ok"))
    add_check(checks, "outcome_reason_present", isinstance(obj.get("outcome_reason"), str) and bool(obj.get("outcome_reason")), obj.get("outcome_reason"))
    add_check(checks, "source_decision_ref_present", isinstance(obj.get("source_decision_ref"), dict), obj.get("source_decision_ref"))
    add_check(checks, "decision_context_present", isinstance(obj.get("decision_context"), dict), obj.get("decision_context"))

    outcome_code = obj.get("outcome_code")
    outcome_ok = obj.get("outcome_ok")

    if outcome_code == "observe_only_retained":
        add_check(checks, "observe_only_retained_consistent", outcome_ok is True, outcome_ok)
    elif outcome_code == "transition_engine_entry_allowed":
        add_check(checks, "transition_engine_entry_allowed_consistent", outcome_ok is True, outcome_ok)
    elif outcome_code == "transition_engine_blocked":
        add_check(checks, "transition_engine_blocked_consistent", outcome_ok is False, outcome_ok)

    failed = [c for c in checks if not c["ok"]]

    result = {
        "report_type": "bybit_event_transition_outcome_contract_check",
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
