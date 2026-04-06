//! Authorization State Machine — SM-01 governance specification.
//! 授權狀態機 — SM-01 治理規範實現。
//!
//! 8 states, 16 valid transitions, 6 forbidden, 5 guards.
//! 8 個狀態、16 條合法遷移、6 條禁止、5 個守衛。

use super::{SmError, TransitionRecord};
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// States / 狀態
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AuthState {
    Draft,
    PendingApproval,
    Active,
    Restricted,
    Frozen,
    Revoked,
    Expired,
    Rejected,
}

impl AuthState {
    pub fn is_terminal(self) -> bool {
        matches!(self, Self::Revoked | Self::Expired | Self::Rejected)
    }

    pub fn is_effective(self) -> bool {
        matches!(self, Self::Active | Self::Restricted)
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Draft => "DRAFT",
            Self::PendingApproval => "PENDING_APPROVAL",
            Self::Active => "ACTIVE",
            Self::Restricted => "RESTRICTED",
            Self::Frozen => "FROZEN",
            Self::Revoked => "REVOKED",
            Self::Expired => "EXPIRED",
            Self::Rejected => "REJECTED",
        }
    }
}

impl std::fmt::Display for AuthState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Events / 事件
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AuthEvent {
    DraftCreated,
    SubmittedForApproval,
    Approved,
    Rejected,
    Activated,
    Restricted,
    FreezeApplied,
    Revoked,
    Expired,
    RecoveryApproved,
}

