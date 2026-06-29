//! ADR-0048 IBKR Phase 2 prerequisite policy acceptance tests.
//!
//! These tests validate source policy contracts only. They must not perform
//! redaction, rate limiting, audit writes, secret lookup, socket I/O, or broker
//! order routing.

use std::path::PathBuf;

use openclaw_types::{
    IbkrAuditEventPolicyBlocker, IbkrAuditEventPolicyV1, IbkrExternalSurfaceGateV1,
    IbkrPaperAttestationPolicyBlocker, IbkrPaperAttestationPolicyV1, IbkrPhase2PolicyBundleBlocker,
    IbkrPhase2PolicyBundleV1, IbkrPythonWriteGuardPolicyBlocker, IbkrPythonWriteGuardPolicyV1,
    IbkrRateLimitPolicyBlocker, IbkrRateLimitPolicyV1, IbkrRateLimitScope,
    IbkrRedactionPolicyBlocker, IbkrRedactionPolicyV1,
};

#[test]
fn default_policy_bundle_blocks_all_gate_prerequisites() {
    let bundle = IbkrPhase2PolicyBundleV1::default();
    let verdict = bundle.validate();
    let flags = bundle.gate_prerequisite_flags();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2PolicyBundleBlocker::RedactionPolicyRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2PolicyBundleBlocker::RateLimitPolicyRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2PolicyBundleBlocker::AuditEventPolicyRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2PolicyBundleBlocker::PaperAttestationPolicyRejected));
    assert!(verdict
        .blockers
        .contains(&IbkrPhase2PolicyBundleBlocker::PythonWriteGuardPolicyRejected));

    assert!(!flags.redaction_suite_passed);
    assert!(!flags.rate_limit_policy_present);
    assert!(!flags.audit_event_policy_present);
    assert!(!flags.paper_attestation_contract_present);
    assert!(!flags.python_no_write_guard_present);
}

#[test]
fn source_policy_bundle_satisfies_gate_prerequisites_without_contact() {
    let bundle = IbkrPhase2PolicyBundleV1::source_template();
    let verdict = bundle.validate();
    let flags = bundle.gate_prerequisite_flags();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert!(flags.redaction_suite_passed);
    assert!(flags.rate_limit_policy_present);
    assert!(flags.audit_event_policy_present);
    assert!(flags.paper_attestation_contract_present);
    assert!(flags.python_no_write_guard_present);

    let gate = IbkrExternalSurfaceGateV1 {
        redaction_suite_passed: flags.redaction_suite_passed,
        rate_limit_policy_present: flags.rate_limit_policy_present,
        audit_event_policy_present: flags.audit_event_policy_present,
        paper_attestation_contract_present: flags.paper_attestation_contract_present,
        python_no_write_guard_present: flags.python_no_write_guard_present,
        ..IbkrExternalSurfaceGateV1::passing_fixture()
    };
    assert!(gate.can_contact_ibkr());
}

#[test]
fn redaction_policy_denies_secret_account_cookie_token_path_and_stack_trace_leaks() {
    let policy = IbkrRedactionPolicyV1 {
        account_id_in_logs_allowed: true,
        secret_in_logs_allowed: true,
        local_path_in_logs_allowed: true,
        cookie_in_logs_allowed: true,
        token_in_logs_allowed: true,
        raw_payload_in_logs_allowed: true,
        stack_trace_in_reports_allowed: true,
        ..IbkrRedactionPolicyV1::source_template()
    };
    let verdict = policy.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrRedactionPolicyBlocker::AccountIdLogLeakAllowed));
    assert!(verdict
        .blockers
        .contains(&IbkrRedactionPolicyBlocker::SecretLogLeakAllowed));
    assert!(verdict
        .blockers
        .contains(&IbkrRedactionPolicyBlocker::LocalPathLogLeakAllowed));
    assert!(verdict
        .blockers
        .contains(&IbkrRedactionPolicyBlocker::CookieLogLeakAllowed));
    assert!(verdict
        .blockers
        .contains(&IbkrRedactionPolicyBlocker::TokenLogLeakAllowed));
    assert!(verdict
        .blockers
        .contains(&IbkrRedactionPolicyBlocker::RawPayloadLogLeakAllowed));
    assert!(verdict
        .blockers
        .contains(&IbkrRedactionPolicyBlocker::StackTraceReportLeakAllowed));
}

#[test]
fn rate_limit_policy_requires_per_action_buckets_and_circuit_breaker() {
    let policy = IbkrRateLimitPolicyV1 {
        scope: IbkrRateLimitScope::GlobalOnly,
        min_request_spacing_ms: 0,
        max_in_flight_requests: 0,
        per_action_buckets_present: false,
        pacing_violation_circuit_breaker_present: false,
        read_snapshot_budget_present: false,
        market_data_subscription_budget_present: false,
        paper_order_write_budget_present: false,
        ..IbkrRateLimitPolicyV1::source_template()
    };
    let verdict = policy.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrRateLimitPolicyBlocker::ScopeNotPerAction));
    assert!(verdict
        .blockers
        .contains(&IbkrRateLimitPolicyBlocker::RequestSpacingMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrRateLimitPolicyBlocker::ConcurrencyLimitMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrRateLimitPolicyBlocker::PerActionBucketsMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrRateLimitPolicyBlocker::PacingCircuitBreakerMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrRateLimitPolicyBlocker::ReadSnapshotBudgetMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrRateLimitPolicyBlocker::MarketDataSubscriptionBudgetMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrRateLimitPolicyBlocker::PaperOrderWriteBudgetMissing));
}

