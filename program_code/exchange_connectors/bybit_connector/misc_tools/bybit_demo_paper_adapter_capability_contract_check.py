#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 对 K 章 paper adapter capability latest 做 contract check。
- 这一步的目的，是把 adapter 当前的能力边界正式 contract 化：
  1. interface surface 已定义
  2. internal intent 已可形成
  3. paper/live order submission 仍关闭
- 这不是执行放权，而是对“能力已到哪一步、仍不能做什么”的结构化校验。

English:
- Contract-check the K paper-adapter capability latest artifact.
- The purpose is to formalize the current adapter capability boundary:
  1. interface surface is defined,
  2. internal intent is formable,
  3. paper/live order submission remain closed.
- This is not execution enablement. It is a structured validation of what the adapter
  can already do and what it must still NOT do.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    """Locate repo root without hard-coded machine-specific absolute paths.
    中文：避免未来维护继续依赖单机路径。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for adapter capability contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
CAPABILITY_PATH = BASE / "bybit_demo_paper_adapter_capability_latest.json"
OUT_LATEST = BASE / "bybit_demo_paper_adapter_capability_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_demo_paper_adapter_capability_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []

    exists = CAPABILITY_PATH.exists()
    checks.append(check("capability_latest_exists", exists, str(CAPABILITY_PATH)))

    capability: Dict[str, Any] = {}
    if exists:
        capability = load_json(CAPABILITY_PATH)

    checks.append(check("capability_type_ok", capability.get("capability_type") == "bybit_demo_paper_adapter_capability", capability.get("capability_type")))
    checks.append(check("chapter_ok", capability.get("chapter") == "K", capability.get("chapter")))
    checks.append(check(
        "capability_state_ok",
        capability.get("capability_state") in {"adapter_capability_defined_intent_only", "adapter_capability_not_ready"},
        capability.get("capability_state"),
    ))
    checks.append(check("capability_ready_bool", isinstance(capability.get("capability_ready"), bool), capability.get("capability_ready")))
    checks.append(check("intent_only_capability_bool", isinstance(capability.get("intent_only_capability"), bool), capability.get("intent_only_capability")))
    checks.append(check("paper_order_submission_disabled", capability.get("paper_order_submission_enabled") is False, capability.get("paper_order_submission_enabled")))
    checks.append(check("live_order_submission_disabled", capability.get("live_order_submission_enabled") is False, capability.get("live_order_submission_enabled")))
    checks.append(check("runtime_still_protected_bool", isinstance(capability.get("runtime_still_protected"), bool), capability.get("runtime_still_protected")))
    checks.append(check("missing_prerequisites_list", isinstance(capability.get("missing_prerequisites"), list), capability.get("missing_prerequisites")))
    checks.append(check("blockers_list", isinstance(capability.get("blockers"), list), capability.get("blockers")))

    summary = capability.get("capability_summary") or {}
    checks.append(check("surface_defined_bool", isinstance(summary.get("surface_defined"), bool), summary.get("surface_defined")))
    checks.append(check("internal_intent_formable_bool", isinstance(summary.get("internal_intent_formable"), bool), summary.get("internal_intent_formable")))
    checks.append(check("paper_submission_enabled_false", summary.get("paper_submission_enabled") is False, summary.get("paper_submission_enabled")))
    checks.append(check("live_submission_enabled_false", summary.get("live_submission_enabled") is False, summary.get("live_submission_enabled")))
    checks.append(check("missing_prerequisite_count_int", isinstance(summary.get("missing_prerequisite_count"), int), summary.get("missing_prerequisite_count")))

    matrix = capability.get("capability_matrix") or []
    checks.append(check("capability_matrix_list", isinstance(matrix, list), type(matrix).__name__))
    if isinstance(matrix, list):
        names = [row.get("capability") for row in matrix if isinstance(row, dict)]
    else:
        names = []
    required_names = {
        "adapter_interface_surface_defined",
        "internal_transition_intent_formable",
        "paper_order_submission",
        "live_order_submission",
    }
    checks.append(check("capability_matrix_contains_required_rows", required_names.issubset(set(names)), names))

    failed_checks = [c for c in checks if not c["ok"]]
    obj: Dict[str, Any] = {
        "contract_type": "bybit_demo_paper_adapter_capability_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "capability_shape_valid": len(failed_checks) == 0,
            "intent_only_boundary_preserved": (
                capability.get("paper_order_submission_enabled") is False
                and capability.get("live_order_submission_enabled") is False
                and summary.get("paper_submission_enabled") is False
                and summary.get("live_submission_enabled") is False
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
