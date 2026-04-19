//! Price history tracker for ATR computation and spike detection.
//! 價格歷史追蹤器：用於 ATR 計算和尖峰偵測。

use std::collections::{HashMap, VecDeque};

/// Default rolling window in seconds (5 minutes) / 預設滾動窗口秒數（5 分鐘）
const DEFAULT_WINDOW_SECS: u64 = 300;

/// Minimum samples required for ATR calculation / ATR 計算所需最少樣本數
const DEFAULT_MIN_SAMPLES: usize = 10;

/// Spike detection threshold in standard deviations / 尖峰偵測閾值（標準差倍數）
const SPIKE_THRESHOLD_SIGMA: f64 = 3.0;

/// Information about a detected price spike / 偵測到的價格尖峰資訊
#[derive(Debug, Clone)]
pub struct SpikeInfo {
    /// Symbol that spiked / 發生尖峰的幣種
    pub symbol: String,
    /// Deviation from mean as percentage / 偏離均值的百分比
    pub deviation_pct: f64,
    /// Number of standard deviations / 標準差倍數
    pub sigma: f64,
    /// Current price / 當前價格
    pub current_price: f64,
    /// Mean price in window / 窗口內均價
    pub mean_price: f64,
}

/// Drop info for a single held symbol. `drop_pct` is peak-to-current fall
/// (positive); `sigma` is the current price's deviation from the window mean
/// measured in units of the window std-dev — separates true outlier events
/// from normal microcap volatility.
///
/// 單一持倉幣種的跌幅資訊。drop_pct 為窗口內峰值到當前的跌幅百分比（正值）；
/// sigma 為當前價格偏離窗口均值的標準差倍數 — 用以區分真正的離群事件與
/// 小幣正常波動。
#[derive(Debug, Clone)]
pub struct SymbolDropInfo {
    pub symbol: String,
    pub drop_pct: f64,
    pub sigma: f64,
}

/// Rolling price history tracker for per-symbol ATR and spike detection.
/// 每幣種滾動價格歷史追蹤器，用於 ATR 計算和尖峰偵測。
///
/// Maintains a time-windowed deque of (timestamp_ms, price) tuples per symbol.
/// 對每個幣種維護一個時間窗口的 (時間戳毫秒, 價格) 雙端佇列。
pub struct PriceHistoryTracker {
    /// Per-symbol price history / 每幣種價格歷史
    history: HashMap<String, VecDeque<(u64, f64)>>,
    /// Rolling window duration in seconds / 滾動窗口時長（秒）
    window_secs: u64,
    /// Minimum samples for valid ATR / ATR 有效所需最少樣本數
    min_samples: usize,
}

impl PriceHistoryTracker {
    /// Create a new tracker with default parameters.
    /// 以預設參數建立新的追蹤器。
    pub fn new() -> Self {
        Self {
            history: HashMap::new(),
            window_secs: DEFAULT_WINDOW_SECS,
            min_samples: DEFAULT_MIN_SAMPLES,
        }
    }

    /// Create a tracker with custom window and minimum samples.
    /// 以自訂窗口和最少樣本數建立追蹤器。
    pub fn with_params(window_secs: u64, min_samples: usize) -> Self {
        Self {
            history: HashMap::new(),
            window_secs,
            min_samples,
        }
    }

    /// Record a price observation, pruning stale entries beyond the window.
    /// 記錄一個價格觀測值，修剪超出窗口的過期條目。
    pub fn record(&mut self, symbol: &str, price: f64, ts_ms: u64) {
        let deque = self.history.entry(symbol.to_string()).or_default();
        deque.push_back((ts_ms, price));

        // Prune entries older than window / 修剪超出窗口的條目
        let cutoff_ms = ts_ms.saturating_sub(self.window_secs * 1000);
        while let Some(&(oldest_ts, _)) = deque.front() {
            if oldest_ts < cutoff_ms {
                deque.pop_front();
            } else {
                break;
            }
        }
    }

    /// Compute ATR as percentage of current price using consecutive returns.
    /// 使用連續回報計算 ATR（佔當前價格的百分比）。
    ///
    /// Returns `None` if insufficient samples.
    /// 樣本不足時回傳 `None`。
    ///
    /// Method: average absolute return between consecutive observations.
    /// 方法：連續觀測值之間的平均絕對回報。
    pub fn compute_atr_pct(&self, symbol: &str) -> Option<f64> {
        let deque = self.history.get(symbol)?;
        if deque.len() < self.min_samples {
            return None;
        }

        let prices: Vec<f64> = deque.iter().map(|(_, p)| *p).collect();
        let last_price = *prices.last()?;
        if last_price <= 0.0 {
            return None;
        }

        // Average absolute return / 平均絕對回報
        let mut sum_abs_return = 0.0;
        let mut count = 0usize;
        for window in prices.windows(2) {
            let prev = window[0];
            let curr = window[1];
            if prev > 0.0 {
                sum_abs_return += ((curr - prev) / prev).abs();
                count += 1;
            }
        }

        if count == 0 {
            return None;
        }

        let avg_return = sum_abs_return / count as f64;
        Some(avg_return * 100.0) // Convert to percentage / 轉換為百分比
    }

