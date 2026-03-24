#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_state_graph_contract_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J2. transition executor skeleton / state graph
- 这一层的白话解释:
  定义 transition state graph 骨架，但当前不是可执行的 transition executor。

Role:
- 校验本脚本对应输出文件的结构、版本与基础字段是否稳定。

Purpose in system:
- 防止 J 章脚本在后续维护时发生结构漂移，给 summary / handoff / final audit / checkpoint 提供稳定上游。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 contract check 层
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

GRAPH_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_state_graph_latest.json")

OUT_DIR = GRAPH_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_transition_state_graph_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_transition_state_graph_contract_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main():
    graph = load_json(GRAPH_PATH)
    checks = []

    checks.append(check("graph_exists", GRAPH_PATH.exists(), str(GRAPH_PATH)))
    checks.append(check("graph_type_expected", graph.get("graph_type") == "bybit_transition_state_graph", graph.get("graph_type")))
    checks.append(check("graph_version_v1", graph.get("graph_version") == "v1", graph.get("graph_version")))
    checks.append(check("exchange_bybit", graph.get("exchange") == "bybit", graph.get("exchange")))
    checks.append(check("stage_g4_7", graph.get("stage") == "G4.7", graph.get("stage")))
    checks.append(check("graph_status_allowed", graph.get("graph_status") in {"skeleton_graph_ready", "graph_not_ready"}, graph.get("graph_status")))

    nodes = graph.get("graph_nodes")
    edges = graph.get("graph_edges")
    closed_paths = graph.get("closed_paths")
    summary = graph.get("graph_summary", {})
    constraints = graph.get("current_constraints", {})

    checks.append(check("graph_nodes_list", isinstance(nodes, list), type(nodes).__name__))
    checks.append(check("graph_edges_list", isinstance(edges, list), type(edges).__name__))
    checks.append(check("closed_paths_list", isinstance(closed_paths, list), type(closed_paths).__name__))
    checks.append(check("node_count_ge_5", isinstance(nodes, list) and len(nodes) >= 5, 0 if not isinstance(nodes, list) else len(nodes)))
    checks.append(check("edge_count_ge_4", isinstance(edges, list) and len(edges) >= 4, 0 if not isinstance(edges, list) else len(edges)))

    checks.append(check("positive_path_mapped_present", summary.get("positive_path_mapped") is True, summary.get("positive_path_mapped")))
    checks.append(check("negative_path_mapped_present", summary.get("negative_path_mapped") is True, summary.get("negative_path_mapped")))
    checks.append(check("execution_path_closed_true", summary.get("execution_path_closed") is True, summary.get("execution_path_closed")))
    checks.append(check("demo_gate_open_false", summary.get("demo_gate_open") is False, summary.get("demo_gate_open")))
    checks.append(check("live_execution_open_false", summary.get("live_execution_open") is False, summary.get("live_execution_open")))

    checks.append(check("system_mode_read_only", constraints.get("system_mode") == "read_only", constraints.get("system_mode")))
    checks.append(check("execution_state_disabled", constraints.get("execution_state") == "disabled", constraints.get("execution_state")))
    checks.append(check("business_event_state_present", constraints.get("business_event_state") is not None, constraints.get("business_event_state")))

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "report_type": "bybit_transition_state_graph_contract_check",
        "report_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
