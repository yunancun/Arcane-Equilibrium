//! Stock/ETF scorecard input contracts for ADR-0048.
//!
//! These source-only validators define the atomic evidence shape feeding future
//! paper/shadow scorecards. They do not import broker fills, write scorecards,
//! apply DB migrations, contact IBKR, or start an evidence clock.

use serde::{Deserialize, Serialize};

mod bundle;
mod components;

pub use bundle::StockEtfScorecardInputBundleV1;
pub use components::{
    BrokerAccountPortfolioCashLedgerV1, StockEtfBenchmarkVersionV1, StockEtfCostModelVersionV1,
    StockEtfOrderSide, StockEtfStorageCapacityV1, StockShadowFillModelV1,
};

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
