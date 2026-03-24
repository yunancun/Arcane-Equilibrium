#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 对 K 章 paper order lifecycle capability latest 做 contract check。
- 这一步的目的，是把 lifecycle 当前的能力边界正式 contract 化：
  1. lifecycle 的状态机骨架已经定义；
  2. 当前只能走 intent -> pre_submission_blocked 这条关闭路径；
  3. lifecycle 仍不能接受新订单；
  4. paper / live submission 仍保持关闭。
- 这不是放开 paper execution，而是把“生命周期模型已定义到哪一步、哪些边界仍不能突破”
  用结构化方式固定下来。

English:
- Contract-check the K paper-order-lifecycle capability latest artifact.
- The goal is to formalize the current lifecycle boundary:
  1. the lifecycle state-machine skeleton is defined,
  2. only the closed path intent -> pre_submission_blocked is available now,
  3. lifecycle still cannot accept new orders,
  4. paper/live submission remain closed.
- This is NOT paper-execution enablement. It is a structured validation of how far the
  lifecycle model has been defined and which boundaries must still remain closed.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    """Locate repo root without machine-specific absolute paths.
    中文：避免未来维护继续依赖单机路径。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for lifecycle capability contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
LIFECYCLE_PATH = BASE / "bybit_paper_order_lifecycle_capability_latest.json"
OUT_LATEST = BASE / "bybit_paper_order_lifecycle_capability_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_paper_order_lifecycle_capability_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []

    exists = LIFECYCLE_PATH.exists()
    checks.append(check("lifecycle_latest_exists", exists, str(LIFECYCLE_PATH)))

    lifecycle: Dict[str, Any] = {}
    if exists:
        lifecycle = load_json(LIFECYCLE_PATH)

    checks.append(check("lifecycle_type_ok", lifecycle.get("lifecycle_type") == "bybit_paper_order_lifecycle_capability", lifecycle.get("lifecycle_type")))
    checks.append(check("chapter_ok", lifecycle.get("chapter") == "K", lifecycle.get("chapter")))
    checks.append(check(
        "lifecycle_state_ok",
        lifecycle.get("lifecycle_state") in {"state_model_defined_submission_closed", "lifecycle_capability_not_ready"},
        lifecycle.get("lifecycle_state"),
    ))
    checks.append(check("lifecycle_ready_false", lifecycle.get("lifecycle_ready") is False, lifecycle.get("lifecycle_ready")))
    checks.append(check("lifecycle_can_accept_new_orders_false", lifecycle.get("lifecycle_can_accept_new_orders") is False, lifecycle.get("lifecycle_can_accept_new_orders")))
    checks.append(check("internal_lifecycle_model_defined_bool", isinstance(lifecycle.get("internal_lifecycle_model_defined"), bool), lifecycle.get("internal_lifecycle_model_defined")))
    checks.append(check("submission_path_closed_true", lifecycle.get("submission_path_closed") is True, lifecycle.get("submission_path_closed")))
    checks.append(check("live_submission_closed_true", lifecycle.get("live_submission_closed") is True, lifecycle.get("live_submission_closed")))
    checks.append(check("runtime_still_protected_bool", isinstance(lifecycle.get("runtime_still_protected"), bool), lifecycle.get("runtime_still_protected")))
    checks.append(check("missing_prerequisites_list", isinstance(lifecycle.get("missing_prerequisites"), list), lifecycle.get("missing_prerequisites")))
    checks.append(check("blockers_list", isinstance(lifecycle.get("blockers"), list), lifecycle.get("blockers")))

    states = lifecycle.get("lifecycle_states") or []
    edges = lifecycle.get("lifecycle_edges") or []
    checks.append(check("lifecycle_states_list", isinstance(states, list), type(states).__name__))
    checks.append(check("lifecycle_edges_list", isinstance(edges, list), type(edges).__name__))

    if isinstance(states, list):
        state_names = [row.get("state") for row in states if isinstance(row, dict)]
    else:
        state_names = []
    required_states = {
        "intent_received_design_only",
        "pre_submission_blocked",
        "paper_pending_simulated",
        "paper_acknowledged",
        "paper_partially_filled",
        "paper_filled",
        "paper_canceled",
        "paper_rejected",
    }
    checks.append(check("required_states_present", required_states.issubset(set(state_names)), state_names))

    if isinstance(edges, list):
        edge_names = [row.get("edge") for row in edges if isinstance(row, dict)]
    else:
        edge_names = []
    required_edges = {
        "intent_to_pre_submission_blocked",
        "intent_to_pending_simulated",
        "pending_to_acknowledged",
        "acknowledged_to_partially_filled_or_filled",
        "pending_or_acknowledged_to_canceled",
    }
    checks.append(check("required_edges_present", required_edges.issubset(set(edge_names)), edge_names))

    summary = lifecycle.get("lifecycle_summary") or {}
    checks.append(check("state_count_int", isinstance(summary.get("state_count"), int), summary.get("state_count")))
    checks.append(check("edge_count_int", isinstance(summary.get("edge_count"), int), summary.get("edge_count")))
    checks.append(check("summary_model_defined_bool", isinstance(summary.get("internal_lifecycle_model_defined"), bool), summary.get("internal_lifecycle_model_defined")))
    checks.append(check("summary_accept_new_orders_false", summary.get("lifecycle_can_accept_new_orders") is False, summary.get("lifecycle_can_accept_new_orders")))
    checks.append(check("summary_submission_closed_true", summary.get("submission_path_closed") is True, summary.get("submission_path_closed")))
    checks.append(check("summary_missing_prereq_count_int", isinstance(summary.get("missing_prerequisite_count"), int), summary.get("missing_prerequisite_count")))

    failed_checks = [c for c in checks if not c["ok"]]
    obj: Dict[str, Any] = {
        "contract_type": "bybit_paper_order_lifecycle_capability_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "lifecycle_shape_valid": len(failed_checks) == 0,
            "submission_closed_boundary_preserved": (
                lifecycle.get("lifecycle_can_accept_new_orders") is False
                and lifecycle.get("submission_path_closed") is True
                and lifecycle.get("live_submission_closed") is True
                and summary.get("lifecycle_can_accept_new_orders") is False
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
