//! ADR-0048 IBKR feature-flag/secret/scoped-auth matrix acceptance tests.
//!
//! These tests validate source contract behavior only. They must not read
//! secrets, contact IBKR, construct a connector, or route paper/live orders.

use std::path::PathBuf;

use openclaw_types::{
    evaluate_feature_flag_secret_auth_matrix, AuthorityScope, BrokerCapabilityRequest,
    BrokerEnvironment, BrokerOperation, FeatureFlagSecretAuthBlocker,
    FeatureFlagSecretAuthMatrixV1, IbkrApiSessionTopologyV1, IbkrExternalSurfaceGateV1,
    IbkrPhase2GateArtifactV1, IbkrPhase2PolicyBundleV1, IbkrSecretSlotContractV1,
    IbkrSessionAttestationV1, InstrumentKind, StockEtfAuthorizationEnvelopeV1,
    StockEtfFeatureFlags, FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID,
};

const NOW_MS: u64 = 1_772_233_000_000;
const EXPIRES_AT_MS: u64 = 1_772_235_600_000;

fn accepted_artifact_fixture(secret: &IbkrSecretSlotContractV1) -> IbkrPhase2GateArtifactV1 {
    let policy_flags = IbkrPhase2PolicyBundleV1::source_template().gate_prerequisite_flags();
    let gate = IbkrExternalSurfaceGateV1 {
        redaction_suite_passed: policy_flags.redaction_suite_passed,
        rate_limit_policy_present: policy_flags.rate_limit_policy_present,
        audit_event_policy_present: policy_flags.audit_event_policy_present,
        paper_attestation_contract_present: policy_flags.paper_attestation_contract_present,
        python_no_write_guard_present: policy_flags.python_no_write_guard_present,
        ..IbkrExternalSurfaceGateV1::passing_fixture()
    };
    let mut topology = IbkrApiSessionTopologyV1::source_template();
    topology.account_fingerprint_hash = secret.account_fingerprint_hash.clone();

    IbkrPhase2GateArtifactV1 {
        artifact_id: "phase2_ibkr_external_surface_gate_v1_matrix_fixture".to_string(),
        source_commit: "0123456789abcdef".to_string(),
        created_at_ms: NOW_MS,
        immutable_storage_path:
            "docs/execution_plan/specs/phase2_ibkr_external_surface_gate_v1.matrix.fixture.json"
                .to_string(),
        reviewer_roles: vec!["PM".to_string(), "Operator".to_string()],
        sealed: true,
        gate,
        policy_flags,
        secret_slot_contract: secret.clone(),
        api_session_topology: topology,
        raw_artifact_hash: "e".repeat(64),
        redacted_summary_hash: "f".repeat(64),
        ..IbkrPhase2GateArtifactV1::default()
    }
}

fn accepted_session_fixture(secret: &IbkrSecretSlotContractV1) -> IbkrSessionAttestationV1 {
    IbkrSessionAttestationV1 {
        account_fingerprint: secret.account_fingerprint_hash.clone(),
        secret_slot_fingerprint: secret.secret_slot_fingerprint.clone(),
        raw_artifact_hash: "e".repeat(64),
        ..IbkrSessionAttestationV1::paper_fixture()
    }
}

fn accepted_matrix(
    ibkr_paper_enabled: bool,
    stock_etf_shadow_only: bool,
) -> FeatureFlagSecretAuthMatrixV1 {
    let secret = IbkrSecretSlotContractV1::source_template();
    FeatureFlagSecretAuthMatrixV1 {
        contract_id: FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID.to_string(),
        source_version: 1,
        flags: StockEtfFeatureFlags {
            stock_etf_lane_enabled: true,
            ibkr_readonly_enabled: true,
            ibkr_paper_enabled,
            stock_etf_shadow_only,
            ..StockEtfFeatureFlags::default()
        },
        phase2_gate_artifact: accepted_artifact_fixture(&secret),
        session_attestation: accepted_session_fixture(&secret),
        secret_slot_contract: secret,
        authorization_envelope: StockEtfAuthorizationEnvelopeV1::paper_fixture(EXPIRES_AT_MS),
        gui_lane_state_override_denied: true,
        server_rust_matrix_authoritative: true,
    }
}

fn paper_submit_request() -> BrokerCapabilityRequest {
    BrokerCapabilityRequest::stock_etf_ibkr_paper(
        InstrumentKind::Stock,
        BrokerOperation::PaperOrderSubmit,
    )
}

