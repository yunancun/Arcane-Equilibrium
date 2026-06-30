//! Stock/ETF Phase 0 named contract packet manifest validator.
//!
//! This source-only validator pins the machine-readable Phase 0 manifest for
//! ADR-0048. It does not read secrets, contact IBKR, create connectors, apply
//! migrations, start an evidence clock, route orders, or change Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::stock_etf_lane::{AssetLane, Broker};
use crate::stock_etf_scorecard_inputs::{
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID, STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID,
    STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
};

pub const STOCK_ETF_PHASE0_MANIFEST_SCHEMA: &str = "stock_etf_phase0_contract_packet_manifest_v1";
pub const STOCK_ETF_PHASE0_MANIFEST_STATUS: &str = "ACCEPTED_PHASE0_CONTRACT_NO_RUNTIME_AUTHORITY";
pub const STOCK_ETF_PHASE0_MANIFEST_SCOPE: &str = "paper_shadow_only";
pub const STOCK_ETF_PHASE0_GENERATED_AT: &str = "2026-06-29";
pub const STOCK_ETF_PHASE0_ADR_PATH: &str = "docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md";
pub const STOCK_ETF_PHASE0_AMD_PATH: &str =
    "docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md";
pub const STOCK_ETF_PHASE0_PACKET_PATH: &str =
    "docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.md";

