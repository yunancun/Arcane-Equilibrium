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

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BrokerLifecycleEventLogV1 {
    pub event_id: String,
    pub event_time_ms: u64,
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
    pub raw_artifact_hash: String,
    pub redacted_summary_hash: String,
}

impl Default for BrokerLifecycleEventLogV1 {
    fn default() -> Self {
        Self {
            event_id: String::new(),
            event_time_ms: 0,
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
            raw_artifact_hash: String::new(),
            redacted_summary_hash: String::new(),
        }
    }
}

impl BrokerLifecycleEventLogV1 {
    pub fn accepted_ack_fixture() -> Self {
        Self {
            event_id: "lifecycle_event_0001".to_string(),
            event_time_ms: 1_772_233_000_000,
            operation: BrokerOperation::PaperOrderSubmit,
            order_local_id: "local_order_0001".to_string(),
            idempotency_key: "idem_0001".to_string(),
            broker_order_id: "paper_broker_order_0001".to_string(),
            reconciliation_run_id: "reconcile_run_0001".to_string(),
            previous_state: IbkrPaperOrderLifecycleState::BrokerSubmitRequested,
            next_state: IbkrPaperOrderLifecycleState::BrokerAcknowledged,
            allowed: true,
            raw_artifact_hash: "a".repeat(64),
            redacted_summary_hash: "b".repeat(64),
            ..Self::default()
        }
    }

    pub fn validate(&self) -> IbkrPaperLifecycleEventVerdict {
        use IbkrPaperLifecycleEventBlocker as Blocker;

        let mut blockers = Vec::new();
        if self.event_id.trim().is_empty() {
            blockers.push(Blocker::EventIdMissing);
        }
        if self.event_time_ms == 0 {
            blockers.push(Blocker::EventTimeMissing);
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
        if !is_paper_lifecycle_operation(self.operation) {
            blockers.push(Blocker::OperationNotPaperLifecycle);
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
    EventIdMissing,
    EventTimeMissing,
    WrongAssetLane,
    WrongBroker,
    LiveEnvironmentDenied,
    OperationNotPaperLifecycle,
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
    RawArtifactHashInvalid,
    RedactedSummaryHashInvalid,
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
