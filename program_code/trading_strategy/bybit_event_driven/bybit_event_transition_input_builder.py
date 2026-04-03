#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_transition_input_builder.py

Role:
- 汇总 runtime_state / business_event_state / event_driven_state / event_driven_phase
- 生成给未来 transition engine 使用的统一输入包

Purpose in system:
- 这是 D23.3 的过渡层
- 先把多份 latest.json 统一成单一 transition input
- 为后续真正的 event-driven transition engine 做输入标准化

Downstream:
- future transition engine
- future demo/paper gate
- future event-driven audit / consistency checks

Maintenance notes:
- 当前阶段只做输入整合，不做交易决策
- healthy_but_empty / observer_only_empty_feed 属于正常健康空态
'''
"""

import json
import time
from pathlib import Path
import os

RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")
BUSINESS_EVENT_STATE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_state_latest.json")
EVENT_DRIVEN_STATE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_state_latest.json")
EVENT_DRIVEN_PHASE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_phase_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_transition_input_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_event_transition_input_{ts_ms}.json"
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)

    runtime = load_json(RUNTIME_PATH)
    business_event_state = load_json(BUSINESS_EVENT_STATE_PATH)
    event_state = load_json(EVENT_DRIVEN_STATE_PATH)
    phase = load_json(EVENT_DRIVEN_PHASE_PATH)

    runtime_ready = runtime.get("overall_runtime_state") == "ready_readonly_observer"
    business_event_healthy = bool(runtime.get("business_event_healthy"))
    phase_code = phase.get("phase_code")
    phase_ready = bool(phase.get("phase_ready"))
    has_business_events = bool(event_state.get("has_business_events", False))
    normalized_count = int(event_state.get("normalized_count", 0) or 0)

    if runtime_ready and business_event_healthy and phase_code == "observer_only_empty_feed":
        transition_readiness = "input_ready_but_empty"
        transition_allowed = False
        transition_reason = "inputs are healthy and consistent, but no business events exist yet"
    elif runtime_ready and business_event_healthy and phase_code == "observer_event_flow_seen" and has_business_events and normalized_count > 0:
        transition_readiness = "input_ready_for_transition_engine"
        transition_allowed = True
        transition_reason = "inputs are healthy and real business events are available"
    else:
        transition_readiness = "input_not_ready"
        transition_allowed = False
        transition_reason = "one or more required upstream states are not ready or not consistent"

    result = {
        "input_type": "bybit_event_transition_input",
        "input_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "D23.3",
        "transition_readiness": transition_readiness,
        "transition_allowed": transition_allowed,
        "transition_reason": transition_reason,
        "source_refs": {
            "runtime_ts_ms": runtime.get("ts_ms"),
            "business_event_state_ts_ms": business_event_state.get("ts_ms"),
            "event_driven_state_ts_ms": event_state.get("ts_ms"),
            "event_driven_phase_ts_ms": phase.get("ts_ms"),
        },
        "runtime_context": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "ws_signal_strength": runtime.get("ws_signal_strength"),
        },
        "business_event_context": {
            "state_code": business_event_state.get("state_code"),
            "healthy": business_event_state.get("healthy"),
            "reason": business_event_state.get("reason"),
        },
        "event_driven_state_context": {
            "event_driven_readiness": event_state.get("event_driven_readiness"),
            "has_business_events": has_business_events,
            "normalized_count": normalized_count,
            "topic_observation": event_state.get("topic_observation", {}),
        },
        "event_driven_phase_context": {
            "phase_code": phase_code,
            "phase_ready": phase_ready,
            "phase_reason": phase.get("phase_reason"),
        },
        "transition_input_explainer": {
            "input_ready_but_empty": "输入完整且健康，但还没有真实业务事件，不能推进 transition engine",
            "input_ready_for_transition_engine": "输入完整且已看到真实业务事件，可进入后续 transition engine",
            "input_not_ready": "输入层仍存在缺口或状态不一致，不能进入 transition engine",
        }
    }

    dated = save_json(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
