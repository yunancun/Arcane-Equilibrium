#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_demo_gate_summary_builder.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K章总控层 / summary
- 这一层的白话解释:
  把 K 章各层统一汇总成人工一眼可读的总状态。

Role:
- 生成本脚本对应的 K 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 K. Paper / Demo Gate 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 K 章内定义/校验 summary 层

Historical note:
- 开发过程中曾临时标为 G5.7
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
ADAPTER_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_paper_adapter_skeleton_latest.json")
LIFECYCLE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_paper_order_lifecycle_skeleton_latest.json")
PROJECTION_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_paper_position_balance_projection_skeleton_latest.json")
RISK_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_pretrade_risk_integration_skeleton_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_demo_gate_summary_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_demo_gate_summary_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    contract = load_json(CONTRACT_PATH)
    readiness = load_json(READINESS_PATH)
    adapter = load_json(ADAPTER_PATH)
    lifecycle = load_json(LIFECYCLE_PATH)
    projection = load_json(PROJECTION_PATH)
    risk = load_json(RISK_PATH)
    runtime = load_json(RUNTIME_PATH)

    missing_prereqs = readiness.get("missing_prerequisites", [])
    readonly_lock_ok = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    layer_status = {
        "contract_layer": {
            "contract_version": contract.get("contract_version"),
            "gate_state": contract.get("gate_state"),
            "gate_open": contract.get("gate_open"),
            "gate_ready": contract.get("gate_ready"),
        },
        "readiness_layer": {
            "readiness_version": readiness.get("readiness_version"),
            "readiness_state": readiness.get("readiness_state"),
            "gate_can_open": readiness.get("gate_can_open"),
            "operator_can_enable": readiness.get("operator_can_enable"),
            "missing_count": len(missing_prereqs),
        },
        "adapter_layer": {
            "adapter_version": adapter.get("adapter_version"),
            "adapter_state": adapter.get("adapter_state"),
            "adapter_ready": adapter.get("adapter_ready"),
            "adapter_can_accept_orders": adapter.get("adapter_can_accept_orders"),
        },
        "lifecycle_layer": {
            "lifecycle_version": lifecycle.get("lifecycle_version"),
            "lifecycle_state": lifecycle.get("lifecycle_state"),
            "lifecycle_ready": lifecycle.get("lifecycle_ready"),
            "lifecycle_can_accept_new_orders": lifecycle.get("lifecycle_can_accept_new_orders"),
        },
        "projection_layer": {
            "projection_version": projection.get("projection_version"),
            "projection_state": projection.get("projection_state"),
            "projection_ready": projection.get("projection_ready"),
            "projection_can_drive_paper_ledger": projection.get("projection_can_drive_paper_ledger"),
        },
        "risk_layer": {
            "risk_version": risk.get("risk_version"),
            "risk_state": risk.get("risk_state"),
            "risk_ready": risk.get("risk_ready"),
            "risk_can_evaluate_orders": risk.get("risk_can_evaluate_orders"),
        },
    }

    summary_state = "design_layers_defined_gate_closed"

    obj = {
        "summary_type": "bybit_demo_gate_summary",
        "summary_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "G5.7",
        "revision_tree_context": {
            "section": "G5",
            "subsection": "G5.7",
            "section_meaning": "demo/paper gate 设计层",
            "current_focus": "demo gate summary / 汇总层",
        },
        "summary_state": summary_state,
        "summary_ok": True,
        "gate_can_open": False,
        "operator_can_enable": False,
        "high_level_reason": "demo gate design layers are now defined across contract/readiness/adapter/lifecycle/projection/risk, but the gate must remain closed because key prerequisites are still missing",
        "source_refs": {
            "contract_version": contract.get("contract_version"),
            "contract_ts_ms": contract.get("ts_ms"),
            "readiness_version": readiness.get("readiness_version"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "adapter_version": adapter.get("adapter_version"),
            "adapter_ts_ms": adapter.get("ts_ms"),
            "lifecycle_version": lifecycle.get("lifecycle_version"),
            "lifecycle_ts_ms": lifecycle.get("ts_ms"),
            "projection_version": projection.get("projection_version"),
            "projection_ts_ms": projection.get("ts_ms"),
            "risk_version": risk.get("risk_version"),
            "risk_ts_ms": risk.get("ts_ms"),
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
        "layer_status": layer_status,
        "missing_prerequisites": missing_prereqs,
        "summary_matrix": {
            "defined_layer_count": 6,
            "ready_layer_count": sum([
                1 if contract.get("gate_state") == "closed_contract_defined" else 0,
                1 if readiness.get("readiness_state") is not None else 0,
                1 if adapter.get("adapter_state") == "skeleton_defined_not_active" else 0,
                1 if lifecycle.get("lifecycle_state") == "skeleton_defined_not_active" else 0,
                1 if projection.get("projection_state") == "skeleton_defined_not_active" else 0,
                1 if risk.get("risk_state") == "skeleton_defined_not_active" else 0,
            ]),
            "missing_prerequisite_count": len(missing_prereqs),
            "gate_can_open_now": False,
            "operator_can_enable_now": False,
        },
        "summary_explainer": {
            "design_layers_defined_gate_closed": "demo gate 设计层已经基本铺开，但当前仍是关闭态，不能进入 demo/paper execution",
            "ready_but_operator_locked": "技术 prerequisite 已满足，但仍需 operator 明确放行",
            "gate_open_for_demo_only": "demo gate 已开启，但仍只允许 demo/paper，不允许 live execution",
        },
        "operator_guidance": [
            "下一步应继续补齐 acceptance / handoff / final audit，而不是尝试绕过 gate",
            "当前 summary 的意义是统一观察设计层进度，不代表 gate 已可打开",
            "主 runtime 仍必须保持 read_only / execution disabled",
        ],
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
