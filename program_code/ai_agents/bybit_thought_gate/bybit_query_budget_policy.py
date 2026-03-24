#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir
from typing import Any, Dict, List, Optional

RUNTIME_DIR = get_thought_gate_runtime_dir()

HANDOFF_PATH = RUNTIME_DIR / "bybit_thought_gate_handoff_latest.json"
REQUEST_PATH = RUNTIME_DIR / "bybit_ai_request_envelope_latest.json"
INVOCATION_PATH = RUNTIME_DIR / "bybit_ai_invocation_attempt_latest.json"

LATEST_PATH = RUNTIME_DIR / "bybit_query_budget_policy_latest.json"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Dict[str, Any]) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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


def as_bool(value: Any) -> Optional[bool]:
    return value if isinstance(value, bool) else None


def main() -> None:
    now_ms = int(time.time() * 1000)

    source_integrity = {
        "handoff_present": HANDOFF_PATH.exists(),
        "ai_request_envelope_present": REQUEST_PATH.exists(),
        "ai_invocation_attempt_present": INVOCATION_PATH.exists(),
        "source_errors": [],
    }

    if not source_integrity["handoff_present"]:
        source_integrity["source_errors"].append("handoff_missing")
    if not source_integrity["ai_request_envelope_present"]:
        source_integrity["source_errors"].append("ai_request_envelope_missing")
    if not source_integrity["ai_invocation_attempt_present"]:
        source_integrity["source_errors"].append("ai_invocation_attempt_missing")

    handoff = read_json(HANDOFF_PATH) if HANDOFF_PATH.exists() else {}
    request = read_json(REQUEST_PATH) if REQUEST_PATH.exists() else {}
    invocation = read_json(INVOCATION_PATH) if INVOCATION_PATH.exists() else {}

    request_summary = as_dict(request.get("request_summary"))
    invocation_request_summary = as_dict(invocation.get("request_summary"))
    provider_runtime = as_dict(request.get("provider_runtime"))
    budget_context = as_dict(request.get("budget_context"))
    request_payload = as_dict(request.get("request_payload"))

    attempt_result = as_dict(invocation.get("attempt_result"))
    response_extract = as_dict(invocation.get("response_extract"))
    usage_summary = as_dict(response_extract.get("usage_summary"))
    output_tokens_details = as_dict(usage_summary.get("output_tokens_details"))

    should_call_ai = request_summary.get("should_call_ai")
    if not isinstance(should_call_ai, bool):
        should_call_ai = invocation_request_summary.get("should_call_ai")
    no_call_path_expected = (should_call_ai is False)

    warning_flags: List[str] = []
    blocking_reasons: List[str] = []

    if handoff.get("handoff_ok") is not True:
        blocking_reasons.append("h1_handoff_not_green")

    latency_ms = as_int(attempt_result.get("latency_ms"))
    deadline_ms_hint = as_int(budget_context.get("response_deadline_ms_hint"))
    provider_roundtrip_ceiling_ms = int(float(os.getenv("BYBIT_AI_MAX_EXPECTED_ROUNDTRIP_MS", "5000")))
    effective_deadline_ms_hint = max(int(deadline_ms_hint), provider_roundtrip_ceiling_ms) if deadline_ms_hint is not None else provider_roundtrip_ceiling_ms

    within_timeout_hint: Optional[bool] = None
    if latency_ms is not None and effective_deadline_ms_hint is not None:
        within_timeout_hint = latency_ms <= effective_deadline_ms_hint
        if within_timeout_hint is False:
            warning_flags.append("last_call_latency_exceeds_deadline_hint")

    invocation_state = invocation.get("invocation_state")
    retries_disabled = provider_runtime.get("max_retries") == 0
    if not retries_disabled:
        warning_flags.append("max_retries_not_zero")

    if not no_call_path_expected:
        if not usage_summary:
            warning_flags.append("last_call_usage_summary_missing")
        if invocation_state != "invocation_success_json_ready":
            warning_flags.append("last_call_not_json_ready")

    report = {
        "report_type": "bybit_query_budget_policy",
        "report_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H2-A",
        "report_ok": True,
        "source_refs": {
            "handoff_path": str(HANDOFF_PATH),
            "ai_request_envelope_path": str(REQUEST_PATH),
            "ai_invocation_attempt_path": str(INVOCATION_PATH),
        },
        "source_integrity": source_integrity,
        "request_summary": {
            "provider_target": request_summary.get("provider_target"),
            "model_name": request_summary.get("model_name"),
            "selected_ai_tier": request_summary.get("selected_ai_tier"),
            "route_plan": request_summary.get("route_plan"),
            "should_call_ai": should_call_ai,
        },
        "policy_snapshot": {
            "ai_daily_budget_usd": budget_context.get("ai_daily_budget_usd"),
            "ai_per_call_budget_usd": budget_context.get("ai_per_call_budget_usd"),
            "max_output_tokens": request_payload.get("max_output_tokens"),
            "response_deadline_ms_hint": budget_context.get("response_deadline_ms_hint"),
            "connect_timeout_sec": provider_runtime.get("connect_timeout_sec"),
            "read_timeout_sec": provider_runtime.get("read_timeout_sec"),
            "max_retries": provider_runtime.get("max_retries"),
            "temperature": provider_runtime.get("temperature"),
        },
        "observed_last_call": {
            "invocation_state": invocation_state,
            "latency_ms": latency_ms,
            "response_text_present": attempt_result.get("response_text_present"),
            "parsed_json_present": attempt_result.get("parsed_json_present"),
            "input_tokens": usage_summary.get("input_tokens"),
            "output_tokens": usage_summary.get("output_tokens"),
            "reasoning_tokens": output_tokens_details.get("reasoning_tokens"),
            "total_tokens": usage_summary.get("total_tokens"),
        },
        "budget_assessment": {
            "within_timeout_hint": within_timeout_hint,
            "retries_disabled": retries_disabled,
            "daily_budget_declared": budget_context.get("ai_daily_budget_usd") is not None,
            "per_call_budget_declared": budget_context.get("ai_per_call_budget_usd") is not None,
            "budget_trace_ready": bool(request and invocation and handoff),
            "no_call_path_expected": no_call_path_expected,
        },
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "policy_state": "query_budget_policy_snapshotted" if not blocking_reasons else "query_budget_policy_blocked",
        "allow_progress_to_h2b_budget_gate": not blocking_reasons,
        "recommended_action": (
            "may_progress_to_h2b_budget_gate"
            if not blocking_reasons
            else "resolve_h2a_policy_blockers"
        ),
        "operator_message": (
            "H2-A query budget policy snapshot built. "
            "This stage normalizes active budget policy and latest observed usage, "
            "without yet making final budget gating decisions."
        ),
    }

    dated_path = RUNTIME_DIR / f"bybit_query_budget_policy_{now_ms}.json"
    write_json(LATEST_PATH, report)
    write_json(dated_path, report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={LATEST_PATH}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()
