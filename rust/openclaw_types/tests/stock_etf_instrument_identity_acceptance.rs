//! ADR-0048 Stock/ETF instrument identity acceptance tests.
//!
//! These tests validate source-only point-in-time identity contracts. They must
//! not contact IBKR, inspect secrets, create connectors, subscribe to market
//! data, route orders, or mutate Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    InstrumentKind, StockEtfCurrency, StockEtfInstrumentIdentityBlocker,
    StockEtfInstrumentIdentityV1, StockEtfListingVenue, StockEtfPriipsKidStatus,
    StockEtfTradabilityStatus, STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID,
};

#[test]
fn default_instrument_identity_blocks_before_contract_details_can_be_used() {
    let identity = StockEtfInstrumentIdentityV1::default();
    let verdict = identity.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            StockEtfInstrumentIdentityBlocker::ContractIdMismatch,
            StockEtfInstrumentIdentityBlocker::SourceVersionMismatch,
            StockEtfInstrumentIdentityBlocker::WrongAssetLane,
            StockEtfInstrumentIdentityBlocker::WrongBroker,
            StockEtfInstrumentIdentityBlocker::InstrumentKindDenied,
            StockEtfInstrumentIdentityBlocker::SymbolInvalid,
            StockEtfInstrumentIdentityBlocker::ListingVenueDenied,
            StockEtfInstrumentIdentityBlocker::PrimaryExchangeDenied,
            StockEtfInstrumentIdentityBlocker::CurrencyDenied,
            StockEtfInstrumentIdentityBlocker::TradabilityNotTradable,
            StockEtfInstrumentIdentityBlocker::PriipsKidBlocked,
            StockEtfInstrumentIdentityBlocker::FractionalPolicyMissing,
            StockEtfInstrumentIdentityBlocker::PointInTimeAsofMissing,
            StockEtfInstrumentIdentityBlocker::MarketCalendarIdMissing,
            StockEtfInstrumentIdentityBlocker::MarketCalendarHashInvalid,
            StockEtfInstrumentIdentityBlocker::BrokerContractDetailsHashInvalid,
            StockEtfInstrumentIdentityBlocker::InstrumentIdentityHashInvalid,
            StockEtfInstrumentIdentityBlocker::CorporateActionAdjustmentHashInvalid,
            StockEtfInstrumentIdentityBlocker::SourceArtifactHashInvalid,
            StockEtfInstrumentIdentityBlocker::BybitLiveExecutionNotProtected,
            StockEtfInstrumentIdentityBlocker::IbkrLiveNotDenied,
            StockEtfInstrumentIdentityBlocker::MarginShortNotDenied,
            StockEtfInstrumentIdentityBlocker::OptionsCfdNotDenied,
        ]
    );
}

#[test]
fn accepted_fixture_is_point_in_time_ibkr_stock_identity_without_runtime_authority() {
    let identity = StockEtfInstrumentIdentityV1::accepted_fixture();
    let verdict = identity.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        identity.contract_id,
        STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID
    );
    assert_eq!(identity.source_version, 1);
    assert_eq!(identity.symbol, "AMD");
    assert_eq!(identity.instrument_kind, InstrumentKind::Stock);
    assert!(identity.bybit_live_execution_unchanged);
    assert!(identity.ibkr_live_denied);
    assert!(identity.margin_short_denied);
    assert!(identity.options_cfd_denied);
    assert!(!identity.ibkr_contact_performed);
    assert!(!identity.secret_content_serialized);
}

#[test]
fn instrument_identity_requires_exact_contract_id_and_source_version() {
    let identity = StockEtfInstrumentIdentityV1 {
        contract_id: "instrument_identity_contract_v1_fixture".to_string(),
        source_version: 2,
        ..StockEtfInstrumentIdentityV1::accepted_fixture()
    };
    let blockers = identity.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            StockEtfInstrumentIdentityBlocker::ContractIdMismatch,
            StockEtfInstrumentIdentityBlocker::SourceVersionMismatch,
        ]
    );
}

#[test]
fn instrument_identity_rejects_wrong_kind_symbol_venue_and_currency() {
    let identity = StockEtfInstrumentIdentityV1 {
        instrument_kind: InstrumentKind::CfdReserved,
        symbol: "amd us".to_string(),
        listing_venue: StockEtfListingVenue::UnknownDenied,
        primary_exchange: StockEtfListingVenue::UnknownDenied,
        currency: StockEtfCurrency::UnknownDenied,
        ..StockEtfInstrumentIdentityV1::accepted_fixture()
    };
    let blockers = identity.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            StockEtfInstrumentIdentityBlocker::InstrumentKindDenied,
            StockEtfInstrumentIdentityBlocker::SymbolInvalid,
            StockEtfInstrumentIdentityBlocker::ListingVenueDenied,
            StockEtfInstrumentIdentityBlocker::PrimaryExchangeDenied,
            StockEtfInstrumentIdentityBlocker::CurrencyDenied,
        ]
    );
}

#[test]
fn cash_and_non_cash_venue_rules_are_separate() {
    let cash_wrong = StockEtfInstrumentIdentityV1 {
        instrument_kind: InstrumentKind::Cash,
        listing_venue: StockEtfListingVenue::Xnys,
        primary_exchange: StockEtfListingVenue::Xnys,
        symbol: "USD".to_string(),
        ..StockEtfInstrumentIdentityV1::accepted_fixture()
    };
    assert_single_blocker(
        cash_wrong,
        StockEtfInstrumentIdentityBlocker::CashInstrumentVenueMismatch,
    );

    let stock_wrong = StockEtfInstrumentIdentityV1 {
        listing_venue: StockEtfListingVenue::CashLedger,
        primary_exchange: StockEtfListingVenue::CashLedger,
        ..StockEtfInstrumentIdentityV1::accepted_fixture()
    };
    assert_single_blocker(
        stock_wrong,
        StockEtfInstrumentIdentityBlocker::NonCashInstrumentVenueMismatch,
    );
}

