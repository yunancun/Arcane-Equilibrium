//! OMS State Machine — 11-state order lifecycle.
//! OMS 狀態機 — 11 態訂單生命週期。
//!
//! CREATED→PENDING→APPROVED→SUBMITTED→WORKING→PARTIALLY_FILLED→FILLED→
//! RECONCILING→COMPLETED | CANCELED | REJECTED
//!
//! Key invariant: cannot skip authorization, cannot skip reconciliation.
//! 關鍵不變量：不可跳過授權，不可跳過對賬。

use super::{SmError, TransitionRecord};
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// States / 狀態
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OrderState {
    Created,
    Pending,
    Approved,
    Submitted,
    Working,
    PartiallyFilled,
    Filled,
    Reconciling,
    Completed,
    Canceled,
    Rejected,
}

impl OrderState {
    pub fn is_terminal(self) -> bool {
        matches!(self, Self::Completed | Self::Canceled | Self::Rejected)
    }

    pub fn is_active(self) -> bool {
        matches!(
            self,
            Self::Pending | Self::Approved | Self::Submitted
                | Self::Working | Self::PartiallyFilled | Self::Reconciling
        )
    }

    pub fn is_pre_execution(self) -> bool {
        matches!(self, Self::Created | Self::Pending | Self::Approved)
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Created => "CREATED",
            Self::Pending => "PENDING",
            Self::Approved => "APPROVED",
            Self::Submitted => "SUBMITTED",
            Self::Working => "WORKING",
            Self::PartiallyFilled => "PARTIALLY_FILLED",
            Self::Filled => "FILLED",
            Self::Reconciling => "RECONCILING",
            Self::Completed => "COMPLETED",
            Self::Canceled => "CANCELED",
            Self::Rejected => "REJECTED",
        }
    }
}

impl std::fmt::Display for OrderState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Events / 事件
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OrderEvent {
    SubmitForApproval,
    Approve,
    RejectAuthorization,
    SendToVenue,
    Acknowledge,
    RejectByVenue,
    PartialFill,
    Fill,
    Cancel,
    BeginReconciliation,
    ReconciliationPass,
    ReconciliationFail,
}

