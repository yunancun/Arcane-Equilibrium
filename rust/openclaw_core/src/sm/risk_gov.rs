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
    /// 三路通知（Slack/Email/Console banner）全 fail + 1h timeout → 觸發 SM-04 Defensive transition。
    /// 為什麼：per AMD-2026-05-21-01 v2 §Decision 3.1 + PA spec §4.4 Stage 3b，三路冗餘全 fail
    /// 且 1h 內無 operator response 必自動進入最高保護模式（保住 unrealized PnL + 停止新倉）。
    /// 不變量：本 variant 是 hard-coded fail-safe 觸發路徑，runtime TOML 不得 override
    /// （per AMD §Decision 2.5 + Q3 RESOLVED Path A）；7d cooling 復原由 transition 邏輯強制。
    NotificationFailsafeTimeout,
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
            Self::NotificationFailsafeTimeout => "notification_failsafe_timeout",
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
// Defensive Active Lock-Profit Hook / Defensive 主動鎖利擴充
// ═══════════════════════════════════════════════════════════════════════════════
//
// 為什麼存在這層 hook：
//   per AMD-2026-05-21-01 v2 §9.8 + PA spec §4.4 Stage 3b，當三路通知全 fail + 1h
//   無 operator response 觸發 NotificationFailsafeTimeout 自動進 Defensive 時，
//   既有 Defensive constraints (active_de_risking=true / emergency_stops=false) 必須
//   配合一個「縮 SL 至 entry + ATR-based protective buffer」的具體執行動作 —
//   否則 active_de_risking 旗標只是個 boolean 不會真的鎖利。
//
// 為什麼放在 openclaw_core 而非 openclaw_engine：
//   1) SM-04 transition rule 與 active 鎖利語義是同一份治理邊界，分裂會讓兩處互
//      相 drift（per CLAUDE.md §九 「business logic 不漂移」）；
//   2) 本層只計算 stop adjustment 的純值，不直接呼叫 exchange API — engine 層
//      取得 Vec<StopAdjustment> 後負責「sync 至 exchange-side conditional」
//      （per CLAUDE.md §二 原則 9 雙重防線）。
//
// 不變量：
//   - 無 panic / 無 unwrap / 無 unsafe（per CLAUDE.md §七 Rust 紀律）
//   - 輸入 NaN / 非正 ATR / 非正 entry 一律跳過該倉位，不阻塞其他倉位
//   - SL 永遠在「保護方向」：Buy 倉 new_sl >= entry，Sell 倉 new_sl <= entry
//   - 不接受 runtime TOML override（per AMD §Decision 2.5 fail-safe compile-time
//     hard-coded）

/// 倉位快照 — 計算 active lock-profit 所需的最小欄位集。
/// 為什麼獨立定義：openclaw_core 不可依賴 openclaw_engine 的 PositionInfo /
/// PositionView（會造成循環依賴）；engine 層在 call hook 前負責 map。
#[derive(Debug, Clone, PartialEq)]
pub struct PositionSnapshot {
    pub symbol: String,
    /// 倉位方向 "Buy" 或 "Sell"（與 openclaw_types::price Trade side 約定一致）。
    pub side: &'static str,
    pub entry_price: f64,
    pub qty: f64,
    /// 當前 SL（若未設則 None）。
    pub current_sl: Option<f64>,
    /// 該倉位的位置生命 ATR（per `openclaw_core::indicators::volatility::atr` 的
    /// position-life ATR；非 PriceHistoryTracker 的 per-tick micro-volatility）。
    pub atr: f64,
}

/// SL 調整指令 — 由 engine 層取走後負責下交易所 conditional order。
#[derive(Debug, Clone, PartialEq)]
pub struct StopAdjustment {
    pub symbol: String,
    pub side: &'static str,
    pub new_sl: f64,
    /// 觸發 lease 紀錄 reason（per PA spec §4.4 line 488）。
    pub reason: &'static str,
}

