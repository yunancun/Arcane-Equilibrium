#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_handoff.py

Role:
- 汇总 D23 event-driven 子链当前状态
- 输出给人工维护 / 下一阶段开发使用的 handoff 摘要

Purpose in system:
- 让维护者快速知道 event-driven 子链是否已经 ready
- 给 D23 后续 / D24 提供明确的阶段交接信息

Upstream:
- bybit_event_driven_state_builder.py
- bybit_event_driven_state_machine.py
- bybit_event_transition_input_builder.py
- bybit_event_transition_decider.py
- bybit_event_transition_outcome_builder.py
- bybit_event_driven_chain_consistency_check.py
- bybit_event_driven_readiness_summary.py

Maintenance notes:
- 当前 healthy-but-empty / observe_only_retained 是正常状态
- 不应把“空但健康”误写成故障
'''
"""

import json
import time
from pathlib import Path

STATE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_state_latest.json")
PHASE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_phase_latest.json")
INPUT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_input_latest.json")
DECISION_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_decision_latest.json")
OUTCOME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_outcome_latest.json")
CONSISTENCY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_chain_consistency_latest.json")
SUMMARY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_readiness_summary_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_driven_handoff_latest.json"
OUT_DATED_PREFIX = OUT_DIR / "bybit_event_driven_handoff_"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    state = load_json(STATE_PATH)
    phase = load_json(PHASE_PATH)
    input_obj = load_json(INPUT_PATH)
    decision = load_json(DECISION_PATH)
    outcome = load_json(OUTCOME_PATH)
    consistency = load_json(CONSISTENCY_PATH)
    summary = load_json(SUMMARY_PATH)

    ts_ms = int(time.time() * 1000)

    result = {
        "handoff_type": "bybit_event_driven_handoff",
        "handoff_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "D23.8",
        "current_status": {
            "readiness_ok": summary.get("readiness_ok"),
            "current_mode": summary.get("current_mode"),
            "high_level_reason": summary.get("high_level_reason"),
            "consistency_ok": consistency.get("overall_ok"),
        },
        "state_layer": {
            "event_driven_readiness": state.get("event_driven_readiness"),
            "has_business_events": state.get("has_business_events"),
            "normalized_count": state.get("normalized_count"),
        },
        "phase_layer": {
            "phase_code": phase.get("phase_code"),
            "phase_ready": phase.get("phase_ready"),
            "phase_reason": phase.get("phase_reason"),
        },
        "input_layer": {
            "transition_readiness": input_obj.get("transition_readiness"),
            "transition_allowed": input_obj.get("transition_allowed"),
            "transition_reason": input_obj.get("transition_reason"),
        },
        "decision_layer": {
            "decision_code": decision.get("decision_code"),
            "decision_allowed": decision.get("decision_allowed"),
            "decision_reason": decision.get("decision_reason"),
        },
        "outcome_layer": {
            "outcome_code": outcome.get("outcome_code"),
            "outcome_ok": outcome.get("outcome_ok"),
            "outcome_reason": outcome.get("outcome_reason"),
        },
        "operator_guidance": [
            "当前 event-driven 子链健康，但仍未看到真实 business-topic 事件",
            "可以继续扩展 transition engine，但不能把当前状态当成可交易事件流已就绪",
            "若后续开始出现 wallet/order/execution/position 真实事件，应优先检查 D23.1 ~ D23.8 全链语义是否同步变化",
        ],
        "next_recommended_build_order": [
            "1. transition engine skeleton",
            "2. event-driven state transition rules",
            "3. transition audit trail",
            "4. demo/paper gate integration",
        ],
        "known_limitations": [
            "business-event feed healthy but empty",
            "no real business-topic event flow yet",
            "no transition engine yet",
            "no demo/paper execution integration yet",
            "no live execution path",
        ],
    }

    OUT_LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = Path(str(OUT_DATED_PREFIX) + f"{ts_ms}.json")
    dated_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
