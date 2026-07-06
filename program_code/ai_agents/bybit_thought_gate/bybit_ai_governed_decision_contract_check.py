#!/usr/bin/env python3
from __future__ import annotations

import json
import time

from bybit_h1_report_utils import THOUGHT_GATE_DIR, make_check, read_json, save_latest_and_dated

try:
    from program_code.ml_training.advisory_review_packet import validate_advisory_review_packet
except ModuleNotFoundError:  # pragma: no cover - import path depends on runner cwd/PYTHONPATH
    from ml_training.advisory_review_packet import validate_advisory_review_packet  # type: ignore

REPORT_PATH = THOUGHT_GATE_DIR / "bybit_ai_governed_decision_latest.json"


def _packet_validation_detail(packet):
    try:
        validate_advisory_review_packet(packet)
        return True, "valid"
    except Exception as exc:
        return False, f"{exc.__class__.__name__}:{exc}"


def main() -> None:
    now_ms = int(time.time() * 1000)
    obj = read_json(REPORT_PATH, {})
    guards = obj.get("governance_guards") or {}
    packet = obj.get("advisory_review_packet")
    packet_valid, packet_detail = _packet_validation_detail(packet)

    checks = [
        make_check("report_exists", bool(obj), str(REPORT_PATH)),
        make_check("decision_type_expected", obj.get("decision_type") == "bybit_ai_governed_decision", obj.get("decision_type")),
        make_check("decision_version_supported", obj.get("decision_version") in {"v1", "v2"}, obj.get("decision_version")),
        make_check("stage_h1h", obj.get("stage") == "H1-H", obj.get("stage")),
        make_check("decision_ok_bool", isinstance(obj.get("decision_ok"), bool), obj.get("decision_ok")),
        make_check(
            "decision_state_known",
            obj.get("decision_state") in {
                "governed_observation_blocked",
                "governed_observation_ready",
                "governed_observation_ready_ai_called",
                "governed_observation_ready_no_ai_call",
            },
            obj.get("decision_state"),
        ),
        make_check(
            "terminal_mode_known",
            obj.get("terminal_mode") in {None, "provider_json_ready", "legal_no_ai_call"},
            obj.get("terminal_mode"),
        ),
        make_check("governance_guards_dict", isinstance(guards, dict), type(guards).__name__),
        make_check("system_mode_read_only", guards.get("system_mode") == "read_only", guards.get("system_mode")),
        make_check("execution_state_disabled", guards.get("execution_state") == "disabled", guards.get("execution_state")),
        make_check("execution_authority_not_granted", guards.get("execution_authority") == "not_granted", guards.get("execution_authority")),
        make_check("live_execution_allowed_false", guards.get("live_execution_allowed") is False, guards.get("live_execution_allowed")),
        make_check("decision_lease_emitted_false", guards.get("decision_lease_emitted") is False, guards.get("decision_lease_emitted")),
        make_check("active_false", guards.get("active") is False, guards.get("active")),
        make_check("no_order_mutation_true", guards.get("no_order_mutation") is True, guards.get("no_order_mutation")),
        make_check("no_cost_gate_mutation_true", guards.get("no_cost_gate_mutation") is True, guards.get("no_cost_gate_mutation")),
        make_check("demo_mutation_not_granted", guards.get("current_packet_grants_demo_mutation") is False, guards.get("current_packet_grants_demo_mutation")),
        make_check("advisory_review_packet_valid", packet_valid, packet_detail),
        make_check(
            "advisory_packet_execution_authority_not_granted",
            isinstance(packet, dict) and packet.get("execution_authority") == "not_granted",
            None if not isinstance(packet, dict) else packet.get("execution_authority"),
        ),
        make_check(
            "advisory_packet_decision_lease_false",
            isinstance(packet, dict) and packet.get("decision_lease_emitted") is False,
            None if not isinstance(packet, dict) else packet.get("decision_lease_emitted"),
        ),
        make_check("allow_progress_bool", isinstance(obj.get("allow_progress_to_h1i_acceptance"), bool), obj.get("allow_progress_to_h1i_acceptance")),
    ]
    overall_ok = all(c["ok"] for c in checks)
    failed = [c["name"] for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_ai_governed_decision_contract_check",
        "report_version": "v2",
        "ts_ms": now_ms,
        "overall_ok": overall_ok,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    save_latest_and_dated("bybit_ai_governed_decision_contract", report)


if __name__ == "__main__":
    main()
