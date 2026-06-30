//! IBKR Phase 2 secret-slot and API topology contracts.
//!
//! These source-only contracts describe the evidence shape required before an
//! immutable Phase 2 gate artifact can pass. They do not read secret contents,
//! open sockets, start IB Gateway/TWS, or route broker orders.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_gate::{
    is_loopback_or_unix_local_host, IBKR_LIVE_GATEWAY_PORT, IBKR_LIVE_TWS_PORT,
    IBKR_PAPER_GATEWAY_DEFAULT_PORT,
};
use crate::stock_etf_lane::BrokerEnvironment;

pub const IBKR_SECRET_SLOT_CONTRACT_ID: &str = "ibkr_secret_slot_contract_v1";
pub const IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID: &str = "ibkr_api_session_topology_v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrSecretSlotPosture {
    Missing,
    PresentHashed,
    LiveAbsentOrEmpty,
    LivePresentDenied,
    Unknown,
}

impl Default for IbkrSecretSlotPosture {
    fn default() -> Self {
        Self::Unknown
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrSecretSlotContractV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub contract_present: bool,
    pub readonly_slot_posture: IbkrSecretSlotPosture,
    pub paper_slot_posture: IbkrSecretSlotPosture,
    pub live_slot_posture: IbkrSecretSlotPosture,
    pub secret_slot_fingerprint: String,
    pub account_fingerprint_hash: String,
    pub owner_only_permissions: bool,
    pub env_var_credential_fallback_denied: bool,
    pub secret_content_serialized: bool,
    pub account_id_serialized: bool,
    pub live_secret_absent_or_empty: bool,
}

impl Default for IbkrSecretSlotContractV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            contract_present: false,
            readonly_slot_posture: IbkrSecretSlotPosture::Unknown,
            paper_slot_posture: IbkrSecretSlotPosture::Unknown,
            live_slot_posture: IbkrSecretSlotPosture::Unknown,
            secret_slot_fingerprint: String::new(),
            account_fingerprint_hash: String::new(),
            owner_only_permissions: false,
            env_var_credential_fallback_denied: false,
            secret_content_serialized: false,
            account_id_serialized: false,
            live_secret_absent_or_empty: false,
        }
    }
}

impl IbkrSecretSlotContractV1 {
    pub fn source_template() -> Self {
        Self {
            contract_id: IBKR_SECRET_SLOT_CONTRACT_ID.to_string(),
            source_version: 1,
            contract_present: true,
            readonly_slot_posture: IbkrSecretSlotPosture::PresentHashed,
            paper_slot_posture: IbkrSecretSlotPosture::PresentHashed,
            live_slot_posture: IbkrSecretSlotPosture::LiveAbsentOrEmpty,
            secret_slot_fingerprint: "a".repeat(64),
            account_fingerprint_hash: "b".repeat(64),
            owner_only_permissions: true,
            env_var_credential_fallback_denied: true,
            secret_content_serialized: false,
            account_id_serialized: false,
            live_secret_absent_or_empty: true,
        }
    }

