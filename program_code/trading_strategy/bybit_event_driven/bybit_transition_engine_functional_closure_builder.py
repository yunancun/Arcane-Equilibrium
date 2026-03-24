#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
J concentrated closeout / J 集中收口

中文：
- 把 J 章现有 canonical 基线与今晚新增的 functional decision / contract 层统一收口。
- 该层的目标不是打开 demo/live execution，而是给出一个最终机器可读结论：
  J 章是否已经达到“functional closeout ready, still shadow/skeleton only”的状态。
- 这层把 J 的旧 canonical 结果与新 decision 层合并成一个更高层闭环对象。

English:
- Concentrate the existing canonical J baseline together with tonight's functional
  decision / contract layers.
- The goal is NOT to open demo/live execution. The goal is to emit one final
  machine-readable verdict for whether J has reached
  "functional closeout ready, still shadow/skeleton only".
- This layer merges the old canonical J results with the new decision layer into
  one higher-level closeout object.
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
    raise RuntimeError("repo root not found for J functional closure builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "event_driven" / "transition_engine"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "summary": BASE / "bybit_transition_engine_summary_latest.json",
    "handoff": BASE / "bybit_transition_engine_handoff_latest.json",
    "final_audit": BASE / "bybit_transition_engine_final_audit_latest.json",
    "chapter_consistency": BASE / "bybit_transition_engine_chapter_consistency_latest.json",
    "decision": BASE / "bybit_transition_engine_decision_latest.json",
    "decision_contract": BASE / "bybit_transition_engine_decision_contract_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_transition_engine_functional_closure_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_transition_engine_functional_closure_{obj['ts_ms']}.json"
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

    summary_final = summary.get("final_status") or {}
    handoff_current = handoff.get("current_status") or {}

    old_chain_green = (
        summary_final.get("transition_engine_skeleton_ready") is True
        and handoff_current.get("transition_engine_skeleton_ready") is True
        and final_audit.get("overall_ok") is True
        and chapter_consistency.get("overall_ok") is True
    )

    new_decision_green = (
        decision.get("decision_ready") is True
        and decision.get("decision_state") == "candidate_transition_ready_skeleton_only"
        and decision.get("execution_permitted") is False
        and decision.get("demo_gate_open") is False
        and decision.get("live_execution_open") is False
        and decision_contract.get("overall_ok") is True
    )

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not old_chain_green:
        blockers.append("old_j_canonical_chain_not_green")
    if not new_decision_green:
        blockers.append("new_j_decision_chain_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    closeout_ready = len(blockers) == 0
    closeout_state = (
        "functional_closeout_ready_shadow_only"
        if closeout_ready
        else "functional_closeout_not_ready"
    )

    obj = {
        "closure_type": "bybit_transition_engine_functional_closure",
        "closure_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "J",
        "chapter_meaning": "Transition Engine Skeleton",
        "closeout_state": closeout_state,
        "closeout_ready": closeout_ready,
        "old_canonical_chain_green": old_chain_green,
        "new_decision_chain_green": new_decision_green,
        "runtime_still_protected": runtime_still_protected,
        "execution_permitted": False,
        "demo_gate_open": False,
        "live_execution_open": False,
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
            "functional_closeout_ready_shadow_only": "J 章已经完成本轮集中收口，但仍严格保持 shadow/skeleton-only，不打开任何 execution。",
            "functional_closeout_not_ready": "J 章当前还不能被视为本轮功能收口完成。",
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
