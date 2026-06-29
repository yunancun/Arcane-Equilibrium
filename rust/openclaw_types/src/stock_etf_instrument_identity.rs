//! Stock/ETF instrument identity contract for ADR-0048.
//!
//! This source-only validator pins the point-in-time identity shape for
//! Stock/ETF cash instruments before any IBKR paper/shadow workflow can consume
//! market data, contract details, or paper order intent. It does not contact
//! IBKR, inspect secrets, create connectors, subscribe to market data, route
//! orders, or change Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{AssetLane, Broker, InstrumentKind};

pub const STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID: &str = "instrument_identity_contract_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfInstrumentIdentityV1 {
    pub contract_id: String,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub instrument_kind: InstrumentKind,
    pub symbol: String,
    pub listing_venue: StockEtfListingVenue,
    pub primary_exchange: StockEtfListingVenue,
    pub currency: StockEtfCurrency,
    pub tradability_status: StockEtfTradabilityStatus,
    pub priips_kid_status: StockEtfPriipsKidStatus,
    pub fractional_policy_recorded: bool,
    pub point_in_time_asof_ms: u64,
    pub market_calendar_id: String,
    pub market_calendar_hash: String,
    pub broker_contract_details_hash: String,
    pub instrument_identity_hash: String,
    pub corporate_action_adjustment_version_hash: String,
    pub source_artifact_hash: String,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_live_denied: bool,
    pub margin_short_denied: bool,
    pub options_cfd_denied: bool,
    pub ibkr_contact_performed: bool,
    pub secret_content_serialized: bool,
}

impl Default for StockEtfInstrumentIdentityV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            instrument_kind: InstrumentKind::CryptoPerp,
            symbol: String::new(),
            listing_venue: StockEtfListingVenue::UnknownDenied,
            primary_exchange: StockEtfListingVenue::UnknownDenied,
            currency: StockEtfCurrency::UnknownDenied,
            tradability_status: StockEtfTradabilityStatus::UnknownDenied,
            priips_kid_status: StockEtfPriipsKidStatus::UnknownDenied,
            fractional_policy_recorded: false,
            point_in_time_asof_ms: 0,
            market_calendar_id: String::new(),
            market_calendar_hash: String::new(),
            broker_contract_details_hash: String::new(),
            instrument_identity_hash: String::new(),
            corporate_action_adjustment_version_hash: String::new(),
            source_artifact_hash: String::new(),
            bybit_live_execution_unchanged: false,
            ibkr_live_denied: false,
            margin_short_denied: false,
            options_cfd_denied: false,
            ibkr_contact_performed: false,
            secret_content_serialized: false,
        }
    }
}

