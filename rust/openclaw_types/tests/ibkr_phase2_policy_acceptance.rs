//! ADR-0048 IBKR Phase 2 prerequisite policy acceptance tests.
//!
//! These tests validate source policy contracts only. They must not perform
//! redaction, rate limiting, audit writes, secret lookup, socket I/O, or broker
//! order routing.

use std::path::PathBuf;

use openclaw_types::{
    IbkrAuditEventPolicyBlocker, IbkrAuditEventPolicyV1, IbkrExternalSurfaceGateV1,
    IbkrPaperAttestationPolicyBlocker, IbkrPaperAttestationPolicyV1, IbkrPhase2PolicyBundleBlocker,
    IbkrPhase2PolicyBundleV1, IbkrPolicyVerdict, IbkrPythonWriteGuardPolicyBlocker,
    IbkrPythonWriteGuardPolicyV1, IbkrRateLimitPolicyBlocker, IbkrRateLimitPolicyV1,
    IbkrRateLimitScope, IbkrRedactionPolicyBlocker, IbkrRedactionPolicyV1,
    IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID, IBKR_PAPER_ATTESTATION_CONTRACT_ID,
    IBKR_PYTHON_WRITE_GUARD_POLICY_CONTRACT_ID, IBKR_RATE_LIMIT_POLICY_CONTRACT_ID,
    IBKR_REDACTION_POLICY_CONTRACT_ID,
};

