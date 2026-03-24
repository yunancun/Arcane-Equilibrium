#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
K functional supplement / K 功能层补齐

中文：
- 对 K 章 paper audit trail capability latest 做 contract check。
- 这一步的目的，是把 audit trail 当前的能力边界正式 contract 化：
  1. audit 模型面已经定义；
  2. audit 仍不能记录真实完整的 paper execution flow；
  3. audit path 仍保持关闭；
  4. paper/live execution 都没有被打开。
- 这不是放开 audit path，而是把“审计模型已经定义到哪一步、仍不能做什么”
  用结构化方式固定下来。

English:
- Contract-check the K paper audit trail capability latest artifact.
- The goal is to formalize the current audit-trail boundary:
  1. the audit model surface is defined,
  2. the audit trail still cannot record a full real paper execution flow,
  3. the audit path remains closed,
  4. paper/live execution are not opened.
- This does NOT enable the audit path. It structurally fixes how far the model has been defined
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
    raise RuntimeError("repo root not found for audit capability contract check")


ROOT = get_repo_root()
BASE = ROOT / "docker_projects" / "trading_services" / "runtime" / "bybit" / "demo_gate"
AUDIT_PATH = BASE / "bybit_paper_audit_trail_capability_latest.json"
OUT_LATEST = BASE / "bybit_paper_audit_trail_capability_contract_latest.json"


def load_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: Any) -> Dict[str, Any]:
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj: Dict[str, Any]) -> Path:
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_paper_audit_trail_capability_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main() -> None:
    checks: List[Dict[str, Any]] = []

    exists = AUDIT_PATH.exists()
    checks.append(check("audit_latest_exists", exists, str(AUDIT_PATH)))

    audit: Dict[str, Any] = {}
    if exists:
        audit = load_json(AUDIT_PATH)

    checks.append(check("audit_type_ok", audit.get("audit_type") == "bybit_paper_audit_trail_capability", audit.get("audit_type")))
    checks.append(check("chapter_ok", audit.get("chapter") == "K", audit.get("chapter")))
    checks.append(check(
        "audit_state_ok",
        audit.get("audit_state") in {"audit_model_defined_path_closed", "audit_capability_not_ready"},
        audit.get("audit_state"),
    ))
    checks.append(check("audit_ready_false", audit.get("audit_ready") is False, audit.get("audit_ready")))
    checks.append(check("audit_can_record_execution_flow_false", audit.get("audit_can_record_execution_flow") is False, audit.get("audit_can_record_execution_flow")))
    checks.append(check("internal_audit_model_defined_bool", isinstance(audit.get("internal_audit_model_defined"), bool), audit.get("internal_audit_model_defined")))
    checks.append(check("audit_path_closed_true", audit.get("audit_path_closed") is True, audit.get("audit_path_closed")))
    checks.append(check("live_audit_path_closed_true", audit.get("live_audit_path_closed") is True, audit.get("live_audit_path_closed")))
    checks.append(check("runtime_still_protected_bool", isinstance(audit.get("runtime_still_protected"), bool), audit.get("runtime_still_protected")))
    checks.append(check("missing_prerequisites_list", isinstance(audit.get("missing_prerequisites"), list), audit.get("missing_prerequisites")))
    checks.append(check("blockers_list", isinstance(audit.get("blockers"), list), audit.get("blockers")))

    components = audit.get("audit_components") or []
    checks.append(check("audit_components_list", isinstance(components, list), type(components).__name__))
    if isinstance(components, list):
        component_names = [row.get("component") for row in components if isinstance(row, dict)]
    else:
        component_names = []
    required_components = {
        "order_intent_record_model",
        "lifecycle_transition_record_model",
        "projection_change_record_model",
        "risk_verdict_record_model",
        "operator_action_record_model",
        "rejection_reason_record_model",
    }
    checks.append(check("required_components_present", required_components.issubset(set(component_names)), component_names))

    summary = audit.get("audit_summary") or {}
    checks.append(check("component_count_int", isinstance(summary.get("component_count"), int), summary.get("component_count")))
    checks.append(check("summary_model_defined_bool", isinstance(summary.get("internal_audit_model_defined"), bool), summary.get("internal_audit_model_defined")))
    checks.append(check("summary_record_flow_false", summary.get("audit_can_record_execution_flow") is False, summary.get("audit_can_record_execution_flow")))
    checks.append(check("summary_audit_path_closed_true", summary.get("audit_path_closed") is True, summary.get("audit_path_closed")))
    checks.append(check("summary_missing_prereq_count_int", isinstance(summary.get("missing_prerequisite_count"), int), summary.get("missing_prerequisite_count")))

    failed_checks = [c for c in checks if not c["ok"]]
    obj: Dict[str, Any] = {
        "contract_type": "bybit_paper_audit_trail_capability_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "contract_summary": {
            "audit_shape_valid": len(failed_checks) == 0,
            "audit_path_closed_boundary_preserved": (
                audit.get("audit_can_record_execution_flow") is False
                and audit.get("audit_path_closed") is True
                and audit.get("live_audit_path_closed") is True
                and summary.get("audit_can_record_execution_flow") is False
            ),
        },
    }

    dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()