    /// Detect a price spike (deviation > SPIKE_THRESHOLD_SIGMA standard deviations).
    /// 偵測價格尖峰（偏離 > SPIKE_THRESHOLD_SIGMA 個標準差）。
    ///
    /// Returns `Some(SpikeInfo)` if current price is an outlier, `None` otherwise.
    /// 若當前價格為離群值回傳 `Some(SpikeInfo)`，否則 `None`。
    pub fn detect_spike(&self, symbol: &str, current_price: f64, _ts_ms: u64) -> Option<SpikeInfo> {
        let deque = self.history.get(symbol)?;
        if deque.len() < self.min_samples {
            return None;
        }

        // Compute mean and std of historical prices / 計算歷史價格均值和標準差
        let prices: Vec<f64> = deque.iter().map(|(_, p)| *p).collect();
        let n = prices.len() as f64;
        let mean = prices.iter().sum::<f64>() / n;

        if mean <= 0.0 {
            return None;
        }

        let variance = prices.iter().map(|p| (p - mean).powi(2)).sum::<f64>() / n;
        let std_dev = variance.sqrt();

        if std_dev < 1e-12 {
            // No variance → no spike possible / 無變異 → 不可能有尖峰
            return None;
        }

        let deviation = (current_price - mean).abs();
        let sigma = deviation / std_dev;

        if sigma >= SPIKE_THRESHOLD_SIGMA {
            let deviation_pct = (current_price - mean) / mean * 100.0;
            Some(SpikeInfo {
                symbol: symbol.to_string(),
                deviation_pct,
                sigma,
                current_price,
                mean_price: mean,
            })
        } else {
            None
        }
    }

    /// Compute the maximum price drop percentage across all tracked symbols
    /// within the rolling window. Returns the worst (largest) drop as a
    /// positive percentage (e.g., 5.2 means a 5.2% drop from peak).
    /// Used by fast_track to detect flash crashes.
    /// 計算滾動窗口內所有追蹤幣種的最大跌幅百分比。
    /// 返回最大跌幅（正值，如 5.2 表示從峰值跌 5.2%）。
    /// 供 fast_track 閃崩偵測使用。
    pub fn max_drop_pct(&self) -> f64 {
        let mut worst = 0.0_f64;
        for deque in self.history.values() {
            if deque.len() < 2 {
                continue;
            }
            // Find peak price and current (last) price in window
            // 找窗口內的峰值和當前（最後）價格
            let mut peak = f64::MIN;
            for &(_, p) in deque.iter() {
                if p > peak {
                    peak = p;
                }
            }
            if peak <= 0.0 {
                continue;
            }
            let current = deque.back().map(|&(_, p)| p).unwrap_or(0.0);
            let drop_pct = (peak - current) / peak * 100.0;
            if drop_pct > worst {
                worst = drop_pct;
            }
        }
        worst
    }