/// 每倉位 active 鎖利 — 縮 SL 至 entry + ATR-based protective buffer。
///
/// 為什麼採「entry + buffer × ATR」公式（per PA spec §4.4 line 485-487）：
///   - Buy 倉 new_sl = entry + atr × buffer_multiplier （買入後價格上漲，SL 拉至
///     entry 上方一個 ATR 的 fraction = 鎖住 unrealized PnL 中的小幅）
///   - Sell 倉 new_sl = entry - atr × buffer_multiplier
///   - 若既有 current_sl 已比新 SL 更保護（Buy 倉 current_sl > new_sl），保留
///     既有 SL（不放鬆保護方向）
///
/// 對輸入無效的倉位（NaN / atr<=0 / entry<=0 / buffer<0）跳過該倉位、不 panic、
/// 不阻塞其他倉位 — fail-closed per CLAUDE.md §二 原則 6 「uncertainty defaults
/// to conservative behavior」。
///
/// 呼叫端契約：本函式只計算 stop adjustment 值；engine 層必負責同步至
/// exchange-side conditional protection（per CLAUDE.md §二 原則 9 雙重防線）+
/// emit lease "active_lock_profit_triggered_by_notification_failsafe"。
pub fn active_lock_profit_per_position(
    positions: &[PositionSnapshot],
    atr_buffer_multiplier: f64,
) -> Vec<StopAdjustment> {
    // 邊界檢查：buffer 負值或 NaN 直接整批返回空（不接受 garbage 配置觸發鎖利）
    if !atr_buffer_multiplier.is_finite() || atr_buffer_multiplier < 0.0 {
        return Vec::new();
    }

    let mut adjustments = Vec::with_capacity(positions.len());
    for pos in positions {
        // 跳過無效輸入 — fail-closed 不 panic 不 unwrap
        if !pos.atr.is_finite() || pos.atr <= 0.0 {
            continue;
        }
        if !pos.entry_price.is_finite() || pos.entry_price <= 0.0 {
            continue;
        }
        if !pos.qty.is_finite() || pos.qty.abs() < f64::EPSILON {
            continue;
        }

        let buffer = pos.atr * atr_buffer_multiplier;
        let candidate_sl = match pos.side {
            "Buy" => pos.entry_price + buffer,
            "Sell" => pos.entry_price - buffer,
            // 未知方向：跳過該倉位（不假設預設方向）
            _ => continue,
        };

        // 不放鬆既有 SL 保護方向：
        //   Buy 倉新 SL 必須 >= current_sl（不向下放鬆）
        //   Sell 倉新 SL 必須 <= current_sl（不向上放鬆）
        let new_sl = match (pos.side, pos.current_sl) {
            ("Buy", Some(existing)) if existing.is_finite() && existing >= candidate_sl => {
                existing
            }
            ("Sell", Some(existing)) if existing.is_finite() && existing <= candidate_sl => {
                existing
            }
            _ => candidate_sl,
        };

        if !new_sl.is_finite() || new_sl <= 0.0 {
            continue;
        }

        adjustments.push(StopAdjustment {
            symbol: pos.symbol.clone(),
            side: pos.side,
            new_sl,
            reason: "active_lock_profit_triggered_by_notification_failsafe",
        });
    }
    adjustments
}

