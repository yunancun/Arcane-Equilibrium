#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_acceptance_suite.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G4.1 acceptance suite
- 这一层的白话解释:
  把 G1/G2/G3 的关键验证结果统一收口成一份 acceptance suite，
  用来判断“非空业务事件路径”与“负向阻断路径”是否都保持正确。

Role:
- 汇总 fixture / replay / positive-path / negative-path / runtime protection 结果
- 输出一份可回归、可审计的 acceptance suite latest

Purpose in system:
- 给 G 章正式收口提供统一验收输出
- 防止后续修改脚本时把 non-empty path 或 blocked path 搞坏却没人发现

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内做 acceptance / regression 套件收口
- 输出必须与主 runtime 隔离

Maintenance notes:
- 本脚本只读取已有 latest 文件做验收，不改主 runtime
- 若后续 G2/G3 结果结构变动，需同步更新本脚本检查项
'''
"""

import json
import time
from pathlib import Path

FIXTURE_PACK_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/fixtures/bybit_business_event_fixture_pack_latest.json")
REPLAY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/replay/bybit_business_event_replay_latest.json")
REPLAY_CONTRACT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/replay/bybit_business_event_replay_contract_latest.json")

POS_STATE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_state_latest.json")
POS_PHASE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_phase_latest.json")
POS_INPUT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_input_latest.json")
POS_DECISION_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_decision_latest.json")
POS_OUTCOME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_outcome_latest.json")
POS_CONSISTENCY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_consistency_latest.json")

NEG_FIXTURE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/fixtures_negative/bybit_business_event_negative_fixture_pack_latest.json")
NEG_REPLAY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/replay_negative/bybit_business_event_negative_replay_latest.json")
NEG_REPLAY_CONTRACT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/replay_negative/bybit_business_event_negative_replay_contract_latest.json")

BLOCK_CHAIN_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_block_test/bybit_event_replay_block_transition_consistency_latest.json")
BLOCK_CHAIN_CONTRACT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_block_test/bybit_event_replay_block_chain_contract_latest.json")
BLOCK_STATE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_block_test/bybit_event_replay_block_state_latest.json")
BLOCK_DECISION_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_block_test/bybit_event_replay_block_transition_decision_latest.json")
BLOCK_OUTCOME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_block_test/bybit_event_replay_block_transition_outcome_latest.json")

RUNTIME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/validation")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_business_event_acceptance_suite_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def add_check(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def save_report(report):
    ts_ms = report["ts_ms"]
    dated = OUT_DIR / f"bybit_business_event_acceptance_suite_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    ts_ms = int(time.time() * 1000)
    checks = []

    required_paths = {
        "fixture_pack": FIXTURE_PACK_PATH,
        "replay": REPLAY_PATH,
        "replay_contract": REPLAY_CONTRACT_PATH,
        "pos_state": POS_STATE_PATH,
        "pos_phase": POS_PHASE_PATH,
        "pos_input": POS_INPUT_PATH,
        "pos_decision": POS_DECISION_PATH,
        "pos_outcome": POS_OUTCOME_PATH,
        "pos_consistency": POS_CONSISTENCY_PATH,
        "neg_fixture": NEG_FIXTURE_PATH,
        "neg_replay": NEG_REPLAY_PATH,
        "neg_replay_contract": NEG_REPLAY_CONTRACT_PATH,
        "block_chain": BLOCK_CHAIN_PATH,
        "block_chain_contract": BLOCK_CHAIN_CONTRACT_PATH,
        "block_state": BLOCK_STATE_PATH,
        "block_decision": BLOCK_DECISION_PATH,
        "block_outcome": BLOCK_OUTCOME_PATH,
        "runtime": RUNTIME_PATH,
    }

    missing = []
    for key, path in required_paths.items():
        exists = path.exists()
        add_check(checks, f"{key}_exists", exists, str(path))
        if not exists:
            missing.append(key)

    if missing:
        report = {
            "report_type": "bybit_business_event_acceptance_suite",
            "report_version": "v1",
            "ts_ms": ts_ms,
            "exchange": "bybit",
            "stage": "G4.1",
            "overall_ok": False,
            "failed_count": sum(1 for x in checks if not x["ok"]),
            "checks": checks,
            "failed_checks": [x for x in checks if not x["ok"]],
            "reason": "required upstream files missing",
            "missing_keys": missing,
        }
        dated = save_report(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"saved_latest={OUT_LATEST}")
        print(f"saved_dated={dated}")
        return

    fixture = load_json(FIXTURE_PACK_PATH)
    replay = load_json(REPLAY_PATH)
    replay_contract = load_json(REPLAY_CONTRACT_PATH)

    pos_state = load_json(POS_STATE_PATH)
    pos_phase = load_json(POS_PHASE_PATH)
    pos_input = load_json(POS_INPUT_PATH)
    pos_decision = load_json(POS_DECISION_PATH)
    pos_outcome = load_json(POS_OUTCOME_PATH)
    pos_consistency = load_json(POS_CONSISTENCY_PATH)

    neg_fixture = load_json(NEG_FIXTURE_PATH)
    neg_replay = load_json(NEG_REPLAY_PATH)
    neg_replay_contract = load_json(NEG_REPLAY_CONTRACT_PATH)

    block_chain = load_json(BLOCK_CHAIN_PATH)
    block_chain_contract = load_json(BLOCK_CHAIN_CONTRACT_PATH)
    block_state = load_json(BLOCK_STATE_PATH)
    block_decision = load_json(BLOCK_DECISION_PATH)
    block_outcome = load_json(BLOCK_OUTCOME_PATH)

    runtime = load_json(RUNTIME_PATH)

    topic_counts = replay.get("topic_counts", {})
    add_check(checks, "fixture_count_ge_4", fixture.get("fixture_count", 0) >= 4, fixture.get("fixture_count"))
    add_check(checks, "replay_contract_ok", replay_contract.get("overall_ok") is True, replay_contract.get("failed_count"))
    add_check(checks, "replay_has_business_events_true", replay.get("has_business_events") is True, replay.get("has_business_events"))
    add_check(checks, "replay_normalized_count_ge_4", replay.get("normalized_count", 0) >= 4, replay.get("normalized_count"))
    add_check(checks, "replay_required_topics_present",
              all(topic_counts.get(k, 0) > 0 for k in ["wallet", "order", "execution", "position"]),
              topic_counts)

    add_check(checks, "positive_state_event_flow_present",
              pos_state.get("event_driven_readiness") == "event_flow_present",
              pos_state.get("event_driven_readiness"))
    add_check(checks, "positive_phase_ready",
              pos_phase.get("phase_code") == "observer_event_flow_seen" and pos_phase.get("phase_ready") is True,
              {"phase_code": pos_phase.get("phase_code"), "phase_ready": pos_phase.get("phase_ready")})
    add_check(checks, "positive_input_ready",
              pos_input.get("transition_readiness") == "input_ready_for_transition_engine" and pos_input.get("transition_allowed") is True,
              {"transition_readiness": pos_input.get("transition_readiness"), "transition_allowed": pos_input.get("transition_allowed")})
    add_check(checks, "positive_decision_allow",
              pos_decision.get("decision_code") == "allow_transition_engine" and pos_decision.get("decision_allowed") is True,
              {"decision_code": pos_decision.get("decision_code"), "decision_allowed": pos_decision.get("decision_allowed")})
    add_check(checks, "positive_outcome_allowed",
              pos_outcome.get("outcome_code") == "transition_engine_entry_allowed" and pos_outcome.get("outcome_ok") is True,
              {"outcome_code": pos_outcome.get("outcome_code"), "outcome_ok": pos_outcome.get("outcome_ok")})
    add_check(checks, "positive_consistency_ok", pos_consistency.get("overall_ok") is True, pos_consistency.get("failed_count"))

    neg_topic_counts = neg_replay.get("topic_counts", {})
    add_check(checks, "negative_fixture_wallet_only",
              neg_fixture.get("fixture_count") == 1 and neg_fixture.get("topic_counts", {}).get("wallet") == 1,
              {"fixture_count": neg_fixture.get("fixture_count"), "topic_counts": neg_fixture.get("topic_counts", {})})
    add_check(checks, "negative_replay_contract_ok", neg_replay_contract.get("overall_ok") is True, neg_replay_contract.get("failed_count"))
    add_check(checks, "negative_replay_wallet_only",
              neg_replay.get("normalized_count") == 1 and neg_topic_counts.get("wallet") == 1,
              {"normalized_count": neg_replay.get("normalized_count"), "topic_counts": neg_topic_counts})
    add_check(checks, "negative_replay_missing_order_execution_position",
              neg_topic_counts.get("order", 0) == 0 and neg_topic_counts.get("execution", 0) == 0 and neg_topic_counts.get("position", 0) == 0,
              neg_topic_counts)

    add_check(checks, "block_chain_contract_ok", block_chain_contract.get("overall_ok") is True, block_chain_contract.get("failed_count"))
    add_check(checks, "block_consistency_ok", block_chain.get("overall_ok") is True, block_chain.get("failed_count"))
    add_check(checks, "block_state_not_ready", block_state.get("event_driven_readiness") == "not_ready", block_state.get("event_driven_readiness"))
    add_check(checks, "block_decision_blocked",
              block_decision.get("decision_code") == "block_transition_engine" and block_decision.get("decision_allowed") is False,
              {"decision_code": block_decision.get("decision_code"), "decision_allowed": block_decision.get("decision_allowed")})
    add_check(checks, "block_outcome_blocked",
              block_outcome.get("outcome_code") == "transition_engine_blocked" and block_outcome.get("outcome_ok") is True,
              {"outcome_code": block_outcome.get("outcome_code"), "outcome_ok": block_outcome.get("outcome_ok")})

    add_check(checks, "runtime_still_read_only", runtime.get("system_mode") == "read_only", runtime.get("system_mode"))
    add_check(checks, "runtime_execution_disabled", runtime.get("execution_state") == "disabled", runtime.get("execution_state"))
    add_check(checks, "runtime_business_event_empty_unchanged",
              runtime.get("business_event_state") == "healthy_no_business_events_yet" and runtime.get("business_event_healthy") is True,
              {"business_event_state": runtime.get("business_event_state"), "business_event_healthy": runtime.get("business_event_healthy")})

    overall_ok = all(x["ok"] for x in checks)

    report = {
        "report_type": "bybit_business_event_acceptance_suite",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "G4.1",
        "overall_ok": overall_ok,
        "failed_count": sum(1 for x in checks if not x["ok"]),
        "checks": checks,
        "failed_checks": [x for x in checks if not x["ok"]],
        "summary": {
            "positive_nonempty_path_verified": all(
                x["ok"] for x in checks if x["name"].startswith("positive_")
            ),
            "negative_blocked_path_verified": all(
                x["ok"] for x in checks if x["name"].startswith("negative_") or x["name"].startswith("block_")
            ),
            "runtime_protection_preserved": all(
                x["ok"] for x in checks if x["name"].startswith("runtime_")
            ),
            "required_topics_seen_in_positive_replay": topic_counts,
            "required_topics_seen_in_negative_replay": neg_topic_counts,
        },
    }

    dated = save_report(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
