//! ADR-0048 Phase 0 named contract packet manifest acceptance tests.
//!
//! These tests validate the machine-readable manifest only. They must not
//! contact IBKR, inspect secrets, create connectors, apply migrations, start an
//! evidence clock, route orders, or mutate Bybit behavior.

use std::path::PathBuf;

use openclaw_types::{
    required_phase0_contract_ids, StockEtfPhase0ApiBaselineV1,
    StockEtfPhase0ContractPacketManifestV1, StockEtfPhase0GlobalDenialsV1,
    StockEtfPhase0ManifestBlocker, StockEtfPhase0UnlockTableV1,
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID,
    STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID, STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
    STOCK_ETF_DB_EVIDENCE_CONTRACT_ID, STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID,
    STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID, STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID,
    STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID, STOCK_ETF_PHASE0_MANIFEST_SCHEMA,
    STOCK_ETF_PHASE0_MANIFEST_STATUS, STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
    STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID, STOCK_ETF_RISK_POLICY_CONTRACT_ID,
    STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID, STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
    STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID, STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
};

#[test]
fn default_manifest_blocks_phase0_acceptance() {
    let manifest = StockEtfPhase0ContractPacketManifestV1::default();
    let verdict = manifest.validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict.blockers,
        StockEtfPhase0ManifestBlocker::SchemaMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPhase0ManifestBlocker::StatusMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPhase0ManifestBlocker::WrongAssetLane
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPhase0ManifestBlocker::WrongBroker
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPhase0ManifestBlocker::GlobalDenialMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPhase0ManifestBlocker::ContractMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfPhase0ManifestBlocker::Phase2ContactNotBlocked
    ));
}

#[test]
fn accepted_fixture_validates_phase0_packet_without_runtime_authority() {
    let manifest = StockEtfPhase0ContractPacketManifestV1::accepted_fixture();
    let verdict = manifest.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(manifest.schema, STOCK_ETF_PHASE0_MANIFEST_SCHEMA);
    assert_eq!(manifest.status, STOCK_ETF_PHASE0_MANIFEST_STATUS);
    assert!(manifest.api_baseline.live_ports_denied);
    assert!(!manifest.api_baseline.ibkr_call_performed);
    assert!(manifest.global_denials.ibkr_live);
    assert!(manifest.global_denials.tiny_live);
    assert!(manifest.global_denials.python_broker_write_authority);
    assert!(manifest.global_denials.gui_lane_authority);
    assert!(manifest.global_denials.automatic_promotion);
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_RISK_POLICY_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_SHADOW_FILL_MODEL_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_DB_EVIDENCE_CONTRACT_ID.to_string()));
    assert!(manifest
        .contracts
        .contains(&STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID.to_string()));
}

#[test]
fn repository_manifest_json_matches_source_contract() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(srv_root.join(
        "docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.manifest.json",
    ))
    .expect("read phase0 manifest");
    let parsed: StockEtfPhase0ContractPacketManifestV1 =
        serde_json::from_str(&raw).expect("phase0 manifest parses");
    let verdict = parsed.validate();

    assert!(
        verdict.accepted,
        "repository manifest blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(parsed.contracts.len(), required_phase0_contract_ids().len());
}

#[test]
fn manifest_contracts_must_be_complete_unique_and_known() {
    let mut manifest = StockEtfPhase0ContractPacketManifestV1::accepted_fixture();
    manifest
        .contracts
        .retain(|contract| contract != "stock_etf_release_packet_v1");
    manifest
        .contracts
        .push(STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID.to_string());
    manifest
        .contracts
        .push("surprise_runtime_contract_v1".to_string());

    let blockers = manifest.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::ContractMissing
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::ContractDuplicated
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::ContractUnexpected
    ));
}

#[test]
fn api_baseline_rejects_non_loopback_live_ports_and_prior_contact() {
    let manifest = StockEtfPhase0ContractPacketManifestV1 {
        api_baseline: StockEtfPhase0ApiBaselineV1 {
            selected: "ib_web_api".to_string(),
            host_policy: "network_host_allowed".to_string(),
            paper_port_default_candidate: 7496,
            live_ports_denied: false,
            ibkr_call_performed: true,
        },
        ..StockEtfPhase0ContractPacketManifestV1::accepted_fixture()
    };
    let blockers = manifest.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::ApiBaselineSelectedMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::ApiBaselineHostPolicyMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::ApiBaselinePaperPortMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::ApiBaselineLivePortsNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::ApiBaselineIbkrCallAlreadyPerformed
    ));
}

#[test]
fn global_denials_and_phase_unlocks_must_remain_fail_closed() {
    let manifest = StockEtfPhase0ContractPacketManifestV1 {
        global_denials: StockEtfPhase0GlobalDenialsV1 {
            ibkr_live: false,
            python_broker_write_authority: false,
            automatic_promotion: false,
            ..StockEtfPhase0GlobalDenialsV1::accepted_fixture()
        },
        phase_unlock: StockEtfPhase0UnlockTableV1 {
            phase1_type_config_schema_ipc: "ALLOWED_NOW_WITHOUT_REVIEW".to_string(),
            phase2_ibkr_external_contact: "ALLOWED".to_string(),
            phase3_evidence_clock: "STARTED".to_string(),
            phase4_gui_runtime: "ENABLED".to_string(),
            phase5_paper_shadow_online: "ONLINE".to_string(),
            tiny_live_or_live: "AUTHORIZED".to_string(),
        },
        ..StockEtfPhase0ContractPacketManifestV1::accepted_fixture()
    };
    let blockers = manifest.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::GlobalDenialMissing
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::Phase1UnlockMismatch
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::Phase2ContactNotBlocked
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::Phase3EvidenceClockNotBlocked
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::Phase4GuiRuntimeNotBlocked
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::Phase5OnlineNotBlocked
    ));
    assert!(has(
        &blockers,
        StockEtfPhase0ManifestBlocker::TinyLiveOrLiveNotBlocked
    ));
}

fn has(blockers: &[StockEtfPhase0ManifestBlocker], blocker: StockEtfPhase0ManifestBlocker) -> bool {
    blockers.contains(&blocker)
}
