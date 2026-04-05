//! Black Swan detector — 4-signal voting on kline close events (Phase 3b).
//! 黑天鵝檢測器 — K 線收盤事件上的 4 信號投票。
//!
//! MODULE_NOTE (EN): Detects extreme market events using 4 independent signals:
//!   1. MAD (6× median absolute deviation) — statistical outlier
//!   2. Correlation break (cross-symbol corr > 0.85) — market contagion
//!   3. Volume anomaly (5× 30-day average) — unusual activity
//!   4. Velocity (15min return > daily range) — rapid movement
//!   Voting: 2/4→Observe, 3/4→Upgrade, 4/4→Defensive.
//!   Gated on bar_close only (not every tick) per E5-O5 audit.
//! MODULE_NOTE (中): 使用 4 個獨立信號檢測極端市場事件：
//!   1. MAD（6× 中位絕對偏差）— 統計異常值
//!   2. 相關性突破（跨品種 corr > 0.85）— 市場傳染
//!   3. 成交量異常（5× 30 天均值）— 異常活動
//!   4. 速度（15 分鐘回報 > 日常範圍）— 快速波動
//!   投票：2/4→觀察，3/4→升級，4/4→防禦。
//!   僅在 bar_close 觸發（非每個 tick），E5-O5 審計。

use std::collections::VecDeque;

/// Black Swan severity level from voting / 黑天鵝嚴重級別
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BlackSwanSeverity {
    /// No alert (0-1 signals) / 無告警
    None,
    /// Observation mode (2 signals) / 觀察模式
    Observe,
    /// Upgrade risk controls (3 signals) / 升級風控
    Upgrade,
    /// Full defensive mode (4 signals) / 全面防禦
    Defensive,
}

/// Individual signal vote result / 單個信號投票結果
#[derive(Debug, Clone)]
pub struct SignalVote {
    pub signal_name: &'static str,
    pub triggered: bool,
    pub metric_value: f64,
    pub threshold: f64,
}

/// Black Swan detection result / 黑天鵝檢測結果
#[derive(Debug, Clone)]
pub struct BlackSwanResult {
    pub severity: BlackSwanSeverity,
    pub votes: [SignalVote; 4],
    pub votes_for: u32,
    pub symbol: String,
    pub ts_ms: u64,
}

/// Configuration for Black Swan detection thresholds.
/// 黑天鵝檢測閾值配置。
#[derive(Debug, Clone)]
pub struct BlackSwanConfig {
    /// MAD multiplier threshold (default 6.0) / MAD 倍數閾值
    pub mad_threshold: f64,
    /// Cross-symbol correlation threshold (default 0.85) / 跨品種相關性閾值
    pub corr_threshold: f64,
    /// Volume anomaly multiplier (default 5.0) / 成交量異常倍數
    pub volume_multiplier: f64,
    /// Return window for velocity check in bars (default 15) / 速度檢查的回報窗口（K 線數）
    pub velocity_bars: usize,
}

impl Default for BlackSwanConfig {
    fn default() -> Self {
        Self {
            mad_threshold: 6.0,
            corr_threshold: 0.85,
            volume_multiplier: 5.0,
            velocity_bars: 15,
        }
    }
}

/// Black Swan detector — owned by TickPipeline, called on bar close.
/// 黑天鵝檢測器 — 由 TickPipeline 擁有，在 K 線收盤時調用。
pub struct BlackSwanDetector {
    config: BlackSwanConfig,
    /// Rolling returns per symbol for MAD + velocity (last 720 bars = ~12h @ 1m).
    /// 每品種滾動回報（最近 720 根 = 1 分鐘約 12 小時）。
    returns: std::collections::HashMap<String, VecDeque<f64>>,
    /// Rolling volumes per symbol (last 43200 bars ≈ 30 days @ 1m).
    /// 每品種滾動成交量（最近 43200 根 ≈ 30 天 @ 1 分鐘）。
    volumes: std::collections::HashMap<String, VecDeque<f64>>,
    /// Max return window size / 最大回報窗口大小
    max_return_window: usize,
    /// Max volume window size / 最大成交量窗口大小
    max_volume_window: usize,
}

impl BlackSwanDetector {
    /// Create a new detector with default config.
    /// 使用默認配置創建新檢測器。
    pub fn new() -> Self {
        Self::with_config(BlackSwanConfig::default())
    }

