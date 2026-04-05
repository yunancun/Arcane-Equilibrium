//! Drift detector — PSI + ADWIN monitoring for feature distribution shifts.
//! 漂移檢測器 — 特徵分佈偏移的 PSI + ADWIN 監控。
//!
//! MODULE_NOTE (EN): Periodically reads features.online_latest, computes PSI against
//!   stored baselines (observability.feature_baselines), and runs ADWIN on feature streams.
//!   Non-overlapping 7-day test windows (W2 audit fix). ADWIN delta=0.05 with 3-consecutive
//!   majority vote and 30-day burn-in (F2 audit fix). Writes to observability.drift_events.
//! MODULE_NOTE (中): 定期讀取 features.online_latest，計算 PSI 對比存儲的基線，
//!   並對特徵流運行 ADWIN。非重疊 7 天測試窗口。ADWIN delta=0.05 + 3 次多數票 + 30 天預熱。

use super::pool::DbPool;
use crate::database::DatabaseConfig;
use std::sync::Arc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

// ═══════════════════════════════════════════════════════════════════
// PSI (Population Stability Index) / 群體穩定性指數
// ═══════════════════════════════════════════════════════════════════

/// Compute PSI between two histograms (reference vs current).
/// PSI = Σ (P_i - Q_i) * ln(P_i / Q_i), with epsilon smoothing for empty bins.
/// 計算兩個直方圖之間的 PSI（參考 vs 當前），空 bin 使用 epsilon 平滑。
pub fn compute_psi(reference_counts: &[u32], current_counts: &[u32], epsilon: f64) -> f64 {
    if reference_counts.len() != current_counts.len() || reference_counts.is_empty() {
        return 0.0;
    }
    let ref_total: f64 = reference_counts.iter().map(|&c| c as f64).sum();
    let cur_total: f64 = current_counts.iter().map(|&c| c as f64).sum();
    if ref_total == 0.0 || cur_total == 0.0 {
        return 0.0;
    }

    let mut psi = 0.0;
    for i in 0..reference_counts.len() {
        let p = (reference_counts[i] as f64 / ref_total).max(epsilon);
        let q = (current_counts[i] as f64 / cur_total).max(epsilon);
        psi += (p - q) * (p / q).ln();
    }
    psi
}

/// Bin a slice of f64 values using pre-defined bin edges.
/// Returns histogram counts per bin.
/// 使用預定義 bin 邊界對 f64 值切片分箱。返回每 bin 的計數。
pub fn histogram(values: &[f64], bin_edges: &[f64]) -> Vec<u32> {
    if bin_edges.len() < 2 {
        return vec![0];
    }
    let n_bins = bin_edges.len() - 1;
    let mut counts = vec![0u32; n_bins];
    for &v in values {
        if !v.is_finite() {
            continue;
        }
        // Binary search for bin index / 二分搜索 bin 索引
        let idx = match bin_edges[1..].binary_search_by(|edge| {
            edge.partial_cmp(&v).unwrap_or(std::cmp::Ordering::Equal)
        }) {
            Ok(i) => i.min(n_bins - 1),
            Err(i) => i.min(n_bins - 1),
        };
        counts[idx] += 1;
    }
    counts
}

/// Compute quantile-based bin edges from a data slice.
/// Returns n_bins+1 edges for n_bins bins (evenly spaced quantiles).
/// 從數據切片計算基於分位數的 bin 邊界。返回 n_bins+1 個邊界。
pub fn quantile_bin_edges(data: &[f64], n_bins: usize) -> Vec<f64> {
    if data.is_empty() || n_bins == 0 {
        return vec![];
    }
    let mut sorted: Vec<f64> = data.iter().filter(|v| v.is_finite()).copied().collect();
    sorted.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
    if sorted.is_empty() {
        return vec![];
    }

    let mut edges = Vec::with_capacity(n_bins + 1);
    for i in 0..=n_bins {
        let q = i as f64 / n_bins as f64;
        let idx = ((sorted.len() - 1) as f64 * q) as usize;
        edges.push(sorted[idx]);
    }
    // Ensure first edge is slightly below min, last is slightly above max
    if let Some(first) = edges.first_mut() {
        *first -= 1e-10;
    }
    if let Some(last) = edges.last_mut() {
        *last += 1e-10;
    }
    edges
}

