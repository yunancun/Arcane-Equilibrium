//! ADR-0048 Stock/ETF release packet acceptance tests.
//!
//! These tests validate release evidence shape only. They must not create a
//! PASS artifact, secret slot, broker session, paper order, evidence clock, or
//! external API call.

use std::path::PathBuf;

use openclaw_types::{
    StockEtfKillDisableCleanupProofV1, StockEtfPgMigrationEvidenceV1, StockEtfReleasePacketBlocker,
    StockEtfReleasePacketV1, STOCK_ETF_RELEASE_PACKET_CONTRACT_ID,
};

#[test]
fn default_release_packet_blocks_launch() {
    let packet = StockEtfReleasePacketV1::default();
    let verdict = packet.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, default_release_packet_blockers());
}

#[test]
fn accepted_fixture_completes_paper_shadow_release_without_live_authority() {
    let packet = StockEtfReleasePacketV1::accepted_fixture();
    let verdict = packet.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert!(!packet.secret_content_serialized);
    assert!(!packet.ibkr_live_or_tiny_live_authorized);
    assert_eq!(packet.packet_id, STOCK_ETF_RELEASE_PACKET_CONTRACT_ID);
    assert_eq!(packet.source_version, 1);
    assert!(packet.paper_shadow_window_complete);
    assert!(packet.engineering_shakedown_complete);
}

