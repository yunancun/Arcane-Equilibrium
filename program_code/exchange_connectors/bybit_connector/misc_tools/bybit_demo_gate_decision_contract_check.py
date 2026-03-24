#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 对 K 章统一 decision latest 做 contract check。
- 确认该 decision 只表达 design-only ready / no-execution，
  不会错误打开 paper execution / live execution / gate enable。

English:
- Contract-check the unified K decision latest artifact.
- Confirm the decision only expresses design-only ready / no-execution,
  without opening paper execution, live execution, or gate enable.
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
    raise RuntimeError("repo root not found for demo gate decision contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
DECISION_PATH = BASE / "bybit_demo_gate_decision_latest.json"
OUT_LATEST = BASE / "bybit_demo_gate_decision_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_demo_gate_decision_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []

    exists = DECISION_PATH.exists()
    checks.append(check("decision_latest_exists", exists, str(DECISION_PATH)))

    decision: Dict[str, Any] = {}
    if exists:
        decision = load_json(DECISION_PATH)

    checks.append(check("decision_type_ok", decision.get("decision_type") == "bybit_demo_gate_decision", decision.get("decision_type")))
    checks.append(check("chapter_ok", decision.get("chapter") == "K", decision.get("chapter")))
    checks.append(check("decision_state_ok", decision.get("decision_state") in {"design_only_ready_no_execution", "design_only_not_ready"}, decision.get("decision_state")))
    checks.append(check("decision_code_ok", isinstance(decision.get("decision_code"), str) and len(decision.get("decision_code")) > 0, decision.get("decision_code")))
    checks.append(check("decision_ready_bool", isinstance(decision.get("decision_ready"), bool), decision.get("decision_ready")))
    checks.append(check("accepted_for_design_only_bool", isinstance(decision.get("accepted_for_design_only"), bool), decision.get("accepted_for_design_only")))
    checks.append(check("paper_execution_permitted_false", decision.get("paper_execution_permitted") is False, decision.get("paper_execution_permitted")))
    checks.append(check("live_execution_permitted_false", decision.get("live_execution_permitted") is False, decision.get("live_execution_permitted")))
    checks.append(check("gate_can_open_false", decision.get("gate_can_open") is False, decision.get("gate_can_open")))
    checks.append(check("operator_can_enable_false", decision.get("operator_can_enable") is False, decision.get("operator_can_enable")))
    checks.append(check("runtime_still_protected_bool", isinstance(decision.get("runtime_still_protected"), bool), decision.get("runtime_still_protected")))
    checks.append(check("missing_prerequisites_list", isinstance(decision.get("missing_prerequisites"), list), decision.get("missing_prerequisites")))
    checks.append(check("blockers_list", isinstance(decision.get("blockers"), list), decision.get("blockers")))

    decision_inputs = decision.get("decision_inputs") or {}
    checks.append(check("intake_ready_bool", isinstance(decision_inputs.get("intake_ready"), bool), decision_inputs.get("intake_ready")))
    checks.append(check("intake_contract_ok_bool", isinstance(decision_inputs.get("intake_contract_ok"), bool), decision_inputs.get("intake_contract_ok")))
    checks.append(check("summary_ok_bool", isinstance(decision_inputs.get("summary_ok"), bool), decision_inputs.get("summary_ok")))
    checks.append(check("handoff_summary_ok_bool", isinstance(decision_inputs.get("handoff_summary_ok"), bool), decision_inputs.get("handoff_summary_ok")))
    checks.append(check("final_audit_ok_bool", isinstance(decision_inputs.get("final_audit_ok"), bool), decision_inputs.get("final_audit_ok")))
    checks.append(check("chapter_consistency_ok_bool", isinstance(decision_inputs.get("chapter_consistency_ok"), bool), decision_inputs.get("chapter_consistency_ok")))
    checks.append(check("runtime_system_mode_read_only", decision_inputs.get("runtime_system_mode") == "read_only", decision_inputs.get("runtime_system_mode")))
    checks.append(check("runtime_execution_state_disabled", decision_inputs.get("runtime_execution_state") == "disabled", decision_inputs.get("runtime_execution_state")))

    failed_checks = [c for c in checks if not c["ok"]]
    obj: Dict[str, Any] = {
        "contract_type": "bybit_demo_gate_decision_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "decision_shape_valid": len(failed_checks) == 0,
            "design_only_no_execution_boundary_preserved": (
                decision.get("paper_execution_permitted") is False
                and decision.get("live_execution_permitted") is False
                and decision.get("gate_can_open") is False
                and decision.get("operator_can_enable") is False
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
