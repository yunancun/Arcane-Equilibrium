#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import os
from typing import Any, Dict, Optional

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

def bool_from_candidates(doc: Dict[str, Any], *paths: str) -> Optional[bool]:
    for path in paths:
        cur: Any = doc
        ok = True
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                ok = False
                break
            cur = cur[part]
        if ok and isinstance(cur, bool):
            return cur
    return None

def stage_closed_from_file(filename: str, stage_key: str) -> bool:
    doc = read_json_if_exists(BASE / filename)
    v = bool_from_candidates(
        doc,
        f"audit_summary.{stage_key}",
        f"chapter_summary.{stage_key}",
        stage_key,
        "overall_ok",
        "summary_ok",
        "audit_ok",
        "log_ok",
    )
    return bool(v is True)

def h2_stage_closed() -> bool:
    return stage_closed_from_file("bybit_query_budget_final_audit_latest.json", "h2_stage_closed")

def h4_stage_closed() -> bool:
    return stage_closed_from_file("bybit_compute_governor_final_audit_latest.json", "h4_stage_closed")

def h5_log_doc() -> Dict[str, Any]:
    return read_json_if_exists(BASE / "bybit_ai_cost_log_latest.json")

def h5_audit_doc() -> Dict[str, Any]:
    return read_json_if_exists(BASE / "bybit_ai_governance_audit_latest.json")

def h5_log_ok() -> bool:
    doc = h5_log_doc()
    if doc.get("log_ok") is True:
        return True
    return doc.get("log_state") in {"ai_cost_log_recorded", "ai_cost_log_recorded_soft_warn"}

def h5_governance_audit_ok() -> bool:
    doc = h5_audit_doc()
    if doc.get("audit_ok") is True:
        return True
    return doc.get("audit_state") in {"ai_governance_audit_passed", "ai_governance_audit_passed_soft_warn"}

def extract_within_timeout_hint() -> Optional[bool]:
    candidates = [
        BASE / "bybit_query_budget_runtime_latest.json",
        BASE / "bybit_query_budget_final_audit_latest.json",
    ]
    for p in candidates:
        doc = read_json_if_exists(p)
        for path in (
            "observed_last_call.within_timeout_hint",
            "runtime_summary.within_timeout_hint",
            "budget_assessment.within_timeout_hint",
            "audit_summary.within_timeout_hint",
            "within_timeout_hint",
        ):
            v = bool_from_candidates(doc, path)
            if isinstance(v, bool):
                return v
    return None
