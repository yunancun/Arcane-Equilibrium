//! IBKR Phase 2 prerequisite policy contracts.
//!
//! These contracts describe policy presence for the external-surface gate. They
//! do not perform redaction, rate limiting, audit writes, secret lookup, socket
//! I/O, or broker order routing.

use serde::{Deserialize, Serialize};

pub const IBKR_REDACTION_POLICY_CONTRACT_ID: &str = "ibkr_redaction_policy_v1";
pub const IBKR_PAPER_ATTESTATION_CONTRACT_ID: &str = "ibkr_paper_attestation_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPolicyVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> IbkrPolicyVerdict<B> {
    pub fn accepted() -> Self {
        Self {
            accepted: true,
            blockers: Vec::new(),
        }
    }

    pub fn from_blockers(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrRedactionPolicyV1 {
    pub policy_present: bool,
    pub raw_payload_hash_required: bool,
    pub redacted_summary_hash_required: bool,
    pub account_id_in_logs_allowed: bool,
    pub secret_in_logs_allowed: bool,
    pub local_path_in_logs_allowed: bool,
    pub cookie_in_logs_allowed: bool,
    pub token_in_logs_allowed: bool,
    pub raw_payload_in_logs_allowed: bool,
    pub stack_trace_in_reports_allowed: bool,
}

impl Default for IbkrRedactionPolicyV1 {
    fn default() -> Self {
        Self {
            policy_present: false,
            raw_payload_hash_required: false,
            redacted_summary_hash_required: false,
            account_id_in_logs_allowed: false,
            secret_in_logs_allowed: false,
            local_path_in_logs_allowed: false,
            cookie_in_logs_allowed: false,
            token_in_logs_allowed: false,
            raw_payload_in_logs_allowed: false,
            stack_trace_in_reports_allowed: false,
        }
    }
}

impl IbkrRedactionPolicyV1 {
    pub fn source_template() -> Self {
        Self {
            policy_present: true,
            raw_payload_hash_required: true,
            redacted_summary_hash_required: true,
            account_id_in_logs_allowed: false,
            secret_in_logs_allowed: false,
            local_path_in_logs_allowed: false,
            cookie_in_logs_allowed: false,
            token_in_logs_allowed: false,
            raw_payload_in_logs_allowed: false,
            stack_trace_in_reports_allowed: false,
        }
    }

    pub fn validate(&self) -> IbkrPolicyVerdict<IbkrRedactionPolicyBlocker> {
        use IbkrRedactionPolicyBlocker as Blocker;

        let mut blockers = Vec::new();
        if !self.policy_present {
            blockers.push(Blocker::PolicyMissing);
        }
        if !self.raw_payload_hash_required {
            blockers.push(Blocker::RawPayloadHashNotRequired);
        }
        if !self.redacted_summary_hash_required {
            blockers.push(Blocker::RedactedSummaryHashNotRequired);
        }
        if self.account_id_in_logs_allowed {
            blockers.push(Blocker::AccountIdLogLeakAllowed);
        }
        if self.secret_in_logs_allowed {
            blockers.push(Blocker::SecretLogLeakAllowed);
        }
        if self.local_path_in_logs_allowed {
            blockers.push(Blocker::LocalPathLogLeakAllowed);
        }
        if self.cookie_in_logs_allowed {
            blockers.push(Blocker::CookieLogLeakAllowed);
        }
        if self.token_in_logs_allowed {
            blockers.push(Blocker::TokenLogLeakAllowed);
        }
        if self.raw_payload_in_logs_allowed {
            blockers.push(Blocker::RawPayloadLogLeakAllowed);
        }
        if self.stack_trace_in_reports_allowed {
            blockers.push(Blocker::StackTraceReportLeakAllowed);
        }

        IbkrPolicyVerdict::from_blockers(blockers)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrRedactionPolicyBlocker {
    PolicyMissing,
    RawPayloadHashNotRequired,
    RedactedSummaryHashNotRequired,
    AccountIdLogLeakAllowed,
    SecretLogLeakAllowed,
    LocalPathLogLeakAllowed,
    CookieLogLeakAllowed,
    TokenLogLeakAllowed,
    RawPayloadLogLeakAllowed,
    StackTraceReportLeakAllowed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrRateLimitScope {
    GlobalAndPerAction,
    GlobalOnly,
    None,
    Unknown,
}

impl Default for IbkrRateLimitScope {
    fn default() -> Self {
        Self::Unknown
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrRateLimitPolicyV1 {
    pub policy_present: bool,
    pub scope: IbkrRateLimitScope,
    pub min_request_spacing_ms: u64,
    pub max_in_flight_requests: u16,
    pub per_action_buckets_present: bool,
    pub pacing_violation_circuit_breaker_present: bool,
    pub read_snapshot_budget_present: bool,
    pub market_data_subscription_budget_present: bool,
    pub paper_order_write_budget_present: bool,
}

impl Default for IbkrRateLimitPolicyV1 {
    fn default() -> Self {
        Self {
            policy_present: false,
            scope: IbkrRateLimitScope::Unknown,
            min_request_spacing_ms: 0,
            max_in_flight_requests: 0,
            per_action_buckets_present: false,
            pacing_violation_circuit_breaker_present: false,
            read_snapshot_budget_present: false,
            market_data_subscription_budget_present: false,
            paper_order_write_budget_present: false,
        }
    }
}

impl IbkrRateLimitPolicyV1 {
    pub fn source_template() -> Self {
        Self {
            policy_present: true,
            scope: IbkrRateLimitScope::GlobalAndPerAction,
            min_request_spacing_ms: 100,
            max_in_flight_requests: 4,
            per_action_buckets_present: true,
            pacing_violation_circuit_breaker_present: true,
            read_snapshot_budget_present: true,
            market_data_subscription_budget_present: true,
            paper_order_write_budget_present: true,
        }
    }

    pub fn validate(&self) -> IbkrPolicyVerdict<IbkrRateLimitPolicyBlocker> {
        use IbkrRateLimitPolicyBlocker as Blocker;

        let mut blockers = Vec::new();
        if !self.policy_present {
            blockers.push(Blocker::PolicyMissing);
        }
        if self.scope != IbkrRateLimitScope::GlobalAndPerAction {
            blockers.push(Blocker::ScopeNotPerAction);
        }
        if self.min_request_spacing_ms == 0 {
            blockers.push(Blocker::RequestSpacingMissing);
        }
        if self.max_in_flight_requests == 0 {
            blockers.push(Blocker::ConcurrencyLimitMissing);
        }
        if !self.per_action_buckets_present {
            blockers.push(Blocker::PerActionBucketsMissing);
        }
        if !self.pacing_violation_circuit_breaker_present {
            blockers.push(Blocker::PacingCircuitBreakerMissing);
        }
        if !self.read_snapshot_budget_present {
            blockers.push(Blocker::ReadSnapshotBudgetMissing);
        }
        if !self.market_data_subscription_budget_present {
            blockers.push(Blocker::MarketDataSubscriptionBudgetMissing);
        }
        if !self.paper_order_write_budget_present {
            blockers.push(Blocker::PaperOrderWriteBudgetMissing);
        }

        IbkrPolicyVerdict::from_blockers(blockers)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrRateLimitPolicyBlocker {
    PolicyMissing,
    ScopeNotPerAction,
    RequestSpacingMissing,
    ConcurrencyLimitMissing,
    PerActionBucketsMissing,
    PacingCircuitBreakerMissing,
    ReadSnapshotBudgetMissing,
    MarketDataSubscriptionBudgetMissing,
    PaperOrderWriteBudgetMissing,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrAuditEventPolicyV1 {
    pub policy_present: bool,
    pub append_only_required: bool,
    pub asset_lane_required: bool,
    pub broker_required: bool,
    pub environment_required: bool,
    pub operation_required: bool,
    pub allowed_required: bool,
    pub denial_reason_required: bool,
    pub source_artifact_hash_required: bool,
    pub raw_artifact_hash_required: bool,
    pub redacted_summary_hash_required: bool,
    pub account_fingerprint_hash_only: bool,
    pub raw_payload_storage_allowed: bool,
}

impl Default for IbkrAuditEventPolicyV1 {
    fn default() -> Self {
        Self {
            policy_present: false,
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
            raw_payload_storage_allowed: false,
        }
    }
}

impl IbkrAuditEventPolicyV1 {
    pub fn source_template() -> Self {
        Self {
            policy_present: true,
            append_only_required: true,
            asset_lane_required: true,
            broker_required: true,
            environment_required: true,
            operation_required: true,
            allowed_required: true,
            denial_reason_required: true,
            source_artifact_hash_required: true,
            raw_artifact_hash_required: true,
            redacted_summary_hash_required: true,
            account_fingerprint_hash_only: true,
            raw_payload_storage_allowed: false,
        }
    }

    pub fn validate(&self) -> IbkrPolicyVerdict<IbkrAuditEventPolicyBlocker> {
        use IbkrAuditEventPolicyBlocker as Blocker;

        let mut blockers = Vec::new();
        if !self.policy_present {
            blockers.push(Blocker::PolicyMissing);
        }
        if !self.append_only_required {
            blockers.push(Blocker::AppendOnlyMissing);
        }
        if !self.asset_lane_required {
            blockers.push(Blocker::AssetLaneMissing);
        }
        if !self.broker_required {
            blockers.push(Blocker::BrokerMissing);
        }
        if !self.environment_required {
            blockers.push(Blocker::EnvironmentMissing);
        }
        if !self.operation_required {
            blockers.push(Blocker::OperationMissing);
        }
        if !self.allowed_required {
            blockers.push(Blocker::AllowedMissing);
        }
        if !self.denial_reason_required {
            blockers.push(Blocker::DenialReasonMissing);
        }
        if !self.source_artifact_hash_required {
            blockers.push(Blocker::SourceArtifactHashMissing);
        }
        if !self.raw_artifact_hash_required {
            blockers.push(Blocker::RawArtifactHashMissing);
        }
        if !self.redacted_summary_hash_required {
            blockers.push(Blocker::RedactedSummaryHashMissing);
        }
        if !self.account_fingerprint_hash_only {
            blockers.push(Blocker::AccountFingerprintHashOnlyMissing);
        }
        if self.raw_payload_storage_allowed {
            blockers.push(Blocker::RawPayloadStorageAllowed);
        }

        IbkrPolicyVerdict::from_blockers(blockers)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrAuditEventPolicyBlocker {
    PolicyMissing,
    AppendOnlyMissing,
    AssetLaneMissing,
    BrokerMissing,
    EnvironmentMissing,
    OperationMissing,
    AllowedMissing,
    DenialReasonMissing,
    SourceArtifactHashMissing,
    RawArtifactHashMissing,
    RedactedSummaryHashMissing,
    AccountFingerprintHashOnlyMissing,
    RawPayloadStorageAllowed,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPaperAttestationPolicyV1 {
    pub policy_present: bool,
    pub external_surface_gate_required: bool,
    pub session_attestation_required: bool,
    pub rust_lane_scoped_ipc_required: bool,
    pub scoped_authorization_required: bool,
    pub decision_lease_required: bool,
    pub guardian_required: bool,
    pub risk_config_hash_required: bool,
    pub instrument_identity_hash_required: bool,
    pub idempotency_key_required: bool,
    pub lifecycle_event_log_required: bool,
    pub reconciliation_required_before_terminal: bool,
    pub paper_environment_only: bool,
    pub live_account_fingerprint_denied: bool,
    pub margin_short_options_cfd_denied: bool,
    pub max_paper_notional_required: bool,
}

impl Default for IbkrPaperAttestationPolicyV1 {
    fn default() -> Self {
        Self {
            policy_present: false,
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
        }
    }
}

impl IbkrPaperAttestationPolicyV1 {
    pub fn source_template() -> Self {
        Self {
            policy_present: true,
            external_surface_gate_required: true,
            session_attestation_required: true,
            rust_lane_scoped_ipc_required: true,
            scoped_authorization_required: true,
            decision_lease_required: true,
            guardian_required: true,
            risk_config_hash_required: true,
            instrument_identity_hash_required: true,
            idempotency_key_required: true,
            lifecycle_event_log_required: true,
            reconciliation_required_before_terminal: true,
            paper_environment_only: true,
            live_account_fingerprint_denied: true,
            margin_short_options_cfd_denied: true,
            max_paper_notional_required: true,
        }
    }

    pub fn validate(&self) -> IbkrPolicyVerdict<IbkrPaperAttestationPolicyBlocker> {
        use IbkrPaperAttestationPolicyBlocker as Blocker;

        let mut blockers = Vec::new();
        if !self.policy_present {
            blockers.push(Blocker::PolicyMissing);
        }
        if !self.external_surface_gate_required {
            blockers.push(Blocker::ExternalSurfaceGateMissing);
        }
        if !self.session_attestation_required {
            blockers.push(Blocker::SessionAttestationMissing);
        }
        if !self.rust_lane_scoped_ipc_required {
            blockers.push(Blocker::RustLaneScopedIpcMissing);
        }
        if !self.scoped_authorization_required {
            blockers.push(Blocker::ScopedAuthorizationMissing);
        }
        if !self.decision_lease_required {
            blockers.push(Blocker::DecisionLeaseMissing);
        }
        if !self.guardian_required {
            blockers.push(Blocker::GuardianMissing);
        }
        if !self.risk_config_hash_required {
            blockers.push(Blocker::RiskConfigHashMissing);
        }
        if !self.instrument_identity_hash_required {
            blockers.push(Blocker::InstrumentIdentityHashMissing);
        }
        if !self.idempotency_key_required {
            blockers.push(Blocker::IdempotencyKeyMissing);
        }
        if !self.lifecycle_event_log_required {
            blockers.push(Blocker::LifecycleEventLogMissing);
        }
        if !self.reconciliation_required_before_terminal {
            blockers.push(Blocker::ReconciliationBeforeTerminalMissing);
        }
        if !self.paper_environment_only {
            blockers.push(Blocker::PaperEnvironmentOnlyMissing);
        }
        if !self.live_account_fingerprint_denied {
            blockers.push(Blocker::LiveAccountFingerprintNotDenied);
        }
        if !self.margin_short_options_cfd_denied {
            blockers.push(Blocker::MarginShortOptionsCfdNotDenied);
        }
        if !self.max_paper_notional_required {
            blockers.push(Blocker::MaxPaperNotionalMissing);
        }

        IbkrPolicyVerdict::from_blockers(blockers)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrPaperAttestationPolicyBlocker {
    PolicyMissing,
    ExternalSurfaceGateMissing,
    SessionAttestationMissing,
    RustLaneScopedIpcMissing,
    ScopedAuthorizationMissing,
    DecisionLeaseMissing,
    GuardianMissing,
    RiskConfigHashMissing,
    InstrumentIdentityHashMissing,
    IdempotencyKeyMissing,
    LifecycleEventLogMissing,
    ReconciliationBeforeTerminalMissing,
    PaperEnvironmentOnlyMissing,
    LiveAccountFingerprintNotDenied,
    MarginShortOptionsCfdNotDenied,
    MaxPaperNotionalMissing,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPythonWriteGuardPolicyV1 {
    pub policy_present: bool,
    pub python_broker_write_authority_denied: bool,
    pub python_can_read_display_import: bool,
    pub python_can_call_rust_lane_ipc: bool,
    pub python_ibkr_order_methods_denied: bool,
    pub python_live_secret_access_denied: bool,
    pub gui_cannot_override_authority: bool,
    pub bybit_paths_unmodified: bool,
}

impl Default for IbkrPythonWriteGuardPolicyV1 {
    fn default() -> Self {
        Self {
            policy_present: false,
            python_broker_write_authority_denied: false,
            python_can_read_display_import: false,
            python_can_call_rust_lane_ipc: false,
            python_ibkr_order_methods_denied: false,
            python_live_secret_access_denied: false,
            gui_cannot_override_authority: false,
            bybit_paths_unmodified: false,
        }
    }
}

impl IbkrPythonWriteGuardPolicyV1 {
    pub fn source_template() -> Self {
        Self {
            policy_present: true,
            python_broker_write_authority_denied: true,
            python_can_read_display_import: true,
            python_can_call_rust_lane_ipc: true,
            python_ibkr_order_methods_denied: true,
            python_live_secret_access_denied: true,
            gui_cannot_override_authority: true,
            bybit_paths_unmodified: true,
        }
    }

    pub fn validate(&self) -> IbkrPolicyVerdict<IbkrPythonWriteGuardPolicyBlocker> {
        use IbkrPythonWriteGuardPolicyBlocker as Blocker;

        let mut blockers = Vec::new();
        if !self.policy_present {
            blockers.push(Blocker::PolicyMissing);
        }
        if !self.python_broker_write_authority_denied {
            blockers.push(Blocker::PythonBrokerWriteAuthorityNotDenied);
        }
        if !self.python_can_read_display_import {
            blockers.push(Blocker::PythonReadDisplayImportMissing);
        }
        if !self.python_can_call_rust_lane_ipc {
            blockers.push(Blocker::PythonRustIpcBridgeMissing);
        }
        if !self.python_ibkr_order_methods_denied {
            blockers.push(Blocker::PythonIbkrOrderMethodsNotDenied);
        }
        if !self.python_live_secret_access_denied {
            blockers.push(Blocker::PythonLiveSecretAccessNotDenied);
        }
        if !self.gui_cannot_override_authority {
            blockers.push(Blocker::GuiAuthorityOverrideNotDenied);
        }
        if !self.bybit_paths_unmodified {
            blockers.push(Blocker::BybitPathMutationNotAccounted);
        }

        IbkrPolicyVerdict::from_blockers(blockers)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrPythonWriteGuardPolicyBlocker {
    PolicyMissing,
    PythonBrokerWriteAuthorityNotDenied,
    PythonReadDisplayImportMissing,
    PythonRustIpcBridgeMissing,
    PythonIbkrOrderMethodsNotDenied,
    PythonLiveSecretAccessNotDenied,
    GuiAuthorityOverrideNotDenied,
    BybitPathMutationNotAccounted,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPhase2GatePrerequisiteFlags {
    pub redaction_suite_passed: bool,
    pub rate_limit_policy_present: bool,
    pub audit_event_policy_present: bool,
    pub paper_attestation_contract_present: bool,
    pub python_no_write_guard_present: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPhase2PolicyBundleV1 {
    pub redaction: IbkrRedactionPolicyV1,
    pub rate_limit: IbkrRateLimitPolicyV1,
    pub audit_event: IbkrAuditEventPolicyV1,
    pub paper_attestation: IbkrPaperAttestationPolicyV1,
    pub python_write_guard: IbkrPythonWriteGuardPolicyV1,
}

impl Default for IbkrPhase2PolicyBundleV1 {
    fn default() -> Self {
        Self {
            redaction: IbkrRedactionPolicyV1::default(),
            rate_limit: IbkrRateLimitPolicyV1::default(),
            audit_event: IbkrAuditEventPolicyV1::default(),
            paper_attestation: IbkrPaperAttestationPolicyV1::default(),
            python_write_guard: IbkrPythonWriteGuardPolicyV1::default(),
        }
    }
}

impl IbkrPhase2PolicyBundleV1 {
    pub fn source_template() -> Self {
        Self {
            redaction: IbkrRedactionPolicyV1::source_template(),
            rate_limit: IbkrRateLimitPolicyV1::source_template(),
            audit_event: IbkrAuditEventPolicyV1::source_template(),
            paper_attestation: IbkrPaperAttestationPolicyV1::source_template(),
            python_write_guard: IbkrPythonWriteGuardPolicyV1::source_template(),
        }
    }

    pub fn gate_prerequisite_flags(&self) -> IbkrPhase2GatePrerequisiteFlags {
        IbkrPhase2GatePrerequisiteFlags {
            redaction_suite_passed: self.redaction.validate().accepted,
            rate_limit_policy_present: self.rate_limit.validate().accepted,
            audit_event_policy_present: self.audit_event.validate().accepted,
            paper_attestation_contract_present: self.paper_attestation.validate().accepted,
            python_no_write_guard_present: self.python_write_guard.validate().accepted,
        }
    }

    pub fn validate(&self) -> IbkrPolicyVerdict<IbkrPhase2PolicyBundleBlocker> {
        let flags = self.gate_prerequisite_flags();
        let mut blockers = Vec::new();
        if !flags.redaction_suite_passed {
            blockers.push(IbkrPhase2PolicyBundleBlocker::RedactionPolicyRejected);
        }
        if !flags.rate_limit_policy_present {
            blockers.push(IbkrPhase2PolicyBundleBlocker::RateLimitPolicyRejected);
        }
        if !flags.audit_event_policy_present {
            blockers.push(IbkrPhase2PolicyBundleBlocker::AuditEventPolicyRejected);
        }
        if !flags.paper_attestation_contract_present {
            blockers.push(IbkrPhase2PolicyBundleBlocker::PaperAttestationPolicyRejected);
        }
        if !flags.python_no_write_guard_present {
            blockers.push(IbkrPhase2PolicyBundleBlocker::PythonWriteGuardPolicyRejected);
        }

        IbkrPolicyVerdict::from_blockers(blockers)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrPhase2PolicyBundleBlocker {
    RedactionPolicyRejected,
    RateLimitPolicyRejected,
    AuditEventPolicyRejected,
    PaperAttestationPolicyRejected,
    PythonWriteGuardPolicyRejected,
}
