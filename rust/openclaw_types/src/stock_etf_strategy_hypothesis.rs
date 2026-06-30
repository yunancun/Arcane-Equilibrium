//! ADR-0048 Stock/ETF strategy hypothesis contract.
//!
//! This source-only validator pins the pre-registered hypothesis evidence that
//! must exist before Phase 3 evidence-clock days or scorecards can treat a
//! strategy hypothesis hash as meaningful. It does not contact IBKR, inspect
//! secrets, create connectors, collect market data, route orders, write
//! scorecards, or change Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{AssetLane, Broker};

pub const STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID: &str =
    "stock_etf_strategy_hypothesis_contract_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfStrategyHypothesisV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub hypothesis_id: String,
    pub hypothesis_version: String,
    pub strategy_family: StockEtfStrategyFamily,
    pub primary_timeframe: StockEtfStrategyTimeframe,
    pub instrument_scope: StockEtfStrategyInstrumentScope,
    pub universe_hash: String,
    pub pit_universe_contract_hash: String,
    pub benchmark_version_hash: String,
    pub cost_model_version_hash: String,
    pub entry_rule_hash: String,
    pub exit_rule_hash: String,
    pub risk_rule_hash: String,
    pub feature_set_hash: String,
    pub data_source_policy_hash: String,
    pub statistical_design_hash: String,
    pub hypothesis_preregistration_hash: String,
    pub expected_holding_period_days_min: u16,
    pub max_turnover_per_month_bps: u32,
    pub max_constituents_used: u32,
    pub independent_observation_target: u32,
    pub lookahead_bias_controls_present: bool,
    pub survivorship_bias_controls_present: bool,
    pub multiple_testing_control_present: bool,
    pub benchmark_relative_metric_defined: bool,
    pub cost_after_metric_defined: bool,
    pub no_options_cfd_margin_short: bool,
    pub paper_shadow_only: bool,
    pub profitability_claimed: bool,
    pub live_or_tiny_live_authority_claimed: bool,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_live_denied: bool,
    pub ibkr_contact_performed: bool,
    pub secret_content_serialized: bool,
}

impl Default for StockEtfStrategyHypothesisV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            hypothesis_id: String::new(),
            hypothesis_version: String::new(),
            strategy_family: StockEtfStrategyFamily::UnknownDenied,
            primary_timeframe: StockEtfStrategyTimeframe::UnknownDenied,
            instrument_scope: StockEtfStrategyInstrumentScope::UnknownDenied,
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
            expected_holding_period_days_min: 0,
            max_turnover_per_month_bps: 0,
            max_constituents_used: 0,
            independent_observation_target: 0,
            lookahead_bias_controls_present: false,
            survivorship_bias_controls_present: false,
            multiple_testing_control_present: false,
            benchmark_relative_metric_defined: false,
            cost_after_metric_defined: false,
            no_options_cfd_margin_short: false,
            paper_shadow_only: false,
            profitability_claimed: false,
            live_or_tiny_live_authority_claimed: false,
            bybit_live_execution_unchanged: false,
            ibkr_live_denied: false,
            ibkr_contact_performed: false,
            secret_content_serialized: false,
        }
    }
}

