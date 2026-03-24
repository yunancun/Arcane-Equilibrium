#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 为了继续加快 K 章推进，这一轮把 demo gate acceptance 的 capability 层补出来。
- 该层不是为了真的打开 demo gate，而是为了把：
  1. 将来如果 K 章想从 design-only 进入 paper/demo acceptance，应该满足哪些接受条件；
  2. 这些接受条件当前已经定义到了什么程度；
  3. 为什么当前 acceptance path 仍必须保持关闭；
  用统一、可机读、可人工审计的方式表达清楚。
- 当前目标：
  1. 定义 acceptance gate 的主要组件面；
  2. 明确当前只是 acceptance model defined，而不是可以真实打开 demo gate；
  3. 明确 `demo_gate_acceptance_ready` 仍不能改成 true；
  4. 保持 runtime 保护态不变。

English:
- To keep accelerating K chapter progress, this round adds the demo-gate acceptance
  capability layer.
- This layer does NOT actually open the demo gate. Its purpose is to describe:
  1. which acceptance conditions should exist before K could ever move from design-only
     toward paper/demo acceptance in the future,
  2. how far those acceptance conditions are currently defined,
  3. why the acceptance path must still remain closed now,
  in a unified machine-readable and human-auditable way.
- Current objectives:
  1. define the main acceptance-gate component surface,
  2. make explicit that the acceptance model is defined but cannot yet open the demo gate,
  3. keep `demo_gate_acceptance_ready` still false,
  4. preserve the protected runtime boundary.

Safety boundary / 安全边界：
- demo gate remains closed
- paper execution remains disabled
- live execution remains disabled
- no order authority is granted
- 本文件不会打开 demo gate，不会打开 paper/live execution，也不会授予下单 authority。
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
    raise RuntimeError("repo root not found for demo gate acceptance capability builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "audit_capability": BASE / "bybit_paper_audit_trail_capability_latest.json",
    "audit_contract": BASE / "bybit_paper_audit_trail_capability_contract_latest.json",
    "switch_capability": BASE / "bybit_explicit_operator_enable_switch_capability_latest.json",
    "k_decision": BASE / "bybit_demo_gate_decision_latest.json",
    "k_decision_contract": BASE / "bybit_demo_gate_decision_contract_latest.json",
    "readiness": BASE / "bybit_demo_gate_readiness_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_demo_gate_acceptance_capability_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    BASE.mkdir(parents=True, exist_ok=True)
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_demo_gate_acceptance_capability_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded: Dict[str, Dict[str, Any]] = {
        name: load_json(path) for name, path in PATHS.items() if path.exists()
    }

    audit_capability = loaded.get("audit_capability", {})
    audit_contract = loaded.get("audit_contract", {})
    switch_capability = loaded.get("switch_capability", {})
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

    switch_model_defined = (
        switch_capability.get("switch_state") == "operator_switch_defined_locked_closed"
        and switch_capability.get("operator_enable_available") is False
        and switch_capability.get("operator_path_closed") is True
    )

    k_design_no_execution_ok = (
        k_decision.get("decision_ready") is True
        and k_decision.get("decision_state") == "design_only_ready_no_execution"
        and k_decision.get("paper_execution_permitted") is False
        and k_decision.get("live_execution_permitted") is False
        and k_decision_contract.get("overall_ok") is True
    )

    missing_prerequisites = readiness.get("missing_prerequisites") or []

    acceptance_components = [
        {
            "component": "acceptance_prerequisite_matrix_model",
            "defined": True,
            "openable_now": False,
            "meaning": "acceptance prerequisite 矩阵模型已定义，但当前不能真实放行 / Acceptance-prerequisite matrix model is defined but cannot open the gate now.",
        },
        {
            "component": "operator_explicit_enable_requirement_model",
            "defined": True,
            "openable_now": False,
            "meaning": "显式 operator enable 要求模型已定义，但当前 operator path 仍关闭 / Explicit operator-enable requirement model is defined but the operator path remains closed.",
        },
        {
            "component": "runtime_protection_confirmation_model",
            "defined": True,
            "openable_now": False,
            "meaning": "runtime 保护确认模型已定义，但当前仍只能确认关闭态 / Runtime-protection confirmation model is defined but can only confirm the closed state now.",
        },
        {
            "component": "chapter_consistency_acceptance_model",
            "defined": True,
            "openable_now": False,
            "meaning": "章节一致性 acceptance 模型已定义，但当前不能把章节状态解释成可放行 / Chapter-consistency acceptance model is defined but cannot interpret the chapter as openable now.",
        },
    ]

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not audit_model_defined:
        blockers.append("audit_model_not_green")
    if not switch_model_defined:
        blockers.append("switch_model_not_green")
    if not k_design_no_execution_ok:
        blockers.append("k_design_decision_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    acceptance_model_defined = len(blockers) == 0
    acceptance_state = (
        "acceptance_model_defined_gate_closed"
        if acceptance_model_defined
        else "acceptance_capability_not_ready"
    )

    obj: Dict[str, Any] = {
        "acceptance_type": "bybit_demo_gate_acceptance_capability",
        "acceptance_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "acceptance_state": acceptance_state,
        "acceptance_ready": False,
        "acceptance_can_open_demo_gate": False,
        "acceptance_can_enable_paper_execution": False,
        "gate_path_closed": True,
        "live_acceptance_path_closed": True,
        "runtime_still_protected": runtime_still_protected,
        "missing_prerequisites": missing_prerequisites,
        "source_refs": {
            "audit_capability_ts_ms": audit_capability.get("ts_ms"),
            "audit_contract_ts_ms": audit_contract.get("ts_ms"),
            "switch_capability_ts_ms": switch_capability.get("ts_ms"),
            "k_decision_ts_ms": k_decision.get("ts_ms"),
            "k_decision_contract_ts_ms": k_decision_contract.get("ts_ms"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "acceptance_components": acceptance_components,
        "acceptance_summary": {
            "component_count": len(acceptance_components),
            "acceptance_model_defined": acceptance_model_defined,
            "acceptance_can_open_demo_gate": False,
            "gate_path_closed": True,
            "missing_prerequisite_count": len(missing_prerequisites),
        },
        "blockers": blockers,
        "acceptance_explainer": {
            "acceptance_model_defined_gate_closed": (
                "demo gate acceptance 的模型面已经被定义出来，但当前 gate path 仍必须保持关闭，"
                "因此 acceptance_ready 仍保持 false。"
            ),
            "acceptance_capability_not_ready": (
                "demo gate acceptance 当前还不能形成稳定的 capability 视图。"
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
