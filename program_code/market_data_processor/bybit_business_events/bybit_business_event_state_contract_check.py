#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_state_contract_check.py
Role:
- 对 business event state 输出做契约检查

Purpose in system:
- 保证 business event 状态分类结果稳定、可被下游可靠消费

Maintenance notes:
- 状态枚举改动后应先同步这里
'''

"""

import json
import time
from pathlib import Path
import os

STATE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_state_latest.json")
OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_LATEST = OUT_DIR / "bybit_business_event_state_contract_latest.json"

ALLOWED_CODES = {
    "healthy_no_business_events_yet",
    "healthy_business_events_present",
    "stale_or_missing_business_event_feed",
}

def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def add(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})

def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_business_event_state_contract_{ts_ms}.json"
    payload = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(payload, encoding="utf-8")
    dated.write_text(payload, encoding="utf-8")
    return str(OUT_LATEST), str(dated)

def main():
    state = load_json(STATE_PATH)
    checks = []

    add(checks, "state_exists", bool(state), str(STATE_PATH))
    add(checks, "state_type_expected", state.get("state_type") == "bybit_business_event_state", state.get("state_type"))
    add(checks, "state_version_v1", state.get("state_version") == "v1", state.get("state_version"))
    add(checks, "exchange_bybit", state.get("exchange") == "bybit", state.get("exchange"))
    add(checks, "stage_d22_3", state.get("stage") == "D22.3", state.get("stage"))
    add(checks, "state_code_allowed", state.get("state_code") in ALLOWED_CODES, state.get("state_code"))
    add(checks, "healthy_bool", isinstance(state.get("healthy"), bool), state.get("healthy"))
    add(checks, "reason_present", bool(state.get("reason")), state.get("reason"))

    freshness = state.get("freshness") or {}
    add(checks, "freshness_present", isinstance(freshness, dict), freshness)

    summary = state.get("business_event_summary") or {}
    add(checks, "normalized_count_present", "normalized_count" in summary, summary.get("normalized_count"))
    add(checks, "has_business_events_present", "has_business_events" in summary, summary.get("has_business_events"))

    code = state.get("state_code")
    healthy = state.get("healthy")
    normalized_count = int(summary.get("normalized_count") or 0)
    has_business_events = bool(summary.get("has_business_events"))

    if code == "healthy_no_business_events_yet":
        add(checks, "healthy_no_events_consistent", healthy is True and normalized_count == 0 and has_business_events is False, {
            "healthy": healthy,
            "normalized_count": normalized_count,
            "has_business_events": has_business_events,
        })
    elif code == "healthy_business_events_present":
        add(checks, "healthy_with_events_consistent", healthy is True and (normalized_count > 0 or has_business_events is True), {
            "healthy": healthy,
            "normalized_count": normalized_count,
            "has_business_events": has_business_events,
        })
    elif code == "stale_or_missing_business_event_feed":
        add(checks, "stale_feed_consistent", healthy is False, {"healthy": healthy})

    failed = [c for c in checks if not c["ok"]]
    obj = {
        "report_type": "bybit_business_event_state_contract_check",
        "report_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")

if __name__ == "__main__":
    main()