    /// Create with custom config / 使用自定義配置創建
    pub fn with_config(config: BlackSwanConfig) -> Self {
        Self {
            config,
            returns: std::collections::HashMap::new(),
            volumes: std::collections::HashMap::new(),
            max_return_window: 720,    // ~12h of 1m bars
            max_volume_window: 43_200, // ~30 days of 1m bars
        }
    }

    /// Record a closed bar's return and volume. Call on every bar close.
    /// 記錄已關閉 K 線的回報和成交量。每次 K 線收盤時調用。
    pub fn record_bar(&mut self, symbol: &str, ret: f64, volume: f64) {
        let returns = self.returns.entry(symbol.to_string()).or_insert_with(VecDeque::new);
        returns.push_back(ret);
        if returns.len() > self.max_return_window {
            returns.pop_front();
        }

        let volumes = self.volumes.entry(symbol.to_string()).or_insert_with(VecDeque::new);
        volumes.push_back(volume);
        if volumes.len() > self.max_volume_window {
            volumes.pop_front();
        }
    }

    /// Run all 4 signal checks and return the detection result.
    /// 運行全部 4 個信號檢查並返回檢測結果。
    ///
    /// Called on bar close only (not every tick).
    /// 僅在 K 線收盤時調用（非每個 tick）。
    pub fn check(
        &self,
        symbol: &str,
        current_return: f64,
        current_volume: f64,
        ts_ms: u64,
    ) -> BlackSwanResult {
        let mad_vote = self.check_mad_signal(symbol, current_return);
        let corr_vote = self.check_correlation_signal();
        let volume_vote = self.check_volume_signal(symbol, current_volume);
        let velocity_vote = self.check_velocity_signal(symbol, current_return);

        let votes = [mad_vote, corr_vote, volume_vote, velocity_vote];
        let votes_for = votes.iter().filter(|v| v.triggered).count() as u32;

        let severity = match votes_for {
            0 | 1 => BlackSwanSeverity::None,
            2 => BlackSwanSeverity::Observe,
            3 => BlackSwanSeverity::Upgrade,
            _ => BlackSwanSeverity::Defensive,
        };

        BlackSwanResult {
            severity,
            votes,
            votes_for,
            symbol: symbol.to_string(),
            ts_ms,
        }
    }

    /// Signal 1: MAD-based statistical outlier detection (6×MAD).
    /// 信號 1：基於 MAD 的統計異常值檢測（6×MAD）。
    fn check_mad_signal(&self, symbol: &str, current_return: f64) -> SignalVote {
        let returns = match self.returns.get(symbol) {
            Some(r) if r.len() >= 30 => r,
            _ => {
                return SignalVote {
                    signal_name: "MAD",
                    triggered: false,
                    metric_value: 0.0,
                    threshold: self.config.mad_threshold,
                };
            }
        };

        let returns_vec: Vec<f64> = returns.iter().copied().collect();
        let mad = compute_mad(&returns_vec);
        let threshold_val = mad * self.config.mad_threshold;
        let median = compute_median(&returns_vec);
        let deviation = (current_return - median).abs();

        SignalVote {
            signal_name: "MAD",
            triggered: threshold_val > 0.0 && deviation > threshold_val,
            metric_value: if mad > 0.0 { deviation / mad } else { 0.0 },
            threshold: self.config.mad_threshold,
        }
    }

    /// Signal 2: Cross-symbol correlation break.
    /// 信號 2：跨品種相關性突破。
    ///
    /// Simplified: checks if recent returns across all symbols are highly correlated.
    /// 簡化版：檢查所有品種的近期回報是否高度相關。
    fn check_correlation_signal(&self) -> SignalVote {
        // Need at least 2 symbols with enough data
        let symbol_returns: Vec<&VecDeque<f64>> = self
            .returns
            .values()
            .filter(|r| r.len() >= 30)
            .collect();

        if symbol_returns.len() < 2 {
            return SignalVote {
                signal_name: "CORRELATION",
                triggered: false,
                metric_value: 0.0,
                threshold: self.config.corr_threshold,
            };
        }

        // Compute average pairwise correlation of last 30 returns
        let window = 30;
        let mut total_corr = 0.0;
        let mut count = 0u32;
        for i in 0..symbol_returns.len() {
            for j in (i + 1)..symbol_returns.len() {
                let a: Vec<f64> = symbol_returns[i].iter().rev().take(window).copied().collect();
                let b: Vec<f64> = symbol_returns[j].iter().rev().take(window).copied().collect();
                let corr = pearson_correlation(&a, &b);
                if corr.is_finite() {
                    total_corr += corr.abs();
                    count += 1;
                }
            }
        }

        let avg_corr = if count > 0 { total_corr / count as f64 } else { 0.0 };

        SignalVote {
            signal_name: "CORRELATION",
            triggered: avg_corr > self.config.corr_threshold,
            metric_value: avg_corr,
            threshold: self.config.corr_threshold,
        }
    }

