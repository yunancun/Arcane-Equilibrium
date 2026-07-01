//! ADR-0048 IBKR Phase 2 immutable gate artifact acceptance tests.
//!
//! These tests validate source artifact shape only. They must not create a PASS
//! artifact, secret slot, broker session, paper order, or external API call.

use std::path::PathBuf;

use openclaw_types::{
    is_sha256_hex, IbkrExternalSurfaceGateV1, IbkrPhase2GateArtifactBlocker,
    IbkrPhase2GateArtifactV1, IbkrPhase2PolicyBundleV1, IbkrSecretSlotContractV1,
    IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
};

fn accepted_artifact_fixture() -> IbkrPhase2GateArtifactV1 {
    let policy_flags = IbkrPhase2PolicyBundleV1::source_template().gate_prerequisite_flags();
    let gate = IbkrExternalSurfaceGateV1 {
        redaction_suite_passed: policy_flags.redaction_suite_passed,
        rate_limit_policy_present: policy_flags.rate_limit_policy_present,
        audit_event_policy_present: policy_flags.audit_event_policy_present,
        paper_attestation_contract_present: policy_flags.paper_attestation_contract_present,
        python_no_write_guard_present: policy_flags.python_no_write_guard_present,
        ..IbkrExternalSurfaceGateV1::passing_fixture()
    };

    IbkrPhase2GateArtifactV1 {
        contract_id: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string(),
        source_version: 1,
        artifact_id: "phase2_ibkr_external_surface_gate_v1_fixture".to_string(),
        source_commit: "0123456789abcdef".to_string(),
        created_at_ms: 1_772_232_000_000,
        immutable_storage_path:
            "docs/execution_plan/specs/phase2_ibkr_external_surface_gate_v1.fixture.json"
                .to_string(),
        reviewer_roles: vec!["PM".to_string(), "Operator".to_string()],
        sealed: true,
        gate,
        policy_flags,
        secret_slot_contract: IbkrSecretSlotContractV1::source_template(),
        api_session_topology: openclaw_types::IbkrApiSessionTopologyV1::source_template(),
        raw_artifact_hash: "a".repeat(64),
        redacted_summary_hash: "b".repeat(64),
        ..IbkrPhase2GateArtifactV1::default()
    }
}

#[test]
fn default_gate_artifact_blocks_contact() {
    let artifact = IbkrPhase2GateArtifactV1::default();
    let verdict = artifact.validate();

    assert!(!verdict.ibkr_contact_allowed);
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ArtifactIdMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::SourceCommitMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ArtifactNotSealed));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ExternalSurfaceGateRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::PolicyPrerequisiteFlagsRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::SecretSlotContractRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ApiSessionTopologyRejected));
}

#[test]
fn accepted_fixture_requires_sealed_gate_and_review_metadata() {
    let artifact = accepted_artifact_fixture();
    let verdict = artifact.validate();

    assert!(verdict.ibkr_contact_allowed);
    assert!(verdict.blockers.is_empty());
    assert_eq!(artifact.contract_id, IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID);
    assert_eq!(artifact.source_version, 1);
    assert!(!artifact.gate.ibkr_call_performed);
    assert!(is_sha256_hex(&artifact.raw_artifact_hash));
    assert!(is_sha256_hex(&artifact.redacted_summary_hash));
}

#[test]
fn artifact_requires_exact_contract_id_and_source_version() {
    let artifact = IbkrPhase2GateArtifactV1 {
        contract_id: "phase2_ibkr_external_surface_gate_v1_fixture".to_string(),
        source_version: 2,
        ..accepted_artifact_fixture()
    };
    let verdict = artifact.validate();

    assert!(!verdict.ibkr_contact_allowed);
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::SourceVersionMismatch));
}

#[test]
fn artifact_rejects_blocked_or_retroactive_external_gate() {
    let blocked_gate = IbkrPhase2GateArtifactV1 {
        gate: IbkrExternalSurfaceGateV1::default(),
        ..accepted_artifact_fixture()
    };
    assert!(blocked_gate
        .validate()
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ExternalSurfaceGateRejected));

    let retroactive_gate = IbkrPhase2GateArtifactV1 {
        gate: IbkrExternalSurfaceGateV1 {
            ibkr_call_performed: true,
            ..IbkrExternalSurfaceGateV1::passing_fixture()
        },
        ..accepted_artifact_fixture()
    };
    let verdict = retroactive_gate.validate();
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ExternalSurfaceGateRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::IbkrCallAlreadyPerformed));
}

#[test]
fn artifact_rejects_missing_review_hash_and_seal_fields() {
    let artifact = IbkrPhase2GateArtifactV1 {
        reviewer_roles: vec!["PM".to_string()],
        sealed: false,
        raw_artifact_hash: "not-a-hash".to_string(),
        redacted_summary_hash: "c".repeat(63),
        immutable_storage_path: String::new(),
        ..accepted_artifact_fixture()
    };
    let verdict = artifact.validate();

    assert!(!verdict.ibkr_contact_allowed);
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::OperatorReviewerMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ArtifactNotSealed));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::RawArtifactHashInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::RedactedSummaryHashInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ImmutableStoragePathMissing));
}

