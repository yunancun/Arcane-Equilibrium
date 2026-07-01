//! ADR-0048 Stock/ETF paper-shadow reconciliation contract acceptance tests.
//!
//! These tests validate source-only reconciliation evidence shape. They must
//! not contact IBKR, inspect secrets, create connectors, import fills, generate
//! shadow fills, write reconciliation rows, write scorecards, apply DB changes,
//! route orders, or mutate Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    AssetLane, AuthorityScope, Broker, StockEtfPaperShadowReconciliationBlocker,
    StockEtfPaperShadowReconciliationV1, StockEtfPaperShadowReconciliationVerdict,
    STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID, STOCK_ETF_PAPER_SHADOW_RECONCILIATION_SCOPE,
};

#[test]
fn default_reconciliation_blocks_all_authority() {
    let verdict = StockEtfPaperShadowReconciliationV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::SourceVersionMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::WrongBroker
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ScopeMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::AuthorityScopeMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ReconciliationRunIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::AppendOnlyEventNotReady
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::PaperFillNotImported
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ShadowFillNotSynthetic
    ));
}

#[test]
fn accepted_reconciliation_validates_without_side_effects() {
    let reconciliation = StockEtfPaperShadowReconciliationV1::accepted_fixture();
    let verdict = reconciliation.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        reconciliation.contract_id,
        STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID
    );
    assert_eq!(reconciliation.source_version, 1);
    assert_eq!(reconciliation.asset_lane, AssetLane::StockEtfCash);
    assert_eq!(reconciliation.broker, Broker::Ibkr);
    assert_eq!(
        reconciliation.scope,
        STOCK_ETF_PAPER_SHADOW_RECONCILIATION_SCOPE
    );
    assert_eq!(reconciliation.authority_scope, AuthorityScope::ReadOnly);
    assert!(!reconciliation.effect_capable);
    assert!(reconciliation.append_only_event_ready);
    assert!(reconciliation.paper_fill_imported);
    assert!(reconciliation.shadow_fill_synthetic);
    assert!(reconciliation.divergence_bps <= reconciliation.divergence_threshold_bps);
    assert_eq!(reconciliation.unmatched_paper_fill_count, 0);
    assert_eq!(reconciliation.unmatched_shadow_fill_count, 0);
    assert!(!reconciliation.ibkr_contact_performed);
    assert!(!reconciliation.connector_runtime_started);
    assert!(!reconciliation.secret_content_serialized);
    assert!(!reconciliation.fill_import_performed);
    assert!(!reconciliation.shadow_fill_generated);
    assert!(!reconciliation.reconciliation_writer_started);
    assert!(!reconciliation.scorecard_writer_started);
    assert!(!reconciliation.db_apply_performed);
    assert!(!reconciliation.order_routed);
    assert!(!reconciliation.bybit_path_reused);
}

#[test]
fn reconciliation_rejects_scope_authority_and_effect_cross_wire() {
    let wrong_scope = StockEtfPaperShadowReconciliationV1 {
        scope: "shadow_signal".to_string(),
        authority_scope: AuthorityScope::ReadOnly,
        effect_capable: false,
        ..StockEtfPaperShadowReconciliationV1::accepted_fixture()
    };
    let verdict = wrong_scope.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ScopeMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::AuthorityScopeMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::EffectCapabilityPresent
    ));

    let wrong_authority = StockEtfPaperShadowReconciliationV1 {
        scope: STOCK_ETF_PAPER_SHADOW_RECONCILIATION_SCOPE.to_string(),
        authority_scope: AuthorityScope::ShadowOnly,
        effect_capable: false,
        ..StockEtfPaperShadowReconciliationV1::accepted_fixture()
    };
    let verdict = wrong_authority.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::AuthorityScopeMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ScopeMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::EffectCapabilityPresent
    ));

    let paper_write_pollution = StockEtfPaperShadowReconciliationV1 {
        scope: "paper_order".to_string(),
        authority_scope: AuthorityScope::PaperRehearsal,
        effect_capable: true,
        ..StockEtfPaperShadowReconciliationV1::accepted_fixture()
    };
    let verdict = paper_write_pollution.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ScopeMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::AuthorityScopeMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::EffectCapabilityPresent
    ));

    let shadow_only_pollution = StockEtfPaperShadowReconciliationV1 {
        scope: "shadow_signal".to_string(),
        authority_scope: AuthorityScope::ShadowOnly,
        effect_capable: false,
        ..StockEtfPaperShadowReconciliationV1::accepted_fixture()
    };
    let verdict = shadow_only_pollution.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ScopeMismatch
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::AuthorityScopeMismatch
    ));
    assert!(!has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::EffectCapabilityPresent
    ));
}