#[test]
fn default_feature_flag_secret_auth_matrix_blocks_contact() {
    let verdict = evaluate_feature_flag_secret_auth_matrix(
        &FeatureFlagSecretAuthMatrixV1::default(),
        paper_submit_request(),
        NOW_MS,
    );

    assert!(!verdict.allowed);
    assert_eq!(verdict.effective_authority_scope, AuthorityScope::Denied);
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::LaneFlagDisabled));
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::PaperFlagDisabled));
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::SecretContractRejected));
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::Phase2ArtifactRejected));
}

#[test]
fn readonly_flag_does_not_allow_paper_write() {
    let matrix = accepted_matrix(false, false);
    let verdict = evaluate_feature_flag_secret_auth_matrix(&matrix, paper_submit_request(), NOW_MS);

    assert!(!verdict.allowed);
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::PaperFlagDisabled));
    assert!(!verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::ReadonlyFlagDisabled));
}

#[test]
fn paper_flag_does_not_allow_live_or_account_write_paths() {
    let matrix = accepted_matrix(true, false);
    let live_request = BrokerCapabilityRequest {
        environment: BrokerEnvironment::LiveReservedDenied,
        operation: BrokerOperation::LiveOrderSubmit,
        ..paper_submit_request()
    };
    let verdict = evaluate_feature_flag_secret_auth_matrix(&matrix, live_request, NOW_MS);

    assert!(!verdict.allowed);
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::LiveEnvironmentDenied));
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::LiveOrAccountWriteOperationDenied));
}

#[test]
fn shadow_only_blocks_paper_even_when_readonly_and_paper_flags_are_enabled() {
    let matrix = accepted_matrix(true, true);
    let verdict = evaluate_feature_flag_secret_auth_matrix(&matrix, paper_submit_request(), NOW_MS);

    assert!(!verdict.allowed);
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::ShadowOnlyBlocksPaper));
}

#[test]
fn gui_lane_state_cannot_override_server_rust_matrix() {
    let mut matrix = accepted_matrix(true, false);
    matrix.gui_lane_state_override_denied = false;
    let verdict = evaluate_feature_flag_secret_auth_matrix(&matrix, paper_submit_request(), NOW_MS);

    assert!(!verdict.allowed);
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::GuiLaneStateOverrideNotDenied));
}

#[test]
fn accepted_paper_matrix_requires_matching_secret_artifact_session_and_envelope() {
    let matrix = accepted_matrix(true, false);
    let verdict = evaluate_feature_flag_secret_auth_matrix(&matrix, paper_submit_request(), NOW_MS);

    assert!(verdict.allowed);
    assert_eq!(
        matrix.contract_id,
        FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID
    );
    assert_eq!(matrix.source_version, 1);
    assert_eq!(
        verdict.effective_authority_scope,
        AuthorityScope::PaperRehearsal
    );

    let mut mismatched = matrix.clone();
    mismatched.authorization_envelope.account_fingerprint_hash = "9".repeat(64);
    let mismatch_verdict =
        evaluate_feature_flag_secret_auth_matrix(&mismatched, paper_submit_request(), NOW_MS);
    assert!(!mismatch_verdict.allowed);
    assert!(mismatch_verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::AccountFingerprintMismatch));
}

#[test]
fn feature_flag_secret_auth_matrix_requires_exact_contract_id_and_version() {
    let matrix = FeatureFlagSecretAuthMatrixV1 {
        contract_id: "feature_flag_secret_auth_matrix_v1_fixture".to_string(),
        source_version: 2,
        ..accepted_matrix(true, false)
    };
    let verdict = evaluate_feature_flag_secret_auth_matrix(&matrix, paper_submit_request(), NOW_MS);

    assert!(!verdict.allowed);
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&FeatureFlagSecretAuthBlocker::SourceVersionMismatch));
}

#[test]
fn source_auth_matrix_template_is_default_blocked_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/ibkr_feature_flag_secret_auth_matrix.toml"),
    )
    .expect("read feature flag secret auth matrix template");
    let parsed: toml::Value = toml::from_str(&raw).expect("auth matrix template toml parses");

    assert_eq!(
        parsed["flags"]["stock_etf_lane_enabled"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["flags"]["ibkr_readonly_enabled"].as_bool(),
        Some(false)
    );
    assert_eq!(parsed["flags"]["ibkr_paper_enabled"].as_bool(), Some(false));
    assert_eq!(
        parsed["flags"]["asset_lane_default"].as_str(),
        Some("crypto_perp")
    );
    assert_eq!(
        parsed["authorization_envelope"]["permission_scope"].as_str(),
        Some("denied")
    );
    assert_eq!(parsed["matrix"]["contract_id"].as_str(), Some(""));
    assert_eq!(parsed["matrix"]["source_version"].as_integer(), Some(0));
    assert_eq!(
        parsed["matrix"]["server_rust_matrix_authoritative"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["matrix"]["gui_lane_state_override_denied"].as_bool(),
        Some(false)
    );

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}
