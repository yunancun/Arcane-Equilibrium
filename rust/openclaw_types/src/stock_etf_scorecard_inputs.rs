//! Stock/ETF scorecard input contracts for ADR-0048.
//!
//! These source-only validators define the atomic evidence shape feeding future
//! paper/shadow scorecards. They do not import broker fills, write scorecards,
//! apply DB migrations, contact IBKR, or start an evidence clock.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_ibkr_readonly_probe_result_import_request::STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID;
use crate::stock_etf_lane::{AssetLane, Broker, BrokerEnvironment};

pub const BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID: &str =
    "broker_account_portfolio_cash_ledger_v1";
pub const STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID: &str = "cost_model_version_v1";
pub const STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID: &str = "benchmark_versions_v1";
pub const STOCK_SHADOW_FILL_MODEL_CONTRACT_ID: &str = "stock_shadow_fill_model_v1";
pub const STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID: &str = "stock_etf_storage_capacity_v1";
pub const STOCK_ETF_STORAGE_MAX_UNIVERSE_SIZE: u32 = 1_000;
pub const STOCK_ETF_STORAGE_MAX_ROWS_PER_DAY_ESTIMATE: u64 = 5_000_000;
pub const STOCK_ETF_STORAGE_MIN_RAW_PAYLOAD_HASH_RETENTION_DAYS: u32 = 365;
pub const STOCK_ETF_STORAGE_MAX_COMPRESSED_RETENTION_DAYS: u32 = 3_650;
pub const STOCK_ETF_STORAGE_MAX_INDEX_BUDGET_MB: u32 = 8_192;
pub const STOCK_ETF_STORAGE_MAX_QUERY_SLO_MS: u32 = 5_000;
pub const STOCK_ETF_STORAGE_ARCHIVE_PATH_PREFIX: &str = "evidence/stock_etf_cash/";

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
    pub contract_id: String,
    pub source_version: u32,
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
            contract_id: String::new(),
            source_version: 0,
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
            contract_id: BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID.to_string(),
            source_version: 1,
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
        if self.contract_id != BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID {
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
    pub contract_id: String,
    pub source_version: u32,
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
            contract_id: String::new(),
            source_version: 0,
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
            contract_id: STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID.to_string(),
            source_version: 1,
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
        if self.contract_id != STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
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
    pub contract_id: String,
    pub source_version: u32,
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
            contract_id: String::new(),
            source_version: 0,
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
            contract_id: STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID.to_string(),
            source_version: 1,
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
        if self.contract_id != STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
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
    pub contract_id: String,
    pub source_version: u32,
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
            contract_id: String::new(),
            source_version: 0,
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
            contract_id: STOCK_SHADOW_FILL_MODEL_CONTRACT_ID.to_string(),
            source_version: 1,
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
        if self.contract_id != STOCK_SHADOW_FILL_MODEL_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
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
    pub contract_id: String,
    pub source_version: u32,
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
            contract_id: String::new(),
            source_version: 0,
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
            contract_id: STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID.to_string(),
            source_version: 1,
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
        if self.contract_id != STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.universe_size == 0 {
            blockers.push(Blocker::UniverseSizeMissing);
        } else if self.universe_size > STOCK_ETF_STORAGE_MAX_UNIVERSE_SIZE {
            blockers.push(Blocker::UniverseSizeExceedsCapacityPlan);
        }
        if self.rows_per_day_estimate == 0 {
            blockers.push(Blocker::RowsPerDayEstimateMissing);
        } else if self.rows_per_day_estimate > STOCK_ETF_STORAGE_MAX_ROWS_PER_DAY_ESTIMATE {
            blockers.push(Blocker::RowsPerDayEstimateExceedsCapacityPlan);
        }
        if self.raw_payload_hash_retention_days == 0 {
            blockers.push(Blocker::RawPayloadRetentionMissing);
        } else if self.raw_payload_hash_retention_days
            < STOCK_ETF_STORAGE_MIN_RAW_PAYLOAD_HASH_RETENTION_DAYS
        {
            blockers.push(Blocker::RawPayloadRetentionTooShort);
        }
        if self.compressed_retention_days == 0 {
            blockers.push(Blocker::CompressedRetentionMissing);
        } else if self.compressed_retention_days < self.raw_payload_hash_retention_days {
            blockers.push(Blocker::CompressedRetentionShorterThanRawPayloadHashRetention);
        } else if self.compressed_retention_days > STOCK_ETF_STORAGE_MAX_COMPRESSED_RETENTION_DAYS {
            blockers.push(Blocker::CompressedRetentionExceedsCapacityPlan);
        }
        if self.index_budget_mb == 0 {
            blockers.push(Blocker::IndexBudgetMissing);
        } else if self.index_budget_mb > STOCK_ETF_STORAGE_MAX_INDEX_BUDGET_MB {
            blockers.push(Blocker::IndexBudgetExceedsCapacityPlan);
        }
        if self.query_slo_ms == 0 {
            blockers.push(Blocker::QuerySloMissing);
        } else if self.query_slo_ms > STOCK_ETF_STORAGE_MAX_QUERY_SLO_MS {
            blockers.push(Blocker::QuerySloExceedsCapacityPlan);
        }
        if self.archive_path.trim().is_empty() {
            blockers.push(Blocker::ArchivePathMissing);
        } else if !is_safe_stock_etf_archive_path(&self.archive_path) {
            blockers.push(Blocker::ArchivePathUnsafe);
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

fn is_safe_stock_etf_archive_path(path: &str) -> bool {
    let trimmed = path.trim();
    trimmed.starts_with(STOCK_ETF_STORAGE_ARCHIVE_PATH_PREFIX)
        && trimmed.len() > STOCK_ETF_STORAGE_ARCHIVE_PATH_PREFIX.len()
        && !trimmed.starts_with('/')
        && !trimmed.contains("..")
        && !trimmed.contains("//")
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfScorecardInputBundleV1 {
    pub cash_ledger: BrokerAccountPortfolioCashLedgerV1,
    pub cost_model: StockEtfCostModelVersionV1,
    pub benchmark: StockEtfBenchmarkVersionV1,
    pub shadow_fill_model: StockShadowFillModelV1,
    pub storage_capacity: StockEtfStorageCapacityV1,
    pub readonly_probe_result_import_request_contract_id: String,
    pub readonly_probe_result_import_request_hash: String,
    pub market_data_provenance_contract_hash: String,
    pub reference_data_sources_contract_hash: String,
    pub risk_policy_contract_hash: String,
    pub atomic_fact_input_hash: String,
    pub source_commit: String,
    pub scorecard_is_derived_only: bool,
    pub paper_and_shadow_fills_separate: bool,
    pub live_fill_claimed: bool,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub broker_fill_import_performed: bool,
    pub scorecard_writer_started: bool,
    pub db_apply_performed: bool,
    pub evidence_clock_started: bool,
    pub secret_content_serialized: bool,
    pub live_or_tiny_live_authorized: bool,
}

impl Default for StockEtfScorecardInputBundleV1 {
    fn default() -> Self {
        Self {
            cash_ledger: BrokerAccountPortfolioCashLedgerV1::default(),
            cost_model: StockEtfCostModelVersionV1::default(),
            benchmark: StockEtfBenchmarkVersionV1::default(),
            shadow_fill_model: StockShadowFillModelV1::default(),
            storage_capacity: StockEtfStorageCapacityV1::default(),
            readonly_probe_result_import_request_contract_id: String::new(),
            readonly_probe_result_import_request_hash: String::new(),
            market_data_provenance_contract_hash: String::new(),
            reference_data_sources_contract_hash: String::new(),
            risk_policy_contract_hash: String::new(),
            atomic_fact_input_hash: String::new(),
            source_commit: String::new(),
            scorecard_is_derived_only: false,
            paper_and_shadow_fills_separate: false,
            live_fill_claimed: false,
            bybit_live_execution_unchanged: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            broker_fill_import_performed: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            evidence_clock_started: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
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
            readonly_probe_result_import_request_contract_id:
                STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID.to_string(),
            readonly_probe_result_import_request_hash: "b".repeat(64),
            market_data_provenance_contract_hash: "8".repeat(64),
            reference_data_sources_contract_hash: "9".repeat(64),
            risk_policy_contract_hash: "a".repeat(64),
            atomic_fact_input_hash: "7".repeat(64),
            source_commit: "535019c9".to_string(),
            scorecard_is_derived_only: true,
            paper_and_shadow_fills_separate: true,
            live_fill_claimed: false,
            bybit_live_execution_unchanged: true,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            broker_fill_import_performed: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            evidence_clock_started: false,
            secret_content_serialized: false,
            live_or_tiny_live_authorized: false,
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
        if self.readonly_probe_result_import_request_contract_id
            != STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID
        {
            blockers.push(Blocker::ReadonlyProbeResultImportRequestContractIdMismatch);
        }
        if !is_sha256_hex(&self.readonly_probe_result_import_request_hash) {
            blockers.push(Blocker::ReadonlyProbeResultImportRequestHashInvalid);
        }
        if !is_sha256_hex(&self.market_data_provenance_contract_hash) {
            blockers.push(Blocker::MarketDataProvenanceContractHashInvalid);
        }
        if !is_sha256_hex(&self.reference_data_sources_contract_hash) {
            blockers.push(Blocker::ReferenceDataSourcesContractHashInvalid);
        }
        if !is_sha256_hex(&self.risk_policy_contract_hash) {
            blockers.push(Blocker::RiskPolicyContractHashInvalid);
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
        if !self.bybit_live_execution_unchanged {
            blockers.push(Blocker::BybitLiveExecutionNotProtected);
        }
        if self.ibkr_contact_performed {
            blockers.push(Blocker::IbkrContactPerformed);
        }
        if self.connector_runtime_started {
            blockers.push(Blocker::ConnectorRuntimeStarted);
        }
        if self.broker_fill_import_performed {
            blockers.push(Blocker::BrokerFillImportPerformed);
        }
        if self.scorecard_writer_started {
            blockers.push(Blocker::ScorecardWriterStarted);
        }
        if self.db_apply_performed {
            blockers.push(Blocker::DbApplyPerformed);
        }
        if self.evidence_clock_started {
            blockers.push(Blocker::EvidenceClockStarted);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if self.live_or_tiny_live_authorized {
            blockers.push(Blocker::LiveOrTinyLiveAuthorized);
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
    ContractIdMismatch,
    SourceVersionMismatch,
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
    UniverseSizeExceedsCapacityPlan,
    RowsPerDayEstimateMissing,
    RowsPerDayEstimateExceedsCapacityPlan,
    RawPayloadRetentionMissing,
    RawPayloadRetentionTooShort,
    CompressedRetentionMissing,
    CompressedRetentionShorterThanRawPayloadHashRetention,
    CompressedRetentionExceedsCapacityPlan,
    IndexBudgetMissing,
    IndexBudgetExceedsCapacityPlan,
    QuerySloMissing,
    QuerySloExceedsCapacityPlan,
    ArchivePathMissing,
    ArchivePathUnsafe,
    CapacityPlanHashInvalid,
    CapacityBreachPolicyMissing,
    CashLedgerRejected,
    CostModelRejected,
    BenchmarkRejected,
    ShadowFillModelRejected,
    StorageCapacityRejected,
    ReadonlyProbeResultImportRequestContractIdMismatch,
    ReadonlyProbeResultImportRequestHashInvalid,
    MarketDataProvenanceContractHashInvalid,
    ReferenceDataSourcesContractHashInvalid,
    RiskPolicyContractHashInvalid,
    AtomicFactInputHashInvalid,
    SourceCommitMissing,
    ScorecardNotDerivedOnly,
    PaperShadowFillSeparationMissing,
    LiveFillClaimed,
    BybitLiveExecutionNotProtected,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    BrokerFillImportPerformed,
    ScorecardWriterStarted,
    DbApplyPerformed,
    EvidenceClockStarted,
    SecretContentSerialized,
    LiveOrTinyLiveAuthorized,
}
