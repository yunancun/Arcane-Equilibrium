#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_phase_contract_check.py

Role:
- 校验 event-driven phase 输出结构与 phase 合法性

Purpose in system:
- 防止 D23.2 状态机输出在后续维护中被改坏
- 作为人工维护时的快速安全检查
'''
"""

import json
import time
from pathlib import Path
import os

PHASE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_phase_latest.json")
OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_driven_phase_contract_latest.json"


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
    obj = load_json(PHASE_PATH)
    checks = []

    add_check(checks, "phase_exists", PHASE_PATH.exists(), str(PHASE_PATH))
    add_check(checks, "phase_type_expected", obj.get("phase_type") == "bybit_event_driven_phase", obj.get("phase_type"))
    add_check(checks, "phase_version_v1", obj.get("phase_version") == "v1", obj.get("phase_version"))
    add_check(checks, "exchange_bybit", obj.get("exchange") == "bybit", obj.get("exchange"))
    add_check(checks, "stage_d23_2", obj.get("stage") == "D23.2", obj.get("stage"))

    allowed_phase_codes = {
        "observer_only_empty_feed",
        "observer_event_flow_seen",
        "observer_feed_not_ready",
    }
    add_check(checks, "phase_code_allowed", obj.get("phase_code") in allowed_phase_codes, obj.get("phase_code"))
    add_check(checks, "phase_ready_bool", isinstance(obj.get("phase_ready"), bool), obj.get("phase_ready"))
    add_check(checks, "phase_reason_present", isinstance(obj.get("phase_reason"), str) and bool(obj.get("phase_reason")), obj.get("phase_reason"))
    add_check(checks, "source_state_ref_present", isinstance(obj.get("source_state_ref"), dict), obj.get("source_state_ref"))
    add_check(checks, "runtime_context_present", isinstance(obj.get("runtime_context"), dict), obj.get("runtime_context"))
    add_check(checks, "state_machine_hint_present", isinstance(obj.get("state_machine_hint"), dict), obj.get("state_machine_hint"))

    phase_code = obj.get("phase_code")
    phase_ready = obj.get("phase_ready")
    hint = obj.get("state_machine_hint") or {}

    if phase_code == "observer_only_empty_feed":
        add_check(
            checks,
            "empty_feed_consistent",
            (phase_ready is False) and (hint.get("allow_future_transition_engine") is False),
            {"phase_ready": phase_ready, "allow_future_transition_engine": hint.get("allow_future_transition_engine")},
        )
    elif phase_code == "observer_event_flow_seen":
        add_check(
            checks,
            "event_flow_seen_consistent",
            hint.get("allow_future_transition_engine") is True,
            {"allow_future_transition_engine": hint.get("allow_future_transition_engine")},
        )

    failed = [c for c in checks if not c["ok"]]

    result = {
        "report_type": "bybit_event_driven_phase_contract_check",
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
