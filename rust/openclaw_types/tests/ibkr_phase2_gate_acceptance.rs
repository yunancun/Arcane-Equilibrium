//! ADR-0048 IBKR Phase 2 pre-contact gate acceptance tests.
//!
//! These tests pin source-only gate behavior. They must not create an IBKR
//! connector, secret slot, broker session, paper order, or external API call.

use std::path::PathBuf;

use openclaw_types::{
    classify_non_bybit_api_action, required_non_bybit_api_actions, BrokerEnvironment,
    IbkrApiBaseline, IbkrExternalSurfaceGateBlocker, IbkrExternalSurfaceGateStatus,
    IbkrExternalSurfaceGateV1, IbkrGatewayMode, IbkrHostPolicy, IbkrPortPolicy, IbkrSecretSlotMode,
    IbkrSessionAttestationBlocker, IbkrSessionAttestationStatus, IbkrSessionAttestationV1,
    IbkrSessionDataTier, NonBybitApiAction, NonBybitApiAllowlistBlocker, NonBybitApiAllowlistV1,
    NonBybitApiDenialReason, IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID, IBKR_LIVE_GATEWAY_PORT,
    IBKR_LIVE_TWS_PORT, IBKR_PAPER_GATEWAY_DEFAULT_PORT, IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
};

#[test]
fn external_surface_gate_default_blocks_before_any_ibkr_contact() {
    use IbkrExternalSurfaceGateBlocker as Blocker;

    let gate = IbkrExternalSurfaceGateV1::default();
    let verdict = gate.validate();

    assert_eq!(gate.status, IbkrExternalSurfaceGateStatus::Blocked);
    assert!(!gate.ibkr_call_performed);
    assert!(!verdict.ibkr_contact_allowed);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::StatusNotPass,
            Blocker::LivePortsNotDenied,
            Blocker::SecretContractMissing,
            Blocker::LiveSecretPresentOrUnknown,
            Blocker::ApiAllowlistMissing,
            Blocker::RedactionSuiteMissing,
            Blocker::RateLimitPolicyMissing,
            Blocker::AuditEventPolicyMissing,
            Blocker::PaperAttestationContractMissing,
            Blocker::PythonNoWriteGuardMissing,
        ]
    );
}

#[test]
fn external_surface_gate_pass_fixture_allows_contact_without_call_side_effect() {
    let gate = IbkrExternalSurfaceGateV1::passing_fixture();
    let verdict = gate.validate();
    let serialized = serde_json::to_value(&gate).expect("serialize gate");

    assert!(verdict.ibkr_contact_allowed);
    assert!(verdict.blockers.is_empty());
    assert!(gate.can_contact_ibkr());
    assert_eq!(gate.contract_id, IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID);
    assert_eq!(gate.source_version, 1);
    assert_eq!(serialized["status"], "PASS");
    assert_eq!(
        serialized["contract_id"],
        IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID
    );
    assert_eq!(serialized["source_version"], 1);
    assert_eq!(serialized["api_baseline"], "ib_gateway_tws_api");
    assert_eq!(serialized["host_policy"], "loopback_only");
    assert_eq!(serialized["port_policy"], "paper_gateway_port_only");
    assert_eq!(serialized["ibkr_call_performed"], false);
}

