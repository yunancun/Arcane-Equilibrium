#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_next_phase_handoff.py
Role:
- 生成“当前阶段完成什么、下一步做什么”的交接文件

Purpose in system:
- 给未来维护者/开发者提供清晰 handoff
- 说明当前边界、限制、建议路线

Current integrated stage:
- 已接入 business event 状态和 policy 解释
- 当前版本应为 v3

Maintenance notes:
- handoff 偏“阶段说明”，不是严格契约校验器
- 改 version 后务必同步 audit
'''

"""

import json
import time
from pathlib import Path

RUNTIME_STATE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")
FAILURE_POLICY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_failure_policy_latest.json")
BUSINESS_EVENT_STATE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_state_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_next_phase_handoff_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_next_phase_handoff_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


def main():
    runtime = load_json(RUNTIME_STATE_PATH)
    policy = load_json(FAILURE_POLICY_PATH)
    business_event_state = load_json(BUSINESS_EVENT_STATE_PATH)

    obj = {
        "handoff_type": "bybit_next_phase_handoff",
        "handoff_version": "v3",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "current_stage_complete": "D22.5 readonly observer + business-event policy/handoff integrated",
        "current_status": {
            "readonly_observer_ready": bool(runtime.get("acceptance_passed") and runtime.get("overall_runtime_state") == "ready_readonly_observer"),
            "system_mode": runtime.get("system_mode"),
            "runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "execution_state": runtime.get("execution_state"),
            "ai_state": runtime.get("ai_state"),
            "verdict_code": runtime.get("verdict_code"),
            "ws_listener_health": runtime.get("ws_listener_health"),
            "ws_signal_strength": runtime.get("ws_signal_strength"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy")
        },
        "business_event_status": {
            "state_code": business_event_state.get("state_code"),
            "healthy": business_event_state.get("healthy"),
            "reason": business_event_state.get("reason"),
            "source_stage": business_event_state.get("stage")
        },
        "hard_safety_boundaries": [
            "keep system_mode as read_only until demo/paper stage is explicitly implemented and validated",
            "do not enable execution while readonly acceptance remains the primary health gate",
            "do not enable AI-driven trade decisioning before compute governance and query budget controls are implemented",
            "do not treat WS control-plane activity as equivalent to business-event signal readiness",
            "do not treat healthy empty business-event feed as equivalent to active event-driven trading readiness"
        ],
        "recommended_next_build_order": [
            "1. persistent business-event ingestion model",
            "2. event-driven state updater from WS into runtime facts",
            "3. latest-file consistency auditor / contract checker",
            "4. AI query budget and governance layer",
            "5. model router v2",
            "6. demo/paper execution gate",
            "7. supervised live trading gate"
        ],
        "minimum_requirements_before_demo_paper": [
            "persistent WebSocket business-event processing",
            "freshness-aware event/state reconciliation",
            "idempotent event ingestion",
            "explicit paper execution adapter",
            "pretrade risk gate integrated with simulator",
            "audit trail for every simulated action",
            "AI invocation budget enforcement"
        ],
        "known_current_limitations": [
            "business-event feed is structurally integrated but no real business-topic events have been observed yet",
            "no event-driven state transitions yet",
            "no live execution",
            "no demo/paper execution gate",
            "no AI-driven trade decisioning",
            "no autonomous execution"
        ],
        "policy_reference": {
            "policy_version": policy.get("policy_version"),
            "base_mode": policy.get("base_mode"),
            "hard_stop_conditions_count": len(policy.get("hard_stop_conditions", [])),
            "degrade_conditions_count": len(policy.get("degrade_conditions", []))
        },
        "operator_message": "Current system is production-grade readonly observer infrastructure with business-event state classification, not trading execution infrastructure."
    }

    save_json(obj)


if __name__ == "__main__":
    main()
