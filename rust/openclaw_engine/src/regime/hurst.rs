//! Hurst exponent regime classification + hysteresis stabilization (G7-03).
//! Hurst 指數 regime 分類 + 滯回穩定（G7-03）。
//!
//! MODULE_NOTE (EN): R/S analysis lives in `openclaw_core::indicators::volatility::hurst`
//!   (single source of truth — kahan-stable, log-log OLS over chunked deviations).
//!   This module sits on top of that estimator and adds:
//!     1. A typed `RegimeLabel` enum (`Persistent` / `AntiPersistent` / `Random`)
//!        replacing the legacy "trending" / "mean_reverting" / "random_walk"
//!        free-form strings used by the strategies. Convertible to/from those
//!        strings via `RegimeLabel::from_legacy_str` / `as_legacy_str` so call
//!        sites can migrate gradually.
//!     2. A `HysteresisDetector` that holds the recent classification stream and
//!        only flips the persisted label after `lag` consecutive same-side
//!        observations. Symmetric for both Persistent and AntiPersistent. Random
//!        is the cooldown / fallback state — leaving Persistent or AntiPersistent
//!        does not require lag (we exit the regime as soon as the instantaneous
//!        classification stops crossing the relevant threshold).
//!     3. `hurst_label_for_symbol(prices, &HurstConfig) -> Option<RegimeLabel>`
//!        — the Phase A entry point. Computes a one-shot label from a price
//!        window without owning detector state. Phase B (deferred) will wire a
//!        per-symbol `HysteresisDetector` map to a tick pipeline / scanner.
//!
//!   Numerical & semantic guarantees:
//!     * Returns `None` for windows shorter than `min_window * 4` (Phase A
//!       heuristic — needs at least 4 chunks at the smallest sub-window).
//!     * The wrapped core estimator already clamps Hurst to [0.0, 1.0], handles
//!       constant series (returns neutral 0.5), and skips degenerate chunks.
//!     * Defaults of `HurstConfig` (enabled=false, persistent=0.55,
//!       anti_persistent=0.45, lag=6) are dormant — `enabled=false` short-
//!       circuits `hurst_label_for_symbol` to `None` so Phase A introduces zero
//!       runtime change in callers.
//!
//! MODULE_NOTE (中): R/S 分析的權威實作在 `openclaw_core::indicators::volatility::hurst`
//!   （單一真相，kahan 穩定 + log-log OLS）。本模組在其上加：
//!     1. 類型化的 `RegimeLabel` enum 取代 legacy 字串。
//!     2. `HysteresisDetector` 滯回器：需 `lag` 次連續同向才翻已持久化的標籤。
//!        對 Persistent 與 AntiPersistent 對稱；Random 為冷卻態（離開 Persistent
//!        或 AntiPersistent 不需 lag，瞬時分類一不過閾值即退回 Random）。
//!     3. `hurst_label_for_symbol()` Phase A 入口：從價格窗口算一次性標籤。
//!        Phase B 將把 per-symbol detector map 接到 tick pipeline / scanner。
//!   預設 `enabled=false` 完全 no-op，Phase A 不影響 runtime。

use std::collections::VecDeque;

use crate::config::HurstConfig;

/// Stabilized regime label after hysteresis filtering.
/// 經滯回濾波後的 regime 標籤。
///
/// `Persistent` ≈ trending (H > persistent_threshold for `lag` consecutive
/// observations); `AntiPersistent` ≈ mean-reverting (H < antipersistent_threshold
/// for `lag` consecutive observations); `Random` is the cooldown / fallback.
///
/// `Persistent` ≈ 趨勢；`AntiPersistent` ≈ 均值回歸；`Random` 為冷卻 / 後備態。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum RegimeLabel {
    Persistent,
    AntiPersistent,
    Random,
}

impl RegimeLabel {
    /// Convert from the legacy free-form regime string used by `HurstResult.regime`
    /// (`"trending"` / `"mean_reverting"` / `"random_walk"`). Unknown strings map
    /// to `Random` to preserve the fail-safe semantics of the legacy code path.
    /// 從 legacy 字串轉換；未知字串 → `Random`（保留 legacy 失敗保守語意）。
    pub fn from_legacy_str(s: &str) -> Self {
        match s {
            "trending" => RegimeLabel::Persistent,
            "mean_reverting" => RegimeLabel::AntiPersistent,
            _ => RegimeLabel::Random,
        }
    }

