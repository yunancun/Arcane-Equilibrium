#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_state_resolver.py
Role:
- 结合 business_event_runtime_facts + ws_runtime_facts
- 输出 business event 健康状态分类

Purpose in system:
- 区分“健康但暂无业务事件”和“业务事件侧不可信”

Current states:
- healthy_no_business_events_yet
- healthy_business_events_present
- stale_or_missing_business_event_feed

Downstream:
- bybit_runtime_state_resolver.py
- bybit_failure_policy_builder.py
- bybit_readonly_final_summary.py
- bybit_next_phase_handoff.py
- bybit_readonly_audit.py

Maintenance notes:
- healthy_no_business_events_yet 是关键健康空态，不能误判为坏
'''

"""

import json
import time
from pathlib import Path
import os

BUSINESS_RUNTIME_FACTS_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_runtime_facts_latest.json")
WS_RUNTIME_FACTS_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_ws_runtime_facts_latest.json")
OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_LATEST = OUT_DIR / "bybit_business_event_state_latest.json"

FRESH_MS = 15 * 60 * 1000

def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_business_event_state_{ts_ms}.json"
    payload = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(payload, encoding="utf-8")
    dated.write_text(payload, encoding="utf-8")
    return str(OUT_LATEST), str(dated)

def freshness_state(ts_ms, now_ms, threshold_ms=FRESH_MS):
    if not ts_ms:
        return {"age_ms": None, "state": "missing"}
    age = now_ms - int(ts_ms)
    return {
        "age_ms": age,
        "state": "fresh" if age <= threshold_ms else "stale"
    }

def main():
    now_ms = int(time.time() * 1000)

    business_facts = load_json(BUSINESS_RUNTIME_FACTS_PATH)
    ws_facts = load_json(WS_RUNTIME_FACTS_PATH)

    business_ts_ms = business_facts.get("ts_ms")
    ws_ts_ms = ws_facts.get("ts_ms")

    business_fresh = freshness_state(business_ts_ms, now_ms)
    ws_fresh = freshness_state(ws_ts_ms, now_ms)

    normalized_count = int(business_facts.get("normalized_count") or 0)
    has_business_events = bool(business_facts.get("has_business_events"))
    ws_connected = ws_facts.get("connection_state") == "connected"
    ws_running = bool(ws_facts.get("running"))
    ws_signal_strength = ws_facts.get("signal_strength")
    business_topic_event_count = int(ws_facts.get("business_topic_event_count") or 0)

    state_code = "unknown"
    healthy = False
    reason = "insufficient_input"

    if business_fresh["state"] != "fresh":
        state_code = "stale_or_missing_business_event_feed"
        healthy = False
        reason = "business event runtime facts missing or stale"
    elif ws_fresh["state"] != "fresh":
        state_code = "stale_or_missing_business_event_feed"
        healthy = False
        reason = "ws runtime facts missing or stale"
    elif not ws_running or not ws_connected:
        state_code = "stale_or_missing_business_event_feed"
        healthy = False
        reason = "ws not running or not connected"
    elif has_business_events or normalized_count > 0 or business_topic_event_count > 0:
        state_code = "healthy_business_events_present"
        healthy = True
        reason = "business events observed and runtime facts are fresh"
    else:
        state_code = "healthy_no_business_events_yet"
        healthy = True
        reason = "ws is healthy but no business-topic events have arrived yet"

    obj = {
        "state_type": "bybit_business_event_state",
        "state_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "D22.3",
        "state_code": state_code,
        "healthy": healthy,
        "reason": reason,
        "inputs": {
            "business_runtime_facts_path": str(BUSINESS_RUNTIME_FACTS_PATH),
            "ws_runtime_facts_path": str(WS_RUNTIME_FACTS_PATH),
        },
        "freshness": {
            "business_runtime_facts_ts_ms": business_ts_ms,
            "business_runtime_facts_age_ms": business_fresh["age_ms"],
            "business_runtime_facts_state": business_fresh["state"],
            "ws_runtime_facts_ts_ms": ws_ts_ms,
            "ws_runtime_facts_age_ms": ws_fresh["age_ms"],
            "ws_runtime_facts_state": ws_fresh["state"],
        },
        "business_event_summary": {
            "normalized_count": normalized_count,
            "has_business_events": has_business_events,
            "topic_counts": business_facts.get("topic_counts") or {},
            "event_type_counts": business_facts.get("event_type_counts") or {},
            "last_event_ts_ms": business_facts.get("last_event_ts_ms"),
            "last_event_age_ms": business_facts.get("last_event_age_ms"),
        },
        "ws_supporting_context": {
            "running": ws_running,
            "connection_state": ws_facts.get("connection_state"),
            "listener_health": ws_facts.get("listener_health"),
            "signal_strength": ws_signal_strength,
            "business_topic_event_count": business_topic_event_count,
            "message_count": ws_facts.get("message_count"),
            "last_event_age_ms": ws_facts.get("last_event_age_ms"),
        },
        "state_explainer": {
            "healthy_no_business_events_yet": "feed is healthy, but real business-topic events have not appeared yet",
            "healthy_business_events_present": "feed is healthy and real business-topic events are being observed",
            "stale_or_missing_business_event_feed": "business-event side is not trustworthy enough for downstream state use",
        }
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")

if __name__ == "__main__":
    main()
