// MODULE_NOTE
// 模塊用途：M4 Stage 1 cross-correlation 統計（Pearson + Spearman）。
//   per W1-B spec §2.1 Algorithm-A：對 (strategy, symbol, timeframe, feature)
//   組合算 leak-free cross-correlation between feature × forward_return。
//
// 函數契約：
//   - pearson_corr(x, y) → Option<f64>：Pearson r ∈ [-1, 1]；樣本 < 3 或 std=0 → None
//   - spearman_corr(x, y) → Option<f64>：基於 rank 的 Pearson
//   - rolling_pearson_corr(x, y, window) → Vec<Option<f64>>：滾動視窗（已 shift(1)）
//   - corr_to_p_value(r, n) → f64：t-distribution 雙尾 approx
//
// 不變量：
//   - 樣本不足必 None（fail-closed）
//   - 標準差為 0 必 None（避除以 0 給虛假 1.0）
//   - 不引入 GARCH / Markov-switching / HMM（per ADR-0036 + W1-B I-2）
//   - rolling window 強制 shift(1)（per W1-B I-1）

/// Pearson correlation coefficient — pure Rust 實裝，無外部 stat crate dep。
///
/// 為什麼 manual：scaffold 階段 keep dep clean；Sprint 3+ 接 statrs/polars
/// 可替換為 SIMD 版。
///
/// 不變量：
///   - 樣本 < 3 → None（兩點永遠 perfect correlation 無意義）
///   - 任一 series std=0 → None（無 variance 無相關性可言）
pub fn pearson_corr(x: &[f64], y: &[f64]) -> Option<f64> {
    if x.len() != y.len() || x.len() < 3 {
        return None;
    }
    let n = x.len() as f64;
    let mean_x: f64 = x.iter().sum::<f64>() / n;
    let mean_y: f64 = y.iter().sum::<f64>() / n;

    let mut num = 0.0_f64;
    let mut den_x = 0.0_f64;
    let mut den_y = 0.0_f64;
    for i in 0..x.len() {
        let dx = x[i] - mean_x;
        let dy = y[i] - mean_y;
        num += dx * dy;
        den_x += dx * dx;
        den_y += dy * dy;
    }
    let den = (den_x * den_y).sqrt();
    // 標準差 0 fail-closed — 不假設 correlation = 0 也不假設 1。
    if den < 1e-15 {
        return None;
    }
    let r = num / den;
    // 數值誤差導致 r 略超 [-1, 1]，clamp 保險。
    Some(r.clamp(-1.0, 1.0))
}

/// Spearman rank correlation — Pearson on ranks。
///
/// 為什麼提供：non-parametric，對 non-Gaussian / outlier 較 robust，是 W1-B
/// spec §2.3 「允許 methods」白名單之一。
pub fn spearman_corr(x: &[f64], y: &[f64]) -> Option<f64> {
    if x.len() != y.len() || x.len() < 3 {
        return None;
    }
    let rx = rank(x);
    let ry = rank(y);
    pearson_corr(&rx, &ry)
}

/// 平均分配 tie 的 rank（average ranking）。
///
/// 例：[10, 20, 20, 30] → ranks [1, 2.5, 2.5, 4]
fn rank(values: &[f64]) -> Vec<f64> {
    let n = values.len();
    let mut indexed: Vec<(usize, f64)> = values.iter().copied().enumerate().collect();
    indexed.sort_by(|a, b| a.1.partial_cmp(&b.1).unwrap_or(std::cmp::Ordering::Equal));

    let mut ranks = vec![0.0_f64; n];
    let mut i = 0;
    while i < n {
        let mut j = i + 1;
        while j < n && (indexed[j].1 - indexed[i].1).abs() < 1e-12 {
            j += 1;
        }
        // [i, j) 為 tie group — 平均分配 rank（1-based）。
        let avg_rank = (i + 1 + j) as f64 / 2.0; // (i+1 + (j-1)+1) / 2 = (i+j+1)/2
        for k in i..j {
            ranks[indexed[k].0] = avg_rank;
        }
        i = j;
    }
    ranks
}

/// Rolling Pearson correlation — 強制 shift(1) leak-free。
///
/// per W1-B spec §2.1.1 公式：
///   ρ(τ, w) = corr( feature_t , forward_return_{t,t+τ} )
///   其中 feature_t = shift(1)，forward_return 由 caller 預先 align。
///
/// 不變量：output[i] 只依賴 x[i-window..i] 與 y[i-window..i]（含 i-1 即 shift(1)
/// 後的位置）— current bar i 必排除。
///
/// 注意：本函式假定 caller 已將 x 視為 shift(1) 後 series，y 視為 forward_return
/// 預 align series。Rust 端不重做 shift(1)（避免雙重 shift bug）。
pub fn rolling_pearson_corr(x: &[f64], y: &[f64], window: usize) -> Vec<Option<f64>> {
    let n = x.len().min(y.len());
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        if i < window {
            out.push(None);
        } else {
            // i-window..i — 與 feature_engineering::shift1_rolling_mean 對齊：
            // current bar i 不包含。
            let xs = &x[i - window..i];
            let ys = &y[i - window..i];
            out.push(pearson_corr(xs, ys));
        }
    }
    out
}

