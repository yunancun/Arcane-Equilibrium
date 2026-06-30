//! IBKR feature-flag, secret, and scoped-authorization matrix.
//!
//! This module is source-only validation for ADR-0048. It does not read
//! environment secrets, inspect secret contents, open sockets, contact IBKR, or
//! route broker orders.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::{is_sha256_hex, IbkrPhase2GateArtifactV1};
use crate::ibkr_phase2_gate::IbkrSessionAttestationV1;
use crate::ibkr_phase2_runtime::IbkrSecretSlotContractV1;
use crate::stock_etf_lane::{
    AssetLane, AuthorityScope, Broker, BrokerCapabilityRequest, BrokerEnvironment, BrokerOperation,
    StockEtfFeatureFlags,
};

pub const FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID: &str = "feature_flag_secret_auth_matrix_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfAuthorizationEnvelopeV1 {
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub permission_scope: AuthorityScope,
    pub secret_slot_fingerprint: String,
    pub account_fingerprint_hash: String,
    pub risk_config_hash: String,
    pub expires_at_ms: u64,
}

impl Default for StockEtfAuthorizationEnvelopeV1 {
    fn default() -> Self {
        Self {
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::ReadOnly,
            permission_scope: AuthorityScope::Denied,
            secret_slot_fingerprint: String::new(),
            account_fingerprint_hash: String::new(),
            risk_config_hash: String::new(),
            expires_at_ms: 0,
        }
    }
}

