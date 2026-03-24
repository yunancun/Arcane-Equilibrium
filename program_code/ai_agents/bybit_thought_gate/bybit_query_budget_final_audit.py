#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any, Dict, List

RUNTIME_DIR = get_thought_gate_runtime_dir()

H1_FINAL_AUDIT_PATH = RUNTIME_DIR / "bybit_thought_gate_final_audit_latest.json"
H2A_POLICY_PATH = RUNTIME_DIR / "bybit_query_budget_policy_latest.json"
H2B_GATE_PATH = RUNTIME_DIR / "bybit_query_budget_gate_latest.json"
H2C_RUNTIME_PATH = RUNTIME_DIR / "bybit_query_budget_runtime_latest.json"

LATEST_PATH = RUNTIME_DIR / "bybit_query_budget_final_audit_latest.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def main() -> None:
    now_ms = int(time.time() * 1000)

    source_integrity = {
        "h1_final_audit_present": H1_FINAL_AUDIT_PATH.exists(),
        "h2a_policy_present": H2A_POLICY_PATH.exists(),
        "h2b_gate_present": H2B_GATE_PATH.exists(),
        "h2c_runtime_present": H2C_RUNTIME_PATH.exists(),
        "source_errors": [],
    }

    if not source_integrity["h1_final_audit_present"]:
        source_integrity["source_errors"].append("h1_final_audit_missing")
    if not source_integrity["h2a_policy_present"]:
        source_integrity["source_errors"].append("h2a_policy_missing")
    if not source_integrity["h2b_gate_present"]:
        source_integrity["source_errors"].append("h2b_gate_missing")
    if not source_integrity["h2c_runtime_present"]:
        source_integrity["source_errors"].append("h2c_runtime_missing")

    h1 = read_json(H1_FINAL_AUDIT_PATH) if H1_FINAL_AUDIT_PATH.exists() else {}
    h2a = read_json(H2A_POLICY_PATH) if H2A_POLICY_PATH.exists() else {}
    h2b = read_json(H2B_GATE_PATH) if H2B_GATE_PATH.exists() else {}
    h2c = read_json(H2C_RUNTIME_PATH) if H2C_RUNTIME_PATH.exists() else {}

    h1_audit_summary = as_dict(h1.get("audit_summary"))
    h2a_request_summary = as_dict(h2a.get("request_summary"))
    h2c_budget_policy = as_dict(h2c.get("budget_policy"))
    h2c_observed_last_call = as_dict(h2c.get("observed_last_call"))
    h2c_runtime_assessment = as_dict(h2c.get("runtime_assessment"))

    provider_target = h2a_request_summary.get("provider_target")
    model_name = h2a_request_summary.get("model_name")
    selected_ai_tier = h2a_request_summary.get("selected_ai_tier")
    route_plan = h2a_request_summary.get("route_plan")
    should_call_ai = h2a_request_summary.get("should_call_ai")
    no_call_path_accepted = (
        h2c_runtime_assessment.get("no_call_path_accepted") is True
        or h1_audit_summary.get("no_call_terminal_accepted") is True
        or should_call_ai is False
    )

    checks: List[Dict[str, Any]] = []

    def add_check(name: str, ok: bool, detail: Any) -> None:
        checks.append({
            "name": name,
            "ok": bool(ok),
            "detail": detail,
        })

    add_check("h1_final_audit_ok", h1.get("overall_ok") is True, h1.get("overall_ok"))
    add_check("h1_ready_for_h2", h1_audit_summary.get("ready_for_h2") is True, h1_audit_summary.get("ready_for_h2"))
    add_check("h1_runtime_still_protected", h1_audit_summary.get("runtime_still_protected") is True, h1_audit_summary.get("runtime_still_protected"))

    add_check("h2a_policy_snapshotted", h2a.get("policy_state") == "query_budget_policy_snapshotted", h2a.get("policy_state"))
    add_check("h2a_allow_progress_true", h2a.get("allow_progress_to_h2b_budget_gate") is True, h2a.get("allow_progress_to_h2b_budget_gate"))

    add_check("h2b_gate_ok", h2b.get("gate_ok") is True, h2b.get("gate_ok"))
    add_check("h2b_allow_progress_true", h2b.get("allow_progress_to_h2c_budget_runtime") is True, h2b.get("allow_progress_to_h2c_budget_runtime"))
    add_check(
        "h2b_gate_state_known",
        h2b.get("gate_state") in {
            "query_budget_gate_pass",
            "query_budget_gate_pass_soft_warn",
        },
        h2b.get("gate_state"),
    )

    add_check("h2c_runtime_ok", h2c.get("runtime_ok") is True, h2c.get("runtime_ok"))
    add_check("h2c_allow_progress_true", h2c.get("allow_progress_to_h2d_final_audit") is True, h2c.get("allow_progress_to_h2d_final_audit"))
    add_check(
        "h2c_runtime_state_known",
        h2c.get("runtime_state") in {
            "query_budget_runtime_ready",
            "query_budget_runtime_ready_soft_warn",
        },
        h2c.get("runtime_state"),
    )
    add_check(
        "h2c_blocking_reasons_empty",
        len(as_list(h2c.get("blocking_reasons"))) == 0,
        as_list(h2c.get("blocking_reasons")),
    )

    add_check("max_retries_zero", h2c_budget_policy.get("max_retries") == 0, h2c_budget_policy.get("max_retries"))
    add_check("output_cap_enforced", h2c_runtime_assessment.get("output_cap_enforced") is True, h2c_runtime_assessment.get("output_cap_enforced"))
    add_check(
        "json_contract_ready_or_no_call_path",
        (h2c_runtime_assessment.get("json_contract_ready") is True) or no_call_path_accepted,
        {"json_contract_ready": h2c_runtime_assessment.get("json_contract_ready"), "no_call_path_accepted": no_call_path_accepted},
    )
    add_check(
        "call_trace_observed_or_no_call_path",
        (h2c_runtime_assessment.get("call_trace_observed") is True) or no_call_path_accepted,
        {"call_trace_observed": h2c_runtime_assessment.get("call_trace_observed"), "no_call_path_accepted": no_call_path_accepted},
    )

    failed_checks = [c["name"] for c in checks if not c["ok"]]
    warning_flags = as_list(h2c.get("warning_flags"))

    overall_ok = len(failed_checks) == 0

    if overall_ok and warning_flags:
        audit_state = "query_budget_closed_soft_warn_ready_for_h3"
        recommended_action = "may_progress_to_h3_model_router_with_soft_warnings_recorded"
    elif overall_ok:
        audit_state = "query_budget_closed_ready_for_h3"
        recommended_action = "may_progress_to_h3_model_router"
    else:
        audit_state = "query_budget_not_closed"
        recommended_action = "inspect_h2_final_audit_failures"

    report = {
        "audit_type": "bybit_query_budget_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H2-D",
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "source_refs": {
            "h1_final_audit_path": str(H1_FINAL_AUDIT_PATH),
            "h2a_policy_path": str(H2A_POLICY_PATH),
            "h2b_gate_path": str(H2B_GATE_PATH),
            "h2c_runtime_path": str(H2C_RUNTIME_PATH),
        },
        "source_integrity": source_integrity,
        "request_summary": {
            "provider_target": provider_target,
            "model_name": model_name,
            "selected_ai_tier": selected_ai_tier,
            "route_plan": route_plan,
            "should_call_ai": should_call_ai,
        },
        "budget_snapshot": {
            "ai_daily_budget_usd": h2c_budget_policy.get("ai_daily_budget_usd"),
            "ai_per_call_budget_usd": h2c_budget_policy.get("ai_per_call_budget_usd"),
            "max_output_tokens": h2c_budget_policy.get("max_output_tokens"),
            "connect_timeout_sec": h2c_budget_policy.get("connect_timeout_sec"),
            "read_timeout_sec": h2c_budget_policy.get("read_timeout_sec"),
            "max_retries": h2c_budget_policy.get("max_retries"),
        },
        "observed_last_call": {
            "latency_ms": h2c_observed_last_call.get("latency_ms"),
            "within_timeout_hint": h2c_observed_last_call.get("within_timeout_hint"),
            "input_tokens": h2c_observed_last_call.get("input_tokens"),
            "output_tokens": h2c_observed_last_call.get("output_tokens"),
            "reasoning_tokens": h2c_observed_last_call.get("reasoning_tokens"),
            "total_tokens": h2c_observed_last_call.get("total_tokens"),
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "audit_summary": {
            "h2_stage_closed": overall_ok,
            "query_budget_policy_snapshotted": h2a.get("allow_progress_to_h2b_budget_gate") is True,
            "query_budget_gate_passed": h2b.get("gate_ok") is True,
            "query_budget_runtime_built": h2c.get("runtime_ok") is True,
            "runtime_soft_warn_only": overall_ok and len(warning_flags) > 0,
            "runtime_still_protected": h1_audit_summary.get("runtime_still_protected") is True,
            "ready_for_h3": overall_ok,
            "no_call_path_accepted": no_call_path_accepted,
        },
        "audit_state": audit_state,
        "recommended_next_build_order": [
            "H3. model_router v2",
            "I1. decision lease schema",
        ],
        "recommended_action": recommended_action,
        "operator_message": (
            "H2 final audit complete. Query-budget chapter is closed using policy -> gate -> runtime governance, "
            "and remains read-only / non-executable."
            if overall_ok else
            "H2 final audit failed. Inspect failed_checks before chapter closure."
        ),
    }

    dated_path = RUNTIME_DIR / f"bybit_query_budget_final_audit_{now_ms}.json"
    write_json(LATEST_PATH, report)
    write_json(dated_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