impl StockEtfInstrumentIdentityV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID.to_string(),
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            instrument_kind: InstrumentKind::Stock,
            symbol: "AMD".to_string(),
            listing_venue: StockEtfListingVenue::Xnas,
            primary_exchange: StockEtfListingVenue::Xnas,
            currency: StockEtfCurrency::Usd,
            tradability_status: StockEtfTradabilityStatus::Tradable,
            priips_kid_status: StockEtfPriipsKidStatus::NotRequired,
            fractional_policy_recorded: true,
            point_in_time_asof_ms: 1_772_236_800_000,
            market_calendar_id: "XNAS-2026-03-01-regular".to_string(),
            market_calendar_hash: hash('1'),
            broker_contract_details_hash: hash('2'),
            instrument_identity_hash: hash('3'),
            corporate_action_adjustment_version_hash: hash('4'),
            source_artifact_hash: hash('5'),
            bybit_live_execution_unchanged: true,
            ibkr_live_denied: true,
            margin_short_denied: true,
            options_cfd_denied: true,
            ibkr_contact_performed: false,
            secret_content_serialized: false,
        }
    }

    pub fn validate(&self) -> StockEtfInstrumentIdentityVerdict<StockEtfInstrumentIdentityBlocker> {
        use StockEtfInstrumentIdentityBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if !matches!(
            self.instrument_kind,
            InstrumentKind::Stock | InstrumentKind::Etf | InstrumentKind::Cash
        ) {
            blockers.push(Blocker::InstrumentKindDenied);
        }
        if !valid_symbol(&self.symbol) {
            blockers.push(Blocker::SymbolInvalid);
        }
        if self.listing_venue == StockEtfListingVenue::UnknownDenied {
            blockers.push(Blocker::ListingVenueDenied);
        }
        if self.primary_exchange == StockEtfListingVenue::UnknownDenied {
            blockers.push(Blocker::PrimaryExchangeDenied);
        }
        validate_cash_venue_pair(
            self.instrument_kind,
            self.listing_venue,
            self.primary_exchange,
            &mut blockers,
        );
        if self.currency != StockEtfCurrency::Usd {
            blockers.push(Blocker::CurrencyDenied);
        }
        if self.tradability_status != StockEtfTradabilityStatus::Tradable {
            blockers.push(Blocker::TradabilityNotTradable);
        }
        if matches!(
            self.priips_kid_status,
            StockEtfPriipsKidStatus::MissingBlocked | StockEtfPriipsKidStatus::UnknownDenied
        ) {
            blockers.push(Blocker::PriipsKidBlocked);
        }
        if !self.fractional_policy_recorded {
            blockers.push(Blocker::FractionalPolicyMissing);
        }
        if self.point_in_time_asof_ms == 0 {
            blockers.push(Blocker::PointInTimeAsofMissing);
        }
        if self.market_calendar_id.trim().is_empty() {
            blockers.push(Blocker::MarketCalendarIdMissing);
        }
        if !is_sha256_hex(&self.market_calendar_hash) {
            blockers.push(Blocker::MarketCalendarHashInvalid);
        }
        if !is_sha256_hex(&self.broker_contract_details_hash) {
            blockers.push(Blocker::BrokerContractDetailsHashInvalid);
        }
        if !is_sha256_hex(&self.instrument_identity_hash) {
            blockers.push(Blocker::InstrumentIdentityHashInvalid);
        }
        if !is_sha256_hex(&self.corporate_action_adjustment_version_hash) {
            blockers.push(Blocker::CorporateActionAdjustmentHashInvalid);
        }
        if !is_sha256_hex(&self.source_artifact_hash) {
            blockers.push(Blocker::SourceArtifactHashInvalid);
        }
        if !self.bybit_live_execution_unchanged {
            blockers.push(Blocker::BybitLiveExecutionNotProtected);
        }
        if !self.ibkr_live_denied {
            blockers.push(Blocker::IbkrLiveNotDenied);
        }
        if !self.margin_short_denied {
            blockers.push(Blocker::MarginShortNotDenied);
        }
        if !self.options_cfd_denied {
            blockers.push(Blocker::OptionsCfdNotDenied);
        }
        if self.ibkr_contact_performed {
            blockers.push(Blocker::IbkrContactPerformed);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }

        StockEtfInstrumentIdentityVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfListingVenue {
    Xnys,
    Xnas,
    Arcx,
    Bats,
    Xase,
    CashLedger,
    UnknownDenied,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfCurrency {
    Usd,
    UnknownDenied,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfTradabilityStatus {
    Tradable,
    Blocked,
    Halted,
    UnknownDenied,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfPriipsKidStatus {
    NotRequired,
    Present,
    MissingBlocked,
    UnknownDenied,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfInstrumentIdentityVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfInstrumentIdentityVerdict<B> {
    pub fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfInstrumentIdentityBlocker {
    ContractIdMismatch,
    WrongAssetLane,
    WrongBroker,
    InstrumentKindDenied,
    SymbolInvalid,
    ListingVenueDenied,
    PrimaryExchangeDenied,
    CashInstrumentVenueMismatch,
    NonCashInstrumentVenueMismatch,
    CurrencyDenied,
    TradabilityNotTradable,
    PriipsKidBlocked,
    FractionalPolicyMissing,
    PointInTimeAsofMissing,
    MarketCalendarIdMissing,
    MarketCalendarHashInvalid,
    BrokerContractDetailsHashInvalid,
    InstrumentIdentityHashInvalid,
    CorporateActionAdjustmentHashInvalid,
    SourceArtifactHashInvalid,
    BybitLiveExecutionNotProtected,
    IbkrLiveNotDenied,
    MarginShortNotDenied,
    OptionsCfdNotDenied,
    IbkrContactPerformed,
    SecretContentSerialized,
}

fn validate_cash_venue_pair(
    instrument_kind: InstrumentKind,
    listing_venue: StockEtfListingVenue,
    primary_exchange: StockEtfListingVenue,
    blockers: &mut Vec<StockEtfInstrumentIdentityBlocker>,
) {
    use StockEtfInstrumentIdentityBlocker as Blocker;

    if instrument_kind == InstrumentKind::Cash {
        if listing_venue != StockEtfListingVenue::CashLedger
            || primary_exchange != StockEtfListingVenue::CashLedger
        {
            blockers.push(Blocker::CashInstrumentVenueMismatch);
        }
    } else if listing_venue == StockEtfListingVenue::CashLedger
        || primary_exchange == StockEtfListingVenue::CashLedger
    {
        blockers.push(Blocker::NonCashInstrumentVenueMismatch);
    }
}

fn valid_symbol(symbol: &str) -> bool {
    let trimmed = symbol.trim();
    !trimmed.is_empty()
        && trimmed == symbol
        && trimmed.len() <= 24
        && trimmed
            .chars()
            .all(|ch| ch.is_ascii_uppercase() || ch.is_ascii_digit() || matches!(ch, '.' | '-'))
}

fn hash(fill: char) -> String {
    fill.to_string().repeat(64)
}
