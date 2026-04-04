//! Volatility indicators: Bollinger Bands, ATR, EWMA Vol, Hurst Exponent.
//! 波動率指標：布林帶、ATR、EWMA 波動率、赫斯特指數。

use serde::{Deserialize, Serialize};

use super::kahan_sum;

// ═══════════════════════════════════════════════════════════════════════════════
// Bollinger Bands / 布林帶
// ═══════════════════════════════════════════════════════════════════════════════

/// Bollinger Bands result.
/// 布林帶結果。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BollingerResult {
    pub upper: f64,
    pub middle: f64,
    pub lower: f64,
    pub bandwidth: f64,
    pub percent_b: f64,
}

/// Bollinger Bands with configurable period and standard deviation multiplier.
/// 可配置週期和標準差倍數的布林帶。
pub fn bollinger(close: &[f64], period: usize, std_mult: f64) -> Option<BollingerResult> {
    if period == 0 || close.len() < period {
        return None;
    }
    let window = &close[close.len() - period..];
    let mean = kahan_sum(window) / period as f64;

    // Standard deviation (population) with Kahan summation of squared deviations
    let sq_devs: Vec<f64> = window.iter().map(|&v| (v - mean) * (v - mean)).collect();
    let variance = kahan_sum(&sq_devs) / period as f64;
    let std_dev = variance.sqrt();

    let upper = mean + std_mult * std_dev;
    let lower = mean - std_mult * std_dev;
    let bandwidth = if mean > 1e-15 {
        (upper - lower) / mean
    } else {
        0.0
    };
    let last = *close.last()?;
    let band_range = upper - lower;
    let percent_b = if band_range > 1e-15 {
        (last - lower) / band_range
    } else {
        0.5
    };

    Some(BollingerResult {
        upper,
        middle: mean,
        lower,
        bandwidth,
        percent_b,
    })
}

// ═══════════════════════════════════════════════════════════════════════════════
// ATR — Average True Range (Wilder's smoothing) / 平均真實波幅
// ═══════════════════════════════════════════════════════════════════════════════

/// ATR calculation result (absolute and percentage).
/// ATR 計算結果（絕對值和百分比）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AtrResult {
    pub atr: f64,
    pub atr_percent: f64,
}

/// Average True Range with Wilder's smoothing.
/// 使用 Wilder 平滑的平均真實波幅。
pub fn atr(high: &[f64], low: &[f64], close: &[f64], period: usize) -> Option<AtrResult> {
    let n = high.len().min(low.len()).min(close.len());
    if period == 0 || n < period + 1 {
        return None;
    }

    // True Range series (starts from index 1)
    let mut tr_vals = Vec::with_capacity(n - 1);
    for i in 1..n {
        let tr = (high[i] - low[i])
            .max((high[i] - close[i - 1]).abs())
            .max((low[i] - close[i - 1]).abs());
        tr_vals.push(tr);
    }

    // Initial ATR: Kahan average of first `period` TR values
    let mut atr_val = kahan_sum(&tr_vals[..period]) / period as f64;

    // Wilder's smoothing
    let p = period as f64;
    for &tr in &tr_vals[period..] {
        atr_val = (atr_val * (p - 1.0) + tr) / p;
    }

    let last_close = close[n - 1];
    let atr_pct = if last_close > 1e-15 {
        atr_val / last_close * 100.0
    } else {
        0.0
    };

    Some(AtrResult {
        atr: atr_val,
        atr_percent: atr_pct,
    })
}

// ═══════════════════════════════════════════════════════════════════════════════
// Hurst Exponent / 赫斯特指數
// ═══════════════════════════════════════════════════════════════════════════════

/// Hurst Exponent result with market regime classification.
/// 赫斯特指數結果，含市場狀態分類。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HurstResult {
    pub hurst: f64,
    pub regime: String,
}

