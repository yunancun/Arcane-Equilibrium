#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_driven_final_audit.py

Role:
- 对 D23 event-driven 全链路做最终总审计
- 检查 state / phase / input / decision / outcome / consistency / readiness / handoff / contracts

Purpose in system:
- 作为 D23 阶段的总体验收器
- 防止某个子脚本单独通过，但整条链版本、语义、引用关系出现漂移

Upstream:
- bybit_event_driven_state_builder.py
- bybit_event_driven_state_machine.py
- bybit_event_transition_input_builder.py
- bybit_event_transition_decider.py
- bybit_event_transition_outcome_builder.py
- bybit_event_driven_chain_consistency_check.py
- bybit_event_driven_readiness_summary.py
- bybit_event_driven_handoff.py
- 以及对应 contract_check 脚本

Output:
- bybit_event_driven_final_audit_latest.json

Maintenance notes:
- 这是 D23 的总审计，不负责生成业务状态
- 如果这里失败，应优先看 failed_checks，再回溯对应上游 latest 文件
'''
"""

import json
import time
from pathlib import Path
import os

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven")

STATE_PATH = BASE / "bybit_event_driven_state_latest.json"
STATE_CONTRACT_PATH = BASE / "bybit_event_driven_state_contract_latest.json"

PHASE_PATH = BASE / "bybit_event_driven_phase_latest.json"
PHASE_CONTRACT_PATH = BASE / "bybit_event_driven_phase_contract_latest.json"

INPUT_PATH = BASE / "bybit_event_transition_input_latest.json"
INPUT_CONTRACT_PATH = BASE / "bybit_event_transition_input_contract_latest.json"

DECISION_PATH = BASE / "bybit_event_transition_decision_latest.json"
DECISION_CONTRACT_PATH = BASE / "bybit_event_transition_decision_contract_latest.json"

OUTCOME_PATH = BASE / "bybit_event_transition_outcome_latest.json"
OUTCOME_CONTRACT_PATH = BASE / "bybit_event_transition_outcome_contract_latest.json"

CHAIN_PATH = BASE / "bybit_event_driven_chain_consistency_latest.json"
CHAIN_CONTRACT_PATH = BASE / "bybit_event_driven_chain_contract_latest.json"

READINESS_PATH = BASE / "bybit_event_driven_readiness_summary_latest.json"
READINESS_CONTRACT_PATH = BASE / "bybit_event_driven_readiness_contract_latest.json"

HANDOFF_PATH = BASE / "bybit_event_driven_handoff_latest.json"
HANDOFF_CONTRACT_PATH = BASE / "bybit_event_driven_handoff_contract_latest.json"

OUT_LATEST = BASE / "bybit_event_driven_final_audit_latest.json"
OUT_PREFIX = BASE / "bybit_event_driven_final_audit_"


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
    state_contract = load_json(STATE_CONTRACT_PATH)

    phase = load_json(PHASE_PATH)
    phase_contract = load_json(PHASE_CONTRACT_PATH)

    input_obj = load_json(INPUT_PATH)
    input_contract = load_json(INPUT_CONTRACT_PATH)

    decision = load_json(DECISION_PATH)
    decision_contract = load_json(DECISION_CONTRACT_PATH)

    outcome = load_json(OUTCOME_PATH)
    outcome_contract = load_json(OUTCOME_CONTRACT_PATH)

    chain = load_json(CHAIN_PATH)
    chain_contract = load_json(CHAIN_CONTRACT_PATH)

    readiness = load_json(READINESS_PATH)
    readiness_contract = load_json(READINESS_CONTRACT_PATH)

    handoff = load_json(HANDOFF_PATH)
    handoff_contract = load_json(HANDOFF_CONTRACT_PATH)

    checks = []

    # existence
    for name, path in [
        ("state_exists", STATE_PATH),
        ("state_contract_exists", STATE_CONTRACT_PATH),
        ("phase_exists", PHASE_PATH),
        ("phase_contract_exists", PHASE_CONTRACT_PATH),
        ("input_exists", INPUT_PATH),
        ("input_contract_exists", INPUT_CONTRACT_PATH),
        ("decision_exists", DECISION_PATH),
        ("decision_contract_exists", DECISION_CONTRACT_PATH),
        ("outcome_exists", OUTCOME_PATH),
        ("outcome_contract_exists", OUTCOME_CONTRACT_PATH),
        ("chain_exists", CHAIN_PATH),
        ("chain_contract_exists", CHAIN_CONTRACT_PATH),
        ("readiness_exists", READINESS_PATH),
        ("readiness_contract_exists", READINESS_CONTRACT_PATH),
        ("handoff_exists", HANDOFF_PATH),
        ("handoff_contract_exists", HANDOFF_CONTRACT_PATH),
    ]:
        add_check(checks, name, path.exists(), str(path))

    # contract pass checks
    add_check(checks, "state_contract_ok", state_contract.get("overall_ok") is True, state_contract.get("overall_ok"))
    add_check(checks, "phase_contract_ok", phase_contract.get("overall_ok") is True, phase_contract.get("overall_ok"))
    add_check(checks, "input_contract_ok", input_contract.get("overall_ok") is True, input_contract.get("overall_ok"))
    add_check(checks, "decision_contract_ok", decision_contract.get("overall_ok") is True, decision_contract.get("overall_ok"))
    add_check(checks, "outcome_contract_ok", outcome_contract.get("overall_ok") is True, outcome_contract.get("overall_ok"))
    add_check(checks, "chain_contract_ok", chain_contract.get("overall_ok") is True, chain_contract.get("overall_ok"))
    add_check(checks, "readiness_contract_ok", readiness_contract.get("overall_ok") is True, readiness_contract.get("overall_ok"))
    add_check(checks, "handoff_contract_ok", handoff_contract.get("overall_ok") is True, handoff_contract.get("overall_ok"))

    # semantic chain
    add_check(
        checks,
        "state_to_phase_semantic",
        state.get("event_driven_readiness") == "healthy_but_empty" and phase.get("phase_code") == "observer_only_empty_feed",
        {
            "state_readiness": state.get("event_driven_readiness"),
            "phase_code": phase.get("phase_code"),
        },
    )

    add_check(
        checks,
        "phase_to_input_semantic",
        phase.get("phase_code") == "observer_only_empty_feed" and input_obj.get("transition_readiness") == "input_ready_but_empty",
        {
            "phase_code": phase.get("phase_code"),
            "input_readiness": input_obj.get("transition_readiness"),
        },
    )

    add_check(
        checks,
        "input_to_decision_semantic",
        input_obj.get("transition_readiness") == "input_ready_but_empty" and decision.get("decision_code") == "keep_observe_only",
        {
            "input_readiness": input_obj.get("transition_readiness"),
            "decision_code": decision.get("decision_code"),
        },
    )

    add_check(
        checks,
        "decision_to_outcome_semantic",
        decision.get("decision_code") == "keep_observe_only" and outcome.get("outcome_code") == "observe_only_retained",
        {
            "decision_code": decision.get("decision_code"),
            "outcome_code": outcome.get("outcome_code"),
        },
    )

    add_check(
        checks,
        "readiness_mode_matches_outcome",
        readiness.get("current_mode") == outcome.get("outcome_code"),
        {
            "readiness_mode": readiness.get("current_mode"),
            "outcome_code": outcome.get("outcome_code"),
        },
    )

    add_check(
        checks,
        "handoff_mode_matches_readiness",
        handoff.get("current_status", {}).get("current_mode") == readiness.get("current_mode"),
        {
            "handoff_mode": handoff.get("current_status", {}).get("current_mode"),
            "readiness_mode": readiness.get("current_mode"),
        },
    )

    add_check(
        checks,
        "chain_consistency_ok",
        chain.get("overall_ok") is True,
        chain.get("overall_ok"),
    )

    ts_ms = int(time.time() * 1000)
    failed = [c for c in checks if not c["ok"]]

    result = {
        "audit_type": "bybit_event_driven_final_audit",
        "audit_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed,
    }

    OUT_LATEST.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = Path(str(OUT_PREFIX) + f"{ts_ms}.json")
    dated.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