#[test]
fn artifact_rejects_each_metadata_seal_and_hash_gap_independently() {
    use IbkrPhase2GateArtifactBlocker as Blocker;

    let cases: [(fn(&mut IbkrPhase2GateArtifactV1), Blocker); 11] = [
        (
            |artifact| artifact.artifact_id = String::new(),
            Blocker::ArtifactIdMissing,
        ),
        (
            |artifact| artifact.adr = "ADR-0047".to_string(),
            Blocker::AdrMismatch,
        ),
        (
            |artifact| artifact.amd = "AMD-2026-06-29-99".to_string(),
            Blocker::AmdMismatch,
        ),
        (
            |artifact| artifact.source_commit = String::new(),
            Blocker::SourceCommitMissing,
        ),
        (
            |artifact| artifact.created_at_ms = 0,
            Blocker::CreatedAtMissing,
        ),
        (
            |artifact| artifact.immutable_storage_path = String::new(),
            Blocker::ImmutableStoragePathMissing,
        ),
        (
            |artifact| artifact.reviewer_roles = vec!["Operator".to_string()],
            Blocker::PmReviewerMissing,
        ),
        (
            |artifact| artifact.reviewer_roles = vec!["PM".to_string()],
            Blocker::OperatorReviewerMissing,
        ),
        (
            |artifact| artifact.sealed = false,
            Blocker::ArtifactNotSealed,
        ),
        (
            |artifact| artifact.raw_artifact_hash = "not-a-hash".to_string(),
            Blocker::RawArtifactHashInvalid,
        ),
        (
            |artifact| artifact.redacted_summary_hash = "c".repeat(63),
            Blocker::RedactedSummaryHashInvalid,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut artifact = accepted_artifact_fixture();
        mutate(&mut artifact);
        assert_single_artifact_blocker(artifact.validate(), blocker);
    }
}

#[test]
fn artifact_rejects_policy_flag_mismatch() {
    let mut artifact = accepted_artifact_fixture();
    artifact.policy_flags.python_no_write_guard_present = false;
    let verdict = artifact.validate();

    assert!(!verdict.ibkr_contact_allowed);
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::PolicyPrerequisiteFlagsRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::PolicyGateFlagMismatch));
}

#[test]
fn artifact_rejects_missing_or_mismatched_runtime_evidence() {
    let missing_runtime = IbkrPhase2GateArtifactV1 {
        secret_slot_contract: IbkrSecretSlotContractV1::default(),
        api_session_topology: openclaw_types::IbkrApiSessionTopologyV1::default(),
        ..accepted_artifact_fixture()
    };
    let verdict = missing_runtime.validate();
    assert!(!verdict.ibkr_contact_allowed);
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::SecretSlotContractRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::ApiSessionTopologyRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::RuntimeGateFlagMismatch));

    let mismatched_gate = IbkrPhase2GateArtifactV1 {
        gate: IbkrExternalSurfaceGateV1 {
            secret_contract_present: false,
            live_secret_absent_or_empty: false,
            ..accepted_artifact_fixture().gate
        },
        ..accepted_artifact_fixture()
    };
    assert!(mismatched_gate
        .validate()
        .blockers
        .contains(&IbkrPhase2GateArtifactBlocker::RuntimeGateFlagMismatch));
}

#[test]
fn blocked_artifact_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/ibkr_phase2_gate_artifact.template.toml"),
    )
    .expect("read gate artifact template");
    let parsed: toml::Value = toml::from_str(&raw).expect("artifact template toml parses");

    assert_eq!(parsed["artifact"]["sealed"].as_bool(), Some(false));
    assert_eq!(parsed["artifact"]["contract_id"].as_str(), Some(""));
    assert_eq!(parsed["artifact"]["source_version"].as_integer(), Some(0));
    assert_eq!(parsed["gate"]["contract_id"].as_str(), Some(""));
    assert_eq!(parsed["gate"]["source_version"].as_integer(), Some(0));
    assert_eq!(parsed["gate"]["status"].as_str(), Some("BLOCKED"));
    assert_eq!(parsed["gate"]["ibkr_call_performed"].as_bool(), Some(false));
    assert_eq!(
        parsed["policy_flags"]["python_no_write_guard_present"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["secret_slot_contract"]["contract_id"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["secret_slot_contract"]["source_version"].as_integer(),
        Some(0)
    );
    assert_eq!(
        parsed["secret_slot_contract"]["contract_present"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["api_session_topology"]["contract_id"].as_str(),
        Some("")
    );
    assert_eq!(
        parsed["api_session_topology"]["source_version"].as_integer(),
        Some(0)
    );
    assert_eq!(
        parsed["api_session_topology"]["topology_present"].as_bool(),
        Some(false)
    );

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn assert_single_artifact_blocker(
    verdict: openclaw_types::IbkrPhase2GateArtifactVerdict,
    blocker: IbkrPhase2GateArtifactBlocker,
) {
    assert!(!verdict.ibkr_contact_allowed);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
