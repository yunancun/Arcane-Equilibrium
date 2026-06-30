//! ADR-0048 IBKR Phase 2 runtime-evidence contract acceptance tests.
//!
//! These tests validate secret-slot and topology evidence shape only. They must
//! not read secret contents, start IB Gateway/TWS, open sockets, or call IBKR.

use std::path::PathBuf;

use openclaw_types::{
    BrokerEnvironment, IbkrApiSessionTopologyBlocker, IbkrApiSessionTopologyV1,
    IbkrGatewayProcessMode, IbkrSecretSlotContractBlocker, IbkrSecretSlotContractV1,
    IbkrSecretSlotPosture, IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID, IBKR_LIVE_GATEWAY_PORT,
    IBKR_PAPER_GATEWAY_DEFAULT_PORT, IBKR_SECRET_SLOT_CONTRACT_ID,
};

#[test]
fn default_secret_slot_contract_blocks_gate_prerequisites() {
    let contract = IbkrSecretSlotContractV1::default();
    let verdict = contract.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::ContractMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::PaperSlotMissingOrUnhashed));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::LiveSlotPresentOrUnknown));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::SecretSlotFingerprintInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::LiveSecretAbsentOrEmptyNotProven));
}

#[test]
fn source_secret_slot_contract_accepts_only_hashed_paper_and_absent_live() {
    let contract = IbkrSecretSlotContractV1::source_template();
    let verdict = contract.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(contract.contract_id, IBKR_SECRET_SLOT_CONTRACT_ID);
    assert_eq!(contract.source_version, 1);
    assert_eq!(
        contract.paper_slot_posture,
        IbkrSecretSlotPosture::PresentHashed
    );
    assert_eq!(
        contract.live_slot_posture,
        IbkrSecretSlotPosture::LiveAbsentOrEmpty
    );
    assert!(!contract.secret_content_serialized);
    assert!(!contract.account_id_serialized);
}

#[test]
fn secret_slot_contract_rejects_live_secret_and_serialized_sensitive_fields() {
    let contract = IbkrSecretSlotContractV1 {
        contract_id: "ibkr_secret_slot_contract_v1_fixture".to_string(),
        source_version: 2,
        readonly_slot_posture: IbkrSecretSlotPosture::LivePresentDenied,
        paper_slot_posture: IbkrSecretSlotPosture::Missing,
        live_slot_posture: IbkrSecretSlotPosture::LivePresentDenied,
        secret_slot_fingerprint: "not-a-hash".to_string(),
        account_fingerprint_hash: "abc".to_string(),
        owner_only_permissions: false,
        env_var_credential_fallback_denied: false,
        secret_content_serialized: true,
        account_id_serialized: true,
        live_secret_absent_or_empty: false,
        ..IbkrSecretSlotContractV1::source_template()
    };
    let verdict = contract.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::ReadonlySlotPostureInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::PaperSlotMissingOrUnhashed));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::LiveSlotPresentOrUnknown));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::SecretSlotFingerprintInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::AccountFingerprintHashInvalid));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::OwnerOnlyPermissionsMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::EnvVarCredentialFallbackNotDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::SecretContentSerialized));
    assert!(verdict
        .blockers
        .contains(&IbkrSecretSlotContractBlocker::AccountIdSerialized));
}

#[test]
fn default_api_session_topology_blocks_before_gateway_contact() {
    let topology = IbkrApiSessionTopologyV1::default();
    let verdict = topology.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::TopologyMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::ApiBaselineMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::HostNotLoopback));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::PaperPortNotUsed));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::GatewayModeNotPaper));
}

#[test]
fn source_api_session_topology_accepts_loopback_paper_gateway_only() {
    let topology = IbkrApiSessionTopologyV1::source_template();
    let verdict = topology.validate();

    assert!(verdict.accepted);
    assert!(verdict.blockers.is_empty());
    assert_eq!(topology.contract_id, IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID);
    assert_eq!(topology.source_version, 1);
    assert_eq!(topology.host, "127.0.0.1");
    assert_eq!(topology.port, IBKR_PAPER_GATEWAY_DEFAULT_PORT);
    assert_eq!(topology.gateway_mode, IbkrGatewayProcessMode::PaperGateway);
    assert_eq!(topology.environment, BrokerEnvironment::Paper);
}

#[test]
fn topology_rejects_network_host_live_port_and_live_mode() {
    let topology = IbkrApiSessionTopologyV1 {
        contract_id: "ibkr_api_session_topology_v1_fixture".to_string(),
        source_version: 2,
        host: "192.0.2.10".to_string(),
        port: IBKR_LIVE_GATEWAY_PORT,
        gateway_mode: IbkrGatewayProcessMode::LiveDenied,
        environment: BrokerEnvironment::LiveReservedDenied,
        deterministic_client_id_present: false,
        process_identity_recorded: false,
        account_fingerprint_hash: "not-a-hash".to_string(),
        api_server_version_recorded: false,
        data_entitlements_recorded: false,
        startup_time_recorded: false,
        attestation_expiry_recorded: false,
        ..IbkrApiSessionTopologyV1::source_template()
    };
    let verdict = topology.validate();

    assert!(!verdict.accepted);
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::ContractIdMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::SourceVersionMismatch));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::HostNotLoopback));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::LivePortDenied));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::PaperPortNotUsed));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::GatewayModeNotPaper));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::EnvironmentNotPaper));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::DeterministicClientIdMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::ProcessIdentityMissing));
    assert!(verdict
        .blockers
        .contains(&IbkrApiSessionTopologyBlocker::AccountFingerprintHashInvalid));
}

#[test]
fn runtime_contract_template_is_blocked_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/ibkr_phase2_runtime_contracts.toml"),
    )
    .expect("read ibkr runtime contract template");
    let parsed: toml::Value = toml::from_str(&raw).expect("runtime contract toml parses");

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
        parsed["secret_slot_contract"]["live_secret_absent_or_empty"].as_bool(),
        Some(false)
    );
    assert_eq!(
        parsed["api_session_topology"]["topology_present"].as_bool(),
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
        parsed["api_session_topology"]["api_baseline"].as_str(),
        Some("ib_gateway_tws_api")
    );
    assert_eq!(parsed["api_session_topology"]["port"].as_integer(), Some(0));

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}