/// Hurst Exponent via R/S analysis with log-log OLS regression.
/// 通過 R/S 分析和對數-對數 OLS 回歸計算赫斯特指數。
pub fn hurst(close: &[f64], min_lag: usize, max_lag: usize) -> Option<HurstResult> {
    if min_lag < 2 || min_lag >= max_lag {
        return None;
    }

    // Pre-check: need at least min_lag+1 raw data points to even attempt.
    // 前置檢查：至少需要 min_lag+1 個原始數據點。
    if close.len() < min_lag + 1 {
        return None;
    }

    // Filter out pairs where either price <= 0 to avoid NaN/Inf in log returns.
    // 過濾掉任一價格 <= 0 的相鄰對，避免 log 計算產生 NaN/Inf。
    let returns: Vec<f64> = close
        .windows(2)
        .filter(|w| w[0] > 0.0 && w[1] > 0.0)
        .map(|w| (w[1] / w[0]).ln())
        .collect();

    let n_returns = returns.len();
    if n_returns < min_lag {
        // Prices filtered out caused insufficient valid returns — return neutral 0.5.
        // 因價格過濾導致有效 return 不足 — 返回中性值 0.5。
        return Some(HurstResult {
            hurst: 0.5,
            regime: "random_walk".to_string(),
        });
    }

    // Dynamic max_lag clipping: prevent chunk count from being 0.
    // 動態裁剪 max_lag：防止 chunk 數為 0。
    let max_lag = max_lag.min(n_returns / 2).max(min_lag);

    let mut log_n = Vec::new();
    let mut log_rs = Vec::new();

    for lag in min_lag..=max_lag {
        let chunks = returns.len() / lag;
        if chunks == 0 {
            continue;
        }

        let mut rs_sum = 0.0;
        let mut valid_chunks = 0usize;

        for c in 0..chunks {
            let chunk = &returns[c * lag..(c + 1) * lag];
            let mean = kahan_sum(chunk) / lag as f64;

            // Cumulative deviations
            let mut cum_dev = Vec::with_capacity(lag);
            let mut running = 0.0;
            for &r in chunk {
                running += r - mean;
                cum_dev.push(running);
            }

            let range = cum_dev.iter().cloned().fold(f64::NEG_INFINITY, f64::max)
                - cum_dev.iter().cloned().fold(f64::INFINITY, f64::min);

            // Standard deviation
            let sq_devs: Vec<f64> = chunk.iter().map(|&r| (r - mean) * (r - mean)).collect();
            let std_dev = (kahan_sum(&sq_devs) / lag as f64).sqrt();

            if std_dev > 1e-15 {
                rs_sum += range / std_dev;
                valid_chunks += 1;
            }
        }

        if valid_chunks > 0 {
            let avg_rs = rs_sum / valid_chunks as f64;
            log_n.push((lag as f64).ln());
            log_rs.push(avg_rs.ln());
        }
    }

    if log_n.len() < 2 {
        return None;
    }

    // OLS: y = a + b*x where b = Hurst exponent
    // Use Kahan summation for all accumulators [V3-QC-2].
    // 所有累加器使用 Kahan 求和 [V3-QC-2]。
    let n = log_n.len() as f64;
    let sum_x = kahan_sum(&log_n);
    let sum_y = kahan_sum(&log_rs);
    let xy_products: Vec<f64> = log_n.iter().zip(log_rs.iter()).map(|(x, y)| x * y).collect();
    let sum_xy = kahan_sum(&xy_products);
    let x_squares: Vec<f64> = log_n.iter().map(|x| x * x).collect();
    let sum_x2 = kahan_sum(&x_squares);

    let denom = n * sum_x2 - sum_x * sum_x;
    if denom.abs() < 1e-15 {
        return None;
    }

    // Clamp result to [0.0, 1.0] — valid Hurst range.
    // 將結果鉗位到 [0.0, 1.0] — 有效赫斯特指數範圍。
    let h = ((n * sum_xy - sum_x * sum_y) / denom).clamp(0.0, 1.0);

    let regime = if h > 0.60 {
        "trending".to_string()
    } else if h < 0.40 {
        "mean_reverting".to_string()
    } else {
        "random_walk".to_string()
    };

    Some(HurstResult { hurst: h, regime })
}

// ═══════════════════════════════════════════════════════════════════════════════
// EWMA Vol — Exponentially Weighted Moving Average Volatility
// EWMA 波動率 — 指數加權移動平均波動率
// ═══════════════════════════════════════════════════════════════════════════════

/// EWMA volatility result with regime classification.
/// EWMA 波動率結果，含波動率狀態分類。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EwmaVolResult {
    pub ewma_vol: f64,
    pub vol_regime: String,
}

