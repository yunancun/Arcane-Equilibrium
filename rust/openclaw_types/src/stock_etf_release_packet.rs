//! Stock/ETF release packet contract for ADR-0048.
//!
//! This source-only contract validates the paper/shadow release evidence packet
//! shape. It does not read files, inspect secrets, open broker sockets, start an
//! evidence clock, or authorize tiny-live/live execution.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;

pub const STOCK_ETF_RELEASE_ADR_PATH: &str = "docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md";
pub const STOCK_ETF_RELEASE_AMD_PATH: &str =
    "docs/governance_dev/amendments/2026-06-29--AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md";
pub const STOCK_ETF_RELEASE_SPEC_PATH: &str =
    "docs/execution_plan/specs/2026-06-29--stock_etf_cash_phase0_named_contract_packet.md";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfReleaseManifestHashV1 {
    pub label: String,
    pub sha256: String,
}

impl StockEtfReleaseManifestHashV1 {
    pub fn fixture(label: &str, fill: char) -> Self {
        Self {
            label: label.to_string(),
            sha256: fill.to_string().repeat(64),
        }
    }

    pub fn validate(&self) -> bool {
        !self.label.trim().is_empty() && is_sha256_hex(&self.sha256)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfPgMigrationEvidenceV1 {
    pub migrations_declared: bool,
    pub migration_manifest_hash: String,
    pub pg_dry_run_log_hash: String,
    pub pg_double_apply_log_hash: String,
}

impl Default for StockEtfPgMigrationEvidenceV1 {
    fn default() -> Self {
        Self {
            migrations_declared: false,
            migration_manifest_hash: String::new(),
            pg_dry_run_log_hash: String::new(),
            pg_double_apply_log_hash: String::new(),
        }
    }
}

impl StockEtfPgMigrationEvidenceV1 {
    pub fn no_migration_fixture() -> Self {
        Self::default()
    }

    pub fn migration_fixture() -> Self {
        Self {
            migrations_declared: true,
            migration_manifest_hash: "1".repeat(64),
            pg_dry_run_log_hash: "2".repeat(64),
            pg_double_apply_log_hash: "3".repeat(64),
        }
    }

    pub fn validate(&self) -> StockEtfReleaseVerdict<StockEtfReleasePacketBlocker> {
        use StockEtfReleasePacketBlocker as Blocker;
        let mut blockers = Vec::new();
        if self.migrations_declared {
            if !is_sha256_hex(&self.migration_manifest_hash) {
                blockers.push(Blocker::PgMigrationManifestHashInvalid);
            }
            if !is_sha256_hex(&self.pg_dry_run_log_hash) {
                blockers.push(Blocker::PgDryRunLogMissing);
            }
            if !is_sha256_hex(&self.pg_double_apply_log_hash) {
                blockers.push(Blocker::PgDoubleApplyLogMissing);
            }
        }
        StockEtfReleaseVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfKillDisableCleanupProofV1 {
    pub stock_etf_lane_enabled_false: bool,
    pub ibkr_readonly_enabled_false: bool,
    pub ibkr_paper_enabled_false: bool,
    pub stock_etf_shadow_only_true: bool,
    pub collector_stopped: bool,
    pub gui_stock_views_disabled_or_hidden: bool,
    pub live_secret_absence_proven: bool,
    pub evidence_archive_forward_only: bool,
    pub destructive_db_cleanup_requested: bool,
    pub proof_hash: String,
}

impl Default for StockEtfKillDisableCleanupProofV1 {
    fn default() -> Self {
        Self {
            stock_etf_lane_enabled_false: false,
            ibkr_readonly_enabled_false: false,
            ibkr_paper_enabled_false: false,
            stock_etf_shadow_only_true: false,
            collector_stopped: false,
            gui_stock_views_disabled_or_hidden: false,
            live_secret_absence_proven: false,
            evidence_archive_forward_only: false,
            destructive_db_cleanup_requested: false,
            proof_hash: String::new(),
        }
    }
}

impl StockEtfKillDisableCleanupProofV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            stock_etf_lane_enabled_false: true,
            ibkr_readonly_enabled_false: true,
            ibkr_paper_enabled_false: true,
            stock_etf_shadow_only_true: true,
            collector_stopped: true,
            gui_stock_views_disabled_or_hidden: true,
            live_secret_absence_proven: true,
            evidence_archive_forward_only: true,
            destructive_db_cleanup_requested: false,
            proof_hash: "4".repeat(64),
        }
    }

    pub fn validate(&self) -> StockEtfReleaseVerdict<StockEtfReleasePacketBlocker> {
        use StockEtfReleasePacketBlocker as Blocker;
        let mut blockers = Vec::new();
        if !self.stock_etf_lane_enabled_false {
            blockers.push(Blocker::KillLaneFlagNotDisabled);
        }
        if !self.ibkr_readonly_enabled_false {
            blockers.push(Blocker::KillReadonlyFlagNotDisabled);
        }
        if !self.ibkr_paper_enabled_false {
            blockers.push(Blocker::KillPaperFlagNotDisabled);
        }
        if !self.stock_etf_shadow_only_true {
            blockers.push(Blocker::KillShadowOnlyFlagNotPreserved);
        }
        if !self.collector_stopped {
            blockers.push(Blocker::CollectorStopProofMissing);
        }
        if !self.gui_stock_views_disabled_or_hidden {
            blockers.push(Blocker::GuiDisableProofMissing);
        }
        if !self.live_secret_absence_proven {
            blockers.push(Blocker::LiveSecretAbsenceProofMissing);
        }
        if !self.evidence_archive_forward_only {
            blockers.push(Blocker::EvidenceArchiveNotForwardOnly);
        }
        if self.destructive_db_cleanup_requested {
            blockers.push(Blocker::DestructiveDbCleanupRequested);
        }
        if !is_sha256_hex(&self.proof_hash) {
            blockers.push(Blocker::KillDisableProofHashInvalid);
        }
        StockEtfReleaseVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfReleasePacketV1 {
    pub packet_id: String,
    pub adr_path: String,
    pub amd_path: String,
    pub spec_path: String,
    pub source_commit: String,
    pub created_at_ms: u64,
    pub reviewer_roles: Vec<String>,
    pub role_report_paths: Vec<String>,
    pub e2_log_hash: String,
    pub e3_redaction_log_hash: String,
    pub e4_log_hash: String,
    pub qa_log_hash: String,
    pub manifest_hashes: Vec<StockEtfReleaseManifestHashV1>,
    pub pg_migration_evidence: StockEtfPgMigrationEvidenceV1,
    pub redaction_fixture_hash: String,
    pub gui_screenshot_hashes: Vec<String>,
    pub dq_manifest_hashes: Vec<String>,
    pub scorecard_regeneration_hashes: Vec<String>,
    pub kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1,
    pub evidence_archive_pointer: String,
    pub evidence_archive_hash: String,
    pub paper_shadow_window_complete: bool,
    pub engineering_shakedown_complete: bool,
    pub secret_content_serialized: bool,
    pub ibkr_live_or_tiny_live_authorized: bool,
    pub sealed: bool,
}

impl Default for StockEtfReleasePacketV1 {
    fn default() -> Self {
        Self {
            packet_id: String::new(),
            adr_path: STOCK_ETF_RELEASE_ADR_PATH.to_string(),
            amd_path: STOCK_ETF_RELEASE_AMD_PATH.to_string(),
            spec_path: STOCK_ETF_RELEASE_SPEC_PATH.to_string(),
            source_commit: String::new(),
            created_at_ms: 0,
            reviewer_roles: Vec::new(),
            role_report_paths: Vec::new(),
            e2_log_hash: String::new(),
            e3_redaction_log_hash: String::new(),
            e4_log_hash: String::new(),
            qa_log_hash: String::new(),
            manifest_hashes: Vec::new(),
            pg_migration_evidence: StockEtfPgMigrationEvidenceV1::default(),
            redaction_fixture_hash: String::new(),
            gui_screenshot_hashes: Vec::new(),
            dq_manifest_hashes: Vec::new(),
            scorecard_regeneration_hashes: Vec::new(),
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1::default(),
            evidence_archive_pointer: String::new(),
            evidence_archive_hash: String::new(),
            paper_shadow_window_complete: false,
            engineering_shakedown_complete: false,
            secret_content_serialized: false,
            ibkr_live_or_tiny_live_authorized: false,
            sealed: false,
        }
    }
}

impl StockEtfReleasePacketV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            packet_id: "stock_etf_release_packet_v1_fixture".to_string(),
            adr_path: STOCK_ETF_RELEASE_ADR_PATH.to_string(),
            amd_path: STOCK_ETF_RELEASE_AMD_PATH.to_string(),
            spec_path: STOCK_ETF_RELEASE_SPEC_PATH.to_string(),
            source_commit: "94e7dbd00da8c2becced247137285c072f7cfdef".to_string(),
            created_at_ms: 1_782_800_000_000,
            reviewer_roles: required_release_roles()
                .iter()
                .map(|role| role.to_string())
                .collect(),
            role_report_paths: vec![
                "docs/CCAgentWorkSpace/PM/workspace/reports/fixture.md".to_string(),
                "docs/CCAgentWorkSpace/QA/workspace/reports/fixture.md".to_string(),
            ],
            e2_log_hash: "5".repeat(64),
            e3_redaction_log_hash: "6".repeat(64),
            e4_log_hash: "7".repeat(64),
            qa_log_hash: "8".repeat(64),
            manifest_hashes: vec![
                StockEtfReleaseManifestHashV1::fixture("release_manifest", '9'),
                StockEtfReleaseManifestHashV1::fixture("artifact_manifest", 'a'),
            ],
            pg_migration_evidence: StockEtfPgMigrationEvidenceV1::no_migration_fixture(),
            redaction_fixture_hash: "b".repeat(64),
            gui_screenshot_hashes: vec!["c".repeat(64)],
            dq_manifest_hashes: vec!["d".repeat(64)],
            scorecard_regeneration_hashes: vec!["e".repeat(64)],
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1::accepted_fixture(),
            evidence_archive_pointer: "archive://stock-etf/fixture".to_string(),
            evidence_archive_hash: "f".repeat(64),
            paper_shadow_window_complete: true,
            engineering_shakedown_complete: true,
            secret_content_serialized: false,
            ibkr_live_or_tiny_live_authorized: false,
            sealed: true,
        }
    }