    /// Convert to the legacy free-form string consumed by existing strategy code
    /// (e.g. `bb_breakout`'s `h.regime == "trending"`). This lets callers feed a
    /// stabilized label back into the legacy comparison sites without changing
    /// them in Phase A.
    /// 轉回 legacy 字串，方便將穩定後的標籤餵回 legacy 比較點，無須改 call site。
    pub fn as_legacy_str(self) -> &'static str {
        match self {
            RegimeLabel::Persistent => "trending",
            RegimeLabel::AntiPersistent => "mean_reverting",
            RegimeLabel::Random => "random_walk",
        }
    }
}

/// Compute a Hurst exponent over `prices` via R/S analysis (delegates to
/// `openclaw_core::indicators::volatility::hurst`). Returns `None` when the
/// window is too short or the estimator degenerates.
///
/// `min_window` and `max_window` are the inclusive sub-window (lag) bounds for
/// R/S chunking; the core estimator dynamically clips `max_window` to
/// `n_returns / 2` if needed.
///
/// Phase A heuristic: require `prices.len() >= min_window * 4` so the smallest
/// sub-window has at least 4 chunks (otherwise the OLS slope is unreliable).
///
/// 從 `prices` 計算 Hurst 指數（委派 openclaw_core）。窗口太短或估計器退化 → None。
/// Phase A 啟發：要求 `prices.len() >= min_window * 4`，最小 sub-window 至少 4 chunks。
pub fn compute_hurst(prices: &[f64], min_window: usize, max_window: usize) -> Option<f64> {
    if min_window < 2 || min_window >= max_window {
        return None;
    }
    if prices.len() < min_window.saturating_mul(4) {
        return None;
    }
    // Use neutral 0.50/0.50 thresholds inside the core call — we only care
    // about the numeric Hurst value here; the regime classification is done
    // by `HysteresisDetector` against `HurstConfig` thresholds.
    // 在此只取數值，分類由 HysteresisDetector 對 HurstConfig 閾值處理。
    let res = openclaw_core::indicators::hurst(
        prices,
        min_window,
        max_window,
        0.5,
        0.5,
    )?;
    let h = res.hurst;
    if h.is_nan() || h.is_infinite() {
        return None;
    }
    Some(h.clamp(0.0, 1.0))
}

/// Hysteresis filter for instantaneous Hurst observations.
///
/// Maintains a rolling history of the most recent `lag` raw H values. The
/// persisted regime label only flips into Persistent or AntiPersistent after
/// every observation in that history sits on the same side of its threshold.
/// Leaving Persistent / AntiPersistent is immediate (one observation crossing
/// back into the band is enough) — this asymmetry mirrors the spec, which is
/// motivated by wanting to enter regime-conditional behaviour cautiously but
/// exit it fast on shift.
///
/// 對瞬時 Hurst 觀察值做滯回濾波。維護最近 `lag` 個原始 H 值滾動歷史；
/// 只有這 `lag` 個全在同一側越過對應閾值，持久化的標籤才會翻入 Persistent /
/// AntiPersistent。離開兩個極端 regime 為即時（一次回到 band 內就回 Random），
/// 符合「進謹慎、出迅速」的設計直覺。
#[derive(Debug, Clone)]
pub struct HysteresisDetector {
    history: VecDeque<f64>,
    lag: usize,
    persistent_threshold: f64,
    antipersistent_threshold: f64,
    current: RegimeLabel,
}

impl HysteresisDetector {
    /// Construct from a `HurstConfig` snapshot. Validation is the caller's
    /// responsibility (the schema validates at load time); we still defensively
    /// clamp `lag = max(lag, 1)` here to avoid panicking on a degenerate config.
    /// 由 `HurstConfig` 快照建構；schema 載入時已 validate，此處仍做 lag>=1 防護。
    pub fn from_config(cfg: &HurstConfig) -> Self {
        let lag = cfg.hysteresis_lag.max(1);
        Self {
            history: VecDeque::with_capacity(lag),
            lag,
            persistent_threshold: cfg.persistent_threshold,
            antipersistent_threshold: cfg.antipersistent_threshold,
            current: RegimeLabel::Random,
        }
    }

