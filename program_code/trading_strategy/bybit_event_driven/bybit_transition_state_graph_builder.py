#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_state_graph_builder.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J2. transition executor skeleton / state graph
- 这一层的白话解释:
  定义 transition state graph 骨架，但当前不是可执行的 transition executor。

Role:
- 生成本脚本对应的 J 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 J. Transition Engine Skeleton 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 state graph 骨架
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.7 / G4.8
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

SUMMARY_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_summary_latest.json")
HANDOFF_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_handoff_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_LATEST = OUT_DIR / "bybit_transition_state_graph_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_transition_state_graph_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    summary = load_json(SUMMARY_PATH)
    handoff = load_json(HANDOFF_PATH)
    runtime = load_json(RUNTIME_PATH)

    final_status = summary.get("final_status", {})
    current_status = handoff.get("current_status", {})

    candidate_transition_supported = bool(final_status.get("candidate_transition_supported"))
    negative_blocking_supported = bool(final_status.get("negative_blocking_supported"))
    execution_permitted = bool(final_status.get("execution_permitted"))
    demo_gate_open = bool(final_status.get("demo_gate_open"))
    live_execution_open = bool(final_status.get("live_execution_open"))

    system_mode = runtime.get("system_mode")
    overall_runtime_state = runtime.get("overall_runtime_state")
    observer_state = runtime.get("observer_state")
    execution_state = runtime.get("execution_state")
    ai_state = runtime.get("ai_state")
    business_event_state = runtime.get("business_event_state")
    business_event_healthy = runtime.get("business_event_healthy")

    graph_nodes = [
        {
            "state_code": "observe_only_locked",
            "meaning": "主系统当前停留在只读观察态，execution 关闭",
            "present_in_main_runtime": True,
            "validated_in_isolation": True,
        },
        {
            "state_code": "candidate_transition_open",
            "meaning": "正向 replay 已证明 candidate transition 在隔离环境中可达",
            "present_in_main_runtime": False,
            "validated_in_isolation": candidate_transition_supported,
        },
        {
            "state_code": "candidate_transition_blocked",
            "meaning": "负向 replay 已证明不完整事件集会被阻断",
            "present_in_main_runtime": False,
            "validated_in_isolation": negative_blocking_supported,
        },
        {
            "state_code": "demo_gate_pending_design",
            "meaning": "后续 demo/paper gate 接入前的挂起设计位",
            "present_in_main_runtime": False,
            "validated_in_isolation": True,
        },
        {
            "state_code": "live_execution_forbidden",
            "meaning": "当前 live execution 仍明确关闭",
            "present_in_main_runtime": True,
            "validated_in_isolation": True,
        },
    ]

    graph_edges = [
        {
            "edge_name": "positive_replay_candidate_path",
            "from_state": "observe_only_locked",
            "to_state": "candidate_transition_open",
            "edge_available": candidate_transition_supported,
            "meaning": "正向 replay 证明 candidate path 可达，但仅限隔离验证上下文",
        },
        {
            "edge_name": "negative_replay_block_path",
            "from_state": "observe_only_locked",
            "to_state": "candidate_transition_blocked",
            "edge_available": negative_blocking_supported,
            "meaning": "负向 replay 证明不完整事件集会停留在 blocked path",
        },
        {
            "edge_name": "candidate_waits_for_demo_gate",
            "from_state": "candidate_transition_open",
            "to_state": "demo_gate_pending_design",
            "edge_available": (candidate_transition_supported and (not demo_gate_open)),
            "meaning": "candidate 已被证明，但 demo/paper gate 尚未打开，所以只能停在待设计阶段",
        },
        {
            "edge_name": "demo_gate_closed_keeps_live_forbidden",
            "from_state": "demo_gate_pending_design",
            "to_state": "live_execution_forbidden",
            "edge_available": (not live_execution_open),
            "meaning": "在 demo/paper gate 和 live gate 都未打开前，execution 必须继续关闭",
        },
    ]

    closed_paths = [
        {
            "path_name": "main_runtime_to_execution",
            "closed": (system_mode == "read_only" and execution_state == "disabled"),
            "reason": "主系统仍处于 read_only，execution 绝对不能开启",
        },
        {
            "path_name": "candidate_to_demo_execution",
            "closed": (not demo_gate_open),
            "reason": "candidate path 已验证，但 demo/paper gate 尚未实现或尚未开放",
        },
        {
            "path_name": "demo_to_live_execution",
            "closed": (not live_execution_open),
            "reason": "live execution gate 仍关闭",
        },
    ]

    graph_summary = {
        "node_count": len(graph_nodes),
        "edge_count": len(graph_edges),
        "positive_path_mapped": candidate_transition_supported,
        "negative_path_mapped": negative_blocking_supported,
        "execution_path_closed": (system_mode == "read_only" and execution_state == "disabled"),
        "demo_gate_open": demo_gate_open,
        "live_execution_open": live_execution_open,
        "graph_ready": (
            candidate_transition_supported
            and negative_blocking_supported
            and (system_mode == "read_only")
            and (execution_state == "disabled")
        ),
    }

    obj = {
        "graph_type": "bybit_transition_state_graph",
        "graph_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "J",
        "revision_tree_context": {
            "section": "J",
            "subsection": "J",
            "section_meaning": "Transition Engine Skeleton",
            "current_focus": "transition state graph skeleton",
        },
        "graph_status": "skeleton_graph_ready" if graph_summary["graph_ready"] else "graph_not_ready",
        "current_constraints": {
            "system_mode": system_mode,
            "overall_runtime_state": overall_runtime_state,
            "observer_state": observer_state,
            "execution_state": execution_state,
            "ai_state": ai_state,
            "business_event_state": business_event_state,
            "business_event_healthy": business_event_healthy,
            "execution_permitted": execution_permitted,
            "demo_gate_open": demo_gate_open,
            "live_execution_open": live_execution_open,
        },
        "source_refs": {
            "summary_version": summary.get("summary_version"),
            "summary_ts_ms": summary.get("ts_ms"),
            "handoff_version": handoff.get("handoff_version"),
            "handoff_ts_ms": handoff.get("ts_ms"),
            "runtime_state_version": runtime.get("state_version"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
        "closed_paths": closed_paths,
        "graph_summary": graph_summary,
        "operator_readme": [
            "当前状态图骨架已经证明：正向 replay candidate path 可达，但仅限隔离验证",
            "当前状态图骨架已经证明：负向 replay blocked path 会正确拦截",
            "当前状态图骨架同时明确：主系统 execution 仍必须保持 forbidden",
            "后续若接入 demo/paper gate，应从 demo_gate_pending_design 节点继续扩展",
        ],
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
