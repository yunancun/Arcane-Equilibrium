//! ADR-0048 IBKR feature-flag/secret/scoped-auth matrix acceptance tests.
//!
//! These tests validate source contract behavior only. They must not read
//! secrets, contact IBKR, construct a connector, or route paper/live orders.

use std::path::PathBuf;

use openclaw_types::{
    evaluate_feature_flag_secret_auth_matrix, AssetLane, AuthorityScope, Broker,
    BrokerCapabilityRequest, BrokerEnvironment, BrokerOperation, FeatureFlagSecretAuthBlocker,
    FeatureFlagSecretAuthMatrixV1, IbkrApiSessionTopologyV1, IbkrExternalSurfaceGateV1,
    IbkrPhase2GateArtifactV1, IbkrPhase2PolicyBundleV1, IbkrSecretSlotContractV1,
    IbkrSessionAttestationV1, InstrumentKind, StockEtfAuthorizationEnvelopeV1,
    StockEtfFeatureFlags, FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID,
    IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
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
        contract_id: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string(),
        source_version: 1,
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
    use FeatureFlagSecretAuthBlocker as Blocker;

    let verdict = evaluate_feature_flag_secret_auth_matrix(
        &FeatureFlagSecretAuthMatrixV1::default(),
        paper_submit_request(),
        NOW_MS,
    );

    assert!(!verdict.allowed);
    assert_eq!(verdict.effective_authority_scope, AuthorityScope::Denied);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::ServerRustMatrixNotAuthoritative,
            Blocker::GuiLaneStateOverrideNotDenied,
            Blocker::LaneFlagDisabled,
            Blocker::PaperFlagDisabled,
            Blocker::ShadowOnlyBlocksPaper,
            Blocker::SecretContractRejected,
            Blocker::LiveSecretAbsentOrEmptyNotProven,
            Blocker::Phase2ArtifactRejected,
            Blocker::SessionAttestationRejected,
            Blocker::AuthorizationEnvelopeMismatch,
            Blocker::PermissionScopeMismatch,
            Blocker::SecretSlotFingerprintInvalid,
            Blocker::AccountFingerprintHashInvalid,
            Blocker::RiskConfigHashInvalid,
            Blocker::AuthorizationEnvelopeExpired,
        ]
    );
}

#[test]
fn readonly_flag_does_not_allow_paper_write() {
    let matrix = accepted_matrix(false, false);
    let verdict = evaluate_feature_flag_secret_auth_matrix(&matrix, paper_submit_request(), NOW_MS);

    assert!(!verdict.allowed);
    assert_eq!(
        verdict.blockers,
        vec![FeatureFlagSecretAuthBlocker::PaperFlagDisabled]
    );
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
    assert_eq!(
        verdict.blockers,
        vec![
            FeatureFlagSecretAuthBlocker::LiveEnvironmentDenied,
            FeatureFlagSecretAuthBlocker::LiveOrAccountWriteOperationDenied,
            FeatureFlagSecretAuthBlocker::AuthorizationEnvelopeMismatch,
            FeatureFlagSecretAuthBlocker::PermissionScopeMismatch,
        ]
    );
}

#[test]
fn shadow_only_blocks_paper_even_when_readonly_and_paper_flags_are_enabled() {
    let matrix = accepted_matrix(true, true);
    let verdict = evaluate_feature_flag_secret_auth_matrix(&matrix, paper_submit_request(), NOW_MS);

    assert!(!verdict.allowed);
    assert_eq!(
        verdict.blockers,
        vec![FeatureFlagSecretAuthBlocker::ShadowOnlyBlocksPaper]
    );
}

