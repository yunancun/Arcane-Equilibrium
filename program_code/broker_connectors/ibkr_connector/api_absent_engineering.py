"""API-absent engineering packet for the IBKR Stock/ETF lane.

This module is a deterministic, no-contact readiness fixture. It does not
import an IBKR SDK, open sockets, read secrets, route paper orders, import
broker fills, write evidence, or mutate Bybit behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field


IBKR_API_ABSENT_ENGINEERING_PACKET_ID = (
    "ibkr_demo_ready_api_absent_engineering_packet_v1"
)
IBKR_API_ABSENT_MODE = "DEMO_READY_API_ABSENT"
IBKR_PHASE2_GATE_CANDIDATE_STATUS = "PENDING_EXTERNAL_ATTESTATION"

API_ABSENT_LOOP_ORDER = (
    "L0_BASELINE_AUDIT",
    "L1_PHASE2_GATE_SCAFFOLD_NO_CONTACT",
    "L2_READONLY_RUNTIME_ABSTRACTION_NO_CONTACT",
    "L3_DATA_FOUNDATION_AND_SCHEMA",
    "L4_SHADOW_COLLECTOR_SIMULATED",
    "L5_PAPER_ORDER_LIFECYCLE_SIMULATED",
    "L6_EVIDENCE_AI_ML_LOOP_OFFLINE",
    "L7_RELEASE_DISABLE_PACKET",
)

EXTERNAL_VERIFICATION_PENDING = (
    "real_ibkr_paper_or_readonly_credential",
    "operator_gateway_or_tws_session",
    "operator_approval_for_external_contact",
    "immutable_real_phase2_pass_artifact",
    "real_account_fingerprint_attestation",
    "real_market_data_entitlement_attestation",
)

NO_CONTACT_BOUNDARY_PROOF = (
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
)


@dataclass(frozen=True)
class IbkrApiAbsentLoopDecision:
    """Loop-level decision payload matching the API-absent engineering loop."""

    current_loop: str
    verdict: str
    implemented_changes: tuple[str, ...]
    evidence_artifacts: tuple[str, ...]
    tests: tuple[str, ...]
    next_loop_or_exit: str
    reason: str
    mode: str = IBKR_API_ABSENT_MODE
    boundary_proof: tuple[str, ...] = NO_CONTACT_BOUNDARY_PROOF
    external_verification_pending: tuple[str, ...] = EXTERNAL_VERIFICATION_PENDING

    def to_dict(self) -> dict[str, object]:
        return {
            "current_loop": self.current_loop,
            "verdict": self.verdict,
            "mode": self.mode,
            "implemented_changes": list(self.implemented_changes),
            "evidence_artifacts": list(self.evidence_artifacts),
            "tests": list(self.tests),
            "boundary_proof": list(self.boundary_proof),
            "external_verification_pending": list(self.external_verification_pending),
            "next_loop_or_exit": self.next_loop_or_exit,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class IbkrApiAbsentEngineeringPacket:
    """Single no-contact packet that ties L0-L7 engineering fixtures together."""

    packet_id: str = IBKR_API_ABSENT_ENGINEERING_PACKET_ID
    source_version: int = 1
    mode: str = IBKR_API_ABSENT_MODE
    status: str = IBKR_API_ABSENT_MODE
    phase2_gate_candidate_status: str = IBKR_PHASE2_GATE_CANDIDATE_STATUS
    asset_lane: str = "stock_etf_cash"
    broker: str = "ibkr"
    environment: str = "paper"
    loops: tuple[IbkrApiAbsentLoopDecision, ...] = field(default_factory=tuple)
    phase2_gate_candidate: dict[str, object] = field(default_factory=dict)
    readonly_transport_fixture: dict[str, object] = field(default_factory=dict)
    data_foundation_fixture: dict[str, object] = field(default_factory=dict)
    shadow_collector_fixture: dict[str, object] = field(default_factory=dict)
    paper_lifecycle_fixture: dict[str, object] = field(default_factory=dict)
    evidence_ai_ml_fixture: dict[str, object] = field(default_factory=dict)
    release_disable_fixture: dict[str, object] = field(default_factory=dict)
    external_verification_readiness_fixture: dict[str, object] = field(default_factory=dict)
    external_verification_pending: tuple[str, ...] = EXTERNAL_VERIFICATION_PENDING
    boundary_proof: tuple[str, ...] = NO_CONTACT_BOUNDARY_PROOF

    def to_dict(self) -> dict[str, object]:
        return {
            "packet_id": self.packet_id,
            "source_version": self.source_version,
            "mode": self.mode,
            "status": self.status,
            "phase2_gate_candidate_status": self.phase2_gate_candidate_status,
            "asset_lane": self.asset_lane,
            "broker": self.broker,
            "environment": self.environment,
            "loops": [loop.to_dict() for loop in self.loops],
            "phase2_gate_candidate": dict(self.phase2_gate_candidate),
            "readonly_transport_fixture": dict(self.readonly_transport_fixture),
            "data_foundation_fixture": dict(self.data_foundation_fixture),
            "shadow_collector_fixture": dict(self.shadow_collector_fixture),
            "paper_lifecycle_fixture": dict(self.paper_lifecycle_fixture),
            "evidence_ai_ml_fixture": dict(self.evidence_ai_ml_fixture),
            "release_disable_fixture": dict(self.release_disable_fixture),
            "external_verification_readiness_fixture": dict(
                self.external_verification_readiness_fixture
            ),
            "external_verification_pending": list(self.external_verification_pending),
            "boundary_proof": list(self.boundary_proof),
        }


def build_api_absent_engineering_packet() -> IbkrApiAbsentEngineeringPacket:
    """Build the deterministic no-contact engineering packet."""

    loops = (
        IbkrApiAbsentLoopDecision(
            current_loop="L0_BASELINE_AUDIT",
            verdict="ADVANCE",
            implemented_changes=(
                "baseline_gap_report_recorded",
                "forbidden_bybit_reuse_identified",
            ),
            evidence_artifacts=(
                "docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ibkr_demo_ready_api_absent_l0_baseline_gap_report.md",
            ),
            tests=("python_static_guard_subset",),
            next_loop_or_exit="L1_PHASE2_GATE_SCAFFOLD_NO_CONTACT",
            reason="no hard engineering blocker found in source-only baseline",
        ),
        IbkrApiAbsentLoopDecision(
            current_loop="L1_PHASE2_GATE_SCAFFOLD_NO_CONTACT",
            verdict="ADVANCE",
            implemented_changes=(
                "phase2_no_contact_gate_candidate_recorded",
                "external_attestation_gap_marked_pending",
            ),
            evidence_artifacts=(
                "ibkr_demo_ready_api_absent_engineering_packet_v1.phase2_gate_candidate",
            ),
            tests=("api_absent_packet_tests",),
            next_loop_or_exit="L2_READONLY_RUNTIME_ABSTRACTION_NO_CONTACT",
            reason="Phase2 blocks real IBKR contact only; no-contact scaffold can advance",
        ),
        IbkrApiAbsentLoopDecision(
            current_loop="L2_READONLY_RUNTIME_ABSTRACTION_NO_CONTACT",
            verdict="ADVANCE",
            implemented_changes=(
                "local_fixture_readonly_transport_recorded",
                "real_transport_fail_closed_by_default",
            ),
            evidence_artifacts=(
                "ibkr_demo_ready_api_absent_engineering_packet_v1.readonly_transport_fixture",
            ),
            tests=("api_absent_packet_tests",),
            next_loop_or_exit="L3_DATA_FOUNDATION_AND_SCHEMA",
            reason="read-only behavior is represented by local fixtures with no socket or secret access",
        ),
        IbkrApiAbsentLoopDecision(
            current_loop="L3_DATA_FOUNDATION_AND_SCHEMA",
            verdict="ADVANCE",
            implemented_changes=(
                "pit_universe_and_reference_data_contracts_linked",
                "cost_model_and_market_session_scaffold_linked",
            ),
            evidence_artifacts=(
                "settings/broker/stock_etf_instrument_identity.template.toml",
                "settings/broker/stock_etf_pit_universe.template.toml",
                "settings/broker/stock_etf_reference_data_sources.template.toml",
                "settings/broker/stock_market_data_provenance.template.toml",
            ),
            tests=("api_absent_packet_tests",),
            next_loop_or_exit="L4_SHADOW_COLLECTOR_SIMULATED",
            reason="data foundation remains source/dry-run and broker independent",
        ),
        IbkrApiAbsentLoopDecision(
            current_loop="L4_SHADOW_COLLECTOR_SIMULATED",
            verdict="ADVANCE",
            implemented_changes=(
                "simulated_shadow_collector_fixture_recorded",
                "after_cost_point_in_time_replay_requirements_recorded",
            ),
            evidence_artifacts=(
                "settings/broker/stock_etf_shadow_signal_request.template.toml",
                "settings/broker/stock_etf_paper_shadow_reconciliation.template.toml",
            ),
            tests=("api_absent_packet_tests",),
            next_loop_or_exit="L5_PAPER_ORDER_LIFECYCLE_SIMULATED",
            reason="shadow flow uses fixtures and cannot emit live or paper broker actions",
        ),
        IbkrApiAbsentLoopDecision(
            current_loop="L5_PAPER_ORDER_LIFECYCLE_SIMULATED",
            verdict="ADVANCE",
            implemented_changes=(
                "simulated_paper_lifecycle_fixture_recorded",
                "decision_lease_guardian_risk_idempotency_audit_requirements_recorded",
            ),
            evidence_artifacts=(
                "settings/broker/stock_etf_paper_order_request.template.toml",
                "settings/broker/ibkr_paper_order_lifecycle.toml",
            ),
            tests=("api_absent_packet_tests",),
            next_loop_or_exit="L6_EVIDENCE_AI_ML_LOOP_OFFLINE",
            reason="paper lifecycle fixture keeps Rust authority required and Python broker writes denied",
        ),
        IbkrApiAbsentLoopDecision(
            current_loop="L6_EVIDENCE_AI_ML_LOOP_OFFLINE",
            verdict="ADVANCE",
            implemented_changes=(
                "offline_evidence_clock_and_scorecard_fixture_recorded",
                "ai_ml_advisory_only_boundary_recorded",
            ),
            evidence_artifacts=(
                "settings/broker/stock_etf_phase3_evidence_contracts.toml",
                "settings/broker/stock_etf_scorecard_inputs.template.toml",
                "settings/broker/stock_etf_scorecard_derivation.template.toml",
                "settings/broker/stock_etf_scorecard_verdict.template.toml",
            ),
            tests=("api_absent_packet_tests",),
            next_loop_or_exit="L7_RELEASE_DISABLE_PACKET",
            reason="offline evidence is replayable from fixtures and grants no execution authority",
        ),
        IbkrApiAbsentLoopDecision(
            current_loop="L7_RELEASE_DISABLE_PACKET",
            verdict="EXIT",
            implemented_changes=(
                "api_absent_release_packet_fixture_recorded",
                "disable_cleanup_and_external_verification_checklist_recorded",
            ),
            evidence_artifacts=(
                "settings/broker/stock_etf_release_packet.template.toml",
                "settings/broker/stock_etf_disable_cleanup_runbook.template.toml",
                "ibkr_demo_ready_api_absent_engineering_packet_v1.release_disable_fixture",
            ),
            tests=("api_absent_packet_tests",),
            next_loop_or_exit="DEMO_READY_API_ABSENT",
            reason="engineering packet is complete while real IBKR external verification remains pending",
        ),
    )

    return IbkrApiAbsentEngineeringPacket(
        loops=loops,
        phase2_gate_candidate={
            "contract_id": "phase2_ibkr_external_surface_gate_v1",
            "status": IBKR_PHASE2_GATE_CANDIDATE_STATUS,
            "real_contact_authorized": False,
            "first_ibkr_contact_performed": False,
            "secret_slot_contract_required": True,
            "session_attestation_required": True,
            "operator_review_required": True,
            "external_verification_pending": list(EXTERNAL_VERIFICATION_PENDING),
            "live_secret_absent_required": True,
            "live_ports_denied": True,
        },
        readonly_transport_fixture={
            "transport": "local_fixture_transport",
            "real_transport_enabled": False,
            "fail_closed_without_external_attestation": True,
            "network_contact_performed": False,
            "secret_content_loaded": False,
            "account_snapshot_fixture_ready": True,
            "contract_details_fixture_ready": True,
            "market_data_fixture_ready": True,
            "live_channel_exposed": False,
        },
        data_foundation_fixture={
            "instrument_identity_contract_ready": True,
            "pit_universe_contract_ready": True,
            "reference_data_contract_ready": True,
            "market_data_provenance_contract_ready": True,
            "db_schema_source_or_dry_run_only": True,
            "broker_dependency_required": False,
        },
        shadow_collector_fixture={
            "simulated_shadow_flow_ready": True,
            "after_cost_required": True,
            "point_in_time_required": True,
            "replayable_from_fixtures": True,
            "shadow_signal_emitted_to_broker": False,
            "scorecard_writer_started": False,
        },
        paper_lifecycle_fixture={
            "simulated_lifecycle_ready": True,
            "rust_authority_required": True,
            "python_broker_write_authority": False,
            "decision_lease_required": True,
            "guardian_required": True,
            "risk_config_hash_required": True,
            "idempotency_required": True,
            "audit_event_required": True,
            "real_broker_route_enabled": False,
            "bybit_path_reused": False,
        },
        evidence_ai_ml_fixture={
            "offline_evidence_clock_ready": True,
            "scorecard_derivation_ready": True,
            "proof_packet_inputs_replayable": True,
            "ai_ml_advisory_only": True,
            "ai_ml_execution_authority": False,
            "mutation_envelope_authorized": False,
            "paper_shadow_window_complete_claimed": False,
        },
        release_disable_fixture={
            "release_packet_ready_api_absent": True,
            "disable_cleanup_runbook_ready": True,
            "external_verification_checklist_required": True,
            "live_or_tiny_live_authorized": False,
            "live_secret_slot_allowed": False,
            "live_order_path_allowed": False,
        },
        external_verification_readiness_fixture={
            "readiness_packet_id": "ibkr_external_verification_readiness_v1",
            "status": "external_verification_pending",
            "operator_checklist": [
                "confirm_paper_or_readonly_account_only",
                "confirm_no_live_account_fingerprint",
                "confirm_operator_contact_window",
                "confirm_redacted_artifact_storage_path",
                "confirm_pm_operator_reviewers_present",
            ],
            "gateway_topology_checklist": [
                "ib_gateway_or_tws_running_on_trade_core",
                "loopback_host_only_127_0_0_1",
                "paper_gateway_port_4002_only",
                "live_ports_4001_and_7496_denied",
                "deterministic_client_id_recorded",
                "api_server_version_recorded",
            ],
            "secret_fingerprint_checklist": [
                "readonly_or_paper_slot_fingerprint_recorded",
                "live_slot_absent_or_empty",
                "owner_only_permissions",
                "env_var_fallback_denied",
                "secret_content_not_serialized",
                "account_id_not_serialized",
            ],
            "phase2_real_contact_runbook": [
                "seal_no_contact_candidate_packet",
                "collect_secret_slot_fingerprint_evidence",
                "collect_loopback_topology_evidence",
                "collect_session_attestation_evidence",
                "run_redaction_and_rate_limit_policy_checks",
                "seal_immutable_phase2_pass_artifact_before_first_contact",
                "perform_first_readonly_healthcheck_only_after_pass",
            ],
            "first_real_contact_allowed_before_pass": False,
            "credential_required_for_next_external_step": True,
            "gateway_session_required_for_next_external_step": True,
            "operator_approval_required_for_next_external_step": True,
            "live_or_tiny_live_authorized": False,
            "runtime_mcp_required": False,
            "python_broker_write_authority": False,
        },
    )


def api_absent_engineering_fixture() -> dict[str, object]:
    """Return the packet as a plain dictionary for tests and display surfaces."""

    return build_api_absent_engineering_packet().to_dict()
