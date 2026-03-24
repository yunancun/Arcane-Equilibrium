#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir

from bybit_h_stage_common import mkcheck, read_json_if_exists, unique_list, write_report

BASE = get_thought_gate_runtime_dir()

GATE_PATH = BASE / "bybit_compute_governor_gate_latest.json"
INV_PATH = BASE / "bybit_ai_invocation_attempt_latest.json"
H1_AUDIT_PATH = BASE / "bybit_thought_gate_final_audit_latest.json"
H2_RUNTIME_PATH = BASE / "bybit_query_budget_runtime_latest.json"

PREFIX = "bybit_compute_governor_runtime"


def main() -> None:
    now_ms = int(time.time() * 1000)

    gate = read_json_if_exists(GATE_PATH)
    inv = read_json_if_exists(INV_PATH)
    h1 = read_json_if_exists(H1_AUDIT_PATH)
    h2 = read_json_if_exists(H2_RUNTIME_PATH)

    transport_summary = inv.get("transport_summary") or {}
    attempt_result = inv.get("attempt_result") or {}
    response_extract = inv.get("response_extract") or {}
    usage_summary = response_extract.get("usage_summary") or {}
    output_tokens_details = usage_summary.get("output_tokens_details") or {}

    h1_summary = h1.get("audit_summary") or {}
    h2_runtime_summary = h2.get("runtime_summary") or {}
    h2_runtime_assessment = h2.get("runtime_assessment") or {}
    gate_context = gate.get("gate_context") or {}

    output_tokens = usage_summary.get("output_tokens")
    reasoning_tokens = output_tokens_details.get("reasoning_tokens")

    no_call_path_accepted = (
        gate_context.get("no_call_path_expected") is True
        or h2_runtime_assessment.get("no_call_path_accepted") is True
        or gate.get("request_summary", {}).get("should_call_ai") is False
    )

    checks = [
        mkcheck("gate_ok", gate.get("gate_ok") is True, gate.get("gate_ok")),
        mkcheck(
            "invocation_attempted_true_or_no_call_path",
            (attempt_result.get("invocation_attempted") is True) or no_call_path_accepted,
            {"invocation_attempted": attempt_result.get("invocation_attempted"), "no_call_path_accepted": no_call_path_accepted},
        ),
        mkcheck(
            "provider_response_present_true_or_no_call_path",
            (attempt_result.get("provider_response_present") is True) or no_call_path_accepted,
            {"provider_response_present": attempt_result.get("provider_response_present"), "no_call_path_accepted": no_call_path_accepted},
        ),
        mkcheck(
            "response_text_present_true_or_no_call_path",
            (attempt_result.get("response_text_present") is True) or no_call_path_accepted,
            {"response_text_present": attempt_result.get("response_text_present"), "no_call_path_accepted": no_call_path_accepted},
        ),
        mkcheck(
            "parsed_json_present_true_or_no_call_path",
            (attempt_result.get("parsed_json_present") is True) or no_call_path_accepted,
            {"parsed_json_present": attempt_result.get("parsed_json_present"), "no_call_path_accepted": no_call_path_accepted},
        ),
        mkcheck("max_retries_zero", transport_summary.get("max_retries") == 0 or no_call_path_accepted, transport_summary.get("max_retries")),
        mkcheck("runtime_still_protected", h1_summary.get("runtime_still_protected") is True, h1_summary.get("runtime_still_protected")),
        mkcheck("reasoning_tokens_zero_or_null", reasoning_tokens in (0, None), reasoning_tokens),
        mkcheck(
            "output_tokens_int_or_null_on_no_call",
            isinstance(output_tokens, int) or (output_tokens is None and no_call_path_accepted),
            {"output_tokens": output_tokens, "no_call_path_accepted": no_call_path_accepted},
        ),
        mkcheck(
            "latency_ms_int_or_null_on_no_call",
            isinstance(attempt_result.get("latency_ms"), int) or (attempt_result.get("latency_ms") is None and no_call_path_accepted),
            {"latency_ms": attempt_result.get("latency_ms"), "no_call_path_accepted": no_call_path_accepted},
        ),
    ]

    runtime_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    warning_flags = unique_list(
        (gate.get("warning_flags") or [])
        + (inv.get("warning_flags") or [])
        + (h2.get("warning_flags") or [])
    )

    blocking_reasons = failed_checks[:]

    runtime_state = (
        "compute_governor_runtime_ready_soft_warn"
        if runtime_ok and warning_flags else
        "compute_governor_runtime_ready"
        if runtime_ok else
        "compute_governor_runtime_blocked"
    )

    report = {
        "runtime_type": "bybit_compute_governor_runtime",
        "runtime_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H4-C",
        "runtime_ok": runtime_ok,
        "source_refs": {
            "compute_governor_gate_path": str(GATE_PATH),
            "ai_invocation_attempt_path": str(INV_PATH),
            "thought_gate_final_audit_path": str(H1_AUDIT_PATH),
            "query_budget_runtime_path": str(H2_RUNTIME_PATH),
        },
        "runtime_summary": {
            "provider_target": transport_summary.get("provider_target"),
            "sdk_mode": transport_summary.get("sdk_mode"),
            "max_retries": transport_summary.get("max_retries"),
            "latency_ms": attempt_result.get("latency_ms"),
            "within_timeout_hint": h2_runtime_summary.get("within_timeout_hint"),
            "input_tokens": usage_summary.get("input_tokens"),
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": usage_summary.get("total_tokens"),
            "response_text_present": attempt_result.get("response_text_present"),
            "parsed_json_present": attempt_result.get("parsed_json_present"),
            "no_call_path_accepted": no_call_path_accepted,
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "runtime_state": runtime_state,
        "allow_progress_to_h4d_final_audit": runtime_ok,
        "recommended_action": (
            "may_progress_to_h4d_final_audit"
            if runtime_ok else
            "inspect_compute_governor_runtime_failures"
        ),
        "operator_message": (
            "H4-C compute governor runtime ready. 当前运行结果符合 anti-abuse 主链约束。"
            if runtime_ok else
            "H4-C compute governor runtime blocked."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