/// EWMA volatility. Lambda typically 0.97 for hourly data.
/// EWMA 波動率。Lambda 通常為 0.97（小時數據）。
pub fn ewma_vol(close: &[f64], lambda: f64) -> Option<EwmaVolResult> {
    if close.len() < 3 || !(0.0..1.0).contains(&lambda) {
        return None;
    }

    // Log returns
    let returns: Vec<f64> = close.windows(2).map(|w| (w[1] / w[0]).ln()).collect();
    if returns.is_empty() {
        return None;
    }

    // EWMA variance
    let mut variance = returns[0] * returns[0];
    for &r in &returns[1..] {
        variance = lambda * variance + (1.0 - lambda) * r * r;
    }
    let ewma = variance.sqrt();

    // Historical mean volatility for regime detection
    let sq_returns: Vec<f64> = returns.iter().map(|r| r * r).collect();
    let hist_mean_var = kahan_sum(&sq_returns) / returns.len() as f64;
    let hist_mean_vol = hist_mean_var.sqrt();

    let regime = if hist_mean_vol < 1e-15 || ewma < 0.6 * hist_mean_vol {
        "low".to_string()
    } else if ewma > 1.5 * hist_mean_vol {
        "high".to_string()
    } else {
        "normal".to_string()
    };

    Some(EwmaVolResult {
        ewma_vol: ewma,
        vol_regime: regime,
    })
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    const CLOSE_20: [f64; 20] = [
        44.0, 44.25, 44.50, 43.75, 44.50, 44.25, 44.00, 43.50, 43.25, 43.75,
        44.00, 44.50, 44.75, 45.00, 45.50, 45.75, 46.00, 45.50, 45.25, 45.00,
    ];

    // --- Bollinger ---
    #[test]
    fn test_bollinger_basic() {
        let r = bollinger(&CLOSE_20, 20, 2.0).unwrap();
        assert!(r.upper > r.middle);
        assert!(r.middle > r.lower);
        assert!(r.bandwidth > 0.0);
        assert!(r.percent_b >= 0.0 && r.percent_b <= 1.5);
    }

    #[test]
    fn test_bollinger_flat() {
        let flat = vec![100.0; 20];
        let r = bollinger(&flat, 20, 2.0).unwrap();
        assert!((r.upper - 100.0).abs() < 1e-10);
        assert!((r.lower - 100.0).abs() < 1e-10);
    }

    #[test]
    fn test_bollinger_edge() {
        assert!(bollinger(&[1.0], 5, 2.0).is_none());
    }

    // --- ATR ---
    #[test]
    fn test_atr_basic() {
        let high: Vec<f64> = CLOSE_20.iter().map(|c| c + 0.5).collect();
        let low: Vec<f64> = CLOSE_20.iter().map(|c| c - 0.5).collect();
        let r = atr(&high, &low, &CLOSE_20, 14).unwrap();
        assert!(r.atr > 0.0);
        assert!(r.atr_percent > 0.0);
    }

    #[test]
    fn test_atr_edge() {
        assert!(atr(&[1.0], &[0.5], &[0.8], 1).is_none()); // need period+1
        let h = vec![10.0; 5];
        let l = vec![9.0; 5];
        let c = vec![9.5; 5];
        let r = atr(&h, &l, &c, 3).unwrap();
        assert!(r.atr > 0.0);
    }

    // --- Hurst ---
    #[test]
    fn test_hurst_trending() {
        // Strong uptrend should yield H > 0.5
        let data: Vec<f64> = (0..200).map(|i| 100.0 + i as f64 * 0.5).collect();
        let r = hurst(&data, 10, 50).unwrap();
        assert!(r.hurst > 0.4); // trending tendency
    }

    #[test]
    fn test_hurst_edge() {
        assert!(hurst(&[1.0; 10], 10, 50).is_none()); // too little data
        assert!(hurst(&CLOSE_20, 5, 3).is_none()); // min_lag >= max_lag
    }

    // --- EWMA Vol ---
    #[test]
    fn test_ewma_vol_basic() {
        let r = ewma_vol(&CLOSE_20, 0.97).unwrap();
        assert!(r.ewma_vol >= 0.0);
        assert!(
            r.vol_regime == "low" || r.vol_regime == "normal" || r.vol_regime == "high"
        );
    }

    #[test]
    fn test_ewma_vol_edge() {
        assert!(ewma_vol(&[1.0, 2.0], 0.97).is_none()); // need >= 3
        assert!(ewma_vol(&CLOSE_20, 1.0).is_none()); // lambda must be < 1
        assert!(ewma_vol(&CLOSE_20, -0.1).is_none()); // lambda must be >= 0
    }
}
