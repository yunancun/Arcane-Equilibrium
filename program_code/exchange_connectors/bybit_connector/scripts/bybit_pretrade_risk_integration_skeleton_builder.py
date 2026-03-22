#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_pretrade_risk_integration_skeleton_builder.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K2. pretrade risk gate integration
- 这一层的白话解释:
  定义 demo/paper 进入前的风险检查边界，但当前不能真正评估或放行订单。

Role:
- 生成本脚本对应的 K 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 K. Paper / Demo Gate 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 K 章内定义/校验 risk integration 骨架

Historical note:
- 开发过程中曾临时标为 G5.6
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

READINESS_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_readiness_latest.json")
ADAPTER_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_paper_adapter_skeleton_latest.json")
LIFECYCLE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_paper_order_lifecycle_skeleton_latest.json")
PROJECTION_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_paper_position_balance_projection_skeleton_latest.json")
RUNTIME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_pretrade_risk_integration_skeleton_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_pretrade_risk_integration_skeleton_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    readiness = load_json(READINESS_PATH)
    adapter = load_json(ADAPTER_PATH)
    lifecycle = load_json(LIFECYCLE_PATH)
    projection = load_json(PROJECTION_PATH)
    runtime = load_json(RUNTIME_PATH)

    readonly_lock_ok = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    risk_surface = {
        "check_symbol_allowlist": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "symbol universe / allowlist policy is not ready yet",
        },
        "check_order_notional_limit": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper notional sizing control is not ready yet",
        },
        "check_position_exposure_limit": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper exposure cap model is not ready yet",
        },
        "check_available_balance_projection": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "balance projection dependency is not ready yet",
        },
        "check_duplicate_order_guard": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "duplicate / replay guard logic is not ready yet",
        },
        "check_daily_loss_or_drawdown_limit": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper daily risk budget logic is not ready yet",
        },
        "emit_pretrade_risk_audit_record": {
            "implemented": False,
            "callable_now": False,
            "mode": "stub_only",
            "reason": "paper risk audit integration is not ready yet",
        },
    }

    obj = {
        "risk_type": "bybit_pretrade_risk_integration_skeleton",
        "risk_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "G5.6",
        "revision_tree_context": {
            "section": "G5",
            "subsection": "G5.6",
            "section_meaning": "demo/paper gate 设计层",
            "current_focus": "pretrade risk integration skeleton",
        },
        "risk_state": "skeleton_defined_not_active",
        "risk_ready": False,
        "risk_can_evaluate_orders": False,
        "risk_reason": "pretrade risk surface is defined, but demo gate / adapter / lifecycle / projection are all still inactive and no paper order path can be evaluated yet",
        "source_refs": {
            "readiness_version": readiness.get("readiness_version"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "adapter_version": adapter.get("adapter_version"),
            "adapter_ts_ms": adapter.get("ts_ms"),
            "lifecycle_version": lifecycle.get("lifecycle_version"),
            "lifecycle_ts_ms": lifecycle.get("ts_ms"),
            "projection_version": projection.get("projection_version"),
            "projection_ts_ms": projection.get("ts_ms"),
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
            "readiness_state": readiness.get("readiness_state"),
            "gate_can_open": readiness.get("gate_can_open"),
            "operator_can_enable": readiness.get("operator_can_enable"),
            "missing_prerequisites": readiness.get("missing_prerequisites", []),
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
        },
        "projection_context": {
            "projection_state": projection.get("projection_state"),
            "projection_ready": projection.get("projection_ready"),
            "projection_can_drive_paper_ledger": projection.get("projection_can_drive_paper_ledger"),
        },
        "risk_surface": risk_surface,
        "risk_summary": {
            "check_count": len(risk_surface),
            "implemented_count": sum(1 for x in risk_surface.values() if x["implemented"]),
            "callable_now_count": sum(1 for x in risk_surface.values() if x["callable_now"]),
            "risk_ready": False,
            "risk_can_evaluate_orders": False,
        },
        "risk_explainer": {
            "skeleton_defined_not_active": "pretrade risk integration 骨架已定义，但当前未激活，也不能评估订单",
            "risk_ready_but_gate_closed": "risk integration 技术上已可用，但 demo gate 仍关闭",
            "risk_ready_for_demo_only": "risk integration 仅服务于 demo/paper，不允许 live execution",
        },
        "operator_guidance": [
            "后续应先把 projection 和 lifecycle 的可运行结果接入 risk checks，再补 acceptance",
            "risk integration 的第一职责是阻断不合规 paper order，而不是放行订单",
            "当前 risk surface 的价值在于固定检查边界，不在于提供实际风控决策能力",
        ],
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
