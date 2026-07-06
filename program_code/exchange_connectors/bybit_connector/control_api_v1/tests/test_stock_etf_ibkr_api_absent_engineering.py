"""API-absent IBKR engineering packet tests."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


SRV_ROOT = Path(__file__).resolve().parents[5]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from program_code.broker_connectors.ibkr_connector import (  # noqa: E402
    IBKR_API_ABSENT_ENGINEERING_PACKET_ID,
    IBKR_API_ABSENT_MODE,
    IBKR_PHASE2_GATE_CANDIDATE_STATUS,
    build_api_absent_engineering_packet,
)
from program_code.broker_connectors.ibkr_connector.fixtures import (  # noqa: E402
    api_absent_engineering_fixture,
)


EXPECTED_LOOP_ORDER = [
    "L0_BASELINE_AUDIT",
    "L1_PHASE2_GATE_SCAFFOLD_NO_CONTACT",
    "L2_READONLY_RUNTIME_ABSTRACTION_NO_CONTACT",
    "L3_DATA_FOUNDATION_AND_SCHEMA",
    "L4_SHADOW_COLLECTOR_SIMULATED",
    "L5_PAPER_ORDER_LIFECYCLE_SIMULATED",
    "L6_EVIDENCE_AI_ML_LOOP_OFFLINE",
    "L7_RELEASE_DISABLE_PACKET",
]

EXPECTED_EXTERNAL_PENDING = [
    "real_ibkr_paper_or_readonly_credential",
    "operator_gateway_or_tws_session",
    "operator_approval_for_external_contact",
    "immutable_real_phase2_pass_artifact",
    "real_account_fingerprint_attestation",
    "real_market_data_entitlement_attestation",
]

EXPECTED_BOUNDARY_PROOF = [
    "ibkr_contact_performed=false",
    "network_contact_performed=false",
    "secret_content_loaded=false",
    "secret_content_serialized=false",
    "connector_runtime_started=false",
    "paper_order_routed=false",
    "paper_fill_imported=false",
    "db_apply_performed=false",
    "mcp_runtime_execution=false",
    "python_broker_write_authority=false",
    "bybit_path_reused=false",
    "live_or_tiny_live_authorized=false",
]

FALSE_PATHS = [
    ("phase2_gate_candidate", "real_contact_authorized"),
    ("phase2_gate_candidate", "first_ibkr_contact_performed"),
    ("readonly_transport_fixture", "real_transport_enabled"),
    ("readonly_transport_fixture", "network_contact_performed"),
    ("readonly_transport_fixture", "secret_content_loaded"),
    ("readonly_transport_fixture", "live_channel_exposed"),
    ("data_foundation_fixture", "broker_dependency_required"),
    ("shadow_collector_fixture", "shadow_signal_emitted_to_broker"),
    ("shadow_collector_fixture", "scorecard_writer_started"),
    ("paper_lifecycle_fixture", "python_broker_write_authority"),
    ("paper_lifecycle_fixture", "real_broker_route_enabled"),
    ("paper_lifecycle_fixture", "bybit_path_reused"),
    ("evidence_ai_ml_fixture", "ai_ml_execution_authority"),
    ("evidence_ai_ml_fixture", "mutation_envelope_authorized"),
    ("evidence_ai_ml_fixture", "paper_shadow_window_complete_claimed"),
    ("release_disable_fixture", "live_or_tiny_live_authorized"),
    ("release_disable_fixture", "live_secret_slot_allowed"),
    ("release_disable_fixture", "live_order_path_allowed"),
    ("external_verification_readiness_fixture", "first_real_contact_allowed_before_pass"),
    ("external_verification_readiness_fixture", "live_or_tiny_live_authorized"),
    ("external_verification_readiness_fixture", "runtime_mcp_required"),
    ("external_verification_readiness_fixture", "python_broker_write_authority"),
]

TRUE_PATHS = [
    ("phase2_gate_candidate", "secret_slot_contract_required"),
    ("phase2_gate_candidate", "session_attestation_required"),
    ("phase2_gate_candidate", "operator_review_required"),
    ("phase2_gate_candidate", "live_secret_absent_required"),
    ("phase2_gate_candidate", "live_ports_denied"),
    ("readonly_transport_fixture", "fail_closed_without_external_attestation"),
    ("readonly_transport_fixture", "account_snapshot_fixture_ready"),
    ("readonly_transport_fixture", "contract_details_fixture_ready"),
    ("readonly_transport_fixture", "market_data_fixture_ready"),
    ("data_foundation_fixture", "instrument_identity_contract_ready"),
    ("data_foundation_fixture", "pit_universe_contract_ready"),
    ("data_foundation_fixture", "reference_data_contract_ready"),
    ("data_foundation_fixture", "market_data_provenance_contract_ready"),
    ("data_foundation_fixture", "db_schema_source_or_dry_run_only"),
    ("shadow_collector_fixture", "simulated_shadow_flow_ready"),
    ("shadow_collector_fixture", "after_cost_required"),
    ("shadow_collector_fixture", "point_in_time_required"),
    ("shadow_collector_fixture", "replayable_from_fixtures"),
    ("paper_lifecycle_fixture", "simulated_lifecycle_ready"),
    ("paper_lifecycle_fixture", "rust_authority_required"),
    ("paper_lifecycle_fixture", "decision_lease_required"),
    ("paper_lifecycle_fixture", "guardian_required"),
    ("paper_lifecycle_fixture", "risk_config_hash_required"),
    ("paper_lifecycle_fixture", "idempotency_required"),
    ("paper_lifecycle_fixture", "audit_event_required"),
    ("evidence_ai_ml_fixture", "offline_evidence_clock_ready"),
    ("evidence_ai_ml_fixture", "scorecard_derivation_ready"),
    ("evidence_ai_ml_fixture", "proof_packet_inputs_replayable"),
    ("evidence_ai_ml_fixture", "ai_ml_advisory_only"),
    ("release_disable_fixture", "release_packet_ready_api_absent"),
    ("release_disable_fixture", "disable_cleanup_runbook_ready"),
    ("release_disable_fixture", "external_verification_checklist_required"),
    ("external_verification_readiness_fixture", "credential_required_for_next_external_step"),
    (
        "external_verification_readiness_fixture",
        "gateway_session_required_for_next_external_step",
    ),
    (
        "external_verification_readiness_fixture",
        "operator_approval_required_for_next_external_step",
    ),
]


def test_api_absent_engineering_packet_reaches_terminal_api_absent_state() -> None:
    packet = build_api_absent_engineering_packet().to_dict()

    assert packet["packet_id"] == IBKR_API_ABSENT_ENGINEERING_PACKET_ID
    assert packet["source_version"] == 1
    assert packet["mode"] == IBKR_API_ABSENT_MODE
    assert packet["status"] == "DEMO_READY_API_ABSENT"
    assert packet["phase2_gate_candidate_status"] == IBKR_PHASE2_GATE_CANDIDATE_STATUS
    assert packet["asset_lane"] == "stock_etf_cash"
    assert packet["broker"] == "ibkr"
    assert packet["environment"] == "paper"
    assert packet["external_verification_pending"] == EXPECTED_EXTERNAL_PENDING
    assert packet["boundary_proof"] == EXPECTED_BOUNDARY_PROOF

    loops = packet["loops"]
    assert [loop["current_loop"] for loop in loops] == EXPECTED_LOOP_ORDER
    assert [loop["verdict"] for loop in loops[:-1]] == ["ADVANCE"] * 7
    assert loops[-1]["verdict"] == "EXIT"
    assert loops[-1]["next_loop_or_exit"] == "DEMO_READY_API_ABSENT"

    for loop in loops:
        assert loop["mode"] == IBKR_API_ABSENT_MODE
        assert loop["boundary_proof"] == EXPECTED_BOUNDARY_PROOF
        assert loop["external_verification_pending"] == EXPECTED_EXTERNAL_PENDING
        assert loop["implemented_changes"]
        assert loop["evidence_artifacts"]
        assert loop["tests"]


def test_api_absent_fixture_keeps_real_ibkr_transport_and_live_paths_closed() -> None:
    packet = api_absent_engineering_fixture()

    assert packet["phase2_gate_candidate"]["status"] == "PENDING_EXTERNAL_ATTESTATION"
    assert packet["phase2_gate_candidate"]["external_verification_pending"] == (
        EXPECTED_EXTERNAL_PENDING
    )
    assert packet["readonly_transport_fixture"]["transport"] == "local_fixture_transport"
    readiness = packet["external_verification_readiness_fixture"]
    assert readiness["readiness_packet_id"] == "ibkr_external_verification_readiness_v1"
    assert readiness["status"] == "external_verification_pending"
    assert readiness["operator_checklist"] == [
        "confirm_paper_or_readonly_account_only",
        "confirm_no_live_account_fingerprint",
        "confirm_operator_contact_window",
        "confirm_redacted_artifact_storage_path",
        "confirm_pm_operator_reviewers_present",
    ]
    assert readiness["gateway_topology_checklist"] == [
        "ib_gateway_or_tws_running_on_trade_core",
        "loopback_host_only_127_0_0_1",
        "paper_gateway_port_4002_only",
        "live_ports_4001_and_7496_denied",
        "deterministic_client_id_recorded",
        "api_server_version_recorded",
    ]
    assert readiness["secret_fingerprint_checklist"] == [
        "readonly_or_paper_slot_fingerprint_recorded",
        "live_slot_absent_or_empty",
        "owner_only_permissions",
        "env_var_fallback_denied",
        "secret_content_not_serialized",
        "account_id_not_serialized",
    ]
    assert readiness["phase2_real_contact_runbook"] == [
        "seal_no_contact_candidate_packet",
        "collect_secret_slot_fingerprint_evidence",
        "collect_loopback_topology_evidence",
        "collect_session_attestation_evidence",
        "run_redaction_and_rate_limit_policy_checks",
        "seal_immutable_phase2_pass_artifact_before_first_contact",
        "perform_first_readonly_healthcheck_only_after_pass",
    ]

    for section, key in FALSE_PATHS:
        assert packet[section][key] is False, f"{section}.{key}"
    for section, key in TRUE_PATHS:
        assert packet[section][key] is True, f"{section}.{key}"


def test_api_absent_engineering_module_remains_static_and_side_effect_free() -> None:
    path = (
        SRV_ROOT
        / "program_code"
        / "broker_connectors"
        / "ibkr_connector"
        / "api_absent_engineering.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    forbidden_import_roots = {
        "asyncio",
        "datetime",
        "ib_insync",
        "ibapi",
        "httpx",
        "os",
        "requests",
        "socket",
        "subprocess",
        "threading",
        "time",
        "urllib",
        "websocket",
        "websockets",
    }
    forbidden_calls = {
        "open",
        "read_text",
        "write_text",
        "getenv",
        "sleep",
        "run",
        "Popen",
    }
    forbidden_strings = {
        "stock_etf.submit_paper_order",
        "stock_etf.cancel_paper_order",
        "stock_etf.replace_paper_order",
        "ibkr.place_order",
        "ibkr.submit_order",
        "ibkr.cancel_order",
        "ibkr.replace_order",
    }

    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".", 1)[0]
                if root in forbidden_import_roots:
                    violations.append(f"forbidden import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if root in forbidden_import_roots:
                violations.append(f"forbidden import {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in forbidden_calls:
                violations.append(f"forbidden call {name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in forbidden_strings:
                violations.append(f"forbidden broker string {node.value}")

    assert violations == []
