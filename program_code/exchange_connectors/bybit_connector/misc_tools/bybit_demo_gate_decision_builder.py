#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 在 K 章已有 summary / final audit / chapter consistency / transition intake / intake contract 的基础上，
  增加一个统一的 K decision 聚合层。
- 该 decision 用来表达：K 章当前已经能稳定接收 J 章 transition candidate，
  且 K 自身 design-only gate 基线成立，但 execution 仍必须关闭。
- 这不是 paper execution decision，更不是 live execution decision。

English:
- Add a unified K decision aggregation layer on top of summary / final audit /
  chapter consistency / transition intake / intake contract.
- The decision expresses that K can stably receive the J transition candidate,
  while the K design-only gate baseline is valid and execution must remain closed.
- This is not a paper-execution decision and definitely not a live-execution decision.
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
    raise RuntimeError("repo root not found for demo gate decision builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "intake": BASE / "bybit_demo_gate_transition_intake_latest.json",
    "intake_contract": BASE / "bybit_demo_gate_transition_intake_contract_latest.json",
    "readiness": BASE / "bybit_demo_gate_readiness_latest.json",
    "summary": BASE / "bybit_demo_gate_summary_latest.json",
    "handoff": BASE / "bybit_demo_gate_handoff_latest.json",
    "final_audit": BASE / "bybit_demo_gate_final_audit_latest.json",
    "chapter_consistency": BASE / "bybit_demo_gate_chapter_consistency_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_demo_gate_decision_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_demo_gate_decision_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded: Dict[str, Dict[str, Any]] = {
        name: load_json(path) for name, path in PATHS.items() if path.exists()
    }

    intake = loaded.get("intake", {})
    intake_contract = loaded.get("intake_contract", {})
    readiness = loaded.get("readiness", {})
    summary = loaded.get("summary", {})
    handoff = loaded.get("handoff", {})
    final_audit = loaded.get("final_audit", {})
    chapter_consistency = loaded.get("chapter_consistency", {})
    runtime = loaded.get("runtime", {})

    intake_ok = (
        intake.get("intake_ready") is True
        and intake.get("accepted_for_design_only") is True
        and intake.get("paper_execution_open") is False
        and intake.get("live_execution_open") is False
    )
    intake_contract_ok = intake_contract.get("overall_ok") is True

    readiness_state = readiness.get("readiness_state")
    readiness_shape_ok = readiness_state in {
        "not_ready_missing_prerequisites",
        "ready_but_operator_locked",
    }

    summary_ok = (
        summary.get("summary_ok") is True
        and summary.get("summary_state") == "design_layers_defined_gate_closed"
        and summary.get("gate_can_open") is False
        and summary.get("operator_can_enable") is False
    )

    handoff_ok = (
        (handoff.get("current_status") or {}).get("summary_ok") is True
        and (handoff.get("current_status") or {}).get("gate_can_open") is False
        and (handoff.get("current_status") or {}).get("operator_can_enable") is False
    )

    final_audit_ok = final_audit.get("overall_ok") is True
    chapter_consistency_ok = chapter_consistency.get("overall_ok") is True

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not intake_ok:
        blockers.append("transition_intake_not_ready")
    if not intake_contract_ok:
        blockers.append("transition_intake_contract_not_green")
    if not readiness_shape_ok:
        blockers.append("readiness_state_invalid")
    if not summary_ok:
        blockers.append("summary_not_design_only_closed")
    if not handoff_ok:
        blockers.append("handoff_not_aligned")
    if not final_audit_ok:
        blockers.append("final_audit_not_green")
    if not chapter_consistency_ok:
        blockers.append("chapter_consistency_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    decision_ready = len(blockers) == 0
    decision_state = (
        "design_only_ready_no_execution"
        if decision_ready
        else "design_only_not_ready"
    )
    decision_code = (
        "k_design_only_gate_structurally_ready_execution_closed"
        if decision_ready
        else "k_design_only_gate_not_ready"
    )

    obj: Dict[str, Any] = {
        "decision_type": "bybit_demo_gate_decision",
        "decision_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "K",
        "chapter_meaning": "Paper / Demo Gate",
        "decision_state": decision_state,
        "decision_code": decision_code,
        "decision_ready": decision_ready,
        "accepted_for_design_only": decision_ready,
        "paper_execution_permitted": False,
        "live_execution_permitted": False,
        "gate_can_open": False,
        "operator_can_enable": False,
        "runtime_still_protected": runtime_still_protected,
        "readiness_state": readiness_state,
        "missing_prerequisites": readiness.get("missing_prerequisites") or [],
        "source_refs": {
            "intake_ts_ms": intake.get("ts_ms"),
            "intake_contract_ts_ms": intake_contract.get("ts_ms"),
            "readiness_ts_ms": readiness.get("ts_ms"),
            "summary_ts_ms": summary.get("ts_ms"),
            "handoff_ts_ms": handoff.get("ts_ms"),
            "final_audit_ts_ms": final_audit.get("ts_ms"),
            "chapter_consistency_ts_ms": chapter_consistency.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "decision_inputs": {
            "intake_state": intake.get("intake_state"),
            "intake_ready": intake.get("intake_ready"),
            "intake_contract_ok": intake_contract.get("overall_ok"),
            "summary_state": summary.get("summary_state"),
            "summary_ok": summary.get("summary_ok"),
            "handoff_summary_ok": (handoff.get("current_status") or {}).get("summary_ok"),
            "final_audit_ok": final_audit.get("overall_ok"),
            "chapter_consistency_ok": chapter_consistency.get("overall_ok"),
            "runtime_system_mode": runtime.get("system_mode"),
            "runtime_execution_state": runtime.get("execution_state"),
        },
        "blockers": blockers,
        "decision_explainer": {
            "design_only_ready_no_execution": (
                "K 章当前已形成统一 decision，表示其 design-only gate 基线稳定成立，"
                "并能安全接收来自 J 章的 transition candidate；execution 仍必须关闭。"
            ),
            "design_only_not_ready": (
                "K 章当前还不能形成稳定的 design-only 统一 decision。"
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
