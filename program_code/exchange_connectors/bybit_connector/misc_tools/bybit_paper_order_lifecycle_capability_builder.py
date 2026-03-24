#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 在 K 章已有 adapter capability / K decision / readiness 基线之上，
  补一层更接近真实 paper order lifecycle 的 capability 聚合层。
- 这一层不是为了打开下单，而是为了把“paper order lifecycle 现在到底已经定义到了什么程度”
  用统一、可机读、可人工审核的方式表达出来。
- 当前目标是：
  1. 把 lifecycle 的状态机骨架明确下来；
  2. 把哪些状态已定义、哪些路径仍必须关闭表达清楚；
  3. 明确 submission 仍关闭，因此 `paper_order_lifecycle_ready` 还不能改成 true。

English:
- On top of the existing K adapter capability / K decision / readiness baseline,
  add a more lifecycle-facing capability aggregation layer.
- The goal is NOT to open order submission.
- The goal is to describe, in a machine-readable and human-auditable way,
  how far the paper order lifecycle has been defined.
- Current objectives are:
  1. define the lifecycle state-machine skeleton clearly,
  2. express which states are already defined and which paths must still remain closed,
  3. make it explicit that submission is still closed, so `paper_order_lifecycle_ready`
     must still remain false.

Safety boundary / 安全边界：
- paper order submission remains disabled
- live order submission remains disabled
- no order authority is granted
- this file does not open paper execution or live execution
- 本文件不会打开 paper/live execution，也不会授予下单 authority。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    """Locate repo root without machine-specific absolute paths.
    中文：避免后续维护时继续依赖单机路径。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for paper order lifecycle capability builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "adapter_capability": BASE / "bybit_demo_paper_adapter_capability_latest.json",
    "adapter_capability_contract": BASE / "bybit_demo_paper_adapter_capability_contract_latest.json",
    "k_decision": BASE / "bybit_demo_gate_decision_latest.json",
    "k_decision_contract": BASE / "bybit_demo_gate_decision_contract_latest.json",
    "readiness": BASE / "bybit_demo_gate_readiness_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_paper_order_lifecycle_capability_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    BASE.mkdir(parents=True, exist_ok=True)
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_paper_order_lifecycle_capability_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded: Dict[str, Dict[str, Any]] = {
        name: load_json(path) for name, path in PATHS.items() if path.exists()
    }

    adapter_capability = loaded.get("adapter_capability", {})
    adapter_capability_contract = loaded.get("adapter_capability_contract", {})
    k_decision = loaded.get("k_decision", {})
    k_decision_contract = loaded.get("k_decision_contract", {})
    readiness = loaded.get("readiness", {})
    runtime = loaded.get("runtime", {})

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    adapter_intent_only_ok = (
        adapter_capability.get("capability_ready") is True
        and adapter_capability.get("intent_only_capability") is True
        and adapter_capability.get("paper_order_submission_enabled") is False
        and adapter_capability.get("live_order_submission_enabled") is False
        and adapter_capability_contract.get("overall_ok") is True
    )

    k_design_no_execution_ok = (
        k_decision.get("decision_ready") is True
        and k_decision.get("decision_state") == "design_only_ready_no_execution"
        and k_decision.get("paper_execution_permitted") is False
        and k_decision.get("live_execution_permitted") is False
        and k_decision_contract.get("overall_ok") is True
    )

    missing_prerequisites = readiness.get("missing_prerequisites") or []

    lifecycle_states = [
        {
            "state": "intent_received_design_only",
            "defined": True,
            "enterable_now": True,
            "meaning": "已收到内部 paper intent 包，但仍是 design-only / Internal paper intent envelope received, still design-only.",
        },
        {
            "state": "pre_submission_blocked",
            "defined": True,
            "enterable_now": True,
            "meaning": "由于 lifecycle / projection / risk / audit 未完成，submission 仍必须阻断 / Submission remains blocked because lifecycle/projection/risk/audit are incomplete.",
        },
        {
            "state": "paper_pending_simulated",
            "defined": True,
            "enterable_now": False,
            "meaning": "未来 paper order 被接受后进入 pending 状态 / Future paper order pending state after acceptance.",
        },
        {
            "state": "paper_acknowledged",
            "defined": True,
            "enterable_now": False,
            "meaning": "未来模拟确认态 / Future simulated acknowledged state.",
        },
        {
            "state": "paper_partially_filled",
            "defined": True,
            "enterable_now": False,
            "meaning": "未来部分成交态 / Future partially-filled simulated state.",
        },
        {
            "state": "paper_filled",
            "defined": True,
            "enterable_now": False,
            "meaning": "未来完全成交态 / Future fully-filled simulated state.",
        },
        {
            "state": "paper_canceled",
            "defined": True,
            "enterable_now": False,
            "meaning": "未来取消态 / Future canceled simulated state.",
        },
        {
            "state": "paper_rejected",
            "defined": True,
            "enterable_now": False,
            "meaning": "未来拒绝态 / Future rejected simulated state.",
        },
    ]

    lifecycle_edges = [
        {
            "edge": "intent_to_pre_submission_blocked",
            "available": True,
            "submission_enabled": False,
            "meaning": "当前唯一真实可走路径：收到 intent 后仍然阻断 submission / Current only real path: receive intent then keep submission blocked.",
        },
        {
            "edge": "intent_to_pending_simulated",
            "available": False,
            "submission_enabled": False,
            "meaning": "未来真正 paper lifecycle ready 后，才可能进入 pending / Only after real paper lifecycle readiness may pending become available.",
        },
        {
            "edge": "pending_to_acknowledged",
            "available": False,
            "submission_enabled": False,
            "meaning": "未来模拟确认流 / Future simulated acknowledge flow.",
        },
        {
            "edge": "acknowledged_to_partially_filled_or_filled",
            "available": False,
            "submission_enabled": False,
            "meaning": "未来模拟成交流 / Future simulated fill flow.",
        },
        {
            "edge": "pending_or_acknowledged_to_canceled",
            "available": False,
            "submission_enabled": False,
            "meaning": "未来模拟取消流 / Future simulated cancel flow.",
        },
    ]

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not adapter_intent_only_ok:
        blockers.append("adapter_capability_not_green")
    if not k_design_no_execution_ok:
        blockers.append("k_design_decision_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    lifecycle_capability_ready = len(blockers) == 0
    lifecycle_state = (
        "state_model_defined_submission_closed"
        if lifecycle_capability_ready
        else "lifecycle_capability_not_ready"
    )

    obj: Dict[str, Any] = {
        "lifecycle_type": "bybit_paper_order_lifecycle_capability",
        "lifecycle_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "lifecycle_state": lifecycle_state,
        "lifecycle_ready": False,
        "lifecycle_can_accept_new_orders": False,
        "internal_lifecycle_model_defined": lifecycle_capability_ready,
        "submission_path_closed": True,
        "live_submission_closed": True,
        "runtime_still_protected": runtime_still_protected,
        "missing_prerequisites": missing_prerequisites,
        "source_refs": {
            "adapter_capability_ts_ms": adapter_capability.get("ts_ms"),
            "adapter_capability_contract_ts_ms": adapter_capability_contract.get("ts_ms"),
            "k_decision_ts_ms": k_decision.get("ts_ms"),
            "k_decision_contract_ts_ms": k_decision_contract.get("ts_ms"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "lifecycle_states": lifecycle_states,
        "lifecycle_edges": lifecycle_edges,
        "lifecycle_summary": {
            "state_count": len(lifecycle_states),
            "edge_count": len(lifecycle_edges),
            "internal_lifecycle_model_defined": lifecycle_capability_ready,
            "lifecycle_can_accept_new_orders": False,
            "submission_path_closed": True,
            "missing_prerequisite_count": len(missing_prerequisites),
        },
        "blockers": blockers,
        "lifecycle_explainer": {
            "state_model_defined_submission_closed": (
                "paper order lifecycle 的状态机骨架已经被定义出来，但当前 submission path 仍必须关闭，"
                "因此 lifecycle_ready 仍保持 false。"
            ),
            "lifecycle_capability_not_ready": (
                "paper order lifecycle 当前还不能形成稳定的 capability 视图。"
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
