#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_paper_position_balance_projection_skeleton_builder.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K4. paper accounting 支撑层
- 这一层的白话解释:
  定义 paper position / balance projection 骨架，但当前没有真实 ledger 计算能力。

Role:
- 生成本脚本对应的 K 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 K. Paper / Demo Gate 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 K 章内定义/校验 projection 骨架

Historical note:
- 开发过程中曾临时标为 G5.5
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

LIFECYCLE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_paper_order_lifecycle_skeleton_latest.json")
ADAPTER_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_paper_adapter_skeleton_latest.json")
READINESS_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_readiness_latest.json")
RUNTIME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_paper_position_balance_projection_skeleton_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_paper_position_balance_projection_skeleton_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    lifecycle = load_json(LIFECYCLE_PATH)
    adapter = load_json(ADAPTER_PATH)
    readiness = load_json(READINESS_PATH)
    runtime = load_json(RUNTIME_PATH)

    readonly_lock_ok = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    projection_surface = {
        "project_balance_after_fill": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper fill settlement model is not ready yet",
        },
        "project_position_after_fill": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper position projection model is not ready yet",
        },
        "project_fee_and_cash_impact": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper fee model is not ready yet",
        },
        "project_order_reservation_and_release": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper reservation / release model is not ready yet",
        },
        "reconcile_projection_with_paper_snapshot": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper snapshot reconciliation is not ready yet",
        },
    }

    obj = {
        "projection_type": "bybit_paper_position_balance_projection_skeleton",
        "projection_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "G5.5",
        "revision_tree_context": {
            "section": "G5",
            "subsection": "G5.5",
            "section_meaning": "demo/paper gate 设计层",
            "current_focus": "paper position / balance projection skeleton",
        },
        "projection_state": "skeleton_defined_not_active",
        "projection_ready": False,
        "projection_can_drive_paper_ledger": False,
        "projection_reason": "projection surface is defined, but lifecycle/adapter/readiness are still inactive and demo gate remains closed",
        "source_refs": {
            "lifecycle_version": lifecycle.get("lifecycle_version"),
            "lifecycle_ts_ms": lifecycle.get("ts_ms"),
            "adapter_version": adapter.get("adapter_version"),
            "adapter_ts_ms": adapter.get("ts_ms"),
            "readiness_version": readiness.get("readiness_version"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "runtime_state_version": runtime.get("state_version"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
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
        "adapter_context": {
            "adapter_state": adapter.get("adapter_state"),
            "adapter_active": adapter.get("adapter_active"),
            "adapter_ready": adapter.get("adapter_ready"),
            "adapter_can_accept_orders": adapter.get("adapter_can_accept_orders"),
        },
        "lifecycle_context": {
            "lifecycle_state": lifecycle.get("lifecycle_state"),
            "lifecycle_ready": lifecycle.get("lifecycle_ready"),
            "lifecycle_can_accept_new_orders": lifecycle.get("lifecycle_can_accept_new_orders"),
            "state_count": lifecycle.get("lifecycle_summary", {}).get("state_count"),
            "edge_count": lifecycle.get("lifecycle_summary", {}).get("edge_count"),
        },
        "demo_gate_context": {
            "readiness_state": readiness.get("readiness_state"),
            "gate_can_open": readiness.get("gate_can_open"),
            "operator_can_enable": readiness.get("operator_can_enable"),
            "missing_prerequisites": readiness.get("missing_prerequisites", []),
        },
        "projection_surface": projection_surface,
        "projection_summary": {
            "surface_count": len(projection_surface),
            "implemented_count": sum(1 for x in projection_surface.values() if x["implemented"]),
            "callable_now_count": sum(1 for x in projection_surface.values() if x["callable_now"]),
            "projection_ready": False,
            "projection_can_drive_paper_ledger": False,
        },
        "projection_explainer": {
            "skeleton_defined_not_active": "position / balance projection 骨架已定义，但当前未激活，也不能驱动 paper ledger",
            "projection_ready_but_gate_closed": "projection 技术上可用，但 demo gate 仍关闭",
            "projection_ready_for_demo_only": "projection 仅服务于 demo/paper，不允许 live execution",
        },
        "operator_guidance": [
            "后续要先把 lifecycle 与 projection 对接，再补充 fill / cancel / fee / reservation 的投影细节",
            "随后应把 projection 与 paper audit trail、risk gate、acceptance 串联起来",
            "当前 projection 的价值在于固定责任边界，不在于提供可运行结算能力",
        ],
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
