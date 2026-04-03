#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_transition_consistency_check.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G4. acceptance / regression / consistency
- 这一层的白话解释:
  对正向 replay 链做一致性回归校验，确保 state / phase / input / decision / outcome 语义联动正确。

Role:
- 生成本脚本对应的 G 章验证输出。

Purpose in system:
- 把 G. 真实业务事件验证层的对应子层固定下来，证明真实业务事件相关语义是否成立，同时不污染主 runtime。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 replay harness
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

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test")

STATE_PATH = BASE / "bybit_event_replay_state_latest.json"
PHASE_PATH = BASE / "bybit_event_replay_phase_latest.json"
INPUT_PATH = BASE / "bybit_event_replay_transition_input_latest.json"
DECISION_PATH = BASE / "bybit_event_replay_transition_decision_latest.json"
OUTCOME_PATH = BASE / "bybit_event_replay_transition_outcome_latest.json"

OUT_LATEST = BASE / "bybit_event_replay_transition_consistency_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(obj: dict, latest_path: Path, dated_prefix: str) -> Path:
    latest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = latest_path.parent / f"{dated_prefix}_{obj['ts_ms']}.json"
    dated_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated_path


def main():
    now_ms = int(time.time() * 1000)

    state = load_json(STATE_PATH)
    phase = load_json(PHASE_PATH)
    inp = load_json(INPUT_PATH)
    decision = load_json(DECISION_PATH)
    outcome = load_json(OUTCOME_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("state_positive", state.get("event_driven_readiness") == "event_flow_present", state.get("event_driven_readiness"))
    add("phase_positive", phase.get("phase_code") == "observer_event_flow_seen" and phase.get("phase_ready") is True, {"phase_code": phase.get("phase_code"), "phase_ready": phase.get("phase_ready")})
    add("input_positive", inp.get("transition_readiness") == "input_ready_for_transition_engine" and inp.get("transition_allowed") is True, {"transition_readiness": inp.get("transition_readiness"), "transition_allowed": inp.get("transition_allowed")})
    add("decision_positive", decision.get("decision_code") == "allow_transition_engine" and decision.get("decision_allowed") is True, {"decision_code": decision.get("decision_code"), "decision_allowed": decision.get("decision_allowed")})
    add("outcome_positive", outcome.get("outcome_code") == "transition_engine_entry_allowed" and outcome.get("outcome_ok") is True, {"outcome_code": outcome.get("outcome_code"), "outcome_ok": outcome.get("outcome_ok")})

    add("phase_ref_matches_state", phase.get("source_state_ref", {}).get("state_ts_ms") == state.get("ts_ms"), {"phase": phase.get("source_state_ref", {}).get("state_ts_ms"), "state": state.get("ts_ms")})
    add("input_ref_matches_phase", inp.get("source_refs", {}).get("replay_phase_ts_ms") == phase.get("ts_ms"), {"input": inp.get("source_refs", {}).get("replay_phase_ts_ms"), "phase": phase.get("ts_ms")})
    add("decision_ref_matches_input", decision.get("source_input_ref", {}).get("input_ts_ms") == inp.get("ts_ms"), {"decision": decision.get("source_input_ref", {}).get("input_ts_ms"), "input": inp.get("ts_ms")})
    add("outcome_ref_matches_decision", outcome.get("source_decision_ref", {}).get("decision_ts_ms") == decision.get("ts_ms"), {"outcome": outcome.get("source_decision_ref", {}).get("decision_ts_ms"), "decision": decision.get("ts_ms")})

    failed = [c for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_event_replay_transition_consistency_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    dated = save_report(report, OUT_LATEST, "bybit_event_replay_transition_consistency")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