#[test]
fn external_surface_gate_rejects_each_precontact_gap_independently() {
    use IbkrExternalSurfaceGateBlocker as Blocker;

    let cases: [(fn(&mut IbkrExternalSurfaceGateV1), Blocker); 17] = [
        (
            |gate| gate.contract_id = "phase2_ibkr_external_surface_gate_v1_fixture".to_string(),
            Blocker::ContractIdMismatch,
        ),
        (
            |gate| gate.source_version = 2,
            Blocker::SourceVersionMismatch,
        ),
        (
            |gate| gate.status = IbkrExternalSurfaceGateStatus::Blocked,
            Blocker::StatusNotPass,
        ),
        (
            |gate| gate.adr = "ADR-0047".to_string(),
            Blocker::AdrMismatch,
        ),
        (
            |gate| gate.amd = "AMD-2026-06-29-99".to_string(),
            Blocker::AmdMismatch,
        ),
        (
            |gate| gate.api_baseline = IbkrApiBaseline::ClientPortalWebApiDenied,
            Blocker::ApiBaselineMismatch,
        ),
        (
            |gate| gate.host_policy = IbkrHostPolicy::NetworkHostDenied,
            Blocker::HostPolicyNotLoopbackOnly,
        ),
        (
            |gate| gate.port_policy = IbkrPortPolicy::LiveOrTwsPortDenied,
            Blocker::PortPolicyNotPaperGatewayOnly,
        ),
        (
            |gate| gate.live_ports_denied = false,
            Blocker::LivePortsNotDenied,
        ),
        (
            |gate| gate.secret_contract_present = false,
            Blocker::SecretContractMissing,
        ),
        (
            |gate| gate.live_secret_absent_or_empty = false,
            Blocker::LiveSecretPresentOrUnknown,
        ),
        (
            |gate| gate.api_allowlist_present = false,
            Blocker::ApiAllowlistMissing,
        ),
        (
            |gate| gate.redaction_suite_passed = false,
            Blocker::RedactionSuiteMissing,
        ),
        (
            |gate| gate.rate_limit_policy_present = false,
            Blocker::RateLimitPolicyMissing,
        ),
        (
            |gate| gate.audit_event_policy_present = false,
            Blocker::AuditEventPolicyMissing,
        ),
        (
            |gate| gate.paper_attestation_contract_present = false,
            Blocker::PaperAttestationContractMissing,
        ),
        (
            |gate| gate.python_no_write_guard_present = false,
            Blocker::PythonNoWriteGuardMissing,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut gate = IbkrExternalSurfaceGateV1::passing_fixture();
        mutate(&mut gate);
        assert_single_external_gate_blocker(gate.validate(), blocker);
    }

    let mut retroactive = IbkrExternalSurfaceGateV1::passing_fixture();
    retroactive.ibkr_call_performed = true;
    assert_single_external_gate_blocker(
        retroactive.validate(),
        IbkrExternalSurfaceGateBlocker::IbkrCallAlreadyPerformed,
    );
}

#[test]
fn external_surface_gate_rejects_retroactive_or_wrong_surface_pass() {
    use IbkrExternalSurfaceGateBlocker as Blocker;

    let wrong_identity = IbkrExternalSurfaceGateV1 {
        contract_id: "phase2_ibkr_external_surface_gate_v1_fixture".to_string(),
        source_version: 2,
        ..IbkrExternalSurfaceGateV1::passing_fixture()
    };
    let identity_verdict = wrong_identity.validate();
    assert_eq!(
        identity_verdict.blockers,
        vec![Blocker::ContractIdMismatch, Blocker::SourceVersionMismatch]
    );

    let retroactive = IbkrExternalSurfaceGateV1 {
        ibkr_call_performed: true,
        ..IbkrExternalSurfaceGateV1::passing_fixture()
    };
    assert_eq!(
        retroactive.validate().blockers,
        vec![Blocker::IbkrCallAlreadyPerformed]
    );

    let client_portal = IbkrExternalSurfaceGateV1 {
        api_baseline: IbkrApiBaseline::ClientPortalWebApiDenied,
        ..IbkrExternalSurfaceGateV1::passing_fixture()
    };
    assert_eq!(
        client_portal.validate().blockers,
        vec![Blocker::ApiBaselineMismatch]
    );

    let network_host = IbkrExternalSurfaceGateV1 {
        host_policy: IbkrHostPolicy::NetworkHostDenied,
        port_policy: IbkrPortPolicy::LiveOrTwsPortDenied,
        ..IbkrExternalSurfaceGateV1::passing_fixture()
    };
    let verdict = network_host.validate();
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::HostPolicyNotLoopbackOnly,
            Blocker::PortPolicyNotPaperGatewayOnly,
        ]
    );
}

