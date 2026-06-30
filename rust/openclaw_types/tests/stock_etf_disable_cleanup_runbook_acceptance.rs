//! ADR-0048 Stock/ETF kill-switch and disable-cleanup acceptance tests.
//!
//! These tests validate a source-only runbook contract. They must not stop
//! services, inspect secrets, mutate DB state, contact IBKR, route paper orders,
//! or change Bybit live behavior.

use std::path::PathBuf;

use openclaw_types::{
    StockEtfDisableCleanupBlocker, StockEtfDisableCleanupEnvFlagV1,
    StockEtfDisableCleanupProofKind, StockEtfDisableCleanupProofV1,
    StockEtfDisableCleanupRunbookV1, STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID,
};

#[test]
fn default_runbook_blocks_cleanup_acceptance() {
    let runbook = StockEtfDisableCleanupRunbookV1::default();
    let verdict = runbook.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict.blockers,
        StockEtfDisableCleanupBlocker::RunbookIdMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfDisableCleanupBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfDisableCleanupBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfDisableCleanupBlocker::WrongBroker
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfDisableCleanupBlocker::SourceArtifactHashInvalid
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfDisableCleanupBlocker::BybitLiveExecutionNotProtected
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfDisableCleanupBlocker::EnvFlagMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfDisableCleanupBlocker::ProofMissing
    ));
}

#[test]
fn accepted_fixture_validates_required_disable_cleanup_contract() {
    let runbook = StockEtfDisableCleanupRunbookV1::accepted_fixture();
    let verdict = runbook.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(runbook.runbook_id, STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID);
    assert_eq!(runbook.source_version, 1);
    assert!(runbook.bybit_live_execution_unchanged);
    assert!(!runbook.ibkr_contact_performed);
    assert!(!runbook.connector_runtime_started);
    assert!(!runbook.paper_order_routed);
    assert!(!runbook.secret_slot_created);
    assert!(!runbook.secret_content_serialized);
    assert!(!runbook.paper_shadow_launch_authorized);
    assert!(!runbook.tiny_live_authorized);
    assert!(!runbook.live_authorized);
}

#[test]
fn runbook_requires_exact_id_and_source_version() {
    let mut runbook = StockEtfDisableCleanupRunbookV1::accepted_fixture();
    runbook.runbook_id = "stock_etf_kill_switch_and_disable_cleanup_runbook_v1_fixture".to_string();
    runbook.source_version = 2;

    let blockers = runbook.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::RunbookIdMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::SourceVersionMismatch
    ));
}

#[test]
fn env_flags_must_be_exact_disable_values_with_evidence_hashes() {
    let mut runbook = StockEtfDisableCleanupRunbookV1::accepted_fixture();
    runbook.env_flags.retain(|flag| {
        flag.name != "OPENCLAW_IBKR_PAPER_ENABLED" && flag.name != "OPENCLAW_STOCK_ETF_SHADOW_ONLY"
    });
    runbook.env_flags.push(StockEtfDisableCleanupEnvFlagV1 {
        name: "OPENCLAW_STOCK_ETF_SHADOW_ONLY".to_string(),
        expected_value: "0".to_string(),
        observed_value: "0".to_string(),
        evidence_hash: "bad".to_string(),
    });
    runbook.env_flags.push(StockEtfDisableCleanupEnvFlagV1 {
        name: "OPENCLAW_STOCK_ETF_SHADOW_ONLY".to_string(),
        expected_value: "1".to_string(),
        observed_value: "1".to_string(),
        evidence_hash: "a".repeat(64),
    });
    runbook.env_flags.push(StockEtfDisableCleanupEnvFlagV1 {
        name: "OPENCLAW_IBKR_LIVE_ENABLED".to_string(),
        expected_value: "0".to_string(),
        observed_value: "0".to_string(),
        evidence_hash: "b".repeat(64),
    });

    let blockers = runbook.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::EnvFlagMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::EnvFlagDuplicated
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::EnvFlagExpectedValueMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::EnvFlagObservedValueMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::EnvFlagEvidenceHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::EnvFlagUnexpected
    ));
}

#[test]
fn proofs_must_cover_required_actions_without_authority_or_destructive_claims() {
    let mut runbook = StockEtfDisableCleanupRunbookV1::accepted_fixture();
    runbook
        .proofs
        .retain(|proof| proof.kind != StockEtfDisableCleanupProofKind::LiveSecretAbsenceProven);
    runbook.proofs.push(StockEtfDisableCleanupProofV1 {
        kind: StockEtfDisableCleanupProofKind::CollectorStopped,
        verified: false,
        evidence_hash: "not-a-hash".to_string(),
        grants_runtime_authority: true,
        destructive_cleanup_claimed: true,
    });

    let blockers = runbook.validate().blockers;

    assert!(has(&blockers, StockEtfDisableCleanupBlocker::ProofMissing));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::ProofDuplicated
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::ProofNotVerified
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::ProofEvidenceHashInvalid
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::ProofGrantsRuntimeAuthority
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::ProofDestructiveCleanupClaimed
    ));
}

#[test]
fn runbook_rejects_contact_secret_destructive_cleanup_and_launch_claims() {
    let runbook = StockEtfDisableCleanupRunbookV1 {
        bybit_live_execution_unchanged: false,
        ibkr_contact_performed: true,
        connector_runtime_started: true,
        paper_order_routed: true,
        secret_slot_created: true,
        secret_content_serialized: true,
        destructive_db_cleanup_requested: true,
        db_delete_or_truncate_allowed: true,
        paper_shadow_launch_authorized: true,
        tiny_live_authorized: true,
        live_authorized: true,
        ..StockEtfDisableCleanupRunbookV1::accepted_fixture()
    };
    let blockers = runbook.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::BybitLiveExecutionNotProtected
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::PaperOrderRouted
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::SecretSlotCreated
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::SecretContentSerialized
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::DestructiveDbCleanupRequested
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::DbDeleteOrTruncateAllowed
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::PaperShadowLaunchAuthorityClaimed
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::TinyLiveAuthorityClaimed
    ));
    assert!(has(
        &blockers,
        StockEtfDisableCleanupBlocker::LiveAuthorityClaimed
    ));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_disable_cleanup_runbook.template.toml"),
    )
    .expect("read disable cleanup runbook template");
    let parsed: toml::Value = toml::from_str(&raw).expect("disable cleanup template parses");

    assert_eq!(parsed["runbook"]["runbook_id"].as_str(), Some(""));
    assert_eq!(parsed["runbook"]["source_version"].as_integer(), Some(0));
    assert_eq!(
        parsed["runbook"]["asset_lane"].as_str(),
        Some("crypto_perp")
    );
    assert_eq!(parsed["runbook"]["broker"].as_str(), Some("bybit"));
    assert_eq!(
        parsed["runbook"]["bybit_live_execution_unchanged"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["runbook"]["paper_shadow_launch_authorized"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["runbook"]["tiny_live_authorized"].as_bool(),
        Some(false)
    );
    assert_eq!(parsed["runbook"]["live_authorized"].as_bool(), Some(false));

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(blockers: &[StockEtfDisableCleanupBlocker], blocker: StockEtfDisableCleanupBlocker) -> bool {
    blockers.contains(&blocker)
}