    /// Compute the worst peak-to-current drop restricted to held symbols.
    /// Returns `None` when the set is empty or none of the symbols have
    /// enough samples to compute a meaningful drop.
    ///
    /// FA-PHANTOM-2 fix (2026-04-15): the legacy `max_drop_pct()` scans ALL
    /// observed symbols (25+), so any microcap in the pool routinely firing
    /// a 5% window move triggers fast_track CloseAll even when no position
    /// is held in that symbol. Scoping to held symbols ties flash-crash
    /// defense to real exposure. The accompanying `sigma` (deviation from
    /// window mean in std-dev units) lets the caller gate on "is this an
    /// outlier" rather than a raw percent threshold — a symbol that
    /// normally swings 5% will have low sigma on a 5% move, while a stable
    /// symbol's 5% move will score high.
    ///
    /// 僅針對持倉幣種計算最大跌幅。空集合或樣本不足時返回 None。
    /// FA-PHANTOM-2 修復：舊 max_drop_pct() 掃全部觀察幣種，任一小幣抖 5%
    /// 就誤觸 CloseAll；改為只看真實持倉的幣種才能把閃崩防禦綁回實際曝險。
    /// 附加的 sigma 提供「是否離群事件」信號，讓 caller 能區分小幣正常波動
    /// 與真正的異常下跌。
    pub fn worst_drop_for_held(&self, held_symbols: &[String]) -> Option<SymbolDropInfo> {
        if held_symbols.is_empty() {
            return None;
        }
        let mut worst: Option<SymbolDropInfo> = None;
        for sym in held_symbols {
            let Some(deque) = self.history.get(sym) else { continue; };
            if deque.len() < self.min_samples {
                continue;
            }
            let prices: Vec<f64> = deque.iter().map(|(_, p)| *p).collect();
            let mut peak = f64::MIN;
            for &p in &prices {
                if p > peak {
                    peak = p;
                }
            }
            if peak <= 0.0 {
                continue;
            }
            let current = match prices.last() {
                Some(&p) => p,
                None => continue,
            };
            let drop_pct = (peak - current) / peak * 100.0;
            if drop_pct <= 0.0 {
                continue;
            }
            let n = prices.len() as f64;
            let mean = prices.iter().sum::<f64>() / n;
            if mean <= 0.0 {
                continue;
            }
            let variance = prices.iter().map(|p| (p - mean).powi(2)).sum::<f64>() / n;
            let std_dev = variance.sqrt();
            let sigma = if std_dev < 1e-12 {
                0.0
            } else {
                (current - mean).abs() / std_dev
            };
            let info = SymbolDropInfo {
                symbol: sym.clone(),
                drop_pct,
                sigma,
            };
            match &worst {
                None => worst = Some(info),
                Some(w) if info.drop_pct > w.drop_pct => worst = Some(info),
                _ => {}
            }
        }
        worst
    }

    /// Get the number of tracked symbols / 取得追蹤的幣種數量
    pub fn symbol_count(&self) -> usize {
        self.history.len()
    }

    /// Get the number of samples for a symbol / 取得某幣種的樣本數
    pub fn sample_count(&self, symbol: &str) -> usize {
        self.history.get(symbol).map_or(0, |d| d.len())
    }

    /// Compute short-window rate-of-change for Track P exit features.
    /// 計算 Track P 退出特徵所需的短窗 ROC。
    ///
    /// Returns `(latest - prior) / prior` as f32 (fractional, not bps/%),
    /// where `prior` is the first sample whose ts_ms ≥ (latest_ts − lookback_ms).
    /// Returns `None` when the symbol has no samples, the buffer contains only
    /// the latest observation, or no sample satisfies the lookback window.
    ///
    /// Design: EXIT-FEATURES-TABLE-1 needs sub-second price_roc_short (default
    /// 300 ms) as a momentum feature for the exit policy learner. Sharing the
    /// already-fed per-tick history here avoids duplicating the sample feed
    /// and keeps a single source of truth for price-tracking state.
    ///
    /// 設計：EXIT-FEATURES-TABLE-1 需要亞秒級 price_roc_short（預設 300 ms）
    /// 作為退出策略學習器的動量特徵。共用既有的每 tick history 可免於重複樣本饋入，
    /// 並維持價格追蹤狀態的單一來源。
    pub fn compute_roc(&self, symbol: &str, lookback_ms: u64) -> Option<f32> {
        let deque = self.history.get(symbol)?;
        if deque.len() < 2 {
            return None;
        }
        let &(latest_ts, latest_price) = deque.back()?;
        if !latest_price.is_finite() || latest_price <= 0.0 {
            return None;
        }
        if lookback_ms == 0 {
            return None;
        }
        let cutoff = latest_ts.saturating_sub(lookback_ms);
        // First sample whose ts_ms ≥ cutoff. Linear scan is fine at expected
        // N ≤ a few hundred (60 Hz × 300 s window).
        // 線性掃描 ts_ms ≥ cutoff 的第一筆樣本；N ≤ 幾百筆足夠。
        let prior = deque.iter().find(|&&(ts, _)| ts >= cutoff)?;
        // If the first sample at/after cutoff IS the latest, there is no usable
        // historical anchor within the window — report None rather than a
        // trivial 0.0 which would mask thin-history symbols.
        // 若找到的就是最新那筆，表示 lookback 窗內無有效歷史錨，回 None
        // 而非 0.0（避免掩蓋歷史稀疏的 symbol）。
        if prior.0 == latest_ts {
            return None;
        }
        let prior_price = prior.1;
        if !prior_price.is_finite() || prior_price <= 0.0 {
            return None;
        }
        let roc = (latest_price - prior_price) / prior_price;
        if !roc.is_finite() {
            return None;
        }
        Some(roc as f32)
    }
}