impl OrderEvent {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::SubmitForApproval => "submit_for_approval",
            Self::Approve => "approve",
            Self::RejectAuthorization => "reject_authorization",
            Self::SendToVenue => "send_to_venue",
            Self::Acknowledge => "acknowledge",
            Self::RejectByVenue => "reject_by_venue",
            Self::PartialFill => "partial_fill",
            Self::Fill => "fill",
            Self::Cancel => "cancel",
            Self::BeginReconciliation => "begin_reconciliation",
            Self::ReconciliationPass => "reconciliation_pass",
            Self::ReconciliationFail => "reconciliation_fail",
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Initiators / 發起者
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum OrderInitiator {
    Operator,
    AiAgent,
    System,
    ExecutionVenue,
    AuthorizationSm,
    ReconciliationEngine,
    RiskGovernor,
}

impl OrderInitiator {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Operator => "Operator",
            Self::AiAgent => "AIAgent",
            Self::System => "System",
            Self::ExecutionVenue => "ExecutionVenue",
            Self::AuthorizationSm => "AuthorizationSM",
            Self::ReconciliationEngine => "ReconciliationEngine",
            Self::RiskGovernor => "RiskGovernor",
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Transition rules / 遷移規則
// ═══════════════════════════════════════════════════════════════════════════════

struct TransitionRule {
    event: OrderEvent,
    allowed: &'static [OrderInitiator],
}

fn is_forbidden(from: OrderState, to: OrderState) -> bool {
    use OrderState::*;
    matches!(
        (from, to),
        // Cannot skip authorization
        (Created, Submitted) | (Created, Working) | (Created, Approved) |
        // Cannot skip reconciliation
        (Filled, Completed) |
        // Terminal cannot exit
        (Completed, Created) | (Completed, Reconciling) |
        (Canceled, Created) | (Canceled, Pending) |
        (Rejected, Created) | (Rejected, Pending) |
        // Cannot go backwards in execution
        (Working, Submitted) | (Filled, Working)
    )
}

fn lookup_rule(from: OrderState, to: OrderState) -> Option<TransitionRule> {
    use OrderInitiator::*;
    use OrderState::*;

    const AGENTS: &[OrderInitiator] = &[AiAgent, Operator, System];
    const AUTH: &[OrderInitiator] = &[AuthorizationSm, Operator];
    const AUTH_RISK: &[OrderInitiator] = &[AuthorizationSm, Operator, RiskGovernor];
    const EXEC_SYS: &[OrderInitiator] = &[System, Operator];
    const VENUE: &[OrderInitiator] = &[ExecutionVenue, System];
    const CANCEL_ALL: &[OrderInitiator] = &[Operator, AiAgent, System, RiskGovernor];
    const RECON: &[OrderInitiator] = &[System, ReconciliationEngine];
    const RECON_OP: &[OrderInitiator] = &[ReconciliationEngine, System, Operator];

    match (from, to) {
        // Pre-execution
        (Created, Pending) => Some(TransitionRule { event: OrderEvent::SubmitForApproval, allowed: AGENTS }),
        (Pending, Approved) => Some(TransitionRule { event: OrderEvent::Approve, allowed: AUTH }),
        (Pending, Rejected) => Some(TransitionRule { event: OrderEvent::RejectAuthorization, allowed: AUTH_RISK }),
        (Pending, Canceled) => Some(TransitionRule { event: OrderEvent::Cancel, allowed: AGENTS }),
        // Execution
        (Approved, Submitted) => Some(TransitionRule { event: OrderEvent::SendToVenue, allowed: EXEC_SYS }),
        (Approved, Canceled) => Some(TransitionRule { event: OrderEvent::Cancel, allowed: CANCEL_ALL }),
        (Submitted, Working) => Some(TransitionRule { event: OrderEvent::Acknowledge, allowed: VENUE }),
        (Submitted, Rejected) => Some(TransitionRule { event: OrderEvent::RejectByVenue, allowed: VENUE }),
        (Working, PartiallyFilled) => Some(TransitionRule { event: OrderEvent::PartialFill, allowed: VENUE }),
        (Working, Filled) => Some(TransitionRule { event: OrderEvent::Fill, allowed: VENUE }),
        (Working, Canceled) => Some(TransitionRule { event: OrderEvent::Cancel, allowed: CANCEL_ALL }),
        (PartiallyFilled, Filled) => Some(TransitionRule { event: OrderEvent::Fill, allowed: VENUE }),
        (PartiallyFilled, Canceled) => Some(TransitionRule { event: OrderEvent::Cancel, allowed: CANCEL_ALL }),
        // Post-execution
        (Filled, Reconciling) => Some(TransitionRule { event: OrderEvent::BeginReconciliation, allowed: RECON }),
        (Reconciling, Completed) => Some(TransitionRule { event: OrderEvent::ReconciliationPass, allowed: RECON }),
        (Reconciling, Rejected) => Some(TransitionRule { event: OrderEvent::ReconciliationFail, allowed: RECON_OP }),
        _ => None,
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Order Object / 訂單對象
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OmsOrder {
    pub order_id: String,
    pub symbol: String,
    pub side: String,
    pub order_type: String,
    pub qty: f64,
    pub price: Option<f64>,
    pub state: OrderState,
    pub created_at_ms: u64,
    pub updated_at_ms: u64,
    pub created_by: String,
    pub approved_by: String,
    pub reconciliation_result: String,
    pub transitions: Vec<TransitionRecord>,
}

impl OmsOrder {
    pub fn new(symbol: &str, side: &str, qty: f64, order_type: &str, price: Option<f64>, created_by: &str) -> Self {
        let now = super::now_ms();
        Self {
            order_id: format!("oms:{:012x}", rand::random::<u64>() & 0xFFFF_FFFF_FFFF),
            symbol: symbol.to_string(),
            side: side.to_string(),
            order_type: order_type.to_string(),
            qty,
            price,
            state: OrderState::Created,
            created_at_ms: now,
            updated_at_ms: now,
            created_by: created_by.to_string(),
            approved_by: String::new(),
            reconciliation_result: String::new(),
            transitions: Vec::new(),
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// State Machine / 狀態機
// ═══════════════════════════════════════════════════════════════════════════════

pub struct OmsStateMachine {
    orders: Vec<OmsOrder>,
}

impl OmsStateMachine {
    pub fn new() -> Self {
        Self { orders: Vec::new() }
    }

    pub fn create_order(
        &mut self, symbol: &str, side: &str, qty: f64,
        order_type: &str, price: Option<f64>, created_by: &str,
    ) -> usize {
        let order = OmsOrder::new(symbol, side, qty, order_type, price, created_by);
        self.orders.push(order);
        self.orders.len() - 1
    }

    pub fn transition(
        &mut self, idx: usize, target: OrderState, initiator: OrderInitiator, reason: &str,
    ) -> Result<(), SmError> {
        let order = self.orders.get_mut(idx)
            .ok_or_else(|| SmError::NotFound(format!("order index {idx}")))?;
        let from = order.state;

        if from.is_terminal() {
            return Err(SmError::TerminalState(from.to_string()));
        }
        if is_forbidden(from, target) {
            return Err(SmError::Forbidden { from: from.to_string(), to: target.to_string() });
        }
        let rule = lookup_rule(from, target)
            .ok_or_else(|| SmError::InvalidTransition { from: from.to_string(), to: target.to_string() })?;
        if !rule.allowed.contains(&initiator) {
            return Err(SmError::InitiatorNotAllowed {
                initiator: initiator.as_str().to_string(),
                from: from.to_string(), to: target.to_string(),
            });
        }

        let record = TransitionRecord::new(
            from.as_str(), target.as_str(), rule.event.as_str(),
            initiator.as_str(), vec![reason.to_string()], false, None, order.transitions.len() as u32,
        );
        order.state = target;
        order.updated_at_ms = super::now_ms();
        order.transitions.push(record);

        // Track metadata
        if target == OrderState::Approved { order.approved_by = initiator.as_str().to_string(); }
        if target == OrderState::Completed { order.reconciliation_result = "PASS".to_string(); }
        if target == OrderState::Rejected && from == OrderState::Reconciling {
            order.reconciliation_result = "FAIL".to_string();
        }
        Ok(())
    }

    // ── Convenience / 便捷 ──

    pub fn submit_for_approval(&mut self, idx: usize, initiator: OrderInitiator) -> Result<(), SmError> {
        self.transition(idx, OrderState::Pending, initiator, "submit_for_approval")
    }

    pub fn approve(&mut self, idx: usize, initiator: OrderInitiator) -> Result<(), SmError> {
        self.transition(idx, OrderState::Approved, initiator, "approved")
    }

    pub fn reject(&mut self, idx: usize, initiator: OrderInitiator, reason: &str) -> Result<(), SmError> {
        self.transition(idx, OrderState::Rejected, initiator, reason)
    }

    pub fn send_to_venue(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, OrderState::Submitted, OrderInitiator::System, "sent_to_venue")
    }

    pub fn acknowledge(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, OrderState::Working, OrderInitiator::ExecutionVenue, "acknowledged")
    }

    pub fn partial_fill(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, OrderState::PartiallyFilled, OrderInitiator::ExecutionVenue, "partial_fill")
    }

    pub fn fill(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, OrderState::Filled, OrderInitiator::ExecutionVenue, "filled")
    }

    pub fn cancel(&mut self, idx: usize, initiator: OrderInitiator, reason: &str) -> Result<(), SmError> {
        self.transition(idx, OrderState::Canceled, initiator, reason)
    }

    pub fn begin_reconciliation(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, OrderState::Reconciling, OrderInitiator::ReconciliationEngine, "begin_recon")
    }

    pub fn reconciliation_pass(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, OrderState::Completed, OrderInitiator::ReconciliationEngine, "recon_pass")
    }

