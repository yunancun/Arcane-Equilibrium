//! ADR-0048 IBKR Phase 2 pre-contact gate acceptance tests.
//!
//! These tests pin source-only gate behavior. They must not create an IBKR
//! connector, secret slot, broker session, paper order, or external API call.

use std::path::PathBuf;

use openclaw_types::{
    classify_non_bybit_api_action, BrokerEnvironment, IbkrApiBaseline,
    IbkrExternalSurfaceGateBlocker, IbkrExternalSurfaceGateStatus, IbkrExternalSurfaceGateV1,
    IbkrGatewayMode, IbkrHostPolicy, IbkrPortPolicy, IbkrSecretSlotMode,
    IbkrSessionAttestationBlocker, IbkrSessionAttestationV1, NonBybitApiAction,
    NonBybitApiDenialReason, IBKR_LIVE_GATEWAY_PORT, IBKR_PAPER_GATEWAY_DEFAULT_PORT,
};

#[test]
fn external_surface_gate_default_blocks_before_any_ibkr_contact() {
    let gate = IbkrExternalSurfaceGateV1::default();
    let verdict = gate.validate();

    assert_eq!(gate.status, IbkrExternalSurfaceGateStatus::Blocked);
    assert!(!gate.ibkr_call_performed);
    assert!(!verdict.ibkr_contact_allowed);
    assert!(verdict
        .blockers
        .contains(&IbkrExternalSurfaceGateBlocker::StatusNotPass));
    assert!(verdict
        .blockers
        .contains(&IbkrExternalSurfaceGateBlocker::LivePortsNotDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrExternalSurfaceGateBlocker::ApiAllowlistMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrExternalSurfaceGateBlocker::RedactionSuiteMissing));
}

#[test]
fn external_surface_gate_pass_fixture_allows_contact_without_call_side_effect() {
    let gate = IbkrExternalSurfaceGateV1::passing_fixture();
    let verdict = gate.validate();
    let serialized = serde_json::to_value(&gate).expect("serialize gate");

    assert!(verdict.ibkr_contact_allowed);
    assert!(verdict.blockers.is_empty());
    assert!(gate.can_contact_ibkr());
    assert_eq!(serialized["status"], "PASS");
    assert_eq!(serialized["api_baseline"], "ib_gateway_tws_api");
    assert_eq!(serialized["host_policy"], "loopback_only");
    assert_eq!(serialized["port_policy"], "paper_gateway_port_only");
    assert_eq!(serialized["ibkr_call_performed"], false);
}

#[test]
fn external_surface_gate_rejects_retroactive_or_wrong_surface_pass() {
    let retroactive = IbkrExternalSurfaceGateV1 {
        ibkr_call_performed: true,
        ..IbkrExternalSurfaceGateV1::passing_fixture()
    };
    assert!(retroactive
        .validate()
        .blockers
        .contains(&IbkrExternalSurfaceGateBlocker::IbkrCallAlreadyPerformed));

    let client_portal = IbkrExternalSurfaceGateV1 {
        api_baseline: IbkrApiBaseline::ClientPortalWebApiDenied,
        ..IbkrExternalSurfaceGateV1::passing_fixture()
    };
    assert!(client_portal
        .validate()
        .blockers
        .contains(&IbkrExternalSurfaceGateBlocker::ApiBaselineMismatch));

    let network_host = IbkrExternalSurfaceGateV1 {
        host_policy: IbkrHostPolicy::NetworkHostDenied,
        port_policy: IbkrPortPolicy::LiveOrTwsPortDenied,
        ..IbkrExternalSurfaceGateV1::passing_fixture()
    };
    let verdict = network_host.validate();
    assert!(verdict
        .blockers
        .contains(&IbkrExternalSurfaceGateBlocker::HostPolicyNotLoopbackOnly));
    assert!(verdict
        .blockers
        .contains(&IbkrExternalSurfaceGateBlocker::PortPolicyNotPaperGatewayOnly));
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
fn session_attestation_default_blocks_without_secret_or_socket() {
    let attestation = IbkrSessionAttestationV1::default();
    let verdict = attestation.validate(1);

    assert!(!verdict.attestation_accepted);
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
}

#[test]
fn paper_session_attestation_accepts_only_loopback_paper_gateway() {
    let attestation = IbkrSessionAttestationV1::paper_fixture();
    let verdict = attestation.validate(attestation.attested_at_ms + 1);

    assert!(verdict.attestation_accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(attestation.host, "127.0.0.1");
    assert_eq!(attestation.port, IBKR_PAPER_GATEWAY_DEFAULT_PORT);

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