impl Default for PriceHistoryTracker {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_tracker_with_data() -> PriceHistoryTracker {
        let mut t = PriceHistoryTracker::with_params(300, 5);
        // Record 20 prices at 1-second intervals near 100.0
        for i in 0..20 {
            let price = 100.0 + (i as f64) * 0.1; // 100.0, 100.1, ..., 101.9
            t.record("BTCUSDT", price, i * 1000);
        }
        t
    }

    #[test]
    fn test_new_tracker_empty() {
        let t = PriceHistoryTracker::new();
        assert_eq!(t.symbol_count(), 0);
        assert_eq!(t.compute_atr_pct("BTCUSDT"), None);
    }

    #[test]
    fn test_record_and_count() {
        let mut t = PriceHistoryTracker::new();
        t.record("BTCUSDT", 100.0, 1000);
        t.record("BTCUSDT", 101.0, 2000);
        assert_eq!(t.symbol_count(), 1);
        assert_eq!(t.sample_count("BTCUSDT"), 2);
    }

    #[test]
    fn test_window_pruning() {
        let mut t = PriceHistoryTracker::with_params(10, 2); // 10s window
        t.record("BTCUSDT", 100.0, 0);
        t.record("BTCUSDT", 101.0, 5_000);
        t.record("BTCUSDT", 102.0, 15_000); // This should prune ts=0
        assert_eq!(t.sample_count("BTCUSDT"), 2); // 5000 and 15000
    }

    #[test]
    fn test_compute_atr_insufficient_samples() {
        let mut t = PriceHistoryTracker::with_params(300, 10);
        for i in 0..5 {
            t.record("BTCUSDT", 100.0 + i as f64, i * 1000);
        }
        assert_eq!(t.compute_atr_pct("BTCUSDT"), None);
    }

    #[test]
    fn test_compute_atr_valid() {
        let t = make_tracker_with_data();
        let atr = t.compute_atr_pct("BTCUSDT");
        assert!(atr.is_some(), "ATR should be computed with enough data");
        let atr = atr.unwrap();
        // Each step is ~0.1% of ~100, so ATR should be small but positive
        assert!(atr > 0.0 && atr < 1.0, "atr={atr}, expected small positive");
    }

    #[test]
    fn test_compute_atr_unknown_symbol() {
        let t = PriceHistoryTracker::new();
        assert_eq!(t.compute_atr_pct("NONEXISTENT"), None);
    }

    #[test]
    fn test_detect_spike_no_spike() {
        let t = make_tracker_with_data();
        // Price within normal range → no spike
        let spike = t.detect_spike("BTCUSDT", 101.0, 20_000);
        assert!(spike.is_none(), "Normal price should not be a spike");
    }

    #[test]
    fn test_detect_spike_extreme_price() {
        let t = make_tracker_with_data();
        // Price far from mean → spike
        let spike = t.detect_spike("BTCUSDT", 200.0, 20_000);
        assert!(spike.is_some(), "Extreme price should trigger spike");
        let info = spike.unwrap();
        assert!(info.sigma >= 3.0);
        assert!(info.deviation_pct > 0.0);
    }

    #[test]
    fn test_detect_spike_insufficient_data() {
        let mut t = PriceHistoryTracker::with_params(300, 10);
        t.record("BTCUSDT", 100.0, 1000);
        assert!(t.detect_spike("BTCUSDT", 200.0, 2000).is_none());
    }

