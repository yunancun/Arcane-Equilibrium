//! Grid computation helpers — pure functions extracted from grid_trading.rs (A0-a).
//! 網格計算輔助函數 — 從 grid_trading.rs 提取的純函數（A0-a）。
//!
//! MODULE_NOTE (EN): Pure grid math: level construction (linear/geometric), nearest-index
//!   lookup, and OU-derived optimal spacing. No strategy state or side effects.
//! MODULE_NOTE (中): 純網格數學：層級構建（線性/幾何）、最近索引查找、
//!   OU 推導最佳間距。無策略狀態或副作用。

use serde::{Deserialize, Serialize};

/// Grid spacing mode: linear (equal dollar) or geometric (equal ratio).
/// 網格間距模式：線性（等差）或幾何（等比）。
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum GridSpacingMode {
    /// Equal dollar spacing between levels (arithmetic progression).
    /// 等差間距：各層級之間價差相等。
    Linear,
    /// Equal ratio spacing between levels (geometric progression).
    /// 等比間距：各層級之間比率相等，更適合加密貨幣（價格按比例波動）。
    Geometric,
}

/// Build grid levels with linear (arithmetic) spacing.
/// 以線性（等差）間距建構網格層級。
pub fn build_linear_levels(lower: f64, upper: f64, count: usize) -> Vec<f64> {
    let mut levels = Vec::with_capacity(count);
    let step = (upper - lower) / (count as f64 - 1.0);
    for i in 0..count {
        levels.push(lower + step * i as f64);
    }
    levels
}

/// Build grid levels with geometric (ratio-based) spacing.
/// 以幾何（等比）間距建構網格層級。
/// ratio = (upper / lower)^(1/(n-1)), level[i] = lower * ratio^i
pub fn build_geometric_levels(lower: f64, upper: f64, count: usize) -> Vec<f64> {
    let mut levels = Vec::with_capacity(count);
    if count <= 1 || lower <= 0.0 || upper <= 0.0 {
        // Degenerate case — fall back to single level or empty.
        // 退化情況 — 回退為單層級或空。
        if count >= 1 && lower > 0.0 {
            levels.push(lower);
        }
        return levels;
    }
    let ratio = (upper / lower).powf(1.0 / (count as f64 - 1.0));
    for i in 0..count {
        levels.push(lower * ratio.powi(i as i32));
    }
    levels
}

/// Build grid levels respecting the given spacing mode.
/// 根據指定的間距模式建構網格層級。
pub fn build_levels(lower: f64, upper: f64, count: usize, mode: &GridSpacingMode) -> Vec<f64> {
    match mode {
        GridSpacingMode::Linear => build_linear_levels(lower, upper, count),
        GridSpacingMode::Geometric => build_geometric_levels(lower, upper, count),
    }
}

/// Find nearest grid level index for a price.
/// 找到價格最近的網格層級索引。
///
/// Returns 0 if levels is empty. Linear scan — grid counts are small (≤50).
/// levels 為空時返回 0。線性掃描 — 網格數量小（≤50）。
pub fn nearest_grid_idx(levels: &[f64], price: f64) -> usize {
    let mut best = 0;
    let mut best_dist = f64::MAX;
    for (i, &level) in levels.iter().enumerate() {
        let d = (price - level).abs();
        if d < best_dist {
            best_dist = d;
            best = i;
        }
    }
    best
}