impl StockEtfAuthorizationEnvelopeV1 {
    pub fn paper_fixture(expires_at_ms: u64) -> Self {
        Self {
            environment: BrokerEnvironment::Paper,
            permission_scope: AuthorityScope::PaperRehearsal,
            secret_slot_fingerprint: "a".repeat(64),
            account_fingerprint_hash: "b".repeat(64),
            risk_config_hash: "d".repeat(64),
            expires_at_ms,
            ..Self::default()
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FeatureFlagSecretAuthMatrixV1 {
    pub flags: StockEtfFeatureFlags,
    pub secret_slot_contract: IbkrSecretSlotContractV1,
    pub phase2_gate_artifact: IbkrPhase2GateArtifactV1,
    pub session_attestation: IbkrSessionAttestationV1,
    pub authorization_envelope: StockEtfAuthorizationEnvelopeV1,
    pub gui_lane_state_override_denied: bool,
    pub server_rust_matrix_authoritative: bool,
}

impl Default for FeatureFlagSecretAuthMatrixV1 {
    fn default() -> Self {
        Self {
            flags: StockEtfFeatureFlags::default(),
            secret_slot_contract: IbkrSecretSlotContractV1::default(),
            phase2_gate_artifact: IbkrPhase2GateArtifactV1::default(),
            session_attestation: IbkrSessionAttestationV1::default(),
            authorization_envelope: StockEtfAuthorizationEnvelopeV1::default(),
            gui_lane_state_override_denied: false,
            server_rust_matrix_authoritative: false,
        }
    }
}

impl FeatureFlagSecretAuthMatrixV1 {
    pub fn validate_operation(
        &self,
        request: BrokerCapabilityRequest,
        now_ms: u64,
    ) -> FeatureFlagSecretAuthVerdict {
        use FeatureFlagSecretAuthBlocker as Blocker;

        let mut blockers = Vec::new();

        if !self.server_rust_matrix_authoritative {
            blockers.push(Blocker::ServerRustMatrixNotAuthoritative);
        }
        if !self.gui_lane_state_override_denied {
            blockers.push(Blocker::GuiLaneStateOverrideNotDenied);
        }
        if request.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if request.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if request.environment == BrokerEnvironment::LiveReservedDenied {
            blockers.push(Blocker::LiveEnvironmentDenied);
        }
        if !request.instrument_kind.allowed_for_stock_etf_cash() {
            blockers.push(Blocker::InstrumentKindDenied);
        }
        if matches!(
            request.operation,
            BrokerOperation::LiveOrderSubmit
                | BrokerOperation::MarginOrShort
                | BrokerOperation::OptionsOrCfd
                | BrokerOperation::TransferOrAccountWrite
        ) {
            blockers.push(Blocker::LiveOrAccountWriteOperationDenied);
        }
        if !self.flags.stock_etf_lane_enabled {
            blockers.push(Blocker::LaneFlagDisabled);
        }
        if request.operation.is_read() && !self.flags.ibkr_readonly_enabled {
            blockers.push(Blocker::ReadonlyFlagDisabled);
        }
        if request.operation.is_paper_write() && !self.flags.ibkr_paper_enabled {
            blockers.push(Blocker::PaperFlagDisabled);
        }
        if request.operation.is_paper_write() && self.flags.stock_etf_shadow_only {
            blockers.push(Blocker::ShadowOnlyBlocksPaper);
        }

        let secret_verdict = self.secret_slot_contract.validate();
        if !secret_verdict.accepted {
            blockers.push(Blocker::SecretContractRejected);
        }
        if !self.secret_slot_contract.live_secret_absent_or_empty {
            blockers.push(Blocker::LiveSecretAbsentOrEmptyNotProven);
        }

        let artifact_verdict = self.phase2_gate_artifact.validate();
        if !artifact_verdict.ibkr_contact_allowed {
            blockers.push(Blocker::Phase2ArtifactRejected);
        }

        let session_verdict = self.session_attestation.validate(now_ms);
        if !session_verdict.attestation_accepted {
            blockers.push(Blocker::SessionAttestationRejected);
        }

        self.validate_authorization_envelope(request, now_ms, &mut blockers);

        FeatureFlagSecretAuthVerdict {
            request,
            allowed: blockers.is_empty(),
            effective_authority_scope: if blockers.is_empty() {
                request.operation.authority_scope()
            } else {
                AuthorityScope::Denied
            },
            blockers,
        }
    }

    fn validate_authorization_envelope(
        &self,
        request: BrokerCapabilityRequest,
        now_ms: u64,
        blockers: &mut Vec<FeatureFlagSecretAuthBlocker>,
    ) {
        use FeatureFlagSecretAuthBlocker as Blocker;

        let envelope = &self.authorization_envelope;
        if envelope.asset_lane != request.asset_lane {
            blockers.push(Blocker::AuthorizationEnvelopeMismatch);
        }
        if envelope.broker != request.broker {
            blockers.push(Blocker::AuthorizationEnvelopeMismatch);
        }
        if envelope.environment != request.environment {
            blockers.push(Blocker::AuthorizationEnvelopeMismatch);
        }
        if envelope.permission_scope != request.operation.authority_scope() {
            blockers.push(Blocker::PermissionScopeMismatch);
        }
        if !is_sha256_hex(&envelope.secret_slot_fingerprint) {
            blockers.push(Blocker::SecretSlotFingerprintInvalid);
        }
        if !is_sha256_hex(&envelope.account_fingerprint_hash) {
            blockers.push(Blocker::AccountFingerprintHashInvalid);
        }
        if !is_sha256_hex(&envelope.risk_config_hash) {
            blockers.push(Blocker::RiskConfigHashInvalid);
        }
        if envelope.expires_at_ms == 0 || now_ms >= envelope.expires_at_ms {
            blockers.push(Blocker::AuthorizationEnvelopeExpired);
        }
        if envelope.secret_slot_fingerprint != self.secret_slot_contract.secret_slot_fingerprint
            || envelope.secret_slot_fingerprint != self.session_attestation.secret_slot_fingerprint
        {
            blockers.push(Blocker::SecretSlotFingerprintMismatch);
        }
        if envelope.account_fingerprint_hash != self.secret_slot_contract.account_fingerprint_hash
            || envelope.account_fingerprint_hash
                != self
                    .phase2_gate_artifact
                    .api_session_topology
                    .account_fingerprint_hash
            || envelope.account_fingerprint_hash != self.session_attestation.account_fingerprint
        {
            blockers.push(Blocker::AccountFingerprintMismatch);
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct FeatureFlagSecretAuthVerdict {
    pub request: BrokerCapabilityRequest,
    pub allowed: bool,
    pub effective_authority_scope: AuthorityScope,
    pub blockers: Vec<FeatureFlagSecretAuthBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum FeatureFlagSecretAuthBlocker {
    ServerRustMatrixNotAuthoritative,
    GuiLaneStateOverrideNotDenied,
    WrongAssetLane,
    WrongBroker,
    LiveEnvironmentDenied,
    InstrumentKindDenied,
    LiveOrAccountWriteOperationDenied,
    LaneFlagDisabled,
    ReadonlyFlagDisabled,
    PaperFlagDisabled,
    ShadowOnlyBlocksPaper,
    SecretContractRejected,
    LiveSecretAbsentOrEmptyNotProven,
    Phase2ArtifactRejected,
    SessionAttestationRejected,
    AuthorizationEnvelopeMismatch,
    PermissionScopeMismatch,
    SecretSlotFingerprintInvalid,
    AccountFingerprintHashInvalid,
    RiskConfigHashInvalid,
    AuthorizationEnvelopeExpired,
    SecretSlotFingerprintMismatch,
    AccountFingerprintMismatch,
}

pub fn evaluate_feature_flag_secret_auth_matrix(
    matrix: &FeatureFlagSecretAuthMatrixV1,
    request: BrokerCapabilityRequest,
    now_ms: u64,
) -> FeatureFlagSecretAuthVerdict {
    matrix.validate_operation(request, now_ms)
}
