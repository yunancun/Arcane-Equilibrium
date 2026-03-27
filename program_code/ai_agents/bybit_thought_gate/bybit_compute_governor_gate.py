#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
from pathlib import Path

from bybit_path_policy import get_thought_gate_runtime_dir

from bybit_h_stage_common import mkcheck, read_json_if_exists, unique_list, write_report

BASE = get_thought_gate_runtime_dir()

POLICY_PATH = BASE / "bybit_compute_governor_policy_latest.json"
REQ_PATH = BASE / "bybit_ai_request_envelope_latest.json"
INV_PATH = BASE / "bybit_ai_invocation_attempt_latest.json"
H3_RUNTIME_PATH = BASE / "bybit_model_router_runtime_latest.json"

PREFIX = "bybit_compute_governor_gate"


def main() -> None:
    now_ms = int(time.time() * 1000)

    policy = read_json_if_exists(POLICY_PATH)
    req = read_json_if_exists(REQ_PATH)
    inv = read_json_if_exists(INV_PATH)
    h3_runtime = read_json_if_exists(H3_RUNTIME_PATH)

    governor_policy = policy.get("governor_policy") or {}
    budget_constraints = governor_policy.get("budget_constraints") or {}

    request_summary = req.get("request_summary") or {}
    request_payload = req.get("request_payload") or {}
    provider_runtime = req.get("provider_runtime") or {}

    transport_summary = inv.get("transport_summary") or {}
    attempt_result = inv.get("attempt_result") or {}
    response_extract = inv.get("response_extract") or {}

    route_request_provider = request_summary.get("provider_target") or request_payload.get("provider_target")
    route_request_model = request_summary.get("model_name") or request_payload.get("model_name")
    route_policy_provider = (policy.get("request_summary") or {}).get("provider_target")
    route_policy_model = (policy.get("request_summary") or {}).get("model_name")

    max_retries_actual = provider_runtime.get("max_retries")
    if max_retries_actual is None:
        max_retries_actual = transport_summary.get("max_retries")

    max_output_tokens_actual = request_payload.get("max_output_tokens")
    idempotency_key = response_extract.get("idempotency_key")

    no_call_path_expected = (
        governor_policy.get("no_call_path_expected") is True
        or request_summary.get("should_call_ai") is False
        or request_summary.get("route_plan") == "route_skip"
        or (h3_runtime.get("runtime_summary") or {}).get("no_call_path_accepted") is True
    )

    checks = [
        mkcheck("policy_ok", policy.get("policy_ok") is True, policy.get("policy_ok")),
        mkcheck("provider_consistent_with_policy", route_request_provider == route_policy_provider, {
            "request": route_request_provider,
            "policy": route_policy_provider,
        }),
        mkcheck("model_consistent_with_policy", route_request_model == route_policy_model, {
            "request": route_request_model,
            "policy": route_policy_model,
        }),
        mkcheck("max_retries_zero", max_retries_actual == 0, max_retries_actual),
        mkcheck(
            "max_output_tokens_within_cap",
            isinstance(max_output_tokens_actual, int) and isinstance(budget_constraints.get("max_output_tokens_cap"), int)
            and max_output_tokens_actual <= budget_constraints.get("max_output_tokens_cap"),
            {
                "actual": max_output_tokens_actual,
                "cap": budget_constraints.get("max_output_tokens_cap"),
            },
        ),
        mkcheck(
            "selected_ai_tier_allowed",
            request_summary.get("selected_ai_tier") in {"light", "standard", "none"},
            request_summary.get("selected_ai_tier"),
        ),
        mkcheck("model_router_runtime_ok", h3_runtime.get("runtime_ok") is True, h3_runtime.get("runtime_ok")),
        mkcheck(
            "idempotency_key_present_or_no_call_path",
            (isinstance(idempotency_key, str) and len(idempotency_key) > 0) or no_call_path_expected,
            {"idempotency_key": idempotency_key, "no_call_path_expected": no_call_path_expected},
        ),
        mkcheck(
            "invocation_attempt_record_present_or_no_call_path",
            (isinstance(attempt_result, dict) and len(attempt_result) > 0) or no_call_path_expected,
            {"attempt_result_type": type(attempt_result).__name__, "no_call_path_expected": no_call_path_expected},
        ),
    ]

    gate_ok = all(c["ok"] for c in checks)
    failed_checks = [c["name"] for c in checks if not c["ok"]]

    warning_flags = unique_list(
        (policy.get("warning_flags") or [])
        + (inv.get("warning_flags") or [])
        + (h3_runtime.get("warning_flags") or [])
    )

    blocking_reasons = failed_checks[:]

    gate_state = (
        "compute_governor_gate_pass_soft_warn"
        if gate_ok and warning_flags else
        "compute_governor_gate_pass"
        if gate_ok else
        "compute_governor_gate_blocked"
    )

    report = {
        "gate_type": "bybit_compute_governor_gate",
        "gate_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H4-B",
        "gate_ok": gate_ok,
        "source_refs": {
            "compute_governor_policy_path": str(POLICY_PATH),
            "ai_request_envelope_path": str(REQ_PATH),
            "ai_invocation_attempt_path": str(INV_PATH),
            "model_router_runtime_path": str(H3_RUNTIME_PATH),
        },
        "request_summary": {
            "provider_target": route_request_provider,
            "model_name": route_request_model,
            "selected_ai_tier": request_summary.get("selected_ai_tier"),
            "route_plan": request_summary.get("route_plan"),
            "should_call_ai": request_summary.get("should_call_ai"),
        },
        "gate_context": {
            "no_call_path_expected": no_call_path_expected,
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": blocking_reasons,
        "gate_state": gate_state,
        "allow_progress_to_h4c_governor_runtime": gate_ok,
        "recommended_action": (
            "may_progress_to_h4c_governor_runtime"
            if gate_ok else
            "inspect_compute_governor_gate_failures"
        ),
        "operator_message": (
            "H4-B compute governor gate passed. 当前主链仍满足 anti-abuse 计算约束。"
            if gate_ok else
            "H4-B compute governor gate blocked."
        ),
    }

    write_report(PREFIX, report)


if __name__ == "__main__":
    main()
