//! ADR-0048 IBKR Phase 2 runtime-evidence contract acceptance tests.
//!
//! These tests validate secret-slot and topology evidence shape only. They must
//! not read secret contents, start IB Gateway/TWS, open sockets, or call IBKR.

use std::path::PathBuf;

use openclaw_types::{
    BrokerEnvironment, IbkrApiSessionTopologyBlocker, IbkrApiSessionTopologyV1,
    IbkrGatewayProcessMode, IbkrSecretSlotContractBlocker, IbkrSecretSlotContractV1,
    IbkrSecretSlotPosture, IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID, IBKR_LIVE_GATEWAY_PORT,
    IBKR_LIVE_TWS_PORT, IBKR_PAPER_GATEWAY_DEFAULT_PORT, IBKR_SECRET_SLOT_CONTRACT_ID,
};

#[test]
fn default_secret_slot_contract_blocks_gate_prerequisites() {
    let contract = IbkrSecretSlotContractV1::default();
    let verdict = contract.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            IbkrSecretSlotContractBlocker::ContractIdMismatch,
            IbkrSecretSlotContractBlocker::SourceVersionMismatch,
            IbkrSecretSlotContractBlocker::ContractMissing,
            IbkrSecretSlotContractBlocker::ReadonlySlotPostureInvalid,
            IbkrSecretSlotContractBlocker::PaperSlotMissingOrUnhashed,
            IbkrSecretSlotContractBlocker::LiveSlotPresentOrUnknown,
            IbkrSecretSlotContractBlocker::SecretSlotFingerprintInvalid,
            IbkrSecretSlotContractBlocker::AccountFingerprintHashInvalid,
            IbkrSecretSlotContractBlocker::OwnerOnlyPermissionsMissing,
            IbkrSecretSlotContractBlocker::EnvVarCredentialFallbackNotDenied,
            IbkrSecretSlotContractBlocker::LiveSecretAbsentOrEmptyNotProven,
        ]
    );
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
    use IbkrSecretSlotContractBlocker as Blocker;

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
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::ReadonlySlotPostureInvalid,
            Blocker::PaperSlotMissingOrUnhashed,
            Blocker::LiveSlotPresentOrUnknown,
            Blocker::SecretSlotFingerprintInvalid,
            Blocker::AccountFingerprintHashInvalid,
            Blocker::OwnerOnlyPermissionsMissing,
            Blocker::EnvVarCredentialFallbackNotDenied,
            Blocker::SecretContentSerialized,
            Blocker::AccountIdSerialized,
            Blocker::LiveSecretAbsentOrEmptyNotProven,
        ]
    );
}

#[test]
fn secret_slot_contract_rejects_each_slot_and_secret_gap_independently() {
    use IbkrSecretSlotContractBlocker as Blocker;

    let cases: [(fn(&mut IbkrSecretSlotContractV1), Blocker); 13] = [
        (
            |contract| contract.contract_id = "ibkr_secret_slot_contract_v1_fixture".to_string(),
            Blocker::ContractIdMismatch,
        ),
        (
            |contract| contract.source_version = 2,
            Blocker::SourceVersionMismatch,
        ),
        (
            |contract| contract.contract_present = false,
            Blocker::ContractMissing,
        ),
        (
            |contract| contract.readonly_slot_posture = IbkrSecretSlotPosture::LivePresentDenied,
            Blocker::ReadonlySlotPostureInvalid,
        ),
        (
            |contract| contract.paper_slot_posture = IbkrSecretSlotPosture::Missing,
            Blocker::PaperSlotMissingOrUnhashed,
        ),
        (
            |contract| contract.live_slot_posture = IbkrSecretSlotPosture::LivePresentDenied,
            Blocker::LiveSlotPresentOrUnknown,
        ),
        (
            |contract| contract.secret_slot_fingerprint = "paper_secret_slot".to_string(),
            Blocker::SecretSlotFingerprintInvalid,
        ),
        (
            |contract| contract.account_fingerprint_hash = "paper_account".to_string(),
            Blocker::AccountFingerprintHashInvalid,
        ),
        (
            |contract| contract.owner_only_permissions = false,
            Blocker::OwnerOnlyPermissionsMissing,
        ),
        (
            |contract| contract.env_var_credential_fallback_denied = false,
            Blocker::EnvVarCredentialFallbackNotDenied,
        ),
        (
            |contract| contract.secret_content_serialized = true,
            Blocker::SecretContentSerialized,
        ),
        (
            |contract| contract.account_id_serialized = true,
            Blocker::AccountIdSerialized,
        ),
        (
            |contract| contract.live_secret_absent_or_empty = false,
            Blocker::LiveSecretAbsentOrEmptyNotProven,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut contract = IbkrSecretSlotContractV1::source_template();
        mutate(&mut contract);
        assert_single_secret_slot_blocker(contract.validate(), blocker);
    }
}

#[test]
fn default_api_session_topology_blocks_before_gateway_contact() {
    let topology = IbkrApiSessionTopologyV1::default();
    let verdict = topology.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            IbkrApiSessionTopologyBlocker::ContractIdMismatch,
            IbkrApiSessionTopologyBlocker::SourceVersionMismatch,
            IbkrApiSessionTopologyBlocker::TopologyMissing,
            IbkrApiSessionTopologyBlocker::ApiBaselineMismatch,
            IbkrApiSessionTopologyBlocker::RuntimeOwnerMismatch,
            IbkrApiSessionTopologyBlocker::HostNotLoopback,
            IbkrApiSessionTopologyBlocker::PaperPortNotUsed,
            IbkrApiSessionTopologyBlocker::GatewayModeNotPaper,
            IbkrApiSessionTopologyBlocker::EnvironmentNotPaper,
            IbkrApiSessionTopologyBlocker::DeterministicClientIdMissing,
            IbkrApiSessionTopologyBlocker::ProcessIdentityMissing,
            IbkrApiSessionTopologyBlocker::AccountFingerprintHashInvalid,
            IbkrApiSessionTopologyBlocker::ApiServerVersionMissing,
            IbkrApiSessionTopologyBlocker::DataEntitlementsMissing,
            IbkrApiSessionTopologyBlocker::StartupTimeMissing,
            IbkrApiSessionTopologyBlocker::AttestationExpiryMissing,
        ]
    );
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
    use IbkrApiSessionTopologyBlocker as Blocker;

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
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::HostNotLoopback,
            Blocker::LivePortDenied,
            Blocker::PaperPortNotUsed,
            Blocker::GatewayModeNotPaper,
            Blocker::EnvironmentNotPaper,
            Blocker::DeterministicClientIdMissing,
            Blocker::ProcessIdentityMissing,
            Blocker::AccountFingerprintHashInvalid,
            Blocker::ApiServerVersionMissing,
            Blocker::DataEntitlementsMissing,
            Blocker::StartupTimeMissing,
            Blocker::AttestationExpiryMissing,
        ]
    );
}