#[test]
fn default_policy_bundle_blocks_all_gate_prerequisites() {
    let bundle = IbkrPhase2PolicyBundleV1::default();
    let verdict = bundle.validate();
    let flags = bundle.gate_prerequisite_flags();

    assert!(!verdict.accepted);
    assert_policy_blockers(
        verdict,
        &[
            IbkrPhase2PolicyBundleBlocker::RedactionPolicyRejected,
            IbkrPhase2PolicyBundleBlocker::RateLimitPolicyRejected,
            IbkrPhase2PolicyBundleBlocker::AuditEventPolicyRejected,
            IbkrPhase2PolicyBundleBlocker::PaperAttestationPolicyRejected,
            IbkrPhase2PolicyBundleBlocker::PythonWriteGuardPolicyRejected,
        ],
    );

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
    assert_eq!(
        bundle.redaction.contract_id,
        IBKR_REDACTION_POLICY_CONTRACT_ID
    );
    assert_eq!(bundle.redaction.source_version, 1);
    assert_eq!(
        bundle.rate_limit.contract_id,
        IBKR_RATE_LIMIT_POLICY_CONTRACT_ID
    );
    assert_eq!(bundle.rate_limit.source_version, 1);
    assert_eq!(
        bundle.audit_event.contract_id,
        IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID
    );
    assert_eq!(bundle.audit_event.source_version, 1);
    assert_eq!(
        bundle.paper_attestation.contract_id,
        IBKR_PAPER_ATTESTATION_CONTRACT_ID
    );
    assert_eq!(bundle.paper_attestation.source_version, 1);
    assert_eq!(
        bundle.python_write_guard.contract_id,
        IBKR_PYTHON_WRITE_GUARD_POLICY_CONTRACT_ID
    );
    assert_eq!(bundle.python_write_guard.source_version, 1);

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
fn source_policies_require_exact_contract_ids_and_versions() {
    let redaction = IbkrRedactionPolicyV1 {
        contract_id: "ibkr_redaction_policy_v1_fixture".to_string(),
        source_version: 2,
        ..IbkrRedactionPolicyV1::source_template()
    };
    let verdict = redaction.validate();
    assert_policy_blockers(
        verdict,
        &[
            IbkrRedactionPolicyBlocker::ContractIdMismatch,
            IbkrRedactionPolicyBlocker::SourceVersionMismatch,
        ],
    );

    let rate_limit = IbkrRateLimitPolicyV1 {
        contract_id: "ibkr_rate_limit_policy_v1_fixture".to_string(),
        source_version: 2,
        ..IbkrRateLimitPolicyV1::source_template()
    };
    let verdict = rate_limit.validate();
    assert_policy_blockers(
        verdict,
        &[
            IbkrRateLimitPolicyBlocker::ContractIdMismatch,
            IbkrRateLimitPolicyBlocker::SourceVersionMismatch,
        ],
    );

    let audit_event = IbkrAuditEventPolicyV1 {
        contract_id: "ibkr_audit_event_policy_v1_fixture".to_string(),
        source_version: 2,
        ..IbkrAuditEventPolicyV1::source_template()
    };
    let verdict = audit_event.validate();
    assert_policy_blockers(
        verdict,
        &[
            IbkrAuditEventPolicyBlocker::ContractIdMismatch,
            IbkrAuditEventPolicyBlocker::SourceVersionMismatch,
        ],
    );

    let paper_attestation = IbkrPaperAttestationPolicyV1 {
        contract_id: "ibkr_paper_attestation_v1_fixture".to_string(),
        source_version: 2,
        ..IbkrPaperAttestationPolicyV1::source_template()
    };
    let verdict = paper_attestation.validate();
    assert_policy_blockers(
        verdict,
        &[
            IbkrPaperAttestationPolicyBlocker::ContractIdMismatch,
            IbkrPaperAttestationPolicyBlocker::SourceVersionMismatch,
        ],
    );

    let python_write_guard = IbkrPythonWriteGuardPolicyV1 {
        contract_id: "ibkr_python_write_guard_policy_v1_fixture".to_string(),
        source_version: 2,
        ..IbkrPythonWriteGuardPolicyV1::source_template()
    };
    let verdict = python_write_guard.validate();
    assert_policy_blockers(
        verdict,
        &[
            IbkrPythonWriteGuardPolicyBlocker::ContractIdMismatch,
            IbkrPythonWriteGuardPolicyBlocker::SourceVersionMismatch,
        ],
    );
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

    assert_policy_blockers(
        verdict,
        &[
            IbkrRedactionPolicyBlocker::AccountIdLogLeakAllowed,
            IbkrRedactionPolicyBlocker::SecretLogLeakAllowed,
            IbkrRedactionPolicyBlocker::LocalPathLogLeakAllowed,
            IbkrRedactionPolicyBlocker::CookieLogLeakAllowed,
            IbkrRedactionPolicyBlocker::TokenLogLeakAllowed,
            IbkrRedactionPolicyBlocker::RawPayloadLogLeakAllowed,
            IbkrRedactionPolicyBlocker::StackTraceReportLeakAllowed,
        ],
    );
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

    assert_policy_blockers(
        verdict,
        &[
            IbkrRateLimitPolicyBlocker::ScopeNotPerAction,
            IbkrRateLimitPolicyBlocker::RequestSpacingMissing,
            IbkrRateLimitPolicyBlocker::ConcurrencyLimitMissing,
            IbkrRateLimitPolicyBlocker::PerActionBucketsMissing,
            IbkrRateLimitPolicyBlocker::PacingCircuitBreakerMissing,
            IbkrRateLimitPolicyBlocker::ReadSnapshotBudgetMissing,
            IbkrRateLimitPolicyBlocker::MarketDataSubscriptionBudgetMissing,
            IbkrRateLimitPolicyBlocker::PaperOrderWriteBudgetMissing,
        ],
    );
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

    assert_policy_blockers(
        verdict,
        &[
            IbkrAuditEventPolicyBlocker::AppendOnlyMissing,
            IbkrAuditEventPolicyBlocker::AssetLaneMissing,
            IbkrAuditEventPolicyBlocker::BrokerMissing,
            IbkrAuditEventPolicyBlocker::EnvironmentMissing,
            IbkrAuditEventPolicyBlocker::OperationMissing,
            IbkrAuditEventPolicyBlocker::AllowedMissing,
            IbkrAuditEventPolicyBlocker::DenialReasonMissing,
            IbkrAuditEventPolicyBlocker::SourceArtifactHashMissing,
            IbkrAuditEventPolicyBlocker::RawArtifactHashMissing,
            IbkrAuditEventPolicyBlocker::RedactedSummaryHashMissing,
            IbkrAuditEventPolicyBlocker::AccountFingerprintHashOnlyMissing,
            IbkrAuditEventPolicyBlocker::RawPayloadStorageAllowed,
        ],
    );
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

    assert_policy_blockers(
        verdict,
        &[
            IbkrPaperAttestationPolicyBlocker::ExternalSurfaceGateMissing,
            IbkrPaperAttestationPolicyBlocker::SessionAttestationMissing,
            IbkrPaperAttestationPolicyBlocker::RustLaneScopedIpcMissing,
            IbkrPaperAttestationPolicyBlocker::ScopedAuthorizationMissing,
            IbkrPaperAttestationPolicyBlocker::DecisionLeaseMissing,
            IbkrPaperAttestationPolicyBlocker::GuardianMissing,
            IbkrPaperAttestationPolicyBlocker::RiskConfigHashMissing,
            IbkrPaperAttestationPolicyBlocker::InstrumentIdentityHashMissing,
            IbkrPaperAttestationPolicyBlocker::IdempotencyKeyMissing,
            IbkrPaperAttestationPolicyBlocker::LifecycleEventLogMissing,
            IbkrPaperAttestationPolicyBlocker::ReconciliationBeforeTerminalMissing,
            IbkrPaperAttestationPolicyBlocker::PaperEnvironmentOnlyMissing,
            IbkrPaperAttestationPolicyBlocker::LiveAccountFingerprintNotDenied,
            IbkrPaperAttestationPolicyBlocker::MarginShortOptionsCfdNotDenied,
            IbkrPaperAttestationPolicyBlocker::MaxPaperNotionalMissing,
        ],
    );
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

    assert_policy_blockers(
        verdict,
        &[
            IbkrPythonWriteGuardPolicyBlocker::PythonBrokerWriteAuthorityNotDenied,
            IbkrPythonWriteGuardPolicyBlocker::PythonReadDisplayImportMissing,
            IbkrPythonWriteGuardPolicyBlocker::PythonRustIpcBridgeMissing,
            IbkrPythonWriteGuardPolicyBlocker::PythonIbkrOrderMethodsNotDenied,
            IbkrPythonWriteGuardPolicyBlocker::PythonLiveSecretAccessNotDenied,
            IbkrPythonWriteGuardPolicyBlocker::GuiAuthorityOverrideNotDenied,
            IbkrPythonWriteGuardPolicyBlocker::BybitPathMutationNotAccounted,
        ],
    );
}

#[test]
fn redaction_policy_rejects_each_leak_and_missing_hash_independently() {
    use IbkrRedactionPolicyBlocker as Blocker;

    let cases: [(fn(&mut IbkrRedactionPolicyV1), Blocker); 9] = [
        (
            |policy| policy.raw_payload_hash_required = false,
            Blocker::RawPayloadHashNotRequired,
        ),
        (
            |policy| policy.redacted_summary_hash_required = false,
            Blocker::RedactedSummaryHashNotRequired,
        ),
        (
            |policy| policy.account_id_in_logs_allowed = true,
            Blocker::AccountIdLogLeakAllowed,
        ),
        (
            |policy| policy.secret_in_logs_allowed = true,
            Blocker::SecretLogLeakAllowed,
        ),
        (
            |policy| policy.local_path_in_logs_allowed = true,
            Blocker::LocalPathLogLeakAllowed,
        ),
        (
            |policy| policy.cookie_in_logs_allowed = true,
            Blocker::CookieLogLeakAllowed,
        ),
        (
            |policy| policy.token_in_logs_allowed = true,
            Blocker::TokenLogLeakAllowed,
        ),
        (
            |policy| policy.raw_payload_in_logs_allowed = true,
            Blocker::RawPayloadLogLeakAllowed,
        ),
        (
            |policy| policy.stack_trace_in_reports_allowed = true,
            Blocker::StackTraceReportLeakAllowed,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut policy = IbkrRedactionPolicyV1::source_template();
        mutate(&mut policy);
        assert_single_policy_blocker(policy.validate(), blocker);
    }
}

#[test]
fn rate_limit_policy_rejects_each_budget_gap_independently() {
    use IbkrRateLimitPolicyBlocker as Blocker;

    let cases: [(fn(&mut IbkrRateLimitPolicyV1), Blocker); 8] = [
        (
            |policy| policy.scope = IbkrRateLimitScope::GlobalOnly,
            Blocker::ScopeNotPerAction,
        ),
        (
            |policy| policy.min_request_spacing_ms = 0,
            Blocker::RequestSpacingMissing,
        ),
        (
            |policy| policy.max_in_flight_requests = 0,
            Blocker::ConcurrencyLimitMissing,
        ),
        (
            |policy| policy.per_action_buckets_present = false,
            Blocker::PerActionBucketsMissing,
        ),
        (
            |policy| policy.pacing_violation_circuit_breaker_present = false,
            Blocker::PacingCircuitBreakerMissing,
        ),
        (
            |policy| policy.read_snapshot_budget_present = false,
            Blocker::ReadSnapshotBudgetMissing,
        ),
        (
            |policy| policy.market_data_subscription_budget_present = false,
            Blocker::MarketDataSubscriptionBudgetMissing,
        ),
        (
            |policy| policy.paper_order_write_budget_present = false,
            Blocker::PaperOrderWriteBudgetMissing,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut policy = IbkrRateLimitPolicyV1::source_template();
        mutate(&mut policy);
        assert_single_policy_blocker(policy.validate(), blocker);
    }
}

#[test]
fn audit_event_policy_rejects_each_lineage_gap_independently() {
    use IbkrAuditEventPolicyBlocker as Blocker;

    let cases: [(fn(&mut IbkrAuditEventPolicyV1), Blocker); 12] = [
        (
            |policy| policy.append_only_required = false,
            Blocker::AppendOnlyMissing,
        ),
        (
            |policy| policy.asset_lane_required = false,
            Blocker::AssetLaneMissing,
        ),
        (
            |policy| policy.broker_required = false,
            Blocker::BrokerMissing,
        ),
        (
            |policy| policy.environment_required = false,
            Blocker::EnvironmentMissing,
        ),
        (
            |policy| policy.operation_required = false,
            Blocker::OperationMissing,
        ),
        (
            |policy| policy.allowed_required = false,
            Blocker::AllowedMissing,
        ),
        (
            |policy| policy.denial_reason_required = false,
            Blocker::DenialReasonMissing,
        ),
        (
            |policy| policy.source_artifact_hash_required = false,
            Blocker::SourceArtifactHashMissing,
        ),
        (
            |policy| policy.raw_artifact_hash_required = false,
            Blocker::RawArtifactHashMissing,
        ),
        (
            |policy| policy.redacted_summary_hash_required = false,
            Blocker::RedactedSummaryHashMissing,
        ),
        (
            |policy| policy.account_fingerprint_hash_only = false,
            Blocker::AccountFingerprintHashOnlyMissing,
        ),
        (
            |policy| policy.raw_payload_storage_allowed = true,
            Blocker::RawPayloadStorageAllowed,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut policy = IbkrAuditEventPolicyV1::source_template();
        mutate(&mut policy);
        assert_single_policy_blocker(policy.validate(), blocker);
    }
}

#[test]
fn paper_attestation_and_python_guard_reject_each_authority_gap_independently() {
    use IbkrPaperAttestationPolicyBlocker as PaperBlocker;
    use IbkrPythonWriteGuardPolicyBlocker as PythonBlocker;

    let paper_cases: [(fn(&mut IbkrPaperAttestationPolicyV1), PaperBlocker); 15] = [
        (
            |policy| policy.external_surface_gate_required = false,
            PaperBlocker::ExternalSurfaceGateMissing,
        ),
        (
            |policy| policy.session_attestation_required = false,
            PaperBlocker::SessionAttestationMissing,
        ),
        (
            |policy| policy.rust_lane_scoped_ipc_required = false,
            PaperBlocker::RustLaneScopedIpcMissing,
        ),
        (
            |policy| policy.scoped_authorization_required = false,
            PaperBlocker::ScopedAuthorizationMissing,
        ),
        (
            |policy| policy.decision_lease_required = false,
            PaperBlocker::DecisionLeaseMissing,
        ),
        (
            |policy| policy.guardian_required = false,
            PaperBlocker::GuardianMissing,
        ),
        (
            |policy| policy.risk_config_hash_required = false,
            PaperBlocker::RiskConfigHashMissing,
        ),
        (
            |policy| policy.instrument_identity_hash_required = false,
            PaperBlocker::InstrumentIdentityHashMissing,
        ),
        (
            |policy| policy.idempotency_key_required = false,
            PaperBlocker::IdempotencyKeyMissing,
        ),
        (
            |policy| policy.lifecycle_event_log_required = false,
            PaperBlocker::LifecycleEventLogMissing,
        ),
        (
            |policy| policy.reconciliation_required_before_terminal = false,
            PaperBlocker::ReconciliationBeforeTerminalMissing,
        ),
        (
            |policy| policy.paper_environment_only = false,
            PaperBlocker::PaperEnvironmentOnlyMissing,
        ),
        (
            |policy| policy.live_account_fingerprint_denied = false,
            PaperBlocker::LiveAccountFingerprintNotDenied,
        ),
        (
            |policy| policy.margin_short_options_cfd_denied = false,
            PaperBlocker::MarginShortOptionsCfdNotDenied,
        ),
        (
            |policy| policy.max_paper_notional_required = false,
            PaperBlocker::MaxPaperNotionalMissing,
        ),
    ];
    for (mutate, blocker) in paper_cases {
        let mut policy = IbkrPaperAttestationPolicyV1::source_template();
        mutate(&mut policy);
        assert_single_policy_blocker(policy.validate(), blocker);
    }

    let python_cases: [(fn(&mut IbkrPythonWriteGuardPolicyV1), PythonBlocker); 7] = [
        (
            |policy| policy.python_broker_write_authority_denied = false,
            PythonBlocker::PythonBrokerWriteAuthorityNotDenied,
        ),
        (
            |policy| policy.python_can_read_display_import = false,
            PythonBlocker::PythonReadDisplayImportMissing,
        ),
        (
            |policy| policy.python_can_call_rust_lane_ipc = false,
            PythonBlocker::PythonRustIpcBridgeMissing,
        ),
        (
            |policy| policy.python_ibkr_order_methods_denied = false,
            PythonBlocker::PythonIbkrOrderMethodsNotDenied,
        ),
        (
            |policy| policy.python_live_secret_access_denied = false,
            PythonBlocker::PythonLiveSecretAccessNotDenied,
        ),
        (
            |policy| policy.gui_cannot_override_authority = false,
            PythonBlocker::GuiAuthorityOverrideNotDenied,
        ),
        (
            |policy| policy.bybit_paths_unmodified = false,
            PythonBlocker::BybitPathMutationNotAccounted,
        ),
    ];
    for (mutate, blocker) in python_cases {
        let mut policy = IbkrPythonWriteGuardPolicyV1::source_template();
        mutate(&mut policy);
        assert_single_policy_blocker(policy.validate(), blocker);
    }
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
        parsed["redaction"]["contract_id"].as_str(),
        Some(IBKR_REDACTION_POLICY_CONTRACT_ID)
    );
    assert_eq!(parsed["redaction"]["source_version"].as_integer(), Some(1));
    assert_eq!(
        parsed["redaction"]["raw_payload_hash_required"].as_bool(),
        Some(true)
    );
    assert_eq!(
        parsed["redaction"]["secret_in_logs_allowed"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["rate_limit"]["contract_id"].as_str(),
        Some(IBKR_RATE_LIMIT_POLICY_CONTRACT_ID)
    );
    assert_eq!(parsed["rate_limit"]["source_version"].as_integer(), Some(1));
    assert_eq!(
        parsed["rate_limit"]["scope"].as_str(),
        Some("global_and_per_action")
    );
    assert_eq!(
        parsed["audit_event"]["contract_id"].as_str(),
        Some(IBKR_AUDIT_EVENT_POLICY_CONTRACT_ID)
    );
    assert_eq!(
        parsed["audit_event"]["source_version"].as_integer(),
        Some(1)
    );
    assert_eq!(
        parsed["audit_event"]["account_fingerprint_hash_only"].as_bool(),
        Some(true)
    );
    assert_eq!(
        parsed["paper_attestation"]["contract_id"].as_str(),
        Some(IBKR_PAPER_ATTESTATION_CONTRACT_ID)
    );
    assert_eq!(
        parsed["paper_attestation"]["source_version"].as_integer(),
        Some(1)
    );
    assert_eq!(
        parsed["paper_attestation"]["rust_lane_scoped_ipc_required"].as_bool(),
        Some(true)
    );
    assert_eq!(
        parsed["python_write_guard"]["contract_id"].as_str(),
        Some(IBKR_PYTHON_WRITE_GUARD_POLICY_CONTRACT_ID)
    );
    assert_eq!(
        parsed["python_write_guard"]["source_version"].as_integer(),
        Some(1)
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

fn assert_single_policy_blocker<B>(verdict: IbkrPolicyVerdict<B>, blocker: B)
where
    B: Copy + Eq + std::fmt::Debug,
{
    assert_policy_blockers(verdict, &[blocker]);
}

fn assert_policy_blockers<B>(verdict: IbkrPolicyVerdict<B>, blockers: &[B])
where
    B: Copy + Eq + std::fmt::Debug,
{
    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        blockers.to_vec(),
        "expected blockers {:?}; blockers: {:?}",
        blockers,
        verdict.blockers
    );
}
