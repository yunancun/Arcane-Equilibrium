//! IBKR paper order lifecycle and append-only event log contracts.
//!
//! This module validates source evidence shape only. It does not contact IBKR,
//! construct a connector, read secrets, or route paper orders.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{
    AssetLane, Broker, BrokerEnvironment, BrokerOperation, IbkrPaperOrderLifecycleState,
    StockEtfDenialReason,
};
use crate::stock_etf_paper_order_request::STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID;

pub const IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID: &str = "ibkr_paper_order_lifecycle_v1";
pub const BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID: &str = "broker_lifecycle_event_log_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BrokerLifecycleEventLogV1 {
    pub lifecycle_contract_id: String,
    pub event_log_contract_id: String,
    pub source_version: u32,
    pub event_id: String,
    pub event_sequence: u64,
    pub genesis_event: bool,
    pub event_time_ms: u64,
    pub previous_event_hash: String,
    pub event_hash: String,
    pub request_contract_id: String,
    pub request_envelope_hash: String,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub operation: BrokerOperation,
    pub order_local_id: String,
    pub idempotency_key: String,
    pub broker_order_id: String,
    pub execution_id: String,
    pub commission_report_id: String,
    pub reconciliation_run_id: String,
    pub previous_state: IbkrPaperOrderLifecycleState,
    pub next_state: IbkrPaperOrderLifecycleState,
    pub allowed: bool,
    pub denial_reason: Option<StockEtfDenialReason>,
    pub stale_state_policy: Option<IbkrPaperStaleStatePolicy>,
    pub raw_artifact_hash: String,
    pub redacted_summary_hash: String,
}

impl Default for BrokerLifecycleEventLogV1 {
    fn default() -> Self {
        Self {
            lifecycle_contract_id: String::new(),
            event_log_contract_id: String::new(),
            source_version: 0,
            event_id: String::new(),
            event_sequence: 0,
            genesis_event: false,
            event_time_ms: 0,
            previous_event_hash: String::new(),
            event_hash: String::new(),
            request_contract_id: String::new(),
            request_envelope_hash: String::new(),
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            operation: BrokerOperation::PaperOrderSubmit,
            order_local_id: String::new(),
            idempotency_key: String::new(),
            broker_order_id: String::new(),
            execution_id: String::new(),
            commission_report_id: String::new(),
            reconciliation_run_id: String::new(),
            previous_state: IbkrPaperOrderLifecycleState::LocalIntentCreated,
            next_state: IbkrPaperOrderLifecycleState::LocalIntentCreated,
            allowed: false,
            denial_reason: None,
            stale_state_policy: None,
            raw_artifact_hash: String::new(),
            redacted_summary_hash: String::new(),
        }
    }
}

impl BrokerLifecycleEventLogV1 {
    pub fn accepted_ack_fixture() -> Self {
        Self {
            lifecycle_contract_id: IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID.to_string(),
            event_log_contract_id: BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID.to_string(),
            source_version: 1,
            event_id: "lifecycle_event_0001".to_string(),
            event_sequence: 2,
            genesis_event: false,
            event_time_ms: 1_772_233_000_000,
            previous_event_hash: "c".repeat(64),
            event_hash: "d".repeat(64),
            request_contract_id: STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID.to_string(),
            request_envelope_hash: "e".repeat(64),
            operation: BrokerOperation::PaperOrderSubmit,
            order_local_id: "local_order_0001".to_string(),
            idempotency_key: "idem_0001".to_string(),
            broker_order_id: "paper_broker_order_0001".to_string(),
            reconciliation_run_id: "reconcile_run_0001".to_string(),
            previous_state: IbkrPaperOrderLifecycleState::BrokerSubmitRequested,
            next_state: IbkrPaperOrderLifecycleState::BrokerAcknowledged,
            allowed: true,
            stale_state_policy: Some(
                IbkrPaperStaleStatePolicy::ReconcileByBrokerOrderIdAndIdempotencyKey,
            ),
            raw_artifact_hash: "a".repeat(64),
            redacted_summary_hash: "b".repeat(64),
            ..Self::default()
        }
    }

