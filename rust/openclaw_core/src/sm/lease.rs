//! Decision Lease State Machine — SM-02 governance specification.
//! 決策租約狀態機 — SM-02 治理規範實現。
//!
//! 9 states, 20 valid transitions, 12 forbidden, 5 guards.
//! 9 個狀態、20 條合法遷移、12 條禁止、5 個守衛。

use super::{SmError, TransitionRecord};
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// States / 狀態
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LeaseState {
    Draft,
    Registered,
    Active,
    Bridged,
    Frozen,
    Revoked,
    Expired,
    Rejected,
    Consumed,
}

impl LeaseState {
    pub fn is_terminal(self) -> bool {
        matches!(self, Self::Revoked | Self::Expired | Self::Rejected | Self::Consumed)
    }

    pub fn is_live(self) -> bool {
        matches!(self, Self::Registered | Self::Active | Self::Bridged)
    }

    pub fn is_bridgeable(self) -> bool {
        matches!(self, Self::Active)
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Draft => "DRAFT",
            Self::Registered => "REGISTERED",
            Self::Active => "ACTIVE",
            Self::Bridged => "BRIDGED",
            Self::Frozen => "FROZEN",
            Self::Revoked => "REVOKED",
            Self::Expired => "EXPIRED",
            Self::Rejected => "REJECTED",
            Self::Consumed => "CONSUMED",
        }
    }
}

impl std::fmt::Display for LeaseState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Events / 事件
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum LeaseEvent {
    DraftCreated,
    RegistrationAccepted,
    RegistrationRejected,
    ActivationWindowOpen,
    BridgeApproved,
    FreezeRequested,
    RevokeRequested,
    ExpiredByTime,
    ConsumedByExecution,
    RecoveryApproved,
}

