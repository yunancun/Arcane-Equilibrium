//! Monotone rearrangement — enforce q10 ≤ q50 ≤ q90 post-inference.
//! 單調重排 — 強制 q10 ≤ q50 ≤ q90。
//!
//! MODULE_NOTE (EN): Quantile crossing (q10 > q50 or q50 > q90) can happen
//!   with independent per-quantile LGBM models even after CQR calibration.
//!   Spec §7.3 Step 5 mandates a deterministic monotone fix before gate
//!   logic consumes the prediction. This module implements the simplest
//!   provably-idempotent approach: sort the three values ascending.
//!   An alternative (median-preserving) clamps only the offending endpoints;
//!   we intentionally use the simpler sort to avoid asymmetric bias.
//! MODULE_NOTE (中): 雖然 CQR 校準後，獨立的 per-quantile LGBM 仍可能產生
//!   quantile crossing。規格 §7.3 Step 5 要求確定性單調修正。本模組採最簡單
//!   且冪等的實現：三值升序排序。
//!
//! Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4 §7.3 Step 5

use super::Prediction;

/// Enforce monotone ordering on three quantile outputs.
/// Returns a new `Prediction` with (q10, q50, q90) in ascending order.
/// 強制三分位單調升序，返回新的 `Prediction`。
pub fn enforce_monotone(p: Prediction) -> Prediction {
    let mut arr = [p.q10, p.q50, p.q90];
    arr.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    Prediction {
        q10: arr[0],
        q50: arr[1],
        q90: arr[2],
    }
}

/// Count quantile-crossing violations in a prediction (0..=2).
/// Useful for emitting the `quantile_crossing_rate` metric without mutation.
/// 計算預測中的 quantile-crossing 違規數（0..=2）。供指標上報用。
pub fn crossing_count(p: &Prediction) -> u8 {
    let mut n = 0u8;
    if p.q10 > p.q50 {
        n += 1;
    }
    if p.q50 > p.q90 {
        n += 1;
    }
    n
}

// ============================================================
// Tests
// ============================================================
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_enforce_monotone_already_ordered() {
        let p = Prediction { q10: -1.0, q50: 0.5, q90: 2.0 };
        let q = enforce_monotone(p);
        assert_eq!(q.q10, -1.0);
        assert_eq!(q.q50, 0.5);
        assert_eq!(q.q90, 2.0);
    }

    #[test]
    fn test_enforce_monotone_full_reverse() {
        let p = Prediction { q10: 5.0, q50: 3.0, q90: 1.0 };
        let q = enforce_monotone(p);
        assert_eq!(q.q10, 1.0);
        assert_eq!(q.q50, 3.0);
        assert_eq!(q.q90, 5.0);
    }

    #[test]
    fn test_enforce_monotone_q10_above_q50_only() {
        let p = Prediction { q10: 2.0, q50: 1.0, q90: 3.0 };
        let q = enforce_monotone(p);
        assert_eq!(q.q10, 1.0);
        assert_eq!(q.q50, 2.0);
        assert_eq!(q.q90, 3.0);
    }

    #[test]
    fn test_enforce_monotone_q50_above_q90_only() {
        let p = Prediction { q10: 1.0, q50: 5.0, q90: 3.0 };
        let q = enforce_monotone(p);
        assert_eq!(q.q10, 1.0);
        assert_eq!(q.q50, 3.0);
        assert_eq!(q.q90, 5.0);
    }

    #[test]
    fn test_enforce_monotone_all_equal() {
        let p = Prediction { q10: 4.0, q50: 4.0, q90: 4.0 };
        let q = enforce_monotone(p);
        assert_eq!(q.q10, 4.0);
        assert_eq!(q.q50, 4.0);
        assert_eq!(q.q90, 4.0);
    }

    #[test]
    fn test_enforce_monotone_is_idempotent() {
        let p = Prediction { q10: 10.0, q50: -5.0, q90: 2.0 };
        let q1 = enforce_monotone(p);
        let q2 = enforce_monotone(q1);
        assert_eq!(q1, q2);
        assert!(q1.is_valid());
    }

    #[test]
    fn test_enforce_monotone_nan_propagates_but_does_not_panic() {
        let p = Prediction { q10: 1.0, q50: f32::NAN, q90: 3.0 };
        // Should not panic; NaN compares Equal per our fallback.
        let q = enforce_monotone(p);
        // is_valid() should reject due to NaN.
        assert!(!q.is_valid());
    }

    #[test]
    fn test_crossing_count_none() {
        assert_eq!(crossing_count(&Prediction { q10: 0.0, q50: 1.0, q90: 2.0 }), 0);
    }

    #[test]
    fn test_crossing_count_q10_q50() {
        // q10=5>q50=1 (cross #1), q50=1<q90=2 (no cross) → 1
        assert_eq!(crossing_count(&Prediction { q10: 5.0, q50: 1.0, q90: 2.0 }), 1);
        // q10=3>q50=2 (cross #1), q50=2<q90=4 (no cross) → 1
        assert_eq!(crossing_count(&Prediction { q10: 3.0, q50: 2.0, q90: 4.0 }), 1);
    }

    #[test]
    fn test_crossing_count_q50_q90() {
        assert_eq!(crossing_count(&Prediction { q10: 0.0, q50: 5.0, q90: 2.0 }), 1);
    }

    #[test]
    fn test_crossing_count_both() {
        assert_eq!(crossing_count(&Prediction { q10: 10.0, q50: 5.0, q90: 1.0 }), 2);
    }

    #[test]
    fn test_enforce_then_is_valid() {
        // After enforce_monotone on finite values, is_valid() must return true.
        let p = Prediction { q10: 99.0, q50: -3.0, q90: 0.5 };
        let q = enforce_monotone(p);
        assert!(q.is_valid());
    }
}