    pub fn validate(&self) -> StockEtfReleaseVerdict<StockEtfReleasePacketBlocker> {
        use StockEtfReleasePacketBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.packet_id.trim().is_empty() {
            blockers.push(Blocker::PacketIdMissing);
        }
        if self.adr_path != STOCK_ETF_RELEASE_ADR_PATH {
            blockers.push(Blocker::AdrPathMismatch);
        }
        if self.amd_path != STOCK_ETF_RELEASE_AMD_PATH {
            blockers.push(Blocker::AmdPathMismatch);
        }
        if self.spec_path != STOCK_ETF_RELEASE_SPEC_PATH {
            blockers.push(Blocker::SpecPathMismatch);
        }
        if self.source_commit.trim().is_empty() {
            blockers.push(Blocker::SourceCommitMissing);
        }
        if self.created_at_ms == 0 {
            blockers.push(Blocker::CreatedAtMissing);
        }
        for role in required_release_roles() {
            if !contains_role(&self.reviewer_roles, role) {
                blockers.push(match *role {
                    "PM" => Blocker::PmSignoffMissing,
                    "Operator" => Blocker::OperatorSignoffMissing,
                    "E2" => Blocker::E2SignoffMissing,
                    "E3" => Blocker::E3SignoffMissing,
                    "E4" => Blocker::E4SignoffMissing,
                    "QA" => Blocker::QaSignoffMissing,
                    "QC" => Blocker::QcSignoffMissing,
                    "MIT" => Blocker::MitSignoffMissing,
                    _ => Blocker::UnknownRequiredRoleMissing,
                });
            }
        }
        if self.role_report_paths.is_empty()
            || self
                .role_report_paths
                .iter()
                .any(|path| path.trim().is_empty())
        {
            blockers.push(Blocker::RoleReportsMissing);
        }
        if !is_sha256_hex(&self.e2_log_hash) {
            blockers.push(Blocker::E2LogHashInvalid);
        }
        if !is_sha256_hex(&self.e3_redaction_log_hash) {
            blockers.push(Blocker::E3RedactionLogHashInvalid);
        }
        if !is_sha256_hex(&self.e4_log_hash) {
            blockers.push(Blocker::E4LogHashInvalid);
        }
        if !is_sha256_hex(&self.qa_log_hash) {
            blockers.push(Blocker::QaLogHashInvalid);
        }
        if self.manifest_hashes.is_empty()
            || self.manifest_hashes.iter().any(|entry| !entry.validate())
        {
            blockers.push(Blocker::ManifestHashesInvalid);
        }
        blockers.extend(self.pg_migration_evidence.validate().blockers);
        if !is_sha256_hex(&self.redaction_fixture_hash) {
            blockers.push(Blocker::RedactionFixtureHashInvalid);
        }
        if empty_or_invalid_hashes(&self.gui_screenshot_hashes) {
            blockers.push(Blocker::GuiScreenshotsMissing);
        }
        if empty_or_invalid_hashes(&self.dq_manifest_hashes) {
            blockers.push(Blocker::DqManifestsMissing);
        }
        if empty_or_invalid_hashes(&self.scorecard_regeneration_hashes) {
            blockers.push(Blocker::ScorecardRegenerationMissing);
        }
        blockers.extend(self.kill_disable_cleanup_proof.validate().blockers);
        if self.evidence_archive_pointer.trim().is_empty() {
            blockers.push(Blocker::EvidenceArchivePointerMissing);
        }
        if !is_sha256_hex(&self.evidence_archive_hash) {
            blockers.push(Blocker::EvidenceArchiveHashInvalid);
        }
        if !self.paper_shadow_window_complete {
            blockers.push(Blocker::PaperShadowWindowIncomplete);
        }
        if !self.engineering_shakedown_complete {
            blockers.push(Blocker::EngineeringShakedownIncomplete);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if self.ibkr_live_or_tiny_live_authorized {
            blockers.push(Blocker::LiveOrTinyLiveAuthorityPresent);
        }
        if !self.sealed {
            blockers.push(Blocker::ReleasePacketNotSealed);
        }

        StockEtfReleaseVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfReleaseVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfReleaseVerdict<B> {
    pub fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfReleasePacketBlocker {
    PacketIdMissing,
    AdrPathMismatch,
    AmdPathMismatch,
    SpecPathMismatch,
    SourceCommitMissing,
    CreatedAtMissing,
    PmSignoffMissing,
    OperatorSignoffMissing,
    E2SignoffMissing,
    E3SignoffMissing,
    E4SignoffMissing,
    QaSignoffMissing,
    QcSignoffMissing,
    MitSignoffMissing,
    UnknownRequiredRoleMissing,
    RoleReportsMissing,
    E2LogHashInvalid,
    E3RedactionLogHashInvalid,
    E4LogHashInvalid,
    QaLogHashInvalid,
    ManifestHashesInvalid,
    PgMigrationManifestHashInvalid,
    PgDryRunLogMissing,
    PgDoubleApplyLogMissing,
    RedactionFixtureHashInvalid,
    GuiScreenshotsMissing,
    DqManifestsMissing,
    ScorecardRegenerationMissing,
    KillLaneFlagNotDisabled,
    KillReadonlyFlagNotDisabled,
    KillPaperFlagNotDisabled,
    KillShadowOnlyFlagNotPreserved,
    CollectorStopProofMissing,
    GuiDisableProofMissing,
    LiveSecretAbsenceProofMissing,
    EvidenceArchiveNotForwardOnly,
    DestructiveDbCleanupRequested,
    KillDisableProofHashInvalid,
    EvidenceArchivePointerMissing,
    EvidenceArchiveHashInvalid,
    PaperShadowWindowIncomplete,
    EngineeringShakedownIncomplete,
    SecretContentSerialized,
    LiveOrTinyLiveAuthorityPresent,
    ReleasePacketNotSealed,
}

fn required_release_roles() -> &'static [&'static str] {
    &["PM", "Operator", "E2", "E3", "E4", "QA", "QC", "MIT"]
}

fn contains_role(roles: &[String], expected: &str) -> bool {
    roles.iter().any(|role| role == expected)
}

fn empty_or_invalid_hashes(values: &[String]) -> bool {
    values.is_empty() || values.iter().any(|value| !is_sha256_hex(value))
}
