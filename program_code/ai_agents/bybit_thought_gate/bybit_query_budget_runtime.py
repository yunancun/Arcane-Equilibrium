#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any, Dict, List, Optional

RUNTIME_DIR = get_thought_gate_runtime_dir()

H1_FINAL_AUDIT_PATH = RUNTIME_DIR / "bybit_thought_gate_final_audit_latest.json"
H2A_POLICY_PATH = RUNTIME_DIR / "bybit_query_budget_policy_latest.json"
H2B_GATE_PATH = RUNTIME_DIR / "bybit_query_budget_gate_latest.json"
H1F_INVOCATION_PATH = RUNTIME_DIR / "bybit_ai_invocation_attempt_latest.json"

LATEST_PATH = RUNTIME_DIR / "bybit_query_budget_runtime_latest.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_bool(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def as_int(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    try:
        return int(value)
    except Exception:
        return None


def as_float(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except Exception:
        return None


def main() -> None:
    now_ms = int(time.time() * 1000)

    source_integrity = {
        "h1_final_audit_present": H1_FINAL_AUDIT_PATH.exists(),
        "h2a_policy_present": H2A_POLICY_PATH.exists(),
        "h2b_gate_present": H2B_GATE_PATH.exists(),
        "h1f_invocation_present": H1F_INVOCATION_PATH.exists(),
        "source_errors": [],
    }

    if not source_integrity["h1_final_audit_present"]:
        source_integrity["source_errors"].append("h1_final_audit_missing")
    if not source_integrity["h2a_policy_present"]:
        source_integrity["source_errors"].append("h2a_policy_missing")
    if not source_integrity["h2b_gate_present"]:
        source_integrity["source_errors"].append("h2b_gate_missing")
    if not source_integrity["h1f_invocation_present"]:
        source_integrity["source_errors"].append("h1f_invocation_missing")

    h1_audit = read_json(H1_FINAL_AUDIT_PATH) if H1_FINAL_AUDIT_PATH.exists() else {}
    h2a_policy = read_json(H2A_POLICY_PATH) if H2A_POLICY_PATH.exists() else {}
    h2b_gate = read_json(H2B_GATE_PATH) if H2B_GATE_PATH.exists() else {}
    h1f_inv = read_json(H1F_INVOCATION_PATH) if H1F_INVOCATION_PATH.exists() else {}

    audit_summary = as_dict(h1_audit.get("audit_summary"))
    request_summary = as_dict(h2a_policy.get("request_summary"))
    policy_snapshot = as_dict(h2a_policy.get("policy_snapshot"))
    budget_assessment = as_dict(h2a_policy.get("budget_assessment"))
    response_extract = as_dict(h1f_inv.get("response_extract"))
    attempt_result = as_dict(h1f_inv.get("attempt_result"))
    usage_summary = as_dict(response_extract.get("usage_summary"))
    output_tokens_details = as_dict(usage_summary.get("output_tokens_details"))

    provider_target = request_summary.get("provider_target")
    model_name = request_summary.get("model_name")
    selected_ai_tier = request_summary.get("selected_ai_tier")
    route_plan = request_summary.get("route_plan")
    should_call_ai = request_summary.get("should_call_ai")

    ai_daily_budget_usd = as_float(policy_snapshot.get("ai_daily_budget_usd"))
    ai_per_call_budget_usd = as_float(policy_snapshot.get("ai_per_call_budget_usd"))
    max_output_tokens = as_int(policy_snapshot.get("max_output_tokens"))
    response_deadline_ms_hint = as_int(policy_snapshot.get("response_deadline_ms_hint"))
    connect_timeout_sec = as_float(policy_snapshot.get("connect_timeout_sec"))
    read_timeout_sec = as_float(policy_snapshot.get("read_timeout_sec"))
    max_retries = as_int(policy_snapshot.get("max_retries"))
    temperature = as_float(policy_snapshot.get("temperature"))

    invocation_state = h1f_inv.get("invocation_state")
    invocation_attempted = as_bool(attempt_result.get("invocation_attempted"))
    provider_response_present = as_bool(attempt_result.get("provider_response_present"))
    response_text_present = as_bool(attempt_result.get("response_text_present"))
    parsed_json_present = as_bool(attempt_result.get("parsed_json_present"))
    latency_ms = as_int(attempt_result.get("latency_ms"))

    input_tokens = as_int(usage_summary.get("input_tokens"))
    output_tokens = as_int(usage_summary.get("output_tokens"))
    total_tokens = as_int(usage_summary.get("total_tokens"))
    reasoning_tokens = as_int(output_tokens_details.get("reasoning_tokens"))

    within_timeout_hint = budget_assessment.get("within_timeout_hint")
    legal_no_call_path = (
        audit_summary.get("no_call_terminal_accepted") is True
        or budget_assessment.get("no_call_path_expected") is True
        or should_call_ai is False
    )

    warning_flags: List[str] = []
    blocking_reasons: List[str] = []

    if h1_audit.get("overall_ok") is not True:
        blocking_reasons.append("h1_not_closed")

    if h2a_policy.get("allow_progress_to_h2b_budget_gate") is not True:
        blocking_reasons.append("h2a_policy_not_green")

    if h2b_gate.get("allow_progress_to_h2c_budget_runtime") is not True:
        blocking_reasons.append("h2b_gate_not_green")

    if provider_target in (None, ""):
        blocking_reasons.append("provider_target_missing")

    if model_name in (None, ""):
        blocking_reasons.append("model_name_missing")

    if ai_daily_budget_usd is None or ai_daily_budget_usd <= 0:
        blocking_reasons.append("daily_budget_missing_or_invalid")

    if ai_per_call_budget_usd is None or ai_per_call_budget_usd <= 0:
        blocking_reasons.append("per_call_budget_missing_or_invalid")

    if max_output_tokens is None or max_output_tokens <= 0:
        blocking_reasons.append("max_output_tokens_missing_or_invalid")

    if max_retries is None:
        blocking_reasons.append("max_retries_missing")
    elif max_retries != 0:
        blocking_reasons.append("max_retries_not_zero")

    if not legal_no_call_path:
        if invocation_attempted is not True:
            blocking_reasons.append("latest_call_not_attempted")
        if provider_response_present is not True:
            blocking_reasons.append("latest_call_no_provider_response")
        if parsed_json_present is not True:
            blocking_reasons.append("latest_call_not_json_ready")
        if output_tokens is not None and max_output_tokens is not None and output_tokens > max_output_tokens:
            blocking_reasons.append("observed_output_tokens_exceed_cap")

    if within_timeout_hint is False:
        warning_flags.append("last_call_latency_exceeds_deadline_hint")

    if not legal_no_call_path:
        if latency_ms is None:
            warning_flags.append("latency_ms_missing")
        if input_tokens is None:
            warning_flags.append("input_tokens_missing")
        if output_tokens is None:
            warning_flags.append("output_tokens_missing")
        if total_tokens is None:
            warning_flags.append("total_tokens_missing")
        if reasoning_tokens is None:
            warning_flags.append("reasoning_tokens_missing")
        if response_text_present is not True:
            warning_flags.append("response_text_present_false")

    runtime_checks: List[Dict[str, Any]] = []

    def add_check(name: str, ok: bool, detail: Any) -> None:
        runtime_checks.append({
            "name": name,
            "ok": bool(ok),
            "detail": detail,
        })

    add_check("h1_final_audit_green", h1_audit.get("overall_ok") is True, h1_audit.get("overall_ok"))
    add_check("h2a_policy_green", h2a_policy.get("allow_progress_to_h2b_budget_gate") is True, h2a_policy.get("allow_progress_to_h2b_budget_gate"))
    add_check("h2b_gate_green", h2b_gate.get("allow_progress_to_h2c_budget_runtime") is True, h2b_gate.get("allow_progress_to_h2c_budget_runtime"))
    add_check(
        "invocation_attempted_true_or_no_call_expected",
        (invocation_attempted is True) or legal_no_call_path,
        {"invocation_attempted": invocation_attempted, "legal_no_call_path": legal_no_call_path},
    )
    add_check(
        "provider_response_present_true_or_no_call_expected",
        (provider_response_present is True) or legal_no_call_path,
        {"provider_response_present": provider_response_present, "legal_no_call_path": legal_no_call_path},
    )
    add_check(
        "parsed_json_present_true_or_no_call_expected",
        (parsed_json_present is True) or legal_no_call_path,
        {"parsed_json_present": parsed_json_present, "legal_no_call_path": legal_no_call_path},
    )
    add_check("max_retries_zero", max_retries == 0, max_retries)
    add_check("output_tokens_within_cap", (output_tokens is None or max_output_tokens is None or output_tokens <= max_output_tokens), {
        "output_tokens": output_tokens,
        "max_output_tokens": max_output_tokens,
    })
    add_check("runtime_still_protected", audit_summary.get("runtime_still_protected") is True, audit_summary.get("runtime_still_protected"))
    add_check("ready_for_h2_true", audit_summary.get("ready_for_h2") is True, audit_summary.get("ready_for_h2"))

    budget_meter_mode = "structural_caps_plus_observed_usage"
    usd_meter_available = False

    if blocking_reasons:
        runtime_state = "query_budget_runtime_blocked"
        runtime_ok = False
        allow_progress = False
        recommended_action = "resolve_h2c_runtime_budget_blockers"
    elif warning_flags:
        runtime_state = "query_budget_runtime_ready_soft_warn"
        runtime_ok = True
        allow_progress = True
        recommended_action = "may_progress_to_h2d_final_audit_with_soft_warnings"
    else:
        runtime_state = "query_budget_runtime_ready"
        runtime_ok = True
        allow_progress = True
        recommended_action = "may_progress_to_h2d_final_audit"

    report = {
        "runtime_type": "bybit_query_budget_runtime",
        "runtime_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H2-C",
        "runtime_ok": runtime_ok,
        "source_refs": {
            "h1_final_audit_path": str(H1_FINAL_AUDIT_PATH),
            "h2a_policy_path": str(H2A_POLICY_PATH),
            "h2b_gate_path": str(H2B_GATE_PATH),
            "h1f_invocation_path": str(H1F_INVOCATION_PATH),
        },
        "source_integrity": source_integrity,
        "request_summary": {
            "provider_target": provider_target,
            "model_name": model_name,
            "selected_ai_tier": selected_ai_tier,
            "route_plan": route_plan,
            "should_call_ai": should_call_ai,
        },
        "budget_policy": {
            "ai_daily_budget_usd": ai_daily_budget_usd,
            "ai_per_call_budget_usd": ai_per_call_budget_usd,
            "max_output_tokens": max_output_tokens,
            "response_deadline_ms_hint": response_deadline_ms_hint,
            "connect_timeout_sec": connect_timeout_sec,
            "read_timeout_sec": read_timeout_sec,
            "max_retries": max_retries,
            "temperature": temperature,
        },
        "observed_last_call": {
            "invocation_state": invocation_state,
            "invocation_attempted": invocation_attempted,
            "provider_response_present": provider_response_present,
            "response_text_present": response_text_present,
            "parsed_json_present": parsed_json_present,
            "latency_ms": latency_ms,
            "within_timeout_hint": within_timeout_hint,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": total_tokens,
        },
        "runtime_assessment": {
            "budget_meter_mode": budget_meter_mode,
            "usd_meter_available": usd_meter_available,
            "call_trace_observed": invocation_attempted is True and provider_response_present is True,
            "json_contract_ready": parsed_json_present is True,
            "no_call_path_accepted": legal_no_call_path,
            "output_cap_enforced": (output_tokens is None or max_output_tokens is None or output_tokens <= max_output_tokens),
            "retry_discipline_ok": max_retries == 0,
            "h1_ready_for_h2": audit_summary.get("ready_for_h2"),
            "runtime_still_protected": audit_summary.get("runtime_still_protected"),
        },
        "runtime_checks": runtime_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "runtime_state": runtime_state,
        "allow_progress_to_h2d_final_audit": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": (
            "H2-C query budget runtime built. "
            "This stage preserves structural budget governance plus observed latest-call usage "
            "without granting any execution authority."
        ),
    }

    dated_path = RUNTIME_DIR / f"bybit_query_budget_runtime_{now_ms}.json"
    write_json(LATEST_PATH, report)
    write_json(dated_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
