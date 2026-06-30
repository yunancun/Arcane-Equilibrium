//! ADR-0048 Stock/ETF risk-policy acceptance tests.
//!
//! These tests validate the source-only risk policy shape. They do not contact
//! IBKR, inspect secrets, create connectors, route orders, start collectors,
//! write scorecards, or mutate existing Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, Broker, BrokerEnvironment, InstrumentKind, StockEtfRiskPolicyBlocker,
    StockEtfRiskPolicySourceConfigV1, StockEtfRiskPolicyV1, STOCK_ETF_RISK_POLICY_CONTRACT_ID,
};

#[test]
fn default_risk_policy_blocks_runtime_authority() {
    let verdict = StockEtfRiskPolicyV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict.blockers,
        StockEtfRiskPolicyBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfRiskPolicyBlocker::VersionMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfRiskPolicyBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfRiskPolicyBlocker::WrongBroker
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfRiskPolicyBlocker::WrongEnvironment
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfRiskPolicyBlocker::RuntimeEnablementClaimed
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfRiskPolicyBlocker::OrderCapMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfRiskPolicyBlocker::MarginAllowed
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfRiskPolicyBlocker::AllowedInstrumentMissing
    ));
}

#[test]
fn accepted_fixture_pins_cash_only_shadow_risk_policy() {
    let policy = StockEtfRiskPolicyV1::accepted_fixture();
    let verdict = policy.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(policy.contract_id, STOCK_ETF_RISK_POLICY_CONTRACT_ID);
    assert_eq!(policy.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(policy.broker, Broker::Ibkr);
    assert_eq!(policy.environment, BrokerEnvironment::Paper);
    assert!(!policy.enabled);
    assert!(policy.shadow_only);
    assert_eq!(policy.max_order_notional_usd, 1_000.0);
    assert!(policy.max_order_notional_usd <= policy.max_position_notional_usd);
    assert!(policy.max_position_notional_usd <= policy.max_daily_notional_usd);
    assert!(!policy.allow_margin);
    assert!(!policy.allow_short);
    assert!(!policy.allow_options);
    assert!(!policy.allow_cfd);
    assert!(!policy.allow_transfer);
    assert!(!policy.allow_live);
    assert!(policy
        .instrument_kinds_allowed
        .contains(&InstrumentKind::Stock));
    assert!(policy
        .instrument_kinds_allowed
        .contains(&InstrumentKind::Etf));
    assert!(policy
        .instrument_kinds_allowed
        .contains(&InstrumentKind::Cash));
    assert!(policy
        .instrument_kinds_denied
        .contains(&InstrumentKind::CryptoPerp));
    assert!(policy
        .instrument_kinds_denied
        .contains(&InstrumentKind::CfdReserved));
    assert!(policy.bybit_live_execution_unchanged);
    assert!(!policy.ibkr_contact_performed);
    assert!(!policy.connector_runtime_started);
    assert!(!policy.secret_content_serialized);
}

#[test]
fn repository_dormant_risk_config_parses_and_validates_as_source_policy() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/risk_control_rules/risk_config_stock_etf_paper.toml"),
    )
    .expect("read stock/ETF risk config");
    let parsed: StockEtfRiskPolicySourceConfigV1 =
        toml::from_str(&raw).expect("stock/ETF risk config parses");
    let policy = StockEtfRiskPolicyV1::from_source_config(&parsed);
    let verdict = policy.validate();

    assert!(
        verdict.accepted,
        "repository risk config blockers: {:?}",
        verdict.blockers
    );
    assert!(!policy.enabled);
    assert!(policy.shadow_only);
    assert_eq!(policy.max_open_orders, 5);
    assert_eq!(policy.max_open_positions, 10);
}