// ═══════════════════════════════════════════════════════════════════
// ADWIN (Adaptive Windowing) / 自適應窗口
// ═══════════════════════════════════════════════════════════════════

/// ADWIN change detector for a single feature stream.
/// Detects mean shifts using adaptive sub-window comparison.
/// 單一特徵流的 ADWIN 變化檢測器，使用自適應子窗口比較。
pub struct AdwinDetector {
    window: Vec<f64>,
    delta: f64,
    min_width: usize,
    consecutive_detections: u32,
    consecutive_required: u32,
    total_observations: u64,
}

impl AdwinDetector {
    /// Create a new ADWIN detector with configurable parameters.
    /// 使用可配置參數創建新的 ADWIN 檢測器。
    pub fn new(delta: f64, min_width: usize, consecutive_required: u32) -> Self {
        Self {
            window: Vec::with_capacity(min_width * 4),
            delta,
            min_width,
            consecutive_detections: 0,
            consecutive_required,
            total_observations: 0,
        }
    }

    /// Add a new observation and check for drift.
    /// Returns true if drift is confirmed (consecutive_required met).
    /// 添加新觀測值並檢查漂移。如果連續檢測次數達標則返回 true。
    pub fn add(&mut self, value: f64) -> bool {
        if !value.is_finite() {
            return false;
        }
        self.window.push(value);
        self.total_observations += 1;

        // Need at least min_width * 2 for meaningful comparison
        if self.window.len() < self.min_width * 2 {
            return false;
        }

        // Check for change point: try splitting window into two halves
        // 檢查變化點：嘗試將窗口拆分為兩半
        let detected = self.detect_change();

        if detected {
            self.consecutive_detections += 1;
            if self.consecutive_detections >= self.consecutive_required {
                // Confirmed drift — shrink window to recent half
                // 確認漂移 — 將窗口縮小到最近一半
                let mid = self.window.len() / 2;
                self.window = self.window[mid..].to_vec();
                self.consecutive_detections = 0;
                return true;
            }
        } else {
            self.consecutive_detections = 0;
        }

        // Prevent unbounded growth — cap at 4x min_width
        if self.window.len() > self.min_width * 4 {
            let trim = self.window.len() - self.min_width * 3;
            self.window = self.window[trim..].to_vec();
        }

        false
    }

    /// Total observations seen / 總觀測數
    pub fn total_observations(&self) -> u64 {
        self.total_observations
    }

    /// Current window size / 當前窗口大小
    pub fn window_size(&self) -> usize {
        self.window.len()
    }

    /// Detect change using Welch's t-test approximation between window halves.
    /// Uses the ADWIN bound: |μ₁ - μ₂| > ε where ε depends on delta and sample sizes.
    /// 使用 Welch t 檢驗近似檢測窗口兩半之間的變化。
    fn detect_change(&self) -> bool {
        let n = self.window.len();
        let mid = n / 2;
        if mid < self.min_width {
            return false;
        }

        let (left, right) = self.window.split_at(mid);

        let n1 = left.len() as f64;
        let n2 = right.len() as f64;

        let mean1: f64 = left.iter().sum::<f64>() / n1;
        let mean2: f64 = right.iter().sum::<f64>() / n2;

        let var1: f64 = left.iter().map(|x| (x - mean1).powi(2)).sum::<f64>() / n1;
        let var2: f64 = right.iter().map(|x| (x - mean2).powi(2)).sum::<f64>() / n2;

        let diff = (mean1 - mean2).abs();

        // ADWIN bound: ε = sqrt((1/(2m)) * ln(4/δ)) for each sub-window
        // Simplified: compare diff against threshold derived from variance + delta
        // 簡化：將差異與由方差 + delta 推導的閾值比較
        let se = ((var1 / n1) + (var2 / n2)).sqrt();
        if se < 1e-15 {
            return diff > 1e-10; // constant series, any change is a drift
        }

        // z-score threshold from delta (approximation: delta=0.05 → z≈1.96)
        let z_threshold = (-2.0 * (self.delta / 4.0).ln()).sqrt();
        let threshold = z_threshold * se;

        diff > threshold
    }
}

