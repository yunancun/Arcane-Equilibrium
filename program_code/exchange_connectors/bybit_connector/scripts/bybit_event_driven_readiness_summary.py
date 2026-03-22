#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_readiness_summary.py

Role:
- 汇总 D23.1 ~ D23.6 的 event-driven 子链结果
- 生成一个适合人工查看与后续模块读取的 readiness summary

Purpose in system:
- 给维护者一个总览入口，不必分别打开 state / phase / input / decision / outcome / consistency
- 为未来 D23 后续模块提供统一摘要输入

Current scope:
- D23.1 bybit_event_driven_state
- D23.2 bybit_event_driven_phase
- D23.3 bybit_event_transition_input
- D23.4 bybit_event_transition_decision
- D23.5 bybit_event_transition_outcome
- D23.6 bybit_event_driven_chain_consistency_check

Maintenance notes:
- 当前 empty-but-healthy 是正常状态
- 不要把 healthy_but_empty / keep_observe_only / observe_only_retained 误判为失败
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

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_driven_readiness_summary_latest.json"


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

    readiness_ok = all([
        state.get("event_driven_readiness") in ["healthy_but_empty", "event_flow_present"],
        phase.get("phase_code") in ["observer_only_empty_feed", "observer_event_flow_seen"],
        input_obj.get("transition_readiness") in ["input_ready_but_empty", "input_ready_for_transition_engine"],
        decision.get("decision_code") in ["keep_observe_only", "allow_transition_engine"],
        outcome.get("outcome_code") in ["observe_only_retained", "transition_engine_entry_allowed"],
        consistency.get("overall_ok") is True,
    ])

    result = {
        "summary_type": "bybit_event_driven_readiness_summary",
        "summary_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "D23.7",
        "readiness_ok": readiness_ok,
        "current_mode": "observe_only_retained" if outcome.get("outcome_code") == "observe_only_retained" else "transition_path_open",
        "high_level_reason": outcome.get("outcome_reason"),
        "state_layer": {
            "state_version": state.get("state_version"),
            "event_driven_readiness": state.get("event_driven_readiness"),
            "has_business_events": state.get("has_business_events"),
            "normalized_count": state.get("normalized_count"),
        },
        "phase_layer": {
            "phase_version": phase.get("phase_version"),
            "phase_code": phase.get("phase_code"),
            "phase_ready": phase.get("phase_ready"),
            "phase_reason": phase.get("phase_reason"),
        },
        "input_layer": {
            "input_version": input_obj.get("input_version"),
            "transition_readiness": input_obj.get("transition_readiness"),
            "transition_allowed": input_obj.get("transition_allowed"),
            "transition_reason": input_obj.get("transition_reason"),
        },
        "decision_layer": {
            "decision_version": decision.get("decision_version"),
            "decision_code": decision.get("decision_code"),
            "decision_allowed": decision.get("decision_allowed"),
            "decision_reason": decision.get("decision_reason"),
        },
        "outcome_layer": {
            "outcome_version": outcome.get("outcome_version"),
            "outcome_code": outcome.get("outcome_code"),
            "outcome_ok": outcome.get("outcome_ok"),
            "outcome_reason": outcome.get("outcome_reason"),
        },
        "consistency_layer": {
            "report_version": consistency.get("report_version"),
            "overall_ok": consistency.get("overall_ok"),
            "failed_count": consistency.get("failed_count"),
        },
        "summary_explainer": {
            "observe_only_retained": "事件驱动子链健康，但暂无真实业务事件，系统继续保持观察态",
            "transition_path_open": "事件驱动子链已具备推进条件，可进入下一层 transition engine 设计",
        }
    }

    OUT_LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")


if __name__ == "__main__":
    main()
