#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 对 K 章 transition intake latest 做 contract check。
- 确认 intake 仍然只表达 design-only accepted，
  不会错误打开 paper execution 或 live execution。

English:
- Contract-check the K transition intake latest artifact.
- Confirm the intake only expresses design-only acceptance,
  without opening paper execution or live execution.
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
    raise RuntimeError("repo root not found for demo gate transition intake contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
INTAKE_PATH = BASE / "bybit_demo_gate_transition_intake_latest.json"
OUT_LATEST = BASE / "bybit_demo_gate_transition_intake_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_demo_gate_transition_intake_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []

    exists = INTAKE_PATH.exists()
    checks.append(check("intake_latest_exists", exists, str(INTAKE_PATH)))

    intake: Dict[str, Any] = {}
    if exists:
        intake = load_json(INTAKE_PATH)

    checks.append(check("intake_type_ok", intake.get("intake_type") == "bybit_demo_gate_transition_intake", intake.get("intake_type")))
    checks.append(check("chapter_ok", intake.get("chapter") == "K", intake.get("chapter")))
    checks.append(check("intake_state_ok", intake.get("intake_state") in {"transition_candidate_accepted_for_k_design_only", "transition_candidate_not_accepted"}, intake.get("intake_state")))
    checks.append(check("intake_ready_bool", isinstance(intake.get("intake_ready"), bool), intake.get("intake_ready")))
    checks.append(check("accepted_for_design_only_bool", isinstance(intake.get("accepted_for_design_only"), bool), intake.get("accepted_for_design_only")))
    checks.append(check("paper_execution_open_false", intake.get("paper_execution_open") is False, intake.get("paper_execution_open")))
    checks.append(check("live_execution_open_false", intake.get("live_execution_open") is False, intake.get("live_execution_open")))
    checks.append(check("blockers_list", isinstance(intake.get("blockers"), list), intake.get("blockers")))

    transition_intake = intake.get("transition_intake") or {}
    checks.append(check("j_decision_ready_bool", isinstance(transition_intake.get("j_decision_ready"), bool), transition_intake.get("j_decision_ready")))
    checks.append(check("k_summary_ok_bool", isinstance(transition_intake.get("k_summary_ok"), bool), transition_intake.get("k_summary_ok")))
    checks.append(check("k_gate_can_open_false", transition_intake.get("k_gate_can_open") is False, transition_intake.get("k_gate_can_open")))
    checks.append(check("k_operator_can_enable_false", transition_intake.get("k_operator_can_enable") is False, transition_intake.get("k_operator_can_enable")))
    checks.append(check("runtime_still_protected_bool", isinstance(transition_intake.get("runtime_still_protected"), bool), transition_intake.get("runtime_still_protected")))

    failed_checks = [c for c in checks if not c["ok"]]
    obj: Dict[str, Any] = {
        "contract_type": "bybit_demo_gate_transition_intake_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "intake_shape_valid": len(failed_checks) == 0,
            "design_only_boundary_preserved": (
                intake.get("paper_execution_open") is False
                and intake.get("live_execution_open") is False
                and transition_intake.get("k_gate_can_open") is False
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