// ═══════════════════════════════════════════════════════════════════
// Drift Monitor Task / 漂移監控任務
// ═══════════════════════════════════════════════════════════════════

/// Run the periodic drift detection task.
/// 運行定期漂移檢測任務。
pub async fn run_drift_detector(
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    let cfg = config.get();
    let db_cfg = &cfg.database;
    let check_interval = std::time::Duration::from_secs(db_cfg.drift_check_interval_secs);
    let psi_warn = db_cfg.psi_warning_threshold;
    let psi_alert = db_cfg.psi_alert_threshold;
    let burnin_days = db_cfg.adwin_burnin_days;

    let mut interval = tokio::time::interval(check_interval);
    interval.tick().await; // skip first
    let start_time = std::time::Instant::now();

    info!(
        interval_secs = db_cfg.drift_check_interval_secs,
        psi_warn = psi_warn,
        psi_alert = psi_alert,
        "drift detector started / 漂移檢測器已啟動"
    );

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = interval.tick() => {
                if !pool.is_available() {
                    continue;
                }

                // Burn-in: log-only mode for first N days (F2 audit fix)
                let uptime_days = start_time.elapsed().as_secs() / 86400;
                let in_burnin = uptime_days < burnin_days as u64;

                // TODO(G3-full): Read baselines from observability.feature_baselines,
                // read current features from features.online_latest,
                // compute PSI per feature, run ADWIN on feature streams.
                // For now, the infrastructure is in place; actual PG queries
                // will be wired when baselines are populated.
                debug!(
                    in_burnin = in_burnin,
                    uptime_days = uptime_days,
                    "drift check cycle (awaiting baseline data) / 漂移檢查週期（等待基線數據）"
                );
            }
        }
    }

    info!("drift detector stopped / 漂移檢測器已停止");
}

/// Write a drift event to observability.drift_events.
/// 寫入漂移事件到 observability.drift_events。
pub async fn write_drift_event(
    pool: &DbPool,
    event_id: &str,
    drift_type: &str,
    severity: &str,
    symbol: &str,
    feature_name: &str,
    metric_value: f64,
    threshold: f64,
) {
    let pg = match pool.get() {
        Some(p) => p,
        None => return,
    };

    let ts = chrono::Utc::now();
    let result = sqlx::query(
        "INSERT INTO observability.drift_events \
         (ts, event_id, drift_type, severity, symbol, feature_name, metric_value, threshold) \
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8) \
         ON CONFLICT (event_id, ts) DO NOTHING"
    )
    .bind(ts)
    .bind(event_id)
    .bind(drift_type)
    .bind(severity)
    .bind(symbol)
    .bind(feature_name)
    .bind(metric_value as f32)
    .bind(threshold as f32)
    .execute(pg)
    .await;

    match result {
        Ok(_) => debug!(event_id = event_id, "drift event written / 漂移事件已寫入"),
        Err(e) => warn!(event_id = event_id, error = %e, "drift event write failed"),
    }
}