impl LeaseEvent {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::DraftCreated => "draft_created",
            Self::RegistrationAccepted => "registration_accepted",
            Self::RegistrationRejected => "registration_rejected",
            Self::ActivationWindowOpen => "activation_window_open",
            Self::BridgeApproved => "bridge_approved",
            Self::FreezeRequested => "freeze_requested",
            Self::RevokeRequested => "revoke_requested",
            Self::ExpiredByTime => "expired_by_time",
            Self::ConsumedByExecution => "consumed_by_execution",
            Self::RecoveryApproved => "recovery_approved",
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Initiators / 發起者
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum LeaseInitiator {
    ControlPlane,
    Operator,
    Governance,
    IncidentPolicy,
    ExecutionClosure,
    ExpiryGuardian,
    RiskGovernor,
}

impl LeaseInitiator {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::ControlPlane => "I",
            Self::Operator => "Operator",
            Self::Governance => "AuthorizationGovernance",
            Self::IncidentPolicy => "IncidentPolicy",
            Self::ExecutionClosure => "ExecutionClosureFlow",
            Self::ExpiryGuardian => "ExpiryGuardian",
            Self::RiskGovernor => "RiskGovernor",
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Transition rules / 遷移規則
// ═══════════════════════════════════════════════════════════════════════════════

struct TransitionRule {
    requires_approval: bool,
    allowed: &'static [LeaseInitiator],
}

fn is_forbidden(from: LeaseState, to: LeaseState) -> bool {
    use LeaseState::*;
    matches!(
        (from, to),
        // Terminal backflow
        (Revoked, Active) | (Revoked, Bridged) |
        (Expired, Active) | (Expired, Bridged) |
        (Rejected, Registered) | (Rejected, Active) |
        (Consumed, Active) | (Consumed, Bridged) |
        // Skip registration
        (Draft, Active) | (Draft, Bridged) | (Draft, Consumed) |
        // Skip active
        (Registered, Bridged)
    )
}

fn lookup_rule(from: LeaseState, to: LeaseState) -> Option<TransitionRule> {
    use LeaseInitiator::*;
    use LeaseState::*;

    const I_OP: &[LeaseInitiator] = &[ControlPlane, Operator];
    const GOV: &[LeaseInitiator] = &[ControlPlane, Operator, Governance, IncidentPolicy];
    const FREEZE: &[LeaseInitiator] = &[Operator, IncidentPolicy, Governance, ControlPlane];
    const REVOKE: &[LeaseInitiator] = &[Operator, Governance, IncidentPolicy, ControlPlane];
    const EXPIRY: &[LeaseInitiator] = &[ExpiryGuardian, ControlPlane];
    const RECOVERY: &[LeaseInitiator] = &[Operator, ControlPlane];
    const EXECUTION: &[LeaseInitiator] = &[ExecutionClosure, ControlPlane];
    const RISK_GOV: &[LeaseInitiator] = &[RiskGovernor, ControlPlane, Operator];

    match (from, to) {
        // §7.1 Draft acceptance
        (Draft, Registered) => Some(TransitionRule { requires_approval: false, allowed: I_OP }),
        (Draft, Rejected) => Some(TransitionRule { requires_approval: false, allowed: I_OP }),
        // §7.2 Registration to activation
        (Registered, Active) => Some(TransitionRule { requires_approval: false, allowed: I_OP }),
        (Registered, Frozen) => Some(TransitionRule { requires_approval: false, allowed: FREEZE }),
        (Registered, Revoked) => Some(TransitionRule { requires_approval: true, allowed: REVOKE }),
        (Registered, Expired) => Some(TransitionRule { requires_approval: false, allowed: EXPIRY }),
        (Registered, Rejected) => Some(TransitionRule { requires_approval: false, allowed: GOV }),
        // §7.3 Active to downstream
        (Active, Bridged) => Some(TransitionRule { requires_approval: false, allowed: RISK_GOV }),
        (Active, Frozen) => Some(TransitionRule { requires_approval: false, allowed: FREEZE }),
        (Active, Revoked) => Some(TransitionRule { requires_approval: true, allowed: REVOKE }),
        (Active, Expired) => Some(TransitionRule { requires_approval: false, allowed: EXPIRY }),
        (Active, Rejected) => Some(TransitionRule { requires_approval: false, allowed: GOV }),
        // §7.4 Frozen recovery
        (Frozen, Registered) => Some(TransitionRule { requires_approval: true, allowed: RECOVERY }),
        (Frozen, Active) => Some(TransitionRule { requires_approval: true, allowed: RECOVERY }),
        (Frozen, Revoked) => Some(TransitionRule { requires_approval: true, allowed: REVOKE }),
        (Frozen, Expired) => Some(TransitionRule { requires_approval: false, allowed: EXPIRY }),
        // §7.5 Bridged closure
        (Bridged, Consumed) => Some(TransitionRule { requires_approval: false, allowed: EXECUTION }),
        (Bridged, Revoked) => Some(TransitionRule { requires_approval: true, allowed: REVOKE }),
        _ => None,
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Lease Object / 租約對象
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LeaseObject {
    pub lease_id: String,
    pub state: LeaseState,
    pub version: u32,
    pub created_at_ms: u64,
    pub updated_at_ms: u64,
    pub valid_from_ms: Option<u64>,
    pub expires_at_ms: Option<u64>,
    pub intent: serde_json::Value,
    pub source_stage: String,
    pub created_by: String,
    pub freeze_reason: String,
    pub revoke_reason: String,
    pub rejection_reason: String,
    pub risk_decision_ref: Option<String>,
    pub transitions: Vec<TransitionRecord>,
}

impl LeaseObject {
    pub fn new(intent: serde_json::Value, created_by: &str, expires_at_ms: Option<u64>) -> Self {
        let now = super::now_ms();
        Self {
            lease_id: format!("lease:{:012x}", rand::random::<u64>() & 0xFFFF_FFFF_FFFF),
            state: LeaseState::Draft,
            version: 1,
            created_at_ms: now,
            updated_at_ms: now,
            valid_from_ms: None,
            expires_at_ms,
            intent,
            source_stage: "H5".to_string(),
            created_by: created_by.to_string(),
            freeze_reason: String::new(),
            revoke_reason: String::new(),
            rejection_reason: String::new(),
            risk_decision_ref: None,
            transitions: Vec::new(),
        }
    }

    pub fn is_expired_by_time(&self, now_ms: u64) -> bool {
        self.expires_at_ms.map_or(false, |exp| now_ms > exp)
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// State Machine / 狀態機
// ═══════════════════════════════════════════════════════════════════════════════

pub struct DecisionLeaseSm {
    objects: Vec<LeaseObject>,
}

impl DecisionLeaseSm {
    pub fn new() -> Self {
        Self { objects: Vec::new() }
    }

    pub fn create_draft(&mut self, intent: serde_json::Value, created_by: &str, expires_at_ms: Option<u64>) -> usize {
        let mut obj = LeaseObject::new(intent, created_by, expires_at_ms);
        let record = TransitionRecord::new(
            "NONE", obj.state.as_str(), LeaseEvent::DraftCreated.as_str(),
            LeaseInitiator::ControlPlane.as_str(), vec!["initial_draft".into()],
            false, None, 0,
        );
        obj.transitions.push(record);
        self.objects.push(obj);
        self.objects.len() - 1
    }

    pub fn transition(
        &mut self, idx: usize, to_state: LeaseState, event: LeaseEvent,
        initiator: LeaseInitiator, reason_codes: Vec<String>,
        approved_by: Option<&str>, reason: &str,
    ) -> Result<(), SmError> {
        let obj = self.objects.get_mut(idx)
            .ok_or_else(|| SmError::NotFound(format!("lease index {idx}")))?;
        let from = obj.state;

        if from.is_terminal() {
            return Err(SmError::TerminalState(from.to_string()));
        }
        if is_forbidden(from, to_state) {
            return Err(SmError::Forbidden { from: from.to_string(), to: to_state.to_string() });
        }
        let rule = lookup_rule(from, to_state)
            .ok_or_else(|| SmError::InvalidTransition { from: from.to_string(), to: to_state.to_string() })?;
        if !rule.allowed.contains(&initiator) {
            return Err(SmError::InitiatorNotAllowed {
                initiator: initiator.as_str().to_string(),
                from: from.to_string(), to: to_state.to_string(),
            });
        }
        if rule.requires_approval && approved_by.is_none() {
            return Err(SmError::ApprovalRequired { from: from.to_string(), to: to_state.to_string() });
        }

        let record = TransitionRecord::new(
            from.as_str(), to_state.as_str(), event.as_str(),
            initiator.as_str(), reason_codes, rule.requires_approval,
            approved_by.map(|s| s.to_string()), obj.version,
        );
        obj.state = to_state;
        obj.version += 1;
        obj.updated_at_ms = super::now_ms();
        obj.transitions.push(record);

        match to_state {
            LeaseState::Frozen => obj.freeze_reason = reason.to_string(),
            LeaseState::Revoked => obj.revoke_reason = reason.to_string(),
            LeaseState::Rejected => obj.rejection_reason = reason.to_string(),
            _ => {}
        }
        Ok(())
    }

    // ── Convenience / 便捷 ──

    pub fn register(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, LeaseState::Registered, LeaseEvent::RegistrationAccepted,
            LeaseInitiator::ControlPlane, vec!["registered".into()], None, "")
    }

    pub fn activate(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, LeaseState::Active, LeaseEvent::ActivationWindowOpen,
            LeaseInitiator::ControlPlane, vec!["activated".into()], None, "")
    }

    pub fn bridge(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, LeaseState::Bridged, LeaseEvent::BridgeApproved,
            LeaseInitiator::RiskGovernor, vec!["bridge_approved".into()], None, "")
    }

    pub fn consume(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, LeaseState::Consumed, LeaseEvent::ConsumedByExecution,
            LeaseInitiator::ExecutionClosure, vec!["execution_closure".into()], None, "")
    }

    pub fn freeze(&mut self, idx: usize, reason: &str) -> Result<(), SmError> {
        self.transition(idx, LeaseState::Frozen, LeaseEvent::FreezeRequested,
            LeaseInitiator::IncidentPolicy, vec!["frozen".into()], None, reason)
    }

    pub fn revoke(&mut self, idx: usize, approved_by: &str, reason: &str) -> Result<(), SmError> {
        self.transition(idx, LeaseState::Revoked, LeaseEvent::RevokeRequested,
            LeaseInitiator::Operator, vec!["revoked".into()], Some(approved_by), reason)
    }

    pub fn reject(&mut self, idx: usize, reason: &str) -> Result<(), SmError> {
        self.transition(idx, LeaseState::Rejected, LeaseEvent::RegistrationRejected,
            LeaseInitiator::ControlPlane, vec!["rejected".into()], None, reason)
    }

    pub fn expire(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(idx, LeaseState::Expired, LeaseEvent::ExpiredByTime,
            LeaseInitiator::ExpiryGuardian, vec!["time_expiry".into()], None, "")
    }

    pub fn check_expiry(&mut self) -> Vec<usize> {
        let now = super::now_ms();
        let candidates: Vec<usize> = self.objects.iter().enumerate()
            .filter(|(_, o)| !o.state.is_terminal() && o.is_expired_by_time(now))
            .map(|(i, _)| i)
            .collect();
        let mut expired = Vec::new();
        for idx in candidates {
            if self.expire(idx).is_ok() {
                expired.push(idx);
            }
        }
        expired
    }

    // ── Query / 查詢 ──

    pub fn get(&self, idx: usize) -> Option<&LeaseObject> {
        self.objects.get(idx)
    }

    pub fn get_live(&self) -> Vec<usize> {
        self.objects.iter().enumerate()
            .filter(|(_, o)| o.state.is_live())
            .map(|(i, _)| i).collect()
    }

    pub fn get_bridgeable(&self) -> Vec<usize> {
        self.objects.iter().enumerate()
            .filter(|(_, o)| o.state.is_bridgeable())
            .map(|(i, _)| i).collect()
    }

    pub fn len(&self) -> usize { self.objects.len() }
    pub fn is_empty(&self) -> bool { self.objects.is_empty() }

    pub fn snapshot_states(&self) -> Vec<(usize, LeaseState)> {
        self.objects.iter().enumerate().map(|(i, o)| (i, o.state)).collect()
    }

    /// Revoke all live leases — called when auth is frozen [cross-SM cascade].
    /// 撤銷所有活躍租約 — 授權凍結時調用。
    pub fn revoke_all_live(&mut self, approved_by: &str, reason: &str) -> Vec<usize> {
        let live: Vec<usize> = self.get_live();
        let mut revoked = Vec::new();
        for idx in live {
            if self.revoke(idx, approved_by, reason).is_ok() {
                revoked.push(idx);
            }
        }
        revoked
    }
}

impl Default for DecisionLeaseSm {
    fn default() -> Self { Self::new() }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn make_active_lease() -> (DecisionLeaseSm, usize) {
        let mut sm = DecisionLeaseSm::new();
        let idx = sm.create_draft(serde_json::json!({"symbol": "BTCUSDT"}), "strategist", None);
        sm.register(idx).unwrap();
        sm.activate(idx).unwrap();
        (sm, idx)
    }

