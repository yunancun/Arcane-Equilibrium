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
    //
    // 90% 是 Bybit 交易所強平接近度（MMR ≈ 100% 觸發強平），屬物理常數，
    // **不可 auto-scale 到 leverage_max / total_exposure_max_pct**。
    // margin_utilization_pct 本身已在 on_tick 計算時除以 leverage（post
    // FA-PHANTOM-1 fix 2026-04-14），是 leverage-aware 的真·保證金使用率；
    // 閾值保持絕對值才有「Guardian/risk envelope 被繞過 → 起碼別被交易所強平」
    // 的獨立兜底意義。
    //
    // Under current config (leverage_max=100, total_exposure_max_pct=200):
    //   max margin_util = 200% / 100 = 2% ≪ 90% → check never fires.
    // This is INTENTIONAL — it's a cash/near-cash mode fail-safe (leverage ≤ 2),
    // not a protection for the current high-leverage regime. Do NOT "fix" by
    // lowering the threshold — that re-opens FA-PHANTOM-1 class false-positive
    // CloseAll on legitimate stacking under position_size_max_pct=50%.
    // 見 docs/references/2026-04-14--fa_phantom_fup7_margin_threshold_decision.md
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
        // Post FA-PHANTOM-1: margin_utilization_pct is now LEVERAGE-AWARE
        // (margin_used / balance × 100), not raw notional / balance. A true
        // 95% margin utilization — ie. margin_used is 95% of balance —
        // remains a crisis and still fires CloseAll.
        // FA-PHANTOM-1 修復後：margin_utilization_pct 已 leverage-aware
        // （margin_used / balance × 100），非原始 notional / balance。95%
        // 真實 margin 使用率仍為危機，CloseAll 照觸發。
        assert_eq!(
            evaluate_fast_track(RiskLevel::Cautious, 1.0, 95.0),
            FastTrackAction::CloseAll
        );
    }

    #[test]
    fn test_fa_phantom_1_regression_full_notional_no_action() {
        // FA-PHANTOM-1 regression: a ledger filled to 100% notional exposure
        // at the default 20x leverage cap should yield a true margin
        // utilization of only 5% — fast_track MUST NOT fire CloseAll.
        // Pre-fix, this scenario fired CloseAll every tick once positions
        // stacked to ~100% notional/balance, force-closing all strategies
        // (including funding_arb, whose G-2 paper validation was blocked
        // by exactly this phantom-fill cycle).
        // FA-PHANTOM-1 回歸測試：20x leverage 下 notional 達 100%（= margin 5%）
        // fast_track 不得誤觸 CloseAll。
        let true_margin_util_pct = 5.0; // = 100% notional / 20x leverage
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 1.0, true_margin_util_pct),
            FastTrackAction::NoAction
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