#[test]
fn gui_lane_state_cannot_override_server_rust_matrix() {
    let mut matrix = accepted_matrix(true, false);
    matrix.gui_lane_state_override_denied = false;
    let verdict = evaluate_feature_flag_secret_auth_matrix(&matrix, paper_submit_request(), NOW_MS);

    assert!(!verdict.allowed);
    assert_eq!(
        verdict.blockers,
        vec![FeatureFlagSecretAuthBlocker::GuiLaneStateOverrideNotDenied]
    );
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
    assert_eq!(
        mismatch_verdict.blockers,
        vec![FeatureFlagSecretAuthBlocker::AccountFingerprintMismatch]
    );
}

#[test]
fn feature_flag_secret_auth_rejects_each_authority_gap_independently() {
    use FeatureFlagSecretAuthBlocker as Blocker;

    let cases: [(
        fn(&mut FeatureFlagSecretAuthMatrixV1, &mut BrokerCapabilityRequest),
        Blocker,
    ); 21] = [
        (
            |matrix, _| {
                matrix.contract_id = "feature_flag_secret_auth_matrix_v1_fixture".to_string()
            },
            Blocker::ContractIdMismatch,
        ),
        (
            |matrix, _| matrix.source_version = 2,
            Blocker::SourceVersionMismatch,
        ),
        (
            |matrix, _| matrix.server_rust_matrix_authoritative = false,
            Blocker::ServerRustMatrixNotAuthoritative,
        ),
        (
            |matrix, _| matrix.gui_lane_state_override_denied = false,
            Blocker::GuiLaneStateOverrideNotDenied,
        ),
        (
            |matrix, request| {
                request.asset_lane = AssetLane::CryptoPerp;
                matrix.authorization_envelope.asset_lane = AssetLane::CryptoPerp;
            },
            Blocker::WrongAssetLane,
        ),
        (
            |matrix, request| {
                request.broker = Broker::Bybit;
                matrix.authorization_envelope.broker = Broker::Bybit;
            },
            Blocker::WrongBroker,
        ),
        (
            |matrix, request| {
                request.environment = BrokerEnvironment::LiveReservedDenied;
                matrix.authorization_envelope.environment = BrokerEnvironment::LiveReservedDenied;
            },
            Blocker::LiveEnvironmentDenied,
        ),
        (
            |_, request| request.instrument_kind = InstrumentKind::CryptoPerp,
            Blocker::InstrumentKindDenied,
        ),
        (
            |matrix, request| {
                request.operation = BrokerOperation::LiveOrderSubmit;
                matrix.authorization_envelope.permission_scope = AuthorityScope::Denied;
            },
            Blocker::LiveOrAccountWriteOperationDenied,
        ),
        (
            |matrix, _| matrix.flags.stock_etf_lane_enabled = false,
            Blocker::LaneFlagDisabled,
        ),
        (
            |matrix, request| {
                request.operation = BrokerOperation::HealthRead;
                matrix.authorization_envelope.permission_scope = AuthorityScope::ReadOnly;
                matrix.flags.ibkr_readonly_enabled = false;
            },
            Blocker::ReadonlyFlagDisabled,
        ),
        (
            |matrix, _| matrix.flags.ibkr_paper_enabled = false,
            Blocker::PaperFlagDisabled,
        ),
        (
            |matrix, _| matrix.flags.stock_etf_shadow_only = true,
            Blocker::ShadowOnlyBlocksPaper,
        ),
        (
            |matrix, _| {
                matrix.secret_slot_contract.contract_id =
                    "ibkr_secret_slot_contract_v1_fixture".to_string()
            },
            Blocker::SecretContractRejected,
        ),
        (
            |matrix, _| matrix.phase2_gate_artifact.artifact_id = String::new(),
            Blocker::Phase2ArtifactRejected,
        ),
        (
            |matrix, _| {
                matrix.session_attestation.contract_id =
                    "ibkr_session_attestation_v1_fixture".to_string()
            },
            Blocker::SessionAttestationRejected,
        ),
        (
            |matrix, _| matrix.authorization_envelope.environment = BrokerEnvironment::ReadOnly,
            Blocker::AuthorizationEnvelopeMismatch,
        ),
        (
            |matrix, _| matrix.authorization_envelope.permission_scope = AuthorityScope::ReadOnly,
            Blocker::PermissionScopeMismatch,
        ),
        (
            |matrix, _| matrix.authorization_envelope.risk_config_hash = "risk_hash".to_string(),
            Blocker::RiskConfigHashInvalid,
        ),
        (
            |matrix, _| matrix.authorization_envelope.expires_at_ms = NOW_MS,
            Blocker::AuthorizationEnvelopeExpired,
        ),
        (
            |matrix, _| matrix.authorization_envelope.secret_slot_fingerprint = "c".repeat(64),
            Blocker::SecretSlotFingerprintMismatch,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut matrix = accepted_matrix(true, false);
        let mut request = paper_submit_request();
        mutate(&mut matrix, &mut request);
        assert_single_feature_flag_secret_auth_blocker(
            evaluate_feature_flag_secret_auth_matrix(&matrix, request, NOW_MS),
            blocker,
        );
    }

    let mut account_mismatch = accepted_matrix(true, false);
    account_mismatch
        .authorization_envelope
        .account_fingerprint_hash = "c".repeat(64);
    assert_single_feature_flag_secret_auth_blocker(
        evaluate_feature_flag_secret_auth_matrix(&account_mismatch, paper_submit_request(), NOW_MS),
        Blocker::AccountFingerprintMismatch,
    );
}

#[test]
fn feature_flag_secret_auth_preserves_aggregate_lineage_failures_when_hashes_are_invalid() {
    let mut secret_live_missing = accepted_matrix(true, false);
    secret_live_missing
        .secret_slot_contract
        .live_secret_absent_or_empty = false;
    let verdict = evaluate_feature_flag_secret_auth_matrix(
        &secret_live_missing,
        paper_submit_request(),
        NOW_MS,
    );
    assert!(!verdict.allowed);
    assert_eq!(
        verdict.blockers,
        vec![
            FeatureFlagSecretAuthBlocker::SecretContractRejected,
            FeatureFlagSecretAuthBlocker::LiveSecretAbsentOrEmptyNotProven,
        ]
    );

    let mut invalid_secret_hash = accepted_matrix(true, false);
    invalid_secret_hash
        .authorization_envelope
        .secret_slot_fingerprint = "paper_secret_slot_fingerprint".to_string();
    let verdict = evaluate_feature_flag_secret_auth_matrix(
        &invalid_secret_hash,
        paper_submit_request(),
        NOW_MS,
    );
    assert!(!verdict.allowed);
    assert_eq!(
        verdict.blockers,
        vec![
            FeatureFlagSecretAuthBlocker::SecretSlotFingerprintInvalid,
            FeatureFlagSecretAuthBlocker::SecretSlotFingerprintMismatch,
        ]
    );

    let mut invalid_account_hash = accepted_matrix(true, false);
    invalid_account_hash
        .authorization_envelope
        .account_fingerprint_hash = "paper_account_fingerprint".to_string();
    let verdict = evaluate_feature_flag_secret_auth_matrix(
        &invalid_account_hash,
        paper_submit_request(),
        NOW_MS,
    );
    assert!(!verdict.allowed);
    assert_eq!(
        verdict.blockers,
        vec![
            FeatureFlagSecretAuthBlocker::AccountFingerprintHashInvalid,
            FeatureFlagSecretAuthBlocker::AccountFingerprintMismatch,
        ]
    );
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
    assert_eq!(
        verdict.blockers,
        vec![
            FeatureFlagSecretAuthBlocker::ContractIdMismatch,
            FeatureFlagSecretAuthBlocker::SourceVersionMismatch,
        ]
    );
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

fn assert_single_feature_flag_secret_auth_blocker(
    verdict: openclaw_types::FeatureFlagSecretAuthVerdict,
    blocker: FeatureFlagSecretAuthBlocker,
) {
    assert!(!verdict.allowed);
    assert_eq!(verdict.effective_authority_scope, AuthorityScope::Denied);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