    pub fn reconciliation_fail(&mut self, idx: usize, reason: &str) -> Result<(), SmError> {
        self.transition(idx, OrderState::Rejected, OrderInitiator::ReconciliationEngine, reason)
    }

    // ── Query / 查詢 ──

    pub fn get(&self, idx: usize) -> Option<&OmsOrder> {
        self.orders.get(idx)
    }

    pub fn get_by_state(&self, state: OrderState) -> Vec<usize> {
        self.orders.iter().enumerate()
            .filter(|(_, o)| o.state == state)
            .map(|(i, _)| i).collect()
    }

    pub fn get_active(&self) -> Vec<usize> {
        self.orders.iter().enumerate()
            .filter(|(_, o)| o.state.is_active())
            .map(|(i, _)| i).collect()
    }

    pub fn len(&self) -> usize { self.orders.len() }
    pub fn is_empty(&self) -> bool { self.orders.is_empty() }
}

impl Default for OmsStateMachine {
    fn default() -> Self { Self::new() }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn make_filled_order() -> (OmsStateMachine, usize) {
        let mut sm = OmsStateMachine::new();
        let idx = sm.create_order("BTCUSDT", "Buy", 0.01, "limit", Some(50000.0), "agent");
        sm.submit_for_approval(idx, OrderInitiator::AiAgent).unwrap();
        sm.approve(idx, OrderInitiator::AuthorizationSm).unwrap();
        sm.send_to_venue(idx).unwrap();
        sm.acknowledge(idx).unwrap();
        sm.fill(idx).unwrap();
        (sm, idx)
    }

