//! ADR-0048 Stock/ETF asset-lane audit event acceptance tests.
//!
//! These tests validate immutable event-reference shape only. They do not write
//! audit rows, contact IBKR, read secrets, apply migrations, or grant authority.

use std::path::PathBuf;

use openclaw_types::{
    BrokerEnvironment, StockEtfAssetLaneEventBlocker, StockEtfAssetLaneEventKind,
    StockEtfAssetLaneEventV1, StockEtfDenialReason,
};

#[test]
fn default_asset_lane_event_is_blocked() {
    let verdict = StockEtfAssetLaneEventV1::default().validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::EventIdMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::EventKindUnknown));
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::SequenceNumberMissing));
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::DenialReasonMissingOnDeniedEvent));
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::PayloadHashInvalid));
}

#[test]
fn genesis_asset_lane_event_allows_empty_previous_hash_only_for_sequence_one() {
    let event = StockEtfAssetLaneEventV1::accepted_genesis_fixture();
    let verdict = event.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert!(event.genesis_event);
    assert_eq!(event.sequence_number, 1);
    assert!(event.previous_event_hash.is_empty());
}

#[test]
fn chained_asset_lane_event_requires_previous_hash() {
    let event = StockEtfAssetLaneEventV1::accepted_chained_fixture();
    assert!(event.validate().accepted);

    let mut missing_previous = event;
    missing_previous.previous_event_hash.clear();
    let verdict = missing_previous.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::PreviousEventHashInvalid));
}

#[test]
fn invalid_genesis_sequence_or_previous_hash_is_rejected() {
    let mut event = StockEtfAssetLaneEventV1::accepted_genesis_fixture();
    event.sequence_number = 2;
    event.previous_event_hash = "a".repeat(64);

    let verdict = event.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::GenesisSequenceInvalid));
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::GenesisPreviousHashPresent));
}

#[test]
fn allowed_and_denied_events_have_opposite_denial_reason_rules() {
    let mut allowed = StockEtfAssetLaneEventV1::accepted_chained_fixture();
    allowed.denial_reason = Some(StockEtfDenialReason::LaneDisabled);
    let allowed_verdict = allowed.validate();
    assert!(!allowed_verdict.accepted);
    assert!(allowed_verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::DenialReasonPresentOnAllowedEvent));

    let mut denied = StockEtfAssetLaneEventV1::accepted_chained_fixture();
    denied.allowed = false;
    denied.denial_reason = None;
    let denied_verdict = denied.validate();
    assert!(!denied_verdict.accepted);
    assert!(denied_verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::DenialReasonMissingOnDeniedEvent));
}

#[test]
fn live_secret_or_inline_raw_payload_is_rejected() {
    let mut event = StockEtfAssetLaneEventV1::accepted_chained_fixture();
    event.environment = BrokerEnvironment::LiveReservedDenied;
    event.secret_content_serialized = true;
    event.raw_payload_inlined = true;

    let verdict = event.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::LiveEnvironmentDenied));
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::SecretContentSerialized));
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::RawPayloadInlined));
}

#[test]
fn unknown_event_kind_and_bad_input_hashes_are_rejected() {
    let mut event = StockEtfAssetLaneEventV1::accepted_chained_fixture();
    event.event_kind = StockEtfAssetLaneEventKind::Unknown;
    event.input_artifact_hashes = vec!["bad-hash".to_string()];

    let verdict = event.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::EventKindUnknown));
    assert!(verdict
        .blockers
        .contains(&StockEtfAssetLaneEventBlocker::InputArtifactHashInvalid));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_asset_lane_events.template.toml"),
    )
    .expect("read asset-lane event template");
    let parsed: StockEtfAssetLaneEventV1 =
        toml::from_str(&raw).expect("asset-lane event template parses");

    assert_eq!(parsed.event_kind, StockEtfAssetLaneEventKind::Unknown);
    assert!(!parsed.raw_payload_inlined);
    assert!(!parsed.secret_content_serialized);
    assert!(!parsed.validate().accepted);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}
