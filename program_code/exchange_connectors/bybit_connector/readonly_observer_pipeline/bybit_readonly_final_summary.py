#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_readonly_final_summary.py
Role:
- 生成人工最容易阅读的最终汇总文件
- 汇总 readonly readiness / freshness / packet / verdict / cycle / business event status

Purpose in system:
- 给维护者快速看当前整体状态
- 是人工交接和阶段确认的重要文件

Current integrated stage:
- 已集成 business event 状态
- 当前版本应为 v4

Maintenance notes:
- 这是面向人工阅读的总览，不是底层判定器
- 若新增状态字段，优先保证可读性和解释性
'''

"""

import json
import time
from pathlib import Path

RUNTIME_STATE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")
ACCEPTANCE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_observer_acceptance_latest.json")
FAILURE_POLICY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_failure_policy_latest.json")
CYCLE_SUMMARY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_observer_cycle_latest.json")
VERDICT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/verdicts/bybit/bybit_observer_verdict_latest.json")
DECISION_PACKET_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json")
WS_RUNTIME_FACTS_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_ws_runtime_facts_latest.json")
PREFLIGHT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_private_rest_preflight_latest.json")
SNAPSHOT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json")
BUSINESS_EVENT_STATE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_state_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_readonly_final_summary_latest.json"

def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}

def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_readonly_final_summary_{ts_ms}.json"
    payload = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(payload, encoding="utf-8")
    dated.write_text(payload, encoding="utf-8")
    return str(OUT_LATEST), str(dated)

def main():
    cycle = load_json(CYCLE_SUMMARY_PATH) or {}
    acceptance = load_json(ACCEPTANCE_PATH) or {}
    failure_policy = load_json(FAILURE_POLICY_PATH) or {}
    verdict = load_json(VERDICT_PATH) or {}
    packet = load_json(DECISION_PACKET_PATH) or {}
    ws_runtime = load_json(WS_RUNTIME_FACTS_PATH) or {}
    preflight = load_json(PREFLIGHT_PATH) or {}
    snapshot = load_json(SNAPSHOT_PATH) or {}
    runtime = load_json(RUNTIME_STATE_PATH) or {}
    business_event_state = load_json(BUSINESS_EVENT_STATE_PATH) or {}

    cycle_steps = cycle.get("steps") or []
    stage_counts = {}
    for step in cycle_steps:
        stage = step.get("stage", "unknown")
        stage_counts[stage] = stage_counts.get(stage, 0) + 1

    latest_cycle_summary = {
        "overall_ok": cycle.get("overall_ok"),
        "step_count": len(cycle_steps),
        "stage_counts": stage_counts,
        "first_stage": cycle_steps[0].get("stage") if cycle_steps else None,
        "last_stage": cycle_steps[-1].get("stage") if cycle_steps else None,
    }

    obj = {
        "summary_type": "bybit_readonly_final_summary",
        "summary_version": "v4",
        "ts_ms": int(time.time() * 1000),
        "project_stage": "D22.4 readonly observer + business-event state integrated",
        "exchange": "bybit",
        "final_status": {
            "readonly_observer_ready": bool(runtime.get("overall_runtime_state") == "ready_readonly_observer"),
            "acceptance_passed": acceptance.get("overall_passed"),
            "system_mode": runtime.get("system_mode"),
            "runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "verdict_code": runtime.get("verdict_code"),
        },
        "safety_status": {
            "execution_disabled": runtime.get("execution_state") == "disabled",
            "ai_disabled_by_policy": runtime.get("ai_state") == "disabled_by_policy",
            "base_mode": "read_only",
            "preflight_guard_allowed": runtime.get("preflight_guard_allowed"),
        },
        "freshness_status": {
            "snapshot_state": runtime.get("snapshot_state"),
            "ws_smoke_state": runtime.get("ws_smoke_state"),
            "ws_runtime_facts_state": runtime.get("ws_runtime_facts_state"),
            "preflight_state": runtime.get("preflight_state"),
            "payload_freshness": runtime.get("payload_freshness") or {},
        },
        "business_event_status": {
            "state_code": runtime.get("business_event_state"),
            "healthy": runtime.get("business_event_healthy"),
            "reason": (runtime.get("business_event_context") or {}).get("reason"),
            "source_stage": (runtime.get("business_event_context") or {}).get("stage"),
        },
        "latest_cycle": latest_cycle_summary,
        "latest_packet": {
            "packet_version": packet.get("packet_version"),
            "ts_ms": packet.get("ts_ms"),
            "risk_flags": packet.get("risk_flags") or [],
            "source_refs": packet.get("source_refs") or {},
        },
        "latest_verdict": {
            "verdict_version": verdict.get("verdict_version"),
            "ts_ms": verdict.get("ts_ms"),
            "verdict_code": verdict.get("verdict_code"),
            "urgency": verdict.get("urgency"),
            "reasons": verdict.get("reasons") or [],
            "next_steps": verdict.get("next_steps") or [],
        },
        "ws_runtime": {
            "facts_version": ws_runtime.get("facts_version"),
            "listener_health": ws_runtime.get("listener_health"),
            "connection_state": ws_runtime.get("connection_state"),
            "signal_strength": ws_runtime.get("signal_strength"),
            "connection_activity_state": ws_runtime.get("connection_activity_state"),
            "business_topic_event_count": ws_runtime.get("business_topic_event_count"),
        },
        "snapshot": {
            "snapshot_version": snapshot.get("snapshot_version"),
            "snapshot_ts_ms": snapshot.get("ts_ms"),
            "payload_time_summary": snapshot.get("payload_time_summary") or {},
        },
        "business_event_state_ref": {
            "state_version": business_event_state.get("state_version"),
            "state_code": business_event_state.get("state_code"),
            "healthy": business_event_state.get("healthy"),
            "ts_ms": business_event_state.get("ts_ms"),
        },
        "policy_reference": {
            "policy_version": failure_policy.get("policy_version"),
            "base_mode": failure_policy.get("base_mode"),
            "hard_stop_conditions_count": len(failure_policy.get("hard_stop_conditions") or []),
            "degrade_conditions_count": len(failure_policy.get("degrade_conditions") or []),
        },
        "completed_capabilities": [
            "private REST readonly account access",
            "private REST readonly positions access",
            "private REST readonly order history access",
            "private REST readonly execution history access",
            "private REST preflight guard",
            "system snapshot generation with payload time summary",
            "snapshot persistence to Postgres",
            "normalized raw snapshot tables",
            "private WebSocket smoke test",
            "persistent private WebSocket listener",
            "WebSocket runtime facts generation",
            "decision packet v4 generation",
            "observer verdict v4 generation",
            "acceptance v4",
            "runtime state v5",
            "readonly consistency audit",
            "business event state classification",
        ],
        "not_yet_enabled": [
            "live execution",
            "demo/paper execution gate",
            "AI-driven trade decisioning",
            "autonomous execution",
            "persistent business-event-driven trading logic",
        ]
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")

if __name__ == "__main__":
    main()
