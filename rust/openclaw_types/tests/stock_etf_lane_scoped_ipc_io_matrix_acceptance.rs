//! Exact gate/request-field matrix coverage for ADR-0048 Stock/ETF IPC.
//!
//! This is test-only. It does not start IPC, contact IBKR, inspect secrets,
//! create connectors, submit paper orders, or mutate Bybit behavior.

use openclaw_types::{
    StockEtfLaneScopedIpcCommandV1, StockEtfLaneScopedIpcContractV1, StockEtfLaneScopedIpcMethod,
    BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID, IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID,
    IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID, IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
    IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID, IBKR_RATE_LIMIT_POLICY_CONTRACT_ID,
    IBKR_REDACTION_POLICY_CONTRACT_ID, IBKR_SECRET_SLOT_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID, NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
    STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID, STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID, STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID, STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID, STOCK_ETF_RISK_POLICY_CONTRACT_ID,
    STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID, STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
};

#[test]
fn accepted_lane_scoped_ipc_command_io_matrix_is_complete_and_ordered() {
    let contract = StockEtfLaneScopedIpcContractV1::accepted_fixture();

    assert_eq!(contract.commands.len(), 21);
    for command in &contract.commands {
        assert_command_io(command);
    }
}

#[test]
fn lane_scoped_ipc_gate_and_field_assertions_stay_exact() {
    let legacy_source = include_str!("stock_etf_lane_scoped_ipc_acceptance.rs");
    let matrix_source = include_str!("stock_etf_lane_scoped_ipc_io_matrix_acceptance.rs");
    let matrix_guard_prefix = matrix_source
        .split("fn lane_scoped_ipc_gate_and_field_assertions_stay_exact")
        .next()
        .expect("matrix source guard anchor exists");
    let forbidden_patterns = [".required_gates.contains(", "assert_fields("];

    for pattern in forbidden_patterns {
        assert!(
            !legacy_source.contains(pattern),
            "loose lane-scoped IPC gate/field assertion returned in legacy acceptance file: {pattern}"
        );
        assert!(
            !matrix_guard_prefix.contains(pattern),
            "loose lane-scoped IPC gate/field assertion returned before matrix guard: {pattern}"
        );
    }
    for (line_no, line) in legacy_source.lines().enumerate() {
        if line.contains("required_request_fields.contains")
            && !line
                .trim_start()
                .starts_with("!command.required_request_fields.contains")
        {
            panic!(
                "loose positive request-field assertion returned in legacy acceptance file at line {}: {}",
                line_no + 1,
                line
            );
        }
    }
}