#[test]
fn non_bybit_api_allowlist_separates_reads_paper_writes_and_denials() {
    let server_time = classify_non_bybit_api_action(NonBybitApiAction::ServerTimeRead);
    assert!(server_time.allowed_after_external_gate);
    assert!(server_time.requires_external_surface_gate);
    assert!(!server_time.requires_session_attestation);
    assert!(!server_time.requires_paper_order_gates);
    assert!(!server_time.denied);

    let account_summary =
        classify_non_bybit_api_action(NonBybitApiAction::AccountSummarySnapshotRead);
    assert!(account_summary.allowed_after_external_gate);
    assert!(account_summary.requires_session_attestation);

    let paper_submit = classify_non_bybit_api_action(NonBybitApiAction::PaperOrderSubmit);
    assert!(!paper_submit.allowed_after_external_gate);
    assert!(paper_submit.requires_external_surface_gate);
    assert!(paper_submit.requires_session_attestation);
    assert!(paper_submit.requires_paper_order_gates);
    assert!(!paper_submit.denied);

    let live = classify_non_bybit_api_action(NonBybitApiAction::LiveOrderSubmit);
    assert!(live.denied);
    assert_eq!(
        live.denial_reason,
        Some(NonBybitApiDenialReason::LiveOrderDenied)
    );

    let client_portal = classify_non_bybit_api_action(NonBybitApiAction::ClientPortalWebApiUse);
    assert!(client_portal.denied);
    assert_eq!(
        client_portal.denial_reason,
        Some(NonBybitApiDenialReason::ClientPortalWebApiDenied)
    );
}

#[test]
fn non_bybit_api_allowlist_contract_pins_complete_action_matrix() {
    let allowlist = NonBybitApiAllowlistV1::accepted_fixture();
    let verdict = allowlist.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(allowlist.contract_id, NON_BYBIT_API_ALLOWLIST_CONTRACT_ID);
    assert_eq!(allowlist.source_version, 1);
    assert_eq!(
        allowlist.read_actions.len()
            + allowlist.paper_write_actions.len()
            + allowlist.denied_actions.len(),
        required_non_bybit_api_actions().len()
    );
    assert!(!allowlist.ibkr_contact_performed);
    assert!(!allowlist.secret_content_serialized);
    assert!(allowlist.bybit_live_execution_protected);
}

#[test]
fn non_bybit_api_allowlist_contract_rejects_identity_and_matrix_drift() {
    let default = NonBybitApiAllowlistV1::default().validate();
    assert!(!default.accepted);
    assert!(default
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::ContractIdMismatch));
    assert!(default
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::SourceVersionMismatch));
    assert!(default
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::ActionMissing));

    let mut drifted = NonBybitApiAllowlistV1 {
        contract_id: "non_bybit_api_allowlist_v1_fixture".to_string(),
        source_version: 2,
        api_baseline: IbkrApiBaseline::ClientPortalWebApiDenied,
        client_portal_web_api_denied: false,
        live_order_denied: false,
        account_transfer_denied: false,
        margin_short_options_cfd_denied: false,
        market_data_entitlement_purchase_denied: false,
        account_management_write_denied: false,
        ibkr_contact_performed: true,
        secret_content_serialized: true,
        bybit_live_execution_protected: false,
        ..NonBybitApiAllowlistV1::accepted_fixture()
    };
    drifted
        .read_actions
        .push(NonBybitApiAction::PaperOrderSubmit);
    drifted
        .denied_actions
        .retain(|action| *action != NonBybitApiAction::LiveOrderSubmit);
    let verdict = drifted.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::ApiBaselineMismatch));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::ActionMissing));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::ActionDuplicated));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::ActionInWrongBucket));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::ClientPortalWebApiNotDenied));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::LiveOrderNotDenied));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::AccountTransferNotDenied));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::MarginShortOptionsCfdNotDenied));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::MarketDataEntitlementPurchaseNotDenied));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::AccountManagementWriteNotDenied));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::IbkrContactPerformed));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::SecretContentSerialized));
    assert!(verdict
        .blockers
        .contains(&NonBybitApiAllowlistBlocker::BybitLiveExecutionNotProtected));
}

