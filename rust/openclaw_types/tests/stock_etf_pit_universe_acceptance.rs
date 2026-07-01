//! ADR-0048 Stock/ETF PIT universe acceptance tests.
//!
//! These tests validate source-only universe membership contracts. They must
//! not contact IBKR, inspect secrets, create connectors, collect market data,
//! route orders, write scorecards, or mutate Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, Broker, InstrumentKind, StockEtfCurrency, StockEtfListingVenue,
    StockEtfPitUniverseBlocker, StockEtfPitUniverseConstituentV1, StockEtfPitUniverseV1,
    StockEtfPriipsKidStatus, StockEtfTradabilityStatus, STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
};

#[test]
fn default_pit_universe_blocks_before_evidence_clock_can_use_universe_hash() {
    let universe = StockEtfPitUniverseV1::default();
    let verdict = universe.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict.blockers,
        StockEtfPitUniverseBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPitUniverseBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPitUniverseBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPitUniverseBlocker::WrongBroker
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPitUniverseBlocker::UniverseHashInvalid
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPitUniverseBlocker::ConstituentCountMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPitUniverseBlocker::UniverseNotFrozenForEvidenceClock
    ));
}

#[test]
fn accepted_fixture_is_frozen_pit_universe_without_runtime_authority() {
    let universe = StockEtfPitUniverseV1::accepted_fixture();
    let verdict = universe.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(universe.contract_id, STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID);
    assert_eq!(universe.source_version, 1);
    assert_eq!(universe.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(universe.broker, Broker::Ibkr);
    assert_eq!(
        universe.constituent_count as usize,
        universe.constituents.len()
    );
    assert!(universe.frozen_for_evidence_clock);
    assert!(universe.survivorship_bias_controls_present);
    assert!(universe.bybit_live_execution_unchanged);
    assert!(universe.ibkr_live_denied);
    assert!(!universe.ibkr_contact_performed);
    assert!(!universe.secret_content_serialized);
}

#[test]
fn pit_universe_requires_exact_contract_id_and_source_version() {
    let universe = StockEtfPitUniverseV1 {
        contract_id: "stock_etf_pit_universe_contract_v1_fixture".to_string(),
        source_version: 2,
        ..StockEtfPitUniverseV1::accepted_fixture()
    };
    let blockers = universe.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ContractIdMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::SourceVersionMismatch
    ));
}

#[test]
fn pit_universe_rejects_identity_and_window_regressions() {
    let universe = StockEtfPitUniverseV1 {
        contract_id: "wrong".to_string(),
        asset_lane: AssetLane::CryptoPerp,
        broker: Broker::Bybit,
        universe_id: "bad id".to_string(),
        universe_version: "bad version".to_string(),
        universe_hash: "not-a-hash".to_string(),
        point_in_time_asof_ms: 0,
        effective_from_ms: 10,
        effective_to_ms: 10,
        ..StockEtfPitUniverseV1::accepted_fixture()
    };
    let blockers = universe.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ContractIdMismatch
    ));
    assert!(has(&blockers, StockEtfPitUniverseBlocker::WrongAssetLane));
    assert!(has(&blockers, StockEtfPitUniverseBlocker::WrongBroker));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::UniverseIdInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::UniverseVersionInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::UniverseHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::PointInTimeAsofMissing
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::EffectiveWindowInvalid
    ));
}

#[test]
fn pit_universe_rejects_bad_constituents_and_count_shape() {
    let bad_constituent = StockEtfPitUniverseConstituentV1 {
        symbol: "spy us".to_string(),
        instrument_kind: InstrumentKind::Cash,
        instrument_identity_hash: String::new(),
        listing_venue: StockEtfListingVenue::CashLedger,
        primary_exchange: StockEtfListingVenue::UnknownDenied,
        currency: StockEtfCurrency::UnknownDenied,
        tradability_status: StockEtfTradabilityStatus::Halted,
        priips_kid_status: StockEtfPriipsKidStatus::MissingBlocked,
        included: false,
        exclusion_reason: "liquidity_screen_failed".to_string(),
    };
    let universe = StockEtfPitUniverseV1 {
        constituent_count: 2,
        max_constituents: 1,
        constituents: vec![bad_constituent],
        ..StockEtfPitUniverseV1::accepted_fixture()
    };
    let blockers = universe.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ConstituentCountMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::MaxConstituentsInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ConstituentSymbolInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ConstituentKindDenied
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ConstituentIdentityHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ConstituentVenueDenied
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ConstituentCashVenueDenied
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ConstituentCurrencyDenied
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ConstituentNotTradable
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ConstituentPriipsBlocked
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::ConstituentNotIncluded
    ));
}

#[test]
fn pit_universe_rejects_missing_rule_hashes_survivorship_and_boundaries() {
    let universe = StockEtfPitUniverseV1 {
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
        ibkr_contact_performed: true,
        secret_content_serialized: true,
        ..StockEtfPitUniverseV1::accepted_fixture()
    };
    let blockers = universe.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::InclusionRuleHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::LiquidityScreenHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::DelistedInactivePolicyHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::CorporateActionVersionHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::UniverseNotFrozenForEvidenceClock
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::SurvivorshipControlsMissing
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::BybitLiveExecutionNotProtected
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::IbkrLiveNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &blockers,
        StockEtfPitUniverseBlocker::SecretContentSerialized
    ));
}

#[test]
fn pit_universe_rejects_freeze_survivorship_and_authority_cross_wire_independently() {
    let mut freeze = StockEtfPitUniverseV1::accepted_fixture();
    freeze.frozen_for_evidence_clock = false;
    assert_single_blocker(
        freeze,
        StockEtfPitUniverseBlocker::UniverseNotFrozenForEvidenceClock,
    );

    let mut survivorship = StockEtfPitUniverseV1::accepted_fixture();
    survivorship.survivorship_bias_controls_present = false;
    assert_single_blocker(
        survivorship,
        StockEtfPitUniverseBlocker::SurvivorshipControlsMissing,
    );

    let mut bybit = StockEtfPitUniverseV1::accepted_fixture();
    bybit.bybit_live_execution_unchanged = false;
    assert_single_blocker(
        bybit,
        StockEtfPitUniverseBlocker::BybitLiveExecutionNotProtected,
    );

    let mut ibkr_live = StockEtfPitUniverseV1::accepted_fixture();
    ibkr_live.ibkr_live_denied = false;
    assert_single_blocker(ibkr_live, StockEtfPitUniverseBlocker::IbkrLiveNotDenied);

    let mut ibkr_contact = StockEtfPitUniverseV1::accepted_fixture();
    ibkr_contact.ibkr_contact_performed = true;
    assert_single_blocker(
        ibkr_contact,
        StockEtfPitUniverseBlocker::IbkrContactPerformed,
    );

    let mut secret = StockEtfPitUniverseV1::accepted_fixture();
    secret.secret_content_serialized = true;
    assert_single_blocker(secret, StockEtfPitUniverseBlocker::SecretContentSerialized);
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_pit_universe.template.toml"),
    )
    .expect("read PIT universe template");
    let parsed: StockEtfPitUniverseV1 = toml::from_str(&raw).expect("PIT universe template parses");

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert!(parsed.constituents.is_empty());
    assert!(!parsed.validate().accepted);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.secret_content_serialized);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(blockers: &[StockEtfPitUniverseBlocker], blocker: StockEtfPitUniverseBlocker) -> bool {
    blockers.contains(&blocker)
}

fn assert_single_blocker(universe: StockEtfPitUniverseV1, blocker: StockEtfPitUniverseBlocker) {
    let verdict = universe.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
