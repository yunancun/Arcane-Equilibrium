#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_chain_consistency_check.py

Role:
- 对 D23.1 ~ D23.5 的 event-driven 链做一致性检查
- 检查 state / phase / input / decision / outcome 之间的引用与语义是否一致

Purpose in system:
- 防止后续人工维护时只改了一层，未同步其他层
- 为未来 transition engine 接入前提供一个稳定的链路完整性检查点

Current scope:
- D23.1 bybit_event_driven_state
- D23.2 bybit_event_driven_phase
- D23.3 bybit_event_transition_input
- D23.4 bybit_event_transition_decision
- D23.5 bybit_event_transition_outcome

Maintenance notes:
- 这是 event-driven 子链的总一致性检查器
- 如果未来版本号升级，记得同步这里的版本断言
'''
"""

import json
import time
from pathlib import Path
import os

STATE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_state_latest.json")
PHASE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_driven_phase_latest.json")
INPUT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_input_latest.json")
DECISION_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_decision_latest.json")
OUTCOME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_outcome_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_driven_chain_consistency_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def add_check(checks, name, ok, detail):
    checks.append({
        "name": name,
        "ok": bool(ok),
        "detail": detail,
    })


def main():
    state = load_json(STATE_PATH)
    phase = load_json(PHASE_PATH)
    input_obj = load_json(INPUT_PATH)
    decision = load_json(DECISION_PATH)
    outcome = load_json(OUTCOME_PATH)

    checks = []

    add_check(checks, "state_exists", STATE_PATH.exists(), str(STATE_PATH))
    add_check(checks, "phase_exists", PHASE_PATH.exists(), str(PHASE_PATH))
    add_check(checks, "input_exists", INPUT_PATH.exists(), str(INPUT_PATH))
    add_check(checks, "decision_exists", DECISION_PATH.exists(), str(DECISION_PATH))
    add_check(checks, "outcome_exists", OUTCOME_PATH.exists(), str(OUTCOME_PATH))

    add_check(checks, "state_version_v1", state.get("state_version") == "v1", state.get("state_version"))
    add_check(checks, "phase_version_v1", phase.get("phase_version") == "v1", phase.get("phase_version"))
    add_check(checks, "input_version_v1", input_obj.get("input_version") == "v1", input_obj.get("input_version"))
    add_check(checks, "decision_version_v1", decision.get("decision_version") == "v1", decision.get("decision_version"))
    add_check(checks, "outcome_version_v1", outcome.get("outcome_version") == "v1", outcome.get("outcome_version"))

    add_check(checks, "state_stage_d23_1", state.get("stage") == "D23.1", state.get("stage"))
    add_check(checks, "phase_stage_d23_2", phase.get("stage") == "D23.2", phase.get("stage"))
    add_check(checks, "input_stage_d23_3", input_obj.get("stage") == "D23.3", input_obj.get("stage"))
    add_check(checks, "decision_stage_d23_4", decision.get("stage") == "D23.4", decision.get("stage"))
    add_check(checks, "outcome_stage_d23_5", outcome.get("stage") == "D23.5", outcome.get("stage"))

    add_check(
        checks,
        "phase_ref_matches_state",
        (phase.get("source_state_ref") or {}).get("state_ts_ms") == state.get("ts_ms"),
        {
            "phase": (phase.get("source_state_ref") or {}).get("state_ts_ms"),
            "state": state.get("ts_ms"),
        },
    )

    input_refs = input_obj.get("source_refs") or {}
    add_check(
        checks,
        "input_ref_matches_state",
        input_refs.get("event_driven_state_ts_ms") == state.get("ts_ms"),
        {
            "input": input_refs.get("event_driven_state_ts_ms"),
            "state": state.get("ts_ms"),
        },
    )
    add_check(
        checks,
        "input_ref_matches_phase",
        input_refs.get("event_driven_phase_ts_ms") == phase.get("ts_ms"),
        {
            "input": input_refs.get("event_driven_phase_ts_ms"),
            "phase": phase.get("ts_ms"),
        },
    )

    add_check(
        checks,
        "decision_ref_matches_input",
        (decision.get("source_input_ref") or {}).get("input_ts_ms") == input_obj.get("ts_ms"),
        {
            "decision": (decision.get("source_input_ref") or {}).get("input_ts_ms"),
            "input": input_obj.get("ts_ms"),
        },
    )

    add_check(
        checks,
        "outcome_ref_matches_decision",
        (outcome.get("source_decision_ref") or {}).get("decision_ts_ms") == decision.get("ts_ms"),
        {
            "outcome": (outcome.get("source_decision_ref") or {}).get("decision_ts_ms"),
            "decision": decision.get("ts_ms"),
        },
    )

    add_check(
        checks,
        "state_to_phase_semantics",
        not (
            state.get("event_driven_readiness") == "healthy_but_empty"
            and phase.get("phase_code") != "observer_only_empty_feed"
        ),
        {
            "state_readiness": state.get("event_driven_readiness"),
            "phase_code": phase.get("phase_code"),
        },
    )

    add_check(
        checks,
        "phase_to_input_semantics",
        not (
            phase.get("phase_code") == "observer_only_empty_feed"
            and input_obj.get("transition_readiness") != "input_ready_but_empty"
        ),
        {
            "phase_code": phase.get("phase_code"),
            "input_readiness": input_obj.get("transition_readiness"),
        },
    )

    add_check(
        checks,
        "input_to_decision_semantics",
        not (
            input_obj.get("transition_readiness") == "input_ready_but_empty"
            and decision.get("decision_code") != "keep_observe_only"
        ),
        {
            "input_readiness": input_obj.get("transition_readiness"),
            "decision_code": decision.get("decision_code"),
        },
    )

    add_check(
        checks,
        "decision_to_outcome_semantics",
        not (
            decision.get("decision_code") == "keep_observe_only"
            and outcome.get("outcome_code") != "observe_only_retained"
        ),
        {
            "decision_code": decision.get("decision_code"),
            "outcome_code": outcome.get("outcome_code"),
        },
    )

    failed = [c for c in checks if not c["ok"]]

    result = {
        "report_type": "bybit_event_driven_chain_consistency_check",
        "report_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    OUT_LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")


if __name__ == "__main__":
    main()