#[test]
fn topology_rejects_each_paper_gateway_gap_independently() {
    use IbkrApiSessionTopologyBlocker as Blocker;

    let cases: [(fn(&mut IbkrApiSessionTopologyV1), Blocker); 16] = [
        (
            |topology| topology.contract_id = "ibkr_api_session_topology_v1_fixture".to_string(),
            Blocker::ContractIdMismatch,
        ),
        (
            |topology| topology.source_version = 2,
            Blocker::SourceVersionMismatch,
        ),
        (
            |topology| topology.topology_present = false,
            Blocker::TopologyMissing,
        ),
        (
            |topology| topology.api_baseline = "client_portal_web_api_denied".to_string(),
            Blocker::ApiBaselineMismatch,
        ),
        (
            |topology| topology.runtime_owner = "operator-laptop".to_string(),
            Blocker::RuntimeOwnerMismatch,
        ),
        (
            |topology| topology.host = "192.0.2.10".to_string(),
            Blocker::HostNotLoopback,
        ),
        (|topology| topology.port = 1, Blocker::PaperPortNotUsed),
        (
            |topology| topology.gateway_mode = IbkrGatewayProcessMode::ReadOnlyGateway,
            Blocker::GatewayModeNotPaper,
        ),
        (
            |topology| topology.environment = BrokerEnvironment::ReadOnly,
            Blocker::EnvironmentNotPaper,
        ),
        (
            |topology| topology.deterministic_client_id_present = false,
            Blocker::DeterministicClientIdMissing,
        ),
        (
            |topology| topology.process_identity_recorded = false,
            Blocker::ProcessIdentityMissing,
        ),
        (
            |topology| topology.account_fingerprint_hash = "paper_account".to_string(),
            Blocker::AccountFingerprintHashInvalid,
        ),
        (
            |topology| topology.api_server_version_recorded = false,
            Blocker::ApiServerVersionMissing,
        ),
        (
            |topology| topology.data_entitlements_recorded = false,
            Blocker::DataEntitlementsMissing,
        ),
        (
            |topology| topology.startup_time_recorded = false,
            Blocker::StartupTimeMissing,
        ),
        (
            |topology| topology.attestation_expiry_recorded = false,
            Blocker::AttestationExpiryMissing,
        ),
    ];

    for (mutate, blocker) in cases {
        let mut topology = IbkrApiSessionTopologyV1::source_template();
        mutate(&mut topology);
        assert_single_topology_blocker(topology.validate(), blocker);
    }

    let live_port = IbkrApiSessionTopologyV1 {
        port: IBKR_LIVE_TWS_PORT,
        ..IbkrApiSessionTopologyV1::source_template()
    };
    let verdict = live_port.validate();
    assert_eq!(
        verdict.blockers,
        vec![Blocker::LivePortDenied, Blocker::PaperPortNotUsed]
    );
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

fn assert_single_secret_slot_blocker(
    verdict: openclaw_types::IbkrSecretSlotContractVerdict,
    blocker: IbkrSecretSlotContractBlocker,
) {
    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}

fn assert_single_topology_blocker(
    verdict: openclaw_types::IbkrApiSessionTopologyVerdict,
    blocker: IbkrApiSessionTopologyBlocker,
) {
    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
