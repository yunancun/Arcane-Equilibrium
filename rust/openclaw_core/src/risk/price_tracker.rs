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

    /// Get the number of tracked symbols / 取得追蹤的幣種數量
    pub fn symbol_count(&self) -> usize {
        self.history.len()
    }

    /// Get the number of samples for a symbol / 取得某幣種的樣本數
    pub fn sample_count(&self, symbol: &str) -> usize {
        self.history.get(symbol).map_or(0, |d| d.len())
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
}
