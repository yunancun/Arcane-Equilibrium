#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 定义 explicit operator enable switch 的 capability 层。
- 当前只描述 operator switch 的模型面，不打开任何执行路径。
- 目标是把 operator 控制面定义清楚，并保持 operator path 关闭。

English:
- Define the explicit operator enable switch capability layer.
- This only describes the operator-switch model surface and does not open any execution path.
- The goal is to define the operator control surface clearly while keeping the operator path closed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for operator enable switch capability builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "audit_capability": BASE / "bybit_paper_audit_trail_capability_latest.json",
    "audit_contract": BASE / "bybit_paper_audit_trail_capability_contract_latest.json",
    "k_decision": BASE / "bybit_demo_gate_decision_latest.json",
    "k_decision_contract": BASE / "bybit_demo_gate_decision_contract_latest.json",
    "readiness": BASE / "bybit_demo_gate_readiness_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_explicit_operator_enable_switch_capability_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    BASE.mkdir(parents=True, exist_ok=True)
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_explicit_operator_enable_switch_capability_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded: Dict[str, Dict[str, Any]] = {
        name: load_json(path) for name, path in PATHS.items() if path.exists()
    }

    audit_capability = loaded.get("audit_capability", {})
    audit_contract = loaded.get("audit_contract", {})
    k_decision = loaded.get("k_decision", {})
    k_decision_contract = loaded.get("k_decision_contract", {})
    readiness = loaded.get("readiness", {})
    runtime = loaded.get("runtime", {})

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    audit_model_defined = (
        audit_capability.get("internal_audit_model_defined") is True
        and audit_capability.get("audit_can_record_execution_flow") is False
        and audit_capability.get("audit_path_closed") is True
        and audit_contract.get("overall_ok") is True
    )

    k_design_no_execution_ok = (
        k_decision.get("decision_ready") is True
        and k_decision.get("decision_state") == "design_only_ready_no_execution"
        and k_decision.get("paper_execution_permitted") is False
        and k_decision.get("live_execution_permitted") is False
        and k_decision_contract.get("overall_ok") is True
    )

    missing_prerequisites = readiness.get("missing_prerequisites") or []

    switch_components = [
        {"component": "operator_enable_flag_model", "defined": True, "activatable_now": False, "meaning": "显式 enable flag 模型已定义 / Explicit enable-flag model is defined."},
        {"component": "operator_enable_scope_model", "defined": True, "activatable_now": False, "meaning": "enable 作用域模型已定义 / Enable-scope model is defined."},
        {"component": "operator_enable_audit_binding_model", "defined": True, "activatable_now": False, "meaning": "operator enable 与审计绑定模型已定义 / Operator-enable-to-audit binding model is defined."},
        {"component": "operator_disable_relock_model", "defined": True, "activatable_now": False, "meaning": "relock / disable 模型已定义 / Relock/disable model is defined."},
    ]

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not audit_model_defined:
        blockers.append("audit_model_not_green")
    if not k_design_no_execution_ok:
        blockers.append("k_design_decision_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    switch_capability_ready = len(blockers) == 0
    switch_state = "operator_switch_defined_locked_closed" if switch_capability_ready else "operator_switch_capability_not_ready"

    obj: Dict[str, Any] = {
        "switch_type": "bybit_explicit_operator_enable_switch_capability",
        "switch_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "switch_state": switch_state,
        "switch_ready": False,
        "operator_enable_available": False,
        "explicit_enable_required": True,
        "operator_path_closed": True,
        "live_operator_path_closed": True,
        "runtime_still_protected": runtime_still_protected,
        "missing_prerequisites": missing_prerequisites,
        "source_refs": {
            "audit_capability_ts_ms": audit_capability.get("ts_ms"),
            "audit_contract_ts_ms": audit_contract.get("ts_ms"),
            "k_decision_ts_ms": k_decision.get("ts_ms"),
            "k_decision_contract_ts_ms": k_decision_contract.get("ts_ms"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "switch_components": switch_components,
        "switch_summary": {
            "component_count": len(switch_components),
            "switch_model_defined": switch_capability_ready,
            "operator_enable_available": False,
            "operator_path_closed": True,
            "missing_prerequisite_count": len(missing_prerequisites),
        },
        "blockers": blockers,
        "switch_explainer": {
            "operator_switch_defined_locked_closed": "operator switch 模型面已经定义出来，但当前 operator path 仍保持关闭 / Operator switch model is defined, but the operator path remains closed.",
            "operator_switch_capability_not_ready": "operator switch 当前还不能形成稳定的 capability 视图 / Operator switch cannot yet form a stable capability view.",
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