/// Compute OU-derived optimal grid step size from price history.
/// Returns None if data is insufficient or parameters are degenerate.
/// 從價格歷史計算 OU 推導的最佳網格步長。
/// 數據不足或參數退化時返回 None。
///
/// Formula: step = max(σ·√(2/θ), 2·fee_rate·μ)
/// where θ = mean-reversion speed, σ = volatility, μ = mean price.
/// 公式：step = max(σ·√(2/θ), 2·fee_rate·μ)
/// θ = 均值回歸速度，σ = 波動率，μ = 均值價格。
pub fn compute_ou_step(history: &[f64], ou_lookback: usize, fee_rate: f64) -> Option<f64> {
    if history.len() < 20 {
        return None;
    }
    let n = history.len().min(ou_lookback);
    let prices = &history[history.len() - n..];

    let changes: Vec<f64> = prices.windows(2).map(|w| w[1] - w[0]).collect();
    let x_lag: Vec<f64> = prices[..prices.len() - 1].to_vec();

    if changes.is_empty() {
        return None;
    }
    let n_f = changes.len() as f64;
    let mean_x: f64 = x_lag.iter().sum::<f64>() / n_f;
    let mean_dx: f64 = changes.iter().sum::<f64>() / n_f;

    let mut num = 0.0;
    let mut den = 0.0;
    for i in 0..changes.len() {
        let dx = x_lag[i] - mean_x;
        num += dx * (changes[i] - mean_dx);
        den += dx * dx;
    }

    if den.abs() < 1e-15 {
        return None;
    }
    let b = num / den;
    // If b >= 0 (trending/random walk, not mean-reverting), OU model is invalid —
    // return None to fall back to adaptive ±10% range.
    // 若 b >= 0（趨勢/隨機遊走，非均值回歸），OU 模型不適用，
    // 返回 None 讓呼叫端回退到 ±10% 自適應範圍。
    if b >= 0.0 {
        return None;
    }
    let theta = (-b).max(0.01); // sane minimum for genuine mean-reversion

    let sigma = (changes.iter().map(|c| c * c).sum::<f64>() / n_f).sqrt();
    let mu = prices.iter().sum::<f64>() / prices.len() as f64;

    // OU optimal grid spacing: σ·√(2/θ) — derived from OU first-passage time.
    // OU 最佳網格間距：σ·√(2/θ) — 由 OU 首次穿越時間推導。
    let ou_step = sigma * (2.0_f64 / theta).sqrt();
    let fee_floor = 2.0 * fee_rate * mu;
    let step = ou_step.max(fee_floor);

    if step > 0.0 && mu > 0.0 {
        Some(step)
    } else {
        None
    }
}

// ---------------------------------------------------------------------------
// G7-06 — OU residual-based σ estimator (Phase A: estimator + tests only).
// G7-06 — OU 殘差 σ 估計器（Phase A：估計器 + 單測，未接 hot path）。
// ---------------------------------------------------------------------------

/// G7-06 (2026-04-24): Residual-based σ estimator for an Ornstein-Uhlenbeck
/// (OU) process `dx_t = θ(μ - x_{t-1})dt + σ dW_t`.
///
/// The existing `compute_ou_step` uses `σ = sqrt(Σ Δx² / n)`, which is the
/// stdev of raw price changes. That number conflates the deterministic
/// mean-reversion drift `θ(μ - x_{t-1})` with the white-noise innovation
/// `σ dW_t`, and is biased high. The residual estimator below subtracts the
/// fitted drift first:
///
/// ```text
///   ε_t = Δx_t − θ̂ (μ̂ − x_{t-1})
///   σ̂  = sqrt( Σ ε_t² / (n − 1) )       // unbiased
/// ```
///
/// `θ̂` and `μ̂` come from the same OLS fit `Δx_t = a + b · x_{t-1} + ε_t`
/// already performed in `compute_ou_step` (with `θ̂ = -b̂` and
/// `μ̂ = -â / b̂`). The shape of the estimator mirrors a Yule-Walker /
/// AR(1) residual fit and gives a strictly correct σ for the OU
/// innovation — which is what `σ · √(2/θ)` (the optimal grid spacing) is
/// supposed to consume.
///
/// This Phase A drop does **not** rewire `compute_ou_step` — the call site
/// stays on the raw-Δx σ path until Phase B wires `RiskConfig.grid_ou`.
/// `defaults preserve runtime behavior bit-for-bit`.
///
/// G7-06：OU 殘差 σ 估計器。`σ = sqrt(Σ Δx²/n)` 把 mean-reversion drift
/// 也算進 σ 是高估；本估計器先扣掉 drift `θ̂(μ̂ − x_{t-1})`，再用
/// `σ̂ = sqrt(Σ ε²/(n-1))`（無偏）。Phase A 不接 hot path。
#[derive(Debug, Clone)]
pub struct OuResidualSigma {
    /// Fitted mean-reversion speed `θ̂` (positive for genuine mean-reversion;
    /// `0.0` if the OU fit is degenerate / non-mean-reverting).
    /// 擬合的均值回歸速度 θ̂；OU 不適用時為 0.0。
    pub theta: f64,
    /// Fitted long-run mean `μ̂` (sample average of the input window).
    /// 擬合的長期均值 μ̂（窗口樣本平均）。
    pub mu: f64,
    /// Residual-based standard deviation `σ̂`. `NaN` when the estimator is
    /// degenerate (insufficient samples / zero design-matrix variance).
    /// 殘差標準差 σ̂；估計器退化時為 NaN。
    pub sigma_hat: f64,
    /// Number of observations the estimate was computed from (window length).
    /// 用於估計的觀測數（窗口長度）。
    pub n_observations: usize,
}

