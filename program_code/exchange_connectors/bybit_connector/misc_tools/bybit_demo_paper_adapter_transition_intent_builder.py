#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 在 K 章现有 skeleton / design-only decision 基线之上，补一个更接近真实 simulator adapter 的
  transition-intent 聚合层。
- 该层读取：
  1. J 章统一 transition decision
  2. K 章 unified demo gate decision
  3. K 章已有 paper adapter skeleton
- 然后生成一个“paper adapter transition intent”对象，明确表达：
  - 当前 candidate transition 已经能被 adapter 层理解
  - 当前可以形成 paper-side intent envelope
  - 但 order submission 仍不能打开，因为 lifecycle / projection / risk / audit 仍未完成

English:
- On top of the existing K skeleton / design-only decision baseline, add a more functional
  simulator-adapter-facing transition-intent aggregation layer.
- This layer reads:
  1. the unified J transition decision
  2. the unified K demo gate decision
  3. the existing K paper adapter skeleton
- It then produces a paper-adapter transition-intent object which states:
  - the current candidate transition can already be understood by the adapter layer
  - a paper-side intent envelope can now be formed
  - but order submission must still remain closed because lifecycle / projection / risk / audit
    are not completed yet

Safety boundary / 安全边界：
- This file does NOT open paper execution.
- This file does NOT open live execution.
- This file does NOT grant order authority.
- 本文件不会打开 paper execution，不会打开 live execution，也不会授予下单 authority。
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    """Locate repo root without hard-coded machine-specific absolute paths.
    中文：避免再次把实现绑死在单机绝对路径上。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for paper adapter transition intent builder")


ROOT = get_repo_root()
DEMO_GATE_BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
TRANSITION_BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "event_driven" / "transition_engine"

PATHS = {
    "j_decision": TRANSITION_BASE / "bybit_transition_engine_decision_latest.json",
    "k_decision": DEMO_GATE_BASE / "bybit_demo_gate_decision_latest.json",
    "adapter_skeleton": DEMO_GATE_BASE / "bybit_demo_paper_adapter_skeleton_latest.json",
    "runtime": ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json",
}

OUT_LATEST = DEMO_GATE_BASE / "bybit_demo_paper_adapter_transition_intent_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    DEMO_GATE_BASE.mkdir(parents=True, exist_ok=True)
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = DEMO_GATE_BASE / f"bybit_demo_paper_adapter_transition_intent_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded: Dict[str, Dict[str, Any]] = {
        name: load_json(path) for name, path in PATHS.items() if path.exists()
    }

    j_decision = loaded.get("j_decision", {})
    k_decision = loaded.get("k_decision", {})
    adapter_skeleton = loaded.get("adapter_skeleton", {})
    runtime = loaded.get("runtime", {})

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    j_transition_ok = (
        j_decision.get("decision_ready") is True
        and j_decision.get("decision_state") == "candidate_transition_ready_skeleton_only"
        and j_decision.get("execution_permitted") is False
        and j_decision.get("demo_gate_open") is False
        and j_decision.get("live_execution_open") is False
    )

    k_design_ok = (
        k_decision.get("decision_ready") is True
        and k_decision.get("decision_state") == "design_only_ready_no_execution"
        and k_decision.get("paper_execution_permitted") is False
        and k_decision.get("live_execution_permitted") is False
        and k_decision.get("gate_can_open") is False
        and k_decision.get("operator_can_enable") is False
    )

    adapter_surface_defined = (
        adapter_skeleton.get("adapter_state") == "skeleton_defined_not_active"
        and adapter_skeleton.get("adapter_can_accept_orders") is False
    )

    intent_ready = all([
        not missing,
        j_transition_ok,
        k_design_ok,
        adapter_surface_defined,
        runtime_still_protected,
    ])

    # Important semantic distinction / 关键语义区分：
    # intent_ready=True means the adapter layer can FORM an internal paper intent envelope.
    # It does NOT mean the system may SUBMIT a paper order.
    # intent_ready=True 只代表 adapter 层已经可以形成内部 paper intent 包，
    # 不代表系统可以提交 paper order。
    paper_intent_formable = intent_ready
    paper_order_submission_enabled = False
    live_order_submission_enabled = False

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not j_transition_ok:
        blockers.append("j_transition_decision_not_ready")
    if not k_design_ok:
        blockers.append("k_design_decision_not_ready")
    if not adapter_surface_defined:
        blockers.append("adapter_surface_not_defined")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    intent_state = (
        "paper_transition_intent_formable_design_only"
        if intent_ready
        else "paper_transition_intent_not_formable"
    )

    order_template = {
        "exchange": "bybit",
        "mode": "paper_design_only",
        "order_authority_granted": False,
        "submission_enabled": False,
        "required_future_fields": [
            "symbol",
            "side",
            "order_type",
            "quantity",
            "price_or_trigger_rule",
            "risk_envelope_ref",
            "lifecycle_id",
            "audit_ref",
        ],
        "reason": "intent envelope only; lifecycle / projection / risk / audit are still incomplete",
    }

    obj: Dict[str, Any] = {
        "intent_type": "bybit_demo_paper_adapter_transition_intent",
        "intent_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "intent_state": intent_state,
        "intent_ready": intent_ready,
        "paper_intent_formable": paper_intent_formable,
        "paper_order_submission_enabled": paper_order_submission_enabled,
        "live_order_submission_enabled": live_order_submission_enabled,
        "runtime_still_protected": runtime_still_protected,
        "source_refs": {
            "j_decision_ts_ms": j_decision.get("ts_ms"),
            "k_decision_ts_ms": k_decision.get("ts_ms"),
            "adapter_skeleton_ts_ms": adapter_skeleton.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "transition_adapter_view": {
            "j_decision_state": j_decision.get("decision_state"),
            "j_decision_code": j_decision.get("decision_code"),
            "k_decision_state": k_decision.get("decision_state"),
            "k_decision_code": k_decision.get("decision_code"),
            "adapter_state": adapter_skeleton.get("adapter_state"),
            "adapter_ready": adapter_skeleton.get("adapter_ready"),
            "adapter_can_accept_orders": adapter_skeleton.get("adapter_can_accept_orders"),
        },
        "paper_order_intent_template": order_template,
        "blockers": blockers,
        "intent_explainer": {
            "paper_transition_intent_formable_design_only": (
                "当前 J->K->adapter 语义链已经足以形成内部 paper transition intent 包，"
                "但这仍然只是 design-only / intake-only，不能提交 paper order。"
            ),
            "paper_transition_intent_not_formable": (
                "当前 adapter 层还不能稳定形成 paper transition intent。"
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
