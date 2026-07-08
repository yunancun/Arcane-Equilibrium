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
    IBKR_DEMO_ENGINE_ID,
    IBKR_DUAL_ENGINE_CONTRACT_ID,
    IBKR_LIVE_ENGINE_ID,
    IBKR_PHASE2_GATE_CANDIDATE_STATUS,
    build_api_absent_engineering_packet,
    ibkr_dual_engine_contract_fixture,
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

EXPECTED_PHASE2_RESEAL_TRIGGERS = [
    "engine_profile_change",
    "api_binding_change",
    "account_fingerprint_change",
    "slot_capability_change",
    "gateway_process_restart",
    "gateway_port_change",
    "risk_policy_hash_change",
    "decision_lease_policy_change",
    "operator_epoch_revoke",
]

EXPECTED_READ_WRITE_INTERFACE_ACTIONS = [
    "server_time_read",
    "connection_health_read",
    "account_summary_snapshot_read",
    "portfolio_positions_snapshot_read",
    "contract_details_read",
    "market_data_snapshot_read",
    "historical_bars_read",
    "open_orders_read",
    "executions_commissions_read",
    "paper_or_authorized_order_submit",
    "paper_or_authorized_order_cancel",
    "paper_or_authorized_order_replace",
]

EXPECTED_DENIED_FUNDS_MOVEMENT_ACTIONS = [
    "account_transfer",
    "cash_withdrawal",
    "internal_transfer",
    "external_transfer",
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


def test_api_absent_engineering_packet_advances_to_work_queue_not_terminal() -> None:
    packet = build_api_absent_engineering_packet().to_dict()

    assert packet["packet_id"] == IBKR_API_ABSENT_ENGINEERING_PACKET_ID
    assert packet["source_version"] == 1
    assert packet["mode"] == IBKR_API_ABSENT_MODE
    assert packet["status"] == "EXTERNAL_VERIFICATION_PENDING"
    assert packet["phase2_gate_candidate_status"] == IBKR_PHASE2_GATE_CANDIDATE_STATUS
    assert packet["asset_lane"] == "stock_etf_cash"
    assert packet["broker"] == "ibkr"
    assert packet["environment"] == "paper"
    assert packet["external_verification_pending"] == EXPECTED_EXTERNAL_PENDING
    assert packet["boundary_proof"] == EXPECTED_BOUNDARY_PROOF

    loops = packet["loops"]
    assert [loop["current_loop"] for loop in loops] == EXPECTED_LOOP_ORDER
    assert [loop["verdict"] for loop in loops] == ["ADVANCE"] * 8
    assert loops[-1]["next_loop_or_exit"] == "L8_WORK_QUEUE_AUTODISPATCH"

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


def test_dual_engine_fixture_matches_latest_no_contact_design() -> None:
    packet = api_absent_engineering_fixture()
    dual = packet["dual_engine_fixture"]

    assert dual == ibkr_dual_engine_contract_fixture()
    assert dual["contract_id"] == IBKR_DUAL_ENGINE_CONTRACT_ID
    assert dual["source_version"] == 1
    assert dual["status"] == "SOURCE_ONLY_NO_CONTACT"
    assert dual["broker"] == "ibkr"
    assert dual["asset_lane"] == "stock_etf_cash"

    profiles = {profile["engine_id"]: profile for profile in dual["profiles"]}
    assert list(profiles) == [IBKR_DEMO_ENGINE_ID, IBKR_LIVE_ENGINE_ID]

    demo = profiles[IBKR_DEMO_ENGINE_ID]
    assert demo["role"] == "paper_demo_execution_and_evidence"
    assert demo["api_binding_kind"] == "paper_or_demo"
    assert demo["risk_profile"] == "demo_risk_profile"
    assert demo["gate_profile"] == "paper_demo_gate_profile"
    assert demo["default_control_port"] == 8711
    assert demo["default_engine_ipc_port"] == 18790
    assert demo["broker_gateway_ports"] == [4002]
    assert demo["can_use_paper_api_for_local_engine_tests"] is True
    assert demo["can_bind_true_live_api_after_governance"] is False

    live = profiles[IBKR_LIVE_ENGINE_ID]
    assert live["role"] == "live_grade_gate_risk_session_rehearsal"
    assert live["api_binding_kind"] == "live_or_second_paper_for_comparison"
    assert live["risk_profile"] == "live_grade_risk_profile"
    assert live["gate_profile"] == "live_grade_gate_profile"
    assert live["default_control_port"] == 8711
    assert live["default_engine_ipc_port"] == 18791
    assert live["broker_gateway_ports"] == [4001, 7496]
    assert live["can_use_paper_api_for_local_engine_tests"] is True
    assert live["can_bind_true_live_api_after_governance"] is True

    for name, profile in profiles.items():
        assert profile["read_write_api_interface_present"] is True, name
        assert profile["true_live_api_bound_now"] is False, name
        assert profile["real_ibkr_contact_enabled"] is False, name
        assert profile["broker_order_route_enabled_now"] is False, name
        assert profile["live_order_route_authorized_now"] is False, name
        assert profile["withdraw_transfer_supported"] is False, name
        assert profile["secret_content_loaded"] is False, name
        assert profile["secret_content_serialized"] is False, name
        assert profile["slot_metadata_only"] is True, name
        assert profile["session_epoch_required"] is True, name
        assert profile["per_call_full_seal_check_required"] is False, name
        assert profile["per_call_cached_epoch_check_required"] is True, name
        assert profile["bybit_path_reused"] is False, name

    assert dual["service_port_plan"] == {
        "runtime_owner": "trade-core",
        "bybit_control_api_reference_port": 8710,
        "bybit_openclaw_proxy_reference_port": 18789,
        "ibkr_control_api_reserved_port": 8711,
        "ibkr_demo_engine_ipc_reserved_port": 18790,
        "ibkr_live_engine_ipc_reserved_port": 18791,
        "service_started": False,
        "listener_bound": False,
    }
    assert dual["ibkr_gateway_port_plan"] == {
        "paper_gateway_port": 4002,
        "live_gateway_port": 4001,
        "live_tws_port": 7496,
        "paper_gateway_authorized_now": False,
        "true_live_gateway_authorized_now": False,
        "source_only_reserved": True,
    }


def test_dual_engine_fixture_keeps_hot_path_seal_and_funds_movement_boundary() -> None:
    dual = ibkr_dual_engine_contract_fixture()
    seal = dual["phase2_seal_policy"]

    assert seal["full_phase2_seal_required_before_session_admission"] is True
    assert seal["session_admission_epoch_required"] is True
    assert seal["per_order_full_seal_check_required"] is False
    assert seal["per_call_cached_epoch_and_capability_check_required"] is True
    assert seal["decision_lease_required_per_order"] is True
    assert seal["risk_guard_required_per_order"] is True
    assert seal["audit_event_required_per_order"] is True
    assert seal["reseal_triggers"] == EXPECTED_PHASE2_RESEAL_TRIGGERS
    assert seal["hot_path_latency_model"] == (
        "check_cached_epoch_capability_lease_risk_and_audit_not_full_artifact"
    )

    policy = dual["interface_policy"]
    assert policy["read_write_api_interface_default"] is True
    assert policy["read_write_actions"] == EXPECTED_READ_WRITE_INTERFACE_ACTIONS
    assert policy["withdraw_transfer_actions_supported"] is False
    assert policy["denied_funds_movement_actions"] == (
        EXPECTED_DENIED_FUNDS_MOVEMENT_ACTIONS
    )
    assert policy["product_family_future_extension_allowed"] is True
    assert policy["current_governed_lane"] == "stock_etf_cash"
    assert policy["python_broker_write_authority"] is False
    assert policy["rust_authority_required_for_any_broker_write"] is True

    authority = dual["current_authority"]
    assert authority == {
        "real_ibkr_contact_enabled": False,
        "connector_runtime_started": False,
        "secret_content_loaded": False,
        "secret_content_serialized": False,
        "demo_order_route_enabled": False,
        "live_order_route_enabled": False,
        "true_live_api_bound": False,
        "runtime_mcp_required": False,
        "bybit_path_reused": False,
        "withdraw_or_transfer_path_present": False,
    }


def test_dual_engine_template_pins_source_contract_values() -> None:
    template_path = SRV_ROOT / "settings" / "broker" / (
        "ibkr_dual_engine_contract.template.toml"
    )
    source = template_path.read_text(encoding="utf-8")

    expected_fragments = [
        'contract_id = "ibkr_dual_engine_local_contract_v1"',
        'engine_id = "ibkr_demo_engine"',
        'engine_id = "ibkr_live_engine"',
        "bybit_control_api_reference_port = 8710",
        "bybit_openclaw_proxy_reference_port = 18789",
        "ibkr_control_api_reserved_port = 8711",
        "ibkr_demo_engine_ipc_reserved_port = 18790",
        "ibkr_live_engine_ipc_reserved_port = 18791",
        "paper_gateway_port = 4002",
        "live_gateway_port = 4001",
        "live_tws_port = 7496",
        "read_write_api_interface_default = true",
        "withdraw_transfer_actions_supported = false",
        "per_order_full_seal_check_required = false",
        "per_call_cached_epoch_and_capability_check_required = true",
        "true_live_api_bound = false",
        "withdraw_or_transfer_path_present = false",
    ]

    assert template_path.exists()
    for fragment in expected_fragments:
        assert fragment in source


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