fn assert_command_io(command: &StockEtfLaneScopedIpcCommandV1) {
    match command.method {
        StockEtfLaneScopedIpcMethod::GetLaneStatus
        | StockEtfLaneScopedIpcMethod::GetPhase0Status
        | StockEtfLaneScopedIpcMethod::GetReadiness
        | StockEtfLaneScopedIpcMethod::GetDataFoundationStatus
        | StockEtfLaneScopedIpcMethod::GetPolicyStatus
        | StockEtfLaneScopedIpcMethod::GetAuthorizationStatus
        | StockEtfLaneScopedIpcMethod::GetAccountStatus
        | StockEtfLaneScopedIpcMethod::GetPaperStatus
        | StockEtfLaneScopedIpcMethod::GetReconciliationStatus
        | StockEtfLaneScopedIpcMethod::GetScorecardStatus
        | StockEtfLaneScopedIpcMethod::GetLaunchStatus
        | StockEtfLaneScopedIpcMethod::GetReleasePacketStatus
        | StockEtfLaneScopedIpcMethod::GetDisableCleanupStatus
        | StockEtfLaneScopedIpcMethod::GetConnectionHealth => {
            assert_gates_eq(command, &[]);
            assert_fields_eq(command, &["asset_lane", "broker", "request_id"]);
        }
        StockEtfLaneScopedIpcMethod::PreviewPaperOrder => {
            assert_gates_eq(
                command,
                &[
                    STOCK_ETF_RISK_POLICY_CONTRACT_ID,
                    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID,
                    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
                    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
                    STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID,
                ],
            );
            assert_fields_eq(
                command,
                &[
                    "asset_lane",
                    "broker",
                    "environment",
                    "operation",
                    "request_id",
                    "account_fingerprint_hash",
                    "instrument_identity_hash",
                    "symbol",
                    "instrument_kind",
                    "side",
                    "order_type",
                    "quantity",
                    "limit_price_policy",
                    "time_in_force",
                    "risk_config_hash",
                    "cost_model_version_hash",
                    "pit_universe_contract_hash",
                    "source_artifact_hash",
                ],
            );
        }
        StockEtfLaneScopedIpcMethod::SubmitPaperOrder => {
            assert_paper_effect_gates_eq(command);
            assert_fields_eq(
                command,
                &[
                    "asset_lane",
                    "broker",
                    "environment",
                    "operation",
                    "request_id",
                    "session_attestation_hash",
                    "scoped_authorization_hash",
                    "decision_lease_id",
                    "guardian_state_hash",
                    "account_fingerprint_hash",
                    "risk_config_hash",
                    "instrument_identity_hash",
                    "symbol",
                    "instrument_kind",
                    "side",
                    "order_type",
                    "quantity",
                    "limit_price_policy",
                    "time_in_force",
                    "order_local_id",
                    "idempotency_key",
                    "lifecycle_contract_hash",
                    "broker_capability_registry_hash",
                    "audit_event_id",
                ],
            );
        }
        StockEtfLaneScopedIpcMethod::CancelPaperOrder => {
            assert_paper_effect_gates_eq(command);
            assert_fields_eq(
                command,
                &[
                    "asset_lane",
                    "broker",
                    "environment",
                    "operation",
                    "request_id",
                    "session_attestation_hash",
                    "scoped_authorization_hash",
                    "decision_lease_id",
                    "guardian_state_hash",
                    "account_fingerprint_hash",
                    "order_local_id",
                    "broker_order_id",
                    "cancel_reason",
                    "idempotency_key",
                    "lifecycle_contract_hash",
                    "broker_capability_registry_hash",
                    "audit_event_id",
                ],
            );
        }
        StockEtfLaneScopedIpcMethod::ReplacePaperOrder => {
            assert_paper_effect_gates_eq(command);
            assert_fields_eq(
                command,
                &[
                    "asset_lane",
                    "broker",
                    "environment",
                    "operation",
                    "request_id",
                    "session_attestation_hash",
                    "scoped_authorization_hash",
                    "decision_lease_id",
                    "guardian_state_hash",
                    "account_fingerprint_hash",
                    "order_local_id",
                    "broker_order_id",
                    "instrument_identity_hash",
                    "symbol",
                    "side",
                    "replacement_idempotency_key",
                    "replacement_quantity",
                    "replacement_limit_price_policy",
                    "replacement_time_in_force",
                    "replace_reason",
                    "lifecycle_contract_hash",
                    "broker_capability_registry_hash",
                    "audit_event_id",
                ],
            );
        }
        StockEtfLaneScopedIpcMethod::ImportPaperFills => {
            assert_gates_eq(
                command,
                &[
                    IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                    IBKR_SESSION_ATTESTATION_CONTRACT_ID,
                    IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
                    BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
                    IBKR_REDACTION_POLICY_CONTRACT_ID,
                ],
            );
            assert_fields_eq(
                command,
                &[
                    "asset_lane",
                    "broker",
                    "environment",
                    "operation",
                    "request_id",
                    "session_attestation_hash",
                    "lifecycle_contract_hash",
                    "redaction_policy_hash",
                    "source_artifact_hash",
                    "reconciliation_run_id",
                ],
            );
        }
        StockEtfLaneScopedIpcMethod::EvaluateShadowSignal => {
            assert_gates_eq(
                command,
                &[
                    STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
                    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
                    STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
                    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
                    STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID,
                ],
            );
            assert_fields_eq(
                command,
                &[
                    "asset_lane",
                    "broker",
                    "environment",
                    "operation",
                    "request_id",
                    "evidence_clock_hash",
                    "pit_universe_contract_hash",
                    "strategy_hypothesis_hash",
                    "cost_model_version_hash",
                    "source_artifact_hash",
                ],
            );
        }
        StockEtfLaneScopedIpcMethod::PreviewReadonlyProbe => {
            assert_gates_eq(
                command,
                &[
                    IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                    NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
                    IBKR_SECRET_SLOT_CONTRACT_ID,
                    IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID,
                    IBKR_SESSION_ATTESTATION_CONTRACT_ID,
                    IBKR_REDACTION_POLICY_CONTRACT_ID,
                    IBKR_RATE_LIMIT_POLICY_CONTRACT_ID,
                    IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID,
                ],
            );
            assert_fields_eq(
                command,
                &[
                    "asset_lane",
                    "broker",
                    "environment",
                    "operation",
                    "probe_kind",
                    "api_action",
                    "request_id",
                    "probe_id",
                    "phase2_gate_artifact_hash",
                    "api_allowlist_hash",
                    "secret_slot_contract_hash",
                    "api_session_topology_hash",
                    "session_attestation_hash",
                    "redaction_policy_hash",
                    "rate_limit_policy_hash",
                    "audit_event_policy_hash",
                    "source_artifact_hash",
                    "raw_artifact_hash",
                    "redacted_summary_hash",
                ],
            );
        }
        StockEtfLaneScopedIpcMethod::BybitSubmitPaperOrderDenied
        | StockEtfLaneScopedIpcMethod::UnknownDenied => {
            assert_gates_eq(command, &[]);
            assert_fields_eq(command, &[]);
        }
    }
}

fn assert_paper_effect_gates_eq(command: &StockEtfLaneScopedIpcCommandV1) {
    assert_gates_eq(
        command,
        &[
            IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
            IBKR_SESSION_ATTESTATION_CONTRACT_ID,
            STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID,
            "decision_lease_valid",
            "guardian_allows",
            STOCK_ETF_RISK_POLICY_CONTRACT_ID,
            "risk_config_hash",
            STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID,
            "idempotency_key",
            STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
            IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
            STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID,
            STOCK_ETF_ASSET_LANE_EVENTS_CONTRACT_ID,
        ],
    );
}

fn assert_gates_eq(command: &StockEtfLaneScopedIpcCommandV1, gates: &[&str]) {
    assert_eq!(
        command.required_gates,
        string_vec(gates),
        "{:?} required gates drifted",
        command.method
    );
}

fn assert_fields_eq(command: &StockEtfLaneScopedIpcCommandV1, fields: &[&str]) {
    assert_eq!(
        command.required_request_fields,
        string_vec(fields),
        "{:?} required request fields drifted",
        command.method
    );
}

fn string_vec(items: &[&str]) -> Vec<String> {
    items.iter().map(|item| item.to_string()).collect()
}
