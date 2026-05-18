//! Momentum / direction indicators: RSI, Stochastic, ADX.
//! 動量/方向指標：RSI、隨機指標、ADX。

use serde::{Deserialize, Serialize};

use super::kahan_sum;

// ═══════════════════════════════════════════════════════════════════════════════
// RSI — Relative Strength Index (Wilder's smoothing) / 相對強弱指數
// ═══════════════════════════════════════════════════════════════════════════════

/// Relative Strength Index using Wilder's smoothing. Returns 0-100.
/// 使用 Wilder 平滑的相對強弱指數。返回 0-100。
pub fn rsi(close: &[f64], period: usize) -> Option<f64> {
    if period == 0 || close.len() < period + 1 {
        return None;
    }

    let changes: Vec<f64> = close.windows(2).map(|w| w[1] - w[0]).collect();

    // Initial average gain/loss over first `period` changes
    let init = &changes[..period];
    let mut avg_gain = kahan_sum(
        &init
            .iter()
            .map(|&c| if c > 0.0 { c } else { 0.0 })
            .collect::<Vec<_>>(),
    ) / period as f64;
    let mut avg_loss = kahan_sum(
        &init
            .iter()
            .map(|&c| if c < 0.0 { -c } else { 0.0 })
            .collect::<Vec<_>>(),
    ) / period as f64;

    // Wilder's smoothing for remaining changes
    let p = period as f64;
    for &change in &changes[period..] {
        let gain = if change > 0.0 { change } else { 0.0 };
        let loss = if change < 0.0 { -change } else { 0.0 };
        avg_gain = (avg_gain * (p - 1.0) + gain) / p;
        avg_loss = (avg_loss * (p - 1.0) + loss) / p;
    }

    if avg_loss < 1e-15 {
        return Some(100.0);
    }
    let rs = avg_gain / avg_loss;
    Some(100.0 - 100.0 / (1.0 + rs))
}

// ═══════════════════════════════════════════════════════════════════════════════
// Stochastic Oscillator / 隨機指標
// ═══════════════════════════════════════════════════════════════════════════════

/// Stochastic oscillator result (%K and %D).
/// 隨機指標結果（%K 和 %D）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StochResult {
    pub k: f64,
    pub d: f64,
}

/// 隨機指標 %K 和 %D（%K 的 SMA），**含當前 bar**，存在 look-ahead bias。
///
/// 為什麼保留：本函數有既存呼叫端（`indicators/mod.rs` 預設 IndicatorSnapshot、
/// `tests/golden_dataset.rs` 數值回歸黃金集），刪除或改語義會破壞回歸基準。
/// 新 alpha 研究 / 策略 gate / 任何 forecast-vs-current 判斷請改用 `stochastic_prior()`，
/// 它排除當前 bar，與 `donchian_prior()` 是同一個 leak-free 設計模式。
///
/// 不變量：呼叫端不得用 `stochastic()` 判斷「當前 bar 是否突破近 N 根 high/low」，
/// 這正是 `rolling(N).max()` 同類 look-ahead leak（見 memory
/// `feedback_indicator_lookahead_bias`）。
pub fn stochastic(
    high: &[f64],
    low: &[f64],
    close: &[f64],
    k_period: usize,
    d_period: usize,
) -> Option<StochResult> {
    let n = high.len().min(low.len()).min(close.len());
    if k_period == 0 || d_period == 0 || n < k_period + d_period - 1 {
        return None;
    }

    // 計算最近 d_period 個 %K 值
    let mut k_values = Vec::with_capacity(d_period);
    for i in (n - d_period)..n {
        let start = i + 1 - k_period;
        let h_max = high[start..=i]
            .iter()
            .cloned()
            .fold(f64::NEG_INFINITY, f64::max);
        let l_min = low[start..=i].iter().cloned().fold(f64::INFINITY, f64::min);
        let range = h_max - l_min;
        let k_val = if range > 1e-15 {
            (close[i] - l_min) / range * 100.0
        } else {
            50.0
        };
        k_values.push(k_val);
    }

    let k = *k_values.last()?;
    let d = kahan_sum(&k_values) / d_period as f64;

    Some(StochResult { k, d })
}

