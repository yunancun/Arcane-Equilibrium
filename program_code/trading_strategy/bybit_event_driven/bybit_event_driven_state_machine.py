#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_state_machine.py

NOTE: Despite the name, this module performs classification-only (not stateful transitions).
It reads current state from files and classifies into phase codes without maintaining state memory.
注意：尽管名为 state_machine，本模块仅做分类（非有状态转换）。
它从文件读取当前状态并分类为 phase code，不维护状态记忆。

Role:
- 基于 bybit_event_driven_state_latest.json 做轻量状态机判定
- 输出 event-driven phase / phase readiness / next action hint

Purpose in system:
- 这是 D23.2 的状态机骨架
- 先把”事件驱动是否真的进入可推进阶段”单独表达出来
- 暂不涉及执行、不涉及下单，只做 phase classification

Current intended phases:
- observer_only_empty_feed
- observer_event_flow_seen
- observer_feed_not_ready

Downstream (future):
- 更完整的 event-driven state transition engine
- demo/paper gate
- pretrade risk gate
- AI gating / routing

Maintenance notes:
- healthy_but_empty 不是错误，而是健康空态
- 只有真的出现 business events，才进入 observer_event_flow_seen
'''
"""

import json
import time
from pathlib import Path
import os

EVENT_DRIVEN_STATE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_state_latest.json")
RUNTIME_STATE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")
OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_LATEST = OUT_DIR / "bybit_event_driven_phase_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_event_driven_phase_{ts_ms}.json"
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)

    state = load_json(EVENT_DRIVEN_STATE_PATH)
    runtime = load_json(RUNTIME_STATE_PATH)

    readiness = state.get("event_driven_readiness", "not_ready")
    has_business_events = bool(state.get("has_business_events", False))
    normalized_count = int(state.get("normalized_count", 0) or 0)
    runtime_state = runtime.get("overall_runtime_state")
    business_event_healthy = bool(state.get("business_event_healthy", False))

    if readiness == "event_flow_present" and has_business_events and normalized_count > 0:
        phase_code = "observer_event_flow_seen"
        phase_ready = True
        phase_reason = "real business-topic events are present and event-driven phase can advance later"
    elif readiness == "healthy_but_empty" and business_event_healthy:
        phase_code = "observer_only_empty_feed"
        phase_ready = False
        phase_reason = "event-driven feed is healthy but still empty"
    else:
        phase_code = "observer_feed_not_ready"
        phase_ready = False
        phase_reason = "event-driven feed is not trustworthy enough for downstream transitions"

    result = {
        "phase_type": "bybit_event_driven_phase",
        "phase_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "D23.2",
        "phase_code": phase_code,
        "phase_ready": phase_ready,
        "phase_reason": phase_reason,
        "source_state_ref": {
            "state_version": state.get("state_version"),
            "state_ts_ms": state.get("ts_ms"),
            "event_driven_readiness": readiness,
            "business_event_state_code": state.get("business_event_state_code"),
            "has_business_events": has_business_events,
            "normalized_count": normalized_count,
        },
        "runtime_context": {
            "overall_runtime_state": runtime_state,
            "observer_state": runtime.get("observer_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "ws_signal_strength": runtime.get("ws_signal_strength"),
        },
        "state_machine_hint": {
            "allow_future_transition_engine": phase_code == "observer_event_flow_seen",
            "allow_demo_gate_consideration": False,
            "allow_live_execution": False,
        },
        "phase_explainer": {
            "observer_only_empty_feed": "事件驱动链路健康但为空，只能继续观察，不能进入交易态",
            "observer_event_flow_seen": "已观察到真实业务事件，可作为后续事件驱动状态机输入",
            "observer_feed_not_ready": "事件驱动侧当前不可信，不能用于下游推进",
        }
    }

    dated = save_json(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
