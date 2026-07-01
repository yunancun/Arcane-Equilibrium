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
    use StockEtfStrategyHypothesisBlocker as Blocker;

    let hypothesis = StockEtfStrategyHypothesisV1::default();
    let verdict = hypothesis.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::WrongAssetLane,
            Blocker::WrongBroker,
            Blocker::HypothesisIdInvalid,
            Blocker::HypothesisVersionInvalid,
            Blocker::StrategyFamilyDenied,
            Blocker::TimeframeDenied,
            Blocker::InstrumentScopeDenied,
            Blocker::UniverseHashInvalid,
            Blocker::PitUniverseContractHashInvalid,
            Blocker::BenchmarkVersionHashInvalid,
            Blocker::CostModelVersionHashInvalid,
            Blocker::EntryRuleHashInvalid,
            Blocker::ExitRuleHashInvalid,
            Blocker::RiskRuleHashInvalid,
            Blocker::FeatureSetHashInvalid,
            Blocker::DataSourcePolicyHashInvalid,
            Blocker::StatisticalDesignHashInvalid,
            Blocker::HypothesisPreregistrationHashInvalid,
            Blocker::HoldingPeriodTooShort,
            Blocker::TurnoverLimitMissing,
            Blocker::MaxConstituentsMissing,
            Blocker::IndependentObservationTargetTooLow,
            Blocker::LookaheadControlsMissing,
            Blocker::SurvivorshipControlsMissing,
            Blocker::MultipleTestingControlMissing,
            Blocker::BenchmarkMetricMissing,
            Blocker::CostAfterMetricMissing,
            Blocker::ForbiddenInstrumentPolicyMissing,
            Blocker::PaperShadowOnlyMissing,
            Blocker::BybitLiveExecutionNotProtected,
            Blocker::IbkrLiveNotDenied,
        ]
    );
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
    assert_eq!(hypothesis.source_version, 1);
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
fn strategy_hypothesis_requires_exact_contract_id_and_source_version() {
    let hypothesis = StockEtfStrategyHypothesisV1 {
        contract_id: "stock_etf_strategy_hypothesis_contract_v1_fixture".to_string(),
        source_version: 2,
        ..StockEtfStrategyHypothesisV1::accepted_fixture()
    };
    let blockers = hypothesis.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            StockEtfStrategyHypothesisBlocker::ContractIdMismatch,
            StockEtfStrategyHypothesisBlocker::SourceVersionMismatch,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfStrategyHypothesisBlocker::ContractIdMismatch,
            StockEtfStrategyHypothesisBlocker::WrongAssetLane,
            StockEtfStrategyHypothesisBlocker::WrongBroker,
            StockEtfStrategyHypothesisBlocker::HypothesisIdInvalid,
            StockEtfStrategyHypothesisBlocker::HypothesisVersionInvalid,
            StockEtfStrategyHypothesisBlocker::StrategyFamilyDenied,
            StockEtfStrategyHypothesisBlocker::TimeframeDenied,
            StockEtfStrategyHypothesisBlocker::InstrumentScopeDenied,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfStrategyHypothesisBlocker::UniverseHashInvalid,
            StockEtfStrategyHypothesisBlocker::PitUniverseContractHashInvalid,
            StockEtfStrategyHypothesisBlocker::BenchmarkVersionHashInvalid,
            StockEtfStrategyHypothesisBlocker::CostModelVersionHashInvalid,
            StockEtfStrategyHypothesisBlocker::EntryRuleHashInvalid,
            StockEtfStrategyHypothesisBlocker::ExitRuleHashInvalid,
            StockEtfStrategyHypothesisBlocker::RiskRuleHashInvalid,
            StockEtfStrategyHypothesisBlocker::FeatureSetHashInvalid,
            StockEtfStrategyHypothesisBlocker::DataSourcePolicyHashInvalid,
            StockEtfStrategyHypothesisBlocker::StatisticalDesignHashInvalid,
            StockEtfStrategyHypothesisBlocker::HypothesisPreregistrationHashInvalid,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfStrategyHypothesisBlocker::HoldingPeriodTooShort,
            StockEtfStrategyHypothesisBlocker::TurnoverLimitTooHigh,
            StockEtfStrategyHypothesisBlocker::MaxConstituentsMissing,
            StockEtfStrategyHypothesisBlocker::IndependentObservationTargetTooLow,
            StockEtfStrategyHypothesisBlocker::LookaheadControlsMissing,
            StockEtfStrategyHypothesisBlocker::SurvivorshipControlsMissing,
            StockEtfStrategyHypothesisBlocker::MultipleTestingControlMissing,
            StockEtfStrategyHypothesisBlocker::BenchmarkMetricMissing,
            StockEtfStrategyHypothesisBlocker::CostAfterMetricMissing,
            StockEtfStrategyHypothesisBlocker::ForbiddenInstrumentPolicyMissing,
            StockEtfStrategyHypothesisBlocker::PaperShadowOnlyMissing,
            StockEtfStrategyHypothesisBlocker::PrematureProfitabilityClaim,
            StockEtfStrategyHypothesisBlocker::LiveOrTinyLiveAuthorityClaimed,
            StockEtfStrategyHypothesisBlocker::BybitLiveExecutionNotProtected,
            StockEtfStrategyHypothesisBlocker::IbkrLiveNotDenied,
            StockEtfStrategyHypothesisBlocker::IbkrContactPerformed,
            StockEtfStrategyHypothesisBlocker::SecretContentSerialized,
        ]
    );
}

#[test]
fn strategy_hypothesis_rejects_authority_profitability_and_secret_cross_wire_independently() {
    for (hypothesis, expected_blocker) in [
        (
            StockEtfStrategyHypothesisV1 {
                paper_shadow_only: false,
                ..StockEtfStrategyHypothesisV1::accepted_fixture()
            },
            StockEtfStrategyHypothesisBlocker::PaperShadowOnlyMissing,
        ),
        (
            StockEtfStrategyHypothesisV1 {
                profitability_claimed: true,
                ..StockEtfStrategyHypothesisV1::accepted_fixture()
            },
            StockEtfStrategyHypothesisBlocker::PrematureProfitabilityClaim,
        ),
        (
            StockEtfStrategyHypothesisV1 {
                live_or_tiny_live_authority_claimed: true,
                ..StockEtfStrategyHypothesisV1::accepted_fixture()
            },
            StockEtfStrategyHypothesisBlocker::LiveOrTinyLiveAuthorityClaimed,
        ),
        (
            StockEtfStrategyHypothesisV1 {
                bybit_live_execution_unchanged: false,
                ..StockEtfStrategyHypothesisV1::accepted_fixture()
            },
            StockEtfStrategyHypothesisBlocker::BybitLiveExecutionNotProtected,
        ),
        (
            StockEtfStrategyHypothesisV1 {
                ibkr_live_denied: false,
                ..StockEtfStrategyHypothesisV1::accepted_fixture()
            },
            StockEtfStrategyHypothesisBlocker::IbkrLiveNotDenied,
        ),
        (
            StockEtfStrategyHypothesisV1 {
                ibkr_contact_performed: true,
                ..StockEtfStrategyHypothesisV1::accepted_fixture()
            },
            StockEtfStrategyHypothesisBlocker::IbkrContactPerformed,
        ),
        (
            StockEtfStrategyHypothesisV1 {
                secret_content_serialized: true,
                ..StockEtfStrategyHypothesisV1::accepted_fixture()
            },
            StockEtfStrategyHypothesisBlocker::SecretContentSerialized,
        ),
    ] {
        assert_eq!(hypothesis.validate().blockers, vec![expected_blocker]);
    }
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

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
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
