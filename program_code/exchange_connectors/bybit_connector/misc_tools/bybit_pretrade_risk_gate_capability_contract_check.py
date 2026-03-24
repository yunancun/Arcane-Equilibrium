#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 对 K 章 pretrade risk gate capability latest 做 contract check。
- 这一步的目的，是把 risk gate 当前的能力边界正式 contract 化：
  1. risk 模型面已经定义；
  2. risk gate 仍不能真实评估并放行 paper order；
  3. risk gate 路径仍保持关闭；
  4. paper/live execution 都没有被打开。
- 这不是放开 risk gate，而是把“风险模型已经定义到哪一步、仍不能做什么”
  用结构化方式固定下来。

English:
- Contract-check the K pretrade risk gate capability latest artifact.
- The goal is to formalize the current risk-gate boundary:
  1. the risk model surface is defined,
  2. the risk gate still cannot evaluate and approve real paper orders,
  3. the risk-gate path remains closed,
  4. paper/live execution are not opened.
- This does NOT enable the risk gate. It structurally fixes how far the model has been defined
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
    raise RuntimeError("repo root not found for risk capability contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
RISK_PATH = BASE / "bybit_pretrade_risk_gate_capability_latest.json"
OUT_LATEST = BASE / "bybit_pretrade_risk_gate_capability_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_pretrade_risk_gate_capability_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []

    exists = RISK_PATH.exists()
    checks.append(check("risk_latest_exists", exists, str(RISK_PATH)))

    risk: Dict[str, Any] = {}
    if exists:
        risk = load_json(RISK_PATH)

    checks.append(check("risk_type_ok", risk.get("risk_type") == "bybit_pretrade_risk_gate_capability", risk.get("risk_type")))
    checks.append(check("chapter_ok", risk.get("chapter") == "K", risk.get("chapter")))
    checks.append(check(
        "risk_state_ok",
        risk.get("risk_state") in {"risk_model_defined_gate_closed", "risk_capability_not_ready"},
        risk.get("risk_state"),
    ))
    checks.append(check("risk_ready_false", risk.get("risk_ready") is False, risk.get("risk_ready")))
    checks.append(check("risk_can_evaluate_orders_false", risk.get("risk_can_evaluate_orders") is False, risk.get("risk_can_evaluate_orders")))
    checks.append(check("internal_risk_model_defined_bool", isinstance(risk.get("internal_risk_model_defined"), bool), risk.get("internal_risk_model_defined")))
    checks.append(check("risk_gate_closed_true", risk.get("risk_gate_closed") is True, risk.get("risk_gate_closed")))
    checks.append(check("live_risk_path_closed_true", risk.get("live_risk_path_closed") is True, risk.get("live_risk_path_closed")))
    checks.append(check("runtime_still_protected_bool", isinstance(risk.get("runtime_still_protected"), bool), risk.get("runtime_still_protected")))
    checks.append(check("missing_prerequisites_list", isinstance(risk.get("missing_prerequisites"), list), risk.get("missing_prerequisites")))
    checks.append(check("blockers_list", isinstance(risk.get("blockers"), list), risk.get("blockers")))

    components = risk.get("risk_components") or []
    checks.append(check("risk_components_list", isinstance(components, list), type(components).__name__))
    if isinstance(components, list):
        component_names = [row.get("component") for row in components if isinstance(row, dict)]
    else:
        component_names = []
    required_components = {
        "order_size_guard_model",
        "order_notional_guard_model",
        "duplicate_submission_guard_model",
        "state_conflict_guard_model",
        "cooldown_guard_model",
        "exposure_guard_model",
    }
    checks.append(check("required_components_present", required_components.issubset(set(component_names)), component_names))

    summary = risk.get("risk_summary") or {}
    checks.append(check("component_count_int", isinstance(summary.get("component_count"), int), summary.get("component_count")))
    checks.append(check("summary_model_defined_bool", isinstance(summary.get("internal_risk_model_defined"), bool), summary.get("internal_risk_model_defined")))
    checks.append(check("summary_evaluate_orders_false", summary.get("risk_can_evaluate_orders") is False, summary.get("risk_can_evaluate_orders")))
    checks.append(check("summary_risk_gate_closed_true", summary.get("risk_gate_closed") is True, summary.get("risk_gate_closed")))
    checks.append(check("summary_missing_prereq_count_int", isinstance(summary.get("missing_prerequisite_count"), int), summary.get("missing_prerequisite_count")))

    failed_checks = [c for c in checks if not c["ok"]]
    obj: Dict[str, Any] = {
        "contract_type": "bybit_pretrade_risk_gate_capability_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "risk_shape_valid": len(failed_checks) == 0,
            "risk_gate_closed_boundary_preserved": (
                risk.get("risk_can_evaluate_orders") is False
                and risk.get("risk_gate_closed") is True
                and risk.get("live_risk_path_closed") is True
                and summary.get("risk_can_evaluate_orders") is False
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
