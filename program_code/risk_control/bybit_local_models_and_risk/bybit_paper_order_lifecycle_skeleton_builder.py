#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_paper_order_lifecycle_skeleton_builder.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K1/K3 支撑层 / paper order lifecycle
- 这一层的白话解释:
  定义 paper order 生命周期语义，但当前不是可运行订单系统。

Role:
- 生成本脚本对应的 K 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 K. Paper / Demo Gate 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 K 章内定义/校验 paper lifecycle 骨架

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

ADAPTER_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_paper_adapter_skeleton_latest.json")
READINESS_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_readiness_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_paper_order_lifecycle_skeleton_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_paper_order_lifecycle_skeleton_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    adapter = load_json(ADAPTER_PATH)
    readiness = load_json(READINESS_PATH)
    runtime = load_json(RUNTIME_PATH)

    readonly_lock_ok = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    state_nodes = [
        {
            "state_code": "paper_order_created",
            "terminal": False,
            "meaning": "本地 paper order 请求对象已创建，但尚未进入 paper lifecycle 处理",
        },
        {
            "state_code": "paper_order_submitted",
            "terminal": False,
            "meaning": "paper order 已提交给 simulator / paper adapter，但尚未得到生命周期确认",
        },
        {
            "state_code": "paper_order_working",
            "terminal": False,
            "meaning": "paper order 处于活动挂单状态，可等待后续撮合或取消",
        },
        {
            "state_code": "paper_order_partially_filled",
            "terminal": False,
            "meaning": "paper order 已部分成交，仍存在剩余量",
        },
        {
            "state_code": "paper_order_filled",
            "terminal": True,
            "meaning": "paper order 已全部成交，生命周期终结",
        },
        {
            "state_code": "paper_order_canceled",
            "terminal": True,
            "meaning": "paper order 已取消，生命周期终结",
        },
        {
            "state_code": "paper_order_rejected",
            "terminal": True,
            "meaning": "paper order 在进入有效工作态之前被拒绝，生命周期终结",
        },
    ]

    state_edges = [
        {"from": "paper_order_created", "to": "paper_order_submitted", "meaning": "提交到 simulator / adapter"},
        {"from": "paper_order_submitted", "to": "paper_order_working", "meaning": "paper order 被接受并进入工作态"},
        {"from": "paper_order_submitted", "to": "paper_order_rejected", "meaning": "paper order 被拒绝"},
        {"from": "paper_order_working", "to": "paper_order_partially_filled", "meaning": "发生部分成交"},
        {"from": "paper_order_working", "to": "paper_order_filled", "meaning": "直接全部成交"},
        {"from": "paper_order_working", "to": "paper_order_canceled", "meaning": "在工作态被取消"},
        {"from": "paper_order_partially_filled", "to": "paper_order_filled", "meaning": "剩余量全部成交"},
        {"from": "paper_order_partially_filled", "to": "paper_order_canceled", "meaning": "剩余量取消"},
    ]

    obj = {
        "lifecycle_type": "bybit_paper_order_lifecycle_skeleton",
        "lifecycle_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "G5.4",
        "revision_tree_context": {
            "section": "G5",
            "subsection": "G5.4",
            "section_meaning": "demo/paper gate 设计层",
            "current_focus": "paper order lifecycle skeleton",
        },
        "lifecycle_state": "skeleton_defined_not_active",
        "lifecycle_ready": False,
        "lifecycle_can_accept_new_orders": False,
        "lifecycle_reason": "paper order lifecycle graph is now defined, but adapter/readiness are still not active and demo gate remains closed",
        "source_refs": {
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
        "demo_gate_context": {
            "readiness_state": readiness.get("readiness_state"),
            "gate_can_open": readiness.get("gate_can_open"),
            "operator_can_enable": readiness.get("operator_can_enable"),
            "missing_prerequisites": readiness.get("missing_prerequisites", []),
        },
        "lifecycle_graph": {
            "state_nodes": state_nodes,
            "state_edges": state_edges,
        },
        "lifecycle_summary": {
            "state_count": len(state_nodes),
            "edge_count": len(state_edges),
            "terminal_state_count": sum(1 for n in state_nodes if n["terminal"]),
            "nonterminal_state_count": sum(1 for n in state_nodes if not n["terminal"]),
            "lifecycle_ready": False,
            "lifecycle_can_accept_new_orders": False,
        },
        "lifecycle_explainer": {
            "skeleton_defined_not_active": "paper order 生命周期骨架已定义，但当前未激活，也不能接收新订单",
            "lifecycle_ready_but_gate_closed": "生命周期技术上已可用，但 demo gate 仍关闭",
            "lifecycle_ready_for_demo_only": "生命周期仅服务于 demo/paper，不允许 live execution",
        },
        "operator_guidance": [
            "后续要先把 simulator adapter 与 lifecycle 对接，再补充 fill / cancel / reject 细节",
            "随后要把 lifecycle 与 balance / position projection 打通",
            "当前生命周期图只提供统一语义，不允许任何真实或 paper 执行入口开启",
        ],
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