#[test]
fn session_attestation_default_blocks_without_secret_or_socket() {
    let attestation = IbkrSessionAttestationV1::default();
    let verdict = attestation.validate(1);

    assert!(!verdict.attestation_accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::StatusBlocked));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::HostNotLoopback));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::PortNotPaperGatewayDefault));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::MissingAccountFingerprint));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::MissingRawArtifactHash));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::MissingDataTier));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::MissingDataEntitlementsFingerprint));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::MarketDataEntitlementPurchaseNotDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::MissingGatewayStartupTime));
}

#[test]
fn paper_session_attestation_accepts_only_loopback_paper_gateway() {
    let attestation = IbkrSessionAttestationV1::paper_fixture();
    let verdict = attestation.validate(attestation.attested_at_ms + 1);

    assert!(verdict.attestation_accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(
        attestation.contract_id,
        IBKR_SESSION_ATTESTATION_CONTRACT_ID
    );
    assert_eq!(attestation.source_version, 1);
    assert_eq!(attestation.host, "127.0.0.1");
    assert_eq!(attestation.port, IBKR_PAPER_GATEWAY_DEFAULT_PORT);
    assert_eq!(attestation.data_tier, IbkrSessionDataTier::Delayed);
    assert_eq!(attestation.account_fingerprint.len(), 64);
    assert_eq!(attestation.secret_slot_fingerprint.len(), 64);
    assert_eq!(attestation.entitlements_fingerprint.len(), 64);
    assert!(attestation.market_data_entitlement_purchase_denied);
    assert!(attestation.gateway_started_at_ms <= attestation.attested_at_ms);

    let wrong_identity = IbkrSessionAttestationV1 {
        contract_id: "ibkr_session_attestation_v1_fixture".to_string(),
        source_version: 2,
        ..IbkrSessionAttestationV1::paper_fixture()
    };
    let verdict = wrong_identity.validate(wrong_identity.attested_at_ms + 1);
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::SourceVersionMismatch));

    let network_host = IbkrSessionAttestationV1 {
        host: "192.0.2.10".to_string(),
        ..IbkrSessionAttestationV1::paper_fixture()
    };
    assert!(network_host
        .validate(network_host.attested_at_ms + 1)
        .blockers
        .contains(&IbkrSessionAttestationBlocker::HostNotLoopback));

    let live_port = IbkrSessionAttestationV1 {
        port: IBKR_LIVE_GATEWAY_PORT,
        ..IbkrSessionAttestationV1::paper_fixture()
    };
    let verdict = live_port.validate(live_port.attested_at_ms + 1);
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::LivePortDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::PortNotPaperGatewayDefault));
}

