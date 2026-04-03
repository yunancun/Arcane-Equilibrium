#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_state_builder.py

Role:
- 从 business_event_runtime_facts + business_event_state + runtime_state 汇总生成 event-driven state
- 给后续状态机、paper/demo gate、风控层提供统一读取入口

Purpose in system:
- 这是 D23 的第一层骨架
- 先把“事件驱动状态”独立成单独 latest 文件
- 目前不做交易动作，只做状态解释与可维护数据整理

Current output philosophy:
- 如果 business-event feed 健康但为空，也要明确表达
- 如果后续真的出现 wallet/order/execution/position 事件，这里会成为主要聚合入口

Downstream (future):
- event-driven state machine
- demo/paper execution gate
- risk gate
- AI gating / model router

Maintenance notes:
- 这里是未来事件驱动核心入口之一
- 字段改名要同步所有后续使用者
'''
"""

import json
import time
from pathlib import Path
import os

BUSINESS_RUNTIME_FACTS_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_runtime_facts_latest.json")
BUSINESS_EVENT_STATE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_state_latest.json")
RUNTIME_STATE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")
DECISION_PACKET_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json")
VERDICT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/verdicts/bybit/bybit_observer_verdict_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_LATEST = OUT_DIR / "bybit_event_driven_state_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_event_driven_state_{ts_ms}.json"
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)

    business_facts = load_json(BUSINESS_RUNTIME_FACTS_PATH)
    business_state = load_json(BUSINESS_EVENT_STATE_PATH)
    runtime = load_json(RUNTIME_STATE_PATH)
    packet = load_json(DECISION_PACKET_PATH)
    verdict = load_json(VERDICT_PATH)

    topic_counts = business_facts.get("topic_counts") or {}
    event_type_counts = business_facts.get("event_type_counts") or {}

    normalized_count = business_facts.get("normalized_count", 0)
    has_business_events = business_facts.get("has_business_events", False)

    state_code = business_state.get("state_code", "unknown")
    business_healthy = bool(business_state.get("healthy", False))

    observed_wallet = topic_counts.get("wallet", 0)
    observed_order = topic_counts.get("order", 0)
    observed_execution = topic_counts.get("execution", 0)
    observed_position = topic_counts.get("position", 0)

    if state_code == "healthy_business_events_present":
        event_driven_readiness = "event_flow_present"
    elif state_code == "healthy_no_business_events_yet":
        event_driven_readiness = "healthy_but_empty"
    else:
        event_driven_readiness = "not_ready"

    result = {
        "state_type": "bybit_event_driven_state",
        "state_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "D23.1",
        "event_driven_readiness": event_driven_readiness,
        "business_event_state_code": state_code,
        "business_event_healthy": business_healthy,
        "has_business_events": has_business_events,
        "normalized_count": normalized_count,
        "topic_observation": {
            "wallet": observed_wallet,
            "order": observed_order,
            "execution": observed_execution,
            "position": observed_position,
        },
        "topic_counts": topic_counts,
        "event_type_counts": event_type_counts,
        "last_event_ts_ms": business_facts.get("last_event_ts_ms"),
        "last_event_age_ms": business_facts.get("last_event_age_ms"),
        "runtime_context": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "ws_signal_strength": runtime.get("ws_signal_strength"),
        },
        "observer_context": {
            "packet_ts_ms": packet.get("ts_ms"),
            "verdict_ts_ms": verdict.get("ts_ms"),
            "verdict_code": verdict.get("verdict_code"),
            "urgency": verdict.get("urgency"),
        },
        "state_explainer": {
            "event_flow_present": "真实 business-topic 事件已经出现，可作为后续 event-driven 模块输入",
            "healthy_but_empty": "business-event feed 健康，但当前没有真实业务事件",
            "not_ready": "business-event 侧当前不适合作为可靠状态输入",
        }
    }

    dated = save_json(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