#[test]
fn instrument_identity_rejects_untradable_priips_missing_and_missing_hashes() {
    let identity = StockEtfInstrumentIdentityV1 {
        tradability_status: StockEtfTradabilityStatus::Halted,
        priips_kid_status: StockEtfPriipsKidStatus::MissingBlocked,
        fractional_policy_recorded: false,
        point_in_time_asof_ms: 0,
        market_calendar_id: String::new(),
        market_calendar_hash: "bad".to_string(),
        broker_contract_details_hash: String::new(),
        instrument_identity_hash: "z".repeat(64),
        corporate_action_adjustment_version_hash: String::new(),
        source_artifact_hash: String::new(),
        ..StockEtfInstrumentIdentityV1::accepted_fixture()
    };
    let blockers = identity.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            StockEtfInstrumentIdentityBlocker::TradabilityNotTradable,
            StockEtfInstrumentIdentityBlocker::PriipsKidBlocked,
            StockEtfInstrumentIdentityBlocker::FractionalPolicyMissing,
            StockEtfInstrumentIdentityBlocker::PointInTimeAsofMissing,
            StockEtfInstrumentIdentityBlocker::MarketCalendarIdMissing,
            StockEtfInstrumentIdentityBlocker::MarketCalendarHashInvalid,
            StockEtfInstrumentIdentityBlocker::BrokerContractDetailsHashInvalid,
            StockEtfInstrumentIdentityBlocker::InstrumentIdentityHashInvalid,
            StockEtfInstrumentIdentityBlocker::CorporateActionAdjustmentHashInvalid,
            StockEtfInstrumentIdentityBlocker::SourceArtifactHashInvalid,
        ]
    );
}

#[test]
fn instrument_identity_rejects_contact_secret_and_boundary_regressions() {
    let identity = StockEtfInstrumentIdentityV1 {
        bybit_live_execution_unchanged: false,
        ibkr_live_denied: false,
        margin_short_denied: false,
        options_cfd_denied: false,
        ibkr_contact_performed: true,
        secret_content_serialized: true,
        ..StockEtfInstrumentIdentityV1::accepted_fixture()
    };
    let blockers = identity.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            StockEtfInstrumentIdentityBlocker::BybitLiveExecutionNotProtected,
            StockEtfInstrumentIdentityBlocker::IbkrLiveNotDenied,
            StockEtfInstrumentIdentityBlocker::MarginShortNotDenied,
            StockEtfInstrumentIdentityBlocker::OptionsCfdNotDenied,
            StockEtfInstrumentIdentityBlocker::IbkrContactPerformed,
            StockEtfInstrumentIdentityBlocker::SecretContentSerialized,
        ]
    );
}

#[test]
fn instrument_identity_rejects_live_margin_secret_and_authority_cross_wire_independently() {
    let mut bybit = StockEtfInstrumentIdentityV1::accepted_fixture();
    bybit.bybit_live_execution_unchanged = false;
    assert_single_blocker(
        bybit,
        StockEtfInstrumentIdentityBlocker::BybitLiveExecutionNotProtected,
    );

    let mut ibkr_live = StockEtfInstrumentIdentityV1::accepted_fixture();
    ibkr_live.ibkr_live_denied = false;
    assert_single_blocker(
        ibkr_live,
        StockEtfInstrumentIdentityBlocker::IbkrLiveNotDenied,
    );

    let mut margin_short = StockEtfInstrumentIdentityV1::accepted_fixture();
    margin_short.margin_short_denied = false;
    assert_single_blocker(
        margin_short,
        StockEtfInstrumentIdentityBlocker::MarginShortNotDenied,
    );

    let mut options_cfd = StockEtfInstrumentIdentityV1::accepted_fixture();
    options_cfd.options_cfd_denied = false;
    assert_single_blocker(
        options_cfd,
        StockEtfInstrumentIdentityBlocker::OptionsCfdNotDenied,
    );

    let mut ibkr_contact = StockEtfInstrumentIdentityV1::accepted_fixture();
    ibkr_contact.ibkr_contact_performed = true;
    assert_single_blocker(
        ibkr_contact,
        StockEtfInstrumentIdentityBlocker::IbkrContactPerformed,
    );

    let mut secret = StockEtfInstrumentIdentityV1::accepted_fixture();
    secret.secret_content_serialized = true;
    assert_single_blocker(
        secret,
        StockEtfInstrumentIdentityBlocker::SecretContentSerialized,
    );
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_instrument_identity.template.toml"),
    )
    .expect("read instrument identity template");
    let parsed: toml::Value = toml::from_str(&raw).expect("instrument identity template parses");

    assert_eq!(parsed["identity"]["contract_id"].as_str(), Some(""));
    assert_eq!(parsed["identity"]["source_version"].as_integer(), Some(0));
    assert_eq!(
        parsed["identity"]["asset_lane"].as_str(),
        Some("crypto_perp")
    );
    assert_eq!(parsed["identity"]["broker"].as_str(), Some("bybit"));
    assert_eq!(
        parsed["identity"]["ibkr_contact_performed"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["identity"]["secret_content_serialized"].as_bool(),
        Some(false)
    );

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn assert_single_blocker(
    identity: StockEtfInstrumentIdentityV1,
    blocker: StockEtfInstrumentIdentityBlocker,
) {
    let verdict = identity.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
