#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import os
from typing import Any, Dict, List, Optional

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

SOFT_WARN_FLAGS = {
    "recent_trade_last_price_missing",
    "recent_trade_last_ts_missing",
    "runtime_state_reference_old",
    "freshness_soft_warning_present",
    "last_trade_fields_missing",
}

def _read(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

def _dedup(xs: Optional[List[Any]]) -> List[Any]:
    out: List[Any] = []
    seen = set()
    for x in xs or []:
        k = json.dumps(x, ensure_ascii=False, sort_keys=True) if isinstance(x, (dict, list)) else repr(x)
        if k not in seen:
            seen.add(k)
            out.append(x)
    return out

def _get_bool(doc: Dict[str, Any], *paths: str) -> Optional[bool]:
    for path in paths:
        cur: Any = doc
        ok = True
        for p in path.split("."):
            if not isinstance(cur, dict) or p not in cur:
                ok = False
                break
            cur = cur[p]
        if ok and isinstance(cur, bool):
            return cur
    return None

def _stage_closed(filename: str, key: str) -> bool:
    doc = _read(BASE / filename)
    v = _get_bool(
        doc,
        f"audit_summary.{key}",
        f"chapter_summary.{key}",
        key,
        "overall_ok",
        "summary_ok",
        "audit_ok",
        "log_ok",
    )
    return bool(v is True)

def authoritative_h2_closed() -> bool:
    return _stage_closed("bybit_query_budget_final_audit_latest.json", "h2_stage_closed")

def authoritative_h4_closed() -> bool:
    return _stage_closed("bybit_compute_governor_final_audit_latest.json", "h4_stage_closed")

def authoritative_h5_log_ok() -> bool:
    doc = _read(BASE / "bybit_ai_cost_log_latest.json")
    if doc.get("log_ok") is True:
        return True
    return doc.get("log_state") in {"ai_cost_log_recorded", "ai_cost_log_recorded_soft_warn"}

def authoritative_h5_audit_ok() -> bool:
    doc = _read(BASE / "bybit_ai_governance_audit_latest.json")
    if doc.get("audit_ok") is True:
        return True
    return doc.get("audit_state") in {"ai_governance_audit_passed", "ai_governance_audit_passed_soft_warn"}

def authoritative_within_timeout_hint() -> Optional[bool]:
    for fn in [
        "bybit_query_budget_runtime_latest.json",
        "bybit_query_budget_final_audit_latest.json",
    ]:
        doc = _read(BASE / fn)
        v = _get_bool(
            doc,
            "observed_last_call.within_timeout_hint",
            "runtime_summary.within_timeout_hint",
            "budget_assessment.within_timeout_hint",
            "audit_summary.within_timeout_hint",
            "within_timeout_hint",
        )
        if isinstance(v, bool):
            return v
    return None

def patch_ai_cost_log_report(report: Dict[str, Any]) -> Dict[str, Any]:
    report = dict(report or {})
    warning_flags = _dedup(report.get("warning_flags"))
    blocking_reasons = _dedup(report.get("blocking_reasons"))

    h4_closed = authoritative_h4_closed()
    blocking_reasons = [x for x in blocking_reasons if x != "h4_not_closed"]
    if not h4_closed:
        blocking_reasons.append("h4_not_closed")

    cost_log = dict(report.get("cost_log") or {})
    perf = dict(cost_log.get("performance_summary") or {})
    hinted = authoritative_within_timeout_hint()
    if hinted is not None:
        perf["within_timeout_hint"] = hinted
    cost_log["performance_summary"] = perf
    report["cost_log"] = cost_log

    report["warning_flags"] = warning_flags
    report["blocking_reasons"] = blocking_reasons

    if blocking_reasons:
        report["log_ok"] = False
        report["log_state"] = "ai_cost_log_blocked"
    else:
        report["log_ok"] = True
        report["log_state"] = "ai_cost_log_recorded_soft_warn" if warning_flags else "ai_cost_log_recorded"

    return report

def patch_ai_governance_audit_report(report: Dict[str, Any]) -> Dict[str, Any]:
    report = dict(report or {})
    warning_flags = _dedup(report.get("warning_flags"))
    failed_checks = _dedup(report.get("failed_checks"))
    blocking_reasons = _dedup(report.get("blocking_reasons"))

    h2_closed = authoritative_h2_closed()
    h4_closed = authoritative_h4_closed()
    h5_log_ok = authoritative_h5_log_ok()

    failed_checks = [x for x in failed_checks if x not in {"h2_stage_closed", "h4_stage_closed", "ai_cost_log_ok"}]
    if not h2_closed:
        failed_checks.append("h2_stage_closed")
    if not h4_closed:
        failed_checks.append("h4_stage_closed")
    if not h5_log_ok:
        failed_checks.append("ai_cost_log_ok")

    report["warning_flags"] = warning_flags
    report["failed_checks"] = failed_checks
    report["blocking_reasons"] = blocking_reasons
    report["failed_count"] = len(failed_checks)

    if failed_checks or blocking_reasons:
        report["audit_ok"] = False
        report["audit_state"] = "ai_governance_audit_blocked"
    else:
        report["audit_ok"] = True
        report["audit_state"] = "ai_governance_audit_passed_soft_warn" if warning_flags else "ai_governance_audit_passed"

    return report

def patch_ai_cost_governance_final_audit_report(report: Dict[str, Any]) -> Dict[str, Any]:
    report = dict(report or {})
    warning_flags = _dedup(report.get("warning_flags"))
    failed_checks = _dedup(report.get("failed_checks"))

    h4_closed = authoritative_h4_closed()
    h5_log_ok = authoritative_h5_log_ok()
    h5_audit_ok = authoritative_h5_audit_ok()

    failed_checks = [x for x in failed_checks if x not in {"h4_stage_closed", "h5_log_ok", "h5_governance_audit_ok"}]
    if not h4_closed:
        failed_checks.append("h4_stage_closed")
    if not h5_log_ok:
        failed_checks.append("h5_log_ok")
    if not h5_audit_ok:
        failed_checks.append("h5_governance_audit_ok")

    report["warning_flags"] = warning_flags
    report["failed_checks"] = failed_checks
    report["failed_count"] = len(failed_checks)
    report["overall_ok"] = (len(failed_checks) == 0)

    final_state = (
        "ai_cost_governance_not_closed"
        if failed_checks
        else ("ai_cost_governance_closed_soft_warn_ready_for_i1" if warning_flags else "ai_cost_governance_closed_ready_for_i1")
    )
    report["final_state"] = final_state

    audit_summary = dict(report.get("audit_summary") or {})
    audit_summary["h5_stage_closed"] = (len(failed_checks) == 0)
    audit_summary["h_chapter_closed"] = (len(failed_checks) == 0)
    audit_summary["ready_for_i1"] = (len(failed_checks) == 0)
    audit_summary["runtime_still_protected"] = True
    report["audit_summary"] = audit_summary

    return report
