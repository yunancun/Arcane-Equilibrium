#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K operator switch capability contract check / K operator 开关能力 contract 校验。
当前只校验形状与关闭边界，不打开任何执行路径。
This validates shape and closed-boundary semantics only. It does not open any execution path.
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
    raise RuntimeError("repo root not found for operator switch capability contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
SWITCH_PATH = BASE / "bybit_explicit_operator_enable_switch_capability_latest.json"
OUT_LATEST = BASE / "bybit_explicit_operator_enable_switch_capability_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_explicit_operator_enable_switch_capability_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []
    exists = SWITCH_PATH.exists()
    checks.append(check("switch_latest_exists", exists, str(SWITCH_PATH)))
    switch: Dict[str, Any] = load_json(SWITCH_PATH) if exists else {}

    checks.append(check("switch_type_ok", switch.get("switch_type") == "bybit_explicit_operator_enable_switch_capability", switch.get("switch_type")))
    checks.append(check("chapter_ok", switch.get("chapter") == "K", switch.get("chapter")))
    checks.append(check("switch_state_ok", switch.get("switch_state") in {"operator_switch_defined_locked_closed", "operator_switch_capability_not_ready"}, switch.get("switch_state")))
    checks.append(check("switch_ready_false", switch.get("switch_ready") is False, switch.get("switch_ready")))
    checks.append(check("operator_enable_available_false", switch.get("operator_enable_available") is False, switch.get("operator_enable_available")))
    checks.append(check("explicit_enable_required_true", switch.get("explicit_enable_required") is True, switch.get("explicit_enable_required")))
    checks.append(check("operator_path_closed_true", switch.get("operator_path_closed") is True, switch.get("operator_path_closed")))
    checks.append(check("live_operator_path_closed_true", switch.get("live_operator_path_closed") is True, switch.get("live_operator_path_closed")))
    checks.append(check("runtime_still_protected_bool", isinstance(switch.get("runtime_still_protected"), bool), switch.get("runtime_still_protected")))
    checks.append(check("missing_prerequisites_list", isinstance(switch.get("missing_prerequisites"), list), switch.get("missing_prerequisites")))
    checks.append(check("blockers_list", isinstance(switch.get("blockers"), list), switch.get("blockers")))

    components = switch.get("switch_components") or []
    checks.append(check("switch_components_list", isinstance(components, list), type(components).__name__))
    names = [row.get("component") for row in components if isinstance(row, dict)] if isinstance(components, list) else []
    required = {"operator_enable_flag_model", "operator_enable_scope_model", "operator_enable_audit_binding_model", "operator_disable_relock_model"}
    checks.append(check("required_components_present", required.issubset(set(names)), names))

    summary = switch.get("switch_summary") or {}
    checks.append(check("component_count_int", isinstance(summary.get("component_count"), int), summary.get("component_count")))
    checks.append(check("switch_model_defined_bool", isinstance(summary.get("switch_model_defined"), bool), summary.get("switch_model_defined")))
    checks.append(check("summary_operator_enable_false", summary.get("operator_enable_available") is False, summary.get("operator_enable_available")))
    checks.append(check("summary_operator_path_closed_true", summary.get("operator_path_closed") is True, summary.get("operator_path_closed")))
    checks.append(check("summary_missing_prereq_count_int", isinstance(summary.get("missing_prerequisite_count"), int), summary.get("missing_prerequisite_count")))

    failed_checks = [c for c in checks if not c["ok"]]
    obj = {
        "contract_type": "bybit_explicit_operator_enable_switch_capability_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "switch_shape_valid": len(failed_checks) == 0,
            "operator_path_closed_boundary_preserved": (
                switch.get("operator_enable_available") is False
                and switch.get("operator_path_closed") is True
                and switch.get("live_operator_path_closed") is True
                and summary.get("operator_enable_available") is False
            ),
        },
    }
    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