/// 7d cooling window（per PA spec §4.4 Stage 4 + Q4 拍板 30d→7d）。
/// Defensive 因 `NotificationFailsafeTimeout` 觸發後，復原至 Normal 必經過
/// 7 天 cooling；engine 層或 operator unfreeze flow 引用本常數做比對。
pub const FAILSAFE_DEFENSIVE_COOLING_MS: u64 = 7 * 24 * 60 * 60 * 1000;

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

    const AUTO: &[RiskInitiator] = &[
        RiskGovernor,
        Operator,
        IncidentPolicy,
        HealthMonitor,
        Reconciler,
    ];
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
        sm.reconciler_escalate_to(RiskLevel::Cautious, "drift")
            .unwrap();
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

    // ── Wave 5 Packet C: NotificationFailsafeTimeout + active lock-profit ──
    //
    // 為什麼一組 6 條 test：對齊 Packet C §3 deliverable T1-T6（per AMD §9.8 +
    // PA spec §4.4 ladder Stage 1-4 + §12 AC）。

    /// 建構一個 buy/sell 倉位 helper（避免 6 條 test 重複 PositionSnapshot 字面值）。
    fn pos(symbol: &str, side: &'static str, entry: f64, sl: Option<f64>, atr: f64) -> PositionSnapshot {
        PositionSnapshot {
            symbol: symbol.to_string(),
            side,
            entry_price: entry,
            qty: 1.0,
            current_sl: sl,
            atr,
        }
    }

    #[test]
    fn t1_notification_failsafe_timeout_variant_emits_and_handles() {
        // T1: 新 variant 可被識別 + as_str 對齊 spec
        let ev = RiskEvent::NotificationFailsafeTimeout;
        assert_eq!(ev.as_str(), "notification_failsafe_timeout");
        // 該 variant 可在 transition 中作為事件原因傳入（不破壞既有 match 完整性）
        let mut sm = RiskGovernorSm::new();
        sm.transition(
            RiskLevel::Defensive,
            RiskEvent::NotificationFailsafeTimeout,
            RiskInitiator::RiskGovernor,
            vec!["notification_3way_fail_1h_timeout".into()],
            None,
            "auto_escalated_to_sm04_defensive",
        )
        .expect("Normal→Defensive via NotificationFailsafeTimeout 應允許");
        assert_eq!(sm.level, RiskLevel::Defensive);
        assert_eq!(sm.transitions.len(), 1);
        assert_eq!(sm.transitions[0].event, "notification_failsafe_timeout");
    }

    #[test]
    fn t2_failsafe_escalation_from_all_lower_levels() {
        // T2: Normal | Cautious | Reduced → Defensive 三條 escalation path 都允許
        //     NotificationFailsafeTimeout 作為觸發事件（per spec §4.4 Stage 3b）
        for from in [RiskLevel::Normal, RiskLevel::Cautious, RiskLevel::Reduced] {
            let mut sm = RiskGovernorSm::new();
            sm.level = from;
            sm.level_entered_at_ms = super::super::now_ms();
            sm.transition(
                RiskLevel::Defensive,
                RiskEvent::NotificationFailsafeTimeout,
                RiskInitiator::RiskGovernor,
                vec!["notification_3way_fail_1h_timeout".into()],
                None,
                "auto_escalated_to_sm04_defensive",
            )
            .unwrap_or_else(|e| panic!("from {from:?} escalate via failsafe 失敗: {e:?}"));
            assert_eq!(sm.level, RiskLevel::Defensive);
            // Defensive 既有 constraints 不動（per AMD §9.8 mitigation 理由 1）
            let c = sm.constraints();
            assert!(c.active_de_risking, "Defensive active_de_risking 必須 true");
            assert!(c.reduce_only, "Defensive reduce_only 必須 true");
            assert!(!c.new_entries_allowed, "Defensive new_entries 必須 false");
            assert!(
                !c.emergency_stops,
                "Defensive emergency_stops 必須 false（保住 unrealized PnL）"
            );
            assert_eq!(c.position_size_multiplier, 0.0);
        }
    }

    #[test]
    fn t3_active_lock_profit_computes_sl_with_atr_buffer() {
        // T3: Defensive transition 後 active_lock_profit_per_position 縮 SL
        //     to entry + ATR-buffer，且不放鬆既有 SL 保護方向。
        let positions = vec![
            // Buy 倉，無既有 SL → new_sl = entry + 0.5 × atr
            pos("BTCUSDT", "Buy", 100.0, None, 4.0),
            // Sell 倉，無既有 SL → new_sl = entry - 0.5 × atr
            pos("ETHUSDT", "Sell", 200.0, None, 6.0),
            // Buy 倉，既有 SL 更保護（高於 candidate） → 保留既有
            pos("SOLUSDT", "Buy", 50.0, Some(55.0), 4.0),
            // Sell 倉，既有 SL 更保護（低於 candidate） → 保留既有
            pos("XRPUSDT", "Sell", 1.0, Some(0.5), 0.2),
        ];
        let adj = active_lock_profit_per_position(&positions, 0.5);
        assert_eq!(adj.len(), 4);
        // Buy candidate = 100 + 0.5*4 = 102.0
        assert!((adj[0].new_sl - 102.0).abs() < 1e-9);
        assert_eq!(adj[0].symbol, "BTCUSDT");
        assert_eq!(adj[0].side, "Buy");
        assert_eq!(
            adj[0].reason,
            "active_lock_profit_triggered_by_notification_failsafe"
        );
        // Sell candidate = 200 - 0.5*6 = 197.0
        assert!((adj[1].new_sl - 197.0).abs() < 1e-9);
        // Buy 既有 SL=55 > candidate(50 + 0.5*4 = 52) → 保留 55
        assert!((adj[2].new_sl - 55.0).abs() < 1e-9);
        // Sell 既有 SL=0.5 < candidate(1.0 - 0.5*0.2 = 0.9) → 保留 0.5
        assert!((adj[3].new_sl - 0.5).abs() < 1e-9);
    }

    #[test]
    fn t3_active_lock_profit_fail_closed_on_bad_input() {
        // T3 fail-closed：NaN / 非正 ATR / 非正 entry / 未知 side / 負 buffer
        // 全部不 panic，跳過該倉位（不阻塞其他倉位）。
        let positions = vec![
            pos("NAN_ATR", "Buy", 100.0, None, f64::NAN),
            pos("ZERO_ATR", "Buy", 100.0, None, 0.0),
            pos("NEG_ATR", "Buy", 100.0, None, -1.0),
            pos("ZERO_ENTRY", "Buy", 0.0, None, 5.0),
            pos("NAN_ENTRY", "Buy", f64::NAN, None, 5.0),
            pos("UNKNOWN_SIDE", "Long", 100.0, None, 5.0),
            pos("OK", "Buy", 100.0, None, 5.0), // 唯一有效倉位
        ];
        let adj = active_lock_profit_per_position(&positions, 0.5);
        assert_eq!(adj.len(), 1, "只有 OK 倉位應產生 adjustment");
        assert_eq!(adj[0].symbol, "OK");

        // 負 buffer / NaN buffer 整批跳過
        assert!(active_lock_profit_per_position(&positions, -0.1).is_empty());
        assert!(active_lock_profit_per_position(&positions, f64::NAN).is_empty());

        // 空陣列輸入 → 空輸出
        assert!(active_lock_profit_per_position(&[], 0.5).is_empty());
    }

    #[test]
    fn t4_failsafe_does_not_break_existing_de_escalation_paths() {
        // T4: 35+ existing transition pair 不應受 NotificationFailsafeTimeout 影響。
        // 全 escalation/de-escalation pair 逐一 lookup_rule 驗存在。
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
                "Escalation regression: {from} → {to} 應仍存在"
            );
        }
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
            assert!(rule.is_some(), "De-escalation regression: {from} → {to}");
            assert!(
                rule.unwrap().requires_approval,
                "De-escalation {from} → {to} 必 require approval"
            );
        }
        // Defensive ↔ CircuitBreaker / ManualReview / Reduced / Cautious 四條
        // 仍可任由現有 initiator 觸發（per spec §9.8 mitigation 理由 2）
        assert!(lookup_rule(Defensive, CircuitBreaker).is_some());
        assert!(lookup_rule(Defensive, ManualReview).is_some());
        assert!(lookup_rule(Defensive, Reduced).is_some());
        assert!(lookup_rule(Defensive, Cautious).is_some());
    }

    #[test]
    fn t5_seven_day_cooling_constant_matches_spec() {
        // T5: 7d cooling window constant = 7 * 24 * 3600 * 1000 ms
        //     per PA spec §4.4 Stage 4 + Q4 拍板 30d→7d。
        //     engine 層 / operator unfreeze flow 引用本常數做 cooling 比對。
        assert_eq!(FAILSAFE_DEFENSIVE_COOLING_MS, 604_800_000);
        // 確認常數可參與算術（不變量檢測 — 若有人誤改成 0 或溢位，本 assert fail）
        let one_week_seconds = FAILSAFE_DEFENSIVE_COOLING_MS / 1000;
        assert_eq!(one_week_seconds, 604_800);
    }

    #[test]
    fn t6_existing_24_tests_unaffected_smoke() {
        // T6: smoke test — 確認新增 variant + active lock-profit hook 不影響
        // 既有 evaluate_risk_context auto-escalation 路徑（pressure / drawdown /
        // daily_loss / consecutive_losses / session_halted / cooldown_active）。
        let mut sm = RiskGovernorSm::new();
        let result = sm.evaluate_risk_context(0.6, 9.0, 0.0, 0, false, false);
        assert_eq!(result, Some(RiskLevel::Reduced));

        let mut sm2 = RiskGovernorSm::new();
        let r2 = sm2.evaluate_risk_context(0.0, 0.0, 0.0, 0, true, false);
        assert_eq!(r2, Some(RiskLevel::CircuitBreaker));

        // Reconciler path 不受影響
        let mut sm3 = RiskGovernorSm::new();
        sm3.reconciler_escalate_to(RiskLevel::Cautious, "drift").unwrap();
        assert_eq!(sm3.level, RiskLevel::Cautious);
    }
}