const REQUIRED_CONTRACTS: &[&str] = &[
    "asset_lane_taxonomy_v1",
    "broker_capability_registry_v1",
    "phase2_ibkr_external_surface_gate_v1",
    "non_bybit_api_allowlist_v1",
    "instrument_identity_contract_v1",
    "stock_etf_pit_universe_contract_v1",
    "stock_etf_strategy_hypothesis_contract_v1",
    "stock_etf_risk_policy_v1",
    "stock_etf_reference_data_sources_v1",
    "ibkr_api_session_topology_v1",
    "ibkr_session_attestation_v1",
    "feature_flag_secret_auth_matrix_v1",
    "lane_scoped_ipc_v1",
    "ibkr_paper_order_lifecycle_v1",
    "broker_lifecycle_event_log_v1",
    "audit.asset_lane_events_v1",
    "stock_etf_db_evidence_ddl_v1",
    "stock_market_data_provenance_v1",
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID,
    STOCK_ETF_COST_MODEL_VERSION_CONTRACT_ID,
    STOCK_ETF_BENCHMARK_VERSIONS_CONTRACT_ID,
    STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
    "stock_etf_evidence_clock_v1",
    "gui_lane_contract_v1",
    STOCK_ETF_STORAGE_CAPACITY_CONTRACT_ID,
    "stock_etf_kill_switch_and_disable_cleanup_runbook_v1",
    "stock_etf_release_packet_v1",
    "tiny_live_adr_eligibility_v1",
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPhase0ContractPacketManifestV1 {
    pub schema: String,
    pub generated_at: String,
    pub status: String,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub scope: String,
    pub authority: StockEtfPhase0AuthorityV1,
    pub api_baseline: StockEtfPhase0ApiBaselineV1,
    pub global_denials: StockEtfPhase0GlobalDenialsV1,
    pub contracts: Vec<String>,
    pub phase_unlock: StockEtfPhase0UnlockTableV1,
}

impl Default for StockEtfPhase0ContractPacketManifestV1 {
    fn default() -> Self {
        Self {
            schema: String::new(),
            generated_at: String::new(),
            status: String::new(),
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            scope: String::new(),
            authority: StockEtfPhase0AuthorityV1::default(),
            api_baseline: StockEtfPhase0ApiBaselineV1::default(),
            global_denials: StockEtfPhase0GlobalDenialsV1::default(),
            contracts: Vec::new(),
            phase_unlock: StockEtfPhase0UnlockTableV1::default(),
        }
    }
}

impl StockEtfPhase0ContractPacketManifestV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            schema: STOCK_ETF_PHASE0_MANIFEST_SCHEMA.to_string(),
            generated_at: STOCK_ETF_PHASE0_GENERATED_AT.to_string(),
            status: STOCK_ETF_PHASE0_MANIFEST_STATUS.to_string(),
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            scope: STOCK_ETF_PHASE0_MANIFEST_SCOPE.to_string(),
            authority: StockEtfPhase0AuthorityV1::accepted_fixture(),
            api_baseline: StockEtfPhase0ApiBaselineV1::accepted_fixture(),
            global_denials: StockEtfPhase0GlobalDenialsV1::accepted_fixture(),
            contracts: REQUIRED_CONTRACTS
                .iter()
                .map(|contract| contract.to_string())
                .collect(),
            phase_unlock: StockEtfPhase0UnlockTableV1::accepted_fixture(),
        }
    }

    pub fn validate(&self) -> StockEtfPhase0ManifestVerdict<StockEtfPhase0ManifestBlocker> {
        use StockEtfPhase0ManifestBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.schema != STOCK_ETF_PHASE0_MANIFEST_SCHEMA {
            blockers.push(Blocker::SchemaMismatch);
        }
        if self.generated_at != STOCK_ETF_PHASE0_GENERATED_AT {
            blockers.push(Blocker::GeneratedAtMismatch);
        }
        if self.status != STOCK_ETF_PHASE0_MANIFEST_STATUS {
            blockers.push(Blocker::StatusMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if self.scope != STOCK_ETF_PHASE0_MANIFEST_SCOPE {
            blockers.push(Blocker::ScopeMismatch);
        }

        validate_authority(&self.authority, &mut blockers);
        validate_api_baseline(&self.api_baseline, &mut blockers);
        validate_global_denials(&self.global_denials, &mut blockers);
        validate_contracts(&self.contracts, &mut blockers);
        validate_phase_unlock(&self.phase_unlock, &mut blockers);

        StockEtfPhase0ManifestVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct StockEtfPhase0AuthorityV1 {
    pub adr: String,
    pub amd: String,
    pub contract_packet: String,
}

impl StockEtfPhase0AuthorityV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            adr: STOCK_ETF_PHASE0_ADR_PATH.to_string(),
            amd: STOCK_ETF_PHASE0_AMD_PATH.to_string(),
            contract_packet: STOCK_ETF_PHASE0_PACKET_PATH.to_string(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPhase0ApiBaselineV1 {
    pub selected: String,
    pub host_policy: String,
    pub paper_port_default_candidate: u16,
    pub live_ports_denied: bool,
    pub ibkr_call_performed: bool,
}

impl Default for StockEtfPhase0ApiBaselineV1 {
    fn default() -> Self {
        Self {
            selected: String::new(),
            host_policy: String::new(),
            paper_port_default_candidate: 0,
            live_ports_denied: false,
            ibkr_call_performed: false,
        }
    }
}

impl StockEtfPhase0ApiBaselineV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            selected: "ib_gateway_tws_api".to_string(),
            host_policy: "loopback_only".to_string(),
            paper_port_default_candidate: 4002,
            live_ports_denied: true,
            ibkr_call_performed: false,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct StockEtfPhase0GlobalDenialsV1 {
    pub ibkr_live: bool,
    pub tiny_live: bool,
    pub margin: bool,
    pub short: bool,
    pub options: bool,
    pub cfd: bool,
    pub transfer: bool,
    pub account_management_writes: bool,
    pub python_broker_write_authority: bool,
    pub gui_lane_authority: bool,
    pub automatic_promotion: bool,
}

impl StockEtfPhase0GlobalDenialsV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            ibkr_live: true,
            tiny_live: true,
            margin: true,
            short: true,
            options: true,
            cfd: true,
            transfer: true,
            account_management_writes: true,
            python_broker_write_authority: true,
            gui_lane_authority: true,
            automatic_promotion: true,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
pub struct StockEtfPhase0UnlockTableV1 {
    pub phase1_type_config_schema_ipc: String,
    pub phase2_ibkr_external_contact: String,
    pub phase3_evidence_clock: String,
    pub phase4_gui_runtime: String,
    pub phase5_paper_shadow_online: String,
    pub tiny_live_or_live: String,
}

impl StockEtfPhase0UnlockTableV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            phase1_type_config_schema_ipc: "ALLOWED_AFTER_THIS_PACKET_WITH_E2_E4_QA".to_string(),
            phase2_ibkr_external_contact: "BLOCKED_UNTIL_PHASE2_EXTERNAL_SURFACE_GATE_PASS"
                .to_string(),
            phase3_evidence_clock: "BLOCKED_UNTIL_DATA_PROVENANCE_EVIDENCE_CONTRACTS_PASS"
                .to_string(),
            phase4_gui_runtime: "BLOCKED_UNTIL_ROUTE_CACHE_AUTH_NEGATIVE_TESTS_PASS".to_string(),
            phase5_paper_shadow_online: "BLOCKED_UNTIL_RELEASE_PACKET_AND_SHAKEDOWN_PASS"
                .to_string(),
            tiny_live_or_live: "BLOCKED_REQUIRES_FUTURE_ADR".to_string(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPhase0ManifestVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfPhase0ManifestVerdict<B> {
    pub fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfPhase0ManifestBlocker {
    SchemaMismatch,
    GeneratedAtMismatch,
    StatusMismatch,
    WrongAssetLane,
    WrongBroker,
    ScopeMismatch,
    AdrPathMismatch,
    AmdPathMismatch,
    ContractPacketPathMismatch,
    ApiBaselineSelectedMismatch,
    ApiBaselineHostPolicyMismatch,
    ApiBaselinePaperPortMismatch,
    ApiBaselineLivePortsNotDenied,
    ApiBaselineIbkrCallAlreadyPerformed,
    GlobalDenialMissing,
    ContractMissing,
    ContractDuplicated,
    ContractUnexpected,
    Phase1UnlockMismatch,
    Phase2ContactNotBlocked,
    Phase3EvidenceClockNotBlocked,
    Phase4GuiRuntimeNotBlocked,
    Phase5OnlineNotBlocked,
    TinyLiveOrLiveNotBlocked,
}

pub fn required_phase0_contract_ids() -> &'static [&'static str] {
    REQUIRED_CONTRACTS
}

fn validate_authority(
    authority: &StockEtfPhase0AuthorityV1,
    blockers: &mut Vec<StockEtfPhase0ManifestBlocker>,
) {
    use StockEtfPhase0ManifestBlocker as Blocker;

    if authority.adr != STOCK_ETF_PHASE0_ADR_PATH {
        blockers.push(Blocker::AdrPathMismatch);
    }
    if authority.amd != STOCK_ETF_PHASE0_AMD_PATH {
        blockers.push(Blocker::AmdPathMismatch);
    }
    if authority.contract_packet != STOCK_ETF_PHASE0_PACKET_PATH {
        blockers.push(Blocker::ContractPacketPathMismatch);
    }
}

fn validate_api_baseline(
    baseline: &StockEtfPhase0ApiBaselineV1,
    blockers: &mut Vec<StockEtfPhase0ManifestBlocker>,
) {
    use StockEtfPhase0ManifestBlocker as Blocker;

    if baseline.selected != "ib_gateway_tws_api" {
        blockers.push(Blocker::ApiBaselineSelectedMismatch);
    }
    if baseline.host_policy != "loopback_only" {
        blockers.push(Blocker::ApiBaselineHostPolicyMismatch);
    }
    if baseline.paper_port_default_candidate != 4002 {
        blockers.push(Blocker::ApiBaselinePaperPortMismatch);
    }
    if !baseline.live_ports_denied {
        blockers.push(Blocker::ApiBaselineLivePortsNotDenied);
    }
    if baseline.ibkr_call_performed {
        blockers.push(Blocker::ApiBaselineIbkrCallAlreadyPerformed);
    }
}

fn validate_global_denials(
    denials: &StockEtfPhase0GlobalDenialsV1,
    blockers: &mut Vec<StockEtfPhase0ManifestBlocker>,
) {
    use StockEtfPhase0ManifestBlocker as Blocker;

    let all_denied = denials.ibkr_live
        && denials.tiny_live
        && denials.margin
        && denials.short
        && denials.options
        && denials.cfd
        && denials.transfer
        && denials.account_management_writes
        && denials.python_broker_write_authority
        && denials.gui_lane_authority
        && denials.automatic_promotion;
    if !all_denied {
        blockers.push(Blocker::GlobalDenialMissing);
    }
}

fn validate_contracts(contracts: &[String], blockers: &mut Vec<StockEtfPhase0ManifestBlocker>) {
    use StockEtfPhase0ManifestBlocker as Blocker;

    for required in REQUIRED_CONTRACTS {
        let count = contracts
            .iter()
            .filter(|contract| contract.as_str() == *required)
            .count();
        if count == 0 {
            blockers.push(Blocker::ContractMissing);
        }
        if count > 1 {
            blockers.push(Blocker::ContractDuplicated);
        }
    }

    for contract in contracts {
        if !REQUIRED_CONTRACTS
            .iter()
            .any(|required| contract == required)
        {
            blockers.push(Blocker::ContractUnexpected);
        }
    }
}

fn validate_phase_unlock(
    unlock: &StockEtfPhase0UnlockTableV1,
    blockers: &mut Vec<StockEtfPhase0ManifestBlocker>,
) {
    use StockEtfPhase0ManifestBlocker as Blocker;

    if unlock.phase1_type_config_schema_ipc != "ALLOWED_AFTER_THIS_PACKET_WITH_E2_E4_QA" {
        blockers.push(Blocker::Phase1UnlockMismatch);
    }
    if unlock.phase2_ibkr_external_contact != "BLOCKED_UNTIL_PHASE2_EXTERNAL_SURFACE_GATE_PASS" {
        blockers.push(Blocker::Phase2ContactNotBlocked);
    }
    if unlock.phase3_evidence_clock != "BLOCKED_UNTIL_DATA_PROVENANCE_EVIDENCE_CONTRACTS_PASS" {
        blockers.push(Blocker::Phase3EvidenceClockNotBlocked);
    }
    if unlock.phase4_gui_runtime != "BLOCKED_UNTIL_ROUTE_CACHE_AUTH_NEGATIVE_TESTS_PASS" {
        blockers.push(Blocker::Phase4GuiRuntimeNotBlocked);
    }
    if unlock.phase5_paper_shadow_online != "BLOCKED_UNTIL_RELEASE_PACKET_AND_SHAKEDOWN_PASS" {
        blockers.push(Blocker::Phase5OnlineNotBlocked);
    }
    if unlock.tiny_live_or_live != "BLOCKED_REQUIRES_FUTURE_ADR" {
        blockers.push(Blocker::TinyLiveOrLiveNotBlocked);
    }
}