#[test]
fn release_packet_rejects_each_identity_and_path_gap_independently() {
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            packet_id: String::new(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::PacketIdMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            packet_id: "stock_etf_release_packet_v1_fixture".to_string(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::PacketIdMismatch,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            source_version: 2,
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::SourceVersionMismatch,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            adr_path: "docs/adr/wrong.md".to_string(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::AdrPathMismatch,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            amd_path: "docs/governance_dev/amendments/wrong.md".to_string(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::AmdPathMismatch,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            spec_path: "docs/execution_plan/specs/wrong.md".to_string(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::SpecPathMismatch,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            source_commit: String::new(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::SourceCommitMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            created_at_ms: 0,
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::CreatedAtMissing,
    );
}

#[test]
fn release_packet_rejects_each_required_role_gap_independently() {
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            reviewer_roles: roles_without("PM"),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::PmSignoffMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            reviewer_roles: roles_without("Operator"),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::OperatorSignoffMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            reviewer_roles: roles_without("E2"),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::E2SignoffMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            reviewer_roles: roles_without("E3"),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::E3SignoffMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            reviewer_roles: roles_without("E4"),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::E4SignoffMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            reviewer_roles: roles_without("QA"),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::QaSignoffMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            reviewer_roles: roles_without("QC"),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::QcSignoffMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            reviewer_roles: roles_without("MIT"),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::MitSignoffMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            role_report_paths: Vec::new(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::RoleReportsMissing,
    );
}

#[test]
fn release_packet_rejects_each_evidence_hash_gap_independently() {
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            e2_log_hash: "not-a-hash".to_string(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::E2LogHashInvalid,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            e3_redaction_log_hash: String::new(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::E3RedactionLogHashInvalid,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            e4_log_hash: "not-a-hash".to_string(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::E4LogHashInvalid,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            qa_log_hash: "z".repeat(64),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::QaLogHashInvalid,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            manifest_hashes: Vec::new(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::ManifestHashesInvalid,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            redaction_fixture_hash: "not-a-hash".to_string(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::RedactionFixtureHashInvalid,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            gui_screenshot_hashes: Vec::new(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::GuiScreenshotsMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            dq_manifest_hashes: Vec::new(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::DqManifestsMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            scorecard_regeneration_hashes: Vec::new(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::ScorecardRegenerationMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            evidence_archive_pointer: String::new(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::EvidenceArchivePointerMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            evidence_archive_hash: "not-a-hash".to_string(),
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::EvidenceArchiveHashInvalid,
    );
}

#[test]
fn release_packet_rejects_each_migration_evidence_gap_independently() {
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            pg_migration_evidence: StockEtfPgMigrationEvidenceV1 {
                migrations_declared: true,
                migration_manifest_hash: String::new(),
                pg_dry_run_log_hash: "2".repeat(64),
                pg_double_apply_log_hash: "3".repeat(64),
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::PgMigrationManifestHashInvalid,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            pg_migration_evidence: StockEtfPgMigrationEvidenceV1 {
                migrations_declared: true,
                migration_manifest_hash: "1".repeat(64),
                pg_dry_run_log_hash: String::new(),
                pg_double_apply_log_hash: "3".repeat(64),
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::PgDryRunLogMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            pg_migration_evidence: StockEtfPgMigrationEvidenceV1 {
                migrations_declared: true,
                migration_manifest_hash: "1".repeat(64),
                pg_dry_run_log_hash: "2".repeat(64),
                pg_double_apply_log_hash: String::new(),
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::PgDoubleApplyLogMissing,
    );
}

#[test]
fn release_packet_rejects_each_kill_disable_cleanup_gap_independently() {
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
                stock_etf_lane_enabled_false: false,
                ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::KillLaneFlagNotDisabled,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
                ibkr_readonly_enabled_false: false,
                ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::KillReadonlyFlagNotDisabled,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
                ibkr_paper_enabled_false: false,
                ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::KillPaperFlagNotDisabled,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
                stock_etf_shadow_only_true: false,
                ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::KillShadowOnlyFlagNotPreserved,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
                collector_stopped: false,
                ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::CollectorStopProofMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
                gui_stock_views_disabled_or_hidden: false,
                ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::GuiDisableProofMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
                live_secret_absence_proven: false,
                ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::LiveSecretAbsenceProofMissing,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
                evidence_archive_forward_only: false,
                ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::EvidenceArchiveNotForwardOnly,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
                destructive_db_cleanup_requested: true,
                ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::DestructiveDbCleanupRequested,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
                proof_hash: "not-a-hash".to_string(),
                ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
            },
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::KillDisableProofHashInvalid,
    );
}

#[test]
fn release_packet_rejects_each_final_posture_gap_independently() {
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            paper_shadow_window_complete: false,
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::PaperShadowWindowIncomplete,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            engineering_shakedown_complete: false,
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::EngineeringShakedownIncomplete,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            secret_content_serialized: true,
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::SecretContentSerialized,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            ibkr_live_or_tiny_live_authorized: true,
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::LiveOrTinyLiveAuthorityPresent,
    );
    assert_single_blocker(
        StockEtfReleasePacketV1 {
            sealed: false,
            ..StockEtfReleasePacketV1::accepted_fixture()
        },
        StockEtfReleasePacketBlocker::ReleasePacketNotSealed,
    );
}

#[test]
fn release_packet_requires_exact_contract_id_and_source_version() {
    use StockEtfReleasePacketBlocker as Blocker;

    let packet = StockEtfReleasePacketV1 {
        packet_id: "stock_etf_release_packet_v1_fixture".to_string(),
        source_version: 2,
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    let blockers = packet.validate().blockers;

    assert_eq!(
        blockers,
        vec![Blocker::PacketIdMismatch, Blocker::SourceVersionMismatch]
    );
}

#[test]
fn release_packet_requires_phase5_role_signoffs_and_hashes() {
    use StockEtfReleasePacketBlocker as Blocker;

    let packet = StockEtfReleasePacketV1 {
        reviewer_roles: vec!["PM".to_string(), "Operator".to_string()],
        role_report_paths: vec!["docs/CCAgentWorkSpace/PM/workspace/reports/x.md".to_string()],
        e2_log_hash: "not-a-hash".to_string(),
        e3_redaction_log_hash: String::new(),
        qa_log_hash: "z".repeat(64),
        manifest_hashes: Vec::new(),
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    let blockers = packet.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::E2SignoffMissing,
            Blocker::E3SignoffMissing,
            Blocker::E4SignoffMissing,
            Blocker::QaSignoffMissing,
            Blocker::QcSignoffMissing,
            Blocker::MitSignoffMissing,
            Blocker::E2LogHashInvalid,
            Blocker::E3RedactionLogHashInvalid,
            Blocker::QaLogHashInvalid,
            Blocker::ManifestHashesInvalid,
        ]
    );
}

#[test]
fn migration_evidence_requires_dry_run_and_double_apply_when_declared() {
    use StockEtfReleasePacketBlocker as Blocker;

    let packet = StockEtfReleasePacketV1 {
        pg_migration_evidence: StockEtfPgMigrationEvidenceV1 {
            migrations_declared: true,
            migration_manifest_hash: "1".repeat(64),
            pg_dry_run_log_hash: String::new(),
            pg_double_apply_log_hash: String::new(),
        },
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    let blockers = packet.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::PgDryRunLogMissing,
            Blocker::PgDoubleApplyLogMissing
        ]
    );

    let accepted = StockEtfReleasePacketV1 {
        pg_migration_evidence: StockEtfPgMigrationEvidenceV1::migration_fixture(),
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    assert!(accepted.validate().accepted);
}

#[test]
fn kill_disable_cleanup_rejects_open_flags_and_destructive_db_cleanup() {
    use StockEtfReleasePacketBlocker as Blocker;

    let packet = StockEtfReleasePacketV1 {
        kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1 {
            stock_etf_lane_enabled_false: false,
            ibkr_readonly_enabled_false: false,
            ibkr_paper_enabled_false: false,
            stock_etf_shadow_only_true: false,
            destructive_db_cleanup_requested: true,
            proof_hash: "bad".to_string(),
            ..StockEtfKillDisableCleanupProofV1::accepted_fixture()
        },
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    let blockers = packet.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::KillLaneFlagNotDisabled,
            Blocker::KillReadonlyFlagNotDisabled,
            Blocker::KillPaperFlagNotDisabled,
            Blocker::KillShadowOnlyFlagNotPreserved,
            Blocker::DestructiveDbCleanupRequested,
            Blocker::KillDisableProofHashInvalid,
        ]
    );
}

#[test]
fn release_packet_rejects_secret_serialization_and_live_authority() {
    use StockEtfReleasePacketBlocker as Blocker;

    let packet = StockEtfReleasePacketV1 {
        secret_content_serialized: true,
        ibkr_live_or_tiny_live_authorized: true,
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    let blockers = packet.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            Blocker::SecretContentSerialized,
            Blocker::LiveOrTinyLiveAuthorityPresent,
        ]
    );
}

#[test]
fn release_packet_rejects_secret_authority_window_and_seal_cross_wire_independently() {
    let secret = StockEtfReleasePacketV1 {
        secret_content_serialized: true,
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    assert_single_blocker(
        secret,
        StockEtfReleasePacketBlocker::SecretContentSerialized,
    );

    let live_authority = StockEtfReleasePacketV1 {
        ibkr_live_or_tiny_live_authorized: true,
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    assert_single_blocker(
        live_authority,
        StockEtfReleasePacketBlocker::LiveOrTinyLiveAuthorityPresent,
    );

    let unsealed = StockEtfReleasePacketV1 {
        sealed: false,
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    assert_single_blocker(
        unsealed,
        StockEtfReleasePacketBlocker::ReleasePacketNotSealed,
    );

    let incomplete_window = StockEtfReleasePacketV1 {
        paper_shadow_window_complete: false,
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    assert_single_blocker(
        incomplete_window,
        StockEtfReleasePacketBlocker::PaperShadowWindowIncomplete,
    );

    let incomplete_shakedown = StockEtfReleasePacketV1 {
        engineering_shakedown_complete: false,
        ..StockEtfReleasePacketV1::accepted_fixture()
    };
    assert_single_blocker(
        incomplete_shakedown,
        StockEtfReleasePacketBlocker::EngineeringShakedownIncomplete,
    );
}

#[test]
fn blocked_release_packet_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_release_packet.template.toml"),
    )
    .expect("read release packet template");
    let parsed: toml::Value = toml::from_str(&raw).expect("release packet template parses");

    assert_eq!(parsed["release_packet"]["sealed"].as_bool(), Some(false));
    assert_eq!(
        parsed["release_packet"]["source_version"].as_integer(),
        Some(0)
    );
    assert_eq!(
        parsed["release_packet"]["paper_shadow_window_complete"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["release_packet"]["ibkr_live_or_tiny_live_authorized"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["kill_disable_cleanup_proof"]["destructive_db_cleanup_requested"].as_bool(),
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
    candidate: StockEtfReleasePacketV1,
    expected: StockEtfReleasePacketBlocker,
) {
    let verdict = candidate.validate();

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, vec![expected]);
}

fn default_release_packet_blockers() -> Vec<StockEtfReleasePacketBlocker> {
    use StockEtfReleasePacketBlocker as Blocker;

    vec![
        Blocker::PacketIdMissing,
        Blocker::SourceVersionMismatch,
        Blocker::SourceCommitMissing,
        Blocker::CreatedAtMissing,
        Blocker::PmSignoffMissing,
        Blocker::OperatorSignoffMissing,
        Blocker::E2SignoffMissing,
        Blocker::E3SignoffMissing,
        Blocker::E4SignoffMissing,
        Blocker::QaSignoffMissing,
        Blocker::QcSignoffMissing,
        Blocker::MitSignoffMissing,
        Blocker::RoleReportsMissing,
        Blocker::E2LogHashInvalid,
        Blocker::E3RedactionLogHashInvalid,
        Blocker::E4LogHashInvalid,
        Blocker::QaLogHashInvalid,
        Blocker::ManifestHashesInvalid,
        Blocker::RedactionFixtureHashInvalid,
        Blocker::GuiScreenshotsMissing,
        Blocker::DqManifestsMissing,
        Blocker::ScorecardRegenerationMissing,
        Blocker::KillLaneFlagNotDisabled,
        Blocker::KillReadonlyFlagNotDisabled,
        Blocker::KillPaperFlagNotDisabled,
        Blocker::KillShadowOnlyFlagNotPreserved,
        Blocker::CollectorStopProofMissing,
        Blocker::GuiDisableProofMissing,
        Blocker::LiveSecretAbsenceProofMissing,
        Blocker::EvidenceArchiveNotForwardOnly,
        Blocker::KillDisableProofHashInvalid,
        Blocker::EvidenceArchivePointerMissing,
        Blocker::EvidenceArchiveHashInvalid,
        Blocker::PaperShadowWindowIncomplete,
        Blocker::EngineeringShakedownIncomplete,
        Blocker::ReleasePacketNotSealed,
    ]
}

fn roles_without(excluded: &str) -> Vec<String> {
    StockEtfReleasePacketV1::accepted_fixture()
        .reviewer_roles
        .into_iter()
        .filter(|role| role != excluded)
        .collect()
}