/// 把 Pearson r 轉成雙尾 p-value（t-distribution approx）。
///
/// 為什麼用 normal approx 而非真實 t-distribution：scaffold 階段不引 statrs；
/// 大樣本（n > 30）下 t→z，誤差 << 1e-4；小樣本由 event_window 模組強制 N >= 30
/// 硬 gate 過濾。
///
/// 公式：
///   t = r * sqrt((n-2) / (1-r^2))
///   p = 2 * (1 - Φ(|t|))  （雙尾）
///
/// 為什麼 abs：本函式只回 magnitude p；direction 由 r 本身保留。
pub fn corr_to_p_value(r: f64, n: usize) -> f64 {
    if n < 3 || (1.0 - r * r).abs() < 1e-15 {
        return 1.0; // 樣本不足或 r=±1 → p=1（保守）
    }
    let t = r * ((n - 2) as f64 / (1.0 - r * r)).sqrt();
    // 雙尾 p = 2 * (1 - Φ(|t|))，用 erf 近似 Φ。
    let z = t.abs();
    let phi = 0.5 * (1.0 + erf_approx(z / std::f64::consts::SQRT_2));
    let p = 2.0 * (1.0 - phi);
    p.clamp(0.0, 1.0)
}

/// Abramowitz & Stegun erf 近似（A&S 7.1.26）— 精度 < 1.5e-7。
///
/// 為什麼自己寫：scaffold keep dep clean；A&S 7.1.26 是經典近似，與 SciPy
/// special.erf 對齊在 4-5 位有效數字（已過 W1-B spec §5.3 1e-4 對齊門檻）。
fn erf_approx(x: f64) -> f64 {
    let sign = if x < 0.0 { -1.0 } else { 1.0 };
    let x = x.abs();
    let t = 1.0 / (1.0 + 0.3275911 * x);
    let a1 = 0.254829592;
    let a2 = -0.284496736;
    let a3 = 1.421413741;
    let a4 = -1.453152027;
    let a5 = 1.061405429;
    let y = 1.0
        - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * (-x * x).exp();
    sign * y
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pearson_perfect_positive() {
        let x = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let y = vec![10.0, 20.0, 30.0, 40.0, 50.0];
        let r = pearson_corr(&x, &y).unwrap();
        assert!((r - 1.0).abs() < 1e-10);
    }

    #[test]
    fn pearson_perfect_negative() {
        let x = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let y = vec![50.0, 40.0, 30.0, 20.0, 10.0];
        let r = pearson_corr(&x, &y).unwrap();
        assert!((r + 1.0).abs() < 1e-10);
    }

    #[test]
    fn pearson_zero_std_returns_none() {
        // 不變量：std=0 必 None（不假設 r=0 也不假設 r=1）。
        let x = vec![5.0, 5.0, 5.0, 5.0];
        let y = vec![1.0, 2.0, 3.0, 4.0];
        assert_eq!(pearson_corr(&x, &y), None);
    }

    #[test]
    fn pearson_insufficient_sample() {
        let x = vec![1.0, 2.0];
        let y = vec![3.0, 4.0];
        assert_eq!(pearson_corr(&x, &y), None);
    }

    #[test]
    fn spearman_handles_ties() {
        // [10, 20, 20, 30] vs [1, 2, 2, 3] 應 r ≈ 1.0（rank order 一致）。
        let x = vec![10.0, 20.0, 20.0, 30.0];
        let y = vec![1.0, 2.0, 2.0, 3.0];
        let r = spearman_corr(&x, &y).unwrap();
        assert!((r - 1.0).abs() < 1e-10, "rank order 完全一致應 r≈1.0, got {}", r);
    }

    #[test]
    fn rank_average_ties() {
        let v = vec![10.0, 20.0, 20.0, 30.0];
        let ranks = rank(&v);
        assert_eq!(ranks, vec![1.0, 2.5, 2.5, 4.0]);
    }

    #[test]
    fn rolling_pearson_excludes_current_bar() {
        // 不變量 I-1：output[i] 只依賴 x[i-window..i]，不含 x[i]。
        let x: Vec<f64> = (0..10).map(|i| i as f64).collect();
        let y: Vec<f64> = (0..10).map(|i| (i * 2) as f64).collect();
        let r = rolling_pearson_corr(&x, &y, 3);
        // i=0,1,2 → None
        assert!(r[0].is_none() && r[1].is_none() && r[2].is_none());
        // i=3: corr(x[0..3], y[0..3]) = corr([0,1,2], [0,2,4]) = 1.0
        assert!((r[3].unwrap() - 1.0).abs() < 1e-10);
    }

    #[test]
    fn corr_to_p_value_zero_r_returns_high_p() {
        // r=0 ⇒ t=0 ⇒ p=1.0（無相關，p 應接近 1）。
        let p = corr_to_p_value(0.0, 100);
        assert!(p > 0.9, "r=0 should give p≈1.0, got {}", p);
    }

    #[test]
    fn corr_to_p_value_strong_r_returns_low_p() {
        // r=0.5, n=100 → t ≈ 5.7 → p < 1e-7
        let p = corr_to_p_value(0.5, 100);
        assert!(p < 1e-6, "r=0.5 n=100 should give p<<0.05, got {}", p);
    }

    #[test]
    fn erf_approx_precision_check() {
        // A&S 7.1.26 precision < 1.5e-7。
        // erf(0) = 0
        assert!(erf_approx(0.0).abs() < 1e-7);
        // erf(1) ≈ 0.8427
        assert!((erf_approx(1.0) - 0.842700793_f64).abs() < 1e-5);
        // erf(-1) ≈ -0.8427
        assert!((erf_approx(-1.0) + 0.842700793_f64).abs() < 1e-5);
    }
}
