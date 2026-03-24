#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 在不打开 demo gate 的前提下，为 K 章增加一个 transition intake 层。
- 该层读取 J 章统一 transition decision，生成 K 章 intake latest，
  用来表达“J 的 candidate 可被 K 章设计层安全接收”。
- 这里仍然只是 design-only / intake-only，不允许 paper execution，更不允许 live execution。

English:
- Add a transition intake layer for K without opening the demo gate.
- This layer reads the unified J transition decision and produces a K intake latest,
  expressing that J's candidate can be safely received by the K design layer.
- This remains design-only / intake-only; no paper execution and no live execution are allowed.
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
    raise RuntimeError("repo root not found for demo gate transition intake builder")


ROOT = get_repo_root()
J_DECISION_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "event_driven" / "transition_engine" / "bybit_transition_engine_decision_latest.json"
K_SUMMARY_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate" / "bybit_demo_gate_summary_latest.json"
K_FINAL_AUDIT_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate" / "bybit_demo_gate_final_audit_latest.json"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"
OUT_DIR = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
OUT_LATEST = OUT_DIR / "bybit_demo_gate_transition_intake_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_demo_gate_transition_intake_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = []
    for path in [J_DECISION_PATH, K_SUMMARY_PATH, K_FINAL_AUDIT_PATH, RUNTIME_PATH]:
        if not path.exists():
            missing.append(str(path))

    j_decision = load_json(J_DECISION_PATH) if J_DECISION_PATH.exists() else {}
    k_summary = load_json(K_SUMMARY_PATH) if K_SUMMARY_PATH.exists() else {}
    k_final_audit = load_json(K_FINAL_AUDIT_PATH) if K_FINAL_AUDIT_PATH.exists() else {}
    runtime = load_json(RUNTIME_PATH) if RUNTIME_PATH.exists() else {}

    j_ready = j_decision.get("decision_ready") is True
    j_state_ok = j_decision.get("decision_state") == "candidate_transition_ready_skeleton_only"
    j_next_gate_ok = j_decision.get("next_gate") == "K_demo_gate_design_only"

    k_design_closed = (
        k_summary.get("summary_ok") is True
        and k_summary.get("summary_state") == "design_layers_defined_gate_closed"
        and (k_summary.get("gate_can_open") is False)
        and (k_summary.get("operator_can_enable") is False)
        and k_final_audit.get("overall_ok") is True
    )

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    intake_ready = all([
        not missing,
        j_ready,
        j_state_ok,
        j_next_gate_ok,
        k_design_closed,
        runtime_still_protected,
    ])

    intake_state = "transition_candidate_accepted_for_k_design_only" if intake_ready else "transition_candidate_not_accepted"

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not j_ready:
        blockers.append("j_decision_not_ready")
    if not j_state_ok:
        blockers.append("j_decision_state_not_skeleton_only_ready")
    if not j_next_gate_ok:
        blockers.append("j_next_gate_not_k_design_only")
    if not k_design_closed:
        blockers.append("k_design_layer_not_closed")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    obj: Dict[str, Any] = {
        "intake_type": "bybit_demo_gate_transition_intake",
        "intake_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "intake_state": intake_state,
        "intake_ready": intake_ready,
        "accepted_for_design_only": intake_ready,
        "paper_execution_open": False,
        "live_execution_open": False,
        "source_refs": {
            "j_decision_ts_ms": j_decision.get("ts_ms"),
            "k_summary_ts_ms": k_summary.get("ts_ms"),
            "k_final_audit_ts_ms": k_final_audit.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "transition_intake": {
            "j_decision_state": j_decision.get("decision_state"),
            "j_decision_code": j_decision.get("decision_code"),
            "j_decision_ready": j_decision.get("decision_ready"),
            "j_candidate_transition_available": j_decision.get("candidate_transition_available"),
            "j_runtime_still_protected": j_decision.get("runtime_still_protected"),
            "k_summary_state": k_summary.get("summary_state"),
            "k_summary_ok": k_summary.get("summary_ok"),
            "k_gate_can_open": k_summary.get("gate_can_open"),
            "k_operator_can_enable": k_summary.get("operator_can_enable"),
            "k_final_audit_ok": k_final_audit.get("overall_ok"),
            "runtime_still_protected": runtime_still_protected,
        },
        "blockers": blockers,
        "intake_explainer": {
            "transition_candidate_accepted_for_k_design_only": (
                "J 章 candidate transition 已能以统一 decision 形式被 K 章安全接收，"
                "但当前仅限 design-only intake，不允许 paper/live execution。"
            ),
            "transition_candidate_not_accepted": (
                "K 章当前还不能把 J 的 transition candidate 当作稳定 intake。"
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