#[test]
fn risk_policy_rejects_runtime_enablement_caps_and_cash_only_regressions() {
    let mut policy = StockEtfRiskPolicyV1::accepted_fixture();
    policy.environment = BrokerEnvironment::LiveReservedDenied;
    policy.enabled = true;
    policy.shadow_only = false;
    policy.max_order_notional_usd = f64::NAN;
    policy.max_position_notional_usd = 5_000.0;
    policy.max_daily_notional_usd = 4_000.0;
    policy.max_open_orders = 21;
    policy.max_open_positions = 101;
    policy.allow_margin = true;
    policy.allow_short = true;
    policy.allow_options = true;
    policy.allow_cfd = true;
    policy.allow_transfer = true;
    policy.allow_live = true;

    let blockers = policy.validate().blockers;

    assert!(has(&blockers, StockEtfRiskPolicyBlocker::WrongEnvironment));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::RuntimeEnablementClaimed
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::ShadowOnlyPostureMissing
    ));
    assert!(has(&blockers, StockEtfRiskPolicyBlocker::OrderCapMissing));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::OpenOrderLimitTooHigh
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::OpenPositionLimitTooHigh
    ));
    assert!(has(&blockers, StockEtfRiskPolicyBlocker::MarginAllowed));
    assert!(has(&blockers, StockEtfRiskPolicyBlocker::ShortAllowed));
    assert!(has(&blockers, StockEtfRiskPolicyBlocker::OptionsAllowed));
    assert!(has(&blockers, StockEtfRiskPolicyBlocker::CfdAllowed));
    assert!(has(&blockers, StockEtfRiskPolicyBlocker::TransferAllowed));
    assert!(has(&blockers, StockEtfRiskPolicyBlocker::LiveAllowed));
}

#[test]
fn risk_policy_rejects_universe_cost_and_order_gate_regressions() {
    let mut policy = StockEtfRiskPolicyV1::accepted_fixture();
    policy.instrument_kinds_allowed = vec![InstrumentKind::Stock, InstrumentKind::CryptoPerp];
    policy.instrument_kinds_denied = vec![InstrumentKind::CfdReserved];
    policy.requires_frozen_universe_hash = false;
    policy.requires_instrument_identity_hash = false;
    policy.requires_market_session = false;
    policy.cost_model_required_before_shadow_fill = false;
    policy.cost_model_required_before_scorecard = false;
    policy.commission_schedule_required = false;
    policy.spread_estimate_required = false;
    policy.slippage_estimate_required = false;
    policy.fx_drag_required = false;
    policy.conservative_fill_penalty_required = false;
    policy.rust_authority_required = false;
    policy.session_attestation_required = false;
    policy.decision_lease_required = false;
    policy.guardian_required = false;
    policy.idempotency_key_required = false;
    policy.broker_reconciliation_required = false;

    let blockers = policy.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::AllowedInstrumentMissing
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::ForbiddenInstrumentAllowed
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::DeniedInstrumentMissing
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::FrozenUniverseHashNotRequired
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::CostModelBeforeShadowFillMissing
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::CommissionScheduleMissing
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::RustAuthorityMissing
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::DecisionLeaseMissing
    ));
    assert!(has(&blockers, StockEtfRiskPolicyBlocker::GuardianMissing));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::BrokerReconciliationMissing
    ));
}

#[test]
fn risk_policy_rejects_contact_secret_connector_and_bybit_regressions() {
    let mut policy = StockEtfRiskPolicyV1::accepted_fixture();
    policy.bybit_live_execution_unchanged = false;
    policy.ibkr_contact_performed = true;
    policy.connector_runtime_started = true;
    policy.secret_content_serialized = true;

    let blockers = policy.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::BybitLiveExecutionNotProtected
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &blockers,
        StockEtfRiskPolicyBlocker::SecretContentSerialized
    ));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_risk_policy.template.toml"),
    )
    .expect("read risk-policy template");
    let parsed: StockEtfRiskPolicyV1 = toml::from_str(&raw).expect("risk-policy template parses");

    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert!(!parsed.validate().accepted);
    assert!(parsed.enabled);
    assert!(!parsed.bybit_live_execution_unchanged);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.secret_content_serialized);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(blockers: &[StockEtfRiskPolicyBlocker], blocker: StockEtfRiskPolicyBlocker) -> bool {
    blockers.contains(&blocker)
}