    #[test]
    fn test_happy_path_draft_to_consumed() {
        let (mut sm, idx) = make_active_lease();
        sm.bridge(idx).unwrap();
        sm.consume(idx).unwrap();
        assert_eq!(sm.get(idx).unwrap().state, LeaseState::Consumed);
        assert!(sm.get(idx).unwrap().state.is_terminal());
    }

    #[test]
    fn test_terminal_cannot_transition() {
        let (mut sm, idx) = make_active_lease();
        sm.bridge(idx).unwrap();
        sm.consume(idx).unwrap();
        let err = sm.register(idx).unwrap_err();
        assert!(matches!(err, SmError::TerminalState(_)));
    }

    #[test]
    fn test_forbidden_skip_registration() {
        let mut sm = DecisionLeaseSm::new();
        let idx = sm.create_draft(serde_json::json!({}), "test", None);
        let err = sm.transition(idx, LeaseState::Active, LeaseEvent::ActivationWindowOpen,
            LeaseInitiator::ControlPlane, vec![], None, "").unwrap_err();
        assert!(matches!(err, SmError::Forbidden { .. }));
    }

    #[test]
    fn test_forbidden_skip_active_to_bridged() {
        let mut sm = DecisionLeaseSm::new();
        let idx = sm.create_draft(serde_json::json!({}), "test", None);
        sm.register(idx).unwrap();
        let err = sm.transition(idx, LeaseState::Bridged, LeaseEvent::BridgeApproved,
            LeaseInitiator::RiskGovernor, vec![], None, "").unwrap_err();
        assert!(matches!(err, SmError::Forbidden { .. }));
    }

