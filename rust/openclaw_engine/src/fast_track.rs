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

/// Fast track decision based on risk level and held-position drop signals.
///
/// Inputs:
/// - `risk_level`: governance-computed risk level
/// - `held_drop_pct`: worst peak-to-current drop **only among held symbols**
///   (0.0 when no positions or no drops). Sourced from
///   `PriceHistoryTracker::worst_drop_for_held`. Was formerly a global
///   cross-symbol scan — see FA-PHANTOM-2 note below.
/// - `held_drop_sigma`: the same drop's deviation from window mean in std-dev
///   units. Separates real outlier events (high sigma) from normal microcap
///   volatility (low sigma on a large absolute move).
/// - `margin_utilization_pct`: leverage-aware margin usage (post FA-PHANTOM-1).
///
/// 基於風控等級與持倉幣種跌幅信號的快速通道決策。
pub fn evaluate_fast_track(
    risk_level: RiskLevel,
    held_drop_pct: f64,
    held_drop_sigma: f64,
    margin_utilization_pct: f64,
) -> FastTrackAction {
    // 1. Circuit Breaker / ManualReview → close everything
    //    governance already decided; execution just carries it out.
    if risk_level >= RiskLevel::CircuitBreaker {
        return FastTrackAction::CloseAll;
    }

    // 2. Margin crisis: physical MMR proximity safety (leverage-aware)
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

    // 3. Extreme drop on a held symbol — true flash crash, any risk level.
    //    15% in a 5-min window is categorically flash-crash territory and
    //    worth closing even if sigma is uninformative (thin samples / stable
    //    symbol with std_dev ≈ 0 / edge cases).
    //    持倉幣種極端跌幅（≥15%）→ 真閃崩，任何風控等級下 CloseAll，
    //    不依賴 sigma（薄樣本/穩定幣 std≈0 等邊緣情境的兜底）。
    if held_drop_pct >= 15.0 {
        return FastTrackAction::CloseAll;
    }

    // 4. Moderate drop (≥5%) that is also a statistical outlier (≥3σ) on a
    //    held symbol:
    //      - risk_level ≥ Defensive → CloseAll (escalated defense)
    //      - risk_level <  Defensive → ReduceToHalf (precaution, not panic)
    //    FA-PHANTOM-2 fix (2026-04-15): the legacy rule fired CloseAll on
    //    any 5% drop at any risk level, scanning ALL observed symbols. With
    //    25+ microcaps in the pool, 5% window moves are routine noise and
    //    triggered CloseAll against every strategy at roughly every tick —
    //    blocking G-2 funding_arb validation (0/20 fills in 7h, 2026-04-15).
    //    FA-PHANTOM-2 修復：原規則任一小幣抖 5% 就 CloseAll，誤殺全策略。
    //    改為持倉幣種 + 5%+3σ 雙條件 + 依風控等級分級升級。
    if held_drop_pct >= 5.0 && held_drop_sigma >= 3.0 {
        if risk_level >= RiskLevel::Defensive {
            return FastTrackAction::CloseAll;
        }
        return FastTrackAction::ReduceToHalf;
    }

    // 5. Risk-level fallbacks (unchanged from pre-FA-PHANTOM-2)
    if risk_level >= RiskLevel::Defensive {
        return FastTrackAction::ReduceToHalf;
    }

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
            evaluate_fast_track(RiskLevel::Normal, 0.5, 0.2, 30.0),
            FastTrackAction::NoAction
        );
    }

    #[test]
    fn test_cautious_no_action() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::Cautious, 1.0, 0.5, 40.0),
            FastTrackAction::NoAction
        );
    }

    #[test]
    fn test_reduced_pauses_entries() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::Reduced, 1.0, 0.5, 40.0),
            FastTrackAction::PauseNewEntries
        );
    }

    #[test]
    fn test_defensive_reduces() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::Defensive, 1.0, 0.5, 40.0),
            FastTrackAction::ReduceToHalf
        );
    }

    #[test]
    fn test_circuit_breaker_closes_all() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::CircuitBreaker, 0.0, 0.0, 0.0),
            FastTrackAction::CloseAll
        );
    }

    #[test]
    fn test_manual_review_closes_all() {
        assert_eq!(
            evaluate_fast_track(RiskLevel::ManualReview, 0.0, 0.0, 0.0),
            FastTrackAction::CloseAll
        );
    }

    #[test]
    fn test_margin_crisis_closes_all() {
        // Post FA-PHANTOM-1: margin_utilization_pct is now LEVERAGE-AWARE
        // (margin_used / balance × 100), not raw notional / balance. A true
        // 95% margin utilization remains a crisis and still fires CloseAll.
        assert_eq!(
            evaluate_fast_track(RiskLevel::Cautious, 1.0, 0.5, 95.0),
            FastTrackAction::CloseAll
        );
    }

    #[test]
    fn test_fa_phantom_1_regression_full_notional_no_action() {
        // FA-PHANTOM-1 regression: a ledger filled to 100% notional exposure
        // at the default 20x leverage cap yields a true margin utilization
        // of only 5% — fast_track MUST NOT fire CloseAll.
        // FA-PHANTOM-1 回歸測試：20x leverage 下 notional 達 100%（= margin 5%）
        // fast_track 不得誤觸 CloseAll。
        let true_margin_util_pct = 5.0; // = 100% notional / 20x leverage
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 1.0, 0.5, true_margin_util_pct),
            FastTrackAction::NoAction
        );
    }

    // ═══════════════════════════════════════════════════════════════════════
    // FA-PHANTOM-2 regression: held-symbol drop + sigma gating + level-aware
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_fa_phantom_2_regression_microcap_noise_no_action() {
        // FA-PHANTOM-2 regression: a 6% drop on a held symbol at Normal risk
        // with sigma < 3 (i.e., consistent with that symbol's usual
        // volatility) MUST NOT fire CloseAll or even ReduceToHalf.
        // Pre-fix, ANY 5%+ drop triggered CloseAll regardless of risk level
        // or whether the drop was statistically exceptional.
        // FA-PHANTOM-2 回歸：持倉小幣 6% 跌 + Normal + sigma<3（正常波動）
        // 絕不可觸發 CloseAll 或 ReduceToHalf。
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 6.0, 1.5, 20.0),
            FastTrackAction::NoAction
        );
    }

    #[test]
    fn test_held_drop_outlier_normal_reduces_to_half() {
        // True outlier drop (8%, 4σ) on held symbol at Normal → ReduceToHalf
        // (precaution), not CloseAll (panic).
        // 真離群跌幅（8%、4σ）在 Normal 等級 → 半倉，不是全平。
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 8.0, 4.0, 20.0),
            FastTrackAction::ReduceToHalf
        );
    }

    #[test]
    fn test_held_drop_outlier_cautious_reduces_to_half() {
        // Cautious is still below Defensive → outlier drop → ReduceToHalf
        assert_eq!(
            evaluate_fast_track(RiskLevel::Cautious, 8.0, 4.0, 20.0),
            FastTrackAction::ReduceToHalf
        );
    }

    #[test]
    fn test_held_drop_outlier_defensive_closes_all() {
        // At Defensive or higher, a 5%+3σ held-symbol drop escalates to
        // CloseAll (existing Defensive regime plus fresh flash-crash signal).
        assert_eq!(
            evaluate_fast_track(RiskLevel::Defensive, 8.0, 4.0, 20.0),
            FastTrackAction::CloseAll
        );
    }

    #[test]
    fn test_held_drop_threshold_boundary_under_5pct() {
        // Just below the 5% gate → no drop-triggered action
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 4.99, 5.0, 20.0),
            FastTrackAction::NoAction
        );
    }

    #[test]
    fn test_held_drop_threshold_boundary_under_3_sigma() {
        // 5%+ drop but sigma just below 3 → not an outlier, NoAction at Normal
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 10.0, 2.99, 20.0),
            FastTrackAction::NoAction
        );
    }

    #[test]
    fn test_extreme_drop_closes_all_regardless_of_sigma() {
        // 15% drop is categorically a flash crash — close even if sigma is
        // uninformative (thin samples, stable history, std≈0).
        // 15% 為閃崩兜底，sigma 不可用時仍要 CloseAll。
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 15.0, 0.5, 20.0),
            FastTrackAction::CloseAll
        );
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 20.0, 0.0, 20.0),
            FastTrackAction::CloseAll
        );
    }

    #[test]
    fn test_extreme_drop_below_threshold_gated_by_sigma() {
        // 14.99% drop (just below the extreme-cliff) needs sigma≥3 to fire
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 14.99, 2.0, 20.0),
            FastTrackAction::NoAction
        );
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 14.99, 5.0, 20.0),
            FastTrackAction::ReduceToHalf
        );
    }

    #[test]
    fn test_defensive_without_drop_still_reduces() {
        // Defensive with no drop input → existing ReduceToHalf behavior
        assert_eq!(
            evaluate_fast_track(RiskLevel::Defensive, 0.0, 0.0, 20.0),
            FastTrackAction::ReduceToHalf
        );
    }

    #[test]
    fn test_no_held_drop_signal_uses_risk_level_only() {
        // Empty held_drop input (0.0, 0.0) at various risk levels falls
        // through to the risk-level ladder unchanged.
        // 持倉跌幅訊號為空時僅依風控等級判斷。
        assert_eq!(
            evaluate_fast_track(RiskLevel::Normal, 0.0, 0.0, 30.0),
            FastTrackAction::NoAction
        );
        assert_eq!(
            evaluate_fast_track(RiskLevel::Reduced, 0.0, 0.0, 30.0),
            FastTrackAction::PauseNewEntries
        );
        assert_eq!(
            evaluate_fast_track(RiskLevel::Defensive, 0.0, 0.0, 30.0),
            FastTrackAction::ReduceToHalf
        );
    }
}