#[test]
fn audit_event_policy_requires_append_only_lane_fields_and_hashes() {
    let policy = IbkrAuditEventPolicyV1 {
        append_only_required: false,
        asset_lane_required: false,
        broker_required: false,
        environment_required: false,
        operation_required: false,
        allowed_required: false,
        denial_reason_required: false,
        source_artifact_hash_required: false,
        raw_artifact_hash_required: false,
        redacted_summary_hash_required: false,
        account_fingerprint_hash_only: false,
        raw_payload_storage_allowed: true,
        ..IbkrAuditEventPolicyV1::source_template()
    };
    let verdict = policy.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::AppendOnlyMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::AssetLaneMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::BrokerMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::EnvironmentMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::OperationMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::AllowedMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::DenialReasonMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::SourceArtifactHashMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::RawArtifactHashMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::RedactedSummaryHashMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::AccountFingerprintHashOnlyMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrAuditEventPolicyBlocker::RawPayloadStorageAllowed));
}

#[test]
fn paper_attestation_policy_requires_rust_scope_and_denies_live_margin() {
    let policy = IbkrPaperAttestationPolicyV1 {
        external_surface_gate_required: false,
        session_attestation_required: false,
        rust_lane_scoped_ipc_required: false,
        scoped_authorization_required: false,
        decision_lease_required: false,
        guardian_required: false,
        risk_config_hash_required: false,
        instrument_identity_hash_required: false,
        idempotency_key_required: false,
        lifecycle_event_log_required: false,
        reconciliation_required_before_terminal: false,
        paper_environment_only: false,
        live_account_fingerprint_denied: false,
        margin_short_options_cfd_denied: false,
        max_paper_notional_required: false,
        ..IbkrPaperAttestationPolicyV1::source_template()
    };
    let verdict = policy.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrPaperAttestationPolicyBlocker::ExternalSurfaceGateMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperAttestationPolicyBlocker::SessionAttestationMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperAttestationPolicyBlocker::RustLaneScopedIpcMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperAttestationPolicyBlocker::ScopedAuthorizationMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperAttestationPolicyBlocker::DecisionLeaseMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperAttestationPolicyBlocker::GuardianMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperAttestationPolicyBlocker::PaperEnvironmentOnlyMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperAttestationPolicyBlocker::LiveAccountFingerprintNotDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrPaperAttestationPolicyBlocker::MarginShortOptionsCfdNotDenied));
}

#[test]
fn python_write_guard_denies_python_broker_writes_without_bybit_mutation() {
    let policy = IbkrPythonWriteGuardPolicyV1 {
        python_broker_write_authority_denied: false,
        python_can_read_display_import: false,
        python_can_call_rust_lane_ipc: false,
        python_ibkr_order_methods_denied: false,
        python_live_secret_access_denied: false,
        gui_cannot_override_authority: false,
        bybit_paths_unmodified: false,
        ..IbkrPythonWriteGuardPolicyV1::source_template()
    };
    let verdict = policy.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrPythonWriteGuardPolicyBlocker::PythonBrokerWriteAuthorityNotDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrPythonWriteGuardPolicyBlocker::PythonReadDisplayImportMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPythonWriteGuardPolicyBlocker::PythonRustIpcBridgeMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrPythonWriteGuardPolicyBlocker::PythonIbkrOrderMethodsNotDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrPythonWriteGuardPolicyBlocker::PythonLiveSecretAccessNotDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrPythonWriteGuardPolicyBlocker::GuiAuthorityOverrideNotDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrPythonWriteGuardPolicyBlocker::BybitPathMutationNotAccounted));
}

#[test]
fn source_policy_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(srv_root.join("settings/broker/ibkr_phase2_policies.toml"))
        .expect("read ibkr phase2 policies template");
    let parsed: toml::Value = toml::from_str(&raw).expect("policy toml parses");

    assert_eq!(
        parsed["redaction"]["raw_payload_hash_required"].as_bool(),
        Some(true)
    );
    assert_eq!(
        parsed["redaction"]["secret_in_logs_allowed"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["rate_limit"]["scope"].as_str(),
        Some("global_and_per_action")
    );
    assert_eq!(
        parsed["audit_event"]["account_fingerprint_hash_only"].as_bool(),
        Some(true)
    );
    assert_eq!(
        parsed["paper_attestation"]["rust_lane_scoped_ipc_required"].as_bool(),
        Some(true)
    );
    assert_eq!(
        parsed["python_write_guard"]["bybit_paths_unmodified"].as_bool(),
        Some(true)
    );

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}