#[test]
fn reconciliation_requires_ids_and_lineage_hashes() {
    let bad = StockEtfPaperShadowReconciliationV1 {
        reconciliation_run_id: String::new(),
        paper_order_local_id: String::new(),
        broker_order_id: String::new(),
        execution_id: String::new(),
        commission_report_id: String::new(),
        shadow_signal_id: String::new(),
        lifecycle_contract_hash: "not_hash".to_string(),
        event_log_contract_hash: String::new(),
        paper_fill_import_request_hash: String::new(),
        shadow_signal_request_hash: String::new(),
        shadow_fill_model_hash: String::new(),
        cost_model_version_hash: String::new(),
        market_data_provenance_hash: String::new(),
        paper_shadow_divergence_threshold_hash: String::new(),
        paper_shadow_link_hash: String::new(),
        raw_artifact_hash: String::new(),
        redacted_summary_hash: String::new(),
        source_artifact_hash: String::new(),
        ..StockEtfPaperShadowReconciliationV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ReconciliationRunIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::PaperOrderLocalIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::BrokerOrderIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ExecutionIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::CommissionReportIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ShadowSignalIdMissing
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::LifecycleContractHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::EventLogContractHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::PaperFillImportRequestHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ShadowSignalRequestHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ShadowFillModelHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::CostModelVersionHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::MarketDataProvenanceHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::PaperShadowDivergenceThresholdHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::PaperShadowLinkHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::RawArtifactHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::RedactedSummaryHashInvalid
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::SourceArtifactHashInvalid
    ));
}

#[test]
fn reconciliation_rejects_unmatched_divergent_or_side_effecting_evidence() {
    let bad = StockEtfPaperShadowReconciliationV1 {
        append_only_event_ready: false,
        paper_fill_imported: false,
        shadow_fill_synthetic: false,
        divergence_bps: 125,
        divergence_threshold_bps: 100,
        unmatched_paper_fill_count: 1,
        unmatched_shadow_fill_count: 2,
        ibkr_contact_performed: true,
        connector_runtime_started: true,
        secret_content_serialized: true,
        fill_import_performed: true,
        shadow_fill_generated: true,
        reconciliation_writer_started: true,
        scorecard_writer_started: true,
        db_apply_performed: true,
        order_routed: true,
        bybit_path_reused: true,
        live_or_tiny_live_authorized: true,
        margin_short_options_cfd_requested: true,
        python_direct_broker_write_requested: true,
        ..StockEtfPaperShadowReconciliationV1::accepted_fixture()
    };
    let verdict = bad.validate();

    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::AppendOnlyEventNotReady
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::PaperFillNotImported
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ShadowFillNotSynthetic
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::DivergenceExceedsThreshold
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::UnmatchedPaperFillPresent
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::UnmatchedShadowFillPresent
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::IbkrContactPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ConnectorRuntimeStarted
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::SecretContentSerialized
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::FillImportPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ShadowFillGenerated
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ReconciliationWriterStarted
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::ScorecardWriterStarted
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::DbApplyPerformed
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::OrderRouted
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::BybitPathReused
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::LiveOrTinyLiveAuthorized
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::MarginShortOptionsCfdRequested
    ));
    assert!(has(
        &verdict,
        StockEtfPaperShadowReconciliationBlocker::PythonDirectBrokerWriteRequested
    ));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_paper_shadow_reconciliation.template.toml"),
    )
    .expect("read paper-shadow reconciliation template");
    let parsed: StockEtfPaperShadowReconciliationV1 =
        toml::from_str(&raw).expect("paper-shadow reconciliation template parses");

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
    assert_eq!(parsed.asset_lane, AssetLane::CryptoPerp);
    assert_eq!(parsed.broker, Broker::Bybit);
    assert_eq!(parsed.authority_scope, AuthorityScope::Denied);
    assert!(!parsed.validate().accepted);
    assert!(!parsed.ibkr_contact_performed);
    assert!(!parsed.connector_runtime_started);
    assert!(!parsed.secret_content_serialized);
    assert!(!parsed.fill_import_performed);
    assert!(!parsed.shadow_fill_generated);
    assert!(!parsed.reconciliation_writer_started);
    assert!(!parsed.scorecard_writer_started);
    assert!(!parsed.db_apply_performed);
    assert!(!parsed.order_routed);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(
    verdict: &StockEtfPaperShadowReconciliationVerdict,
    blocker: StockEtfPaperShadowReconciliationBlocker,
) -> bool {
    verdict.blockers.contains(&blocker)
}
