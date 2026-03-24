#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 为了继续加快 K 章推进，这一轮把 paper audit trail 的 capability 层补出来。
- 该层不是为了打开 paper execution，而是为了把 paper/demo 场景里，
  哪些审计记录面已经被定义、这些记录当前能覆盖到什么程度、以及哪些记录仍然
  只能停留在设计层，用统一、可机读、可人工审计的方式表达清楚。
- 当前目标：
  1. 明确定义 audit trail 的主要记录组件面；
  2. 明确当前只是 audit model defined，而不是可以真实记录完整 paper 订单执行流；
  3. 明确 `paper_audit_trail_ready` 仍不能改成 true；
  4. 保持 runtime 保护态不变。

English:
- To keep accelerating K chapter progress, this round adds the paper audit trail
  capability layer.
- This layer does NOT open paper execution. Its purpose is to describe, in a unified
  machine-readable and human-auditable way, which audit-record surfaces are already defined,
  how far they currently reach, and which parts still remain design-only.
- Current objectives:
  1. define the main audit-trail component surface,
  2. make explicit that the audit model is defined but cannot yet record a complete real
     paper-order execution flow,
  3. keep `paper_audit_trail_ready` still false,
  4. preserve the protected runtime boundary.

Safety boundary / 安全边界：
- paper order submission remains disabled
- live order submission remains disabled
- audit trail cannot yet record a full real paper execution chain
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
    raise RuntimeError("repo root not found for paper audit trail capability builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "risk_capability": BASE / "bybit_pretrade_risk_gate_capability_latest.json",
    "risk_contract": BASE / "bybit_pretrade_risk_gate_capability_contract_latest.json",
    "k_decision": BASE / "bybit_demo_gate_decision_latest.json",
    "k_decision_contract": BASE / "bybit_demo_gate_decision_contract_latest.json",
    "readiness": BASE / "bybit_demo_gate_readiness_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_paper_audit_trail_capability_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    BASE.mkdir(parents=True, exist_ok=True)
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_paper_audit_trail_capability_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded: Dict[str, Dict[str, Any]] = {
        name: load_json(path) for name, path in PATHS.items() if path.exists()
    }

    risk_capability = loaded.get("risk_capability", {})
    risk_contract = loaded.get("risk_contract", {})
    k_decision = loaded.get("k_decision", {})
    k_decision_contract = loaded.get("k_decision_contract", {})
    readiness = loaded.get("readiness", {})
    runtime = loaded.get("runtime", {})

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    risk_model_defined = (
        risk_capability.get("internal_risk_model_defined") is True
        and risk_capability.get("risk_can_evaluate_orders") is False
        and risk_capability.get("risk_gate_closed") is True
        and risk_contract.get("overall_ok") is True
    )

    k_design_no_execution_ok = (
        k_decision.get("decision_ready") is True
        and k_decision.get("decision_state") == "design_only_ready_no_execution"
        and k_decision.get("paper_execution_permitted") is False
        and k_decision.get("live_execution_permitted") is False
        and k_decision_contract.get("overall_ok") is True
    )

    missing_prerequisites = readiness.get("missing_prerequisites") or []

    audit_components = [
        {
            "component": "order_intent_record_model",
            "defined": True,
            "recordable_now": False,
            "meaning": "订单 intent 记录模型已定义，但当前不能形成真实 paper submission 审计 / Order-intent record model is defined but cannot yet form a real paper-submission audit trail.",
        },
        {
            "component": "lifecycle_transition_record_model",
            "defined": True,
            "recordable_now": False,
            "meaning": "生命周期迁移记录模型已定义，但当前不能记录真实 pending/fill/cancel 流 / Lifecycle-transition record model is defined but cannot yet record real pending/fill/cancel flows.",
        },
        {
            "component": "projection_change_record_model",
            "defined": True,
            "recordable_now": False,
            "meaning": "projection 变更记录模型已定义，但当前不能记录真实 ledger 变动 / Projection-change record model is defined but cannot yet record real ledger changes.",
        },
        {
            "component": "risk_verdict_record_model",
            "defined": True,
            "recordable_now": False,
            "meaning": "risk verdict 记录模型已定义，但当前不能记录真实 order-level risk verdict / Risk-verdict record model is defined but cannot yet record real order-level risk verdicts.",
        },
        {
            "component": "operator_action_record_model",
            "defined": True,
            "recordable_now": False,
            "meaning": "operator 动作记录模型已定义，但当前还没有真实 operator enable flow / Operator-action record model is defined but no real operator-enable flow exists yet.",
        },
        {
            "component": "rejection_reason_record_model",
            "defined": True,
            "recordable_now": False,
            "meaning": "拒绝原因记录模型已定义，但当前不能记录真实订单拒绝链路 / Rejection-reason record model is defined but cannot yet record a real order rejection chain.",
        },
    ]

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not risk_model_defined:
        blockers.append("risk_model_not_green")
    if not k_design_no_execution_ok:
        blockers.append("k_design_decision_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    audit_capability_ready = len(blockers) == 0
    audit_state = (
        "audit_model_defined_path_closed"
        if audit_capability_ready
        else "audit_capability_not_ready"
    )

    obj: Dict[str, Any] = {
        "audit_type": "bybit_paper_audit_trail_capability",
        "audit_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "audit_state": audit_state,
        "audit_ready": False,
        "audit_can_record_execution_flow": False,
        "internal_audit_model_defined": audit_capability_ready,
        "audit_path_closed": True,
        "live_audit_path_closed": True,
        "runtime_still_protected": runtime_still_protected,
        "missing_prerequisites": missing_prerequisites,
        "source_refs": {
            "risk_capability_ts_ms": risk_capability.get("ts_ms"),
            "risk_contract_ts_ms": risk_contract.get("ts_ms"),
            "k_decision_ts_ms": k_decision.get("ts_ms"),
            "k_decision_contract_ts_ms": k_decision_contract.get("ts_ms"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "audit_components": audit_components,
        "audit_summary": {
            "component_count": len(audit_components),
            "internal_audit_model_defined": audit_capability_ready,
            "audit_can_record_execution_flow": False,
            "audit_path_closed": True,
            "missing_prerequisite_count": len(missing_prerequisites),
        },
        "blockers": blockers,
        "audit_explainer": {
            "audit_model_defined_path_closed": (
                "paper audit trail 的模型面已经被定义出来，但当前 audit path 仍必须保持关闭，"
                "因此 audit_ready 仍保持 false。"
            ),
            "audit_capability_not_ready": (
                "paper audit trail 当前还不能形成稳定的 capability 视图。"
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