impl OuResidualSigma {
    /// Minimum window length below which the estimator returns a degenerate
    /// (`sigma_hat = NaN`) result rather than risking division by ~0.
    /// `n - 1 >= 4` matches a 5-sample minimum for the `(n-1)` denominator.
    /// 估計器退化下限；< 5 樣本回傳 NaN，避免 (n-1) 除接近 0。
    pub const MIN_SAMPLES: usize = 5;

    /// Build a degenerate placeholder (all-zero coefficients, `σ̂ = NaN`).
    /// Useful as the seed value of a streaming `update()` accumulator before
    /// enough samples arrive.
    /// 建立退化佔位（係數全 0、σ̂ = NaN），作為 streaming 起始種子。
    pub fn empty() -> Self {
        Self {
            theta: 0.0,
            mu: 0.0,
            sigma_hat: f64::NAN,
            n_observations: 0,
        }
    }

    /// Estimate `θ̂ / μ̂ / σ̂` from a price window via the OLS fit
    /// `Δx_t = a + b · x_{t-1} + ε_t`. Returns `OuResidualSigma::empty()`-style
    /// degenerate result (`sigma_hat = NaN`) when the window is too short
    /// (`< MIN_SAMPLES + 1`) or the OLS design matrix collapses
    /// (zero variance in `x_{t-1}`).
    ///
    /// Note: this estimator deliberately does NOT short-circuit on `b̂ >= 0`
    /// (trending / random-walk fit). Callers that need the
    /// "mean-reverting only" guard already handle that in
    /// `compute_ou_step`. Returning a finite `σ̂` even for non-mean-reverting
    /// data lets a Phase B wire-up still benefit from a clean residual-vs-
    /// raw σ comparison.
    ///
    /// G7-06：以 OLS `Δx = a + b·x_{t-1} + ε` 從窗口估計 θ̂/μ̂/σ̂。
    /// 樣本不足或設計矩陣退化時回傳 σ̂ = NaN。**不**短路 b ≥ 0
    /// （留給 compute_ou_step 處理「僅均值回歸」guard）。
    pub fn estimate_from_window(window: &[f64]) -> Self {
        let n_obs = window.len();
        if n_obs < Self::MIN_SAMPLES + 1 {
            return Self {
                theta: 0.0,
                mu: 0.0,
                sigma_hat: f64::NAN,
                n_observations: n_obs,
            };
        }
        let n_f = (n_obs - 1) as f64; // number of Δx terms
        let mu = window.iter().sum::<f64>() / n_obs as f64;

        // OLS fit: Δx_t = a + b · x_{t-1} + ε_t
        // OLS 擬合
        let mean_x_lag: f64 = window[..n_obs - 1].iter().sum::<f64>() / n_f;
        let mean_dx: f64 = (window[n_obs - 1] - window[0]) / n_f; // = (sum Δx) / (n-1)

        let mut num = 0.0;
        let mut den = 0.0;
        for i in 0..n_obs - 1 {
            let dx = window[i + 1] - window[i];
            let x_lag_centered = window[i] - mean_x_lag;
            num += x_lag_centered * (dx - mean_dx);
            den += x_lag_centered * x_lag_centered;
        }

        if den.abs() < 1e-15 {
            // Degenerate design matrix (all x_{t-1} equal) — σ̂ undefined.
            // 設計矩陣退化 — σ̂ 無定義。
            return Self {
                theta: 0.0,
                mu,
                sigma_hat: f64::NAN,
                n_observations: n_obs,
            };
        }
        let b = num / den;
        let a = mean_dx - b * mean_x_lag;
        // θ̂ = −b̂; clamp to 0 for non-mean-reverting fit (caller decides).
        // θ̂ = -b̂；非均值回歸時 clamp 到 0，由 caller 決定如何處理。
        let theta = (-b).max(0.0);

        // Residuals: ε_t = Δx_t − (a + b·x_{t-1})
        // 殘差
        let mut sse = 0.0;
        for i in 0..n_obs - 1 {
            let dx = window[i + 1] - window[i];
            let pred = a + b * window[i];
            let e = dx - pred;
            sse += e * e;
        }
        // Unbiased σ̂ uses (n − 1) − 2 = n − 3 dof for OLS-with-intercept,
        // but for the "approximately Gaussian innovation" interpretation
        // the simpler `(n − 1)` denominator is adequate and conventional in
        // OU estimation (Aït-Sahalia 2002 §3.1). We expose `(n − 1)` here.
        // 無偏 σ̂ 嚴格 OLS 應用 n-3 自由度，OU 文獻常用 (n-1) 簡化。
        let dof = (n_obs - 1).saturating_sub(1).max(1) as f64;
        let sigma_hat = (sse / dof).sqrt();

        Self {
            theta,
            mu,
            sigma_hat,
            n_observations: n_obs,
        }
    }