    /// Push a fresh raw Hurst observation and return the post-filtering label.
    /// Logic:
    ///   * Append `h` to history; trim to `lag` entries.
    ///   * If history full and all `> persistent_threshold` → flip to Persistent.
    ///   * If history full and all `< antipersistent_threshold` → flip to
    ///     AntiPersistent.
    ///   * Otherwise: if currently Persistent and the latest observation is no
    ///     longer above `persistent_threshold`, fall back to Random; symmetric
    ///     for AntiPersistent. Hold otherwise.
    ///
    /// 推入一個新的原始 Hurst 觀察值，回傳濾波後的標籤。邏輯：
    ///   - history 滿且全部 > persistent_threshold → 翻 Persistent。
    ///   - history 滿且全部 < antipersistent_threshold → 翻 AntiPersistent。
    ///   - 否則：若目前 Persistent 但最新觀察跌出 persistent_threshold → 退 Random（對稱）。
    pub fn push(&mut self, h: f64) -> RegimeLabel {
        if self.history.len() == self.lag {
            self.history.pop_front();
        }
        self.history.push_back(h);

        let full = self.history.len() == self.lag;

        if full {
            let all_persistent = self
                .history
                .iter()
                .all(|x| *x > self.persistent_threshold);
            let all_anti = self
                .history
                .iter()
                .all(|x| *x < self.antipersistent_threshold);
            if all_persistent {
                self.current = RegimeLabel::Persistent;
                return self.current;
            }
            if all_anti {
                self.current = RegimeLabel::AntiPersistent;
                return self.current;
            }
        }

        // Cooldown: if the most recent observation no longer supports the held
        // regime, drop back to Random immediately (asymmetric — "exit fast").
        // 冷卻：最新觀察不再支持當前 regime → 立即退 Random（離開即時）。
        match self.current {
            RegimeLabel::Persistent if h <= self.persistent_threshold => {
                self.current = RegimeLabel::Random;
            }
            RegimeLabel::AntiPersistent if h >= self.antipersistent_threshold => {
                self.current = RegimeLabel::Random;
            }
            _ => {}
        }
        self.current
    }

    /// Read the persisted label without consuming a new observation.
    /// 讀取目前持久化的標籤，不消費新觀察。
    pub fn current(&self) -> RegimeLabel {
        self.current
    }

    /// Number of observations currently buffered.
    /// 目前 buffer 中的觀察數。
    pub fn buffered(&self) -> usize {
        self.history.len()
    }
}

