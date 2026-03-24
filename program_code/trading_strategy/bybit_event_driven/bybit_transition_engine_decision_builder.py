#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
J functional supplement / J 功能层补齐

中文：
- 在现有 J skeleton 已闭环的基础上，补一个正式的 transition decision 聚合层。
- 该层把 matrix / audit / rule / graph / summary / handoff / final audit / runtime
  汇总成一个统一的机器可读 decision 对象。
- 这个 decision 只表示“candidate transition 在 skeleton 语义下成立，且可继续流向 K 章设计层”，
  并不表示 demo execution 或 live execution 被打开。

English:
- Add a formal transition-decision aggregation layer on top of the already-closed J skeleton.
- This layer consolidates matrix / audit / rule / graph / summary / handoff / final audit / runtime
  into one machine-readable decision object.
- The decision only means the candidate transition is structurally valid under skeleton semantics
  and may continue into the K design layer. It does not enable demo or live execution.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    """Locate repo root without relying on hard-coded absolute paths.
    中文：避免继续依赖硬编码绝对路径。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for transition decision builder")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "event_driven" / "transition_engine"
RUNTIME_PATH = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "bybit_runtime_state_latest.json"

PATHS = {
    "matrix": BASE / "bybit_transition_engine_replay_matrix_latest.json",
    "audit": BASE / "bybit_transition_engine_audit_trail_latest.json",
    "rule": BASE / "bybit_transition_rule_layer_latest.json",
    "graph": BASE / "bybit_transition_state_graph_latest.json",
    "graph_consistency": BASE / "bybit_transition_state_graph_consistency_latest.json",
    "summary": BASE / "bybit_transition_engine_summary_latest.json",
    "handoff": BASE / "bybit_transition_engine_handoff_latest.json",
    "final_audit": BASE / "bybit_transition_engine_final_audit_latest.json",
    "chapter_consistency": BASE / "bybit_transition_engine_chapter_consistency_latest.json",
    "runtime": RUNTIME_PATH,
}

OUT_LATEST = BASE / "bybit_transition_engine_decision_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_transition_engine_decision_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    missing: List[str] = [name for name, path in PATHS.items() if not path.exists()]
    loaded: Dict[str, Dict[str, Any]] = {
        name: load_json(path) for name, path in PATHS.items() if path.exists()
    }

    matrix = loaded.get("matrix", {})
    audit = loaded.get("audit", {})
    rule = loaded.get("rule", {})
    graph = loaded.get("graph", {})
    graph_consistency = loaded.get("graph_consistency", {})
    summary = loaded.get("summary", {})
    handoff = loaded.get("handoff", {})
    final_audit = loaded.get("final_audit", {})
    chapter_consistency = loaded.get("chapter_consistency", {})
    runtime = loaded.get("runtime", {})

    matrix_verdict = matrix.get("matrix_verdict") or {}
    trail_summary = audit.get("trail_summary") or {}
    layer_summary = rule.get("layer_summary") or {}
    graph_summary = graph.get("graph_summary") or {}
    summary_final = summary.get("final_status") or {}
    handoff_current = handoff.get("current_status") or {}

    runtime_still_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
        and summary_final.get("execution_permitted") is False
        and summary_final.get("demo_gate_open") is False
        and summary_final.get("live_execution_open") is False
    )

    candidate_transition_available = all([
        matrix_verdict.get("positive_path_open") is True,
        trail_summary.get("positive_case_verdict") == "candidate_open_but_execution_forbidden",
        layer_summary.get("positive_candidate_recognized") is True,
        graph_summary.get("positive_path_mapped") is True,
        summary_final.get("candidate_transition_supported") is True,
        handoff_current.get("candidate_transition_supported") is True,
    ])

    negative_path_protection_ok = all([
        matrix_verdict.get("negative_path_blocked") is True,
        trail_summary.get("negative_case_verdict") == "candidate_blocked",
        layer_summary.get("negative_candidate_blocked") is True,
        graph_summary.get("negative_path_mapped") is True,
        summary_final.get("negative_blocking_supported") is True,
        handoff_current.get("negative_blocking_supported") is True,
    ])

    consistency_ok = all([
        graph_consistency.get("overall_ok") is True,
        final_audit.get("overall_ok") is True,
        chapter_consistency.get("overall_ok") is True,
    ])

    blockers: List[str] = []
    if missing:
        blockers.append("missing_inputs")
    if not candidate_transition_available:
        blockers.append("candidate_transition_not_fully_supported")
    if not negative_path_protection_ok:
        blockers.append("negative_path_protection_not_fully_supported")
    if not consistency_ok:
        blockers.append("consistency_or_final_audit_not_green")
    if not runtime_still_protected:
        blockers.append("runtime_not_protected")

    decision_ready = len(blockers) == 0
    decision_state = (
        "candidate_transition_ready_skeleton_only"
        if decision_ready
        else "candidate_transition_blocked"
    )
    decision_code = (
        "candidate_transition_ready_for_k_design_gate"
        if decision_ready
        else "candidate_transition_not_ready_for_k_design_gate"
    )

    obj: Dict[str, Any] = {
        "decision_type": "bybit_transition_engine_decision",
        "decision_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "chapter": "J",
        "chapter_meaning": "Transition Engine Skeleton",
        "decision_state": decision_state,
        "decision_code": decision_code,
        "decision_ready": decision_ready,
        "candidate_transition_available": candidate_transition_available,
        "negative_path_protection_ok": negative_path_protection_ok,
        "consistency_ok": consistency_ok,
        "runtime_still_protected": runtime_still_protected,
        "next_gate": "K_demo_gate_design_only",
        "execution_permitted": False,
        "demo_gate_open": False,
        "live_execution_open": False,
        "source_refs": {
            "matrix_ts_ms": matrix.get("ts_ms"),
            "audit_ts_ms": audit.get("ts_ms"),
            "rule_ts_ms": rule.get("ts_ms"),
            "graph_ts_ms": graph.get("ts_ms"),
            "graph_consistency_ts_ms": graph_consistency.get("ts_ms"),
            "summary_ts_ms": summary.get("ts_ms"),
            "handoff_ts_ms": handoff.get("ts_ms"),
            "final_audit_ts_ms": final_audit.get("ts_ms"),
            "chapter_consistency_ts_ms": chapter_consistency.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "transition_decision": {
            "positive_path_open": matrix_verdict.get("positive_path_open"),
            "negative_path_blocked": matrix_verdict.get("negative_path_blocked"),
            "positive_case_verdict": trail_summary.get("positive_case_verdict"),
            "negative_case_verdict": trail_summary.get("negative_case_verdict"),
            "rule_layer_state": rule.get("rule_layer_state"),
            "graph_status": graph.get("graph_status"),
            "summary_ready": summary_final.get("transition_engine_skeleton_ready"),
            "handoff_ready": handoff_current.get("transition_engine_skeleton_ready"),
            "final_audit_ok": final_audit.get("overall_ok"),
            "chapter_consistency_ok": chapter_consistency.get("overall_ok"),
        },
        "blockers": blockers,
        "decision_explainer": {
            "candidate_transition_ready_skeleton_only": (
                "J 章已能产出统一 transition decision，表示 candidate transition 在 skeleton 语义下成立，"
                "并可继续流向 K 章设计层；这不代表 execution 被打开。"
            ),
            "candidate_transition_blocked": (
                "J 章仍存在缺口，当前不能把 transition candidate 作为稳定输入交给 K 章。"
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
