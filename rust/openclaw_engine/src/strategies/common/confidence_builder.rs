//! `ConfidenceBuilder` — ADX+regime confidence formula for trend-family strategies.
//! `ConfidenceBuilder` — 趨勢家族策略的 ADX+regime 信心值公式。
//!
//! MODULE_NOTE (EN): Extracted from `ma_crossover::compute_entry_confidence`
//!   (and close siblings in bb_breakout / bb_reversion trend paths) to centralize
//!   the formula:
//!
//!   ```text
//!   adx_bonus     = ((adx - adx_threshold).max(0.0) / adx_scale).min(adx_bonus_cap)
//!   regime_bonus' = +regime_bonus   if regime == Some("trending")
//!                 = -regime_bonus   if regime == Some("mean_reverting")
//!                 = 0.0             otherwise
//!   confidence    = (base + adx_bonus + regime_bonus').clamp(clamp_min, clamp_max)
//!   ```
//!
//!   **Bit-exact preservation mandate.** Callers must get `f64::to_bits()`-equal
//!   output compared to the pre-extraction code. To achieve this:
//!     * addition order is fixed as `(base + adx_bonus + regime_bonus).clamp(...)`
//!       — do NOT reorder or introduce intermediate variables.
//!     * default constants match ma_crossover's in-place values exactly:
//!       `adx_scale = 100.0`, `adx_bonus_cap = 0.25`, `clamp_min = 0.2`,
//!       `clamp_max = 0.9`.
//!     * callers that previously used different caps (e.g. `exit_conf` used
//!       `.min(0.2)` and `.clamp(0.4, 0.8)`) MUST construct via `with_bounds`
//!       rather than `new`, OR keep their ad-hoc local formula (we chose the
//!       latter for `compute_exit_confidence` since it's also `base + adx_bonus`
//!       with no regime term — there's no duplication to remove there).
//! MODULE_NOTE (中): 從 `ma_crossover::compute_entry_confidence`（及 bb_breakout /
//!   bb_reversion 趨勢路徑相似碼）抽離。公式詳見 EN。
//!
//!   **位元精確保留義務。** 呼叫端以 `f64::to_bits()` 比對必須與抽離前碼相同。
//!   加法順序鎖定為 `(base + adx_bonus + regime_bonus).clamp(...)`，不得重排或
//!   引入中間變數。預設常數與 ma_crossover 原碼完全一致：
//!   `adx_scale = 100.0, adx_bonus_cap = 0.25, clamp_min = 0.2, clamp_max = 0.9`。
//!   `exit_conf` 使用不同上下界（`.min(0.2)` / `.clamp(0.4, 0.8)` 且無 regime 項）
//!   可用 `with_bounds` 建構，或保留策略內部原公式（`compute_exit_confidence`
//!   無重複碼，此處選擇後者）。

/// ADX+regime 信心值計算器 / ADX+regime confidence calculator.
///
/// `base` / `adx_threshold` / `regime_bonus` 是策略特定的三個參數（由配置驅動）。
/// 其餘欄位為 ma_crossover 原碼的常數上下界，保留為 struct field 以便未來需要
/// 時可經 `with_bounds` 調整而不改公式。
#[derive(Debug, Clone, Copy)]
pub struct ConfidenceBuilder {
    base: f64,
    adx_threshold: f64,
    regime_bonus: f64,
    adx_scale: f64,
    adx_bonus_cap: f64,
    clamp_min: f64,
    clamp_max: f64,
}

impl ConfidenceBuilder {
    /// Construct with ma_crossover-style defaults:
    /// `adx_scale = 100.0, adx_bonus_cap = 0.25, clamp_min = 0.2, clamp_max = 0.9`.
    /// 以 ma_crossover 預設值建構。
    pub fn new(base: f64, adx_threshold: f64, regime_bonus: f64) -> Self {
        Self {
            base,
            adx_threshold,
            regime_bonus,
            adx_scale: 100.0,
            adx_bonus_cap: 0.25,
            clamp_min: 0.2,
            clamp_max: 0.9,
        }
    }

