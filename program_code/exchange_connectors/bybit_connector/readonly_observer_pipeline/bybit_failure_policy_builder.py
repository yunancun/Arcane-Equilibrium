#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_failure_policy_builder.py
Role:
- 基于当前 runtime / acceptance / verdict / business event state
- 生成 hard stop / degrade policy 说明

Purpose in system:
- 明确什么情况必须停，什么情况只是降级
- 给人工维护和后续自动治理提供策略解释

Current integrated stage:
- 已接入 business event 解释
- 当前版本应为 v3

Maintenance notes:
- healthy_no_business_events_yet 是允许的健康空态
- 不应把它等价成“事件驱动链路已准备好交易”
'''

"""

import json
import sys
import time
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_misc_tools_dir = _script_dir.parent / "misc_tools"
if str(_misc_tools_dir) not in sys.path:
    sys.path.insert(0, str(_misc_tools_dir))
import bybit_path_policy as bpp

RUNTIME_STATE_PATH = bpp.BYBIT_RUNTIME_ROOT / "bybit_runtime_state_latest.json"
ACCEPTANCE_PATH = bpp.BYBIT_RUNTIME_ROOT / "bybit_observer_acceptance_latest.json"
PACKET_PATH = bpp.DECISION_PACKETS_ROOT / "bybit_decision_packet_latest.json"
VERDICT_PATH = bpp.VERDICTS_ROOT / "bybit_observer_verdict_latest.json"
WS_RUNTIME_FACTS_PATH = bpp.BYBIT_RUNTIME_ROOT / "bybit_ws_runtime_facts_latest.json"
PREFLIGHT_PATH = bpp.BYBIT_RUNTIME_ROOT / "bybit_private_rest_preflight_latest.json"
BUSINESS_EVENT_STATE_PATH = bpp.BUSINESS_EVENTS_RUNTIME_DIR / "bybit_business_event_state_latest.json"

OUT_DIR = bpp.BYBIT_RUNTIME_ROOT
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_failure_policy_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_failure_policy_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


def main():
    runtime = load_json(RUNTIME_STATE_PATH)
    acceptance = load_json(ACCEPTANCE_PATH)
    packet = load_json(PACKET_PATH)
    verdict = load_json(VERDICT_PATH)
    ws_runtime = load_json(WS_RUNTIME_FACTS_PATH)
    preflight = load_json(PREFLIGHT_PATH)
    business_event_state = load_json(BUSINESS_EVENT_STATE_PATH)

    obj = {
        "policy_type": "bybit_failure_and_degrade_policy",
        "policy_version": "v3",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "base_mode": "read_only",
        "hard_stop_conditions": [
            {
                "name": "acceptance_failed",
                "condition": "observer acceptance report overall_passed != true",
                "action": "stop pipeline result from being considered healthy"
            },
            {
                "name": "execution_enabled_unexpectedly",
                "condition": "execution_state != disabled while system_mode == read_only",
                "action": "treat as critical configuration violation"
            },
            {
                "name": "ai_enabled_unexpectedly",
                "condition": "ai_state not in ['disabled_by_policy', 'unknown'] while current stage is observer-only",
                "action": "treat as policy violation and force observer-only"
            },
            {
                "name": "preflight_guard_blocked",
                "condition": "preflight_guard_allowed != true",
                "action": "block downstream observer pipeline and require REST revalidation"
            }
        ],
        "degrade_conditions": [
            {
                "name": "snapshot_stale",
                "condition": "snapshot_state != fresh",
                "degrade_to": "refresh_required",
                "action": "refresh private REST snapshot before any higher-level reasoning"
            },
            {
                "name": "ws_smoke_stale",
                "condition": "ws_smoke_state != fresh",
                "degrade_to": "rest_only_observer",
                "action": "continue with REST observer facts, but do not trust recent WS smoke timing"
            },
            {
                "name": "ws_runtime_facts_stale",
                "condition": "ws_runtime_facts_state != fresh",
                "degrade_to": "observer_with_stale_ws_runtime",
                "action": "rebuild ws runtime facts before using WS-derived signal state"
            },
            {
                "name": "ws_control_only_no_business_events",
                "condition": "ws_signal_strength == control_only and business_topic_event_count == 0",
                "degrade_to": "observer_control_only",
                "action": "allow observer mode to continue, but do not promote WS-dependent business logic"
            },
            {
                "name": "no_positions_no_orders_no_executions",
                "condition": "position_count == 0 and order_count == 0 and execution_count == 0",
                "degrade_to": "observe_only_low_urgency",
                "action": "keep urgency low, no AI query, no execution"
            },
            {
                "name": "business_event_feed_missing_or_stale",
                "condition": "business_event_state in ['missing', 'stale_or_missing_business_event_feed', 'unknown']",
                "degrade_to": "observer_without_business_event_confidence",
                "action": "do not rely on business-event side for downstream state transitions"
            },
            {
                "name": "business_event_feed_healthy_but_empty",
                "condition": "business_event_state == healthy_no_business_events_yet",
                "degrade_to": "observer_business_feed_empty",
                "action": "healthy empty feed is allowed, but do not treat it as business-event-ready trading signal flow"
            }
        ],
        "business_event_interpretation": {
            "healthy_no_business_events_yet": "feed is integrated and healthy, but real business-topic events have not appeared yet",
            "healthy_business_events_present": "feed is integrated and healthy, and real business-topic events are being observed",
            "stale_or_missing_business_event_feed": "business-event side is not trustworthy enough for downstream state use"
        },
        "default_safe_actions": [
            "remain in read_only mode",
            "keep execution disabled",
            "keep AI querying disabled unless later policy explicitly enables it",
            "prefer OBSERVE_ONLY over any active behavior",
            "require fresh REST snapshot before nontrivial local verdicts",
            "do not treat healthy empty business-event feed as equivalent to active event-driven readiness"
        ],
        "current_runtime_state": {
            "state_version": runtime.get("state_version"),
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "execution_state": runtime.get("execution_state"),
            "ai_state": runtime.get("ai_state"),
            "snapshot_state": runtime.get("snapshot_state"),
            "ws_smoke_state": runtime.get("ws_smoke_state"),
            "ws_runtime_facts_state": runtime.get("ws_runtime_facts_state"),
            "ws_signal_strength": runtime.get("ws_signal_strength"),
            "preflight_guard_allowed": runtime.get("preflight_guard_allowed"),
            "verdict_code": runtime.get("verdict_code"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
        },
        "current_acceptance": {
            "report_version": acceptance.get("report_version"),
            "overall_passed": acceptance.get("overall_passed"),
            "failed_count": acceptance.get("failed_count")
        },
        "current_packet": {
            "packet_version": packet.get("packet_version"),
            "risk_flags": packet.get("risk_flags", []),
            "should_query_ai": ((packet.get("local_decision_hints") or {}).get("should_query_ai"))
        },
        "current_verdict": {
            "verdict_version": verdict.get("verdict_version"),
            "verdict_code": verdict.get("verdict_code"),
            "urgency": verdict.get("urgency"),
            "should_refresh_rest": verdict.get("should_refresh_rest"),
            "should_query_ai": verdict.get("should_query_ai")
        },
        "current_ws_runtime": {
            "facts_version": ws_runtime.get("facts_version"),
            "listener_health": ws_runtime.get("listener_health"),
            "connection_state": ws_runtime.get("connection_state"),
            "signal_strength": ws_runtime.get("signal_strength"),
            "business_signal_state": ws_runtime.get("business_signal_state"),
            "connection_activity_state": ws_runtime.get("connection_activity_state"),
            "business_topic_event_count": ws_runtime.get("business_topic_event_count")
        },
        "current_preflight": {
            "guard_version": preflight.get("guard_version"),
            "allowed_to_continue": preflight.get("allowed_to_continue"),
            "failed_count": preflight.get("failed_count")
        },
        "current_business_event_state": {
            "state_version": business_event_state.get("state_version"),
            "state_code": business_event_state.get("state_code"),
            "healthy": business_event_state.get("healthy"),
            "reason": business_event_state.get("reason"),
            "stage": business_event_state.get("stage")
        }
    }

    save_json(obj)


if __name__ == "__main__":
    main()
