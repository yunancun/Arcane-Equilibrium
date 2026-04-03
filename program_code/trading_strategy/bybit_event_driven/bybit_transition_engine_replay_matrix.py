#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_replay_matrix.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J4. transition replay
- 这一层的白话解释:
  把正向 replay 路径和负向 replay 路径做成统一矩阵，用来证明 transition skeleton 的语义成立。

Role:
- 生成本脚本对应的 J 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 J. Transition Engine Skeleton 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 transition replay matrix
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.1
- 该临时编号现已废弃
- 后续以 Revision 2 正式章节树为准

Maintenance notes:
- 本批修正只改头部注释归位，不改文件名、latest 路径、JSON stage 字段
- 如后续要改 stage / 输出字段，必须单独做兼容性修订
\'\'\'
"""
import json
import time
from pathlib import Path
import os

POS_DECISION_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_decision_latest.json")
POS_OUTCOME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_outcome_latest.json")

NEG_DECISION_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_block_test/bybit_event_replay_block_transition_decision_latest.json")
NEG_OUTCOME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_block_test/bybit_event_replay_block_transition_outcome_latest.json")

RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_transition_engine_replay_matrix_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_engine_replay_matrix_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)

    pos_decision = load_json(POS_DECISION_PATH)
    pos_outcome = load_json(POS_OUTCOME_PATH)
    neg_decision = load_json(NEG_DECISION_PATH)
    neg_outcome = load_json(NEG_OUTCOME_PATH)
    runtime = load_json(RUNTIME_PATH)

    readonly_ok = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    positive_candidate_open = (
        pos_decision.get("decision_code") == "allow_transition_engine"
        and pos_decision.get("decision_allowed") is True
        and pos_outcome.get("outcome_code") == "transition_engine_entry_allowed"
        and pos_outcome.get("outcome_ok") is True
    )

    negative_candidate_blocked = (
        neg_decision.get("decision_code") == "block_transition_engine"
        and neg_decision.get("decision_allowed") is False
        and neg_outcome.get("outcome_code") == "transition_engine_blocked"
        and neg_outcome.get("outcome_ok") is True
    )

    report = {
        "report_type": "bybit_transition_engine_replay_matrix",
        "report_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "J",
        "engine_mode": "simulation_only_skeleton",
        "system_context": {
            "system_mode": runtime.get("system_mode"),
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "execution_state": runtime.get("execution_state"),
            "ai_state": runtime.get("ai_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
        },
        "safety_boundaries": {
            "readonly_required": True,
            "execution_allowed": False,
            "demo_gate_open": False,
            "live_execution_open": False,
            "readonly_context_ok": readonly_ok,
        },
        "positive_replay_path": {
            "source_decision_ts_ms": pos_decision.get("ts_ms"),
            "source_outcome_ts_ms": pos_outcome.get("ts_ms"),
            "decision_code": pos_decision.get("decision_code"),
            "decision_allowed": pos_decision.get("decision_allowed"),
            "outcome_code": pos_outcome.get("outcome_code"),
            "outcome_ok": pos_outcome.get("outcome_ok"),
            "transition_candidate_state": "candidate_transition_open" if positive_candidate_open else "candidate_transition_unknown",
            "candidate_available": bool(positive_candidate_open),
            "execution_still_forbidden": True,
            "reason": "positive replay path reached transition-engine-entry-allowed semantics under isolated replay validation",
        },
        "negative_replay_path": {
            "source_decision_ts_ms": neg_decision.get("ts_ms"),
            "source_outcome_ts_ms": neg_outcome.get("ts_ms"),
            "decision_code": neg_decision.get("decision_code"),
            "decision_allowed": neg_decision.get("decision_allowed"),
            "outcome_code": neg_outcome.get("outcome_code"),
            "outcome_ok": neg_outcome.get("outcome_ok"),
            "transition_candidate_state": "candidate_transition_blocked" if negative_candidate_blocked else "candidate_transition_unknown",
            "candidate_available": False,
            "execution_still_forbidden": True,
            "reason": "negative replay path remained blocked because event set was incomplete",
        },
        "matrix_verdict": {
            "positive_path_open": positive_candidate_open,
            "negative_path_blocked": negative_candidate_blocked,
            "readonly_context_ok": readonly_ok,
            "matrix_ok": bool(positive_candidate_open and negative_candidate_blocked and readonly_ok),
        },
        "next_transition_engine_goals": [
            "define formal transition-engine input schema",
            "add rule-layer separation between candidate-open and candidate-blocked",
            "add transition audit trail per evaluation",
            "keep execution forbidden until demo/paper gate is explicitly implemented"
        ],
        "matrix_explainer": {
            "candidate_transition_open": "正向 replay 已证明 transition candidate 可达，但此时仍不允许 execution",
            "candidate_transition_blocked": "负向 replay 已证明不完整业务事件会被阻断",
            "simulation_only_skeleton": "当前只是 transition engine 骨架验证，并非可执行交易模块"
        }
    }

    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