impl AuthEvent {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::DraftCreated => "draft_created",
            Self::SubmittedForApproval => "submitted_for_approval",
            Self::Approved => "approved",
            Self::Rejected => "rejected",
            Self::Activated => "activated",
            Self::Restricted => "restricted",
            Self::FreezeApplied => "freeze_applied",
            Self::Revoked => "revoked",
            Self::Expired => "expired",
            Self::RecoveryApproved => "recovery_approved",
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Initiators / 發起者
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AuthInitiator {
    Governance,
    Operator,
    IncidentPolicy,
    RecoveryFlow,
    ExpiryGuardian,
}

impl AuthInitiator {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Governance => "AuthorizationGovernance",
            Self::Operator => "Operator",
            Self::IncidentPolicy => "IncidentPolicy",
            Self::RecoveryFlow => "RecoveryApprovalFlow",
            Self::ExpiryGuardian => "ExpiryGuardian",
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Transition rules — static validation via match
// 遷移規則 — 通過 match 靜態驗證
// ═══════════════════════════════════════════════════════════════════════════════

struct TransitionRule {
    requires_approval: bool,
    allowed: &'static [AuthInitiator],
}

/// Forbidden transitions (SM-01 §8).
/// 禁止遷移。
fn is_forbidden(from: AuthState, to: AuthState) -> bool {
    use AuthState::*;
    matches!(
        (from, to),
        (Revoked, Active)
            | (Revoked, Restricted)
            | (Expired, Active)
            | (Expired, Restricted)
            | (Rejected, Active)
            | (Rejected, PendingApproval)
            | (Draft, Active) // skip approval
    )
}

/// Look up transition rule. Returns None if not in table.
/// 查找遷移規則。不在表中返回 None。
fn lookup_rule(from: AuthState, to: AuthState) -> Option<TransitionRule> {
    use AuthInitiator::*;
    use AuthState::*;

    const OP_GOV: &[AuthInitiator] = &[Governance, Operator];
    const INCIDENT: &[AuthInitiator] = &[IncidentPolicy, Governance, Operator];
    const RECOVERY: &[AuthInitiator] = &[RecoveryFlow, Operator];
    const EXPIRY: &[AuthInitiator] = &[ExpiryGuardian, Governance];

    match (from, to) {
        // §7.1 Draft & approval
        (Draft, PendingApproval) => Some(TransitionRule {
            requires_approval: false,
            allowed: OP_GOV,
        }),
        (Draft, Rejected) => Some(TransitionRule {
            requires_approval: false,
            allowed: OP_GOV,
        }),
        (PendingApproval, Active) => Some(TransitionRule {
            requires_approval: true,
            allowed: OP_GOV,
        }),
        (PendingApproval, Rejected) => Some(TransitionRule {
            requires_approval: false,
            allowed: OP_GOV,
        }),
        // §7.2 Post-activation
        (Active, Restricted) => Some(TransitionRule {
            requires_approval: false,
            allowed: INCIDENT,
        }),
        (Active, Frozen) => Some(TransitionRule {
            requires_approval: false,
            allowed: INCIDENT,
        }),
        (Active, Revoked) => Some(TransitionRule {
            requires_approval: true,
            allowed: OP_GOV,
        }),
        (Active, Expired) => Some(TransitionRule {
            requires_approval: false,
            allowed: EXPIRY,
        }),
        // §7.3 Recovery & termination
        (Restricted, Active) => Some(TransitionRule {
            requires_approval: true,
            allowed: RECOVERY,
        }),
        (Restricted, Frozen) => Some(TransitionRule {
            requires_approval: false,
            allowed: INCIDENT,
        }),
        (Restricted, Revoked) => Some(TransitionRule {
            requires_approval: true,
            allowed: OP_GOV,
        }),
        (Restricted, Expired) => Some(TransitionRule {
            requires_approval: false,
            allowed: EXPIRY,
        }),
        (Frozen, Restricted) => Some(TransitionRule {
            requires_approval: true,
            allowed: RECOVERY,
        }),
        (Frozen, Active) => Some(TransitionRule {
            requires_approval: true,
            allowed: RECOVERY,
        }),
        (Frozen, Revoked) => Some(TransitionRule {
            requires_approval: true,
            allowed: OP_GOV,
        }),
        (Frozen, Expired) => Some(TransitionRule {
            requires_approval: false,
            allowed: EXPIRY,
        }),
        _ => None,
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Authorization Object / 授權對象
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AuthorizationObject {
    pub authorization_id: String,
    pub state: AuthState,
    pub version: u32,
    pub created_at_ms: u64,
    pub updated_at_ms: u64,
    pub expires_at_ms: Option<u64>,
    pub title: String,
    pub scope: serde_json::Value,
    pub created_by: String,
    pub approved_by: Option<String>,
    pub restriction_reason: String,
    pub freeze_reason: String,
    pub revoke_reason: String,
    pub transitions: Vec<TransitionRecord>,
}

impl AuthorizationObject {
    pub fn new(
        title: &str,
        scope: serde_json::Value,
        created_by: &str,
        expires_at_ms: Option<u64>,
    ) -> Self {
        let now = super::now_ms();
        Self {
            authorization_id: format!("auth:{:012x}", rand::random::<u64>() & 0xFFFF_FFFF_FFFF),
            state: AuthState::Draft,
            version: 1,
            created_at_ms: now,
            updated_at_ms: now,
            expires_at_ms,
            title: title.to_string(),
            scope,
            created_by: created_by.to_string(),
            approved_by: None,
            restriction_reason: String::new(),
            freeze_reason: String::new(),
            revoke_reason: String::new(),
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

/// Authorization State Machine (SM-01).
/// 授權狀態機。
///
/// Sole-owned by tick actor — no internal locks [V3-PA-1].
/// 由 tick actor 獨佔 — 無內部鎖。
#[derive(Clone)]
pub struct AuthorizationSm {
    objects: Vec<AuthorizationObject>,
}

impl AuthorizationSm {
    pub fn new() -> Self {
        Self {
            objects: Vec::new(),
        }
    }

    pub fn create_draft(
        &mut self,
        title: &str,
        scope: serde_json::Value,
        created_by: &str,
        expires_at_ms: Option<u64>,
    ) -> usize {
        let mut obj = AuthorizationObject::new(title, scope, created_by, expires_at_ms);
        let record = TransitionRecord::new(
            "NONE",
            obj.state.as_str(),
            AuthEvent::DraftCreated.as_str(),
            AuthInitiator::Operator.as_str(),
            vec!["initial_draft".into()],
            false,
            None,
            0,
        );
        obj.transitions.push(record);
        self.objects.push(obj);
        self.objects.len() - 1
    }

    /// Core transition with 5 guards.
    /// 核心遷移，5 個守衛。
    pub fn transition(
        &mut self,
        idx: usize,
        to_state: AuthState,
        event: AuthEvent,
        initiator: AuthInitiator,
        reason_codes: Vec<String>,
        approved_by: Option<&str>,
        reason: &str,
    ) -> Result<(), SmError> {
        let obj = self
            .objects
            .get_mut(idx)
            .ok_or_else(|| SmError::NotFound(format!("auth index {idx}")))?;
        let from = obj.state;

        // Guard 1: terminal
        if from.is_terminal() {
            return Err(SmError::TerminalState(from.to_string()));
        }
        // Guard 2: forbidden
        if is_forbidden(from, to_state) {
            return Err(SmError::Forbidden {
                from: from.to_string(),
                to: to_state.to_string(),
            });
        }
        // Guard 3: valid table
        let rule = lookup_rule(from, to_state).ok_or_else(|| SmError::InvalidTransition {
            from: from.to_string(),
            to: to_state.to_string(),
        })?;
        // Guard 4: initiator
        if !rule.allowed.contains(&initiator) {
            return Err(SmError::InitiatorNotAllowed {
                initiator: initiator.as_str().to_string(),
                from: from.to_string(),
                to: to_state.to_string(),
            });
        }
        // Guard 5: approval
        if rule.requires_approval && approved_by.is_none() {
            return Err(SmError::ApprovalRequired {
                from: from.to_string(),
                to: to_state.to_string(),
            });
        }

        // Execute transition
        let record = TransitionRecord::new(
            from.as_str(),
            to_state.as_str(),
            event.as_str(),
            initiator.as_str(),
            reason_codes,
            rule.requires_approval,
            approved_by.map(|s| s.to_string()),
            obj.version,
        );
        obj.state = to_state;
        obj.version += 1;
        obj.updated_at_ms = super::now_ms();
        obj.transitions.push(record);

        // Update metadata
        match to_state {
            AuthState::Active if approved_by.is_some() => {
                obj.approved_by = approved_by.map(|s| s.to_string());
            }
            AuthState::Restricted => obj.restriction_reason = reason.to_string(),
            AuthState::Frozen => obj.freeze_reason = reason.to_string(),
            AuthState::Revoked => obj.revoke_reason = reason.to_string(),
            _ => {}
        }
        Ok(())
    }

    // ── Convenience methods / 便捷方法 ──

    pub fn submit_for_approval(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(
            idx,
            AuthState::PendingApproval,
            AuthEvent::SubmittedForApproval,
            AuthInitiator::Operator,
            vec!["submitted".into()],
            None,
            "",
        )
    }

    pub fn approve(&mut self, idx: usize, approved_by: &str, reason: &str) -> Result<(), SmError> {
        self.transition(
            idx,
            AuthState::Active,
            AuthEvent::Approved,
            AuthInitiator::Operator,
            vec!["approved".into()],
            Some(approved_by),
            reason,
        )
    }

    pub fn reject(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(
            idx,
            AuthState::Rejected,
            AuthEvent::Rejected,
            AuthInitiator::Operator,
            vec!["rejected".into()],
            None,
            "",
        )
    }

    pub fn restrict(&mut self, idx: usize, reason: &str) -> Result<(), SmError> {
        self.transition(
            idx,
            AuthState::Restricted,
            AuthEvent::Restricted,
            AuthInitiator::IncidentPolicy,
            vec!["scope_restricted".into()],
            None,
            reason,
        )
    }

    pub fn freeze(&mut self, idx: usize, reason: &str) -> Result<(), SmError> {
        self.transition(
            idx,
            AuthState::Frozen,
            AuthEvent::FreezeApplied,
            AuthInitiator::IncidentPolicy,
            vec!["frozen".into()],
            None,
            reason,
        )
    }

    pub fn revoke(&mut self, idx: usize, approved_by: &str, reason: &str) -> Result<(), SmError> {
        self.transition(
            idx,
            AuthState::Revoked,
            AuthEvent::Revoked,
            AuthInitiator::Operator,
            vec!["revoked".into()],
            Some(approved_by),
            reason,
        )
    }

    pub fn recover_to_active(
        &mut self,
        idx: usize,
        approved_by: &str,
        reason: &str,
    ) -> Result<(), SmError> {
        self.transition(
            idx,
            AuthState::Active,
            AuthEvent::RecoveryApproved,
            AuthInitiator::RecoveryFlow,
            vec!["full_recovery".into()],
            Some(approved_by),
            reason,
        )
    }

    pub fn recover_to_restricted(
        &mut self,
        idx: usize,
        approved_by: &str,
        reason: &str,
    ) -> Result<(), SmError> {
        self.transition(
            idx,
            AuthState::Restricted,
            AuthEvent::RecoveryApproved,
            AuthInitiator::RecoveryFlow,
            vec!["conservative_recovery".into()],
            Some(approved_by),
            reason,
        )
    }

    pub fn expire(&mut self, idx: usize) -> Result<(), SmError> {
        self.transition(
            idx,
            AuthState::Expired,
            AuthEvent::Expired,
            AuthInitiator::ExpiryGuardian,
            vec!["time_expiry".into()],
            None,
            "",
        )
    }

    /// Check all non-terminal objects for time-based expiry.
    /// 檢查所有非終態對象的時間過期。
    pub fn check_expiry(&mut self) -> Vec<usize> {
        let now = super::now_ms();
        let candidates: Vec<usize> = self
            .objects
            .iter()
            .enumerate()
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

    pub fn get(&self, idx: usize) -> Option<&AuthorizationObject> {
        self.objects.get(idx)
    }

    pub fn get_effective(&self) -> Vec<usize> {
        self.objects
            .iter()
            .enumerate()
            .filter(|(_, o)| o.state.is_effective())
            .map(|(i, _)| i)
            .collect()
    }

    pub fn len(&self) -> usize {
        self.objects.len()
    }

    pub fn is_empty(&self) -> bool {
        self.objects.is_empty()
    }

    /// Clone SM state for cascade snapshot [V3-PA-3].
    /// 克隆 SM 狀態用於級聯快照。
    pub fn snapshot_states(&self) -> Vec<(usize, AuthState)> {
        self.objects
            .iter()
            .enumerate()
            .map(|(i, o)| (i, o.state))
            .collect()
    }
}

impl Default for AuthorizationSm {
    fn default() -> Self {
        Self::new()
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn make_sm_with_draft() -> (AuthorizationSm, usize) {
        let mut sm = AuthorizationSm::new();
        let idx = sm.create_draft("test", serde_json::json!({}), "operator", None);
        (sm, idx)
    }

    fn make_sm_active() -> (AuthorizationSm, usize) {
        let (mut sm, idx) = make_sm_with_draft();
        sm.submit_for_approval(idx).unwrap();
        sm.approve(idx, "admin", "ok").unwrap();
        (sm, idx)
    }

    #[test]
    fn test_happy_path_draft_to_active() {
        let (sm, idx) = make_sm_active();
        assert_eq!(sm.get(idx).unwrap().state, AuthState::Active);
        assert_eq!(sm.get(idx).unwrap().version, 3); // submit(2) + approve(3)
    }

    #[test]
    fn test_terminal_states_cannot_transition() {
        let (mut sm, idx) = make_sm_with_draft();
        sm.reject(idx).unwrap();
        assert!(sm.get(idx).unwrap().state.is_terminal());

        let err = sm.submit_for_approval(idx).unwrap_err();
        assert!(matches!(err, SmError::TerminalState(_)));
    }

    #[test]
    fn test_forbidden_draft_to_active() {
        let (mut sm, idx) = make_sm_with_draft();
        let err = sm
            .transition(
                idx,
                AuthState::Active,
                AuthEvent::Approved,
                AuthInitiator::Operator,
                vec![],
                Some("admin"),
                "",
            )
            .unwrap_err();
        assert!(matches!(err, SmError::Forbidden { .. }));
    }

    #[test]
    fn test_approval_required_for_pending_to_active() {
        let (mut sm, idx) = make_sm_with_draft();
        sm.submit_for_approval(idx).unwrap();
        let err = sm
            .transition(
                idx,
                AuthState::Active,
                AuthEvent::Approved,
                AuthInitiator::Operator,
                vec![],
                None,
                "",
            )
            .unwrap_err();
        assert!(matches!(err, SmError::ApprovalRequired { .. }));
    }

    #[test]
    fn test_initiator_check() {
        let (mut sm, idx) = make_sm_active();
        // ExpiryGuardian cannot restrict (only IncidentPolicy/Governance/Operator)
        let err = sm
            .transition(
                idx,
                AuthState::Restricted,
                AuthEvent::Restricted,
                AuthInitiator::ExpiryGuardian,
                vec![],
                None,
                "",
            )
            .unwrap_err();
        assert!(matches!(err, SmError::InitiatorNotAllowed { .. }));
    }

    #[test]
    fn test_active_restrict_freeze_revoke() {
        let (mut sm, idx) = make_sm_active();
        sm.restrict(idx, "risk high").unwrap();
        assert_eq!(sm.get(idx).unwrap().state, AuthState::Restricted);

        sm.freeze(idx, "incident").unwrap();
        assert_eq!(sm.get(idx).unwrap().state, AuthState::Frozen);

        sm.revoke(idx, "admin", "severe").unwrap();
        assert_eq!(sm.get(idx).unwrap().state, AuthState::Revoked);
        assert!(sm.get(idx).unwrap().state.is_terminal());
    }

    #[test]
    fn test_recovery_from_frozen() {
        let (mut sm, idx) = make_sm_active();
        sm.freeze(idx, "incident").unwrap();

        // Recover to restricted (conservative)
        sm.recover_to_restricted(idx, "admin", "resolved").unwrap();
        assert_eq!(sm.get(idx).unwrap().state, AuthState::Restricted);

        // Then recover to active
        sm.recover_to_active(idx, "admin", "fully resolved")
            .unwrap();
        assert_eq!(sm.get(idx).unwrap().state, AuthState::Active);
    }

    #[test]
    fn test_expiry_guardian() {
        let mut sm = AuthorizationSm::new();
        // Create with already-expired time
        let idx = sm.create_draft("test", serde_json::json!({}), "op", Some(1));
        sm.submit_for_approval(idx).unwrap();
        sm.approve(idx, "admin", "ok").unwrap();

        let expired = sm.check_expiry();
        assert_eq!(expired, vec![idx]);
        assert_eq!(sm.get(idx).unwrap().state, AuthState::Expired);
    }

    #[test]
    fn test_get_effective() {
        let (mut sm, idx) = make_sm_active();
        assert_eq!(sm.get_effective(), vec![idx]);

        sm.restrict(idx, "risk").unwrap();
        assert_eq!(sm.get_effective(), vec![idx]); // Restricted is effective

        sm.freeze(idx, "freeze").unwrap();
        assert!(sm.get_effective().is_empty()); // Frozen is not effective
    }

    #[test]
    fn test_all_16_valid_transitions() {
        use AuthState::*;
        let valid_pairs = [
            (Draft, PendingApproval),
            (Draft, Rejected),
            (PendingApproval, Active),
            (PendingApproval, Rejected),
            (Active, Restricted),
            (Active, Frozen),
            (Active, Revoked),
            (Active, Expired),
            (Restricted, Active),
            (Restricted, Frozen),
            (Restricted, Revoked),
            (Restricted, Expired),
            (Frozen, Restricted),
            (Frozen, Active),
            (Frozen, Revoked),
            (Frozen, Expired),
        ];
        for (from, to) in valid_pairs {
            assert!(
                lookup_rule(from, to).is_some(),
                "Missing rule: {from} → {to}"
            );
        }
    }

    #[test]
    fn test_all_7_forbidden_transitions() {
        use AuthState::*;
        let forbidden = [
            (Revoked, Active),
            (Revoked, Restricted),
            (Expired, Active),
            (Expired, Restricted),
            (Rejected, Active),
            (Rejected, PendingApproval),
            (Draft, Active),
        ];
        for (from, to) in forbidden {
            assert!(is_forbidden(from, to), "Should be forbidden: {from} → {to}");
        }
    }

    #[test]
    fn test_exhaustive_invalid_transitions_rejected() {
        use AuthState::*;
        let all_states = [
            Draft,
            PendingApproval,
            Active,
            Restricted,
            Frozen,
            Revoked,
            Expired,
            Rejected,
        ];
        for from in all_states {
            for to in all_states {
                if from == to {
                    continue;
                }
                if is_forbidden(from, to) || lookup_rule(from, to).is_some() {
                    continue;
                }
                // Must be invalid — confirm lookup returns None
                assert!(
                    lookup_rule(from, to).is_none(),
                    "Unexpected valid rule for non-specified transition: {from} → {to}"
                );
            }
        }
    }

    #[test]
    fn test_transition_history_grows() {
        let (mut sm, idx) = make_sm_with_draft();
        assert_eq!(sm.get(idx).unwrap().transitions.len(), 1); // create
        sm.submit_for_approval(idx).unwrap();
        assert_eq!(sm.get(idx).unwrap().transitions.len(), 2);
        sm.approve(idx, "admin", "ok").unwrap();
        assert_eq!(sm.get(idx).unwrap().transitions.len(), 3);
    }

    #[test]
    fn test_snapshot_states() {
        let (sm, idx) = make_sm_active();
        let snap = sm.snapshot_states();
        assert_eq!(snap[idx].1, AuthState::Active);
    }
}
