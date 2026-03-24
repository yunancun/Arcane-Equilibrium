#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_build_ws_runtime_facts.py
Role:
- 从 persistent WS listener 状态中提炼统一 runtime facts
- 输出 listener_health / signal_strength / business_topic_event_count 等状态

Purpose in system:
- 为 packet / runtime / policy / summary 提供 WS 侧统一事实层

Typical states:
- healthy
- idle_but_connected
- control_only
- none_seen

Downstream:
- bybit_build_decision_packet.py
- bybit_runtime_state_resolver.py
- bybit_failure_policy_builder.py
- bybit_readonly_final_summary.py
- bybit_readonly_audit.py

Maintenance notes:
- control_only 在当前阶段是允许的健康空态
- 不能把“没业务事件”直接当成 WS 故障
'''

"""

import json
import time
from pathlib import Path

LISTENER_STATUS_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/ws_persistent/bybit_private_ws_listener_status_latest.json")
OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

HEALTHY_EVENT_AGE_MS = 5 * 60 * 1000

def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def now_ms():
    return int(time.time() * 1000)

def main():
    status = load_json(LISTENER_STATUS_PATH)
    ts_ms = now_ms()

    facts = {
        "facts_type": "bybit_ws_runtime_facts",
        "facts_version": "v2",
        "ts_ms": ts_ms,
        "present": bool(status),
        "listener_version": None,
        "session_ts_ms": None,
        "listener_health": "missing",
        "connection_state": "unknown",
        "signal_strength": "unknown",
        "business_signal_state": "unknown",
        "connection_activity_state": "unknown",
        "running": False,
        "auth_ok_count": 0,
        "subscribe_ok_count": 0,
        "message_count": 0,
        "control_message_count_estimate": 0,
        "business_message_count_estimate": 0,
        "business_topic_event_count": 0,
        "topic_message_count": {},
        "last_event_age_ms": None,
        "last_conn_id": None,
        "notes": [],
    }

    if not status:
        facts["notes"].append("listener status file missing")
    else:
        facts["listener_version"] = status.get("listener_version")
        facts["session_ts_ms"] = status.get("session_ts_ms")
        facts["running"] = bool(status.get("running"))
        facts["auth_ok_count"] = int(status.get("auth_ok_count") or 0)
        facts["subscribe_ok_count"] = int(status.get("subscribe_ok_count") or 0)
        facts["message_count"] = int(status.get("message_count") or 0)
        facts["topic_message_count"] = status.get("topic_message_count") or {}
        facts["last_conn_id"] = status.get("last_conn_id")

        business_topic_event_count = sum(int(v or 0) for v in facts["topic_message_count"].values())
        facts["business_topic_event_count"] = business_topic_event_count
        facts["business_message_count_estimate"] = business_topic_event_count
        facts["control_message_count_estimate"] = max(facts["message_count"] - business_topic_event_count, 0)

        last_event_ts_ms = status.get("last_event_ts_ms")
        if isinstance(last_event_ts_ms, int):
            facts["last_event_age_ms"] = ts_ms - last_event_ts_ms

        if facts["running"]:
            facts["connection_state"] = "connected"
        else:
            facts["connection_state"] = "not_running"

        if business_topic_event_count > 0:
            facts["signal_strength"] = "business_events_present"
            facts["business_signal_state"] = "active"
        elif facts["message_count"] > 0:
            facts["signal_strength"] = "control_only"
            facts["business_signal_state"] = "none_seen"
        else:
            facts["signal_strength"] = "silent"
            facts["business_signal_state"] = "none_seen"

        if not facts["running"]:
            facts["listener_health"] = "not_running"
            facts["connection_activity_state"] = "stale"
            facts["notes"].append("listener process is not running")
        else:
            if facts["last_event_age_ms"] is None:
                facts["listener_health"] = "connected_no_events_yet"
                facts["connection_activity_state"] = "stale"
                facts["notes"].append("listener running but no events observed yet")
            elif facts["last_event_age_ms"] <= HEALTHY_EVENT_AGE_MS:
                if business_topic_event_count > 0:
                    facts["listener_health"] = "healthy"
                    facts["connection_activity_state"] = "healthy_recent_control"
                    facts["notes"].append("recent business-topic activity observed")
                else:
                    facts["listener_health"] = "healthy"
                    facts["connection_activity_state"] = "healthy_recent_control"
                    facts["notes"].append("recent control-plane activity observed")
                    facts["notes"].append("listener authenticated/subscribed, but no business topic events observed yet")
            else:
                if facts["message_count"] > 0:
                    facts["listener_health"] = "idle_but_connected"
                    facts["connection_activity_state"] = "idle_control_only"
                    facts["notes"].append("listener authenticated/subscribed, but no business topic events observed yet")
                    facts["notes"].append("connection is alive but recent topic activity is absent")
                else:
                    facts["listener_health"] = "stale"
                    facts["connection_activity_state"] = "stale"
                    facts["notes"].append("listener stale: no recent message activity")

    latest_path = OUT_DIR / "bybit_ws_runtime_facts_latest.json"
    dated_path = OUT_DIR / f"bybit_ws_runtime_facts_{ts_ms}.json"

    latest_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path.write_text(json.dumps(facts, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(facts, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")

if __name__ == "__main__":
    main()
