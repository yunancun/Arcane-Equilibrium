//! IBKR Phase 2 pre-contact gate contracts for ADR-0048 / AMD-2026-06-29-01.
//!
//! This module is source-only validation. It performs no socket I/O, no secret
//! lookup, no IBKR client construction, and no broker order routing.

use serde::{Deserialize, Serialize};

use crate::stock_etf_lane::BrokerEnvironment;

pub const IBKR_PHASE2_ADR: &str = "ADR-0048";
pub const IBKR_PHASE2_AMD: &str = "AMD-2026-06-29-01";
pub const IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID: &str = "phase2_ibkr_external_surface_gate_v1";
pub const NON_BYBIT_API_ALLOWLIST_CONTRACT_ID: &str = "non_bybit_api_allowlist_v1";
pub const IBKR_SESSION_ATTESTATION_CONTRACT_ID: &str = "ibkr_session_attestation_v1";
pub const IBKR_PAPER_GATEWAY_DEFAULT_PORT: u16 = 4002;
pub const IBKR_LIVE_GATEWAY_PORT: u16 = 4001;
pub const IBKR_LIVE_TWS_PORT: u16 = 7496;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum IbkrExternalSurfaceGateStatus {
    Pass,
    Blocked,
}

impl Default for IbkrExternalSurfaceGateStatus {
    fn default() -> Self {
        Self::Blocked
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrApiBaseline {
    IbGatewayTwsApi,
    ClientPortalWebApiDenied,
}

impl Default for IbkrApiBaseline {
    fn default() -> Self {
        Self::IbGatewayTwsApi
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrHostPolicy {
    LoopbackOnly,
    NetworkHostDenied,
}

impl Default for IbkrHostPolicy {
    fn default() -> Self {
        Self::LoopbackOnly
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrPortPolicy {
    PaperGatewayPortOnly,
    LiveOrTwsPortDenied,
}

impl Default for IbkrPortPolicy {
    fn default() -> Self {
        Self::PaperGatewayPortOnly
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrExternalSurfaceGateV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub status: IbkrExternalSurfaceGateStatus,
    pub adr: String,
    pub amd: String,
    pub api_baseline: IbkrApiBaseline,
    pub host_policy: IbkrHostPolicy,
    pub port_policy: IbkrPortPolicy,
    pub live_ports_denied: bool,
    pub secret_contract_present: bool,
    pub live_secret_absent_or_empty: bool,
    pub api_allowlist_present: bool,
    pub redaction_suite_passed: bool,
    pub rate_limit_policy_present: bool,
    pub audit_event_policy_present: bool,
    pub paper_attestation_contract_present: bool,
    pub python_no_write_guard_present: bool,
    pub ibkr_call_performed: bool,
}

impl Default for IbkrExternalSurfaceGateV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            status: IbkrExternalSurfaceGateStatus::Blocked,
            adr: IBKR_PHASE2_ADR.to_string(),
            amd: IBKR_PHASE2_AMD.to_string(),
            api_baseline: IbkrApiBaseline::IbGatewayTwsApi,
            host_policy: IbkrHostPolicy::LoopbackOnly,
            port_policy: IbkrPortPolicy::PaperGatewayPortOnly,
            live_ports_denied: false,
            secret_contract_present: false,
            live_secret_absent_or_empty: false,
            api_allowlist_present: false,
            redaction_suite_passed: false,
            rate_limit_policy_present: false,
            audit_event_policy_present: false,
            paper_attestation_contract_present: false,
            python_no_write_guard_present: false,
            ibkr_call_performed: false,
        }
    }
}

impl IbkrExternalSurfaceGateV1 {
    pub fn passing_fixture() -> Self {
        Self {
            contract_id: IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID.to_string(),
            source_version: 1,
            status: IbkrExternalSurfaceGateStatus::Pass,
            live_ports_denied: true,
            secret_contract_present: true,
            live_secret_absent_or_empty: true,
            api_allowlist_present: true,
            redaction_suite_passed: true,
            rate_limit_policy_present: true,
            audit_event_policy_present: true,
            paper_attestation_contract_present: true,
            python_no_write_guard_present: true,
            ibkr_call_performed: false,
            ..Self::default()
        }
    }

    pub fn validate(&self) -> IbkrExternalSurfaceGateVerdict {
        use IbkrExternalSurfaceGateBlocker as Blocker;

        let mut blockers = Vec::new();

        if self.contract_id != IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.status != IbkrExternalSurfaceGateStatus::Pass {
            blockers.push(Blocker::StatusNotPass);
        }
        if self.adr != IBKR_PHASE2_ADR {
            blockers.push(Blocker::AdrMismatch);
        }
        if self.amd != IBKR_PHASE2_AMD {
            blockers.push(Blocker::AmdMismatch);
        }
        if self.api_baseline != IbkrApiBaseline::IbGatewayTwsApi {
            blockers.push(Blocker::ApiBaselineMismatch);
        }
        if self.host_policy != IbkrHostPolicy::LoopbackOnly {
            blockers.push(Blocker::HostPolicyNotLoopbackOnly);
        }
        if self.port_policy != IbkrPortPolicy::PaperGatewayPortOnly {
            blockers.push(Blocker::PortPolicyNotPaperGatewayOnly);
        }
        if !self.live_ports_denied {
            blockers.push(Blocker::LivePortsNotDenied);
        }
        if !self.secret_contract_present {
            blockers.push(Blocker::SecretContractMissing);
        }
        if !self.live_secret_absent_or_empty {
            blockers.push(Blocker::LiveSecretPresentOrUnknown);
        }
        if !self.api_allowlist_present {
            blockers.push(Blocker::ApiAllowlistMissing);
        }
        if !self.redaction_suite_passed {
            blockers.push(Blocker::RedactionSuiteMissing);
        }
        if !self.rate_limit_policy_present {
            blockers.push(Blocker::RateLimitPolicyMissing);
        }
        if !self.audit_event_policy_present {
            blockers.push(Blocker::AuditEventPolicyMissing);
        }
        if !self.paper_attestation_contract_present {
            blockers.push(Blocker::PaperAttestationContractMissing);
        }
        if !self.python_no_write_guard_present {
            blockers.push(Blocker::PythonNoWriteGuardMissing);
        }
        if self.ibkr_call_performed {
            blockers.push(Blocker::IbkrCallAlreadyPerformed);
        }

        IbkrExternalSurfaceGateVerdict {
            status: self.status,
            ibkr_contact_allowed: blockers.is_empty(),
            blockers,
        }
    }

    pub fn can_contact_ibkr(&self) -> bool {
        self.validate().ibkr_contact_allowed
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrExternalSurfaceGateBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    StatusNotPass,
    AdrMismatch,
    AmdMismatch,
    ApiBaselineMismatch,
    HostPolicyNotLoopbackOnly,
    PortPolicyNotPaperGatewayOnly,
    LivePortsNotDenied,
    SecretContractMissing,
    LiveSecretPresentOrUnknown,
    ApiAllowlistMissing,
    RedactionSuiteMissing,
    RateLimitPolicyMissing,
    AuditEventPolicyMissing,
    PaperAttestationContractMissing,
    PythonNoWriteGuardMissing,
    IbkrCallAlreadyPerformed,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrExternalSurfaceGateVerdict {
    pub status: IbkrExternalSurfaceGateStatus,
    pub ibkr_contact_allowed: bool,
    pub blockers: Vec<IbkrExternalSurfaceGateBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NonBybitApiAction {
    ServerTimeRead,
    ConnectionHealthRead,
    AccountSummarySnapshotRead,
    PortfolioPositionsSnapshotRead,
    ContractDetailsRead,
    MarketDataSnapshotRead,
    MarketDataSubscriptionRead,
    HistoricalBarsRead,
    OpenPaperOrdersRead,
    PaperExecutionsCommissionsRead,
    PaperOrderSubmit,
    PaperOrderCancel,
    PaperOrderReplace,
    LiveOrderSubmit,
    LiveAccountQuery,
    AccountTransfer,
    MarginEnablement,
    ShortBorrow,
    OptionsTrading,
    CfdTrading,
    MarketDataEntitlementPurchase,
    AccountManagementWrite,
    ClientPortalWebApiUse,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NonBybitApiDenialReason {
    LiveOrderDenied,
    LiveAccountFingerprintDenied,
    AccountTransferDenied,
    MarginDenied,
    ShortDenied,
    OptionsDenied,
    CfdDenied,
    MarketDataEntitlementPurchaseDenied,
    AccountManagementWriteDenied,
    ClientPortalWebApiDenied,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct NonBybitApiAllowlistDecision {
    pub action: NonBybitApiAction,
    pub allowed_after_external_gate: bool,
    pub requires_external_surface_gate: bool,
    pub requires_session_attestation: bool,
    pub requires_paper_order_gates: bool,
    pub denied: bool,
    pub denial_reason: Option<NonBybitApiDenialReason>,
}

impl NonBybitApiAllowlistDecision {
    const fn allowed_read(action: NonBybitApiAction, requires_session_attestation: bool) -> Self {
        Self {
            action,
            allowed_after_external_gate: true,
            requires_external_surface_gate: true,
            requires_session_attestation,
            requires_paper_order_gates: false,
            denied: false,
            denial_reason: None,
        }
    }

    const fn paper_write(action: NonBybitApiAction) -> Self {
        Self {
            action,
            allowed_after_external_gate: false,
            requires_external_surface_gate: true,
            requires_session_attestation: true,
            requires_paper_order_gates: true,
            denied: false,
            denial_reason: None,
        }
    }

    const fn denied(action: NonBybitApiAction, denial_reason: NonBybitApiDenialReason) -> Self {
        Self {
            action,
            allowed_after_external_gate: false,
            requires_external_surface_gate: false,
            requires_session_attestation: false,
            requires_paper_order_gates: false,
            denied: true,
            denial_reason: Some(denial_reason),
        }
    }
}

pub const fn classify_non_bybit_api_action(
    action: NonBybitApiAction,
) -> NonBybitApiAllowlistDecision {
    use NonBybitApiAction as Action;
    use NonBybitApiDenialReason as Deny;

    match action {
        Action::ServerTimeRead
        | Action::ConnectionHealthRead
        | Action::ContractDetailsRead
        | Action::MarketDataSnapshotRead
        | Action::MarketDataSubscriptionRead
        | Action::HistoricalBarsRead => NonBybitApiAllowlistDecision::allowed_read(action, false),
        Action::AccountSummarySnapshotRead
        | Action::PortfolioPositionsSnapshotRead
        | Action::OpenPaperOrdersRead
        | Action::PaperExecutionsCommissionsRead => {
            NonBybitApiAllowlistDecision::allowed_read(action, true)
        }
        Action::PaperOrderSubmit | Action::PaperOrderCancel | Action::PaperOrderReplace => {
            NonBybitApiAllowlistDecision::paper_write(action)
        }
        Action::LiveOrderSubmit => {
            NonBybitApiAllowlistDecision::denied(action, Deny::LiveOrderDenied)
        }
        Action::LiveAccountQuery => {
            NonBybitApiAllowlistDecision::denied(action, Deny::LiveAccountFingerprintDenied)
        }
        Action::AccountTransfer => {
            NonBybitApiAllowlistDecision::denied(action, Deny::AccountTransferDenied)
        }
        Action::MarginEnablement => {
            NonBybitApiAllowlistDecision::denied(action, Deny::MarginDenied)
        }
        Action::ShortBorrow => NonBybitApiAllowlistDecision::denied(action, Deny::ShortDenied),
        Action::OptionsTrading => NonBybitApiAllowlistDecision::denied(action, Deny::OptionsDenied),
        Action::CfdTrading => NonBybitApiAllowlistDecision::denied(action, Deny::CfdDenied),
        Action::MarketDataEntitlementPurchase => {
            NonBybitApiAllowlistDecision::denied(action, Deny::MarketDataEntitlementPurchaseDenied)
        }
        Action::AccountManagementWrite => {
            NonBybitApiAllowlistDecision::denied(action, Deny::AccountManagementWriteDenied)
        }
        Action::ClientPortalWebApiUse => {
            NonBybitApiAllowlistDecision::denied(action, Deny::ClientPortalWebApiDenied)
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum IbkrSessionAttestationStatus {
    PaperAttested,
    ReadonlyAttested,
    Blocked,
}

impl Default for IbkrSessionAttestationStatus {
    fn default() -> Self {
        Self::Blocked
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrGatewayMode {
    Paper,
    ReadOnly,
    LiveDenied,
    Unknown,
}

impl Default for IbkrGatewayMode {
    fn default() -> Self {
        Self::Unknown
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrSecretSlotMode {
    ReadOnly,
    Paper,
    LiveDenied,
    Missing,
    WorldReadable,
    Unknown,
}

impl Default for IbkrSecretSlotMode {
    fn default() -> Self {
        Self::Unknown
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrSessionAttestationV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub status: IbkrSessionAttestationStatus,
    pub account_fingerprint: String,
    pub account_fingerprint_is_live: bool,
    pub environment: BrokerEnvironment,
    pub host: String,
    pub port: u16,
    pub process_identity: String,
    pub gateway_mode: IbkrGatewayMode,
    pub secret_slot_fingerprint: String,
    pub secret_slot_mode: IbkrSecretSlotMode,
    pub secret_world_readable: bool,
    pub live_secret_absent_or_empty: bool,
    pub env_var_credential_fallback_used: bool,
    pub api_server_version: String,
    pub attested_at_ms: u64,
    pub expires_at_ms: u64,
    pub raw_artifact_hash: String,
}

impl Default for IbkrSessionAttestationV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            status: IbkrSessionAttestationStatus::Blocked,
            account_fingerprint: String::new(),
            account_fingerprint_is_live: false,
            environment: BrokerEnvironment::ReadOnly,
            host: String::new(),
            port: 0,
            process_identity: String::new(),
            gateway_mode: IbkrGatewayMode::Unknown,
            secret_slot_fingerprint: String::new(),
            secret_slot_mode: IbkrSecretSlotMode::Unknown,
            secret_world_readable: false,
            live_secret_absent_or_empty: false,
            env_var_credential_fallback_used: false,
            api_server_version: String::new(),
            attested_at_ms: 0,
            expires_at_ms: 0,
            raw_artifact_hash: String::new(),
        }
    }
}

impl IbkrSessionAttestationV1 {
    pub fn paper_fixture() -> Self {
        Self {
            contract_id: IBKR_SESSION_ATTESTATION_CONTRACT_ID.to_string(),
            source_version: 1,
            status: IbkrSessionAttestationStatus::PaperAttested,
            account_fingerprint: "paper_account_fingerprint_hash".to_string(),
            account_fingerprint_is_live: false,
            environment: BrokerEnvironment::Paper,
            host: "127.0.0.1".to_string(),
            port: IBKR_PAPER_GATEWAY_DEFAULT_PORT,
            process_identity: "trade-core:ibgateway-paper".to_string(),
            gateway_mode: IbkrGatewayMode::Paper,
            secret_slot_fingerprint: "paper_secret_slot_fingerprint_hash".to_string(),
            secret_slot_mode: IbkrSecretSlotMode::Paper,
            secret_world_readable: false,
            live_secret_absent_or_empty: true,
            env_var_credential_fallback_used: false,
            api_server_version: "source_fixture_only".to_string(),
            attested_at_ms: 1_772_232_000_000,
            expires_at_ms: 1_772_235_600_000,
            raw_artifact_hash: "redacted_raw_artifact_hash".to_string(),
        }
    }

    pub fn validate(&self, now_ms: u64) -> IbkrSessionAttestationVerdict {
        use IbkrSessionAttestationBlocker as Blocker;

        let mut blockers = Vec::new();

        if self.contract_id != IBKR_SESSION_ATTESTATION_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        match self.status {
            IbkrSessionAttestationStatus::PaperAttested
            | IbkrSessionAttestationStatus::ReadonlyAttested => {}
            IbkrSessionAttestationStatus::Blocked => blockers.push(Blocker::StatusBlocked),
        }

        if !matches!(
            self.environment,
            BrokerEnvironment::Paper | BrokerEnvironment::ReadOnly
        ) {
            blockers.push(Blocker::EnvironmentDenied);
        }
        if !is_loopback_or_unix_local_host(&self.host) {
            blockers.push(Blocker::HostNotLoopback);
        }
        if self.port == IBKR_LIVE_GATEWAY_PORT || self.port == IBKR_LIVE_TWS_PORT {
            blockers.push(Blocker::LivePortDenied);
        }
        if self.port != IBKR_PAPER_GATEWAY_DEFAULT_PORT {
            blockers.push(Blocker::PortNotPaperGatewayDefault);
        }
        if self.account_fingerprint.trim().is_empty() {
            blockers.push(Blocker::MissingAccountFingerprint);
        }
        if self.account_fingerprint_is_live {
            blockers.push(Blocker::LiveAccountFingerprint);
        }
        if self.process_identity.trim().is_empty() {
            blockers.push(Blocker::MissingProcessIdentity);
        }
        if matches!(
            self.gateway_mode,
            IbkrGatewayMode::LiveDenied | IbkrGatewayMode::Unknown
        ) {
            blockers.push(Blocker::UnknownOrLiveGatewayMode);
        }
        if self.secret_slot_fingerprint.trim().is_empty() {
            blockers.push(Blocker::MissingSecretSlotFingerprint);
        }
        match self.secret_slot_mode {
            IbkrSecretSlotMode::Paper | IbkrSecretSlotMode::ReadOnly => {}
            IbkrSecretSlotMode::Missing => blockers.push(Blocker::SecretSlotMissing),
            IbkrSecretSlotMode::WorldReadable => blockers.push(Blocker::SecretSlotWorldReadable),
            IbkrSecretSlotMode::LiveDenied | IbkrSecretSlotMode::Unknown => {
                blockers.push(Blocker::SecretSlotModeDenied)
            }
        }
        if self.secret_world_readable {
            blockers.push(Blocker::SecretSlotWorldReadable);
        }
        if !self.live_secret_absent_or_empty {
            blockers.push(Blocker::LiveSecretPresentOrUnknown);
        }
        if self.env_var_credential_fallback_used {
            blockers.push(Blocker::EnvVarCredentialFallback);
        }
        if self.api_server_version.trim().is_empty() {
            blockers.push(Blocker::MissingApiServerVersion);
        }
        if self.raw_artifact_hash.trim().is_empty() {
            blockers.push(Blocker::MissingRawArtifactHash);
        }
        if self.expires_at_ms <= self.attested_at_ms || self.attested_at_ms == 0 {
            blockers.push(Blocker::InvalidAttestationWindow);
        }
        if now_ms >= self.expires_at_ms {
            blockers.push(Blocker::StaleAttestation);
        }

        IbkrSessionAttestationVerdict {
            status: self.status,
            attestation_accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrSessionAttestationBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    StatusBlocked,
    EnvironmentDenied,
    HostNotLoopback,
    LivePortDenied,
    PortNotPaperGatewayDefault,
    MissingAccountFingerprint,
    LiveAccountFingerprint,
    MissingProcessIdentity,
    UnknownOrLiveGatewayMode,
    MissingSecretSlotFingerprint,
    SecretSlotMissing,
    SecretSlotWorldReadable,
    SecretSlotModeDenied,
    LiveSecretPresentOrUnknown,
    EnvVarCredentialFallback,
    MissingApiServerVersion,
    MissingRawArtifactHash,
    InvalidAttestationWindow,
    StaleAttestation,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrSessionAttestationVerdict {
    pub status: IbkrSessionAttestationStatus,
    pub attestation_accepted: bool,
    pub blockers: Vec<IbkrSessionAttestationBlocker>,
}

pub fn is_loopback_or_unix_local_host(host: &str) -> bool {
    let normalized = host.trim().to_ascii_lowercase();
    matches!(normalized.as_str(), "127.0.0.1" | "::1" | "localhost")
        || normalized.starts_with("unix:")
}
