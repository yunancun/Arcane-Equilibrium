//! ADR-0048 Stock/ETF strategy hypothesis acceptance tests.
//!
//! These tests validate source-only pre-registration contracts. They must not
//! contact IBKR, inspect secrets, create connectors, collect market data, route
//! orders, write scorecards, or mutate Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, Broker, StockEtfStrategyFamily, StockEtfStrategyHypothesisBlocker,
    StockEtfStrategyHypothesisV1, StockEtfStrategyInstrumentScope, StockEtfStrategyTimeframe,
    STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
};

#[test]
fn default_strategy_hypothesis_blocks_before_evidence_clock_can_use_hash() {
    let hypothesis = StockEtfStrategyHypothesisV1::default();
    let verdict = hypothesis.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict.blockers,
        StockEtfStrategyHypothesisBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfStrategyHypothesisBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfStrategyHypothesisBlocker::WrongBroker
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfStrategyHypothesisBlocker::StrategyFamilyDenied
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfStrategyHypothesisBlocker::HypothesisPreregistrationHashInvalid
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfStrategyHypothesisBlocker::PaperShadowOnlyMissing
    ));
}

#[test]
fn accepted_fixture_is_preregistered_paper_shadow_hypothesis_without_authority() {
    let hypothesis = StockEtfStrategyHypothesisV1::accepted_fixture();
    let verdict = hypothesis.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        hypothesis.contract_id,
        STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID
    );
    assert_eq!(hypothesis.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(hypothesis.broker, Broker::Ibkr);
    assert!(hypothesis.paper_shadow_only);
    assert!(!hypothesis.profitability_claimed);
    assert!(!hypothesis.live_or_tiny_live_authority_claimed);
    assert!(hypothesis.bybit_live_execution_unchanged);
    assert!(hypothesis.ibkr_live_denied);
    assert!(!hypothesis.ibkr_contact_performed);
    assert!(!hypothesis.secret_content_serialized);
}

#[test]
fn strategy_hypothesis_rejects_identity_family_timeframe_and_scope_regressions() {
    let hypothesis = StockEtfStrategyHypothesisV1 {
        contract_id: "wrong".to_string(),
        asset_lane: AssetLane::CryptoPerp,
        broker: Broker::Bybit,
        hypothesis_id: " bad id ".to_string(),
        hypothesis_version: "".to_string(),
        strategy_family: StockEtfStrategyFamily::HighFrequencyReservedDenied,
        primary_timeframe: StockEtfStrategyTimeframe::IntradayReservedDenied,
        instrument_scope: StockEtfStrategyInstrumentScope::UnknownDenied,
        ..StockEtfStrategyHypothesisV1::accepted_fixture()
    };
    let blockers = hypothesis.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::ContractIdMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::WrongAssetLane
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::WrongBroker
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::HypothesisIdInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::HypothesisVersionInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::StrategyFamilyDenied
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::TimeframeDenied
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::InstrumentScopeDenied
    ));
}

#[test]
fn strategy_hypothesis_rejects_missing_hashes_and_design_inputs() {
    let hypothesis = StockEtfStrategyHypothesisV1 {
        universe_hash: String::new(),
        pit_universe_contract_hash: String::new(),
        benchmark_version_hash: String::new(),
        cost_model_version_hash: String::new(),
        entry_rule_hash: String::new(),
        exit_rule_hash: String::new(),
        risk_rule_hash: String::new(),
        feature_set_hash: String::new(),
        data_source_policy_hash: String::new(),
        statistical_design_hash: String::new(),
        hypothesis_preregistration_hash: String::new(),
        ..StockEtfStrategyHypothesisV1::accepted_fixture()
    };
    let blockers = hypothesis.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::UniverseHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::PitUniverseContractHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::BenchmarkVersionHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::CostModelVersionHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::EntryRuleHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::StatisticalDesignHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::HypothesisPreregistrationHashInvalid
    ));
}

#[test]
fn strategy_hypothesis_rejects_bad_limits_controls_and_authority_claims() {
    let hypothesis = StockEtfStrategyHypothesisV1 {
        expected_holding_period_days_min: 0,
        max_turnover_per_month_bps: 20_001,
        max_constituents_used: 0,
        independent_observation_target: 10,
        lookahead_bias_controls_present: false,
        survivorship_bias_controls_present: false,
        multiple_testing_control_present: false,
        benchmark_relative_metric_defined: false,
        cost_after_metric_defined: false,
        no_options_cfd_margin_short: false,
        paper_shadow_only: false,
        profitability_claimed: true,
        live_or_tiny_live_authority_claimed: true,
        bybit_live_execution_unchanged: false,
        ibkr_live_denied: false,
        ibkr_contact_performed: true,
        secret_content_serialized: true,
        ..StockEtfStrategyHypothesisV1::accepted_fixture()
    };
    let blockers = hypothesis.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::HoldingPeriodTooShort
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::TurnoverLimitTooHigh
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::MaxConstituentsMissing
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::IndependentObservationTargetTooLow
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::LookaheadControlsMissing
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::MultipleTestingControlMissing
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::PaperShadowOnlyMissing
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::PrematureProfitabilityClaim
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::LiveOrTinyLiveAuthorityClaimed
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &blockers,
        StockEtfStrategyHypothesisBlocker::SecretContentSerialized
    ));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_strategy_hypothesis.template.toml"),
    )
    .expect("read strategy hypothesis template");
    let parsed: StockEtfStrategyHypothesisV1 =
        toml::from_str(&raw).expect("strategy hypothesis template parses");

    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert!(!parsed.validate().accepted);
    assert!(!parsed.paper_shadow_only);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.secret_content_serialized);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(
    blockers: &[StockEtfStrategyHypothesisBlocker],
    blocker: StockEtfStrategyHypothesisBlocker,
) -> bool {
    blockers.contains(&blocker)
}
