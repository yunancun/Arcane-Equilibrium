//! Trend indicators: SMA, EMA, MACD, KAMA, Donchian Channel.
//! 趨勢指標：SMA、EMA、MACD、KAMA、唐奇安通道。

use serde::{Deserialize, Serialize};

use super::kahan_sum;

// ═══════════════════════════════════════════════════════════════════════════════
// SMA — Simple Moving Average / 簡單移動平均
// ═══════════════════════════════════════════════════════════════════════════════

/// Simple Moving Average using Kahan compensated summation [V3-QC-2].
/// 使用 Kahan 補償求和的簡單移動平均 [V3-QC-2]。
pub fn sma(close: &[f64], period: usize) -> Option<f64> {
    if period == 0 || close.len() < period {
        return None;
    }
    let window = &close[close.len() - period..];
    Some(kahan_sum(window) / period as f64)
}

// ═══════════════════════════════════════════════════════════════════════════════
// EMA — Exponential Moving Average / 指數移動平均
// ═══════════════════════════════════════════════════════════════════════════════

/// Exponential Moving Average. Seeds with SMA of first `period` values.
/// 指數移動平均。以前 `period` 個值的 SMA 為種子。
pub fn ema(close: &[f64], period: usize) -> Option<f64> {
    if period == 0 || close.len() < period {
        return None;
    }
    let k = 2.0 / (period as f64 + 1.0);
    // Seed: SMA of first `period` values
    let seed = kahan_sum(&close[..period]) / period as f64;
    let mut ema_val = seed;
    for &price in &close[period..] {
        ema_val = price * k + ema_val * (1.0 - k);
    }
    Some(ema_val)
}

/// Compute full EMA series (internal helper for MACD).
/// 計算完整 EMA 序列（MACD 內部輔助）。
fn ema_series(close: &[f64], period: usize) -> Option<Vec<f64>> {
    if period == 0 || close.len() < period {
        return None;
    }
    let k = 2.0 / (period as f64 + 1.0);
    let seed = kahan_sum(&close[..period]) / period as f64;
    let mut result = Vec::with_capacity(close.len() - period + 1);
    result.push(seed);
    let mut prev = seed;
    for &price in &close[period..] {
        let val = price * k + prev * (1.0 - k);
        result.push(val);
        prev = val;
    }
    Some(result)
}

// ═══════════════════════════════════════════════════════════════════════════════
// MACD — Moving Average Convergence Divergence / 移動平均收斂發散
// ═══════════════════════════════════════════════════════════════════════════════

/// MACD calculation result.
/// MACD 計算結果。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct MacdResult {
    pub macd: f64,
    pub signal: f64,
    pub histogram: f64,
}

/// MACD with configurable fast/slow/signal periods.
/// 可配置快/慢/信號期的 MACD。
pub fn macd(close: &[f64], fast: usize, slow: usize, signal: usize) -> Option<MacdResult> {
    if fast == 0 || slow == 0 || signal == 0 || fast >= slow {
        return None;
    }
    let fast_ema = ema_series(close, fast)?;
    let slow_ema = ema_series(close, slow)?;

    // Align: slow_ema starts at index 0 (corresponding to close[slow-1]),
    // fast_ema starts at index 0 (corresponding to close[fast-1]).
    // Offset fast_ema to align with slow_ema.
    let offset = slow - fast;
    if fast_ema.len() <= offset {
        return None;
    }

    let macd_line: Vec<f64> = fast_ema[offset..]
        .iter()
        .zip(slow_ema.iter())
        .map(|(f, s)| f - s)
        .collect();

    if macd_line.len() < signal {
        return None;
    }

    // Signal line: EMA of MACD line
    let sig_k = 2.0 / (signal as f64 + 1.0);
    let sig_seed = kahan_sum(&macd_line[..signal]) / signal as f64;
    let mut sig_val = sig_seed;
    for &m in &macd_line[signal..] {
        sig_val = m * sig_k + sig_val * (1.0 - sig_k);
    }

    let last_macd = *macd_line.last()?;
    Some(MacdResult {
        macd: last_macd,
        signal: sig_val,
        histogram: last_macd - sig_val,
    })
}

// ═══════════════════════════════════════════════════════════════════════════════
// KAMA — Kaufman Adaptive Moving Average / 考夫曼自適應移動平均
// ═══════════════════════════════════════════════════════════════════════════════

/// KAMA calculation result.
/// KAMA 計算結果。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KamaResult {
    pub kama: f64,
    pub efficiency_ratio: f64,
}

/// Kaufman Adaptive Moving Average with Kahan-summed volatility [V3-QC-2].
/// 使用 Kahan 求和波動率的考夫曼自適應移動平均 [V3-QC-2]。
pub fn kama(close: &[f64], period: usize, fast_sc: usize, slow_sc: usize) -> Option<KamaResult> {
    if period == 0 || close.len() <= period || fast_sc == 0 || slow_sc == 0 {
        return None;
    }

    let fast_alpha = 2.0 / (fast_sc as f64 + 1.0);
    let slow_alpha = 2.0 / (slow_sc as f64 + 1.0);

    // Direction: absolute price change over period
    let tail = &close[close.len() - period - 1..];
    let direction = (tail[period] - tail[0]).abs();

    // Volatility: sum of absolute day-to-day changes (Kahan)
    let abs_changes: Vec<f64> = tail.windows(2).map(|w| (w[1] - w[0]).abs()).collect();
    let volatility = kahan_sum(&abs_changes);

    let er = if volatility > 1e-15 {
        direction / volatility
    } else {
        0.0
    };

    let sc = er * (fast_alpha - slow_alpha) + slow_alpha;
    let sc_sq = sc * sc;

    // Build KAMA from first value in window
    let mut kama_val = tail[0];
    for &price in &tail[1..] {
        kama_val += sc_sq * (price - kama_val);
    }

    Some(KamaResult {
        kama: kama_val,
        efficiency_ratio: er,
    })
}

