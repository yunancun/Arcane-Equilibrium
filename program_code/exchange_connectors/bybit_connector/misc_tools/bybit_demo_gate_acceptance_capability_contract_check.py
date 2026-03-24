#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 对 K 章 demo gate acceptance capability latest 做 contract check。
- 这一步的目的，是把 acceptance 当前的能力边界正式 contract 化：
  1. acceptance 模型面已经定义；
  2. acceptance 当前仍不能打开 demo gate；
  3. acceptance path 仍保持关闭；
  4. paper/live execution 都没有被打开。
- 这不是打开 demo gate，而是把“acceptance 控制面已经定义到哪一步、仍不能做什么”
  用结构化方式固定下来。

English:
- Contract-check the K demo gate acceptance capability latest artifact.
- The goal is to formalize the current acceptance boundary:
  1. the acceptance model surface is defined,
  2. acceptance still cannot open the demo gate,
  3. the acceptance path remains closed,
  4. paper/live execution are not opened.
- This does NOT open the demo gate. It structurally fixes how far the model has been defined
  and what it must still NOT do.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List


def get_repo_root() -> Path:
    """Locate repo root without machine-specific absolute paths.
    中文：避免维护继续依赖单机路径。
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docker_projects").exists() and (parent / "program_code").exists():
            return parent
    raise RuntimeError("repo root not found for acceptance capability contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
ACCEPTANCE_PATH = BASE / "bybit_demo_gate_acceptance_capability_latest.json"
OUT_LATEST = BASE / "bybit_demo_gate_acceptance_capability_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_demo_gate_acceptance_capability_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []

    exists = ACCEPTANCE_PATH.exists()
    checks.append(check("acceptance_latest_exists", exists, str(ACCEPTANCE_PATH)))

    acceptance: Dict[str, Any] = {}
    if exists:
        acceptance = load_json(ACCEPTANCE_PATH)

    checks.append(check("acceptance_type_ok", acceptance.get("acceptance_type") == "bybit_demo_gate_acceptance_capability", acceptance.get("acceptance_type")))
    checks.append(check("chapter_ok", acceptance.get("chapter") == "K", acceptance.get("chapter")))
    checks.append(check(
        "acceptance_state_ok",
        acceptance.get("acceptance_state") in {"acceptance_model_defined_gate_closed", "acceptance_capability_not_ready"},
        acceptance.get("acceptance_state"),
    ))
    checks.append(check("acceptance_ready_false", acceptance.get("acceptance_ready") is False, acceptance.get("acceptance_ready")))
    checks.append(check("acceptance_can_open_demo_gate_false", acceptance.get("acceptance_can_open_demo_gate") is False, acceptance.get("acceptance_can_open_demo_gate")))
    checks.append(check("acceptance_can_enable_paper_execution_false", acceptance.get("acceptance_can_enable_paper_execution") is False, acceptance.get("acceptance_can_enable_paper_execution")))
    checks.append(check("gate_path_closed_true", acceptance.get("gate_path_closed") is True, acceptance.get("gate_path_closed")))
    checks.append(check("live_acceptance_path_closed_true", acceptance.get("live_acceptance_path_closed") is True, acceptance.get("live_acceptance_path_closed")))
    checks.append(check("runtime_still_protected_bool", isinstance(acceptance.get("runtime_still_protected"), bool), acceptance.get("runtime_still_protected")))
    checks.append(check("missing_prerequisites_list", isinstance(acceptance.get("missing_prerequisites"), list), acceptance.get("missing_prerequisites")))
    checks.append(check("blockers_list", isinstance(acceptance.get("blockers"), list), acceptance.get("blockers")))

    components = acceptance.get("acceptance_components") or []
    checks.append(check("acceptance_components_list", isinstance(components, list), type(components).__name__))
    if isinstance(components, list):
        component_names = [row.get("component") for row in components if isinstance(row, dict)]
    else:
        component_names = []
    required_components = {
        "acceptance_prerequisite_matrix_model",
        "operator_explicit_enable_requirement_model",
        "runtime_protection_confirmation_model",
        "chapter_consistency_acceptance_model",
    }
    checks.append(check("required_components_present", required_components.issubset(set(component_names)), component_names))

    summary = acceptance.get("acceptance_summary") or {}
    checks.append(check("component_count_int", isinstance(summary.get("component_count"), int), summary.get("component_count")))
    checks.append(check("acceptance_model_defined_bool", isinstance(summary.get("acceptance_model_defined"), bool), summary.get("acceptance_model_defined")))
    checks.append(check("summary_acceptance_can_open_false", summary.get("acceptance_can_open_demo_gate") is False, summary.get("acceptance_can_open_demo_gate")))
    checks.append(check("summary_gate_path_closed_true", summary.get("gate_path_closed") is True, summary.get("gate_path_closed")))
    checks.append(check("summary_missing_prereq_count_int", isinstance(summary.get("missing_prerequisite_count"), int), summary.get("missing_prerequisite_count")))

    failed_checks = [c for c in checks if not c["ok"]]
    obj: Dict[str, Any] = {
        "contract_type": "bybit_demo_gate_acceptance_capability_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "acceptance_shape_valid": len(failed_checks) == 0,
            "gate_closed_boundary_preserved": (
                acceptance.get("acceptance_can_open_demo_gate") is False
                and acceptance.get("acceptance_can_enable_paper_execution") is False
                and acceptance.get("gate_path_closed") is True
                and acceptance.get("live_acceptance_path_closed") is True
                and summary.get("acceptance_can_open_demo_gate") is False
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
