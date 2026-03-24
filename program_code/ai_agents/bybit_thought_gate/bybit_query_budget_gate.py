#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any, Dict, List, Optional

RUNTIME_DIR = get_thought_gate_runtime_dir()

FINAL_AUDIT_PATH = RUNTIME_DIR / "bybit_thought_gate_final_audit_latest.json"
POLICY_PATH = RUNTIME_DIR / "bybit_query_budget_policy_latest.json"

LATEST_PATH = RUNTIME_DIR / "bybit_query_budget_gate_latest.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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
        "final_audit_present": FINAL_AUDIT_PATH.exists(),
        "query_budget_policy_present": POLICY_PATH.exists(),
        "source_errors": [],
    }

    if not source_integrity["final_audit_present"]:
        source_integrity["source_errors"].append("final_audit_missing")
    if not source_integrity["query_budget_policy_present"]:
        source_integrity["source_errors"].append("query_budget_policy_missing")

    final_audit = read_json(FINAL_AUDIT_PATH) if FINAL_AUDIT_PATH.exists() else {}
    policy = read_json(POLICY_PATH) if POLICY_PATH.exists() else {}

    audit_summary = as_dict(final_audit.get("audit_summary"))
    request_summary = as_dict(policy.get("request_summary"))
    policy_snapshot = as_dict(policy.get("policy_snapshot"))
    observed_last_call = as_dict(policy.get("observed_last_call"))
    budget_assessment = as_dict(policy.get("budget_assessment"))

    should_call_ai = request_summary.get("should_call_ai")
    legal_no_call_path = (
        audit_summary.get("no_call_terminal_accepted") is True
        or budget_assessment.get("no_call_path_expected") is True
        or should_call_ai is False
    )

    warning_flags: List[str] = []
    blocking_reasons: List[str] = []

    if final_audit.get("overall_ok") is not True:
        blocking_reasons.append("h1_final_audit_not_green")

    if policy.get("allow_progress_to_h2b_budget_gate") is not True:
        blocking_reasons.append("h2a_policy_not_green")

    ai_daily_budget_usd = as_float(policy_snapshot.get("ai_daily_budget_usd"))
    ai_per_call_budget_usd = as_float(policy_snapshot.get("ai_per_call_budget_usd"))
    max_output_tokens = as_int(policy_snapshot.get("max_output_tokens"))
    max_retries = as_int(policy_snapshot.get("max_retries"))

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

    provider_target = request_summary.get("provider_target")
    model_name = request_summary.get("model_name")
    if not provider_target:
        blocking_reasons.append("provider_target_missing")
    if not model_name:
        blocking_reasons.append("model_name_missing")

    parsed_json_present = observed_last_call.get("parsed_json_present")
    if not legal_no_call_path and parsed_json_present is not True:
        blocking_reasons.append("last_call_not_json_ready")

    within_timeout_hint = budget_assessment.get("within_timeout_hint")
    if within_timeout_hint is False:
        warning_flags.append("last_call_latency_exceeds_deadline_hint")

    if not legal_no_call_path:
        if observed_last_call.get("invocation_state") != "invocation_success_json_ready":
            warning_flags.append("invocation_state_not_json_ready")

        output_tokens = as_int(observed_last_call.get("output_tokens"))
        total_tokens = as_int(observed_last_call.get("total_tokens"))
        latency_ms = as_int(observed_last_call.get("latency_ms"))

        if output_tokens is None:
            warning_flags.append("output_tokens_missing")
        if total_tokens is None:
            warning_flags.append("total_tokens_missing")
        if latency_ms is None:
            warning_flags.append("latency_ms_missing")

        if output_tokens is not None and max_output_tokens is not None and output_tokens > max_output_tokens:
            blocking_reasons.append("output_tokens_exceed_policy_cap")

    structural_budget_trace_ready = all([
        ai_daily_budget_usd is not None,
        ai_per_call_budget_usd is not None,
        max_output_tokens is not None,
        provider_target,
        model_name,
    ])

    gate_checks: List[Dict[str, Any]] = []

    def add_check(name: str, ok: bool, detail: Any) -> None:
        gate_checks.append({
            "name": name,
            "ok": bool(ok),
            "detail": detail,
        })

    add_check("h1_final_audit_green", final_audit.get("overall_ok") is True, final_audit.get("overall_ok"))
    add_check("h2a_policy_green", policy.get("allow_progress_to_h2b_budget_gate") is True, policy.get("allow_progress_to_h2b_budget_gate"))
    add_check("daily_budget_declared", ai_daily_budget_usd is not None and ai_daily_budget_usd > 0, ai_daily_budget_usd)
    add_check("per_call_budget_declared", ai_per_call_budget_usd is not None and ai_per_call_budget_usd > 0, ai_per_call_budget_usd)
    add_check("max_output_tokens_declared", max_output_tokens is not None and max_output_tokens > 0, max_output_tokens)
    add_check("max_retries_zero", max_retries == 0, max_retries)
    add_check("provider_target_present", bool(provider_target), provider_target)
    add_check("model_name_present", bool(model_name), model_name)
    add_check(
        "last_call_json_ready_or_no_call_expected",
        (parsed_json_present is True) or legal_no_call_path,
        {"parsed_json_present": parsed_json_present, "legal_no_call_path": legal_no_call_path},
    )
    add_check("structural_budget_trace_ready", structural_budget_trace_ready, structural_budget_trace_ready)

    if blocking_reasons:
        gate_state = "query_budget_gate_blocked"
        gate_ok = False
        allow_progress = False
        recommended_action = "resolve_h2b_budget_blockers"
    else:
        gate_state = "query_budget_gate_pass_soft_warn" if warning_flags or legal_no_call_path else "query_budget_gate_pass_soft_warn"
        gate_ok = True
        allow_progress = True
        recommended_action = (
            "may_progress_to_h2c_with_soft_warnings"
            if (warning_flags or legal_no_call_path)
            else "may_progress_to_h2c_budget_runtime"
        )

    report = {
        "gate_type": "bybit_query_budget_gate",
        "gate_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H2-B",
        "gate_ok": gate_ok,
        "source_refs": {
            "final_audit_path": str(FINAL_AUDIT_PATH),
            "query_budget_policy_path": str(POLICY_PATH),
        },
        "source_integrity": source_integrity,
        "request_summary": {
            "provider_target": provider_target,
            "model_name": model_name,
            "selected_ai_tier": request_summary.get("selected_ai_tier"),
            "route_plan": request_summary.get("route_plan"),
            "should_call_ai": should_call_ai,
        },
        "budget_policy": {
            "ai_daily_budget_usd": ai_daily_budget_usd,
            "ai_per_call_budget_usd": ai_per_call_budget_usd,
            "max_output_tokens": max_output_tokens,
            "response_deadline_ms_hint": as_int(policy_snapshot.get("response_deadline_ms_hint")),
            "connect_timeout_sec": as_float(policy_snapshot.get("connect_timeout_sec")),
            "read_timeout_sec": as_float(policy_snapshot.get("read_timeout_sec")),
            "max_retries": max_retries,
            "temperature": as_float(policy_snapshot.get("temperature")),
        },
        "observed_last_call": {
            "invocation_state": observed_last_call.get("invocation_state"),
            "latency_ms": as_int(observed_last_call.get("latency_ms")),
            "within_timeout_hint": within_timeout_hint,
            "response_text_present": as_bool(observed_last_call.get("response_text_present")),
            "parsed_json_present": as_bool(observed_last_call.get("parsed_json_present")),
            "input_tokens": as_int(observed_last_call.get("input_tokens")),
            "output_tokens": as_int(observed_last_call.get("output_tokens")),
            "reasoning_tokens": as_int(observed_last_call.get("reasoning_tokens")),
            "total_tokens": as_int(observed_last_call.get("total_tokens")),
        },
        "audit_context": {
            "h1_stage_closed": audit_summary.get("h1_stage_closed"),
            "runtime_still_protected": audit_summary.get("runtime_still_protected"),
            "ready_for_h2": audit_summary.get("ready_for_h2"),
            "no_call_terminal_accepted": audit_summary.get("no_call_terminal_accepted"),
        },
        "gate_checks": gate_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "gate_state": gate_state,
        "allow_progress_to_h2c_budget_runtime": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": (
            "H2-B budget gate built. "
            "This stage verifies structural budget declarations, bounded output policy, "
            "retry discipline, and traceability of the latest provider-native call, "
            "while still preserving read-only runtime safety."
        ),
    }

    dated_path = RUNTIME_DIR / f"bybit_query_budget_gate_{now_ms}.json"
    write_json(LATEST_PATH, report)
    write_json(dated_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
