#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
J functional supplement / J 功能层补齐

中文：
- 对 J 章统一 decision latest 做 contract check。
- 确认这个 decision 仍然只表达 skeleton-only candidate ready，
  且不会把 execution / demo gate / live gate 错误打开。

English:
- Contract-check the unified J transition decision latest artifact.
- Confirm the decision still only expresses skeleton-only candidate readiness,
  without opening execution, demo gate, or live gate.
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
    raise RuntimeError("repo root not found for transition decision contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "event_driven" / "transition_engine"
DECISION_PATH = BASE / "bybit_transition_engine_decision_latest.json"
OUT_LATEST = BASE / "bybit_transition_engine_decision_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_transition_engine_decision_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []

    exists = DECISION_PATH.exists()
    checks.append(check("decision_latest_exists", exists, str(DECISION_PATH)))

    decision: Dict[str, Any] = {}
    if exists:
        decision = load_json(DECISION_PATH)

    checks.append(check("decision_type_ok", decision.get("decision_type") == "bybit_transition_engine_decision", decision.get("decision_type")))
    checks.append(check("chapter_ok", decision.get("chapter") == "J", decision.get("chapter")))
    checks.append(check("decision_state_ok", decision.get("decision_state") in {"candidate_transition_ready_skeleton_only", "candidate_transition_blocked"}, decision.get("decision_state")))
    checks.append(check("decision_code_ok", isinstance(decision.get("decision_code"), str) and len(decision.get("decision_code")) > 0, decision.get("decision_code")))
    checks.append(check("decision_ready_bool", isinstance(decision.get("decision_ready"), bool), decision.get("decision_ready")))
    checks.append(check("candidate_transition_available_bool", isinstance(decision.get("candidate_transition_available"), bool), decision.get("candidate_transition_available")))
    checks.append(check("negative_path_protection_ok_bool", isinstance(decision.get("negative_path_protection_ok"), bool), decision.get("negative_path_protection_ok")))
    checks.append(check("consistency_ok_bool", isinstance(decision.get("consistency_ok"), bool), decision.get("consistency_ok")))
    checks.append(check("runtime_still_protected_bool", isinstance(decision.get("runtime_still_protected"), bool), decision.get("runtime_still_protected")))
    checks.append(check("next_gate_ok", decision.get("next_gate") == "K_demo_gate_design_only", decision.get("next_gate")))
    checks.append(check("execution_permitted_false", decision.get("execution_permitted") is False, decision.get("execution_permitted")))
    checks.append(check("demo_gate_open_false", decision.get("demo_gate_open") is False, decision.get("demo_gate_open")))
    checks.append(check("live_execution_open_false", decision.get("live_execution_open") is False, decision.get("live_execution_open")))
    checks.append(check("blockers_list", isinstance(decision.get("blockers"), list), decision.get("blockers")))

    failed_checks = [c for c in checks if not c["ok"]]
    obj: Dict[str, Any] = {
        "contract_type": "bybit_transition_engine_decision_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "decision_shape_valid": len(failed_checks) == 0,
            "skeleton_only_boundary_preserved": (
                decision.get("execution_permitted") is False
                and decision.get("demo_gate_open") is False
                and decision.get("live_execution_open") is False
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