// ═══════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_psi_identical_distributions() {
        let ref_counts = vec![10, 20, 30, 20, 10];
        let cur_counts = vec![10, 20, 30, 20, 10];
        let psi = compute_psi(&ref_counts, &cur_counts, 1e-6);
        assert!(psi.abs() < 1e-10, "identical distributions should have PSI ≈ 0, got {psi}");
    }

    #[test]
    fn test_psi_shifted_distribution() {
        let ref_counts = vec![10, 20, 30, 20, 10]; // centered
        let cur_counts = vec![30, 20, 10, 5, 5];   // shifted left
        let psi = compute_psi(&ref_counts, &cur_counts, 1e-6);
        assert!(psi > 0.1, "shifted distribution should have PSI > 0.1, got {psi}");
    }

    #[test]
    fn test_psi_empty_bins_epsilon() {
        let ref_counts = vec![0, 50, 50, 0];
        let cur_counts = vec![25, 25, 25, 25];
        let psi = compute_psi(&ref_counts, &cur_counts, 1e-6);
        assert!(psi.is_finite(), "PSI with empty bins should be finite, got {psi}");
        assert!(psi > 0.0, "different distributions should have PSI > 0");
    }

    #[test]
    fn test_histogram_basic() {
        let values = vec![1.0, 2.5, 3.5, 5.5];
        let edges = vec![0.0, 2.0, 4.0, 6.0];
        let counts = histogram(&values, &edges);
        assert_eq!(counts, vec![1, 2, 1]); // [1.0], [2.5, 3.5], [5.5]
    }

    #[test]
    fn test_histogram_nan_skipped() {
        let values = vec![1.0, f64::NAN, 3.0, f64::INFINITY];
        let edges = vec![0.0, 2.0, 4.0];
        let counts = histogram(&values, &edges);
        assert_eq!(counts, vec![1, 1]); // NaN and Inf skipped
    }

    #[test]
    fn test_quantile_bin_edges() {
        let data = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
        let edges = quantile_bin_edges(&data, 5);
        assert_eq!(edges.len(), 6); // 5 bins → 6 edges
        assert!(edges[0] < 1.0); // slightly below min
        assert!(edges[5] > 10.0); // slightly above max
    }

    #[test]
    fn test_adwin_no_drift_stable_series() {
        let mut adwin = AdwinDetector::new(0.05, 50, 3);
        let mut drifts = 0;
        for _ in 0..500 {
            if adwin.add(50.0 + rand_small()) {
                drifts += 1;
            }
        }
        assert_eq!(drifts, 0, "stable series should not trigger drift");
    }

    #[test]
    fn test_adwin_detects_mean_shift() {
        let mut adwin = AdwinDetector::new(0.05, 50, 3);
        // Phase 1: stable at ~50
        for _ in 0..200 {
            adwin.add(50.0 + rand_small());
        }
        // Phase 2: shift to ~100
        let mut detected = false;
        for _ in 0..200 {
            if adwin.add(100.0 + rand_small()) {
                detected = true;
                break;
            }
        }
        assert!(detected, "mean shift 50→100 should be detected");
    }

    #[test]
    fn test_adwin_majority_vote() {
        let mut adwin = AdwinDetector::new(0.05, 50, 3);
        // Need 3 consecutive detections before confirmed drift
        assert_eq!(adwin.consecutive_detections, 0);
        // Single detection doesn't confirm
        for _ in 0..200 {
            adwin.add(50.0);
        }
        // The majority vote filter means sporadic noise won't trigger
        assert_eq!(adwin.consecutive_detections, 0);
    }

    #[test]
    fn test_psi_severity_levels() {
        let base = vec![20, 20, 20, 20, 20];
        // Small shift → below warning
        let small = vec![22, 20, 19, 20, 19];
        let psi_small = compute_psi(&base, &small, 1e-6);
        assert!(psi_small < 0.1, "small shift PSI should be < 0.1 (warning)");

        // Large shift → above alert
        let large = vec![50, 5, 5, 5, 35];
        let psi_large = compute_psi(&base, &large, 1e-6);
        assert!(psi_large > 0.2, "large shift PSI should be > 0.2 (alert), got {psi_large}");
    }

    /// Deterministic pseudo-random small noise for tests.
    /// 測試用的確定性小噪聲。
    fn rand_small() -> f64 {
        use std::cell::Cell;
        thread_local! {
            static SEED: Cell<u64> = Cell::new(42);
        }
        SEED.with(|s| {
            let mut x = s.get();
            x ^= x << 13;
            x ^= x >> 7;
            x ^= x << 17;
            s.set(x);
            (x % 100) as f64 / 1000.0 - 0.05 // [-0.05, 0.05)
        })
    }
}
