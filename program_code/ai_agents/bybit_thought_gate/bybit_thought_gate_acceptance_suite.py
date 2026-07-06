#!/usr/bin/env python3
from __future__ import annotations

import json
import time

from bybit_h1_report_utils import THOUGHT_GATE_DIR, make_check, read_json, save_latest_and_dated

try:
    from program_code.ml_training.advisory_review_packet import (
        build_advisory_review_packet,
        stable_sha256_json,
        validate_advisory_review_packet,
    )
except ModuleNotFoundError:  # pragma: no cover - import path depends on runner cwd/PYTHONPATH
    from ml_training.advisory_review_packet import (  # type: ignore
        build_advisory_review_packet,
        stable_sha256_json,
        validate_advisory_review_packet,
    )

RESP_CHECK = THOUGHT_GATE_DIR / "bybit_ai_response_check_latest.json"
GOV_DECISION = THOUGHT_GATE_DIR / "bybit_ai_governed_decision_latest.json"
INV = THOUGHT_GATE_DIR / "bybit_ai_invocation_attempt_latest.json"
REQ = THOUGHT_GATE_DIR / "bybit_ai_request_envelope_latest.json"


def _packet_validation_detail(packet):
    try:
        validate_advisory_review_packet(packet)
        return True, "valid"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}:{exc}"


def main() -> None:
    now_ms = int(time.time() * 1000)
    r = read_json(RESP_CHECK, {})
    g = read_json(GOV_DECISION, {})
    i = read_json(INV, {})
    q = read_json(REQ, {})

    parsed = (r.get("parsed_json_object") or {})
    guards = (g.get("governance_guards") or {})
    observation = (g.get("governed_observation") or {})
    governed_packet = g.get("advisory_review_packet")
    request_packet = q.get("advisory_review_packet")
    governed_packet_valid, governed_packet_detail = _packet_validation_detail(governed_packet)
    request_packet_valid, request_packet_detail = _packet_validation_detail(request_packet)

    terminal_mode_resp = r.get("terminal_mode")
    terminal_mode_gov = g.get("terminal_mode")
    accepted_terminal_mode = terminal_mode_resp
    should_call_ai = (i.get("request_summary") or {}).get("should_call_ai")
    invocation_state = i.get("invocation_state")

    checks = [
        make_check("response_check_overall_ok", r.get("overall_ok") is True, r.get("overall_ok")),
        make_check("governed_decision_ok", g.get("decision_ok") is True, g.get("decision_ok")),
        make_check("terminal_mode_consistent", terminal_mode_resp == terminal_mode_gov, {"resp": terminal_mode_resp, "gov": terminal_mode_gov}),
        make_check("analysis_mode_observation_only", observation.get("analysis_mode") == "observation_only", observation.get("analysis_mode")),
        make_check("action_bias_present", observation.get("action_bias") in {"long_bias", "short_bias", "flat_bias"}, observation.get("action_bias")),
        make_check("execution_authority_not_granted", guards.get("execution_authority") == "not_granted", guards.get("execution_authority")),
        make_check("live_execution_allowed_false", guards.get("live_execution_allowed") is False, guards.get("live_execution_allowed")),
        make_check("decision_lease_emitted_false", guards.get("decision_lease_emitted") is False, guards.get("decision_lease_emitted")),
        make_check("governed_advisory_review_packet_valid", governed_packet_valid, governed_packet_detail),
        make_check("request_advisory_review_packet_valid", request_packet_valid, request_packet_detail),
        make_check(
            "governed_packet_execution_authority_not_granted",
            isinstance(governed_packet, dict) and governed_packet.get("execution_authority") == "not_granted",
            None if not isinstance(governed_packet, dict) else governed_packet.get("execution_authority"),
        ),
        make_check(
            "governed_packet_decision_lease_false",
            isinstance(governed_packet, dict) and governed_packet.get("decision_lease_emitted") is False,
            None if not isinstance(governed_packet, dict) else governed_packet.get("decision_lease_emitted"),
        ),
        make_check(
            "governed_packet_demo_mutation_not_granted",
            isinstance(governed_packet, dict) and governed_packet.get("current_packet_grants_demo_mutation") is False,
            None if not isinstance(governed_packet, dict) else governed_packet.get("current_packet_grants_demo_mutation"),
        ),
    ]

    if terminal_mode_resp == "legal_no_ai_call":
        checks.append(make_check("accepted_terminal_mode_legal_no_ai_call", True, terminal_mode_resp))
        checks.append(make_check("should_call_ai_false", should_call_ai is False, should_call_ai))
        checks.append(make_check("invocation_not_json_ready_expected", invocation_state != "invocation_success_json_ready", invocation_state))
    else:
        checks.append(make_check("accepted_terminal_mode_provider_json_ready", terminal_mode_resp == "provider_json_ready", terminal_mode_resp))
        checks.append(make_check("invocation_state_json_ready", invocation_state == "invocation_success_json_ready", invocation_state))

    overall_ok = all(c["ok"] for c in checks)
    failed = [c["name"] for c in checks if not c["ok"]]
    input_hashes = {
        "ai_response_check": stable_sha256_json(r),
        "ai_governed_decision": stable_sha256_json(g),
        "ai_invocation_attempt": stable_sha256_json(i),
        "ai_request_envelope": stable_sha256_json(q),
        "acceptance_checks": stable_sha256_json(checks),
    }
    advisory_review_packet = build_advisory_review_packet(
        capability_id="bybit_thought_gate.h1i_acceptance_suite",
        producer="bybit_thought_gate_acceptance_suite",
        mode="thought_gate_acceptance_passed" if overall_ok else "thought_gate_acceptance_failed",
        input_hashes=input_hashes,
        budget_ref="bybit_ai_request_envelope.budget_context",
        notes=[
            "H1-I acceptance is an inactive advisory/check packet only.",
            "Acceptance does not grant execution, mutation, Cost Gate, Decision Lease, demo, live, or mainnet authority.",
        ],
    )

    report = {
        "suite_type": "bybit_thought_gate_acceptance_suite",
        "suite_version": "v2",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "H1-I",
        "overall_ok": overall_ok,
        "accepted_terminal_mode": accepted_terminal_mode,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
        "input_hashes": input_hashes,
        "advisory_review_packet": advisory_review_packet,
        "suite_state": "thought_gate_acceptance_passed" if overall_ok else "thought_gate_acceptance_failed",
        "recommended_action": "may_progress_to_h1i_summary" if overall_ok else "inspect_h1_acceptance_failures",
        "operator_message": (
            "H1-I acceptance suite passed. Legal no-call terminal mode is accepted as a governed read-only AI observation path."
            if overall_ok and accepted_terminal_mode == "legal_no_ai_call"
            else (
                "H1-I acceptance suite passed. Thought-gate chain is closed as a governed read-only AI observation path."
                if overall_ok
                else "H1-I acceptance suite failed. Inspect failed_checks before chapter closure."
            )
        ),
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_thought_gate_acceptance_suite", report)


if __name__ == "__main__":
    main()
