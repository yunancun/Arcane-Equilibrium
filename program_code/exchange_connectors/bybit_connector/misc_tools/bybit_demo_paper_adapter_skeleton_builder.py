#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_demo_paper_adapter_skeleton_builder.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K1. paper execution adapter
- 这一层的白话解释:
  定义 paper/demo adapter 外壳，但当前仍不能接任何 paper order。

Role:
- 生成本脚本对应的 K 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 K. Paper / Demo Gate 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 K 章内定义/校验 paper/simulator adapter 骨架

Historical note:
- 开发过程中曾临时标为 G5.3
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

CONTRACT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_contract_latest.json")
READINESS_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_readiness_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_demo_paper_adapter_skeleton_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_demo_paper_adapter_skeleton_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    contract = load_json(CONTRACT_PATH)
    readiness = load_json(READINESS_PATH)
    runtime = load_json(RUNTIME_PATH)

    missing = readiness.get("missing_prerequisites", [])
    readonly_lock_ok = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    interface_surface = {
        "submit_paper_order": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper order lifecycle is not ready yet",
        },
        "cancel_paper_order": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper order lifecycle is not ready yet",
        },
        "sync_paper_positions": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper position projection is not ready yet",
        },
        "sync_paper_balance_projection": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper balance projection is not ready yet",
        },
        "run_pretrade_risk_check": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "pretrade risk integration is not ready yet",
        },
        "write_paper_audit_trail": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper audit trail is not ready yet",
        },
    }

    obj = {
        "adapter_type": "bybit_demo_paper_adapter_skeleton",
        "adapter_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "G5.3",
        "revision_tree_context": {
            "section": "G5",
            "subsection": "G5.3",
            "section_meaning": "demo/paper gate 设计层",
            "current_focus": "demo/paper adapter skeleton",
        },
        "adapter_state": "skeleton_defined_not_active",
        "adapter_active": False,
        "adapter_ready": False,
        "adapter_can_accept_orders": False,
        "adapter_reason": "adapter surface is now defined, but demo gate readiness is still incomplete and no paper lifecycle/risk/audit stack is implemented yet",
        "source_refs": {
            "demo_gate_contract_version": contract.get("contract_version"),
            "demo_gate_contract_ts_ms": contract.get("ts_ms"),
            "demo_gate_readiness_version": readiness.get("readiness_version"),
            "demo_gate_readiness_ts_ms": readiness.get("ts_ms"),
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
        "demo_gate_context": {
            "gate_state": contract.get("gate_state"),
            "gate_open": contract.get("gate_open"),
            "gate_ready": contract.get("gate_ready"),
            "readiness_state": readiness.get("readiness_state"),
            "gate_can_open": readiness.get("gate_can_open"),
            "operator_can_enable": readiness.get("operator_can_enable"),
        },
        "missing_prerequisites": missing,
        "interface_surface": interface_surface,
        "adapter_summary": {
            "interface_count": len(interface_surface),
            "implemented_count": sum(1 for x in interface_surface.values() if x["implemented"]),
            "callable_now_count": sum(1 for x in interface_surface.values() if x["callable_now"]),
            "adapter_active": False,
            "adapter_can_accept_orders": False,
        },
        "adapter_explainer": {
            "skeleton_defined_not_active": "adapter 接口骨架已经定义，但当前仍未激活，也不能接 paper order",
            "adapter_ready_but_gate_closed": "adapter 技术上可用，但 demo gate 仍关闭",
            "adapter_ready_for_demo_only": "adapter 仅可用于 demo/paper，不可用于 live execution",
        },
        "operator_guidance": [
            "后续应先补 paper lifecycle / balance projection / risk / audit，再考虑让 adapter 进入 ready",
            "当前 adapter 的价值在于固定接口面，不在于执行能力",
            "即使 adapter 将来 ready，也仍需 demo gate 明确放行后才能接 paper order",
        ],
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