/// 隨機指標 %K 和 %D 的 leak-free 變體：排除當前 bar，僅用 close[..n-1] / high[..n-1] / low[..n-1]。
///
/// 為什麼：`stochastic()` 用 `high[start..=i]` 含當前 bar，當當前 bar 創新高/低時
/// %K 必然落在 0 或 100 附近 — 對「當前 bar 是否突破近 N 根 high/low」這類判斷
/// 構成 look-ahead bias。研究路徑與 forecast-vs-current 判斷必須用本函數。
///
/// 不變量：與 `donchian_prior()` 同一設計 — 先切掉當前 bar 再算原始指標。
/// 若資料量不足 `k_period + d_period`（含一根當前 bar 預留），返回 None。
pub fn stochastic_prior(
    high: &[f64],
    low: &[f64],
    close: &[f64],
    k_period: usize,
    d_period: usize,
) -> Option<StochResult> {
    let n = high.len().min(low.len()).min(close.len());
    // 至少需要 k_period + d_period 根（其中 1 根作為當前 bar 被排除）
    if k_period == 0 || d_period == 0 || n < k_period + d_period {
        return None;
    }
    stochastic(
        &high[..n - 1],
        &low[..n - 1],
        &close[..n - 1],
        k_period,
        d_period,
    )
}

// ═══════════════════════════════════════════════════════════════════════════════
// ADX — Average Directional Index / 平均方向指數
// ═══════════════════════════════════════════════════════════════════════════════

/// ADX calculation result with +DI and -DI.
/// ADX 計算結果，含 +DI 和 -DI。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AdxResult {
    pub adx: f64,
    pub plus_di: f64,
    pub minus_di: f64,
}

