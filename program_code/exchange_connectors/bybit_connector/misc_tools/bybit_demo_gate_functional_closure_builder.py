#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K concentrated closeout / K 集中收口

中文：
- 把 K 章现有 canonical 基线与今晚新增的 capability / contract 层统一收口。
- 该层的目标不是打开 demo gate 或 paper/live execution，而是给出一个最终机器可读结论：
  K 章是否已经达到“functional closeout ready, still design-only gate closed”的状态。
- 这层把旧的 K canonical 结果与今晚新增的 capability 链合并成一个更高层闭环对象。

English:
- Concentrate the existing canonical K baseline together with tonight's capability / contract layers.
- The goal is NOT to open the demo gate or any paper/live execution. The goal is to emit one final
  machine-readable verdict for whether K has reached
  "functional closeout ready, still design-only gate closed".
- This layer merges the old canonical K results with tonight's capability chains into one higher-level closeout object.
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
    raise RuntimeError("repo root not found for K functional closure builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "summary": BASE / "bybit_demo_gate_summary_latest.json",
    "handoff": BASE / "bybit_demo_gate_handoff_latest.json",
    "final_audit": BASE / "bybit_demo_gate_final_audit_latest.json",
    "chapter_consistency": BASE / "bybit_demo_gate_chapter_consistency_latest.json",
    "decision": BASE / "bybit_demo_gate_decision_latest.json",
    "decision_contract": BASE / "bybit_demo_gate_decision_contract_latest.json",
    "adapter_contract": BASE / "bybit_demo_paper_adapter_capability_contract_latest.json",
    "lifecycle_contract": BASE / "bybit_paper_order_lifecycle_capability_contract_latest.json",
    "projection_contract": BASE / "bybit_paper_position_balance_projection_capability_contract_latest.json",
    "risk_contract": BASE / "bybit_pretrade_risk_gate_capability_contract_latest.json",
    "audit_contract": BASE / "bybit_paper_audit_trail_capability_contract_latest.json",
    "switch_contract": BASE / "bybit_explicit_operator_enable_switch_capability_contract_latest.json",
    "acceptance_contract": BASE / "bybit_demo_gate_acceptance_capability_contract_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_demo_gate_functional_closure_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_demo_gate_functional_closure_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded = {name: load_json(path) for name, path in PATHS.items() if path.exists()}

    summary = loaded.get("summary", {})
    handoff = loaded.get("handoff", {})
    final_audit = loaded.get("final_audit", {})
    chapter_consistency = loaded.get("chapter_consistency", {})
    decision = loaded.get("decision", {})
    decision_contract = loaded.get("decision_contract", {})
    runtime = loaded.get("runtime", {})

    old_chain_green = (
        summary.get("summary_ok") is True
        and (handoff.get("current_status") or {}).get("summary_ok") is True
        and final_audit.get("overall_ok") is True
        and chapter_consistency.get("overall_ok") is True
    )

    decision_green = (
        decision.get("decision_ready") is True
        and decision.get("decision_state") == "design_only_ready_no_execution"
        and decision.get("paper_execution_permitted") is False
        and decision.get("live_execution_permitted") is False
        and decision.get("gate_can_open") is False
        and decision.get("operator_can_enable") is False
        and decision_contract.get("overall_ok") is True
    )

    capability_contracts_green = all([
        loaded.get("adapter_contract", {}).get("overall_ok") is True,
        loaded.get("lifecycle_contract", {}).get("overall_ok") is True,
        loaded.get("projection_contract", {}).get("overall_ok") is True,
        loaded.get("risk_contract", {}).get("overall_ok") is True,
        loaded.get("audit_contract", {}).get("overall_ok") is True,
        loaded.get("switch_contract", {}).get("overall_ok") is True,
        loaded.get("acceptance_contract", {}).get("overall_ok") is True,
    ])

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not old_chain_green:
        blockers.append("old_k_canonical_chain_not_green")
    if not decision_green:
        blockers.append("new_k_decision_chain_not_green")
    if not capability_contracts_green:
        blockers.append("k_capability_contract_chain_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    closeout_ready = len(blockers) == 0
    closeout_state = (
        "functional_closeout_ready_design_only_gate_closed"
        if closeout_ready
        else "functional_closeout_not_ready"
    )

    obj = {
        "closure_type": "bybit_demo_gate_functional_closure",
        "closure_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "closeout_state": closeout_state,
        "closeout_ready": closeout_ready,
        "old_canonical_chain_green": old_chain_green,
        "decision_chain_green": decision_green,
        "capability_contract_chain_green": capability_contracts_green,
        "runtime_still_protected": runtime_still_protected,
        "paper_execution_permitted": False,
        "live_execution_permitted": False,
        "gate_can_open": False,
        "operator_can_enable": False,
        "source_refs": {
            "summary_ts_ms": summary.get("ts_ms"),
            "handoff_ts_ms": handoff.get("ts_ms"),
            "final_audit_ts_ms": final_audit.get("ts_ms"),
            "chapter_consistency_ts_ms": chapter_consistency.get("ts_ms"),
            "decision_ts_ms": decision.get("ts_ms"),
            "decision_contract_ts_ms": decision_contract.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "blockers": blockers,
        "closure_explainer": {
            "functional_closeout_ready_design_only_gate_closed": "K 章已经完成本轮集中收口，但仍严格保持 design-only gate closed，不打开任何 execution。",
            "functional_closeout_not_ready": "K 章当前还不能被视为本轮功能收口完成。",
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
