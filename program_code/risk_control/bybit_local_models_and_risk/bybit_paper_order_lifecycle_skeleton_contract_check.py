#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_paper_order_lifecycle_skeleton_contract_check.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K1/K3 支撑层 / paper order lifecycle
- 这一层的白话解释:
  定义 paper order 生命周期语义，但当前不是可运行订单系统。

Role:
- 校验本脚本对应输出文件的结构、版本与基础字段是否稳定。

Purpose in system:
- 防止 K 章脚本在后续维护时发生结构漂移，给 summary / handoff / final audit 提供稳定上游。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 K 章内定义/校验 contract check 层

Historical note:
- 开发过程中曾临时标为 G5.4
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

CHECK_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_paper_order_lifecycle_skeleton_latest.json")

OUT_DIR = CHECK_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_paper_order_lifecycle_skeleton_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_paper_order_lifecycle_skeleton_contract_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main():
    report = load_json(CHECK_PATH)
    graph = report.get("lifecycle_graph", {})
    nodes = graph.get("state_nodes")
    edges = graph.get("state_edges")

    checks = []
    checks.append(check("lifecycle_exists", CHECK_PATH.exists(), str(CHECK_PATH)))
    checks.append(check("lifecycle_type_expected", report.get("lifecycle_type") == "bybit_paper_order_lifecycle_skeleton", report.get("lifecycle_type")))
    checks.append(check("lifecycle_version_v1", report.get("lifecycle_version") == "v1", report.get("lifecycle_version")))
    checks.append(check("stage_g5_4", report.get("stage") == "G5.4", report.get("stage")))
    checks.append(check("exchange_bybit", report.get("exchange") == "bybit", report.get("exchange")))
    checks.append(check("lifecycle_state_expected", report.get("lifecycle_state") == "skeleton_defined_not_active", report.get("lifecycle_state")))
    checks.append(check("lifecycle_ready_false", report.get("lifecycle_ready") is False, report.get("lifecycle_ready")))
    checks.append(check("lifecycle_can_accept_new_orders_false", report.get("lifecycle_can_accept_new_orders") is False, report.get("lifecycle_can_accept_new_orders")))

    checks.append(check("source_refs_present", isinstance(report.get("source_refs"), dict), type(report.get("source_refs")).__name__))
    checks.append(check("runtime_safety_context_present", isinstance(report.get("runtime_safety_context"), dict), type(report.get("runtime_safety_context")).__name__))
    checks.append(check("adapter_context_present", isinstance(report.get("adapter_context"), dict), type(report.get("adapter_context")).__name__))
    checks.append(check("demo_gate_context_present", isinstance(report.get("demo_gate_context"), dict), type(report.get("demo_gate_context")).__name__))
    checks.append(check("lifecycle_graph_present", isinstance(graph, dict), type(graph).__name__))
    checks.append(check("state_nodes_list", isinstance(nodes, list), type(nodes).__name__))
    checks.append(check("state_edges_list", isinstance(edges, list), type(edges).__name__))
    checks.append(check("state_nodes_nonempty", isinstance(nodes, list) and len(nodes) >= 5, len(nodes) if isinstance(nodes, list) else None))
    checks.append(check("state_edges_nonempty", isinstance(edges, list) and len(edges) >= 4, len(edges) if isinstance(edges, list) else None))
    checks.append(check("lifecycle_summary_present", isinstance(report.get("lifecycle_summary"), dict), type(report.get("lifecycle_summary")).__name__))
    checks.append(check("lifecycle_explainer_present", isinstance(report.get("lifecycle_explainer"), dict), type(report.get("lifecycle_explainer")).__name__))
    checks.append(check("operator_guidance_list", isinstance(report.get("operator_guidance"), list), type(report.get("operator_guidance")).__name__))

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "report_type": "bybit_paper_order_lifecycle_skeleton_contract_check",
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
