//! ADR-0048 Stock/ETF point-in-time universe contract.
//!
//! This source-only validator pins the universe membership evidence needed
//! before Phase 3 evidence-clock or scorecard inputs may rely on a universe
//! hash. It does not contact IBKR, inspect secrets, create connectors, collect
//! market data, route orders, write scorecards, or change Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_instrument_identity::{
    StockEtfCurrency, StockEtfListingVenue, StockEtfPriipsKidStatus, StockEtfTradabilityStatus,
};
use crate::stock_etf_lane::{AssetLane, Broker, InstrumentKind};

pub const STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID: &str = "stock_etf_pit_universe_contract_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPitUniverseV1 {
    pub contract_id: String,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub universe_id: String,
    pub universe_version: String,
    pub universe_hash: String,
    pub point_in_time_asof_ms: u64,
    pub effective_from_ms: u64,
    pub effective_to_ms: u64,
    pub constituent_count: u32,
    pub max_constituents: u32,
    pub constituents: Vec<StockEtfPitUniverseConstituentV1>,
    pub inclusion_rule_hash: String,
    pub exclusion_rule_hash: String,
    pub liquidity_screen_hash: String,
    pub tradability_screen_hash: String,
    pub priips_screen_hash: String,
    pub delisted_or_inactive_policy_hash: String,
    pub corporate_action_adjustment_version_hash: String,
    pub market_calendar_hash: String,
    pub source_artifact_hash: String,
    pub frozen_for_evidence_clock: bool,
    pub survivorship_bias_controls_present: bool,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_live_denied: bool,
    pub ibkr_contact_performed: bool,
    pub secret_content_serialized: bool,
}

impl Default for StockEtfPitUniverseV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            universe_id: String::new(),
            universe_version: String::new(),
            universe_hash: String::new(),
            point_in_time_asof_ms: 0,
            effective_from_ms: 0,
            effective_to_ms: 0,
            constituent_count: 0,
            max_constituents: 0,
            constituents: Vec::new(),
            inclusion_rule_hash: String::new(),
            exclusion_rule_hash: String::new(),
            liquidity_screen_hash: String::new(),
            tradability_screen_hash: String::new(),
            priips_screen_hash: String::new(),
            delisted_or_inactive_policy_hash: String::new(),
            corporate_action_adjustment_version_hash: String::new(),
            market_calendar_hash: String::new(),
            source_artifact_hash: String::new(),
            frozen_for_evidence_clock: false,
            survivorship_bias_controls_present: false,
            bybit_live_execution_unchanged: false,
            ibkr_live_denied: false,
            ibkr_contact_performed: false,
            secret_content_serialized: false,
        }
    }
}

