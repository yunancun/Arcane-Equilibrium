//! Stock/ETF kill switch and disable-cleanup runbook contract for ADR-0048.
//!
//! This source-only validator checks the shutdown/cleanup evidence shape for
//! the IBKR Stock/ETF paper-shadow lane. It does not read environment
//! variables, inspect secrets, stop services, delete database rows, contact
//! IBKR, route paper orders, or change Bybit live execution behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{AssetLane, Broker};

pub const STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID: &str =
    "stock_etf_kill_switch_and_disable_cleanup_runbook_v1";

const REQUIRED_ENV_FLAGS: &[(&str, &str)] = &[
    ("OPENCLAW_STOCK_ETF_LANE_ENABLED", "0"),
    ("OPENCLAW_IBKR_READONLY_ENABLED", "0"),
    ("OPENCLAW_IBKR_PAPER_ENABLED", "0"),
    ("OPENCLAW_STOCK_ETF_SHADOW_ONLY", "1"),
];

const REQUIRED_PROOFS: &[StockEtfDisableCleanupProofKind] = &[
    StockEtfDisableCleanupProofKind::CollectorStopped,
    StockEtfDisableCleanupProofKind::GuiStockViewsDisabledOrHidden,
    StockEtfDisableCleanupProofKind::LiveSecretAbsenceProven,
    StockEtfDisableCleanupProofKind::EvidenceArchiveForwardOnly,
    StockEtfDisableCleanupProofKind::DbForwardOnlyRetentionPreserved,
    StockEtfDisableCleanupProofKind::AppendOnlyAuditPreserved,
    StockEtfDisableCleanupProofKind::BybitLiveExecutionUnchanged,
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfDisableCleanupRunbookV1 {
    pub runbook_id: String,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub source_artifact_hash: String,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub paper_order_routed: bool,
    pub secret_slot_created: bool,
    pub secret_content_serialized: bool,
    pub destructive_db_cleanup_requested: bool,
    pub db_delete_or_truncate_allowed: bool,
    pub paper_shadow_launch_authorized: bool,
    pub tiny_live_authorized: bool,
    pub live_authorized: bool,
    pub env_flags: Vec<StockEtfDisableCleanupEnvFlagV1>,
    pub proofs: Vec<StockEtfDisableCleanupProofV1>,
}

impl Default for StockEtfDisableCleanupRunbookV1 {
    fn default() -> Self {
        Self {
            runbook_id: String::new(),
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            source_artifact_hash: String::new(),
            bybit_live_execution_unchanged: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            paper_order_routed: false,
            secret_slot_created: false,
            secret_content_serialized: false,
            destructive_db_cleanup_requested: false,
            db_delete_or_truncate_allowed: false,
            paper_shadow_launch_authorized: false,
            tiny_live_authorized: false,
            live_authorized: false,
            env_flags: Vec::new(),
            proofs: Vec::new(),
        }
    }
}

impl StockEtfDisableCleanupRunbookV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            runbook_id: STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID.to_string(),
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            source_artifact_hash: hash('1'),
            bybit_live_execution_unchanged: true,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            paper_order_routed: false,
            secret_slot_created: false,
            secret_content_serialized: false,
            destructive_db_cleanup_requested: false,
            db_delete_or_truncate_allowed: false,
            paper_shadow_launch_authorized: false,
            tiny_live_authorized: false,
            live_authorized: false,
            env_flags: REQUIRED_ENV_FLAGS
                .iter()
                .enumerate()
                .map(|(idx, (name, value))| {
                    StockEtfDisableCleanupEnvFlagV1::fixture(name, value, fill_for(idx))
                })
                .collect(),
            proofs: REQUIRED_PROOFS
                .iter()
                .enumerate()
                .map(|(idx, kind)| StockEtfDisableCleanupProofV1::fixture(*kind, fill_for(idx + 4)))
                .collect(),
        }
    }

    pub fn validate(&self) -> StockEtfDisableCleanupVerdict<StockEtfDisableCleanupBlocker> {
        use StockEtfDisableCleanupBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.runbook_id != STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID {
            blockers.push(Blocker::RunbookIdMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if !is_sha256_hex(&self.source_artifact_hash) {
            blockers.push(Blocker::SourceArtifactHashInvalid);
        }
        if !self.bybit_live_execution_unchanged {
            blockers.push(Blocker::BybitLiveExecutionNotProtected);
        }
        if self.ibkr_contact_performed {
            blockers.push(Blocker::IbkrContactPerformed);
        }
        if self.connector_runtime_started {
            blockers.push(Blocker::ConnectorRuntimeStarted);
        }
        if self.paper_order_routed {
            blockers.push(Blocker::PaperOrderRouted);
        }
        if self.secret_slot_created {
            blockers.push(Blocker::SecretSlotCreated);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if self.destructive_db_cleanup_requested {
            blockers.push(Blocker::DestructiveDbCleanupRequested);
        }
        if self.db_delete_or_truncate_allowed {
            blockers.push(Blocker::DbDeleteOrTruncateAllowed);
        }
        if self.paper_shadow_launch_authorized {
            blockers.push(Blocker::PaperShadowLaunchAuthorityClaimed);
        }
        if self.tiny_live_authorized {
            blockers.push(Blocker::TinyLiveAuthorityClaimed);
        }
        if self.live_authorized {
            blockers.push(Blocker::LiveAuthorityClaimed);
        }

        validate_env_flags(&self.env_flags, &mut blockers);
        validate_proofs(&self.proofs, &mut blockers);

        StockEtfDisableCleanupVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfDisableCleanupEnvFlagV1 {
    pub name: String,
    pub expected_value: String,
    pub observed_value: String,
    pub evidence_hash: String,
}

impl StockEtfDisableCleanupEnvFlagV1 {
    pub fn fixture(name: &str, value: &str, fill: char) -> Self {
        Self {
            name: name.to_string(),
            expected_value: value.to_string(),
            observed_value: value.to_string(),
            evidence_hash: hash(fill),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfDisableCleanupProofKind {
    CollectorStopped,
    GuiStockViewsDisabledOrHidden,
    LiveSecretAbsenceProven,
    EvidenceArchiveForwardOnly,
    DbForwardOnlyRetentionPreserved,
    AppendOnlyAuditPreserved,
    BybitLiveExecutionUnchanged,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfDisableCleanupProofV1 {
    pub kind: StockEtfDisableCleanupProofKind,
    pub verified: bool,
    pub evidence_hash: String,
    pub grants_runtime_authority: bool,
    pub destructive_cleanup_claimed: bool,
}

impl StockEtfDisableCleanupProofV1 {
    pub fn fixture(kind: StockEtfDisableCleanupProofKind, fill: char) -> Self {
        Self {
            kind,
            verified: true,
            evidence_hash: hash(fill),
            grants_runtime_authority: false,
            destructive_cleanup_claimed: false,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfDisableCleanupVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfDisableCleanupVerdict<B> {
    pub fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfDisableCleanupBlocker {
    RunbookIdMismatch,
    WrongAssetLane,
    WrongBroker,
    SourceArtifactHashInvalid,
    BybitLiveExecutionNotProtected,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    PaperOrderRouted,
    SecretSlotCreated,
    SecretContentSerialized,
    DestructiveDbCleanupRequested,
    DbDeleteOrTruncateAllowed,
    PaperShadowLaunchAuthorityClaimed,
    TinyLiveAuthorityClaimed,
    LiveAuthorityClaimed,
    EnvFlagMissing,
    EnvFlagDuplicated,
    EnvFlagUnexpected,
    EnvFlagExpectedValueMismatch,
    EnvFlagObservedValueMismatch,
    EnvFlagEvidenceHashInvalid,
    ProofMissing,
    ProofDuplicated,
    ProofNotVerified,
    ProofEvidenceHashInvalid,
    ProofGrantsRuntimeAuthority,
    ProofDestructiveCleanupClaimed,
}

fn validate_env_flags(
    flags: &[StockEtfDisableCleanupEnvFlagV1],
    blockers: &mut Vec<StockEtfDisableCleanupBlocker>,
) {
    use StockEtfDisableCleanupBlocker as Blocker;

    for (name, _) in REQUIRED_ENV_FLAGS {
        let matches: Vec<_> = flags.iter().filter(|flag| flag.name == *name).collect();
        if matches.is_empty() {
            blockers.push(Blocker::EnvFlagMissing);
            continue;
        }
        if matches.len() > 1 {
            blockers.push(Blocker::EnvFlagDuplicated);
        }
        for flag in matches {
            validate_env_flag(flag, blockers);
        }
    }

    for flag in flags {
        if expected_env_flag_value(&flag.name).is_none() {
            blockers.push(Blocker::EnvFlagUnexpected);
        }
    }
}

fn validate_env_flag(
    flag: &StockEtfDisableCleanupEnvFlagV1,
    blockers: &mut Vec<StockEtfDisableCleanupBlocker>,
) {
    use StockEtfDisableCleanupBlocker as Blocker;

    let Some(expected) = expected_env_flag_value(&flag.name) else {
        return;
    };
    if flag.expected_value != expected {
        blockers.push(Blocker::EnvFlagExpectedValueMismatch);
    }
    if flag.observed_value != expected {
        blockers.push(Blocker::EnvFlagObservedValueMismatch);
    }
    if !is_sha256_hex(&flag.evidence_hash) {
        blockers.push(Blocker::EnvFlagEvidenceHashInvalid);
    }
}

fn validate_proofs(
    proofs: &[StockEtfDisableCleanupProofV1],
    blockers: &mut Vec<StockEtfDisableCleanupBlocker>,
) {
    use StockEtfDisableCleanupBlocker as Blocker;

    for kind in REQUIRED_PROOFS {
        let matches: Vec<_> = proofs.iter().filter(|proof| proof.kind == *kind).collect();
        if matches.is_empty() {
            blockers.push(Blocker::ProofMissing);
            continue;
        }
        if matches.len() > 1 {
            blockers.push(Blocker::ProofDuplicated);
        }
        for proof in matches {
            validate_proof(proof, blockers);
        }
    }
}

fn validate_proof(
    proof: &StockEtfDisableCleanupProofV1,
    blockers: &mut Vec<StockEtfDisableCleanupBlocker>,
) {
    use StockEtfDisableCleanupBlocker as Blocker;

    if !proof.verified {
        blockers.push(Blocker::ProofNotVerified);
    }
    if !is_sha256_hex(&proof.evidence_hash) {
        blockers.push(Blocker::ProofEvidenceHashInvalid);
    }
    if proof.grants_runtime_authority {
        blockers.push(Blocker::ProofGrantsRuntimeAuthority);
    }
    if proof.destructive_cleanup_claimed {
        blockers.push(Blocker::ProofDestructiveCleanupClaimed);
    }
}

fn expected_env_flag_value(name: &str) -> Option<&'static str> {
    REQUIRED_ENV_FLAGS
        .iter()
        .find_map(|(expected_name, expected_value)| {
            if *expected_name == name {
                Some(*expected_value)
            } else {
                None
            }
        })
}

fn fill_for(index: usize) -> char {
    const FILLS: &[char] = &['2', '3', '4', '5', '6', '7', '8', '9', 'a', 'b', 'c', 'd'];
    FILLS[index % FILLS.len()]
}

fn hash(fill: char) -> String {
    fill.to_string().repeat(64)
}