    #[test]
    fn test_multiple_symbols() {
        let mut t = PriceHistoryTracker::with_params(300, 3);
        for i in 0..5 {
            t.record("BTCUSDT", 100.0, i * 1000);
            t.record("ETHUSDT", 3000.0, i * 1000);
        }
        assert_eq!(t.symbol_count(), 2);
        assert_eq!(t.sample_count("BTCUSDT"), 5);
        assert_eq!(t.sample_count("ETHUSDT"), 5);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // FA-PHANTOM-2 regression tests — worst_drop_for_held
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_worst_drop_empty_held_symbols() {
        let t = make_tracker_with_data();
        assert!(t.worst_drop_for_held(&[]).is_none(),
            "empty held set must return None");
    }

    #[test]
    fn test_worst_drop_unheld_symbol_ignored() {
        // FA-PHANTOM-2: microcap drops hard, but we hold no position in it.
        // Old max_drop_pct() would return a huge drop; new method returns None.
        // FA-PHANTOM-2：小幣大跌但未持倉，新方法必須忽略。
        let mut t = PriceHistoryTracker::with_params(300, 5);
        // Crash from 1.00 → 0.80 (20% drop)
        for i in 0..10 {
            let price = if i < 5 { 1.00 } else { 0.80 };
            t.record("MICROUSDT", price, i * 1000);
        }
        // We hold only BTCUSDT (not recorded, no history)
        assert!(t.worst_drop_for_held(&["BTCUSDT".to_string()]).is_none(),
            "drop on unheld symbol must not surface");
        // And legacy global scanner does still see it — proves behavior diverged intentionally
        assert!(t.max_drop_pct() > 15.0,
            "legacy max_drop_pct still scans all symbols");
    }

    #[test]
    fn test_worst_drop_held_symbol_surfaces() {
        let mut t = PriceHistoryTracker::with_params(300, 5);
        for i in 0..10 {
            // Crash from 100 → 90 (10% drop)
            let price = if i < 5 { 100.0 } else { 90.0 };
            t.record("BTCUSDT", price, i * 1000);
        }
        let info = t.worst_drop_for_held(&["BTCUSDT".to_string()])
            .expect("held symbol with drop must return info");
        assert_eq!(info.symbol, "BTCUSDT");
        assert!((info.drop_pct - 10.0).abs() < 0.01, "drop_pct={}", info.drop_pct);
        // Sigma must be positive — current=90 is below the within-window mean
        assert!(info.sigma > 0.0, "sigma should be positive, got {}", info.sigma);
    }

    #[test]
    fn test_worst_drop_insufficient_samples() {
        let mut t = PriceHistoryTracker::with_params(300, 10);
        for i in 0..5 {
            t.record("BTCUSDT", 100.0 - i as f64, i * 1000);
        }
        // Only 5 samples, min_samples=10 → None
        assert!(t.worst_drop_for_held(&["BTCUSDT".to_string()]).is_none());
    }

    #[test]
    fn test_worst_drop_picks_largest_across_held() {
        let mut t = PriceHistoryTracker::with_params(300, 5);
        for i in 0..10 {
            // BTCUSDT: 3% drop
            let btc = if i < 5 { 100.0 } else { 97.0 };
            // ETHUSDT: 8% drop — this should win
            let eth = if i < 5 { 3000.0 } else { 2760.0 };
            t.record("BTCUSDT", btc, i * 1000);
            t.record("ETHUSDT", eth, i * 1000);
        }
        let info = t.worst_drop_for_held(&[
            "BTCUSDT".to_string(),
            "ETHUSDT".to_string(),
        ]).expect("held symbols with drops must return info");
        assert_eq!(info.symbol, "ETHUSDT");
        assert!(info.drop_pct > 7.5 && info.drop_pct < 8.5,
            "expected ~8% drop, got {}", info.drop_pct);
    }

    #[test]
    fn test_worst_drop_stable_symbol_zero() {
        let mut t = PriceHistoryTracker::with_params(300, 5);
        // Flat 100.00 price — no drop
        for i in 0..10 {
            t.record("USDCUSDT", 100.0, i * 1000);
        }
        // Flat price → peak == current → drop_pct == 0 → skipped (returns None)
        assert!(t.worst_drop_for_held(&["USDCUSDT".to_string()]).is_none(),
            "zero-drop held symbol must return None");
    }

    #[test]
    fn test_worst_drop_sigma_low_for_noisy_symbol() {
        // Microcap that naturally swings 5% — a 5% drop is NOT an outlier.
        // 小幣本身 ±5% 震盪 — 5% 跌幅不應視為離群事件。
        let mut t = PriceHistoryTracker::with_params(300, 5);
        // Oscillate between 95 and 105 repeatedly, end at 95
        let pattern = [100.0, 105.0, 95.0, 105.0, 95.0, 105.0, 95.0, 105.0, 95.0, 95.0];
        for (i, &px) in pattern.iter().enumerate() {
            t.record("MICROUSDT", px, i as u64 * 1000);
        }
        let info = t.worst_drop_for_held(&["MICROUSDT".to_string()]).expect("has drop");
        // ~10% drop from peak 105 to 95
        assert!(info.drop_pct > 8.0, "drop_pct={}", info.drop_pct);
        // But sigma should be modest (< 3) because 95 is within normal swing range
        assert!(info.sigma < 3.0,
            "naturally-noisy symbol should have sigma < 3, got {}", info.sigma);
    }

    #[test]
    fn test_worst_drop_sigma_high_for_stable_symbol() {
        // Normally-stable symbol that suddenly tanks — should score high sigma.
        // 平時穩定的幣種突然下跌 — sigma 應該很高。
        // Use 19 stable samples so the outlier doesn't inflate std_dev enough
        // to bring sigma below 3 (pure 10-sample cases land right at ~3.0
        // due to the outlier dominating its own std-dev estimate).
        let mut t = PriceHistoryTracker::with_params(300, 5);
        for i in 0..19 {
            t.record("STABLEUSDT", 100.0 + (i as f64) * 0.01, i * 1000);
        }
        t.record("STABLEUSDT", 92.0, 19_000);
        let info = t.worst_drop_for_held(&["STABLEUSDT".to_string()]).expect("has drop");
        assert!(info.drop_pct > 7.0, "drop_pct={}", info.drop_pct);
        assert!(info.sigma >= 3.0,
            "stable-then-crash should have sigma >= 3, got {}", info.sigma);
    }

    // ═══════════════════════════════════════════════════════════════════════
    // EXIT-FEATURES-TABLE-1 — compute_roc short-window ROC
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_compute_roc_empty_returns_none() {
        let t = PriceHistoryTracker::new();
        assert_eq!(t.compute_roc("BTCUSDT", 300), None);
    }

    #[test]
    fn test_compute_roc_single_sample_returns_none() {
        let mut t = PriceHistoryTracker::new();
        t.record("BTCUSDT", 100.0, 1_000);
        assert_eq!(t.compute_roc("BTCUSDT", 300), None,
            "single sample → no prior anchor → None");
    }

    #[test]
    fn test_compute_roc_two_sample_positive() {
        let mut t = PriceHistoryTracker::new();
        t.record("BTCUSDT", 100.0, 1_000);
        t.record("BTCUSDT", 100.5, 1_300);
        // (100.5 - 100.0) / 100.0 = 0.005
        let roc = t.compute_roc("BTCUSDT", 500).expect("roc present");
        assert!((roc - 0.005).abs() < 1e-6, "got {roc}");
    }

    #[test]
    fn test_compute_roc_two_sample_negative() {
        let mut t = PriceHistoryTracker::new();
        t.record("ETHUSDT", 2_000.0, 1_000);
        t.record("ETHUSDT", 1_990.0, 1_200);
        let roc = t.compute_roc("ETHUSDT", 500).unwrap();
        assert!((roc - (-0.005)).abs() < 1e-6, "got {roc}");
    }

    #[test]
    fn test_compute_roc_lookback_exceeds_history_uses_oldest() {
        let mut t = PriceHistoryTracker::new();
        t.record("BTCUSDT", 100.0, 1_000);
        t.record("BTCUSDT", 105.0, 2_000);
        // 10 s lookback >> history (1 s) → anchor = oldest sample ($100)
        let roc = t.compute_roc("BTCUSDT", 10_000).unwrap();
        assert!((roc - 0.05).abs() < 1e-6, "got {roc}");
    }

    #[test]
    fn test_compute_roc_zero_lookback_returns_none() {
        let mut t = PriceHistoryTracker::new();
        t.record("BTCUSDT", 100.0, 1_000);
        t.record("BTCUSDT", 100.5, 1_300);
        // lookback=0 is degenerate — no meaningful historical anchor.
        assert_eq!(t.compute_roc("BTCUSDT", 0), None);
    }

    #[test]
    fn test_compute_roc_unknown_symbol_returns_none() {
        let mut t = PriceHistoryTracker::new();
        t.record("BTCUSDT", 100.0, 1_000);
        t.record("BTCUSDT", 100.5, 1_300);
        assert_eq!(t.compute_roc("ETHUSDT", 300), None);
    }

    #[test]
    fn test_compute_roc_short_lookback_no_anchor_returns_none() {
        let mut t = PriceHistoryTracker::new();
        t.record("BTCUSDT", 100.0, 1_000);
        t.record("BTCUSDT", 100.5, 5_000);
        // lookback=100ms, cutoff=4900; only ts=5000 satisfies, but that IS latest
        // → no usable anchor → None (not 0.0)
        assert_eq!(t.compute_roc("BTCUSDT", 100), None);
    }

    #[test]
    fn test_compute_roc_multi_symbol_isolated() {
        let mut t = PriceHistoryTracker::new();
        t.record("BTCUSDT", 100.0, 1_000);
        t.record("BTCUSDT", 101.0, 1_200);
        t.record("ETHUSDT", 2_000.0, 1_000);
        t.record("ETHUSDT", 1_980.0, 1_200);
        let btc = t.compute_roc("BTCUSDT", 500).unwrap();
        let eth = t.compute_roc("ETHUSDT", 500).unwrap();
        assert!((btc - 0.01).abs() < 1e-6, "btc={btc}");
        assert!((eth - (-0.01)).abs() < 1e-6, "eth={eth}");
    }

    // ═══════════════════════════════════════════════════════════════════════
    // DUAL-TRACK-EXIT-1 Track P T2 — compute_roc hot-path edge coverage
    // DUAL-TRACK-EXIT-1 Track P T2 — compute_roc 熱路徑邊界覆蓋
    //
    // Track P calls compute_roc(symbol, 300) every tick from tick_pipeline.
    // T3's `stale_and_decaying` gate depends on None meaning "insufficient
    // history" (never 0.0). These tests lock in that contract against both
    // sample-sparse starts and adversarial price inputs.
    //
    // Track P 熱路徑每 tick 以 lookback_ms=300 呼叫 compute_roc。T3 的
    // stale_and_decaying gate 依賴 None 表達「歷史不足」（絕不為 0.0）。
    // 以下測試封死稀疏啟動與惡意價格輸入下的 None 合約。
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_compute_roc_returns_none_with_two_or_fewer_samples() {
        // 0-sample / 1-sample paths both MUST return None — never Some(0.0),
        // which would silently claim "no momentum" on a cold-start symbol and
        // bypass T3's stale_and_decaying gate.
        // 0 / 1 樣本必須回 None，不得回 Some(0.0)，否則 T3 的
        // stale_and_decaying gate 會被冷啟 symbol 誤繞過。
        let mut t = PriceHistoryTracker::new();

        // 0 samples for symbol → None
        assert_eq!(
            t.compute_roc("BTCUSDT", 300),
            None,
            "0-sample history must return None (Track P contract)"
        );

        // 1 sample for symbol → None (len() < 2 branch)
        t.record("BTCUSDT", 100.0, 1_000);
        assert_eq!(
            t.compute_roc("BTCUSDT", 300),
            None,
            "1-sample history must return None (Track P contract)"
        );

        // Sanity: 2 samples with valid lookback → Some(..) (guardrail against
        // an accidental change that makes the thin-history case permanent).
        // 防禦測試：2 樣本下合理 lookback 必須能算出 ROC，避免誤改導致永遠回 None。
        t.record("BTCUSDT", 100.5, 1_200);
        assert!(
            t.compute_roc("BTCUSDT", 500).is_some(),
            "2-sample valid input must succeed — guards against over-tightening"
        );
        // 封閉 T3 stale_and_decaying gate 對 None 的保守依賴：
        // seals T3's stale_and_decaying conservative dependency on None.
    }

    #[test]
    fn test_compute_roc_handles_degenerate_prices() {
        // Degenerate inputs: NaN, +Inf, -Inf, 0.0, and negative prices can
        // slip through `record()` (no input sanitation there). compute_roc
        // MUST never surface Some(NaN) or Some(±Inf) to the exit policy —
        // that would corrupt ExitFeatureRow and poison downstream training.
        //
        // 惡意輸入：NaN / ±Inf / 0.0 / 負價格可能滑過 record()（無輸入清洗）。
        // compute_roc 絕不可回 Some(NaN) 或 Some(±Inf)，否則汙染
        // ExitFeatureRow 與下游訓練。
        let mut t = PriceHistoryTracker::new();

        // Case 1: prior=NaN → price finite check on prior_price should reject → None.
        let mut t_nan_prior = PriceHistoryTracker::new();
        t_nan_prior.record("BTCUSDT", f64::NAN, 1_000);
        t_nan_prior.record("BTCUSDT", 100.0, 1_200);
        let roc = t_nan_prior.compute_roc("BTCUSDT", 500);
        assert!(
            roc.is_none() || roc.map(|r| r.is_finite()).unwrap_or(false),
            "NaN prior must not surface as Some(NaN), got {:?}",
            roc
        );
        // Current impl: prior_price.is_finite() check rejects → None. ✅

        // Case 2: latest=NaN → latest_price.is_finite() check → None.
        t.record("BTCUSDT", 100.0, 1_000);
        t.record("BTCUSDT", f64::NAN, 1_200);
        let roc = t.compute_roc("BTCUSDT", 500);
        assert_eq!(roc, None, "NaN latest must return None, got {:?}", roc);

        // Case 3: latest=+Inf → latest_price.is_finite() rejects → None.
        let mut t_inf = PriceHistoryTracker::new();
        t_inf.record("BTCUSDT", 100.0, 1_000);
        t_inf.record("BTCUSDT", f64::INFINITY, 1_200);
        assert_eq!(
            t_inf.compute_roc("BTCUSDT", 500),
            None,
            "+Inf latest must return None"
        );

        // Case 4: prior=+Inf → find(ts>=cutoff) picks Inf sample → prior_price
        // is_finite check rejects → None.
        let mut t_inf_prior = PriceHistoryTracker::new();
        t_inf_prior.record("BTCUSDT", f64::INFINITY, 1_000);
        t_inf_prior.record("BTCUSDT", 100.0, 1_200);
        let roc = t_inf_prior.compute_roc("BTCUSDT", 500);
        assert!(
            roc.is_none() || roc.map(|r| r.is_finite()).unwrap_or(false),
            "+Inf prior must not surface as Some(Inf), got {:?}",
            roc
        );

        // Case 5: latest=0.0 → latest_price <= 0.0 rejects → None.
        let mut t_zero = PriceHistoryTracker::new();
        t_zero.record("BTCUSDT", 100.0, 1_000);
        t_zero.record("BTCUSDT", 0.0, 1_200);
        assert_eq!(
            t_zero.compute_roc("BTCUSDT", 500),
            None,
            "zero latest must return None"
        );

        // Case 6: prior=0.0 → find picks 0.0 sample → prior_price <= 0.0 → None.
        let mut t_zero_prior = PriceHistoryTracker::new();
        t_zero_prior.record("BTCUSDT", 0.0, 1_000);
        t_zero_prior.record("BTCUSDT", 100.0, 1_200);
        assert_eq!(
            t_zero_prior.compute_roc("BTCUSDT", 500),
            None,
            "zero prior must return None"
        );

        // Case 7: negative latest → <= 0.0 branch → None.
        let mut t_neg = PriceHistoryTracker::new();
        t_neg.record("BTCUSDT", 100.0, 1_000);
        t_neg.record("BTCUSDT", -50.0, 1_200);
        assert_eq!(
            t_neg.compute_roc("BTCUSDT", 500),
            None,
            "negative latest must return None"
        );
        // 封閉 T3 對 Track P ExitFeatureRow 有限浮點假設：
        // seals T3's finite-float assumption for Track P ExitFeatureRow.
    }

    #[test]
    fn test_compute_roc_isolates_symbols() {
        // Track P hot path reads per-symbol ROC each tick; a HashMap-indexing
        // regression that cross-pollinates symbols would silently leak
        // BTC momentum into ETH exit decisions. Lock in per-symbol isolation
        // with distinct price trajectories and lookback windows.
        //
        // Track P 熱路徑逐 symbol 讀 ROC；HashMap 索引若回歸跨 symbol 污染，
        // BTC 動量會悄悄洩漏到 ETH 退出決策。用不同價格軌跡與 lookback 窗
        // 鎖死 per-symbol 隔離。
        let mut t = PriceHistoryTracker::new();

        // BTC: +2% climb  / BTC：+2% 上漲
        t.record("BTCUSDT", 100.0, 1_000);
        t.record("BTCUSDT", 100.5, 1_150);
        t.record("BTCUSDT", 102.0, 1_250);

        // ETH: -3% drop  / ETH：-3% 下跌
        t.record("ETHUSDT", 2_000.0, 1_000);
        t.record("ETHUSDT", 1_990.0, 1_150);
        t.record("ETHUSDT", 1_940.0, 1_250);

        // SOL: flat → would be 0.0 ROC (valid, proves BTC/ETH don't mask it)
        // SOL：持平 → ROC 應為 0.0（驗證 BTC/ETH 不會掩蓋它）
        t.record("SOLUSDT", 50.0, 1_000);
        t.record("SOLUSDT", 50.0, 1_150);
        t.record("SOLUSDT", 50.0, 1_250);

        let btc = t.compute_roc("BTCUSDT", 300).expect("btc roc");
        let eth = t.compute_roc("ETHUSDT", 300).expect("eth roc");
        let sol = t.compute_roc("SOLUSDT", 300).expect("sol roc");

        // BTC: anchor=100.0 at ts=1000, latest=102.0 → (102-100)/100 = 0.02
        assert!(
            (btc - 0.02).abs() < 1e-6,
            "BTC ROC must be +2%, got {btc} (cross-symbol contamination?)"
        );
        // ETH: anchor=2000 at ts=1000, latest=1940 → (1940-2000)/2000 = -0.03
        assert!(
            (eth - (-0.03)).abs() < 1e-6,
            "ETH ROC must be -3%, got {eth} (cross-symbol contamination?)"
        );
        // SOL: flat → exactly 0.0 (important: 0.0 is semantically "no change",
        // distinct from None which means "insufficient history")
        // SOL：持平 → 0.0（語意區別：0.0=「無變化」; None=「歷史不足」）
        assert!(
            sol.abs() < 1e-9,
            "SOL ROC must be 0.0 (flat price), got {sol}"
        );

        // Also verify unknown symbol returns None even when others have data
        // 同時驗證未知 symbol 回 None 即使其他 symbol 有資料
        assert_eq!(
            t.compute_roc("UNKNOWNUSDT", 300),
            None,
            "unknown symbol must return None regardless of other symbols' history"
        );
        // 封閉 Track P per-symbol HashMap 索引契約：
        // seals Track P's per-symbol HashMap indexing contract.
    }
}
