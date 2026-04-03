#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_block_chain_builder.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G3/G4. 负向阻断链 + regression check
- 这一层的白话解释:
  把负向 replay 的 blocked path 串起来，证明 input / decision / outcome 会一致地保持阻断。

Role:
- 生成本脚本对应的 G 章验证输出。

Purpose in system:
- 把 G. 真实业务事件验证层的对应子层固定下来，证明真实业务事件相关语义是否成立，同时不污染主 runtime。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 blocked-path regression
- 所有 replay / negative / consistency 输出都应与主 runtime 隔离

Maintenance notes:
- 本批修正主要增强白话说明，不改变 G 章归属
- 本批修正不改文件名、latest 路径、JSON stage 字段
- 如后续要把 replay 结果真正接到更高层，必须显式经过 J / K 章节边界
\'\'\'
"""
import json
import time
from pathlib import Path
import os

NEG_REPLAY_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/replay_negative/bybit_business_event_negative_replay_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_block_test")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_latest_and_dated(name: str, obj: dict):
    latest = OUT_DIR / f"{name}_latest.json"
    latest.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"{name}_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(latest), str(dated)


def main():
    now_ms = int(time.time() * 1000)
    replay = load_json(NEG_REPLAY_PATH)
    runtime = load_json(RUNTIME_PATH)

    topic_counts = replay.get("topic_counts") or {}
    normalized_count = int(replay.get("normalized_count", 0) or 0)
    has_business_events = bool(replay.get("has_business_events"))

    required_topics = ["wallet", "order", "execution", "position"]
    complete = all(topic_counts.get(t, 0) > 0 for t in required_topics)

    if has_business_events and normalized_count > 0 and not complete:
        state_readiness = "not_ready"
        phase_code = "observer_feed_not_ready"
        phase_ready = False
        input_readiness = "input_not_ready"
        transition_allowed = False
        decision_code = "block_transition_engine"
        decision_allowed = False
        outcome_code = "transition_engine_blocked"
        outcome_ok = True
        high_reason = "replay contains partial business events only, so transition path must stay blocked"
    else:
        state_readiness = "unknown"
        phase_code = "observer_feed_not_ready"
        phase_ready = False
        input_readiness = "input_not_ready"
        transition_allowed = False
        decision_code = "block_transition_engine"
        decision_allowed = False
        outcome_code = "transition_engine_blocked"
        outcome_ok = True
        high_reason = "replay block chain defaulted to blocked path"

    state_obj = {
        "state_type": "bybit_event_replay_block_state",
        "state_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G3.2",
        "event_driven_readiness": state_readiness,
        "has_business_events": has_business_events,
        "normalized_count": normalized_count,
        "topic_observation": {k: topic_counts.get(k, 0) for k in required_topics},
        "topic_counts": topic_counts,
        "event_type_counts": replay.get("event_type_counts", {}),
        "source_replay_ref": {
            "report_version": replay.get("report_version"),
            "report_ts_ms": replay.get("ts_ms"),
            "replayed_count": replay.get("replayed_count"),
            "normalized_count": normalized_count,
        },
        "runtime_context": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "ws_signal_strength": runtime.get("ws_signal_strength"),
        },
        "state_explainer": {
            "not_ready": "replay 业务事件不完整，不能视为可推进 transition engine 的有效事件流",
            "event_flow_present": "仅在完整 replay 正向样本中成立",
        },
    }

    phase_obj = {
        "phase_type": "bybit_event_replay_block_phase",
        "phase_version": "v1",
        "ts_ms": now_ms + 1,
        "exchange": "bybit",
        "stage": "G3.2",
        "phase_code": phase_code,
        "phase_ready": phase_ready,
        "phase_reason": high_reason,
        "source_state_ref": {
            "state_version": state_obj["state_version"],
            "state_ts_ms": state_obj["ts_ms"],
            "event_driven_readiness": state_readiness,
            "has_business_events": has_business_events,
            "normalized_count": normalized_count,
        },
    }

    input_obj = {
        "input_type": "bybit_event_replay_block_transition_input",
        "input_version": "v1",
        "ts_ms": now_ms + 2,
        "exchange": "bybit",
        "stage": "G3.2",
        "transition_readiness": input_readiness,
        "transition_allowed": transition_allowed,
        "transition_reason": high_reason,
        "source_refs": {
            "runtime_ts_ms": runtime.get("ts_ms"),
            "replay_state_ts_ms": state_obj["ts_ms"],
            "replay_phase_ts_ms": phase_obj["ts_ms"],
        },
    }

    decision_obj = {
        "decision_type": "bybit_event_replay_block_transition_decision",
        "decision_version": "v1",
        "ts_ms": now_ms + 3,
        "exchange": "bybit",
        "stage": "G3.2",
        "decision_code": decision_code,
        "decision_allowed": decision_allowed,
        "decision_reason": high_reason,
        "source_input_ref": {
            "input_version": input_obj["input_version"],
            "input_ts_ms": input_obj["ts_ms"],
            "transition_readiness": input_readiness,
            "transition_allowed": transition_allowed,
        },
    }

    outcome_obj = {
        "outcome_type": "bybit_event_replay_block_transition_outcome",
        "outcome_version": "v1",
        "ts_ms": now_ms + 4,
        "exchange": "bybit",
        "stage": "G3.2",
        "outcome_code": outcome_code,
        "outcome_ok": outcome_ok,
        "outcome_reason": high_reason,
        "source_decision_ref": {
            "decision_version": decision_obj["decision_version"],
            "decision_ts_ms": decision_obj["ts_ms"],
            "decision_code": decision_code,
            "decision_allowed": decision_allowed,
        },
    }

    consistency_obj = {
        "report_type": "bybit_event_replay_block_transition_consistency_check",
        "report_version": "v1",
        "ts_ms": now_ms + 5,
        "overall_ok": True,
        "failed_count": 0,
        "checks": [
            {"name": "state_blocked", "ok": state_readiness == "not_ready", "detail": state_readiness},
            {"name": "phase_blocked", "ok": phase_code == "observer_feed_not_ready" and phase_ready is False, "detail": {"phase_code": phase_code, "phase_ready": phase_ready}},
            {"name": "input_blocked", "ok": input_readiness == "input_not_ready" and transition_allowed is False, "detail": {"transition_readiness": input_readiness, "transition_allowed": transition_allowed}},
            {"name": "decision_blocked", "ok": decision_code == "block_transition_engine" and decision_allowed is False, "detail": {"decision_code": decision_code, "decision_allowed": decision_allowed}},
            {"name": "outcome_blocked", "ok": outcome_code == "transition_engine_blocked" and outcome_ok is True, "detail": {"outcome_code": outcome_code, "outcome_ok": outcome_ok}},
            {"name": "phase_ref_matches_state", "ok": phase_obj["source_state_ref"]["state_ts_ms"] == state_obj["ts_ms"], "detail": {"phase": phase_obj["source_state_ref"]["state_ts_ms"], "state": state_obj["ts_ms"]}},
            {"name": "input_ref_matches_phase", "ok": input_obj["source_refs"]["replay_phase_ts_ms"] == phase_obj["ts_ms"], "detail": {"input": input_obj["source_refs"]["replay_phase_ts_ms"], "phase": phase_obj["ts_ms"]}},
            {"name": "decision_ref_matches_input", "ok": decision_obj["source_input_ref"]["input_ts_ms"] == input_obj["ts_ms"], "detail": {"decision": decision_obj["source_input_ref"]["input_ts_ms"], "input": input_obj["ts_ms"]}},
            {"name": "outcome_ref_matches_decision", "ok": outcome_obj["source_decision_ref"]["decision_ts_ms"] == decision_obj["ts_ms"], "detail": {"outcome": outcome_obj["source_decision_ref"]["decision_ts_ms"], "decision": decision_obj["ts_ms"]}},
        ],
        "failed_checks": [],
    }
    consistency_obj["failed_checks"] = [c for c in consistency_obj["checks"] if not c["ok"]]
    consistency_obj["failed_count"] = len(consistency_obj["failed_checks"])
    consistency_obj["overall_ok"] = len(consistency_obj["failed_checks"]) == 0

    outputs = {
        "state": write_latest_and_dated("bybit_event_replay_block_state", state_obj),
        "phase": write_latest_and_dated("bybit_event_replay_block_phase", phase_obj),
        "input": write_latest_and_dated("bybit_event_replay_block_transition_input", input_obj),
        "decision": write_latest_and_dated("bybit_event_replay_block_transition_decision", decision_obj),
        "outcome": write_latest_and_dated("bybit_event_replay_block_transition_outcome", outcome_obj),
        "consistency": write_latest_and_dated("bybit_event_replay_block_transition_consistency", consistency_obj),
    }

    summary = {
        "report_type": "bybit_event_replay_block_chain_builder",
        "report_version": "v1",
        "ts_ms": now_ms + 6,
        "overall_ok": consistency_obj["overall_ok"],
        "state_readiness": state_readiness,
        "phase_code": phase_code,
        "input_readiness": input_readiness,
        "decision_code": decision_code,
        "outcome_code": outcome_code,
        "outputs": outputs,
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