// ═══════════════════════════════════════════════════════════════════════════════
// Donchian Channel / 唐奇安通道
// ═══════════════════════════════════════════════════════════════════════════════

/// Donchian Channel result.
/// 唐奇安通道結果。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DonchianResult {
    pub upper: f64,
    pub lower: f64,
    pub middle: f64,
    pub width: f64,
}

/// Donchian Channel over the last `period` bars.
/// 最近 `period` 根 K 線的唐奇安通道。
pub fn donchian(
    high: &[f64],
    low: &[f64],
    close: &[f64],
    period: usize,
) -> Option<DonchianResult> {
    let n = high.len().min(low.len()).min(close.len());
    if period == 0 || n < period {
        return None;
    }
    let h_window = &high[n - period..n];
    let l_window = &low[n - period..n];

    let upper = h_window.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    let lower = l_window.iter().cloned().fold(f64::INFINITY, f64::min);
    let middle = (upper + lower) / 2.0;
    let width = if middle > 1e-15 {
        (upper - lower) / middle
    } else {
        0.0
    };

    Some(DonchianResult {
        upper,
        lower,
        middle,
        width,
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

    // --- SMA ---
    #[test]
    fn test_sma_basic() {
        let data = [1.0, 2.0, 3.0, 4.0, 5.0];
        assert_eq!(sma(&data, 5), Some(3.0));
        assert_eq!(sma(&data, 3), Some(4.0));
    }

    #[test]
    fn test_sma_insufficient_data() {
        assert_eq!(sma(&[1.0, 2.0], 3), None);
        assert_eq!(sma(&[], 1), None);
        assert_eq!(sma(&[1.0], 0), None);
    }

    // --- EMA ---
    #[test]
    fn test_ema_basic() {
        let data = [1.0, 2.0, 3.0, 4.0, 5.0];
        let result = ema(&data, 3).unwrap();
        // Seed = SMA(1,2,3) = 2.0, k=0.5
        // Step 4: 4*0.5 + 2*0.5 = 3.0
        // Step 5: 5*0.5 + 3*0.5 = 4.0
        assert!((result - 4.0).abs() < 1e-10);
    }

    #[test]
    fn test_ema_edge() {
        assert_eq!(ema(&[1.0], 2), None);
        // Exact period length => just the SMA seed
        let result = ema(&[2.0, 4.0, 6.0], 3).unwrap();
        assert!((result - 4.0).abs() < 1e-10);
    }

    // --- MACD ---
    #[test]
    fn test_macd_basic() {
        // Need at least slow(26)+signal(9)-1 = 34 data points
        let data: Vec<f64> = (1..=50).map(|i| 100.0 + i as f64 * 0.5).collect();
        let r = macd(&data, 12, 26, 9).unwrap();
        // In an uptrend, MACD should be positive
        assert!(r.macd > 0.0);
    }

    #[test]
    fn test_macd_insufficient() {
        assert!(macd(&CLOSE_20, 12, 26, 9).is_none());
        assert!(macd(&[1.0], 1, 2, 1).is_none()); // fast >= slow disallowed? no, fast<slow
    }

    // --- KAMA ---
    #[test]
    fn test_kama_basic() {
        let r = kama(&CLOSE_20, 10, 2, 30).unwrap();
        // KAMA should be somewhere near the price range
        assert!(r.kama > 40.0 && r.kama < 50.0);
        assert!(r.efficiency_ratio >= 0.0 && r.efficiency_ratio <= 1.0);
    }

    #[test]
    fn test_kama_edge() {
        assert!(kama(&[1.0, 2.0], 3, 2, 30).is_none());
        // Flat prices => ER ≈ 0
        let flat = vec![100.0; 15];
        let r = kama(&flat, 10, 2, 30).unwrap();
        assert!(r.efficiency_ratio < 0.01);
    }

    // --- Donchian ---
    #[test]
    fn test_donchian_basic() {
        let high = [10.0, 12.0, 11.0, 13.0, 12.5];
        let low = [8.0, 9.0, 8.5, 10.0, 9.5];
        let close = [9.0, 11.0, 10.0, 12.0, 11.0];
        let r = donchian(&high, &low, &close, 5).unwrap();
        assert!((r.upper - 13.0).abs() < 1e-10);
        assert!((r.lower - 8.0).abs() < 1e-10);
        assert!((r.middle - 10.5).abs() < 1e-10);
    }

    #[test]
    fn test_donchian_insufficient() {
        assert!(donchian(&[1.0], &[0.5], &[0.8], 3).is_none());
        assert!(donchian(&[], &[], &[], 1).is_none());
    }
}