impl StockEtfPitUniverseV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string(),
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            universe_id: "US_LARGE_100_V1".to_string(),
            universe_version: "US_LARGE_100_V1_20260301".to_string(),
            universe_hash: hash('1'),
            point_in_time_asof_ms: 1_772_236_800_000,
            effective_from_ms: 1_772_236_800_000,
            effective_to_ms: 1_774_828_800_000,
            constituent_count: 3,
            max_constituents: 100,
            constituents: vec![
                StockEtfPitUniverseConstituentV1::fixture("AMD"),
                StockEtfPitUniverseConstituentV1::fixture("MSFT"),
                StockEtfPitUniverseConstituentV1::fixture("SPY"),
            ],
            inclusion_rule_hash: hash('2'),
            exclusion_rule_hash: hash('3'),
            liquidity_screen_hash: hash('4'),
            tradability_screen_hash: hash('5'),
            priips_screen_hash: hash('6'),
            delisted_or_inactive_policy_hash: hash('7'),
            corporate_action_adjustment_version_hash: hash('8'),
            market_calendar_hash: hash('9'),
            source_artifact_hash: hash('a'),
            frozen_for_evidence_clock: true,
            survivorship_bias_controls_present: true,
            bybit_live_execution_unchanged: true,
            ibkr_live_denied: true,
            ibkr_contact_performed: false,
            secret_content_serialized: false,
        }
    }

    pub fn validate(&self) -> StockEtfPitUniverseVerdict<StockEtfPitUniverseBlocker> {
        use StockEtfPitUniverseBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if !valid_identifier(&self.universe_id) {
            blockers.push(Blocker::UniverseIdInvalid);
        }
        if !valid_identifier(&self.universe_version) {
            blockers.push(Blocker::UniverseVersionInvalid);
        }
        if !is_sha256_hex(&self.universe_hash) {
            blockers.push(Blocker::UniverseHashInvalid);
        }
        if self.point_in_time_asof_ms == 0 {
            blockers.push(Blocker::PointInTimeAsofMissing);
        }
        if self.effective_from_ms == 0 {
            blockers.push(Blocker::EffectiveFromMissing);
        }
        if self.effective_to_ms != 0 && self.effective_to_ms <= self.effective_from_ms {
            blockers.push(Blocker::EffectiveWindowInvalid);
        }
        if self.constituent_count == 0 || self.constituents.is_empty() {
            blockers.push(Blocker::ConstituentCountMissing);
        }
        if self.constituent_count as usize != self.constituents.len() {
            blockers.push(Blocker::ConstituentCountMismatch);
        }
        if self.max_constituents == 0 || self.constituent_count > self.max_constituents {
            blockers.push(Blocker::MaxConstituentsInvalid);
        }
        if self.max_constituents > 500 {
            blockers.push(Blocker::UniverseTooBroadForV1);
        }

        for constituent in &self.constituents {
            validate_constituent(constituent, &mut blockers);
        }

        validate_required_hashes(self, &mut blockers);

        if !self.frozen_for_evidence_clock {
            blockers.push(Blocker::UniverseNotFrozenForEvidenceClock);
        }
        if !self.survivorship_bias_controls_present {
            blockers.push(Blocker::SurvivorshipControlsMissing);
        }
        if !self.bybit_live_execution_unchanged {
            blockers.push(Blocker::BybitLiveExecutionNotProtected);
        }
        if !self.ibkr_live_denied {
            blockers.push(Blocker::IbkrLiveNotDenied);
        }
        if self.ibkr_contact_performed {
            blockers.push(Blocker::IbkrContactPerformed);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }

        StockEtfPitUniverseVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPitUniverseConstituentV1 {
    pub symbol: String,
    pub instrument_kind: InstrumentKind,
    pub instrument_identity_hash: String,
    pub listing_venue: StockEtfListingVenue,
    pub primary_exchange: StockEtfListingVenue,
    pub currency: StockEtfCurrency,
    pub tradability_status: StockEtfTradabilityStatus,
    pub priips_kid_status: StockEtfPriipsKidStatus,
    pub included: bool,
    pub exclusion_reason: String,
}

impl StockEtfPitUniverseConstituentV1 {
    pub fn fixture(symbol: &str) -> Self {
        Self {
            symbol: symbol.to_string(),
            instrument_kind: InstrumentKind::Stock,
            instrument_identity_hash: hash('b'),
            listing_venue: StockEtfListingVenue::Xnas,
            primary_exchange: StockEtfListingVenue::Xnas,
            currency: StockEtfCurrency::Usd,
            tradability_status: StockEtfTradabilityStatus::Tradable,
            priips_kid_status: StockEtfPriipsKidStatus::NotRequired,
            included: true,
            exclusion_reason: String::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPitUniverseVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfPitUniverseVerdict<B> {
    pub fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfPitUniverseBlocker {
    ContractIdMismatch,
    WrongAssetLane,
    WrongBroker,
    UniverseIdInvalid,
    UniverseVersionInvalid,
    UniverseHashInvalid,
    PointInTimeAsofMissing,
    EffectiveFromMissing,
    EffectiveWindowInvalid,
    ConstituentCountMissing,
    ConstituentCountMismatch,
    MaxConstituentsInvalid,
    UniverseTooBroadForV1,
    ConstituentSymbolInvalid,
    ConstituentKindDenied,
    ConstituentIdentityHashInvalid,
    ConstituentVenueDenied,
    ConstituentCashVenueDenied,
    ConstituentCurrencyDenied,
    ConstituentNotTradable,
    ConstituentPriipsBlocked,
    ConstituentNotIncluded,
    IncludedConstituentHasExclusionReason,
    InclusionRuleHashInvalid,
    ExclusionRuleHashInvalid,
    LiquidityScreenHashInvalid,
    TradabilityScreenHashInvalid,
    PriipsScreenHashInvalid,
    DelistedInactivePolicyHashInvalid,
    CorporateActionVersionHashInvalid,
    MarketCalendarHashInvalid,
    SourceArtifactHashInvalid,
    UniverseNotFrozenForEvidenceClock,
    SurvivorshipControlsMissing,
    BybitLiveExecutionNotProtected,
    IbkrLiveNotDenied,
    IbkrContactPerformed,
    SecretContentSerialized,
}

fn validate_constituent(
    constituent: &StockEtfPitUniverseConstituentV1,
    blockers: &mut Vec<StockEtfPitUniverseBlocker>,
) {
    use StockEtfPitUniverseBlocker as Blocker;

    if !valid_symbol(&constituent.symbol) {
        blockers.push(Blocker::ConstituentSymbolInvalid);
    }
    if !matches!(
        constituent.instrument_kind,
        InstrumentKind::Stock | InstrumentKind::Etf
    ) {
        blockers.push(Blocker::ConstituentKindDenied);
    }
    if !is_sha256_hex(&constituent.instrument_identity_hash) {
        blockers.push(Blocker::ConstituentIdentityHashInvalid);
    }
    if constituent.listing_venue == StockEtfListingVenue::UnknownDenied
        || constituent.primary_exchange == StockEtfListingVenue::UnknownDenied
    {
        blockers.push(Blocker::ConstituentVenueDenied);
    }
    if constituent.listing_venue == StockEtfListingVenue::CashLedger
        || constituent.primary_exchange == StockEtfListingVenue::CashLedger
    {
        blockers.push(Blocker::ConstituentCashVenueDenied);
    }
    if constituent.currency != StockEtfCurrency::Usd {
        blockers.push(Blocker::ConstituentCurrencyDenied);
    }
    if constituent.tradability_status != StockEtfTradabilityStatus::Tradable {
        blockers.push(Blocker::ConstituentNotTradable);
    }
    if matches!(
        constituent.priips_kid_status,
        StockEtfPriipsKidStatus::MissingBlocked | StockEtfPriipsKidStatus::UnknownDenied
    ) {
        blockers.push(Blocker::ConstituentPriipsBlocked);
    }
    if !constituent.included {
        blockers.push(Blocker::ConstituentNotIncluded);
    }
    if constituent.included && !constituent.exclusion_reason.trim().is_empty() {
        blockers.push(Blocker::IncludedConstituentHasExclusionReason);
    }
}

fn validate_required_hashes(
    universe: &StockEtfPitUniverseV1,
    blockers: &mut Vec<StockEtfPitUniverseBlocker>,
) {
    use StockEtfPitUniverseBlocker as Blocker;

    if !is_sha256_hex(&universe.inclusion_rule_hash) {
        blockers.push(Blocker::InclusionRuleHashInvalid);
    }
    if !is_sha256_hex(&universe.exclusion_rule_hash) {
        blockers.push(Blocker::ExclusionRuleHashInvalid);
    }
    if !is_sha256_hex(&universe.liquidity_screen_hash) {
        blockers.push(Blocker::LiquidityScreenHashInvalid);
    }
    if !is_sha256_hex(&universe.tradability_screen_hash) {
        blockers.push(Blocker::TradabilityScreenHashInvalid);
    }
    if !is_sha256_hex(&universe.priips_screen_hash) {
        blockers.push(Blocker::PriipsScreenHashInvalid);
    }
    if !is_sha256_hex(&universe.delisted_or_inactive_policy_hash) {
        blockers.push(Blocker::DelistedInactivePolicyHashInvalid);
    }
    if !is_sha256_hex(&universe.corporate_action_adjustment_version_hash) {
        blockers.push(Blocker::CorporateActionVersionHashInvalid);
    }
    if !is_sha256_hex(&universe.market_calendar_hash) {
        blockers.push(Blocker::MarketCalendarHashInvalid);
    }
    if !is_sha256_hex(&universe.source_artifact_hash) {
        blockers.push(Blocker::SourceArtifactHashInvalid);
    }
}

fn valid_identifier(value: &str) -> bool {
    let trimmed = value.trim();
    !trimmed.is_empty()
        && trimmed == value
        && trimmed.len() <= 64
        && trimmed
            .chars()
            .all(|ch| ch.is_ascii_uppercase() || ch.is_ascii_digit() || matches!(ch, '_' | '-'))
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