    #[test]
    fn test_happy_path_full_lifecycle() {
        let (mut sm, idx) = make_filled_order();
        sm.begin_reconciliation(idx).unwrap();
        sm.reconciliation_pass(idx).unwrap();
        assert_eq!(sm.get(idx).unwrap().state, OrderState::Completed);
        assert_eq!(sm.get(idx).unwrap().reconciliation_result, "PASS");
    }

    #[test]
    fn test_reconciliation_fail() {
        let (mut sm, idx) = make_filled_order();
        sm.begin_reconciliation(idx).unwrap();
        sm.reconciliation_fail(idx, "mismatch").unwrap();
        assert_eq!(sm.get(idx).unwrap().state, OrderState::Rejected);
        assert_eq!(sm.get(idx).unwrap().reconciliation_result, "FAIL");
    }

    #[test]
    fn test_cannot_skip_authorization() {
        let mut sm = OmsStateMachine::new();
        let idx = sm.create_order("BTCUSDT", "Buy", 0.01, "limit", None, "agent");
        let err = sm.transition(idx, OrderState::Submitted, OrderInitiator::System, "").unwrap_err();
        assert!(matches!(err, SmError::Forbidden { .. }));
    }

    #[test]
    fn test_cannot_skip_reconciliation() {
        let (mut sm, idx) = make_filled_order();
        let err = sm.transition(idx, OrderState::Completed, OrderInitiator::System, "").unwrap_err();
        assert!(matches!(err, SmError::Forbidden { .. }));
    }

    #[test]
    fn test_terminal_cannot_transition() {
        let (mut sm, idx) = make_filled_order();
        sm.begin_reconciliation(idx).unwrap();
        sm.reconciliation_pass(idx).unwrap();
        let err = sm.submit_for_approval(idx, OrderInitiator::AiAgent).unwrap_err();
        assert!(matches!(err, SmError::TerminalState(_)));
    }

    #[test]
    fn test_cancel_from_various_states() {
        // Cancel from Pending
        let mut sm = OmsStateMachine::new();
        let idx = sm.create_order("ETH", "Sell", 1.0, "market", None, "op");
        sm.submit_for_approval(idx, OrderInitiator::Operator).unwrap();
        sm.cancel(idx, OrderInitiator::Operator, "changed mind").unwrap();
        assert_eq!(sm.get(idx).unwrap().state, OrderState::Canceled);

        // Cancel from Working
        let idx2 = sm.create_order("ETH", "Buy", 0.5, "limit", Some(3000.0), "agent");
        sm.submit_for_approval(idx2, OrderInitiator::AiAgent).unwrap();
        sm.approve(idx2, OrderInitiator::AuthorizationSm).unwrap();
        sm.send_to_venue(idx2).unwrap();
        sm.acknowledge(idx2).unwrap();
        sm.cancel(idx2, OrderInitiator::RiskGovernor, "risk").unwrap();
        assert_eq!(sm.get(idx2).unwrap().state, OrderState::Canceled);
    }

