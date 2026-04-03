//! Fast Track — emergency execution path (R04-3).
//! 快速通道 — 緊急執行路徑。
//!
//! Risk ≥ DEFENSIVE → predefined rules execute immediately.
//! 風控 ≥ DEFENSIVE → 預定義規則立即執行。
//! Flash crash / margin crisis → immediate close all.
//! 閃崩/保證金危機 → 立即全平。

use openclaw_core::sm::risk_gov::RiskLevel;
use serde::{Deserialize, Serialize};

/// Fast track action type.
/// 快速通道動作類型。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum FastTrackAction {
    CloseAll,
    ReduceToHalf,
    PauseNewEntries,
    NoAction,
}

/// Fast track decision based on risk level and conditions.
/// 基於風控等級和條件的快速通道決策。
pub fn evaluate_fast_track(
    risk_level: RiskLevel,
    price_drop_pct: f64,
    margin_utilization_pct: f64,
) -> FastTrackAction {
    // Circuit Breaker or Manual Review → close everything
    if risk_level >= RiskLevel::CircuitBreaker {
        return FastTrackAction::CloseAll;
    }

    // Flash crash detection: >5% drop in short time
    if price_drop_pct >= 5.0 {
        return FastTrackAction::CloseAll;
    }

    // Margin crisis: >90% utilization
    if margin_utilization_pct >= 90.0 {
        return FastTrackAction::CloseAll;
    }

    // Defensive mode → reduce exposure
    if risk_level >= RiskLevel::Defensive {
        return FastTrackAction::ReduceToHalf;
    }

    // Reduced mode → no new entries
    if risk_level >= RiskLevel::Reduced {
        return FastTrackAction::PauseNewEntries;
    }

    FastTrackAction::NoAction
}

/// Fast track result with details.
/// 快速通道結果含詳情。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FastTrackResult {
    pub action: FastTrackAction,
    pub positions_closed: usize,
    pub reason: String,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_normal_no_action() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 0.5, 30.0),
            FastTrackAction::NoAction
        );
    }

    #[test]
    fn test_cautious_no_action() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::Cautious, 1.0, 40.0),
            FastTrackAction::NoAction
        );
    }

    #[test]
    fn test_reduced_pauses_entries() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::Reduced, 1.0, 40.0),
            FastTrackAction::PauseNewEntries
        );
    }

    #[test]
    fn test_defensive_reduces() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::Defensive, 1.0, 40.0),
            FastTrackAction::ReduceToHalf
        );
    }

    #[test]
    fn test_circuit_breaker_closes_all() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::CircuitBreaker, 0.0, 0.0),
            FastTrackAction::CloseAll
        );
    }

    #[test]
    fn test_flash_crash_closes_all() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 6.0, 20.0),
            FastTrackAction::CloseAll
        );
    }

    #[test]
    fn test_margin_crisis_closes_all() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::Cautious, 1.0, 95.0),
            FastTrackAction::CloseAll
        );
    }

    #[test]
    fn test_manual_review_closes_all() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::ManualReview, 0.0, 0.0),
            FastTrackAction::CloseAll
        );
    }
}