    /// Construct with custom bounds for callers whose original formula used
    /// different caps (kept for future migration of exit-conf paths).
    /// 以自訂上下界建構，供原 exit-conf 等不同邊界的路徑未來遷移使用。
    #[allow(dead_code)]
    pub fn with_bounds(
        base: f64,
        adx_threshold: f64,
        regime_bonus: f64,
        adx_scale: f64,
        adx_bonus_cap: f64,
        clamp_min: f64,
        clamp_max: f64,
    ) -> Self {
        Self {
            base,
            adx_threshold,
            regime_bonus,
            adx_scale,
            adx_bonus_cap,
            clamp_min,
            clamp_max,
        }
    }

    /// Compute the confidence in bit-exact parity with the pre-extraction
    /// `compute_entry_confidence`. Addition order (`base + adx_bonus +
    /// regime_bonus`) is load-bearing — do not refactor.
    /// 計算信心值，加法順序鎖定與抽離前碼位元相同。
    pub fn compute(&self, adx: f64, regime: Option<&str>) -> f64 {
        let adx_bonus = ((adx - self.adx_threshold).max(0.0) / self.adx_scale).min(self.adx_bonus_cap);
        let regime_bonus = match regime {
            Some("trending") => self.regime_bonus,
            Some("mean_reverting") => -self.regime_bonus,
            _ => 0.0,
        };
        (self.base + adx_bonus + regime_bonus).clamp(self.clamp_min, self.clamp_max)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Pre-extraction formula — reproduces ma_crossover::compute_entry_confidence
    /// with the same parameter shape. Used as the bit-exact oracle for the
    /// preservation test below.
    /// 抽離前公式——重建 ma_crossover 原碼，做為位元精確對照基準。
    fn oracle_entry_conf(
        adx: f64,
        regime: Option<&str>,
        base: f64,
        regime_bonus_param: f64,
        adx_threshold: f64,
    ) -> f64 {
        let adx_bonus = ((adx - adx_threshold).max(0.0) / 100.0).min(0.25);
        let regime_bonus = match regime {
            Some("trending") => regime_bonus_param,
            Some("mean_reverting") => -regime_bonus_param,
            _ => 0.0,
        };
        (base + adx_bonus + regime_bonus).clamp(0.2, 0.9)
    }

    #[test]
    fn test_bit_exact_matches_pre_extraction_trending() {
        // CRITICAL: this is the preservation test. If this fails, ma_crossover
        // migration will drift f64 bits.
        // 核心保留性測試：失敗則 ma_crossover 遷移必位元漂移。
        let cb = ConfidenceBuilder::new(0.45, 20.0, 0.15);
        let got = cb.compute(20.0, Some("trending"));
        let want = oracle_entry_conf(20.0, Some("trending"), 0.45, 0.15, 20.0);
        assert_eq!(
            got.to_bits(),
            want.to_bits(),
            "ConfidenceBuilder.compute must be f64-bit-identical to ma_crossover's inline formula"
        );
        // sanity: value is base + 0 + regime_bonus = 0.45 + 0 + 0.15 = 0.60
        // 健康檢查：base + 0 + regime_bonus = 0.60
        assert_eq!(got, 0.60);
    }

    #[test]
    fn test_bit_exact_sweeps_adx_and_regime_variants() {
        // Sweep representative (adx, regime, base, threshold, regime_bonus)
        // tuples to guard against drift at edge cases (below threshold, at cap,
        // above cap, negative adx_bonus-impossible branch).
        // 以代表性組合掃描，防止 threshold 以下 / cap 上下界 / 負 adx_bonus 分支漂移。
        let cases = [
            (10.0, Some("trending"), 0.45, 20.0, 0.15),     // adx < threshold
            (20.0, Some("trending"), 0.45, 20.0, 0.15),     // at threshold
            (45.0, Some("mean_reverting"), 0.45, 20.0, 0.15), // cap + penalty
            (80.0, Some("trending"), 0.45, 20.0, 0.15),     // well above cap
            (60.0, None, 0.45, 20.0, 0.15),                 // no regime
            (60.0, Some("ranging"), 0.45, 20.0, 0.15),      // unknown regime
            (35.0, Some("trending"), 0.50, 25.0, 0.20),     // alt params
        ];
        for (adx, regime, base, threshold, rb) in cases {
            let cb = ConfidenceBuilder::new(base, threshold, rb);
            let got = cb.compute(adx, regime);
            let want = oracle_entry_conf(adx, regime, base, rb, threshold);
            assert_eq!(
                got.to_bits(),
                want.to_bits(),
                "drift at adx={adx} regime={regime:?} base={base} thr={threshold} rb={rb}"
            );
        }
    }

    #[test]
    fn test_clamp_floor_holds_when_penalty_dominates() {
        // mean_reverting penalty + adx below threshold → forced to clamp_min=0.2.
        // mean_reverting 懲罰 + adx 低於門檻 → 被 clamp 到下界 0.2。
        let cb = ConfidenceBuilder::new(0.30, 50.0, 0.40);
        // adx_bonus = 0, regime_bonus = -0.40 → base+contribs = -0.10 → clamp → 0.2
        // adx_bonus = 0, regime_bonus = -0.40 → 合計 -0.10 → clamp 至 0.2
        assert_eq!(cb.compute(10.0, Some("mean_reverting")), 0.2);
    }

    #[test]
    fn test_clamp_ceiling_holds_when_all_bonuses_apply() {
        // High adx + trending + high base → clamp_max=0.9.
        // 高 adx + trending + 高 base → clamp 至 0.9。
        let cb = ConfidenceBuilder::new(0.80, 20.0, 0.15);
        // adx_bonus = min((120-20)/100, 0.25) = 0.25, regime = +0.15
        //   → 0.80 + 0.25 + 0.15 = 1.20 → clamp → 0.9
        // adx_bonus = 0.25, regime = +0.15 → 合計 1.20 → clamp 至 0.9
        assert_eq!(cb.compute(120.0, Some("trending")), 0.9);
    }

    #[test]
    fn test_adx_below_threshold_yields_zero_bonus() {
        // adx < threshold → (adx-thr).max(0.0) = 0 → adx_bonus = 0.
        // adx < threshold → 負值被 max 清零 → adx_bonus 為 0。
        let cb = ConfidenceBuilder::new(0.45, 30.0, 0.15);
        // adx=10 → adx_bonus=0, no regime → value = 0.45
        // adx=10 → adx_bonus=0，無 regime → 值為 0.45
        assert_eq!(cb.compute(10.0, None), 0.45);
    }

    #[test]
    fn test_unknown_regime_treated_as_none() {
        // Only "trending" and "mean_reverting" move the needle; any other
        // string falls through to 0.0 — matches ma_crossover's `_ => 0.0` arm.
        // 僅 "trending" 和 "mean_reverting" 生效，其他字串走 0.0 分支。
        let cb = ConfidenceBuilder::new(0.45, 20.0, 0.15);
        let a = cb.compute(50.0, Some("sideways"));
        let b = cb.compute(50.0, None);
        assert_eq!(a.to_bits(), b.to_bits());
    }

    #[test]
    fn test_with_bounds_respects_custom_caps() {
        // Custom bounds are used for potential exit-conf migration; ensure the
        // cap and clamp paths honor them rather than the `new` defaults.
        // 自訂上下界測試：確認 cap 與 clamp 走自訂值。
        // exit-conf style: base=0.5, adx_bonus_cap=0.2, clamp (0.4, 0.8), no regime.
        // exit-conf 風格：上下界 (0.4, 0.8)，adx_bonus_cap=0.2，無 regime。
        let cb = ConfidenceBuilder::with_bounds(0.5, 20.0, 0.0, 100.0, 0.2, 0.4, 0.8);
        // adx=120 → adx_bonus = min((120-20)/100, 0.2) = 0.2
        //   → 0.5 + 0.2 + 0.0 = 0.7 → within [0.4, 0.8] → 0.7
        assert_eq!(cb.compute(120.0, None), 0.7);
        // adx=10 → adx_bonus=0 → 0.5, within clamp.
        assert_eq!(cb.compute(10.0, None), 0.5);
    }
}