    #[test]
    fn test_partial_fill_then_fill() {
        let mut sm = OmsStateMachine::new();
        let idx = sm.create_order("BTC", "Buy", 1.0, "limit", Some(50000.0), "ag");
        sm.submit_for_approval(idx, OrderInitiator::AiAgent).unwrap();
        sm.approve(idx, OrderInitiator::AuthorizationSm).unwrap();
        sm.send_to_venue(idx).unwrap();
        sm.acknowledge(idx).unwrap();
        sm.partial_fill(idx).unwrap();
        assert_eq!(sm.get(idx).unwrap().state, OrderState::PartiallyFilled);
        sm.fill(idx).unwrap();
        assert_eq!(sm.get(idx).unwrap().state, OrderState::Filled);
    }

    #[test]
    fn test_initiator_check() {
        let mut sm = OmsStateMachine::new();
        let idx = sm.create_order("BTC", "Buy", 0.1, "market", None, "agent");
        sm.submit_for_approval(idx, OrderInitiator::AiAgent).unwrap();
        // AiAgent cannot approve (only AuthorizationSm or Operator)
        let err = sm.approve(idx, OrderInitiator::AiAgent).unwrap_err();
        assert!(matches!(err, SmError::InitiatorNotAllowed { .. }));
    }

    #[test]
    fn test_cannot_go_backwards() {
        let mut sm = OmsStateMachine::new();
        let idx = sm.create_order("BTC", "Buy", 0.1, "limit", Some(50000.0), "agent");
        sm.submit_for_approval(idx, OrderInitiator::AiAgent).unwrap();
        sm.approve(idx, OrderInitiator::AuthorizationSm).unwrap();
        sm.send_to_venue(idx).unwrap();
        sm.acknowledge(idx).unwrap();
        // Working → Submitted is forbidden
        let err = sm.transition(idx, OrderState::Submitted, OrderInitiator::System, "").unwrap_err();
        assert!(matches!(err, SmError::Forbidden { .. }));
    }

    #[test]
    fn test_get_by_state_and_active() {
        let mut sm = OmsStateMachine::new();
        let i0 = sm.create_order("BTC", "Buy", 0.1, "market", None, "a");
        let i1 = sm.create_order("ETH", "Sell", 1.0, "market", None, "a");
        sm.submit_for_approval(i0, OrderInitiator::AiAgent).unwrap();
        assert_eq!(sm.get_by_state(OrderState::Pending), vec![i0]);
        assert_eq!(sm.get_by_state(OrderState::Created), vec![i1]);
        assert_eq!(sm.get_active(), vec![i0]); // i1 is Created (not active)
    }

    #[test]
    fn test_all_16_valid_transitions() {
        use OrderState::*;
        let valid = [
            (Created, Pending), (Pending, Approved), (Pending, Rejected), (Pending, Canceled),
            (Approved, Submitted), (Approved, Canceled),
            (Submitted, Working), (Submitted, Rejected),
            (Working, PartiallyFilled), (Working, Filled), (Working, Canceled),
            (PartiallyFilled, Filled), (PartiallyFilled, Canceled),
            (Filled, Reconciling), (Reconciling, Completed), (Reconciling, Rejected),
        ];
        for (from, to) in valid {
            assert!(lookup_rule(from, to).is_some(), "Missing: {from} → {to}");
        }
    }

    #[test]
    fn test_all_12_forbidden_transitions() {
        use OrderState::*;
        let forbidden = [
            (Created, Submitted), (Created, Working), (Created, Approved),
            (Filled, Completed),
            (Completed, Created), (Completed, Reconciling),
            (Canceled, Created), (Canceled, Pending),
            (Rejected, Created), (Rejected, Pending),
            (Working, Submitted), (Filled, Working),
        ];
        for (from, to) in forbidden {
            assert!(is_forbidden(from, to), "Should be forbidden: {from} → {to}");
        }
    }

    #[test]
    fn test_transition_history() {
        let mut sm = OmsStateMachine::new();
        let idx = sm.create_order("BTC", "Buy", 0.1, "market", None, "a");
        assert_eq!(sm.get(idx).unwrap().transitions.len(), 0);
        sm.submit_for_approval(idx, OrderInitiator::AiAgent).unwrap();
        assert_eq!(sm.get(idx).unwrap().transitions.len(), 1);
        sm.approve(idx, OrderInitiator::AuthorizationSm).unwrap();
        assert_eq!(sm.get(idx).unwrap().transitions.len(), 2);
    }
}