    #[test]
    fn test_freeze_and_recover() {
        let (mut sm, idx) = make_active_lease();
        sm.freeze(idx, "incident").unwrap();
        assert_eq!(sm.get(idx).unwrap().state, LeaseState::Frozen);

        sm.transition(idx, LeaseState::Active, LeaseEvent::RecoveryApproved,
            LeaseInitiator::Operator, vec![], Some("admin"), "resolved").unwrap();
        assert_eq!(sm.get(idx).unwrap().state, LeaseState::Active);
    }

    #[test]
    fn test_revoke_all_live() {
        let mut sm = DecisionLeaseSm::new();
        let i0 = sm.create_draft(serde_json::json!({}), "s", None);
        let i1 = sm.create_draft(serde_json::json!({}), "s", None);
        sm.register(i0).unwrap();
        sm.activate(i0).unwrap();
        sm.register(i1).unwrap();
        // i0=Active (live), i1=Registered (live)
        let revoked = sm.revoke_all_live("admin", "auth frozen");
        assert_eq!(revoked.len(), 2);
    }

    #[test]
    fn test_expiry() {
        let mut sm = DecisionLeaseSm::new();
        let idx = sm.create_draft(serde_json::json!({}), "s", Some(1));
        sm.register(idx).unwrap();
        let expired = sm.check_expiry();
        assert_eq!(expired, vec![idx]);
        assert_eq!(sm.get(idx).unwrap().state, LeaseState::Expired);
    }