impl StockEtfStrategyHypothesisV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            hypothesis_id: "stock_etf_daily_momentum_us_large_100_v1".to_string(),
            hypothesis_version: "v1_20260301".to_string(),
            strategy_family: StockEtfStrategyFamily::DailyMomentum,
            primary_timeframe: StockEtfStrategyTimeframe::Daily,
            instrument_scope: StockEtfStrategyInstrumentScope::StockAndEtf,
            universe_hash: hash('1'),
            pit_universe_contract_hash: hash('2'),
            benchmark_version_hash: hash('3'),
            cost_model_version_hash: hash('4'),
            entry_rule_hash: hash('5'),
            exit_rule_hash: hash('6'),
            risk_rule_hash: hash('7'),
            feature_set_hash: hash('8'),
            data_source_policy_hash: hash('9'),
            statistical_design_hash: hash('a'),
            hypothesis_preregistration_hash: hash('b'),
            expected_holding_period_days_min: 3,
            max_turnover_per_month_bps: 5_000,
            max_constituents_used: 100,
            independent_observation_target: 50,
            lookahead_bias_controls_present: true,
            survivorship_bias_controls_present: true,
            multiple_testing_control_present: true,
            benchmark_relative_metric_defined: true,
            cost_after_metric_defined: true,
            no_options_cfd_margin_short: true,
            paper_shadow_only: true,
            profitability_claimed: false,
            live_or_tiny_live_authority_claimed: false,
            bybit_live_execution_unchanged: true,
            ibkr_live_denied: true,
            ibkr_contact_performed: false,
            secret_content_serialized: false,
        }
    }

    pub fn validate(&self) -> StockEtfStrategyHypothesisVerdict<StockEtfStrategyHypothesisBlocker> {
        use StockEtfStrategyHypothesisBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if !valid_identifier(&self.hypothesis_id) {
            blockers.push(Blocker::HypothesisIdInvalid);
        }
        if !valid_identifier(&self.hypothesis_version) {
            blockers.push(Blocker::HypothesisVersionInvalid);
        }
        if !matches!(
            self.strategy_family,
            StockEtfStrategyFamily::DailyMomentum
                | StockEtfStrategyFamily::WeeklyMomentum
                | StockEtfStrategyFamily::SectorRotation
                | StockEtfStrategyFamily::EtfTrendRiskOff
        ) {
            blockers.push(Blocker::StrategyFamilyDenied);
        }
        if !matches!(
            self.primary_timeframe,
            StockEtfStrategyTimeframe::Daily | StockEtfStrategyTimeframe::Weekly
        ) {
            blockers.push(Blocker::TimeframeDenied);
        }
        if self.instrument_scope == StockEtfStrategyInstrumentScope::UnknownDenied {
            blockers.push(Blocker::InstrumentScopeDenied);
        }

        validate_hashes(self, &mut blockers);
        validate_limits_and_controls(self, &mut blockers);

        StockEtfStrategyHypothesisVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfStrategyFamily {
    DailyMomentum,
    WeeklyMomentum,
    SectorRotation,
    EtfTrendRiskOff,
    EventDrivenReservedDenied,
    HighFrequencyReservedDenied,
    UnknownDenied,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfStrategyTimeframe {
    Daily,
    Weekly,
    IntradayReservedDenied,
    UnknownDenied,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfStrategyInstrumentScope {
    StockOnly,
    EtfOnly,
    StockAndEtf,
    UnknownDenied,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfStrategyHypothesisVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfStrategyHypothesisVerdict<B> {
    pub fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfStrategyHypothesisBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    HypothesisIdInvalid,
    HypothesisVersionInvalid,
    StrategyFamilyDenied,
    TimeframeDenied,
    InstrumentScopeDenied,
    UniverseHashInvalid,
    PitUniverseContractHashInvalid,
    BenchmarkVersionHashInvalid,
    CostModelVersionHashInvalid,
    EntryRuleHashInvalid,
    ExitRuleHashInvalid,
    RiskRuleHashInvalid,
    FeatureSetHashInvalid,
    DataSourcePolicyHashInvalid,
    StatisticalDesignHashInvalid,
    HypothesisPreregistrationHashInvalid,
    HoldingPeriodTooShort,
    TurnoverLimitMissing,
    TurnoverLimitTooHigh,
    MaxConstituentsMissing,
    MaxConstituentsTooBroad,
    IndependentObservationTargetTooLow,
    LookaheadControlsMissing,
    SurvivorshipControlsMissing,
    MultipleTestingControlMissing,
    BenchmarkMetricMissing,
    CostAfterMetricMissing,
    ForbiddenInstrumentPolicyMissing,
    PaperShadowOnlyMissing,
    PrematureProfitabilityClaim,
    LiveOrTinyLiveAuthorityClaimed,
    BybitLiveExecutionNotProtected,
    IbkrLiveNotDenied,
    IbkrContactPerformed,
    SecretContentSerialized,
}

fn validate_hashes(
    hypothesis: &StockEtfStrategyHypothesisV1,
    blockers: &mut Vec<StockEtfStrategyHypothesisBlocker>,
) {
    use StockEtfStrategyHypothesisBlocker as Blocker;

    if !is_sha256_hex(&hypothesis.universe_hash) {
        blockers.push(Blocker::UniverseHashInvalid);
    }
    if !is_sha256_hex(&hypothesis.pit_universe_contract_hash) {
        blockers.push(Blocker::PitUniverseContractHashInvalid);
    }
    if !is_sha256_hex(&hypothesis.benchmark_version_hash) {
        blockers.push(Blocker::BenchmarkVersionHashInvalid);
    }
    if !is_sha256_hex(&hypothesis.cost_model_version_hash) {
        blockers.push(Blocker::CostModelVersionHashInvalid);
    }
    if !is_sha256_hex(&hypothesis.entry_rule_hash) {
        blockers.push(Blocker::EntryRuleHashInvalid);
    }
    if !is_sha256_hex(&hypothesis.exit_rule_hash) {
        blockers.push(Blocker::ExitRuleHashInvalid);
    }
    if !is_sha256_hex(&hypothesis.risk_rule_hash) {
        blockers.push(Blocker::RiskRuleHashInvalid);
    }
    if !is_sha256_hex(&hypothesis.feature_set_hash) {
        blockers.push(Blocker::FeatureSetHashInvalid);
    }
    if !is_sha256_hex(&hypothesis.data_source_policy_hash) {
        blockers.push(Blocker::DataSourcePolicyHashInvalid);
    }
    if !is_sha256_hex(&hypothesis.statistical_design_hash) {
        blockers.push(Blocker::StatisticalDesignHashInvalid);
    }
    if !is_sha256_hex(&hypothesis.hypothesis_preregistration_hash) {
        blockers.push(Blocker::HypothesisPreregistrationHashInvalid);
    }
}

fn validate_limits_and_controls(
    hypothesis: &StockEtfStrategyHypothesisV1,
    blockers: &mut Vec<StockEtfStrategyHypothesisBlocker>,
) {
    use StockEtfStrategyHypothesisBlocker as Blocker;

    if hypothesis.expected_holding_period_days_min < 1 {
        blockers.push(Blocker::HoldingPeriodTooShort);
    }
    if hypothesis.max_turnover_per_month_bps == 0 {
        blockers.push(Blocker::TurnoverLimitMissing);
    }
    if hypothesis.max_turnover_per_month_bps > 10_000 {
        blockers.push(Blocker::TurnoverLimitTooHigh);
    }
    if hypothesis.max_constituents_used == 0 {
        blockers.push(Blocker::MaxConstituentsMissing);
    }
    if hypothesis.max_constituents_used > 500 {
        blockers.push(Blocker::MaxConstituentsTooBroad);
    }
    if hypothesis.independent_observation_target < 30 {
        blockers.push(Blocker::IndependentObservationTargetTooLow);
    }
    if !hypothesis.lookahead_bias_controls_present {
        blockers.push(Blocker::LookaheadControlsMissing);
    }
    if !hypothesis.survivorship_bias_controls_present {
        blockers.push(Blocker::SurvivorshipControlsMissing);
    }
    if !hypothesis.multiple_testing_control_present {
        blockers.push(Blocker::MultipleTestingControlMissing);
    }
    if !hypothesis.benchmark_relative_metric_defined {
        blockers.push(Blocker::BenchmarkMetricMissing);
    }
    if !hypothesis.cost_after_metric_defined {
        blockers.push(Blocker::CostAfterMetricMissing);
    }
    if !hypothesis.no_options_cfd_margin_short {
        blockers.push(Blocker::ForbiddenInstrumentPolicyMissing);
    }
    if !hypothesis.paper_shadow_only {
        blockers.push(Blocker::PaperShadowOnlyMissing);
    }
    if hypothesis.profitability_claimed {
        blockers.push(Blocker::PrematureProfitabilityClaim);
    }
    if hypothesis.live_or_tiny_live_authority_claimed {
        blockers.push(Blocker::LiveOrTinyLiveAuthorityClaimed);
    }
    if !hypothesis.bybit_live_execution_unchanged {
        blockers.push(Blocker::BybitLiveExecutionNotProtected);
    }
    if !hypothesis.ibkr_live_denied {
        blockers.push(Blocker::IbkrLiveNotDenied);
    }
    if hypothesis.ibkr_contact_performed {
        blockers.push(Blocker::IbkrContactPerformed);
    }
    if hypothesis.secret_content_serialized {
        blockers.push(Blocker::SecretContentSerialized);
    }
}

fn valid_identifier(value: &str) -> bool {
    let trimmed = value.trim();
    !trimmed.is_empty()
        && trimmed == value
        && trimmed.len() <= 96
        && trimmed
            .chars()
            .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '_' | '-' | '.' | ':' | '/'))
}

fn hash(fill: char) -> String {
    fill.to_string().repeat(64)
}
