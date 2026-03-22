#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_runtime_state_resolver.py
Role:
- 汇总 acceptance / packet / verdict / ws facts / preflight / snapshot / business_event_state
- 输出统一 runtime state

Purpose in system:
- 是当前系统总状态解释器
- 给 summary / policy / audit 提供统一状态源

Current integrated stage:
- 已集成 business event state
- 当前 runtime state 版本应为 v5

Maintenance notes:
- freshness 过期时，runtime 可能进入 degraded，这未必是代码故障
- 任何状态枚举改动都要同步 policy / summary / audit / handoff
'''

"""

import json
import time
from pathlib import Path

CYCLE_SUMMARY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_observer_cycle_latest.json")
ACCEPTANCE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_observer_acceptance_latest.json")
DECISION_PACKET_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json")
VERDICT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/verdicts/bybit/bybit_observer_verdict_latest.json")
PERSISTENT_WS_STATUS_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/ws_persistent/bybit_private_ws_listener_status_latest.json")
WS_RUNTIME_FACTS_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_ws_runtime_facts_latest.json")
PREFLIGHT_GUARD_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_private_rest_preflight_latest.json")
SNAPSHOT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json")
BUSINESS_EVENT_STATE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_state_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_runtime_state_latest.json"

FRESH_MS = 15 * 60 * 1000

def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))

def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_runtime_state_{ts_ms}.json"
    payload = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(payload, encoding="utf-8")
    dated.write_text(payload, encoding="utf-8")
    return str(OUT_LATEST), str(dated)

def age_state(ts_ms, now_ms, threshold_ms=FRESH_MS):
    if not ts_ms:
        return None, "missing"
    age = now_ms - int(ts_ms)
    return age, ("fresh" if age <= threshold_ms else "stale")

def main():
    now_ms = int(time.time() * 1000)

    cycle = load_json(CYCLE_SUMMARY_PATH)
    acceptance = load_json(ACCEPTANCE_PATH)
    packet = load_json(DECISION_PACKET_PATH)
    verdict = load_json(VERDICT_PATH)
    persistent_ws = load_json(PERSISTENT_WS_STATUS_PATH)
    ws_facts = load_json(WS_RUNTIME_FACTS_PATH)
    preflight = load_json(PREFLIGHT_GUARD_PATH)
    snapshot = load_json(SNAPSHOT_PATH)
    business_event_state = load_json(BUSINESS_EVENT_STATE_PATH)

    acceptance_passed = bool(acceptance.get("overall_passed"))
    preflight_allowed = bool(preflight.get("allowed_to_continue"))
    verdict_code = verdict.get("verdict_code", "UNKNOWN")

    snapshot_age_ms, snapshot_state = age_state(snapshot.get("ts_ms"), now_ms)
    ws_smoke_ts = packet.get("source_refs", {}).get("source_ws_smoke_ts_ms")
    ws_smoke_age_ms, ws_smoke_state = age_state(ws_smoke_ts, now_ms)
    ws_runtime_facts_age_ms, ws_runtime_facts_state = age_state(ws_facts.get("ts_ms"), now_ms)
    preflight_age_ms, preflight_state = age_state(preflight.get("ts_ms"), now_ms)

    payload_time_summary = snapshot.get("payload_time_summary") or {}
    account_payload_age_ms, account_payload_state = age_state(payload_time_summary.get("account_payload_ts_ms"), now_ms)
    positions_payload_age_ms, positions_payload_state = age_state(payload_time_summary.get("positions_payload_ts_ms"), now_ms)
    order_history_payload_age_ms, order_history_payload_state = age_state(payload_time_summary.get("order_history_payload_ts_ms"), now_ms)
    execution_history_payload_age_ms, execution_history_payload_state = age_state(payload_time_summary.get("execution_history_payload_ts_ms"), now_ms)

    persistent_ws_running = bool(persistent_ws.get("running", True))
    ws_listener_health = ws_facts.get("listener_health", "unknown")
    ws_connection_state = ws_facts.get("connection_state", "unknown")
    ws_signal_strength = ws_facts.get("signal_strength", "unknown")
    ws_connection_activity_state = ws_facts.get("connection_activity_state", "unknown")

    business_event_state_code = business_event_state.get("state_code", "unknown")
    business_event_healthy = bool(business_event_state.get("healthy"))
    business_event_stage = business_event_state.get("stage")
    business_event_reason = business_event_state.get("reason")

    stale_any_core = any([
        snapshot_state != "fresh",
        ws_smoke_state != "fresh",
        ws_runtime_facts_state != "fresh",
        preflight_state != "fresh",
        account_payload_state != "fresh",
        positions_payload_state != "fresh",
        order_history_payload_state != "fresh",
        execution_history_payload_state != "fresh",
    ])

    if not acceptance_passed or not preflight_allowed or stale_any_core:
        overall_runtime_state = "degraded"
    else:
        overall_runtime_state = "ready_readonly_observer"

    if verdict_code == "OBSERVE_ONLY":
        observer_state = "healthy_observe_only"
    else:
        observer_state = "nonstandard_observer_state"

    obj = {
        "state_type": "bybit_runtime_state",
        "state_version": "v5",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "system_mode": "read_only",
        "overall_runtime_state": overall_runtime_state,
        "acceptance_passed": acceptance_passed,
        "observer_state": observer_state,
        "verdict_code": verdict_code,
        "execution_state": "disabled",
        "ai_state": "disabled_by_policy",
        "preflight_guard_allowed": preflight_allowed,
        "persistent_ws_running": persistent_ws_running,
        "persistent_ws_state": ws_listener_health,
        "ws_listener_health": ws_listener_health,
        "ws_signal_strength": ws_signal_strength,
        "ws_connection_activity_state": ws_connection_activity_state,
        "snapshot_state": snapshot_state,
        "ws_smoke_state": ws_smoke_state,
        "ws_runtime_facts_state": ws_runtime_facts_state,
        "preflight_state": preflight_state,
        "business_event_state": business_event_state_code,
        "business_event_healthy": business_event_healthy,
        "payload_freshness": {
            "account_payload_age_ms": account_payload_age_ms,
            "account_payload_state": account_payload_state,
            "positions_payload_age_ms": positions_payload_age_ms,
            "positions_payload_state": positions_payload_state,
            "order_history_payload_age_ms": order_history_payload_age_ms,
            "order_history_payload_state": order_history_payload_state,
            "execution_history_payload_age_ms": execution_history_payload_age_ms,
            "execution_history_payload_state": execution_history_payload_state,
        },
        "freshness_refs": {
            "snapshot_age_ms": snapshot_age_ms,
            "ws_smoke_age_ms": ws_smoke_age_ms,
            "ws_runtime_facts_age_ms": ws_runtime_facts_age_ms,
            "preflight_age_ms": preflight_age_ms,
            "packet_freshness": packet.get("freshness", {}),
        },
        "business_event_context": {
            "stage": business_event_stage,
            "state_code": business_event_state_code,
            "healthy": business_event_healthy,
            "reason": business_event_reason,
        },
        "status_explainer": {
            "system_mode": "read_only means no live execution is allowed",
            "observer_state": "OBSERVE_ONLY is healthy readonly monitoring state",
            "payload_freshness": "tracks actual source payload ages, not just snapshot file creation time",
            "ws_signal_strength": "control_only means auth/subscribe traffic is present but no business-topic events seen yet",
            "business_event_state": "separates healthy empty business-event feed from broken business-event feed",
        }
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")

if __name__ == "__main__":
    main()