    /// Signal 3: Volume anomaly (current > 5× 30-day average).
    /// 信號 3：成交量異常（當前 > 5× 30 天均值）。
    fn check_volume_signal(&self, symbol: &str, current_volume: f64) -> SignalVote {
        let volumes = match self.volumes.get(symbol) {
            Some(v) if v.len() >= 100 => v,
            _ => {
                return SignalVote {
                    signal_name: "VOLUME",
                    triggered: false,
                    metric_value: 0.0,
                    threshold: self.config.volume_multiplier,
                };
            }
        };

        let avg_volume: f64 = volumes.iter().sum::<f64>() / volumes.len() as f64;
        let ratio = if avg_volume > 0.0 {
            current_volume / avg_volume
        } else {
            0.0
        };

        SignalVote {
            signal_name: "VOLUME",
            triggered: ratio > self.config.volume_multiplier,
            metric_value: ratio,
            threshold: self.config.volume_multiplier,
        }
    }

    /// Signal 4: Velocity — short-term return exceeds normal daily range.
    /// 信號 4：速度 — 短期回報超過正常日常範圍。
    fn check_velocity_signal(&self, symbol: &str, current_return: f64) -> SignalVote {
        let returns = match self.returns.get(symbol) {
            Some(r) if r.len() >= 100 => r,
            _ => {
                return SignalVote {
                    signal_name: "VELOCITY",
                    triggered: false,
                    metric_value: 0.0,
                    threshold: 1.0,
                };
            }
        };

        // Estimate daily range as sum of absolute returns over ~1440 bars (1 day of 1m)
        // Use available data (may be less than full day)
        let daily_bars = returns.len().min(1440);
        let daily_range: f64 = returns.iter().rev().take(daily_bars).map(|r| r.abs()).sum();
        let daily_range_normalized = if daily_bars > 0 {
            daily_range / daily_bars as f64 * 1440.0
        } else {
            0.0
        };

        // Current velocity: the abs return itself
        // Trigger if current return (single bar) > daily_range_normalized * velocity_factor
        // A single bar contributing > 1/(velocity_bars) of daily range is unusual
        let velocity_threshold = if daily_range_normalized > 0.0 {
            daily_range_normalized / self.config.velocity_bars as f64
        } else {
            f64::MAX
        };

        let ratio = if velocity_threshold > 0.0 && velocity_threshold < f64::MAX {
            current_return.abs() / velocity_threshold
        } else {
            0.0
        };

        SignalVote {
            signal_name: "VELOCITY",
            triggered: current_return.abs() > velocity_threshold && velocity_threshold < f64::MAX,
            metric_value: ratio,
            threshold: 1.0,
        }
    }
}