    #[test]
    fn test_all_18_valid_transitions() {
        use LeaseState::*;
        let valid = [
            (Draft, Registered), (Draft, Rejected),
            (Registered, Active), (Registered, Frozen), (Registered, Revoked),
            (Registered, Expired), (Registered, Rejected),
            (Active, Bridged), (Active, Frozen), (Active, Revoked),
            (Active, Expired), (Active, Rejected),
            (Frozen, Registered), (Frozen, Active), (Frozen, Revoked), (Frozen, Expired),
            (Bridged, Consumed), (Bridged, Revoked),
        ];
        for (from, to) in valid {
            assert!(lookup_rule(from, to).is_some(), "Missing: {from} → {to}");
        }
    }

    #[test]
    fn test_all_12_forbidden_transitions() {
        use LeaseState::*;
        let forbidden = [
            (Revoked, Active), (Revoked, Bridged),
            (Expired, Active), (Expired, Bridged),
            (Rejected, Registered), (Rejected, Active),
            (Consumed, Active), (Consumed, Bridged),
            (Draft, Active), (Draft, Bridged), (Draft, Consumed),
            (Registered, Bridged),
        ];
        for (from, to) in forbidden {
            assert!(is_forbidden(from, to), "Should be forbidden: {from} → {to}");
        }
    }

    #[test]
    fn test_get_live_and_bridgeable() {
        let (sm, idx) = make_active_lease();
        assert_eq!(sm.get_live(), vec![idx]);
        assert_eq!(sm.get_bridgeable(), vec![idx]);
    }
}
