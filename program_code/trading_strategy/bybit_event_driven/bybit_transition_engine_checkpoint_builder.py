#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_checkpoint_builder.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章阶段收口 / checkpoint
- 这一层的白话解释:
  把 J 章各层结果打包成 checkpoint，作为后续 K 章继续施工的基线。

Role:
- 生成本脚本对应的 J 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 J. Transition Engine Skeleton 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 checkpoint 层
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.9
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

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine")

MATRIX_PATH = BASE / "bybit_transition_engine_replay_matrix_latest.json"
AUDIT_PATH = BASE / "bybit_transition_engine_audit_trail_latest.json"
RULE_PATH = BASE / "bybit_transition_rule_layer_latest.json"
SUMMARY_PATH = BASE / "bybit_transition_engine_summary_latest.json"
HANDOFF_PATH = BASE / "bybit_transition_engine_handoff_latest.json"
FINAL_AUDIT_PATH = BASE / "bybit_transition_engine_final_audit_latest.json"
GRAPH_PATH = BASE / "bybit_transition_state_graph_latest.json"
GRAPH_CONSISTENCY_PATH = BASE / "bybit_transition_state_graph_consistency_latest.json"
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = BASE
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_transition_engine_checkpoint_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_transition_engine_checkpoint_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    matrix = load_json(MATRIX_PATH)
    audit = load_json(AUDIT_PATH)
    rule = load_json(RULE_PATH)
    summary = load_json(SUMMARY_PATH)
    handoff = load_json(HANDOFF_PATH)
    final_audit = load_json(FINAL_AUDIT_PATH)
    graph = load_json(GRAPH_PATH)
    graph_consistency = load_json(GRAPH_CONSISTENCY_PATH)
    runtime = load_json(RUNTIME_PATH)

    matrix_verdict = matrix.get("matrix_verdict", {})
    trail_summary = audit.get("trail_summary", {})
    rule_summary = rule.get("layer_summary", {})
    final_status = summary.get("final_status", {})
    current_status = handoff.get("current_status", {})
    graph_summary = graph.get("graph_summary", {})

    readonly_lock_ok = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    checkpoint_ready = all([
        matrix_verdict.get("matrix_ok") is True,
        trail_summary.get("trail_ok") is True,
        rule_summary.get("skeleton_rules_ready") is True,
        final_status.get("transition_engine_skeleton_ready") is True,
        current_status.get("transition_engine_skeleton_ready") is True,
        final_audit.get("overall_ok") is True,
        graph_summary.get("graph_ready") is True,
        graph_consistency.get("overall_ok") is True,
        readonly_lock_ok,
    ])

    obj = {
        "checkpoint_type": "bybit_transition_engine_checkpoint",
        "checkpoint_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "J",
        "revision_tree_context": {
            "section": "J",
            "subsection": "J",
            "section_meaning": "Transition Engine Skeleton",
            "current_focus": "transition engine checkpoint pack",
        },
        "checkpoint_status": "skeleton_checkpoint_ready" if checkpoint_ready else "checkpoint_not_ready",
        "runtime_safety_context": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "system_mode": runtime.get("system_mode"),
            "observer_state": runtime.get("observer_state"),
            "execution_state": runtime.get("execution_state"),
            "ai_state": runtime.get("ai_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "readonly_lock_ok": readonly_lock_ok,
        },
        "source_refs": {
            "matrix_version": matrix.get("report_version"),
            "matrix_ts_ms": matrix.get("ts_ms"),
            "audit_version": audit.get("audit_version"),
            "audit_ts_ms": audit.get("ts_ms"),
            "rule_layer_version": rule.get("layer_version"),
            "rule_layer_ts_ms": rule.get("ts_ms"),
            "summary_version": summary.get("summary_version"),
            "summary_ts_ms": summary.get("ts_ms"),
            "handoff_version": handoff.get("handoff_version"),
            "handoff_ts_ms": handoff.get("ts_ms"),
            "final_audit_version": final_audit.get("audit_version"),
            "final_audit_ts_ms": final_audit.get("ts_ms"),
            "graph_version": graph.get("graph_version"),
            "graph_ts_ms": graph.get("ts_ms"),
            "graph_consistency_version": graph_consistency.get("report_version"),
            "graph_consistency_ts_ms": graph_consistency.get("ts_ms"),
            "runtime_state_version": runtime.get("state_version"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "checkpoint_layers": {
            "matrix_layer": {
                "matrix_ok": matrix_verdict.get("matrix_ok"),
                "positive_path_open": matrix_verdict.get("positive_path_open"),
                "negative_path_blocked": matrix_verdict.get("negative_path_blocked"),
                "readonly_context_ok": matrix_verdict.get("readonly_context_ok"),
            },
            "audit_layer": {
                "trail_ok": trail_summary.get("trail_ok"),
                "positive_case_open": trail_summary.get("positive_case_open"),
                "negative_case_blocked": trail_summary.get("negative_case_blocked"),
                "execution_forbidden_confirmed": trail_summary.get("execution_forbidden_confirmed"),
            },
            "rule_layer": {
                "skeleton_rules_ready": rule_summary.get("skeleton_rules_ready"),
                "positive_candidate_recognized": rule_summary.get("positive_candidate_recognized"),
                "negative_candidate_blocked": rule_summary.get("negative_candidate_blocked"),
                "execution_still_forbidden": rule_summary.get("execution_still_forbidden"),
            },
            "summary_layer": {
                "transition_engine_skeleton_ready": final_status.get("transition_engine_skeleton_ready"),
                "candidate_transition_supported": final_status.get("candidate_transition_supported"),
                "negative_blocking_supported": final_status.get("negative_blocking_supported"),
                "execution_permitted": final_status.get("execution_permitted"),
                "demo_gate_open": final_status.get("demo_gate_open"),
                "live_execution_open": final_status.get("live_execution_open"),
            },
            "handoff_layer": {
                "transition_engine_skeleton_ready": current_status.get("transition_engine_skeleton_ready"),
                "candidate_transition_supported": current_status.get("candidate_transition_supported"),
                "negative_blocking_supported": current_status.get("negative_blocking_supported"),
                "execution_permitted": current_status.get("execution_permitted"),
                "demo_gate_open": current_status.get("demo_gate_open"),
                "live_execution_open": current_status.get("live_execution_open"),
            },
            "final_audit_layer": {
                "overall_ok": final_audit.get("overall_ok"),
                "failed_count": final_audit.get("failed_count"),
                "total_checks": final_audit.get("total_checks"),
            },
            "graph_layer": {
                "graph_ready": graph_summary.get("graph_ready"),
                "positive_path_mapped": graph_summary.get("positive_path_mapped"),
                "negative_path_mapped": graph_summary.get("negative_path_mapped"),
                "execution_path_closed": graph_summary.get("execution_path_closed"),
                "demo_gate_open": graph_summary.get("demo_gate_open"),
                "live_execution_open": graph_summary.get("live_execution_open"),
            },
            "graph_consistency_layer": {
                "overall_ok": graph_consistency.get("overall_ok"),
                "failed_count": graph_consistency.get("failed_count"),
            },
        },
        "checkpoint_conclusion": {
            "positive_candidate_path_proven_in_isolation": bool(graph_summary.get("positive_path_mapped")),
            "negative_blocking_path_proven_in_isolation": bool(graph_summary.get("negative_path_mapped")),
            "execution_still_forbidden": readonly_lock_ok,
            "demo_gate_still_closed": final_status.get("demo_gate_open") is False,
            "live_execution_still_closed": final_status.get("live_execution_open") is False,
            "checkpoint_ready": checkpoint_ready,
        },
        "operator_guidance": [
            "J 章已经形成可维护的 skeleton checkpoint，可作为后续 K 章的统一起点",
            "当前证明的是 isolated replay 下 candidate transition path 可达，不代表主系统已进入可执行交易阶段",
            "主系统仍必须保持 read_only / execution disabled",
            "下一阶段若进入 G5，应优先设计 demo/paper gate contract，而不是直接碰 live execution",
        ],
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