    pub fn validate(&self) -> IbkrSecretSlotContractVerdict {
        use IbkrSecretSlotContractBlocker as Blocker;

        let mut blockers = Vec::new();
        if self.contract_id != IBKR_SECRET_SLOT_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if !self.contract_present {
            blockers.push(Blocker::ContractMissing);
        }
        if !matches!(
            self.readonly_slot_posture,
            IbkrSecretSlotPosture::PresentHashed | IbkrSecretSlotPosture::Missing
        ) {
            blockers.push(Blocker::ReadonlySlotPostureInvalid);
        }
        if self.paper_slot_posture != IbkrSecretSlotPosture::PresentHashed {
            blockers.push(Blocker::PaperSlotMissingOrUnhashed);
        }
        if self.live_slot_posture != IbkrSecretSlotPosture::LiveAbsentOrEmpty {
            blockers.push(Blocker::LiveSlotPresentOrUnknown);
        }
        if !is_sha256_hex(&self.secret_slot_fingerprint) {
            blockers.push(Blocker::SecretSlotFingerprintInvalid);
        }
        if !is_sha256_hex(&self.account_fingerprint_hash) {
            blockers.push(Blocker::AccountFingerprintHashInvalid);
        }
        if !self.owner_only_permissions {
            blockers.push(Blocker::OwnerOnlyPermissionsMissing);
        }
        if !self.env_var_credential_fallback_denied {
            blockers.push(Blocker::EnvVarCredentialFallbackNotDenied);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if self.account_id_serialized {
            blockers.push(Blocker::AccountIdSerialized);
        }
        if !self.live_secret_absent_or_empty {
            blockers.push(Blocker::LiveSecretAbsentOrEmptyNotProven);
        }

        IbkrSecretSlotContractVerdict {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrSecretSlotContractVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrSecretSlotContractBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrSecretSlotContractBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    ContractMissing,
    ReadonlySlotPostureInvalid,
    PaperSlotMissingOrUnhashed,
    LiveSlotPresentOrUnknown,
    SecretSlotFingerprintInvalid,
    AccountFingerprintHashInvalid,
    OwnerOnlyPermissionsMissing,
    EnvVarCredentialFallbackNotDenied,
    SecretContentSerialized,
    AccountIdSerialized,
    LiveSecretAbsentOrEmptyNotProven,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrGatewayProcessMode {
    PaperGateway,
    ReadOnlyGateway,
    LiveDenied,
    Unknown,
}

impl Default for IbkrGatewayProcessMode {
    fn default() -> Self {
        Self::Unknown
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrApiSessionTopologyV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub topology_present: bool,
    pub api_baseline: String,
    pub runtime_owner: String,
    pub host: String,
    pub port: u16,
    pub gateway_mode: IbkrGatewayProcessMode,
    pub environment: BrokerEnvironment,
    pub deterministic_client_id_present: bool,
    pub process_identity_recorded: bool,
    pub account_fingerprint_hash: String,
    pub api_server_version_recorded: bool,
    pub data_entitlements_recorded: bool,
    pub startup_time_recorded: bool,
    pub attestation_expiry_recorded: bool,
}

impl Default for IbkrApiSessionTopologyV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            topology_present: false,
            api_baseline: String::new(),
            runtime_owner: String::new(),
            host: String::new(),
            port: 0,
            gateway_mode: IbkrGatewayProcessMode::Unknown,
            environment: BrokerEnvironment::ReadOnly,
            deterministic_client_id_present: false,
            process_identity_recorded: false,
            account_fingerprint_hash: String::new(),
            api_server_version_recorded: false,
            data_entitlements_recorded: false,
            startup_time_recorded: false,
            attestation_expiry_recorded: false,
        }
    }
}

impl IbkrApiSessionTopologyV1 {
    pub fn source_template() -> Self {
        Self {
            contract_id: IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID.to_string(),
            source_version: 1,
            topology_present: true,
            api_baseline: "ib_gateway_tws_api".to_string(),
            runtime_owner: "trade-core".to_string(),
            host: "127.0.0.1".to_string(),
            port: IBKR_PAPER_GATEWAY_DEFAULT_PORT,
            gateway_mode: IbkrGatewayProcessMode::PaperGateway,
            environment: BrokerEnvironment::Paper,
            deterministic_client_id_present: true,
            process_identity_recorded: true,
            account_fingerprint_hash: "c".repeat(64),
            api_server_version_recorded: true,
            data_entitlements_recorded: true,
            startup_time_recorded: true,
            attestation_expiry_recorded: true,
        }
    }

    pub fn validate(&self) -> IbkrApiSessionTopologyVerdict {
        use IbkrApiSessionTopologyBlocker as Blocker;

        let mut blockers = Vec::new();
        if self.contract_id != IBKR_API_SESSION_TOPOLOGY_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if !self.topology_present {
            blockers.push(Blocker::TopologyMissing);
        }
        if self.api_baseline != "ib_gateway_tws_api" {
            blockers.push(Blocker::ApiBaselineMismatch);
        }
        if self.runtime_owner != "trade-core" {
            blockers.push(Blocker::RuntimeOwnerMismatch);
        }
        if !is_loopback_or_unix_local_host(&self.host) {
            blockers.push(Blocker::HostNotLoopback);
        }
        if self.port == IBKR_LIVE_GATEWAY_PORT || self.port == IBKR_LIVE_TWS_PORT {
            blockers.push(Blocker::LivePortDenied);
        }
        if self.port != IBKR_PAPER_GATEWAY_DEFAULT_PORT {
            blockers.push(Blocker::PaperPortNotUsed);
        }
        if self.gateway_mode != IbkrGatewayProcessMode::PaperGateway {
            blockers.push(Blocker::GatewayModeNotPaper);
        }
        if self.environment != BrokerEnvironment::Paper {
            blockers.push(Blocker::EnvironmentNotPaper);
        }
        if !self.deterministic_client_id_present {
            blockers.push(Blocker::DeterministicClientIdMissing);
        }
        if !self.process_identity_recorded {
            blockers.push(Blocker::ProcessIdentityMissing);
        }
        if !is_sha256_hex(&self.account_fingerprint_hash) {
            blockers.push(Blocker::AccountFingerprintHashInvalid);
        }
        if !self.api_server_version_recorded {
            blockers.push(Blocker::ApiServerVersionMissing);
        }
        if !self.data_entitlements_recorded {
            blockers.push(Blocker::DataEntitlementsMissing);
        }
        if !self.startup_time_recorded {
            blockers.push(Blocker::StartupTimeMissing);
        }
        if !self.attestation_expiry_recorded {
            blockers.push(Blocker::AttestationExpiryMissing);
        }

        IbkrApiSessionTopologyVerdict {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrApiSessionTopologyVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrApiSessionTopologyBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrApiSessionTopologyBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    TopologyMissing,
    ApiBaselineMismatch,
    RuntimeOwnerMismatch,
    HostNotLoopback,
    LivePortDenied,
    PaperPortNotUsed,
    GatewayModeNotPaper,
    EnvironmentNotPaper,
    DeterministicClientIdMissing,
    ProcessIdentityMissing,
    AccountFingerprintHashInvalid,
    ApiServerVersionMissing,
    DataEntitlementsMissing,
    StartupTimeMissing,
    AttestationExpiryMissing,
}

pub fn is_sha256_hex(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 64
        && bytes
            .iter()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(b))
}
