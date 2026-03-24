#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 为了加快 K 章推进，这一轮直接把 paper position / balance projection 的 capability 层补出来。
- 该层不是为了打开 paper execution，而是为了把 paper ledger / position / balance / PnL / fee / margin
  这些 projection 模型目前已经定义到什么程度，用统一、可机读、可人工审计的方式表达清楚。
- 当前目标：
  1. 明确定义 projection 组件面；
  2. 明确当前只是 projection model defined，而不是可驱动真实 paper ledger；
  3. 明确 `paper_position_balance_projection_ready` 仍不能改成 true；
  4. 保持 runtime 保护态不变。

English:
- To accelerate K chapter progress, this round directly adds the paper position / balance projection
  capability layer.
- This layer does NOT open paper execution. Its purpose is to describe, in a unified machine-readable
  and human-auditable way, how far the paper ledger / position / balance / PnL / fee / margin
  projection model has been defined.
- Current objectives:
  1. define the projection component surface clearly,
  2. make explicit that the model is defined but cannot drive a real paper ledger yet,
  3. keep `paper_position_balance_projection_ready` still false,
  4. preserve the protected runtime boundary.

Safety boundary / 安全边界：
- paper order submission remains disabled
- live order submission remains disabled
- projection cannot drive a real paper ledger yet
- no execution authority is granted
- 本文件不会打开 paper/live execution，也不会授予下单 authority。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    """Locate repo root without machine-specific absolute paths.
    中文：避免维护时继续被单机路径绑死。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for projection capability builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "lifecycle_capability": BASE / "bybit_paper_order_lifecycle_capability_latest.json",
    "lifecycle_contract": BASE / "bybit_paper_order_lifecycle_capability_contract_latest.json",
    "k_decision": BASE / "bybit_demo_gate_decision_latest.json",
    "k_decision_contract": BASE / "bybit_demo_gate_decision_contract_latest.json",
    "readiness": BASE / "bybit_demo_gate_readiness_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_paper_position_balance_projection_capability_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    BASE.mkdir(parents=True, exist_ok=True)
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_paper_position_balance_projection_capability_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded: Dict[str, Dict[str, Any]] = {
        name: load_json(path) for name, path in PATHS.items() if path.exists()
    }

    lifecycle_capability = loaded.get("lifecycle_capability", {})
    lifecycle_contract = loaded.get("lifecycle_contract", {})
    k_decision = loaded.get("k_decision", {})
    k_decision_contract = loaded.get("k_decision_contract", {})
    readiness = loaded.get("readiness", {})
    runtime = loaded.get("runtime", {})

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    lifecycle_model_defined = (
        lifecycle_capability.get("internal_lifecycle_model_defined") is True
        and lifecycle_capability.get("lifecycle_can_accept_new_orders") is False
        and lifecycle_capability.get("submission_path_closed") is True
        and lifecycle_contract.get("overall_ok") is True
    )

    k_design_no_execution_ok = (
        k_decision.get("decision_ready") is True
        and k_decision.get("decision_state") == "design_only_ready_no_execution"
        and k_decision.get("paper_execution_permitted") is False
        and k_decision.get("live_execution_permitted") is False
        and k_decision_contract.get("overall_ok") is True
    )

    missing_prerequisites = readiness.get("missing_prerequisites") or []

    projection_components = [
        {
            "component": "paper_position_snapshot_model",
            "defined": True,
            "drivable_now": False,
            "meaning": "持仓快照模型已定义，但当前不能真实驱动 paper ledger / Position snapshot model is defined, but cannot drive a real paper ledger yet.",
        },
        {
            "component": "paper_balance_snapshot_model",
            "defined": True,
            "drivable_now": False,
            "meaning": "余额快照模型已定义，但当前不能真实驱动 paper ledger / Balance snapshot model is defined, but cannot drive a real paper ledger yet.",
        },
        {
            "component": "paper_pnl_projection_model",
            "defined": True,
            "drivable_now": False,
            "meaning": "PnL projection 模型已定义，但当前只是设计层 / PnL projection model is defined but remains design-only.",
        },
        {
            "component": "paper_fee_projection_model",
            "defined": True,
            "drivable_now": False,
            "meaning": "手续费 projection 模型已定义，但当前不能参与真实 ledger 结算 / Fee projection model is defined but cannot participate in a real ledger settlement yet.",
        },
        {
            "component": "paper_reserved_margin_projection_model",
            "defined": True,
            "drivable_now": False,
            "meaning": "预留保证金 projection 模型已定义，但当前仍不能真实扣账 / Reserved-margin projection model is defined but cannot apply real paper-ledger reservation yet.",
        },
    ]

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not lifecycle_model_defined:
        blockers.append("lifecycle_model_not_green")
    if not k_design_no_execution_ok:
        blockers.append("k_design_decision_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    projection_capability_ready = len(blockers) == 0
    projection_state = (
        "projection_model_defined_ledger_closed"
        if projection_capability_ready
        else "projection_capability_not_ready"
    )

    obj: Dict[str, Any] = {
        "projection_type": "bybit_paper_position_balance_projection_capability",
        "projection_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "projection_state": projection_state,
        "projection_ready": False,
        "projection_can_drive_paper_ledger": False,
        "internal_projection_model_defined": projection_capability_ready,
        "ledger_path_closed": True,
        "live_projection_closed": True,
        "runtime_still_protected": runtime_still_protected,
        "missing_prerequisites": missing_prerequisites,
        "source_refs": {
            "lifecycle_capability_ts_ms": lifecycle_capability.get("ts_ms"),
            "lifecycle_contract_ts_ms": lifecycle_contract.get("ts_ms"),
            "k_decision_ts_ms": k_decision.get("ts_ms"),
            "k_decision_contract_ts_ms": k_decision_contract.get("ts_ms"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "projection_components": projection_components,
        "projection_summary": {
            "component_count": len(projection_components),
            "internal_projection_model_defined": projection_capability_ready,
            "projection_can_drive_paper_ledger": False,
            "ledger_path_closed": True,
            "missing_prerequisite_count": len(missing_prerequisites),
        },
        "blockers": blockers,
        "projection_explainer": {
            "projection_model_defined_ledger_closed": (
                "paper position / balance projection 的模型面已经被定义出来，但当前 ledger path 仍必须关闭，"
                "因此 projection_ready 仍保持 false。"
            ),
            "projection_capability_not_ready": (
                "paper position / balance projection 当前还不能形成稳定的 capability 视图。"
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
