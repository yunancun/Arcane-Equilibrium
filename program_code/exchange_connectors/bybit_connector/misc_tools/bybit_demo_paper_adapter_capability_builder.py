#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 在 adapter skeleton、adapter transition intent、K unified decision 之上，
  再补一层 paper adapter capability 聚合层。
- 这层的目标不是打开 paper order submission，而是把“adapter 目前到底已经具备什么能力、
  哪些能力仍然缺失、哪些能力只能内部形成 intent 不能真正提交订单”表达清楚。
- 这样后续人工阅读时，一眼就能区分：
  1. 接口面已定义
  2. 内部 intent 已可形成
  3. 真正的 order submission 仍未开放

English:
- On top of the adapter skeleton, adapter transition intent, and unified K decision,
  add a paper-adapter capability aggregation layer.
- The goal is NOT to open paper order submission.
- The goal is to express clearly:
  1. what capability the adapter already has,
  2. what is still missing,
  3. what is currently intent-only and must not submit orders yet.

Safety boundary / 安全边界：
- paper order submission remains disabled
- live order submission remains disabled
- no order authority is granted
- paper execution is still not open
- 本层不会打开 paper/live execution，也不会授予下单 authority。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    """Locate repo root without machine-specific absolute paths.
    中文：避免维护时继续被单机绝对路径绑死。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for paper adapter capability builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "adapter_skeleton": BASE / "bybit_demo_paper_adapter_skeleton_latest.json",
    "adapter_intent": BASE / "bybit_demo_paper_adapter_transition_intent_latest.json",
    "adapter_intent_contract": BASE / "bybit_demo_paper_adapter_transition_intent_contract_latest.json",
    "k_decision": BASE / "bybit_demo_gate_decision_latest.json",
    "k_decision_contract": BASE / "bybit_demo_gate_decision_contract_latest.json",
    "readiness": BASE / "bybit_demo_gate_readiness_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_demo_paper_adapter_capability_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    BASE.mkdir(parents=True, exist_ok=True)
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_demo_paper_adapter_capability_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded: Dict[str, Dict[str, Any]] = {
        name: load_json(path) for name, path in PATHS.items() if path.exists()
    }

    adapter_skeleton = loaded.get("adapter_skeleton", {})
    adapter_intent = loaded.get("adapter_intent", {})
    adapter_intent_contract = loaded.get("adapter_intent_contract", {})
    k_decision = loaded.get("k_decision", {})
    k_decision_contract = loaded.get("k_decision_contract", {})
    readiness = loaded.get("readiness", {})
    runtime = loaded.get("runtime", {})

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    skeleton_surface_defined = (
        adapter_skeleton.get("adapter_state") == "skeleton_defined_not_active"
        and adapter_skeleton.get("adapter_can_accept_orders") is False
    )

    internal_intent_formable = (
        adapter_intent.get("intent_ready") is True
        and adapter_intent.get("paper_intent_formable") is True
        and adapter_intent.get("paper_order_submission_enabled") is False
        and adapter_intent_contract.get("overall_ok") is True
    )

    k_design_boundary_ok = (
        k_decision.get("decision_ready") is True
        and k_decision.get("decision_state") == "design_only_ready_no_execution"
        and k_decision.get("paper_execution_permitted") is False
        and k_decision.get("live_execution_permitted") is False
        and k_decision_contract.get("overall_ok") is True
    )

    missing_prerequisites = readiness.get("missing_prerequisites") or []

    capability_rows = [
        {
            "capability": "adapter_interface_surface_defined",
            "available": skeleton_surface_defined,
            "submission_enabled": False,
            "meaning": "adapter 的接口面已经定义，但当前仍不可提交 paper order / The adapter interface surface is defined but cannot submit paper orders yet.",
        },
        {
            "capability": "internal_transition_intent_formable",
            "available": internal_intent_formable,
            "submission_enabled": False,
            "meaning": "内部 paper transition intent 包已可形成，但仍仅限 design-only / Internal paper transition intent envelope can be formed, but remains design-only.",
        },
        {
            "capability": "paper_order_submission",
            "available": False,
            "submission_enabled": False,
            "meaning": "真正的 paper order submission 仍关闭 / Real paper order submission remains closed.",
        },
        {
            "capability": "live_order_submission",
            "available": False,
            "submission_enabled": False,
            "meaning": "live order submission 仍明确关闭 / Live order submission remains explicitly closed.",
        },
    ]

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not skeleton_surface_defined:
        blockers.append("adapter_skeleton_surface_not_defined")
    if not internal_intent_formable:
        blockers.append("adapter_internal_intent_not_formable")
    if not k_design_boundary_ok:
        blockers.append("k_design_boundary_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    capability_ready = len(blockers) == 0
    capability_state = (
        "adapter_capability_defined_intent_only"
        if capability_ready
        else "adapter_capability_not_ready"
    )

    obj: Dict[str, Any] = {
        "capability_type": "bybit_demo_paper_adapter_capability",
        "capability_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "capability_state": capability_state,
        "capability_ready": capability_ready,
        "intent_only_capability": capability_ready,
        "paper_order_submission_enabled": False,
        "live_order_submission_enabled": False,
        "runtime_still_protected": runtime_still_protected,
        "missing_prerequisites": missing_prerequisites,
        "source_refs": {
            "adapter_skeleton_ts_ms": adapter_skeleton.get("ts_ms"),
            "adapter_intent_ts_ms": adapter_intent.get("ts_ms"),
            "adapter_intent_contract_ts_ms": adapter_intent_contract.get("ts_ms"),
            "k_decision_ts_ms": k_decision.get("ts_ms"),
            "k_decision_contract_ts_ms": k_decision_contract.get("ts_ms"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "capability_matrix": capability_rows,
        "capability_summary": {
            "surface_defined": skeleton_surface_defined,
            "internal_intent_formable": internal_intent_formable,
            "paper_submission_enabled": False,
            "live_submission_enabled": False,
            "missing_prerequisite_count": len(missing_prerequisites),
        },
        "blockers": blockers,
        "capability_explainer": {
            "adapter_capability_defined_intent_only": (
                "adapter 目前已经具备 intent-only 能力：可以承接 J->K 语义链并形成内部 paper intent 包，"
                "但不能提交 paper order。"
            ),
            "adapter_capability_not_ready": (
                "adapter 当前还不能形成稳定的 capability 视图。"
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
