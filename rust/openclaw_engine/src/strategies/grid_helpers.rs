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
}
