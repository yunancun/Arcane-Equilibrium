#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 为了继续加快 K 章推进，这一轮把 pretrade risk gate 的 capability 层也补出来。
- 该层不是为了打开下单，而是为了把 paper/demo 场景里，订单进入 submission 之前
  应该先经过哪些风险闸门、这些闸门目前定义到了什么程度、哪些能力仍然只停留在设计层，
  用统一、可机读、可人工审计的方式表达清楚。
- 当前目标：
  1. 明确定义 pretrade risk gate 的主要组件面；
  2. 明确当前只是 risk model defined，而不是可以真实评估并放行 paper order；
  3. 明确 `pretrade_risk_gate_integrated` 仍不能改成 true；
  4. 保持 runtime 保护态不变。

English:
- To keep accelerating K chapter progress, this round adds the pretrade risk gate
  capability layer.
- This layer does NOT open order submission. Its purpose is to describe, in a unified
  machine-readable and human-auditable way, which risk gates should stand before a
  paper/demo order submission, how far those gates are currently defined, and which parts
  still remain design-only.
- Current objectives:
  1. define the main pretrade risk gate component surface,
  2. make explicit that the risk model is defined but cannot yet evaluate and approve
     real paper submissions,
  3. keep `pretrade_risk_gate_integrated` still false,
  4. preserve the protected runtime boundary.

Safety boundary / 安全边界：
- paper order submission remains disabled
- live order submission remains disabled
- risk gate cannot approve real paper orders yet
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
    raise RuntimeError("repo root not found for pretrade risk gate capability builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "projection_capability": BASE / "bybit_paper_position_balance_projection_capability_latest.json",
    "projection_contract": BASE / "bybit_paper_position_balance_projection_capability_contract_latest.json",
    "k_decision": BASE / "bybit_demo_gate_decision_latest.json",
    "k_decision_contract": BASE / "bybit_demo_gate_decision_contract_latest.json",
    "readiness": BASE / "bybit_demo_gate_readiness_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_pretrade_risk_gate_capability_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    BASE.mkdir(parents=True, exist_ok=True)
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_pretrade_risk_gate_capability_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded: Dict[str, Dict[str, Any]] = {
        name: load_json(path) for name, path in PATHS.items() if path.exists()
    }

    projection_capability = loaded.get("projection_capability", {})
    projection_contract = loaded.get("projection_contract", {})
    k_decision = loaded.get("k_decision", {})
    k_decision_contract = loaded.get("k_decision_contract", {})
    readiness = loaded.get("readiness", {})
    runtime = loaded.get("runtime", {})

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    projection_model_defined = (
        projection_capability.get("internal_projection_model_defined") is True
        and projection_capability.get("projection_can_drive_paper_ledger") is False
        and projection_capability.get("ledger_path_closed") is True
        and projection_contract.get("overall_ok") is True
    )

    k_design_no_execution_ok = (
        k_decision.get("decision_ready") is True
        and k_decision.get("decision_state") == "design_only_ready_no_execution"
        and k_decision.get("paper_execution_permitted") is False
        and k_decision.get("live_execution_permitted") is False
        and k_decision_contract.get("overall_ok") is True
    )

    missing_prerequisites = readiness.get("missing_prerequisites") or []

    risk_components = [
        {
            "component": "order_size_guard_model",
            "defined": True,
            "enforceable_now": False,
            "meaning": "下单数量边界模型已定义，但当前不能真实拦截 paper order / Order-size guard model is defined but cannot block real paper orders yet.",
        },
        {
            "component": "order_notional_guard_model",
            "defined": True,
            "enforceable_now": False,
            "meaning": "名义价值边界模型已定义，但当前不能真实放行/拒绝 paper order / Order-notional guard model is defined but cannot yet approve/reject real paper orders.",
        },
        {
            "component": "duplicate_submission_guard_model",
            "defined": True,
            "enforceable_now": False,
            "meaning": "重复提交保护模型已定义，但当前不能真实防止重复 submission / Duplicate-submission guard model is defined but cannot yet prevent real duplicate submissions.",
        },
        {
            "component": "state_conflict_guard_model",
            "defined": True,
            "enforceable_now": False,
            "meaning": "状态冲突保护模型已定义，但当前不能真实检查 lifecycle/ledger 冲突 / State-conflict guard model is defined but cannot yet validate real lifecycle/ledger conflicts.",
        },
        {
            "component": "cooldown_guard_model",
            "defined": True,
            "enforceable_now": False,
            "meaning": "冷却期保护模型已定义，但当前不能真实执行 cooldown 拦截 / Cooldown guard model is defined but cannot yet enforce a real cooldown block.",
        },
        {
            "component": "exposure_guard_model",
            "defined": True,
            "enforceable_now": False,
            "meaning": "风险暴露保护模型已定义，但当前不能真实评估持仓与保证金暴露 / Exposure guard model is defined but cannot yet evaluate real position/margin exposure.",
        },
    ]

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not projection_model_defined:
        blockers.append("projection_model_not_green")
    if not k_design_no_execution_ok:
        blockers.append("k_design_decision_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    risk_capability_ready = len(blockers) == 0
    risk_state = (
        "risk_model_defined_gate_closed"
        if risk_capability_ready
        else "risk_capability_not_ready"
    )

    obj: Dict[str, Any] = {
        "risk_type": "bybit_pretrade_risk_gate_capability",
        "risk_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "risk_state": risk_state,
        "risk_ready": False,
        "risk_can_evaluate_orders": False,
        "internal_risk_model_defined": risk_capability_ready,
        "risk_gate_closed": True,
        "live_risk_path_closed": True,
        "runtime_still_protected": runtime_still_protected,
        "missing_prerequisites": missing_prerequisites,
        "source_refs": {
            "projection_capability_ts_ms": projection_capability.get("ts_ms"),
            "projection_contract_ts_ms": projection_contract.get("ts_ms"),
            "k_decision_ts_ms": k_decision.get("ts_ms"),
            "k_decision_contract_ts_ms": k_decision_contract.get("ts_ms"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "risk_components": risk_components,
        "risk_summary": {
            "component_count": len(risk_components),
            "internal_risk_model_defined": risk_capability_ready,
            "risk_can_evaluate_orders": False,
            "risk_gate_closed": True,
            "missing_prerequisite_count": len(missing_prerequisites),
        },
        "blockers": blockers,
        "risk_explainer": {
            "risk_model_defined_gate_closed": (
                "pretrade risk gate 的模型面已经被定义出来，但当前 risk gate 仍必须保持关闭，"
                "因此 risk_ready 仍保持 false。"
            ),
            "risk_capability_not_ready": (
                "pretrade risk gate 当前还不能形成稳定的 capability 视图。"
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