    pub fn validate(&self) -> IbkrPaperLifecycleEventVerdict {
        use IbkrPaperLifecycleEventBlocker as Blocker;

        let mut blockers = Vec::new();
        if self.lifecycle_contract_id != IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID {
            blockers.push(Blocker::LifecycleContractIdMismatch);
        }
        if self.event_log_contract_id != BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID {
            blockers.push(Blocker::EventLogContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.event_id.trim().is_empty() {
            blockers.push(Blocker::EventIdMissing);
        }
        if self.event_sequence == 0 {
            blockers.push(Blocker::EventSequenceMissing);
        }
        if self.genesis_event {
            if self.event_sequence != 1 {
                blockers.push(Blocker::GenesisSequenceInvalid);
            }
            if !self.previous_event_hash.trim().is_empty() {
                blockers.push(Blocker::GenesisPreviousEventHashPresent);
            }
        } else if !is_sha256_hex(&self.previous_event_hash) {
            blockers.push(Blocker::PreviousEventHashInvalid);
        }
        if self.event_time_ms == 0 {
            blockers.push(Blocker::EventTimeMissing);
        }
        if !is_sha256_hex(&self.event_hash) {
            blockers.push(Blocker::EventHashInvalid);
        }
        if self.request_contract_id != STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID {
            blockers.push(Blocker::RequestContractIdMismatch);
        }
        if !is_sha256_hex(&self.request_envelope_hash) {
            blockers.push(Blocker::RequestEnvelopeHashInvalid);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if self.environment == BrokerEnvironment::LiveReservedDenied {
            blockers.push(Blocker::LiveEnvironmentDenied);
        }
        if self.environment != BrokerEnvironment::Paper {
            blockers.push(Blocker::PaperEnvironmentRequired);
        }
        if !is_paper_lifecycle_operation(self.operation) {
            blockers.push(Blocker::OperationNotPaperLifecycle);
        }
        if !is_operation_transition_allowed(self.operation, self.previous_state, self.next_state) {
            blockers.push(Blocker::OperationTransitionMismatch);
        }
        if self.order_local_id.trim().is_empty() {
            blockers.push(Blocker::LocalOrderIdMissing);
        }
        if self.idempotency_key.trim().is_empty() {
            blockers.push(Blocker::IdempotencyKeyMissing);
        }
        if self.reconciliation_run_id.trim().is_empty() {
            blockers.push(Blocker::ReconciliationRunIdMissing);
        }
        if requires_broker_order_id(self.previous_state, self.next_state)
            && self.broker_order_id.trim().is_empty()
        {
            blockers.push(Blocker::BrokerOrderIdMissing);
        }
        if requires_fill_ids(self.next_state) {
            if self.execution_id.trim().is_empty() {
                blockers.push(Blocker::ExecutionIdMissing);
            }
            if self.commission_report_id.trim().is_empty() {
                blockers.push(Blocker::CommissionReportIdMissing);
            }
        }
        if !is_transition_allowed(self.previous_state, self.next_state) {
            blockers.push(Blocker::InvalidStateTransition);
        }
        if self.previous_state == IbkrPaperOrderLifecycleState::StateUnknown
            && self.next_state != IbkrPaperOrderLifecycleState::ManualReviewRequired
            && !self.next_state.is_terminal()
        {
            blockers.push(Blocker::StateUnknownRecoveryInvalid);
        }
        if self.previous_state == IbkrPaperOrderLifecycleState::StateUnknown
            && self.next_state.is_terminal()
            && !is_sha256_hex(&self.raw_artifact_hash)
        {
            blockers.push(Blocker::StateUnknownTerminalEvidenceMissing);
        }
        if self.allowed && self.denial_reason.is_some() {
            blockers.push(Blocker::DenialReasonPresentOnAllowedEvent);
        }
        if !self.allowed && self.denial_reason.is_none() {
            blockers.push(Blocker::DenialReasonMissingOnDeniedEvent);
        }
        if !self.allowed
            && self.denial_reason.is_some()
            && !matches!(
                self.next_state,
                IbkrPaperOrderLifecycleState::Rejected
                    | IbkrPaperOrderLifecycleState::ManualReviewRequired
                    | IbkrPaperOrderLifecycleState::StateUnknown
            )
        {
            blockers.push(Blocker::DeniedEventAdvancesActiveState);
        }
        match self.stale_state_policy {
            Some(policy) => {
                if !stale_state_policy_matches_transition(
                    policy,
                    self.previous_state,
                    self.next_state,
                ) {
                    blockers.push(Blocker::StaleStatePolicyMismatch);
                }
            }
            None => blockers.push(Blocker::StaleStatePolicyMissing),
        }
        if !is_sha256_hex(&self.raw_artifact_hash) {
            blockers.push(Blocker::RawArtifactHashInvalid);
        }
        if !is_sha256_hex(&self.redacted_summary_hash) {
            blockers.push(Blocker::RedactedSummaryHashInvalid);
        }

        IbkrPaperLifecycleEventVerdict {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPaperLifecycleEventVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrPaperLifecycleEventBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrPaperLifecycleEventBlocker {
    LifecycleContractIdMismatch,
    EventLogContractIdMismatch,
    SourceVersionMismatch,
    EventIdMissing,
    EventSequenceMissing,
    GenesisSequenceInvalid,
    GenesisPreviousEventHashPresent,
    PreviousEventHashInvalid,
    EventTimeMissing,
    EventHashInvalid,
    RequestContractIdMismatch,
    RequestEnvelopeHashInvalid,
    WrongAssetLane,
    WrongBroker,
    PaperEnvironmentRequired,
    LiveEnvironmentDenied,
    OperationNotPaperLifecycle,
    OperationTransitionMismatch,
    LocalOrderIdMissing,
    IdempotencyKeyMissing,
    ReconciliationRunIdMissing,
    BrokerOrderIdMissing,
    ExecutionIdMissing,
    CommissionReportIdMissing,
    InvalidStateTransition,
    StateUnknownRecoveryInvalid,
    StateUnknownTerminalEvidenceMissing,
    DenialReasonPresentOnAllowedEvent,
    DenialReasonMissingOnDeniedEvent,
    DeniedEventAdvancesActiveState,
    StaleStatePolicyMissing,
    StaleStatePolicyMismatch,
    RawArtifactHashInvalid,
    RedactedSummaryHashInvalid,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrPaperStaleStatePolicy {
    ManualReviewOnUnknown,
    ReconcileByBrokerOrderIdAndIdempotencyKey,
    PreserveTerminalWithEvidence,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPaperRestartRecoveryInputV1 {
    pub last_local_state: IbkrPaperOrderLifecycleState,
    pub broker_state_known: bool,
    pub broker_order_id: String,
    pub idempotency_key: String,
    pub terminal_evidence_hash: String,
}

impl Default for IbkrPaperRestartRecoveryInputV1 {
    fn default() -> Self {
        Self {
            last_local_state: IbkrPaperOrderLifecycleState::StateUnknown,
            broker_state_known: false,
            broker_order_id: String::new(),
            idempotency_key: String::new(),
            terminal_evidence_hash: String::new(),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrPaperRestartRecoveryAction {
    ReconcileByBrokerOrderIdAndIdempotencyKey,
    MarkStateUnknown,
    PreserveTerminalState,
}

pub fn classify_ibkr_paper_restart_recovery(
    input: &IbkrPaperRestartRecoveryInputV1,
) -> IbkrPaperRestartRecoveryAction {
    if input.last_local_state.is_terminal() && is_sha256_hex(&input.terminal_evidence_hash) {
        return IbkrPaperRestartRecoveryAction::PreserveTerminalState;
    }
    if input.broker_state_known
        && !input.broker_order_id.trim().is_empty()
        && !input.idempotency_key.trim().is_empty()
    {
        return IbkrPaperRestartRecoveryAction::ReconcileByBrokerOrderIdAndIdempotencyKey;
    }
    IbkrPaperRestartRecoveryAction::MarkStateUnknown
}

pub const fn is_transition_allowed(
    previous: IbkrPaperOrderLifecycleState,
    next: IbkrPaperOrderLifecycleState,
) -> bool {
    use IbkrPaperOrderLifecycleState as State;

    match previous {
        State::LocalIntentCreated => matches!(
            next,
            State::RustAuthorityAccepted | State::Rejected | State::ManualReviewRequired
        ),
        State::RustAuthorityAccepted => matches!(
            next,
            State::BrokerSubmitRequested | State::Rejected | State::ManualReviewRequired
        ),
        State::BrokerSubmitRequested => matches!(
            next,
            State::BrokerAcknowledged
                | State::Rejected
                | State::StateUnknown
                | State::ManualReviewRequired
        ),
        State::BrokerAcknowledged => matches!(
            next,
            State::PartiallyFilled
                | State::Filled
                | State::CancelRequested
                | State::ReplaceRequested
                | State::Inactive
                | State::StateUnknown
        ),
        State::PartiallyFilled => matches!(
            next,
            State::PartiallyFilled | State::Filled | State::CancelRequested | State::StateUnknown
        ),
        State::CancelRequested => matches!(
            next,
            State::Cancelled | State::StateUnknown | State::ManualReviewRequired
        ),
        State::ReplaceRequested => matches!(
            next,
            State::Replaced | State::Rejected | State::StateUnknown | State::ManualReviewRequired
        ),
        State::Replaced => matches!(
            next,
            State::BrokerAcknowledged
                | State::PartiallyFilled
                | State::Filled
                | State::CancelRequested
                | State::StateUnknown
        ),
        State::StateUnknown => {
            matches!(
                next,
                State::ManualReviewRequired
                    | State::Filled
                    | State::Cancelled
                    | State::Rejected
                    | State::Inactive
            )
        }
        State::Filled
        | State::Cancelled
        | State::Rejected
        | State::Inactive
        | State::ManualReviewRequired => false,
    }
}

pub const fn is_operation_transition_allowed(
    operation: BrokerOperation,
    previous: IbkrPaperOrderLifecycleState,
    next: IbkrPaperOrderLifecycleState,
) -> bool {
    use BrokerOperation as Op;
    use IbkrPaperOrderLifecycleState as State;

    match operation {
        Op::PaperOrderSubmit => matches!(
            (previous, next),
            (
                State::LocalIntentCreated,
                State::RustAuthorityAccepted | State::Rejected | State::ManualReviewRequired
            ) | (
                State::RustAuthorityAccepted,
                State::BrokerSubmitRequested | State::Rejected | State::ManualReviewRequired
            ) | (
                State::BrokerSubmitRequested,
                State::BrokerAcknowledged
                    | State::Rejected
                    | State::StateUnknown
                    | State::ManualReviewRequired
            ) | (State::StateUnknown, State::ManualReviewRequired)
        ),
        Op::PaperOrderCancel => matches!(
            (previous, next),
            (
                State::BrokerAcknowledged | State::PartiallyFilled | State::Replaced,
                State::CancelRequested | State::StateUnknown | State::ManualReviewRequired
            ) | (
                State::CancelRequested,
                State::Cancelled | State::StateUnknown | State::ManualReviewRequired
            ) | (State::StateUnknown, State::ManualReviewRequired)
        ),
        Op::PaperOrderReplace => matches!(
            (previous, next),
            (
                State::BrokerAcknowledged | State::Replaced,
                State::ReplaceRequested | State::StateUnknown | State::ManualReviewRequired
            ) | (
                State::ReplaceRequested,
                State::Replaced
                    | State::Rejected
                    | State::StateUnknown
                    | State::ManualReviewRequired
            ) | (State::Replaced, State::BrokerAcknowledged)
                | (State::StateUnknown, State::ManualReviewRequired)
        ),
        Op::PaperOrderFillImport => matches!(
            (previous, next),
            (
                State::BrokerAcknowledged | State::PartiallyFilled | State::Replaced,
                State::PartiallyFilled | State::Filled | State::Inactive | State::StateUnknown
            ) | (
                State::StateUnknown,
                State::Filled
                    | State::Cancelled
                    | State::Rejected
                    | State::Inactive
                    | State::ManualReviewRequired
            )
        ),
        _ => false,
    }
}

const fn stale_state_policy_matches_transition(
    policy: IbkrPaperStaleStatePolicy,
    previous: IbkrPaperOrderLifecycleState,
    next: IbkrPaperOrderLifecycleState,
) -> bool {
    use IbkrPaperOrderLifecycleState as State;
    use IbkrPaperStaleStatePolicy as Policy;

    if matches!(previous, State::StateUnknown) {
        return match next {
            State::ManualReviewRequired => matches!(policy, Policy::ManualReviewOnUnknown),
            State::Filled | State::Cancelled | State::Rejected | State::Inactive => {
                matches!(policy, Policy::ReconcileByBrokerOrderIdAndIdempotencyKey)
            }
            _ => false,
        };
    }

    if previous.is_terminal() {
        return matches!(policy, Policy::PreserveTerminalWithEvidence);
    }

    if matches!(policy, Policy::PreserveTerminalWithEvidence) {
        return false;
    }

    true
}

const fn is_paper_lifecycle_operation(operation: BrokerOperation) -> bool {
    matches!(
        operation,
        BrokerOperation::PaperOrderSubmit
            | BrokerOperation::PaperOrderCancel
            | BrokerOperation::PaperOrderReplace
            | BrokerOperation::PaperOrderFillImport
    )
}

const fn requires_broker_order_id(
    previous: IbkrPaperOrderLifecycleState,
    next: IbkrPaperOrderLifecycleState,
) -> bool {
    use IbkrPaperOrderLifecycleState as State;

    matches!(
        previous,
        State::BrokerAcknowledged
            | State::PartiallyFilled
            | State::CancelRequested
            | State::ReplaceRequested
            | State::Replaced
            | State::StateUnknown
    ) || matches!(
        next,
        State::BrokerAcknowledged
            | State::PartiallyFilled
            | State::Filled
            | State::CancelRequested
            | State::Cancelled
            | State::ReplaceRequested
            | State::Replaced
            | State::Inactive
    )
}

const fn requires_fill_ids(next: IbkrPaperOrderLifecycleState) -> bool {
    matches!(
        next,
        IbkrPaperOrderLifecycleState::PartiallyFilled | IbkrPaperOrderLifecycleState::Filled
    )
}