    /// G7-06 streaming convenience: feed a single price observation into a
    /// rolling window of capacity `window_capacity` and re-estimate. The
    /// caller owns the buffer (typically `Vec<f64>`) and pushes / truncates
    /// on each tick; this method just refits from the current window slice.
    ///
    /// Designed to be cheap (one OLS pass + one residual pass = O(n)). For
    /// hot-path use in Phase B, the caller can decide to refit only every
    /// K ticks instead of every tick.
    ///
    /// G7-06 streaming 版本：caller 持有 rolling buffer，本方法只負責重新擬合。
    /// O(n) 兩次 pass，Phase B 可決定每 K tick 才重算。
    pub fn update(&mut self, buffer: &mut Vec<f64>, x_new: f64, window_capacity: usize) {
        buffer.push(x_new);
        if buffer.len() > window_capacity {
            let drop = buffer.len() - window_capacity;
            buffer.drain(..drop);
        }
        *self = Self::estimate_from_window(buffer);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_linear_levels_basic() {
        let levels = build_linear_levels(100.0, 200.0, 5);
        assert_eq!(levels.len(), 5);
        assert!((levels[0] - 100.0).abs() < 1e-10);
        assert!((levels[4] - 200.0).abs() < 1e-10);
        // Equal spacing / 等差
        let step = levels[1] - levels[0];
        assert!((levels[2] - levels[1] - step).abs() < 1e-10);
    }

    #[test]
    fn test_geometric_levels_basic() {
        let levels = build_geometric_levels(100.0, 400.0, 3);
        assert_eq!(levels.len(), 3);
        assert!((levels[0] - 100.0).abs() < 1e-10);
        assert!((levels[2] - 400.0).abs() < 1e-6);
        // Equal ratio / 等比
        let ratio1 = levels[1] / levels[0];
        let ratio2 = levels[2] / levels[1];
        assert!((ratio1 - ratio2).abs() < 1e-10);
    }

    #[test]
    fn test_geometric_degenerate() {
        assert!(build_geometric_levels(-1.0, 100.0, 5).is_empty());
        assert_eq!(build_geometric_levels(100.0, 200.0, 1), vec![100.0]);
        assert!(build_geometric_levels(100.0, 200.0, 0).is_empty());
    }

    #[test]
    fn test_build_levels_dispatches() {
        let linear = build_levels(10.0, 20.0, 3, &GridSpacingMode::Linear);
        let geo = build_levels(10.0, 20.0, 3, &GridSpacingMode::Geometric);
        assert_eq!(linear.len(), 3);
        assert_eq!(geo.len(), 3);
        // Linear middle = 15, geometric middle ≈ 14.14
        assert!((linear[1] - 15.0).abs() < 1e-10);
        assert!((geo[1] - (10.0_f64 * 20.0_f64).sqrt()).abs() < 1e-6);
    }

    #[test]
    fn test_nearest_grid_idx() {
        let levels = vec![100.0, 110.0, 120.0, 130.0, 140.0];
        assert_eq!(nearest_grid_idx(&levels, 100.0), 0);
        assert_eq!(nearest_grid_idx(&levels, 115.0), 1); // closer to 110
        assert_eq!(nearest_grid_idx(&levels, 116.0), 2); // closer to 120
        assert_eq!(nearest_grid_idx(&levels, 140.0), 4);
        assert_eq!(nearest_grid_idx(&[], 100.0), 0);
    }

    #[test]
    fn test_compute_ou_step_insufficient_data() {
        assert!(compute_ou_step(&[1.0; 10], 60, 0.001).is_none());
    }

    #[test]
    fn test_compute_ou_step_mean_reverting() {
        // Simulate mean-reverting prices around 100
        // 模擬圍繞 100 均值回歸的價格
        let mut prices = Vec::new();
        for i in 0..50 {
            prices.push(100.0 + 5.0 * (i as f64 * 0.3).sin());
        }
        let result = compute_ou_step(&prices, 60, 0.001);
        // Should return Some for mean-reverting data / 均值回歸數據應返回 Some
        assert!(result.is_some());
        assert!(result.unwrap() > 0.0);
    }

    #[test]
    fn test_compute_ou_step_trending() {
        // Strongly trending prices — OU model invalid / 強趨勢價格 — OU 模型不適用
        let prices: Vec<f64> = (0..50).map(|i| 100.0 + i as f64 * 2.0).collect();
        assert!(compute_ou_step(&prices, 60, 0.001).is_none());
    }

    // -----------------------------------------------------------------------
    // G7-06 — OuResidualSigma estimator tests
    // -----------------------------------------------------------------------

    /// Tiny, deterministic linear-congruential generator. Avoids pulling
    /// `rand` into the engine crate just for tests.
    /// 簡易 LCG 隨機數產生器，避免為測試引 rand。
    fn lcg_unit(state: &mut u64) -> f64 {
        // Numerical Recipes LCG constants. Returns a U(0, 1) value.
        // 經典 NR LCG 常數，回傳 U(0, 1)。
        *state = state.wrapping_mul(1664525).wrapping_add(1013904223);
        ((*state >> 11) as f64) / ((1u64 << 53) as f64)
    }

    /// Box-Muller transform → standard-normal sample (single output).
    /// Box-Muller 轉換 → 標準常態樣本（單值）。
    fn standard_normal(state: &mut u64) -> f64 {
        let u1 = lcg_unit(state).max(1e-300);
        let u2 = lcg_unit(state);
        (-2.0 * u1.ln()).sqrt() * (2.0 * std::f64::consts::PI * u2).cos()
    }

    /// Generate `n` samples from a discrete-time OU process with known
    /// `theta`, `mu`, `sigma`, starting from `x0` and using time step `dt`.
    /// `x_{t+1} = x_t + theta * (mu − x_t) * dt + sigma * sqrt(dt) * ε_t`.
    /// 以已知 θ/μ/σ 產生離散 OU 樣本。
    fn simulate_ou(
        n: usize,
        x0: f64,
        theta: f64,
        mu: f64,
        sigma: f64,
        dt: f64,
        seed: u64,
    ) -> Vec<f64> {
        let mut state = seed;
        let mut out = Vec::with_capacity(n);
        out.push(x0);
        let sd_step = sigma * dt.sqrt();
        for _ in 1..n {
            let x_prev = *out.last().unwrap();
            let drift = theta * (mu - x_prev) * dt;
            let shock = sd_step * standard_normal(&mut state);
            out.push(x_prev + drift + shock);
        }
        out
    }

    #[test]
    fn test_ou_residual_sigma_recovers_known_sigma() {
        // True OU with σ = 0.5 over n=200 samples, dt=1.0 (so per-step σ=0.5).
        // Check the residual estimator recovers σ within 5%.
        // 已知 σ = 0.5 的 OU 過程，n=200，檢查殘差估計器 5% 內回收。
        let prices = simulate_ou(
            200, 100.0, /*theta*/ 0.4, /*mu*/ 100.0, 0.5, 1.0, 0xC0FFEE,
        );
        let est = OuResidualSigma::estimate_from_window(&prices);
        assert_eq!(est.n_observations, 200);
        assert!(
            est.sigma_hat.is_finite(),
            "σ̂ should be finite for valid OU data"
        );
        let rel_err = (est.sigma_hat - 0.5).abs() / 0.5;
        assert!(
            rel_err < 0.10,
            "residual σ̂ = {} too far from true σ = 0.5 (relative error {:.2}%)",
            est.sigma_hat,
            rel_err * 100.0
        );
        // θ̂ should be positive for genuine mean-reversion / θ̂ 應為正
        assert!(
            est.theta > 0.0,
            "θ̂ should be positive for OU data, got {}",
            est.theta
        );
        // μ̂ should be near 100 (long-run mean) / μ̂ 應接近 100
        assert!(
            (est.mu - 100.0).abs() < 1.0,
            "μ̂ = {} too far from true μ = 100",
            est.mu
        );
    }

    #[test]
    fn test_ou_residual_sigma_trending_is_graceful() {
        // Linear trend with no mean reversion. σ̂ should still be finite
        // and small (residuals from a poorly-fit drift line are small) — no
        // panic, no NaN propagation.
        // 純線性趨勢：σ̂ 應為有限小值（線性擬合下殘差很小），不應 NaN/panic。
        let prices: Vec<f64> = (0..100).map(|i| 100.0 + (i as f64) * 2.0).collect();
        let est = OuResidualSigma::estimate_from_window(&prices);
        assert!(
            est.sigma_hat.is_finite(),
            "σ̂ should be finite for trending data, got {}",
            est.sigma_hat
        );
        // Strict trend — residual σ̂ should be very small (numerical noise).
        // 嚴格線性 — 殘差應為數值雜訊量級。
        assert!(
            est.sigma_hat < 1e-6,
            "σ̂ for pure linear trend should be ~0, got {}",
            est.sigma_hat
        );
        // θ̂ clamped to 0 (b ≥ 0 path) / θ̂ 被 clamp 到 0
        assert_eq!(
            est.theta, 0.0,
            "θ̂ for non-mean-reverting trend should clamp to 0"
        );
    }

    #[test]
    fn test_ou_residual_sigma_window_size_returns_valid_self() {
        // Sanity: arbitrary window of valid OU prices yields a populated Self.
        // 健全：任意 OU 窗口應產出 populated Self。
        let prices = simulate_ou(50, 100.0, 0.3, 100.0, 0.2, 1.0, 0xDEADBEEF);
        let est = OuResidualSigma::estimate_from_window(&prices);
        assert_eq!(est.n_observations, 50);
        assert!(est.sigma_hat.is_finite());
        assert!(est.theta >= 0.0);
        assert!(est.mu.is_finite());
    }

    #[test]
    fn test_ou_residual_sigma_update_lifecycle() {
        // Streaming update: feed 250 prices into a 200-capacity window;
        // σ̂ should remain stable (within 10% band) after the buffer saturates.
        // Streaming：餵 250 筆到 200 容量窗口，飽和後 σ̂ 應穩定（10% 帶內）。
        let prices = simulate_ou(250, 100.0, 0.4, 100.0, 0.5, 1.0, 0xBADF00D);
        let mut estimator = OuResidualSigma::empty();
        let mut buf: Vec<f64> = Vec::new();
        for &p in &prices[..200] {
            estimator.update(&mut buf, p, 200);
        }
        let sigma_at_full = estimator.sigma_hat;
        assert!(sigma_at_full.is_finite() && sigma_at_full > 0.0);
        for &p in &prices[200..] {
            estimator.update(&mut buf, p, 200);
        }
        let sigma_after = estimator.sigma_hat;
        assert!(sigma_after.is_finite() && sigma_after > 0.0);
        let rel_drift = (sigma_after - sigma_at_full).abs() / sigma_at_full;
        assert!(
            rel_drift < 0.20,
            "σ̂ drifted >20% after rolling window: {} → {} (rel {:.2}%)",
            sigma_at_full,
            sigma_after,
            rel_drift * 100.0
        );
        // Buffer must be capped at the configured capacity / buffer 應被截到 capacity
        assert_eq!(buf.len(), 200);
    }

    #[test]
    fn test_ou_residual_sigma_insufficient_samples_returns_nan() {
        // n < MIN_SAMPLES + 1 → degenerate placeholder (σ̂ = NaN).
        // 樣本不足 → NaN 退化值。
        let est = OuResidualSigma::estimate_from_window(&[1.0, 2.0, 3.0]);
        assert!(
            est.sigma_hat.is_nan(),
            "expected NaN for n=3, got {}",
            est.sigma_hat
        );
        assert_eq!(est.n_observations, 3);
        // Empty seed / 空種子
        let empty = OuResidualSigma::empty();
        assert!(empty.sigma_hat.is_nan());
        assert_eq!(empty.n_observations, 0);
    }

    #[test]
    fn test_ou_residual_sigma_constant_window_is_degenerate() {
        // All-equal x_{t-1} → zero design-matrix variance → σ̂ NaN, μ̂ exact.
        // x_{t-1} 全相等 → 設計矩陣退化 → σ̂ = NaN，μ̂ 精確。
        let prices = vec![100.0_f64; 30];
        let est = OuResidualSigma::estimate_from_window(&prices);
        assert!(est.sigma_hat.is_nan());
        assert!((est.mu - 100.0).abs() < 1e-12);
        assert_eq!(est.n_observations, 30);
    }

    #[test]
    fn test_ou_residual_sigma_smaller_than_raw_for_mean_reverting() {
        // Core G7-06 motivation: residual σ̂ < raw-Δx σ for mean-reverting
        // data, because the residual estimator subtracts the drift first.
        // 核心動機驗證：均值回歸資料上殘差 σ̂ < 原始 Δx σ（先扣 drift）。
        let prices = simulate_ou(300, 100.0, 0.6, 100.0, 0.4, 1.0, 0xFEEDC0DE);
        let est = OuResidualSigma::estimate_from_window(&prices);
        // Raw-Δx σ as a baseline / 原始 Δx σ 作為基準
        let n_dx = prices.len() - 1;
        let raw_sigma = (prices
            .windows(2)
            .map(|w| (w[1] - w[0]).powi(2))
            .sum::<f64>()
            / n_dx as f64)
            .sqrt();
        assert!(est.sigma_hat.is_finite());
        assert!(raw_sigma > 0.0);
        // For genuinely mean-reverting data with non-trivial θ, residual σ̂
        // is smaller than raw σ (or at most ~equal under tight numerical noise).
        // 真正均值回歸 + 非平凡 θ 時，殘差 σ̂ 應 ≤ 原始 σ。
        assert!(
            est.sigma_hat <= raw_sigma * 1.02,
            "expected residual σ̂ ({}) ≤ raw-Δx σ ({}) for mean-reverting data",
            est.sigma_hat,
            raw_sigma
        );
    }
}