#[test]
fn session_attestation_rejects_each_secret_lineage_and_window_gap_independently() {
    use IbkrSessionAttestationBlocker as Blocker;

    let cases: [(fn(&mut IbkrSessionAttestationV1), Blocker); 29] = [
        (
            |attestation| {
                attestation.contract_id = "ibkr_session_attestation_v1_fixture".to_string()
            },
            Blocker::ContractIdMismatch,
        ),
        (
            |attestation| attestation.source_version = 2,
            Blocker::SourceVersionMismatch,
        ),
        (
            |attestation| attestation.status = IbkrSessionAttestationStatus::Blocked,
            Blocker::StatusBlocked,
        ),
        (
            |attestation| attestation.environment = BrokerEnvironment::LiveReservedDenied,
            Blocker::EnvironmentDenied,
        ),
        (
            |attestation| attestation.host = "192.0.2.10".to_string(),
            Blocker::HostNotLoopback,
        ),
        (
            |attestation| attestation.port = 1,
            Blocker::PortNotPaperGatewayDefault,
        ),
        (
            |attestation| attestation.account_fingerprint = String::new(),
            Blocker::MissingAccountFingerprint,
        ),
        (
            |attestation| {
                attestation.account_fingerprint = "paper_account_fingerprint_hash".to_string()
            },
            Blocker::AccountFingerprintInvalid,
        ),
        (
            |attestation| attestation.account_fingerprint_is_live = true,
            Blocker::LiveAccountFingerprint,
        ),
        (
            |attestation| attestation.process_identity = String::new(),
            Blocker::MissingProcessIdentity,
        ),
        (
            |attestation| attestation.gateway_mode = IbkrGatewayMode::Unknown,
            Blocker::UnknownOrLiveGatewayMode,
        ),
        (
            |attestation| attestation.secret_slot_fingerprint = String::new(),
            Blocker::MissingSecretSlotFingerprint,
        ),
        (
            |attestation| {
                attestation.secret_slot_fingerprint =
                    "paper_secret_slot_fingerprint_hash".to_string()
            },
            Blocker::SecretSlotFingerprintInvalid,
        ),
        (
            |attestation| attestation.secret_slot_mode = IbkrSecretSlotMode::Missing,
            Blocker::SecretSlotMissing,
        ),
        (
            |attestation| attestation.secret_slot_mode = IbkrSecretSlotMode::WorldReadable,
            Blocker::SecretSlotWorldReadable,
        ),
        (
            |attestation| attestation.secret_slot_mode = IbkrSecretSlotMode::LiveDenied,
            Blocker::SecretSlotModeDenied,
        ),
        (
            |attestation| attestation.secret_world_readable = true,
            Blocker::SecretSlotWorldReadable,
        ),
        (
            |attestation| attestation.live_secret_absent_or_empty = false,
            Blocker::LiveSecretPresentOrUnknown,
        ),
        (
            |attestation| attestation.env_var_credential_fallback_used = true,
            Blocker::EnvVarCredentialFallback,
        ),
        (
            |attestation| attestation.api_server_version = String::new(),
            Blocker::MissingApiServerVersion,
        ),
        (
            |attestation| attestation.data_tier = IbkrSessionDataTier::Unknown,
            Blocker::MissingDataTier,
        ),
        (
            |attestation| attestation.entitlements_fingerprint = String::new(),
            Blocker::MissingDataEntitlementsFingerprint,
        ),
        (
            |attestation| {
                attestation.entitlements_fingerprint = "data_entitlements_fixture".to_string()
            },
            Blocker::DataEntitlementsFingerprintInvalid,
        ),
        (
            |attestation| attestation.market_data_entitlement_purchase_denied = false,
            Blocker::MarketDataEntitlementPurchaseNotDenied,
        ),
        (
            |attestation| attestation.gateway_started_at_ms = 0,
            Blocker::MissingGatewayStartupTime,
        ),
        (
            |attestation| attestation.gateway_started_at_ms = attestation.attested_at_ms + 1,
            Blocker::GatewayStartupAfterAttestation,
        ),
        (
            |attestation| attestation.raw_artifact_hash = String::new(),
            Blocker::MissingRawArtifactHash,
        ),
        (
            |attestation| attestation.raw_artifact_hash = "redacted_raw_artifact_hash".to_string(),
            Blocker::RawArtifactHashInvalid,
        ),
        (
            |attestation| attestation.expires_at_ms = attestation.attested_at_ms,
            Blocker::InvalidAttestationWindow,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut attestation = IbkrSessionAttestationV1::paper_fixture();
        mutate(&mut attestation);
        let now_ms = if blocker == Blocker::InvalidAttestationWindow {
            attestation.attested_at_ms - 1
        } else {
            attestation.attested_at_ms + 1
        };
        assert_single_session_attestation_blocker(attestation.validate(now_ms), blocker);
    }

    let live_port = IbkrSessionAttestationV1 {
        port: IBKR_LIVE_TWS_PORT,
        ..IbkrSessionAttestationV1::paper_fixture()
    };
    let live_port_verdict = live_port.validate(live_port.attested_at_ms + 1);
    assert!(live_port_verdict
        .blockers
        .contains(&Blocker::LivePortDenied));
    assert!(live_port_verdict
        .blockers
        .contains(&Blocker::PortNotPaperGatewayDefault));

    let stale = IbkrSessionAttestationV1::paper_fixture();
    assert_single_session_attestation_blocker(
        stale.validate(stale.expires_at_ms),
        Blocker::StaleAttestation,
    );
}

#[test]
fn session_attestation_requires_hashed_lineage_data_tier_and_startup_time() {
    let attestation = IbkrSessionAttestationV1 {
        account_fingerprint: "paper_account_fingerprint_hash".to_string(),
        secret_slot_fingerprint: "paper_secret_slot_fingerprint_hash".to_string(),
        data_tier: IbkrSessionDataTier::Unknown,
        entitlements_fingerprint: "data_entitlements_fixture".to_string(),
        market_data_entitlement_purchase_denied: false,
        gateway_started_at_ms: 1_772_232_000_001,
        raw_artifact_hash: "redacted_raw_artifact_hash".to_string(),
        ..IbkrSessionAttestationV1::paper_fixture()
    };
    let verdict = attestation.validate(attestation.attested_at_ms + 1);

    assert!(!verdict.attestation_accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::AccountFingerprintInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::SecretSlotFingerprintInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::MissingDataTier));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::DataEntitlementsFingerprintInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::MarketDataEntitlementPurchaseNotDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::GatewayStartupAfterAttestation));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::RawArtifactHashInvalid));
}