/// Average Directional Index (Wilder's method). Requires 2*period+1 data points.
/// 平均方向指數（Wilder 方法）。需要 2*period+1 個數據點。
pub fn adx(high: &[f64], low: &[f64], close: &[f64], period: usize) -> Option<AdxResult> {
    let n = high.len().min(low.len()).min(close.len());
    if period == 0 || n < 2 * period + 1 {
        return None;
    }

    let p = period as f64;

    // True Range, +DM, -DM for each bar (starting from index 1)
    let len = n - 1;
    let mut tr_vals = Vec::with_capacity(len);
    let mut plus_dm_vals = Vec::with_capacity(len);
    let mut minus_dm_vals = Vec::with_capacity(len);

    for i in 1..n {
        let h_diff = high[i] - high[i - 1];
        let l_diff = low[i - 1] - low[i];

        let plus_dm = if h_diff > l_diff && h_diff > 0.0 {
            h_diff
        } else {
            0.0
        };
        let minus_dm = if l_diff > h_diff && l_diff > 0.0 {
            l_diff
        } else {
            0.0
        };

        let tr = (high[i] - low[i])
            .max((high[i] - close[i - 1]).abs())
            .max((low[i] - close[i - 1]).abs());

        tr_vals.push(tr);
        plus_dm_vals.push(plus_dm);
        minus_dm_vals.push(minus_dm);
    }

    // Initial smoothed sums (Kahan for first period)
    let mut atr_smooth = kahan_sum(&tr_vals[..period]);
    let mut plus_dm_smooth = kahan_sum(&plus_dm_vals[..period]);
    let mut minus_dm_smooth = kahan_sum(&minus_dm_vals[..period]);

    // Wilder's smoothing for the rest, collecting DX values
    let mut dx_values = Vec::with_capacity(len - period);

    for i in period..len {
        atr_smooth = atr_smooth - atr_smooth / p + tr_vals[i];
        plus_dm_smooth = plus_dm_smooth - plus_dm_smooth / p + plus_dm_vals[i];
        minus_dm_smooth = minus_dm_smooth - minus_dm_smooth / p + minus_dm_vals[i];

        let plus_di = if atr_smooth > 1e-15 {
            100.0 * plus_dm_smooth / atr_smooth
        } else {
            0.0
        };
        let minus_di = if atr_smooth > 1e-15 {
            100.0 * minus_dm_smooth / atr_smooth
        } else {
            0.0
        };

        let di_sum = plus_di + minus_di;
        let dx = if di_sum > 1e-15 {
            100.0 * (plus_di - minus_di).abs() / di_sum
        } else {
            0.0
        };

        dx_values.push((dx, plus_di, minus_di));
    }

    if dx_values.len() < period {
        return None;
    }

    // First ADX: average of first `period` DX values (Kahan)
    let first_dx: Vec<f64> = dx_values[..period].iter().map(|(dx, _, _)| *dx).collect();
    let mut adx_val = kahan_sum(&first_dx) / p;

    // Smooth ADX
    for &(dx, _, _) in &dx_values[period..] {
        adx_val = (adx_val * (p - 1.0) + dx) / p;
    }

    let (_, plus_di, minus_di) = *dx_values.last()?;

    Some(AdxResult {
        adx: adx_val,
        plus_di,
        minus_di,
    })
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    const CLOSE_20: [f64; 20] = [
        44.0, 44.25, 44.50, 43.75, 44.50, 44.25, 44.00, 43.50, 43.25, 43.75, 44.00, 44.50, 44.75,
        45.00, 45.50, 45.75, 46.00, 45.50, 45.25, 45.00,
    ];

    // --- RSI ---
    #[test]
    fn test_rsi_basic() {
        let r = rsi(&CLOSE_20, 14).unwrap();
        assert!(r >= 0.0 && r <= 100.0);
    }

    #[test]
    fn test_rsi_all_up() {
        let data: Vec<f64> = (0..20).map(|i| 100.0 + i as f64).collect();
        let r = rsi(&data, 14).unwrap();
        assert!((r - 100.0).abs() < 1e-10);
    }

    #[test]
    fn test_rsi_edge() {
        assert!(rsi(&[1.0, 2.0], 3).is_none());
        assert!(rsi(&[], 1).is_none());
    }

    // --- Stochastic ---
    #[test]
    fn test_stochastic_basic() {
        let high: Vec<f64> = CLOSE_20.iter().map(|c| c + 0.5).collect();
        let low: Vec<f64> = CLOSE_20.iter().map(|c| c - 0.5).collect();
        let r = stochastic(&high, &low, &CLOSE_20, 14, 3).unwrap();
        assert!(r.k >= 0.0 && r.k <= 100.0);
        assert!(r.d >= 0.0 && r.d <= 100.0);
    }

    #[test]
    fn test_stochastic_edge() {
        assert!(stochastic(&[1.0], &[0.5], &[0.8], 5, 3).is_none());
    }

    #[test]
    fn test_stochastic_prior_excludes_current_bar() {
        // 設計與 donchian_prior 同模式：當前 bar 放極端值，驗證 leak-free 變體確實排除。
        // stochastic(14, 3) 需要 n >= 14+3-1 = 16；stochastic_prior 需要 n >= 14+3 = 17。
        // 用 17 根 ascending series，當前 bar (idx 16) 放 9999 / -9999 / 5000 極端值。
        let mut high: Vec<f64> = (0..17).map(|i| 100.0 + i as f64).collect();
        let mut low: Vec<f64> = (0..17).map(|i| 95.0 + i as f64).collect();
        let mut close: Vec<f64> = (0..17).map(|i| 97.5 + i as f64).collect();
        high[16] = 9999.0;
        low[16] = -9999.0;
        close[16] = 5000.0;

        let leaky = stochastic(&high, &low, &close, 14, 3).expect("含當前 bar 應有結果");
        let prior = stochastic_prior(&high, &low, &close, 14, 3).expect("prior 應有結果");

        // leaky 最後一個 %K：i=16，window high[3..=16] 含 9999，low[3..=16] 含 -9999，
        //   close[16]=5000 → (5000-(-9999))/(9999-(-9999))*100 ≈ 75.00。
        // prior：完全不看 bar 16，僅看 ascending 0..=15，最後一根 close=112.5
        //   是 N-bar max，%K 必近 100。兩者必須顯著分歧，證明 prior 排除了當前 bar 污染。
        assert!(
            (leaky.k - prior.k).abs() > 10.0,
            "leaky.k={:.4} vs prior.k={:.4}：當前 bar 極端值必須讓兩者分歧 >10",
            leaky.k,
            prior.k
        );
        // %D 是 3 個 %K 的 SMA，當前 bar 只直接影響最後一個 %K，故 %D 分歧約為 %K 的 1/3；
        // 觀測值 leaky.d≈82 vs prior.d≈86，閾值取 >3 確保非零差但允許 SMA 抑制。
        assert!(
            (leaky.d - prior.d).abs() > 3.0,
            "leaky.d={:.4} vs prior.d={:.4}：當前 bar 極端值必須讓 %D 分歧 >3",
            leaky.d,
            prior.d
        );

        // 邊界：恰夠 stochastic(16 根)、不足 stochastic_prior(需 17 根)。
        let short_h = vec![100.0; 16];
        let short_l = vec![95.0; 16];
        let short_c = vec![97.5; 16];
        assert!(stochastic(&short_h, &short_l, &short_c, 14, 3).is_some());
        assert!(stochastic_prior(&short_h, &short_l, &short_c, 14, 3).is_none());
    }

    // --- ADX ---
    #[test]
    fn test_adx_basic() {
        // Need 2*14+1 = 29 data points minimum
        let n = 40;
        let close: Vec<f64> = (0..n).map(|i| 100.0 + (i as f64) * 0.3).collect();
        let high: Vec<f64> = close.iter().map(|c| c + 1.0).collect();
        let low: Vec<f64> = close.iter().map(|c| c - 1.0).collect();
        let r = adx(&high, &low, &close, 14).unwrap();
        assert!(r.adx >= 0.0 && r.adx <= 100.0);
        assert!(r.plus_di >= 0.0);
        assert!(r.minus_di >= 0.0);
    }

    #[test]
    fn test_adx_insufficient() {
        let d = vec![1.0; 20];
        assert!(adx(&d, &d, &d, 14).is_none());
    }
}
