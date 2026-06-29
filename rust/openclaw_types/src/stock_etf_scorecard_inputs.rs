//! Stock/ETF scorecard input contracts for ADR-0048.
//!
//! These source-only validators define the atomic evidence shape feeding future
//! paper/shadow scorecards. They do not import broker fills, write scorecards,
//! apply DB migrations, contact IBKR, or start an evidence clock.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{AssetLane, Broker, BrokerEnvironment};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfOrderSide {
    Unknown,
    Buy,
    Sell,
}

impl Default for StockEtfOrderSide {
    fn default() -> Self {
        Self::Unknown
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BrokerAccountPortfolioCashLedgerV1 {
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub account_fingerprint_hash: String,
    pub account_snapshot_hash: String,
    pub portfolio_positions_hash: String,
    pub currency: String,
    pub cash_balance_minor_units: i64,
    pub buying_power_minor_units: i64,
    pub as_of_ms: u64,
    pub source_report_hash: String,
}

impl Default for BrokerAccountPortfolioCashLedgerV1 {
    fn default() -> Self {
        Self {
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            account_fingerprint_hash: String::new(),
            account_snapshot_hash: String::new(),
            portfolio_positions_hash: String::new(),
            currency: String::new(),
            cash_balance_minor_units: 0,
            buying_power_minor_units: 0,
            as_of_ms: 0,
            source_report_hash: String::new(),
        }
    }
}

impl BrokerAccountPortfolioCashLedgerV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            account_fingerprint_hash: "1".repeat(64),
            account_snapshot_hash: "2".repeat(64),
            portfolio_positions_hash: "3".repeat(64),
            currency: "USD".to_string(),
            cash_balance_minor_units: 1_000_000,
            buying_power_minor_units: 2_000_000,
            as_of_ms: 1_772_233_000_000,
            source_report_hash: "4".repeat(64),
        }
    }

    pub fn validate(&self) -> StockEtfScorecardInputVerdict<StockEtfScorecardInputBlocker> {
        use StockEtfScorecardInputBlocker as Blocker;
        let mut blockers = Vec::new();
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if !matches!(
            self.environment,
            BrokerEnvironment::ReadOnly | BrokerEnvironment::Paper
        ) {
            blockers.push(Blocker::CashLedgerEnvironmentDenied);
        }
        if !is_sha256_hex(&self.account_fingerprint_hash) {
            blockers.push(Blocker::AccountFingerprintHashInvalid);
        }
        if !is_sha256_hex(&self.account_snapshot_hash) {
            blockers.push(Blocker::AccountSnapshotHashInvalid);
        }
        if !is_sha256_hex(&self.portfolio_positions_hash) {
            blockers.push(Blocker::PortfolioPositionsHashInvalid);
        }
        if self.currency.trim().is_empty() {
            blockers.push(Blocker::CurrencyMissing);
        }
        if self.as_of_ms == 0 {
            blockers.push(Blocker::AsOfMissing);
        }
        if !is_sha256_hex(&self.source_report_hash) {
            blockers.push(Blocker::SourceReportHashInvalid);
        }
        StockEtfScorecardInputVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfCostModelVersionV1 {
    pub version_hash: String,
    pub commission_schedule_hash: String,
    pub exchange_reg_fee_hash: String,
    pub spread_model_hash: String,
    pub slippage_model_hash: String,
    pub fx_drag_model_hash: String,
    pub tax_fee_placeholder_hash: String,
    pub conservative_fill_penalty_bps: u32,
}

impl Default for StockEtfCostModelVersionV1 {
    fn default() -> Self {
        Self {
            version_hash: String::new(),
            commission_schedule_hash: String::new(),
            exchange_reg_fee_hash: String::new(),
            spread_model_hash: String::new(),
            slippage_model_hash: String::new(),
            fx_drag_model_hash: String::new(),
            tax_fee_placeholder_hash: String::new(),
            conservative_fill_penalty_bps: 0,
        }
    }
}

impl StockEtfCostModelVersionV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            version_hash: "5".repeat(64),
            commission_schedule_hash: "6".repeat(64),
            exchange_reg_fee_hash: "7".repeat(64),
            spread_model_hash: "8".repeat(64),
            slippage_model_hash: "9".repeat(64),
            fx_drag_model_hash: "a".repeat(64),
            tax_fee_placeholder_hash: "b".repeat(64),
            conservative_fill_penalty_bps: 10,
        }
    }

    pub fn validate(&self) -> StockEtfScorecardInputVerdict<StockEtfScorecardInputBlocker> {
        use StockEtfScorecardInputBlocker as Blocker;
        let mut blockers = Vec::new();
        if !is_sha256_hex(&self.version_hash) {
            blockers.push(Blocker::CostModelVersionHashInvalid);
        }
        if !is_sha256_hex(&self.commission_schedule_hash) {
            blockers.push(Blocker::CommissionScheduleHashInvalid);
        }
        if !is_sha256_hex(&self.exchange_reg_fee_hash) {
            blockers.push(Blocker::ExchangeRegFeeHashInvalid);
        }
        if !is_sha256_hex(&self.spread_model_hash) {
            blockers.push(Blocker::SpreadModelHashInvalid);
        }
        if !is_sha256_hex(&self.slippage_model_hash) {
            blockers.push(Blocker::SlippageModelHashInvalid);
        }
        if !is_sha256_hex(&self.fx_drag_model_hash) {
            blockers.push(Blocker::FxDragModelHashInvalid);
        }
        if !is_sha256_hex(&self.tax_fee_placeholder_hash) {
            blockers.push(Blocker::TaxFeePlaceholderHashInvalid);
        }
        if self.conservative_fill_penalty_bps == 0 {
            blockers.push(Blocker::ConservativeFillPenaltyMissing);
        }
        StockEtfScorecardInputVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfBenchmarkVersionV1 {
    pub benchmark_id: String,
    pub data_source_hash: String,
    pub construction_version_hash: String,
    pub rebalance_rule_hash: String,
    pub currency_treatment_hash: String,
    pub corporate_action_adjustment_hash: String,
    pub matched_control_rule_hash: String,
    pub version_hash: String,
}

impl Default for StockEtfBenchmarkVersionV1 {
    fn default() -> Self {
        Self {
            benchmark_id: String::new(),
            data_source_hash: String::new(),
            construction_version_hash: String::new(),
            rebalance_rule_hash: String::new(),
            currency_treatment_hash: String::new(),
            corporate_action_adjustment_hash: String::new(),
            matched_control_rule_hash: String::new(),
            version_hash: String::new(),
        }
    }
}

impl StockEtfBenchmarkVersionV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            benchmark_id: "SPY_total_return_matched_control_v1".to_string(),
            data_source_hash: "c".repeat(64),
            construction_version_hash: "d".repeat(64),
            rebalance_rule_hash: "e".repeat(64),
            currency_treatment_hash: "f".repeat(64),
            corporate_action_adjustment_hash: "1".repeat(64),
            matched_control_rule_hash: "2".repeat(64),
            version_hash: "3".repeat(64),
        }
    }

    pub fn validate(&self) -> StockEtfScorecardInputVerdict<StockEtfScorecardInputBlocker> {
        use StockEtfScorecardInputBlocker as Blocker;
        let mut blockers = Vec::new();
        if self.benchmark_id.trim().is_empty() {
            blockers.push(Blocker::BenchmarkIdMissing);
        }
        if !is_sha256_hex(&self.data_source_hash) {
            blockers.push(Blocker::BenchmarkDataSourceHashInvalid);
        }
        if !is_sha256_hex(&self.construction_version_hash) {
            blockers.push(Blocker::BenchmarkConstructionHashInvalid);
        }
        if !is_sha256_hex(&self.rebalance_rule_hash) {
            blockers.push(Blocker::BenchmarkRebalanceHashInvalid);
        }
        if !is_sha256_hex(&self.currency_treatment_hash) {
            blockers.push(Blocker::BenchmarkCurrencyHashInvalid);
        }
        if !is_sha256_hex(&self.corporate_action_adjustment_hash) {
            blockers.push(Blocker::BenchmarkCorporateActionHashInvalid);
        }
        if !is_sha256_hex(&self.matched_control_rule_hash) {
            blockers.push(Blocker::BenchmarkMatchedControlHashInvalid);
        }
        if !is_sha256_hex(&self.version_hash) {
            blockers.push(Blocker::BenchmarkVersionHashInvalid);
        }
        StockEtfScorecardInputVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockShadowFillModelV1 {
    pub signal_id: String,
    pub instrument_identity_hash: String,
    pub side: StockEtfOrderSide,
    pub intended_notional_minor_units: u64,
    pub market_session_id: String,
    pub quote_or_bar_source_hash: String,
    pub conservative_fill_price_micros: u64,
    pub spread_bps: u32,
    pub slippage_bps: u32,
    pub cost_bps: u32,
    pub rejection_reason: String,
    pub synthetic_shadow: bool,
    pub broker_paper_fill_linked: bool,
    pub live_fill_linked: bool,
}

impl Default for StockShadowFillModelV1 {
    fn default() -> Self {
        Self {
            signal_id: String::new(),
            instrument_identity_hash: String::new(),
            side: StockEtfOrderSide::Unknown,
            intended_notional_minor_units: 0,
            market_session_id: String::new(),
            quote_or_bar_source_hash: String::new(),
            conservative_fill_price_micros: 0,
            spread_bps: 0,
            slippage_bps: 0,
            cost_bps: 0,
            rejection_reason: String::new(),
            synthetic_shadow: false,
            broker_paper_fill_linked: false,
            live_fill_linked: false,
        }
    }
}

impl StockShadowFillModelV1 {
    pub fn accepted_fill_fixture() -> Self {
        Self {
            signal_id: "shadow-signal-20260301-SPY-buy-001".to_string(),
            instrument_identity_hash: "4".repeat(64),
            side: StockEtfOrderSide::Buy,
            intended_notional_minor_units: 50_000,
            market_session_id: "XNYS-2026-03-01-regular".to_string(),
            quote_or_bar_source_hash: "5".repeat(64),
            conservative_fill_price_micros: 512_340_000,
            spread_bps: 4,
            slippage_bps: 6,
            cost_bps: 10,
            rejection_reason: String::new(),
            synthetic_shadow: true,
            broker_paper_fill_linked: false,
            live_fill_linked: false,
        }
    }

    pub fn validate(&self) -> StockEtfScorecardInputVerdict<StockEtfScorecardInputBlocker> {
        use StockEtfScorecardInputBlocker as Blocker;
        let mut blockers = Vec::new();
        if self.signal_id.trim().is_empty() {
            blockers.push(Blocker::SignalIdMissing);
        }
        if !is_sha256_hex(&self.instrument_identity_hash) {
            blockers.push(Blocker::InstrumentIdentityHashInvalid);
        }
        if self.side == StockEtfOrderSide::Unknown {
            blockers.push(Blocker::OrderSideUnknown);
        }
        if self.intended_notional_minor_units == 0 {
            blockers.push(Blocker::IntendedNotionalMissing);
        }
        if self.market_session_id.trim().is_empty() {
            blockers.push(Blocker::MarketSessionMissing);
        }
        if !is_sha256_hex(&self.quote_or_bar_source_hash) {
            blockers.push(Blocker::QuoteOrBarSourceHashInvalid);
        }
        if self.rejection_reason.trim().is_empty() && self.conservative_fill_price_micros == 0 {
            blockers.push(Blocker::ConservativeFillPriceMissing);
        }
        if !self.synthetic_shadow {
            blockers.push(Blocker::SyntheticShadowMarkerMissing);
        }
        if self.broker_paper_fill_linked {
            blockers.push(Blocker::ShadowFillLinkedToBrokerPaperFill);
        }
        if self.live_fill_linked {
            blockers.push(Blocker::ShadowFillLinkedToLiveFill);
        }
        StockEtfScorecardInputVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfStorageCapacityV1 {
    pub universe_size: u32,
    pub rows_per_day_estimate: u64,
    pub raw_payload_hash_retention_days: u32,
    pub compressed_retention_days: u32,
    pub index_budget_mb: u32,
    pub query_slo_ms: u32,
    pub archive_path: String,
    pub capacity_plan_hash: String,
    pub capacity_breach_blocks_evidence_clock: bool,
}

impl Default for StockEtfStorageCapacityV1 {
    fn default() -> Self {
        Self {
            universe_size: 0,
            rows_per_day_estimate: 0,
            raw_payload_hash_retention_days: 0,
            compressed_retention_days: 0,
            index_budget_mb: 0,
            query_slo_ms: 0,
            archive_path: String::new(),
            capacity_plan_hash: String::new(),
            capacity_breach_blocks_evidence_clock: false,
        }
    }
}

impl StockEtfStorageCapacityV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            universe_size: 100,
            rows_per_day_estimate: 25_000,
            raw_payload_hash_retention_days: 365,
            compressed_retention_days: 2_555,
            index_budget_mb: 512,
            query_slo_ms: 1_000,
            archive_path: "evidence/stock_etf_cash/archive".to_string(),
            capacity_plan_hash: "6".repeat(64),
            capacity_breach_blocks_evidence_clock: true,
        }
    }

    pub fn validate(&self) -> StockEtfScorecardInputVerdict<StockEtfScorecardInputBlocker> {
        use StockEtfScorecardInputBlocker as Blocker;
        let mut blockers = Vec::new();
        if self.universe_size == 0 {
            blockers.push(Blocker::UniverseSizeMissing);
        }
        if self.rows_per_day_estimate == 0 {
            blockers.push(Blocker::RowsPerDayEstimateMissing);
        }
        if self.raw_payload_hash_retention_days == 0 {
            blockers.push(Blocker::RawPayloadRetentionMissing);
        }
        if self.compressed_retention_days == 0 {
            blockers.push(Blocker::CompressedRetentionMissing);
        }
        if self.index_budget_mb == 0 {
            blockers.push(Blocker::IndexBudgetMissing);
        }
        if self.query_slo_ms == 0 {
            blockers.push(Blocker::QuerySloMissing);
        }
        if self.archive_path.trim().is_empty() {
            blockers.push(Blocker::ArchivePathMissing);
        }
        if !is_sha256_hex(&self.capacity_plan_hash) {
            blockers.push(Blocker::CapacityPlanHashInvalid);
        }
        if !self.capacity_breach_blocks_evidence_clock {
            blockers.push(Blocker::CapacityBreachPolicyMissing);
        }
        StockEtfScorecardInputVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfScorecardInputBundleV1 {
    pub cash_ledger: BrokerAccountPortfolioCashLedgerV1,
    pub cost_model: StockEtfCostModelVersionV1,
    pub benchmark: StockEtfBenchmarkVersionV1,
    pub shadow_fill_model: StockShadowFillModelV1,
    pub storage_capacity: StockEtfStorageCapacityV1,
    pub atomic_fact_input_hash: String,
    pub source_commit: String,
    pub scorecard_is_derived_only: bool,
    pub paper_and_shadow_fills_separate: bool,
    pub live_fill_claimed: bool,
}

impl Default for StockEtfScorecardInputBundleV1 {
    fn default() -> Self {
        Self {
            cash_ledger: BrokerAccountPortfolioCashLedgerV1::default(),
            cost_model: StockEtfCostModelVersionV1::default(),
            benchmark: StockEtfBenchmarkVersionV1::default(),
            shadow_fill_model: StockShadowFillModelV1::default(),
            storage_capacity: StockEtfStorageCapacityV1::default(),
            atomic_fact_input_hash: String::new(),
            source_commit: String::new(),
            scorecard_is_derived_only: false,
            paper_and_shadow_fills_separate: false,
            live_fill_claimed: false,
        }
    }
}

impl StockEtfScorecardInputBundleV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            cash_ledger: BrokerAccountPortfolioCashLedgerV1::accepted_fixture(),
            cost_model: StockEtfCostModelVersionV1::accepted_fixture(),
            benchmark: StockEtfBenchmarkVersionV1::accepted_fixture(),
            shadow_fill_model: StockShadowFillModelV1::accepted_fill_fixture(),
            storage_capacity: StockEtfStorageCapacityV1::accepted_fixture(),
            atomic_fact_input_hash: "7".repeat(64),
            source_commit: "535019c9".to_string(),
            scorecard_is_derived_only: true,
            paper_and_shadow_fills_separate: true,
            live_fill_claimed: false,
        }
    }

    pub fn validate(&self) -> StockEtfScorecardInputVerdict<StockEtfScorecardInputBlocker> {
        use StockEtfScorecardInputBlocker as Blocker;
        let mut blockers = Vec::new();
        if !self.cash_ledger.validate().accepted {
            blockers.push(Blocker::CashLedgerRejected);
        }
        if !self.cost_model.validate().accepted {
            blockers.push(Blocker::CostModelRejected);
        }
        if !self.benchmark.validate().accepted {
            blockers.push(Blocker::BenchmarkRejected);
        }
        if !self.shadow_fill_model.validate().accepted {
            blockers.push(Blocker::ShadowFillModelRejected);
        }
        if !self.storage_capacity.validate().accepted {
            blockers.push(Blocker::StorageCapacityRejected);
        }
        if !is_sha256_hex(&self.atomic_fact_input_hash) {
            blockers.push(Blocker::AtomicFactInputHashInvalid);
        }
        if self.source_commit.trim().is_empty() {
            blockers.push(Blocker::SourceCommitMissing);
        }
        if !self.scorecard_is_derived_only {
            blockers.push(Blocker::ScorecardNotDerivedOnly);
        }
        if !self.paper_and_shadow_fills_separate {
            blockers.push(Blocker::PaperShadowFillSeparationMissing);
        }
        if self.live_fill_claimed {
            blockers.push(Blocker::LiveFillClaimed);
        }
        StockEtfScorecardInputVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfScorecardInputVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfScorecardInputVerdict<B> {
    fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfScorecardInputBlocker {
    WrongAssetLane,
    WrongBroker,
    CashLedgerEnvironmentDenied,
    AccountFingerprintHashInvalid,
    AccountSnapshotHashInvalid,
    PortfolioPositionsHashInvalid,
    CurrencyMissing,
    AsOfMissing,
    SourceReportHashInvalid,
    CostModelVersionHashInvalid,
    CommissionScheduleHashInvalid,
    ExchangeRegFeeHashInvalid,
    SpreadModelHashInvalid,
    SlippageModelHashInvalid,
    FxDragModelHashInvalid,
    TaxFeePlaceholderHashInvalid,
    ConservativeFillPenaltyMissing,
    BenchmarkIdMissing,
    BenchmarkDataSourceHashInvalid,
    BenchmarkConstructionHashInvalid,
    BenchmarkRebalanceHashInvalid,
    BenchmarkCurrencyHashInvalid,
    BenchmarkCorporateActionHashInvalid,
    BenchmarkMatchedControlHashInvalid,
    BenchmarkVersionHashInvalid,
    SignalIdMissing,
    InstrumentIdentityHashInvalid,
    OrderSideUnknown,
    IntendedNotionalMissing,
    MarketSessionMissing,
    QuoteOrBarSourceHashInvalid,
    ConservativeFillPriceMissing,
    SyntheticShadowMarkerMissing,
    ShadowFillLinkedToBrokerPaperFill,
    ShadowFillLinkedToLiveFill,
    UniverseSizeMissing,
    RowsPerDayEstimateMissing,
    RawPayloadRetentionMissing,
    CompressedRetentionMissing,
    IndexBudgetMissing,
    QuerySloMissing,
    ArchivePathMissing,
    CapacityPlanHashInvalid,
    CapacityBreachPolicyMissing,
    CashLedgerRejected,
    CostModelRejected,
    BenchmarkRejected,
    ShadowFillModelRejected,
    StorageCapacityRejected,
    AtomicFactInputHashInvalid,
    SourceCommitMissing,
    ScorecardNotDerivedOnly,
    PaperShadowFillSeparationMissing,
    LiveFillClaimed,
}