#[test]
fn session_attestation_denies_live_secret_and_env_fallback() {
    let attestation = IbkrSessionAttestationV1 {
        account_fingerprint_is_live: true,
        environment: BrokerEnvironment::LiveReservedDenied,
        gateway_mode: IbkrGatewayMode::LiveDenied,
        secret_slot_mode: IbkrSecretSlotMode::WorldReadable,
        secret_world_readable: true,
        live_secret_absent_or_empty: false,
        env_var_credential_fallback_used: true,
        ..IbkrSessionAttestationV1::paper_fixture()
    };
    let verdict = attestation.validate(attestation.attested_at_ms + 1);

    assert!(!verdict.attestation_accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::LiveAccountFingerprint));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::EnvironmentDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::UnknownOrLiveGatewayMode));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::SecretSlotWorldReadable));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::LiveSecretPresentOrUnknown));
    assert!(verdict
        .blockers
        .contains(&IbkrSessionAttestationBlocker::EnvVarCredentialFallback));
}

#[test]
fn source_gate_template_is_blocked_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw =
        std::fs::read_to_string(srv_root.join("settings/broker/ibkr_external_surface_gate.toml"))
            .expect("read external surface gate template");
    let parsed: toml::Value = toml::from_str(&raw).expect("gate toml parses");

    assert_eq!(parsed["gate"]["status"].as_str(), Some("BLOCKED"));
    assert_eq!(parsed["gate"]["contract_id"].as_str(), Some(""));
    assert_eq!(parsed["gate"]["source_version"].as_integer(), Some(0));
    assert_eq!(
        parsed["gate"]["api_baseline"].as_str(),
        Some("ib_gateway_tws_api")
    );
    assert_eq!(parsed["gate"]["live_ports_denied"].as_bool(), Some(false));
    assert_eq!(parsed["gate"]["ibkr_call_performed"].as_bool(), Some(false));
    assert_eq!(
        parsed["allowlist"]["denied"]["live_order"].as_bool(),
        Some(true)
    );
    assert_eq!(parsed["allowlist"]["contract_id"].as_str(), Some(""));
    assert_eq!(parsed["allowlist"]["source_version"].as_integer(), Some(0));
    assert_eq!(
        parsed["allowlist"]["denied"]["client_portal_web_api"].as_bool(),
        Some(true)
    );

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn assert_single_external_gate_blocker(
    verdict: openclaw_types::IbkrExternalSurfaceGateVerdict,
    blocker: IbkrExternalSurfaceGateBlocker,
) {
    assert!(!verdict.ibkr_contact_allowed);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}

fn assert_single_session_attestation_blocker(
    verdict: openclaw_types::IbkrSessionAttestationVerdict,
    blocker: IbkrSessionAttestationBlocker,
) {
    assert!(!verdict.attestation_accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
