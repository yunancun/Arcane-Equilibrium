#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_state_contract_check.py

Role:
- 校验 event-driven state 输出结构是否完整、状态是否合理

Purpose in system:
- 防止 D23 的 event-driven state 在后续扩展中被改坏
- 让人工维护时快速知道当前输出是否 still contract-safe
'''
"""

import json
import time
from pathlib import Path
import os

STATE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_state_latest.json")
OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_driven_state_contract_latest.json"


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
    obj = load_json(STATE_PATH)
    checks = []

    add_check(checks, "state_exists", STATE_PATH.exists(), str(STATE_PATH))
    add_check(checks, "state_type_expected", obj.get("state_type") == "bybit_event_driven_state", obj.get("state_type"))
    add_check(checks, "state_version_v1", obj.get("state_version") == "v1", obj.get("state_version"))
    add_check(checks, "exchange_bybit", obj.get("exchange") == "bybit", obj.get("exchange"))
    add_check(checks, "stage_d23_1", obj.get("stage") == "D23.1", obj.get("stage"))

    allowed_readiness = {"event_flow_present", "healthy_but_empty", "not_ready"}
    add_check(checks, "event_driven_readiness_allowed", obj.get("event_driven_readiness") in allowed_readiness, obj.get("event_driven_readiness"))

    add_check(checks, "has_business_events_present", isinstance(obj.get("has_business_events"), bool), obj.get("has_business_events"))
    add_check(checks, "normalized_count_present", isinstance(obj.get("normalized_count"), int), obj.get("normalized_count"))
    add_check(checks, "topic_observation_present", isinstance(obj.get("topic_observation"), dict), obj.get("topic_observation"))
    add_check(checks, "runtime_context_present", isinstance(obj.get("runtime_context"), dict), obj.get("runtime_context"))
    add_check(checks, "observer_context_present", isinstance(obj.get("observer_context"), dict), obj.get("observer_context"))

    failed = [c for c in checks if not c["ok"]]

    result = {
        "report_type": "bybit_event_driven_state_contract_check",
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
