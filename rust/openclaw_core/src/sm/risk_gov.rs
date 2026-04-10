//! Risk Governor State Machine — SM-04: 6-level risk governance.
//! 風控總督狀態機 — SM-04：6 級風控治理。
//!
//! Escalation auto, de-escalation needs approval + min hold time.
//! 升級自動，降級需審批 + 最低持有時間。

use super::{SmError, TransitionRecord};
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// Risk Levels / 風控等級
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
#[repr(u8)]
pub enum RiskLevel {
    Normal = 0,
    Cautious = 1,
    Reduced = 2,
    Defensive = 3,
    CircuitBreaker = 4,
    ManualReview = 5,
}

impl RiskLevel {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Normal => "NORMAL",
            Self::Cautious => "CAUTIOUS",
            Self::Reduced => "REDUCED",
            Self::Defensive => "DEFENSIVE",
            Self::CircuitBreaker => "CIRCUIT_BREAKER",
            Self::ManualReview => "MANUAL_REVIEW",
        }
    }

    pub fn value(self) -> u8 {
        self as u8
    }
}

impl std::fmt::Display for RiskLevel {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Events / 事件
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum RiskEvent {
    DrawdownWarning,
    DrawdownCritical,
    DailyLossWarning,
    DailyLossBreach,
    ConsecutiveLosses,
    CorrelationBreach,
    HealthDegraded,
    MarketDataStale,
    ApiConnectivityLoss,
    IncidentTriggered,
    OperatorEscalation,
    ConditionsImproved,
    OperatorDeEscalation,
    RecoveryApproved,
    ManualReviewCompleted,
    OperatorCircuitBreak,
    OperatorManualReview,
    OperatorResetNormal,
    /// Reconciler detected position drift (MajorDrift / Orphan / Ghost / persistent).
    /// 對帳器偵測到持倉漂移。
    ReconcilerDrift,
    /// Reconciler REST polling failed consecutively (6-RC-10).
    /// 對帳器 REST 輪詢連續失敗。
    ReconcilerRestFailure,
    /// Reconciler clean cycles met — auto-recovery toward pre-escalation floor.
    /// 對帳器連續乾淨週期達標 — 自動恢復至降級前水位。
    ReconcilerRecovery,
}

impl RiskEvent {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::DrawdownWarning => "drawdown_warning",
            Self::DrawdownCritical => "drawdown_critical",
            Self::DailyLossWarning => "daily_loss_warning",
            Self::DailyLossBreach => "daily_loss_breach",
            Self::ConsecutiveLosses => "consecutive_losses",
            Self::CorrelationBreach => "correlation_breach",
            Self::HealthDegraded => "health_degraded",
            Self::MarketDataStale => "market_data_stale",
            Self::ApiConnectivityLoss => "api_connectivity_loss",
            Self::IncidentTriggered => "incident_triggered",
            Self::OperatorEscalation => "operator_escalation",
            Self::ConditionsImproved => "conditions_improved",
            Self::OperatorDeEscalation => "operator_de_escalation",
            Self::RecoveryApproved => "recovery_approved",
            Self::ManualReviewCompleted => "manual_review_completed",
            Self::OperatorCircuitBreak => "operator_circuit_break",
            Self::OperatorManualReview => "operator_manual_review",
            Self::OperatorResetNormal => "operator_reset_normal",
            Self::ReconcilerDrift => "reconciler_drift",
            Self::ReconcilerRestFailure => "reconciler_rest_failure",
            Self::ReconcilerRecovery => "reconciler_recovery",
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Initiators / 發起者
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum RiskInitiator {
    RiskGovernor,
    Operator,
    IncidentPolicy,
    HealthMonitor,
    ExpiryGuardian,
    /// Position reconciler — auto-escalation on drift, auto-recovery when clean.
    /// 持倉對帳器 — 漂移時自動升級，恢復時自動降級。
    Reconciler,
}

impl RiskInitiator {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::RiskGovernor => "RiskGovernor",
            Self::Operator => "Operator",
            Self::IncidentPolicy => "IncidentPolicy",
            Self::HealthMonitor => "HealthMonitor",
            Self::ExpiryGuardian => "ExpiryGuardian",
            Self::Reconciler => "Reconciler",
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Level Constraints / 等級約束
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct LevelConstraints {
    pub new_entries_allowed: bool,
    pub position_size_multiplier: f64,
    pub reduce_only: bool,
    pub active_de_risking: bool,
    pub emergency_stops: bool,
    pub requires_operator: bool,
}

pub fn constraints_for(level: RiskLevel) -> LevelConstraints {
    match level {
        RiskLevel::Normal => LevelConstraints {
            new_entries_allowed: true,
            position_size_multiplier: 1.0,
            reduce_only: false,
            active_de_risking: false,
            emergency_stops: false,
            requires_operator: false,
        },
        RiskLevel::Cautious => LevelConstraints {
            new_entries_allowed: true,
            position_size_multiplier: 0.7,
            reduce_only: false,
            active_de_risking: false,
            emergency_stops: false,
            requires_operator: false,
        },
        RiskLevel::Reduced => LevelConstraints {
            new_entries_allowed: false,
            position_size_multiplier: 0.5,
            reduce_only: true,
            active_de_risking: false,
            emergency_stops: false,
            requires_operator: false,
        },
        RiskLevel::Defensive => LevelConstraints {
            new_entries_allowed: false,
            position_size_multiplier: 0.0,
            reduce_only: true,
            active_de_risking: true,
            emergency_stops: false,
            requires_operator: false,
        },
        RiskLevel::CircuitBreaker => LevelConstraints {
            new_entries_allowed: false,
            position_size_multiplier: 0.0,
            reduce_only: true,
            active_de_risking: true,
            emergency_stops: true,
            requires_operator: true,
        },
        RiskLevel::ManualReview => LevelConstraints {
            new_entries_allowed: false,
            position_size_multiplier: 0.0,
            reduce_only: true,
            active_de_risking: false,
            emergency_stops: true,
            requires_operator: true,
        },
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Escalation Thresholds / 升級閾值
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EscalationThresholds {
    pub drawdown_cautious_pct: f64,
    pub drawdown_reduced_pct: f64,
    pub drawdown_defensive_pct: f64,
    pub drawdown_circuit_breaker_pct: f64,
    pub daily_loss_cautious_pct: f64,
    pub daily_loss_reduced_pct: f64,
    pub daily_loss_circuit_breaker_pct: f64,
    pub consecutive_loss_cautious: u32,
    pub consecutive_loss_reduced: u32,
    pub consecutive_loss_circuit_breaker: u32,
    pub pressure_cautious: f64,
    pub pressure_reduced: f64,
    pub pressure_defensive: f64,
    pub pressure_circuit_breaker: f64,
    pub min_hold_time_ms: u64,
}

impl Default for EscalationThresholds {
    fn default() -> Self {
        Self {
            drawdown_cautious_pct: 5.0,
            drawdown_reduced_pct: 8.0,
            drawdown_defensive_pct: 12.0,
            drawdown_circuit_breaker_pct: 15.0,
            daily_loss_cautious_pct: 2.0,
            daily_loss_reduced_pct: 3.5,
            daily_loss_circuit_breaker_pct: 5.0,
            consecutive_loss_cautious: 3,
            consecutive_loss_reduced: 5,
            consecutive_loss_circuit_breaker: 10,
            pressure_cautious: 0.3,
            pressure_reduced: 0.5,
            pressure_defensive: 0.7,
            pressure_circuit_breaker: 0.9,
            min_hold_time_ms: 300_000, // 5 min
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Transition rules / 遷移規則
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Direction {
    Escalation,
    DeEscalation,
    Lateral,
}

struct TransitionRule {
    direction: Direction,
    requires_approval: bool,
    allowed: &'static [RiskInitiator],
}

fn lookup_rule(from: RiskLevel, to: RiskLevel) -> Option<TransitionRule> {
    use RiskInitiator::*;
    use RiskLevel::*;

    const AUTO: &[RiskInitiator] = &[RiskGovernor, Operator, IncidentPolicy, HealthMonitor, Reconciler];
    const OP_GOV: &[RiskInitiator] = &[Operator, RiskGovernor, Reconciler];
    const OP_ONLY: &[RiskInitiator] = &[Operator];

    match (from, to) {
        // Escalation (auto, no approval)
        (Normal, Cautious) | (Normal, Reduced) | (Normal, Defensive) | (Normal, CircuitBreaker) => {
            Some(TransitionRule {
                direction: Direction::Escalation,
                requires_approval: false,
                allowed: AUTO,
            })
        }
        (Normal, ManualReview) => Some(TransitionRule {
            direction: Direction::Escalation,
            requires_approval: false,
            allowed: OP_GOV,
        }),
        (Cautious, Reduced) | (Cautious, Defensive) | (Cautious, CircuitBreaker) => {
            Some(TransitionRule {
                direction: Direction::Escalation,
                requires_approval: false,
                allowed: AUTO,
            })
        }
        (Cautious, ManualReview) => Some(TransitionRule {
            direction: Direction::Escalation,
            requires_approval: false,
            allowed: OP_GOV,
        }),
        (Reduced, Defensive) | (Reduced, CircuitBreaker) => Some(TransitionRule {
            direction: Direction::Escalation,
            requires_approval: false,
            allowed: AUTO,
        }),
        (Reduced, ManualReview) => Some(TransitionRule {
            direction: Direction::Escalation,
            requires_approval: false,
            allowed: OP_GOV,
        }),
        (Defensive, CircuitBreaker) => Some(TransitionRule {
            direction: Direction::Escalation,
            requires_approval: false,
            allowed: AUTO,
        }),
        (Defensive, ManualReview) => Some(TransitionRule {
            direction: Direction::Escalation,
            requires_approval: false,
            allowed: OP_GOV,
        }),
        (CircuitBreaker, ManualReview) => Some(TransitionRule {
            direction: Direction::Lateral,
            requires_approval: false,
            allowed: OP_GOV,
        }),

        // De-escalation (requires approval + hold time)
        (Cautious, Normal) => Some(TransitionRule {
            direction: Direction::DeEscalation,
            requires_approval: true,
            allowed: OP_GOV,
        }),
        (Reduced, Cautious) => Some(TransitionRule {
            direction: Direction::DeEscalation,
            requires_approval: true,
            allowed: OP_GOV,
        }),
        (Reduced, Normal) => Some(TransitionRule {
            direction: Direction::DeEscalation,
            requires_approval: true,
            allowed: OP_ONLY,
        }),
        (Defensive, Reduced) => Some(TransitionRule {
            direction: Direction::DeEscalation,
            requires_approval: true,
            allowed: OP_GOV,
        }),
        (Defensive, Cautious) => Some(TransitionRule {
            direction: Direction::DeEscalation,
            requires_approval: true,
            allowed: OP_ONLY,
        }),
        (CircuitBreaker, Defensive) => Some(TransitionRule {
            direction: Direction::DeEscalation,
            requires_approval: true,
            allowed: OP_ONLY,
        }),
        (ManualReview, Defensive)
        | (ManualReview, Reduced)
        | (ManualReview, Cautious)
        | (ManualReview, Normal) => Some(TransitionRule {
            direction: Direction::DeEscalation,
            requires_approval: true,
            allowed: OP_ONLY,
        }),

        _ => None,
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// State Machine / 狀態機
// ═══════════════════════════════════════════════════════════════════════════════

pub struct RiskGovernorSm {
    pub level: RiskLevel,
    pub level_entered_at_ms: u64,
    pub consecutive_escalations: u32,
    pub version: u32,
    pub transitions: Vec<TransitionRecord>,
    pub thresholds: EscalationThresholds,
}

impl RiskGovernorSm {
    pub fn new() -> Self {
        Self {
            level: RiskLevel::Normal,
            level_entered_at_ms: super::now_ms(),
            consecutive_escalations: 0,
            version: 1,
            transitions: Vec::new(),
            thresholds: EscalationThresholds::default(),
        }
    }

    pub fn with_thresholds(thresholds: EscalationThresholds) -> Self {
        Self {
            thresholds,
            ..Self::new()
        }
    }

    pub fn constraints(&self) -> LevelConstraints {
        constraints_for(self.level)
    }

    pub fn transition(
        &mut self,
        to_level: RiskLevel,
        event: RiskEvent,
        initiator: RiskInitiator,
        reason_codes: Vec<String>,
        approved_by: Option<&str>,
        _reason: &str,
    ) -> Result<(), SmError> {
        let from = self.level;
        if from == to_level {
            return Ok(());
        } // no-op

        let rule = lookup_rule(from, to_level).ok_or_else(|| SmError::InvalidTransition {
            from: from.to_string(),
            to: to_level.to_string(),
        })?;

        if !rule.allowed.contains(&initiator) {
            return Err(SmError::InitiatorNotAllowed {
                initiator: initiator.as_str().to_string(),
                from: from.to_string(),
                to: to_level.to_string(),
            });
        }

        if rule.requires_approval && approved_by.is_none() {
            return Err(SmError::ApprovalRequired {
                from: from.to_string(),
                to: to_level.to_string(),
            });
        }

        // Hold time check for de-escalation
        if rule.direction == Direction::DeEscalation {
            let now = super::now_ms();
            let held_ms = now.saturating_sub(self.level_entered_at_ms);
            if held_ms < self.thresholds.min_hold_time_ms {
                return Err(SmError::HoldTimeNotMet {
                    remaining_ms: self.thresholds.min_hold_time_ms - held_ms,
                });
            }
        }

        let record = TransitionRecord::new(
            from.as_str(),
            to_level.as_str(),
            event.as_str(),
            initiator.as_str(),
            reason_codes,
            rule.requires_approval,
            approved_by.map(|s| s.to_string()),
            self.version,
        );
        self.level = to_level;
        self.level_entered_at_ms = super::now_ms();
        self.version += 1;
        self.transitions.push(record);

        if to_level > from {
            self.consecutive_escalations += 1;
        } else {
            self.consecutive_escalations = 0;
        }
        Ok(())
    }

    // ── Convenience / 便捷 ──

    pub fn escalate_to(
        &mut self,
        level: RiskLevel,
        reason: &str,
        event: RiskEvent,
    ) -> Result<(), SmError> {
        self.transition(
            level,
            event,
            RiskInitiator::RiskGovernor,
            vec!["escalation".into()],
            None,
            reason,
        )
    }

    pub fn de_escalate_to(
        &mut self,
        level: RiskLevel,
        approved_by: &str,
        reason: &str,
    ) -> Result<(), SmError> {
        self.transition(
            level,
            RiskEvent::RecoveryApproved,
            RiskInitiator::Operator,
            vec!["de_escalation_approved".into()],
            Some(approved_by),
            reason,
        )
    }

    /// Reconciler-driven escalation (tighten risk on drift detection).
    /// Bypasses operator whitelist/cooldown — drift response must never be blocked.
    /// 對帳器驅動的升級（漂移時收緊風控）。繞過 operator 白名單/冷卻。
    pub fn reconciler_escalate_to(
        &mut self,
        level: RiskLevel,
        reason: &str,
    ) -> Result<(), SmError> {
        self.transition(
            level,
            RiskEvent::ReconcilerDrift,
            RiskInitiator::Reconciler,
            vec!["reconciler_drift".into()],
            None,
            reason,
        )
    }

    /// Reconciler-driven de-escalation (auto-recovery after clean cycles).
    /// Only works for Cautious/Reduced/Defensive → one-step-lower.
    /// CB/MR recovery remains OP_ONLY and will be rejected.
    /// 對帳器驅動的降級（乾淨週期後自動恢復）。CB/MR 仍需 operator。
    pub fn reconciler_de_escalate_to(
        &mut self,
        level: RiskLevel,
        reason: &str,
    ) -> Result<(), SmError> {
        self.transition(
            level,
            RiskEvent::ReconcilerRecovery,
            RiskInitiator::Reconciler,
            vec!["reconciler_auto_recovery".into()],
            Some("reconciler_auto_recovery"),
            reason,
        )
    }

    pub fn circuit_break(&mut self, reason: &str) -> Result<(), SmError> {
        self.escalate_to(
            RiskLevel::CircuitBreaker,
            reason,
            RiskEvent::IncidentTriggered,
        )
    }

    /// Auto-evaluate risk metrics and escalate if needed.
    /// 自動評估風控指標，超閾值則升級。
    pub fn evaluate_risk_context(
        &mut self,
        pressure: f64,
        drawdown_pct: f64,
        daily_loss_pct: f64,
        consecutive_losses: u32,
        session_halted: bool,
        cooldown_active: bool,
    ) -> Option<RiskLevel> {
        let t = &self.thresholds;
        let mut target = RiskLevel::Normal;

        // Pressure
        if pressure >= t.pressure_circuit_breaker {
            target = target.max(RiskLevel::CircuitBreaker);
        } else if pressure >= t.pressure_defensive {
            target = target.max(RiskLevel::Defensive);
        } else if pressure >= t.pressure_reduced {
            target = target.max(RiskLevel::Reduced);
        } else if pressure >= t.pressure_cautious {
            target = target.max(RiskLevel::Cautious);
        }

        // Drawdown
        if drawdown_pct >= t.drawdown_circuit_breaker_pct {
            target = target.max(RiskLevel::CircuitBreaker);
        } else if drawdown_pct >= t.drawdown_defensive_pct {
            target = target.max(RiskLevel::Defensive);
        } else if drawdown_pct >= t.drawdown_reduced_pct {
            target = target.max(RiskLevel::Reduced);
        } else if drawdown_pct >= t.drawdown_cautious_pct {
            target = target.max(RiskLevel::Cautious);
        }

        // Daily loss
        if daily_loss_pct >= t.daily_loss_circuit_breaker_pct {
            target = target.max(RiskLevel::CircuitBreaker);
        } else if daily_loss_pct >= t.daily_loss_reduced_pct {
            target = target.max(RiskLevel::Reduced);
        } else if daily_loss_pct >= t.daily_loss_cautious_pct {
            target = target.max(RiskLevel::Cautious);
        }

        // Consecutive losses
        if consecutive_losses >= t.consecutive_loss_circuit_breaker {
            target = target.max(RiskLevel::CircuitBreaker);
        } else if consecutive_losses >= t.consecutive_loss_reduced {
            target = target.max(RiskLevel::Reduced);
        } else if consecutive_losses >= t.consecutive_loss_cautious {
            target = target.max(RiskLevel::Cautious);
        }

        if session_halted {
            target = target.max(RiskLevel::CircuitBreaker);
        }
        if cooldown_active {
            target = target.max(RiskLevel::Reduced);
        }

        // Only escalate, never auto-de-escalate
        if target > self.level {
            let event = if drawdown_pct >= t.drawdown_defensive_pct {
                RiskEvent::DrawdownCritical
            } else if daily_loss_pct >= t.daily_loss_reduced_pct {
                RiskEvent::DailyLossBreach
            } else if consecutive_losses >= t.consecutive_loss_reduced {
                RiskEvent::ConsecutiveLosses
            } else {
                RiskEvent::DrawdownWarning
            };
            if self.escalate_to(target, "auto_eval", event).is_ok() {
                return Some(target);
            }
        }
        None
    }

    pub fn snapshot_level(&self) -> RiskLevel {
        self.level
    }
}

impl Default for RiskGovernorSm {
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

    #[test]
    fn test_escalation_auto() {
        let mut sm = RiskGovernorSm::new();
        sm.escalate_to(RiskLevel::Cautious, "test", RiskEvent::DrawdownWarning)
            .unwrap();
        assert_eq!(sm.level, RiskLevel::Cautious);
        assert_eq!(sm.consecutive_escalations, 1);
    }

    #[test]
    fn test_skip_escalation() {
        let mut sm = RiskGovernorSm::new();
        sm.escalate_to(
            RiskLevel::CircuitBreaker,
            "severe",
            RiskEvent::IncidentTriggered,
        )
        .unwrap();
        assert_eq!(sm.level, RiskLevel::CircuitBreaker);
        assert_eq!(sm.consecutive_escalations, 1);
    }

    #[test]
    fn test_de_escalation_requires_approval() {
        let mut sm = RiskGovernorSm::new();
        sm.thresholds.min_hold_time_ms = 0; // disable for test
        sm.escalate_to(RiskLevel::Cautious, "test", RiskEvent::DrawdownWarning)
            .unwrap();
        let err = sm
            .transition(
                RiskLevel::Normal,
                RiskEvent::RecoveryApproved,
                RiskInitiator::Operator,
                vec![],
                None,
                "",
            )
            .unwrap_err();
        assert!(matches!(err, SmError::ApprovalRequired { .. }));
    }

    #[test]
    fn test_de_escalation_hold_time() {
        let mut sm = RiskGovernorSm::new();
        sm.escalate_to(RiskLevel::Cautious, "test", RiskEvent::DrawdownWarning)
            .unwrap();
        // min_hold_time_ms = 300_000, so immediate de-escalation fails
        let err = sm
            .de_escalate_to(RiskLevel::Normal, "admin", "resolved")
            .unwrap_err();
        assert!(matches!(err, SmError::HoldTimeNotMet { .. }));
    }

    #[test]
    fn test_de_escalation_after_hold() {
        let mut sm = RiskGovernorSm::new();
        sm.thresholds.min_hold_time_ms = 0;
        sm.escalate_to(RiskLevel::Cautious, "test", RiskEvent::DrawdownWarning)
            .unwrap();
        sm.de_escalate_to(RiskLevel::Normal, "admin", "resolved")
            .unwrap();
        assert_eq!(sm.level, RiskLevel::Normal);
        assert_eq!(sm.consecutive_escalations, 0);
    }

    #[test]
    fn test_same_level_noop() {
        let mut sm = RiskGovernorSm::new();
        sm.transition(
            RiskLevel::Normal,
            RiskEvent::ConditionsImproved,
            RiskInitiator::Operator,
            vec![],
            None,
            "",
        )
        .unwrap();
        assert_eq!(sm.transitions.len(), 0);
    }

    #[test]
    fn test_constraints() {
        let sm = RiskGovernorSm::new();
        let c = sm.constraints();
        assert!(c.new_entries_allowed);
        assert!(!c.reduce_only);
    }

    #[test]
    fn test_circuit_breaker_constraints() {
        let c = constraints_for(RiskLevel::CircuitBreaker);
        assert!(!c.new_entries_allowed);
        assert!(c.reduce_only);
        assert!(c.emergency_stops);
        assert!(c.requires_operator);
        assert_eq!(c.position_size_multiplier, 0.0);
    }

    #[test]
    fn test_evaluate_risk_context_escalates() {
        let mut sm = RiskGovernorSm::new();
        let result = sm.evaluate_risk_context(0.6, 9.0, 0.0, 0, false, false);
        assert_eq!(result, Some(RiskLevel::Reduced));
        assert_eq!(sm.level, RiskLevel::Reduced);
    }

    #[test]
    fn test_evaluate_no_escalation() {
        let mut sm = RiskGovernorSm::new();
        let result = sm.evaluate_risk_context(0.1, 1.0, 0.5, 0, false, false);
        assert_eq!(result, None);
        assert_eq!(sm.level, RiskLevel::Normal);
    }

    #[test]
    fn test_evaluate_session_halted() {
        let mut sm = RiskGovernorSm::new();
        let result = sm.evaluate_risk_context(0.0, 0.0, 0.0, 0, true, false);
        assert_eq!(result, Some(RiskLevel::CircuitBreaker));
    }

    #[test]
    fn test_all_escalation_paths() {
        use RiskLevel::*;
        let escalations = [
            (Normal, Cautious),
            (Normal, Reduced),
            (Normal, Defensive),
            (Normal, CircuitBreaker),
            (Normal, ManualReview),
            (Cautious, Reduced),
            (Cautious, Defensive),
            (Cautious, CircuitBreaker),
            (Cautious, ManualReview),
            (Reduced, Defensive),
            (Reduced, CircuitBreaker),
            (Reduced, ManualReview),
            (Defensive, CircuitBreaker),
            (Defensive, ManualReview),
            (CircuitBreaker, ManualReview),
        ];
        for (from, to) in escalations {
            assert!(
                lookup_rule(from, to).is_some(),
                "Missing escalation: {from} → {to}"
            );
        }
    }

    #[test]
    fn test_all_de_escalation_paths() {
        use RiskLevel::*;
        let de_escalations = [
            (Cautious, Normal),
            (Reduced, Cautious),
            (Reduced, Normal),
            (Defensive, Reduced),
            (Defensive, Cautious),
            (CircuitBreaker, Defensive),
            (ManualReview, Defensive),
            (ManualReview, Reduced),
            (ManualReview, Cautious),
            (ManualReview, Normal),
        ];
        for (from, to) in de_escalations {
            let rule = lookup_rule(from, to);
            assert!(rule.is_some(), "Missing de-escalation: {from} → {to}");
            assert!(
                rule.unwrap().requires_approval,
                "De-escalation {from} → {to} should require approval"
            );
        }
    }

    #[test]
    fn test_invalid_transition() {
        let mut sm = RiskGovernorSm::new();
        // Normal → ManualReview is valid, but Normal → Reduced → Normal without hold fails
        sm.escalate_to(RiskLevel::Reduced, "test", RiskEvent::DrawdownWarning)
            .unwrap();
        // Skip de-escalation to Normal needs Operator only
        let err = sm
            .transition(
                RiskLevel::Normal,
                RiskEvent::RecoveryApproved,
                RiskInitiator::HealthMonitor,
                vec![],
                Some("admin"),
                "",
            )
            .unwrap_err();
        assert!(matches!(err, SmError::InitiatorNotAllowed { .. }));
    }

    #[test]
    fn test_operator_only_circuit_breaker_de_escalation() {
        let mut sm = RiskGovernorSm::new();
        sm.thresholds.min_hold_time_ms = 0;
        sm.circuit_break("test").unwrap();
        // RiskGovernor cannot de-escalate from CircuitBreaker
        let err = sm
            .transition(
                RiskLevel::Defensive,
                RiskEvent::RecoveryApproved,
                RiskInitiator::RiskGovernor,
                vec![],
                Some("admin"),
                "",
            )
            .unwrap_err();
        assert!(matches!(err, SmError::InitiatorNotAllowed { .. }));
        // But Operator can
        sm.de_escalate_to(RiskLevel::Defensive, "admin", "resolved")
            .unwrap();
        assert_eq!(sm.level, RiskLevel::Defensive);
    }

    // ── Phase 6: Reconciler auto-contraction tests ──

    #[test]
    fn test_reconciler_escalate_to_cautious() {
        let mut sm = RiskGovernorSm::new();
        sm.reconciler_escalate_to(RiskLevel::Cautious, "major_drift: BTCUSDT|Buy")
            .unwrap();
        assert_eq!(sm.level, RiskLevel::Cautious);
        assert_eq!(sm.consecutive_escalations, 1);
        let rec = &sm.transitions[0];
        assert_eq!(rec.initiator, "Reconciler");
        assert_eq!(rec.event, "reconciler_drift");
    }

    #[test]
    fn test_reconciler_escalate_to_circuit_breaker() {
        let mut sm = RiskGovernorSm::new();
        sm.reconciler_escalate_to(RiskLevel::CircuitBreaker, "5+ simultaneous drifts")
            .unwrap();
        assert_eq!(sm.level, RiskLevel::CircuitBreaker);
    }

    #[test]
    fn test_reconciler_de_escalate_cautious_to_normal() {
        let mut sm = RiskGovernorSm::new();
        sm.thresholds.min_hold_time_ms = 0;
        sm.reconciler_escalate_to(RiskLevel::Cautious, "drift").unwrap();
        sm.reconciler_de_escalate_to(RiskLevel::Normal, "30 clean cycles")
            .unwrap();
        assert_eq!(sm.level, RiskLevel::Normal);
    }

    #[test]
    fn test_reconciler_cannot_de_escalate_from_cb() {
        // Reconciler should NOT be able to auto-recover from CircuitBreaker.
        // CB de-escalation is OP_ONLY. Reconciler is in OP_GOV but CB→Defensive
        // path is restricted to OP_ONLY.
        // 對帳器不能從 CB 自動恢復。CB 降級限 operator-only。
        let mut sm = RiskGovernorSm::new();
        sm.thresholds.min_hold_time_ms = 0;
        sm.reconciler_escalate_to(RiskLevel::CircuitBreaker, "drift storm")
            .unwrap();
        let err = sm
            .reconciler_de_escalate_to(RiskLevel::Defensive, "clean cycles")
            .unwrap_err();
        assert!(matches!(err, SmError::InitiatorNotAllowed { .. }));
    }

    #[test]
    fn test_reconciler_rest_failure_escalation() {
        let mut sm = RiskGovernorSm::new();
        sm.transition(
            RiskLevel::Cautious,
            RiskEvent::ReconcilerRestFailure,
            RiskInitiator::Reconciler,
            vec!["rest_failure_streak".into()],
            None,
            "10 consecutive REST failures",
        )
        .unwrap();
        assert_eq!(sm.level, RiskLevel::Cautious);
    }
}