/// Phase A public adapter: compute a stabilized `RegimeLabel` for a one-off
/// price window. Returns `None` when the config is disabled, the window is too
/// short, or the estimator degenerates.
///
/// Note: this performs *no* hysteresis (a single call has no history), so the
/// returned label is just the threshold classification of the raw Hurst. Phase
/// B will plumb a per-symbol `HysteresisDetector` cache through the call sites
/// so the lag actually applies. We expose this stub now so call sites can
/// adopt the typed return + dormant-by-default contract before Phase B lands.
///
/// Phase A 對外 adapter：對單次價格窗口算一個穩定後的標籤（gated by `enabled`）。
/// 注意：單次呼叫無歷史 → 不施 hysteresis，回的是原始 Hurst 對閾值的分類。
/// Phase B 才會把 per-symbol HysteresisDetector cache 串到 call site，讓 lag 真正生效。
pub fn hurst_label_for_symbol(prices: &[f64], cfg: &HurstConfig) -> Option<RegimeLabel> {
    if !cfg.enabled {
        return None;
    }
    let max_window = cfg.window_size / 2;
    let h = compute_hurst(prices, cfg.min_window(), max_window)?;
    let label = if h > cfg.persistent_threshold {
        RegimeLabel::Persistent
    } else if h < cfg.antipersistent_threshold {
        RegimeLabel::AntiPersistent
    } else {
        RegimeLabel::Random
    };
    Some(label)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    // ───────────────────────────────────────────────────────────────────────
    // RegimeLabel string round-trip
    // ───────────────────────────────────────────────────────────────────────

    #[test]
    fn regime_label_legacy_str_round_trip() {
        for label in [
            RegimeLabel::Persistent,
            RegimeLabel::AntiPersistent,
            RegimeLabel::Random,
        ] {
            assert_eq!(RegimeLabel::from_legacy_str(label.as_legacy_str()), label);
        }
    }

    #[test]
    fn regime_label_legacy_str_unknown_maps_random() {
        assert_eq!(RegimeLabel::from_legacy_str("totally bogus"), RegimeLabel::Random);
        assert_eq!(RegimeLabel::from_legacy_str(""), RegimeLabel::Random);
    }

    // ───────────────────────────────────────────────────────────────────────
    // compute_hurst — argument validation
    // ───────────────────────────────────────────────────────────────────────

    #[test]
    fn compute_hurst_rejects_too_short_window() {
        // min_window * 4 = 8; supply only 6 samples.
        let prices: Vec<f64> = (0..6).map(|i| 100.0 + i as f64).collect();
        assert!(compute_hurst(&prices, 2, 4).is_none());
    }

    #[test]
    fn compute_hurst_rejects_zero_min_window() {
        let prices: Vec<f64> = (0..200).map(|i| 100.0 + i as f64).collect();
        assert!(compute_hurst(&prices, 0, 32).is_none());
        assert!(compute_hurst(&prices, 1, 32).is_none());
    }

    #[test]
    fn compute_hurst_rejects_inverted_window() {
        let prices: Vec<f64> = (0..200).map(|i| 100.0 + i as f64).collect();
        assert!(compute_hurst(&prices, 64, 16).is_none());
        assert!(compute_hurst(&prices, 32, 32).is_none());
    }

    // ───────────────────────────────────────────────────────────────────────
    // compute_hurst — known-shape sequences (loose bounds)
    // ───────────────────────────────────────────────────────────────────────

    #[test]
    fn compute_hurst_random_walk_near_half() {
        // Deterministic pseudo-random walk with seeded LCG so the test is
        // reproducible without pulling in `rand`. Drift-free; expect H ≈ 0.5.
        // 確定性偽隨機 walk（LCG 種子）— 無漂移；期望 H ≈ 0.5。
        let mut state: u64 = 0xC0FFEE_D00D_BEEF;
        let mut price = 100.0_f64;
        let mut prices = Vec::with_capacity(512);
        prices.push(price);
        for _ in 0..511 {
            // Park-Miller-ish LCG
            state = state.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1);
            // Map upper 32 bits to f64 in [-0.005, 0.005]
            let u = ((state >> 32) as u32) as f64 / u32::MAX as f64;
            let step = (u - 0.5) * 0.01;
            price *= 1.0 + step;
            prices.push(price);
        }
        let h = compute_hurst(&prices, 8, 128).expect("random walk should yield Some(H)");
        // R/S over a 512-pt random walk is noisy; just sanity-check it lies in
        // a wide neighborhood of 0.5 — used to detect a regression in the
        // delegation, not as a tight statistical claim.
        // 512 點 random walk 的 R/S 噪聲大；只做寬鬆健全檢查（防止委派回歸）。
        assert!(
            (0.30..=0.70).contains(&h),
            "expected H in [0.30, 0.70] for random walk, got {h}"
        );
    }

    #[test]
    fn compute_hurst_strong_trend_above_half() {
        // Pure deterministic trend — pathological case; the kahan R/S routine
        // should still return *something* in [0, 1] and lean trending or
        // saturate at 1.0 for an exactly-deterministic series.
        // 純確定性趨勢；估計器應回 [0,1] 之內（趨勢上端或飽和到 1.0）。
        let prices: Vec<f64> = (0..512).map(|i| 100.0 + i as f64 * 0.1).collect();
        let h = compute_hurst(&prices, 8, 128).expect("trend should yield Some(H)");
        assert!(h >= 0.5 - 1e-9, "expected H >= 0.5 for pure trend, got {h}");
    }

    #[test]
    fn compute_hurst_constant_series_returns_none() {
        // Constant prices → all returns are zero → every R/S chunk has
        // std_dev = 0 → core skips them and OLS has < 2 points → returns
        // `None`. (The neutral 0.5 fallback in core only kicks in when there
        // aren't enough valid returns *to start with*, not when the chunks all
        // degenerate.) Document the wrapper's None-passthrough here so a
        // regression in core can't silently switch to a fabricated value.
        // 常數價 → 全 0 returns → 每個 R/S chunk std_dev=0 → core 跳過 → OLS
        // 點數 <2 → 回 None。包裹器原樣透傳，藉此測試固守此語意。
        let prices = vec![100.0; 512];
        assert!(
            compute_hurst(&prices, 8, 128).is_none(),
            "constant series should yield None (degenerate R/S)"
        );
    }

    #[test]
    fn compute_hurst_clamps_into_unit_interval() {
        // Property check: for a pile of distinct *non-degenerate* shapes,
        // output is always in [0.0, 1.0]. The core clamps; this guards against
        // accidental drift. (Constant series exits via None per the previous
        // test — not part of the property check.)
        // 多樣形狀（非退化）下，輸出必落於 [0,1]，防止 clamp 漂移。
        let cases: Vec<Vec<f64>> = vec![
            (0..512).map(|i| 100.0 + i as f64).collect(),
            (0..512).map(|i| 100.0 + (i as f64 * 0.05).sin()).collect(),
            (0..512).map(|i| 100.0 - i as f64 * 0.01).collect(),
        ];
        for prices in &cases {
            let h = compute_hurst(prices, 8, 128).expect("non-empty result");
            assert!(
                (0.0..=1.0).contains(&h),
                "Hurst out of [0,1]: {h}"
            );
        }
    }

    // ───────────────────────────────────────────────────────────────────────
    // HysteresisDetector lifecycle
    // ───────────────────────────────────────────────────────────────────────

    fn cfg_for_test(lag: usize) -> HurstConfig {
        HurstConfig {
            enabled: true,
            window_size: 128,
            min_window: 8,
            hysteresis_lag: lag,
            persistent_threshold: 0.55,
            antipersistent_threshold: 0.45,
        }
    }

    #[test]
    fn hysteresis_starts_in_random() {
        let det = HysteresisDetector::from_config(&cfg_for_test(6));
        assert_eq!(det.current(), RegimeLabel::Random);
        assert_eq!(det.buffered(), 0);
    }

    #[test]
    fn hysteresis_persistent_only_flips_after_lag() {
        let mut det = HysteresisDetector::from_config(&cfg_for_test(6));
        // 5 strong-trend observations: still Random because lag is 6.
        for _ in 0..5 {
            assert_eq!(det.push(0.80), RegimeLabel::Random);
        }
        // 6th observation tips us over the lag → Persistent.
        assert_eq!(det.push(0.80), RegimeLabel::Persistent);
    }

    #[test]
    fn hysteresis_anti_only_flips_after_lag() {
        let mut det = HysteresisDetector::from_config(&cfg_for_test(6));
        for _ in 0..5 {
            assert_eq!(det.push(0.20), RegimeLabel::Random);
        }
        assert_eq!(det.push(0.20), RegimeLabel::AntiPersistent);
    }

    #[test]
    fn hysteresis_mixed_history_does_not_flip() {
        let mut det = HysteresisDetector::from_config(&cfg_for_test(6));
        // 5 trending then a single random-walk neutral — the buffer is mixed
        // so no flip occurs.
        for _ in 0..5 {
            det.push(0.80);
        }
        assert_eq!(det.push(0.50), RegimeLabel::Random);
    }

    #[test]
    fn hysteresis_persistent_exits_immediately_on_first_breach() {
        let mut det = HysteresisDetector::from_config(&cfg_for_test(3));
        // Establish Persistent.
        for _ in 0..2 {
            det.push(0.80);
        }
        assert_eq!(det.push(0.80), RegimeLabel::Persistent);
        // First observation back inside the band → drop to Random instantly.
        assert_eq!(det.push(0.50), RegimeLabel::Random);
    }

    #[test]
    fn hysteresis_anti_exits_immediately_on_first_breach() {
        let mut det = HysteresisDetector::from_config(&cfg_for_test(3));
        for _ in 0..2 {
            det.push(0.20);
        }
        assert_eq!(det.push(0.20), RegimeLabel::AntiPersistent);
        assert_eq!(det.push(0.50), RegimeLabel::Random);
    }

    #[test]
    fn hysteresis_lag_one_acts_as_pass_through() {
        let mut det = HysteresisDetector::from_config(&cfg_for_test(1));
        assert_eq!(det.push(0.80), RegimeLabel::Persistent);
        assert_eq!(det.push(0.20), RegimeLabel::AntiPersistent);
        assert_eq!(det.push(0.50), RegimeLabel::Random);
        assert_eq!(det.push(0.80), RegimeLabel::Persistent);
    }

    #[test]
    fn hysteresis_zero_lag_clamped_to_one() {
        // Defensive: HurstConfig::validate should reject lag=0, but if a
        // caller assembled the struct manually we must not panic.
        let cfg = HurstConfig {
            hysteresis_lag: 0,
            ..cfg_for_test(1)
        };
        let mut det = HysteresisDetector::from_config(&cfg);
        // With lag clamped to 1 we should behave like the pass-through above.
        assert_eq!(det.push(0.80), RegimeLabel::Persistent);
        assert_eq!(det.push(0.20), RegimeLabel::AntiPersistent);
    }

    #[test]
    fn hysteresis_window_slides_correctly() {
        let mut det = HysteresisDetector::from_config(&cfg_for_test(3));
        // First three trending → Persistent.
        for _ in 0..3 {
            det.push(0.80);
        }
        assert_eq!(det.current(), RegimeLabel::Persistent);
        // One observation back to neutral → Random (asymmetric exit).
        det.push(0.50);
        assert_eq!(det.current(), RegimeLabel::Random);
        // Two more anti — buffer now [0.50, anti, anti] — still mixed.
        det.push(0.20);
        det.push(0.20);
        assert_eq!(det.current(), RegimeLabel::Random);
        // Third anti pushes the 0.50 out → buffer [anti, anti, anti] → flip.
        assert_eq!(det.push(0.20), RegimeLabel::AntiPersistent);
    }

    // ───────────────────────────────────────────────────────────────────────
    // hurst_label_for_symbol — gating + classification
    // ───────────────────────────────────────────────────────────────────────

    #[test]
    fn hurst_label_for_symbol_disabled_returns_none() {
        let cfg = HurstConfig::default(); // enabled=false by default
        let prices: Vec<f64> = (0..256).map(|i| 100.0 + i as f64 * 0.1).collect();
        assert!(hurst_label_for_symbol(&prices, &cfg).is_none());
    }

    #[test]
    fn hurst_label_for_symbol_short_window_returns_none() {
        let cfg = cfg_for_test(6);
        let prices: Vec<f64> = (0..10).map(|i| 100.0 + i as f64).collect();
        assert!(hurst_label_for_symbol(&prices, &cfg).is_none());
    }

    #[test]
    fn hurst_label_for_symbol_trend_classifies_persistent() {
        let cfg = cfg_for_test(6);
        let prices: Vec<f64> = (0..512).map(|i| 100.0 + i as f64 * 0.2).collect();
        let label = hurst_label_for_symbol(&prices, &cfg)
            .expect("strong trend should produce a label");
        // Pure deterministic trend ⇒ Hurst saturates near 1.0 ⇒ Persistent.
        assert_eq!(label, RegimeLabel::Persistent);
    }

    #[test]
    fn hurst_label_for_symbol_constant_returns_none() {
        // Degenerate (constant) series → core hurst returns None (every R/S
        // chunk has std_dev=0 and OLS has < 2 points), so we propagate None.
        // 退化（常數）序列 → core 回 None；包裹器原樣傳遞，無法分類。
        let cfg = cfg_for_test(6);
        let prices = vec![100.0_f64; 512];
        assert!(
            hurst_label_for_symbol(&prices, &cfg).is_none(),
            "degenerate series must propagate None, not fabricate a label"
        );
    }

    #[test]
    fn hurst_label_for_symbol_classification_matches_thresholds() {
        // Property: the label returned by `hurst_label_for_symbol` must agree
        // with a direct threshold check on the underlying Hurst value. Run
        // over a varied set (LCG random walk, deterministic trend, noisy
        // mean-reverting AR(1)-ish wobble) so we cover all three branches.
        // 屬性測試：標籤必與底層 Hurst 直接閾值比對結果一致。
        let cfg = cfg_for_test(6);

        // LCG random walk (drift-free).
        let mut state: u64 = 0xC0FFEE_D00D_BEEF;
        let mut price = 100.0_f64;
        let mut walk = Vec::with_capacity(512);
        walk.push(price);
        for _ in 0..511 {
            state = state.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1);
            let u = ((state >> 32) as u32) as f64 / u32::MAX as f64;
            let step = (u - 0.5) * 0.01;
            price *= 1.0 + step;
            walk.push(price);
        }

        // Pure deterministic trend.
        let trend: Vec<f64> = (0..512).map(|i| 100.0 + i as f64 * 0.2).collect();

        // Noisy oscillator (mean-reverting flavour).
        let osc: Vec<f64> = (0..512)
            .map(|i| 100.0 + (i as f64 * 0.5).sin() * 0.5)
            .collect();

        for prices in [&walk, &trend, &osc] {
            let label = hurst_label_for_symbol(prices, &cfg).expect("non-degenerate");
            let h = compute_hurst(prices, cfg.min_window(), cfg.window_size / 2)
                .expect("non-degenerate");
            let expected = if h > cfg.persistent_threshold {
                RegimeLabel::Persistent
            } else if h < cfg.antipersistent_threshold {
                RegimeLabel::AntiPersistent
            } else {
                RegimeLabel::Random
            };
            assert_eq!(
                label, expected,
                "label/threshold disagreement at H={h:.4} for series of len {}",
                prices.len()
            );
        }
    }
}