impl Default for BlackSwanDetector {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Math helpers / 數學輔助函數
// ---------------------------------------------------------------------------

/// Compute Median Absolute Deviation (MAD).
/// 計算中位絕對偏差。
fn compute_mad(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let median = compute_median(values);
    let mut deviations: Vec<f64> = values.iter().map(|v| (v - median).abs()).collect();
    deviations.sort_unstable_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    compute_median(&deviations)
}

/// Compute median of a slice / 計算切片的中位數
fn compute_median(values: &[f64]) -> f64 {
    if values.is_empty() {
        return 0.0;
    }
    let mut sorted: Vec<f64> = values.to_vec();
    sorted.sort_unstable_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    let mid = sorted.len() / 2;
    if sorted.len() % 2 == 0 {
        (sorted[mid - 1] + sorted[mid]) / 2.0
    } else {
        sorted[mid]
    }
}

/// Pearson correlation between two slices / 兩個切片的 Pearson 相關係數
fn pearson_correlation(a: &[f64], b: &[f64]) -> f64 {
    let n = a.len().min(b.len());
    if n < 2 {
        return 0.0;
    }
    let mean_a: f64 = a[..n].iter().sum::<f64>() / n as f64;
    let mean_b: f64 = b[..n].iter().sum::<f64>() / n as f64;

    let mut cov = 0.0;
    let mut var_a = 0.0;
    let mut var_b = 0.0;
    for i in 0..n {
        let da = a[i] - mean_a;
        let db = b[i] - mean_b;
        cov += da * db;
        var_a += da * da;
        var_b += db * db;
    }

    let denom = (var_a * var_b).sqrt();
    if denom < 1e-15 {
        0.0
    } else {
        cov / denom
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_mad_signal_triggers_at_6x() {
        let mut detector = BlackSwanDetector::new();
        // Feed 100 bars of small returns (normal market)
        for i in 0..100 {
            let ret = (i as f64 % 10.0 - 5.0) * 0.001; // ±0.5%
            detector.record_bar("BTCUSDT", ret, 1000.0);
        }
        // A 10× MAD return should trigger
        let result = detector.check("BTCUSDT", 0.15, 1000.0, 1000);
        assert!(
            result.votes[0].triggered,
            "MAD signal should trigger for extreme return: metric={:.4}",
            result.votes[0].metric_value
        );
    }

    #[test]
    fn test_volume_signal_triggers_at_5x() {
        let mut detector = BlackSwanDetector::new();
        // Feed 200 bars of normal volume
        for _ in 0..200 {
            detector.record_bar("BTCUSDT", 0.001, 1000.0);
        }
        // 6× average volume should trigger
        let result = detector.check("BTCUSDT", 0.001, 6000.0, 2000);
        assert!(
            result.votes[2].triggered,
            "Volume signal should trigger at 6×: metric={:.2}",
            result.votes[2].metric_value
        );
        // 3× should NOT trigger
        let result2 = detector.check("BTCUSDT", 0.001, 3000.0, 2000);
        assert!(
            !result2.votes[2].triggered,
            "Volume signal should NOT trigger at 3×"
        );
    }

    #[test]
    fn test_velocity_signal_triggers() {
        let mut detector = BlackSwanDetector::new();
        // Feed 200 bars of tiny returns
        for _ in 0..200 {
            detector.record_bar("BTCUSDT", 0.0001, 1000.0);
        }
        // A huge return should trigger velocity
        let result = detector.check("BTCUSDT", 0.05, 1000.0, 3000);
        assert!(
            result.votes[3].triggered,
            "Velocity signal should trigger for huge single-bar return: metric={:.4}",
            result.votes[3].metric_value
        );
    }

    #[test]
    fn test_vote_aggregation_severity() {
        // Test vote counting → severity mapping
        let none_result = BlackSwanResult {
            severity: BlackSwanSeverity::None,
            votes: [
                SignalVote { signal_name: "MAD", triggered: false, metric_value: 0.0, threshold: 6.0 },
                SignalVote { signal_name: "CORRELATION", triggered: false, metric_value: 0.0, threshold: 0.85 },
                SignalVote { signal_name: "VOLUME", triggered: false, metric_value: 0.0, threshold: 5.0 },
                SignalVote { signal_name: "VELOCITY", triggered: false, metric_value: 0.0, threshold: 1.0 },
            ],
            votes_for: 0,
            symbol: "BTC".into(),
            ts_ms: 0,
        };
        assert_eq!(none_result.severity, BlackSwanSeverity::None);

        // Test with 2 votes → Observe
        let mut detector = BlackSwanDetector::new();
        for _ in 0..200 {
            detector.record_bar("BTCUSDT", 0.0001, 100.0);
        }
        // Extreme return + extreme volume = 2+ signals (MAD + volume + velocity likely)
        let result = detector.check("BTCUSDT", 0.2, 1000.0, 4000);
        assert!(
            result.votes_for >= 2,
            "Should have at least 2 votes for extreme conditions, got {}",
            result.votes_for
        );
        assert_ne!(result.severity, BlackSwanSeverity::None);
    }

    #[test]
    fn test_no_alert_normal_conditions() {
        let mut detector = BlackSwanDetector::new();
        for _ in 0..200 {
            detector.record_bar("BTCUSDT", 0.001, 1000.0);
        }
        let result = detector.check("BTCUSDT", 0.001, 1000.0, 5000);
        assert_eq!(result.severity, BlackSwanSeverity::None);
        assert_eq!(result.votes_for, 0);
    }

    #[test]
    fn test_bar_close_gate_insufficient_data() {
        let detector = BlackSwanDetector::new();
        // No data recorded yet — all signals should be safe (not triggered)
        let result = detector.check("BTCUSDT", 0.5, 50000.0, 6000);
        assert_eq!(result.severity, BlackSwanSeverity::None);
        assert_eq!(result.votes_for, 0);
    }
}
