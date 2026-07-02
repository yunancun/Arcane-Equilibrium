//! Exact gate matrix coverage for ADR-0048 Stock/ETF broker capabilities.
//!
//! This is test-only. It does not contact IBKR, inspect secrets, create
//! connectors, submit paper orders, import fills, or mutate Bybit behavior.

use openclaw_types::{
    AuthorityScope, BrokerOperation, StockEtfBrokerCapabilityEntryV1,
    StockEtfBrokerCapabilityRegistryV1, StockEtfDenialReason,
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
    IBKR_PAPER_ATTESTATION_CONTRACT_ID, IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID, STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID, STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID, STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID, STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID,
    STOCK_ETF_RISK_POLICY_CONTRACT_ID, STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID,
    STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID, STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
    STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
};

#[test]
fn accepted_broker_capability_operation_gate_matrix_is_complete_and_ordered() {
    let registry = StockEtfBrokerCapabilityRegistryV1::accepted_fixture();

    assert!(registry.validate().accepted);
    assert_eq!(registry.operations.len(), 15);
    for entry in &registry.operations {
        assert_operation_shape(entry);
    }
}

#[test]
fn broker_capability_gate_assertions_stay_exact() {
    let legacy_source = include_str!("stock_etf_broker_capability_registry_acceptance.rs");
    let matrix_source =
        include_str!("stock_etf_broker_capability_registry_gate_matrix_acceptance.rs");
    let matrix_guard_prefix = matrix_source
        .split("fn broker_capability_gate_assertions_stay_exact")
        .next()
        .expect("matrix source guard anchor exists");

    for (name, source) in [
        ("legacy acceptance file", legacy_source),
        ("matrix guard prefix", matrix_guard_prefix),
    ] {
        assert!(
            !source.contains(".required_gates.contains("),
            "loose broker capability gate assertion returned in {name}"
        );
    }
}

fn assert_operation_shape(entry: &StockEtfBrokerCapabilityEntryV1) {
    match entry.operation {
        BrokerOperation::HealthRead => assert_entry(
            entry,
            AuthorityScope::ReadOnly,
            &[
                IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
                STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
            ],
            None,
            false,
        ),
        BrokerOperation::AccountSnapshotRead => assert_entry(
            entry,
            AuthorityScope::ReadOnly,
            &[
                IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
                STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
                IBKR_SESSION_ATTESTATION_CONTRACT_ID,
            ],
            None,
            false,
        ),
        BrokerOperation::MarketDataRead => assert_entry(
            entry,
            AuthorityScope::ReadOnly,
            &[
                IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
                STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
                STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
            ],
            None,
            false,
        ),
        BrokerOperation::ContractDetailsRead => assert_entry(
            entry,
            AuthorityScope::ReadOnly,
            &[
                IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
                STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
                STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID,
            ],
            None,
            false,
        ),
        BrokerOperation::PaperOrderSubmit
        | BrokerOperation::PaperOrderCancel
        | BrokerOperation::PaperOrderReplace => assert_entry(
            entry,
            AuthorityScope::PaperRehearsal,
            &[
                IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
                IBKR_PAPER_ATTESTATION_CONTRACT_ID,
                STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
                STOCK_ETF_SCOPED_AUTHORIZATION_CONTRACT_ID,
                STOCK_ETF_RISK_POLICY_CONTRACT_ID,
                "decision_lease_valid",
                "guardian_allows",
                IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
            ],
            None,
            true,
        ),
        BrokerOperation::PaperOrderFillImport => assert_entry(
            entry,
            AuthorityScope::ReadOnly,
            &[
                IBKR_SESSION_ATTESTATION_CONTRACT_ID,
                IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
            ],
            None,
            false,
        ),
        BrokerOperation::ShadowSignalEmit => assert_entry(
            entry,
            AuthorityScope::ShadowOnly,
            &[
                STOCK_ETF_RISK_POLICY_CONTRACT_ID,
                STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
                STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
                STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
                "frozen_strategy_hypothesis_hash",
                "frozen_universe_hash",
            ],
            None,
            false,
        ),
        BrokerOperation::ShadowFillReconstruct => assert_entry(
            entry,
            AuthorityScope::ShadowOnly,
            &[
                STOCK_ETF_RISK_POLICY_CONTRACT_ID,
                STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID,
                STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
                STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
            ],
            None,
            false,
        ),
        BrokerOperation::ScorecardDerive => assert_entry(
            entry,
            AuthorityScope::ReadOnly,
            &[
                STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
                BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID,
                STOCK_ETF_RISK_POLICY_CONTRACT_ID,
                STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID,
                STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
                STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
                STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID,
                STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
                STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
                STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
                "paper_shadow_fill_separation",
            ],
            None,
            false,
        ),
        BrokerOperation::LiveOrderSubmit => assert_entry(
            entry,
            AuthorityScope::Denied,
            &[],
            Some(StockEtfDenialReason::IbkrLiveNotAuthorized),
            false,
        ),
        BrokerOperation::MarginOrShort => assert_entry(
            entry,
            AuthorityScope::Denied,
            &[],
            Some(StockEtfDenialReason::StockEtfCashOnly),
            false,
        ),
        BrokerOperation::OptionsOrCfd => assert_entry(
            entry,
            AuthorityScope::Denied,
            &[],
            Some(StockEtfDenialReason::InstrumentKindDenied),
            false,
        ),
        BrokerOperation::TransferOrAccountWrite => assert_entry(
            entry,
            AuthorityScope::Denied,
            &[],
            Some(StockEtfDenialReason::AccountWriteDenied),
            false,
        ),
    }
}

fn assert_entry(
    entry: &StockEtfBrokerCapabilityEntryV1,
    authority_scope: AuthorityScope,
    required_gates: &[&str],
    typed_denial_reason: Option<StockEtfDenialReason>,
    rust_owned: bool,
) {
    assert_eq!(
        entry.authority_scope, authority_scope,
        "{:?}",
        entry.operation
    );
    assert_eq!(
        entry.required_gates,
        string_vec(required_gates),
        "{:?}",
        entry.operation
    );
    assert_eq!(
        entry.typed_denial_reason, typed_denial_reason,
        "{:?}",
        entry.operation
    );
    assert_eq!(entry.rust_owned, rust_owned, "{:?}", entry.operation);
    assert!(entry.audit_event_required, "{:?}", entry.operation);
    assert!(entry.source_artifact_hash_required, "{:?}", entry.operation);
}

fn string_vec(values: &[&str]) -> Vec<String> {
    values.iter().map(|value| value.to_string()).collect()
}
