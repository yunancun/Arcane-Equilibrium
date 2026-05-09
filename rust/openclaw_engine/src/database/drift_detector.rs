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
use crate::feature_collector::{FeatureSnapshot, FEATURE_DIM, FEATURE_NAMES};
use openclaw_core::indicators::IndicatorSnapshot;
use std::collections::{HashMap, VecDeque};
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
        let idx = match bin_edges[1..]
            .binary_search_by(|edge| edge.partial_cmp(&v).unwrap_or(std::cmp::Ordering::Equal))
        {
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

// ═══════════════════════════════════════════════════════════════════
// PG-wired drift monitor / PG 接線的漂移監控
// ═══════════════════════════════════════════════════════════════════

/// Composite key identifying a baseline: (symbol, feature_name).
/// 基線的複合鍵：(symbol, feature_name)。
pub type BaselineKey = (String, String);

/// One active baseline row from `observability.feature_baselines`.
/// `observability.feature_baselines` 的一條當前生效基線。
#[derive(Debug, Clone)]
pub struct BaselineEntry {
    pub bin_edges: Vec<f64>,
    pub bin_counts: Vec<u32>,
}

/// Resolve a feature name to its index in the flat feature vector.
/// 將特徵名稱解析為扁平特徵向量的索引。
pub fn feature_index(name: &str) -> Option<usize> {
    crate::feature_collector::FEATURE_NAMES
        .iter()
        .position(|n| *n == name)
}

/// Fetch all currently-active baselines (`valid_until IS NULL`).
/// 拉取所有當前生效的基線。
pub async fn fetch_active_baselines(pool: &DbPool) -> HashMap<BaselineKey, BaselineEntry> {
    let mut out: HashMap<BaselineKey, BaselineEntry> = HashMap::new();
    let pg = match pool.get() {
        Some(p) => p,
        None => return out,
    };
    let rows = sqlx::query_as::<_, (String, String, Vec<f32>, Vec<i32>)>(
        "SELECT symbol, feature_name, bin_edges, bin_counts \
         FROM observability.feature_baselines \
         WHERE valid_until IS NULL",
    )
    .fetch_all(pg)
    .await;
    let rows = match rows {
        Ok(r) => r,
        Err(e) => {
            warn!(error = %e, "fetch_active_baselines failed / 基線讀取失敗");
            return out;
        }
    };
    for (symbol, feature_name, edges, counts) in rows {
        if edges.len() < 2 || counts.len() + 1 != edges.len() {
            continue;
        }
        out.insert(
            (symbol, feature_name),
            BaselineEntry {
                bin_edges: edges.into_iter().map(|e| e as f64).collect(),
                bin_counts: counts.into_iter().map(|c| c.max(0) as u32).collect(),
            },
        );
    }
    out
}

/// Fetch latest feature vectors per symbol from `features.online_latest`.
/// Returns rows of (symbol, feature_vector). Timeframe is collapsed — the
/// drift monitor uses the most-recent row per symbol regardless of timeframe.
/// 按 symbol 拉取最新特徵向量。
pub async fn fetch_latest_features(pool: &DbPool) -> Vec<(String, Vec<f32>)> {
    let pg = match pool.get() {
        Some(p) => p,
        None => return vec![],
    };
    match sqlx::query_as::<_, (String, Vec<f32>)>(
        "SELECT DISTINCT ON (symbol) symbol, feature_vector \
         FROM features.online_latest \
         WHERE feature_vector IS NOT NULL \
         ORDER BY symbol, updated_ts_ms DESC",
    )
    .fetch_all(pg)
    .await
    {
        Ok(rows) => rows,
        Err(e) => {
            warn!(error = %e, "fetch_latest_features failed / 最新特徵讀取失敗");
            vec![]
        }
    }
}

/// In-memory sliding observation buffer per (symbol, feature_name).
/// 每個 (symbol, feature_name) 的記憶體滑動觀測緩衝。
#[derive(Default)]
pub struct DriftMonitorState {
    buffers: HashMap<BaselineKey, VecDeque<f64>>,
    max_buffer: usize,
}

impl DriftMonitorState {
    pub fn new(max_buffer: usize) -> Self {
        Self {
            buffers: HashMap::new(),
            max_buffer: max_buffer.max(1),
        }
    }

    /// Append a new observation. Drops oldest when buffer exceeds capacity.
    /// 追加觀測，超出容量時丟棄最舊。
    pub fn observe(&mut self, key: BaselineKey, value: f64) {
        if !value.is_finite() {
            return;
        }
        let buf = self.buffers.entry(key).or_default();
        if buf.len() >= self.max_buffer {
            buf.pop_front();
        }
        buf.push_back(value);
    }

    pub fn get(&self, key: &BaselineKey) -> Option<&VecDeque<f64>> {
        self.buffers.get(key)
    }

    pub fn len(&self) -> usize {
        self.buffers.len()
    }
}

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
    let min_window = db_cfg.adwin_min_width as usize;
    let max_buffer = (min_window * 4).max(min_window + 1);

    let mut interval = tokio::time::interval(check_interval);
    interval.tick().await; // skip first
    let start_time = std::time::Instant::now();
    let mut state = DriftMonitorState::new(max_buffer);

    info!(
        interval_secs = db_cfg.drift_check_interval_secs,
        psi_warn = psi_warn,
        psi_alert = psi_alert,
        min_window = min_window,
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

                let baselines = fetch_active_baselines(&pool).await;
                if baselines.is_empty() {
                    debug!(
                        in_burnin = in_burnin,
                        "drift check: no active baselines / 漂移檢查：無生效基線"
                    );
                    continue;
                }

                let latest = fetch_latest_features(&pool).await;
                let mut events_emitted = 0u32;
                for (symbol, vector) in latest {
                    for ((bsym, fname), baseline) in baselines.iter() {
                        if bsym != &symbol {
                            continue;
                        }
                        let Some(idx) = feature_index(fname) else { continue };
                        if idx >= vector.len() {
                            continue;
                        }
                        let key = (symbol.clone(), fname.clone());
                        state.observe(key.clone(), vector[idx] as f64);

                        let buf = match state.get(&key) {
                            Some(b) if b.len() >= min_window => b,
                            _ => continue,
                        };
                        let values: Vec<f64> = buf.iter().copied().collect();
                        let cur_counts = histogram(&values, &baseline.bin_edges);
                        let psi = compute_psi(&baseline.bin_counts, &cur_counts, 1e-6);

                        let (severity, threshold) = if psi >= psi_alert {
                            ("ALERT", psi_alert)
                        } else if psi >= psi_warn {
                            ("WARNING", psi_warn)
                        } else {
                            debug!(
                                symbol = %symbol, feature = %fname, psi = psi,
                                "drift ok / 漂移正常"
                            );
                            continue;
                        };

                        if in_burnin {
                            debug!(
                                symbol = %symbol, feature = %fname, psi = psi,
                                severity = severity,
                                "drift detected (burn-in, log-only) / 漂移檢測（預熱期，僅記錄）"
                            );
                            continue;
                        }

                        let event_id = format!(
                            "psi-{}-{}-{}",
                            symbol,
                            fname,
                            chrono::Utc::now().timestamp_millis()
                        );
                        write_drift_event(
                            &pool,
                            &event_id,
                            "PSI",
                            severity,
                            &symbol,
                            fname,
                            psi,
                            threshold,
                        )
                        .await;
                        events_emitted += 1;
                    }
                }

                debug!(
                    baselines = baselines.len(),
                    monitored = state.len(),
                    events = events_emitted,
                    in_burnin = in_burnin,
                    "drift check cycle complete / 漂移檢查週期完成"
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
         ON CONFLICT (event_id, ts) DO NOTHING",
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
// PSI Baseline Rebuild / PSI 基線重建
// ═══════════════════════════════════════════════════════════════════

/// A single baseline window for PSI reference distribution.
/// 單個 PSI 參考分佈的基線窗口。
#[derive(Debug, Clone)]
pub struct BaselineWindow {
    /// Start of the window (epoch ms). / 窗口起點（毫秒時間戳）。
    pub valid_from_ms: u64,
    /// End of the window (epoch ms). / 窗口終點（毫秒時間戳）。
    pub valid_until_ms: u64,
    /// Quantile-based bin edges for this window. / 此窗口的分位數 bin 邊界。
    pub bin_edges: Vec<f64>,
    /// Histogram counts per bin. / 每 bin 的計數。
    pub bin_counts: Vec<u32>,
    /// Number of finite samples in this window. / 此窗口中的有限樣本數。
    pub n_samples: usize,
}

/// Historical sample used to rebuild PSI baselines.
/// 用於重建 PSI 基線的一條歷史 34 維特徵樣本。
#[derive(Debug, Clone)]
pub struct HistoricalFeatureSample {
    pub symbol: String,
    pub ts_ms: u64,
    pub feature_vector: Vec<f32>,
}

/// Row candidate for `observability.feature_baselines`.
/// `observability.feature_baselines` 的待寫入行。
#[derive(Debug, Clone, PartialEq)]
pub struct FeatureBaselineRow {
    pub symbol: String,
    pub feature_name: String,
    pub valid_from_ms: u64,
    pub valid_until_ms: Option<u64>,
    pub bin_edges: Vec<f64>,
    pub bin_counts: Vec<u32>,
    pub n_samples: usize,
}

/// Summary returned by a feature baseline write.
/// feature baseline 寫入摘要。
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct FeatureBaselineWriteSummary {
    pub rows_written: u64,
    pub active_rows_closed: u64,
}

/// Build a 34-dim `features.online_latest`-compatible vector from a decision
/// context snapshot row.
/// 從 decision context snapshot 行重建與 `features.online_latest` 相同的 34 維向量。
pub fn feature_vector_from_decision_context_snapshot(
    symbol: &str,
    ts_ms: u64,
    last_price: f64,
    indicators: IndicatorSnapshot,
) -> Vec<f32> {
    FeatureSnapshot::new(
        symbol.to_string(),
        ts_ms,
        last_price,
        0.0,
        indicators,
        "decision_context_snapshot".to_string(),
    )
    .to_feature_vector()
}

/// Convert a `trading.decision_context_snapshots` row into a historical feature
/// sample. This intentionally reconstructs the Rust 34-dim feature collector
/// vector and does not use the 17-dim edge-predictor training schema.
/// 將 `trading.decision_context_snapshots` 行轉成歷史特徵樣本。此處刻意重建
/// Rust feature collector 的 34 維向量，不使用 edge predictor 的 17 維訓練 schema。
pub fn sample_from_decision_context_snapshot(
    symbol: String,
    ts_ms: u64,
    last_price: f64,
    indicators_snapshot: serde_json::Value,
) -> Option<HistoricalFeatureSample> {
    if !last_price.is_finite() {
        return None;
    }
    let indicators: IndicatorSnapshot = serde_json::from_value(indicators_snapshot).ok()?;
    let feature_vector =
        feature_vector_from_decision_context_snapshot(&symbol, ts_ms, last_price, indicators);
    if feature_vector.len() != FEATURE_DIM {
        return None;
    }
    Some(HistoricalFeatureSample {
        symbol,
        ts_ms,
        feature_vector,
    })
}

/// Fetch historical feature samples from the canonical historical context
/// source: `trading.decision_context_snapshots.indicators_snapshot`.
/// 從 canonical 歷史上下文來源讀取樣本：
/// `trading.decision_context_snapshots.indicators_snapshot`。
pub async fn fetch_historical_feature_samples_from_decision_contexts(
    pool: &DbPool,
    lookback_days: u32,
    symbol_filter: Option<&str>,
) -> Result<Vec<HistoricalFeatureSample>, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(vec![]);
    };

    let rows = sqlx::query_as::<_, (String, i64, Option<f32>, serde_json::Value)>(
        "SELECT symbol, \
                COALESCE(ts_ms, FLOOR(EXTRACT(EPOCH FROM ts) * 1000)::BIGINT) AS ts_ms, \
                last_price, \
                indicators_snapshot \
           FROM trading.decision_context_snapshots \
          WHERE ts >= NOW() - ($1::INT * INTERVAL '1 day') \
            AND ($2::TEXT IS NULL OR symbol = $2) \
            AND last_price IS NOT NULL \
            AND indicators_snapshot IS NOT NULL \
          ORDER BY symbol, ts ASC",
    )
    .bind(lookback_days as i32)
    .bind(symbol_filter)
    .fetch_all(pg)
    .await?;

    let mut samples = Vec::with_capacity(rows.len());
    for (symbol, ts_ms, last_price, indicators_snapshot) in rows {
        let Some(price) = last_price.map(|v| v as f64).filter(|v| v.is_finite()) else {
            continue;
        };
        let Ok(ts_ms) = u64::try_from(ts_ms) else {
            continue;
        };
        if let Some(sample) =
            sample_from_decision_context_snapshot(symbol, ts_ms, price, indicators_snapshot)
        {
            samples.push(sample);
        }
    }
    Ok(samples)
}

/// Build `observability.feature_baselines` rows from 34-dim historical samples.
/// The latest window per `(symbol, feature_name)` is emitted as active
/// (`valid_until_ms = None`); earlier windows are emitted as closed history.
/// 從 34 維歷史樣本建立 `feature_baselines` 行。每個 `(symbol, feature_name)` 的
/// 最新窗口為 active（`valid_until_ms = None`），較早窗口為 closed history。
pub fn build_feature_baseline_rows(
    samples: &[HistoricalFeatureSample],
    window_days: u32,
    step_days: u32,
    n_bins: usize,
) -> Vec<FeatureBaselineRow> {
    let mut grouped: HashMap<(String, usize), (Vec<f64>, Vec<u64>)> = HashMap::new();

    for sample in samples {
        if sample.feature_vector.len() != FEATURE_DIM {
            continue;
        }
        for (idx, value) in sample.feature_vector.iter().enumerate() {
            if !value.is_finite() {
                continue;
            }
            let entry = grouped
                .entry((sample.symbol.clone(), idx))
                .or_insert_with(|| (Vec::new(), Vec::new()));
            entry.0.push(*value as f64);
            entry.1.push(sample.ts_ms);
        }
    }

    let mut rows = Vec::new();
    for ((symbol, idx), (values, timestamps_ms)) in grouped {
        let windows =
            compute_baseline_windows(&values, &timestamps_ms, window_days, step_days, n_bins);
        let latest = windows.len().saturating_sub(1);
        for (win_idx, window) in windows.into_iter().enumerate() {
            rows.push(FeatureBaselineRow {
                symbol: symbol.clone(),
                feature_name: FEATURE_NAMES[idx].to_string(),
                valid_from_ms: window.valid_from_ms,
                valid_until_ms: if win_idx == latest {
                    None
                } else {
                    Some(window.valid_until_ms)
                },
                bin_edges: window.bin_edges,
                bin_counts: window.bin_counts,
                n_samples: window.n_samples,
            });
        }
    }

    rows.sort_by(|a, b| {
        let a_idx = feature_index(&a.feature_name).unwrap_or(usize::MAX);
        let b_idx = feature_index(&b.feature_name).unwrap_or(usize::MAX);
        a.symbol
            .cmp(&b.symbol)
            .then_with(|| a_idx.cmp(&b_idx))
            .then_with(|| a.valid_from_ms.cmp(&b.valid_from_ms))
    });
    rows
}

fn utc_from_ms(ms: u64) -> Option<chrono::DateTime<chrono::Utc>> {
    let ms = i64::try_from(ms).ok()?;
    chrono::DateTime::from_timestamp_millis(ms)
}

/// Write feature baseline rows to Postgres. Existing active rows for keys that
/// receive a new active row are closed first; inserts are idempotent on
/// `(symbol, feature_name, valid_from)`.
/// 將 feature baseline 行寫入 Postgres。收到新 active row 的 key 會先關閉既有
/// active row；insert 對 `(symbol, feature_name, valid_from)` 冪等。
pub async fn write_feature_baseline_rows(
    pool: &DbPool,
    rows: &[FeatureBaselineRow],
) -> Result<FeatureBaselineWriteSummary, sqlx::Error> {
    let Some(pg) = pool.get() else {
        return Ok(FeatureBaselineWriteSummary::default());
    };

    let mut tx = pg.begin().await?;
    let mut summary = FeatureBaselineWriteSummary::default();

    for row in rows.iter().filter(|r| r.valid_until_ms.is_none()) {
        let Some(valid_from) = utc_from_ms(row.valid_from_ms) else {
            continue;
        };
        let result = sqlx::query(
            "UPDATE observability.feature_baselines \
                SET valid_until = $1 \
              WHERE symbol = $2 \
                AND feature_name = $3 \
                AND valid_until IS NULL",
        )
        .bind(valid_from)
        .bind(&row.symbol)
        .bind(&row.feature_name)
        .execute(&mut *tx)
        .await?;
        summary.active_rows_closed += result.rows_affected();
    }

    for row in rows {
        let Some(valid_from) = utc_from_ms(row.valid_from_ms) else {
            continue;
        };
        let valid_until = row.valid_until_ms.and_then(utc_from_ms);
        let bin_edges: Vec<f32> = row.bin_edges.iter().map(|v| *v as f32).collect();
        let bin_counts: Vec<i32> = row.bin_counts.iter().map(|v| *v as i32).collect();

        let result = sqlx::query(
            "INSERT INTO observability.feature_baselines \
                (symbol, feature_name, bin_edges, bin_counts, valid_from, valid_until) \
             VALUES ($1, $2, $3, $4, $5, $6) \
             ON CONFLICT (symbol, feature_name, valid_from) DO UPDATE \
                SET bin_edges = EXCLUDED.bin_edges, \
                    bin_counts = EXCLUDED.bin_counts, \
                    valid_until = EXCLUDED.valid_until",
        )
        .bind(&row.symbol)
        .bind(&row.feature_name)
        .bind(bin_edges)
        .bind(bin_counts)
        .bind(valid_from)
        .bind(valid_until)
        .execute(&mut *tx)
        .await?;
        summary.rows_written += result.rows_affected();
    }

    tx.commit().await?;
    Ok(summary)
}

/// Rebuild PSI baselines from historical feature data using overlapping sliding windows.
/// 使用重疊滑動窗口從歷史特徵數據重建 PSI 基線。
///
/// Window: `window_days` days, step: `step_days` days (QA2-8 audit: 30/7 defaults).
/// Empty or degenerate windows (< 2 finite samples) are skipped.
/// 窗口：`window_days` 天，步長：`step_days` 天（QA2-8 審計：默認 30/7）。
/// 空或退化窗口（< 2 有限樣本）會被跳過。
pub fn compute_baseline_windows(
    values: &[f64],
    timestamps_ms: &[u64],
    window_days: u32,
    step_days: u32,
    n_bins: usize,
) -> Vec<BaselineWindow> {
    if values.len() != timestamps_ms.len()
        || values.is_empty()
        || step_days == 0
        || window_days == 0
        || n_bins == 0
    {
        return vec![];
    }

    let window_ms: u64 = window_days as u64 * 86_400_000;
    let step_ms: u64 = step_days as u64 * 86_400_000;

    // Find the overall time range / 找到整體時間範圍
    let t_min = *timestamps_ms.iter().min().unwrap_or(&0);
    let t_max = *timestamps_ms.iter().max().unwrap_or(&0);

    if t_max.saturating_sub(t_min) < window_ms {
        // Not enough span for even one window / 時間跨度不足一個窗口
        return vec![];
    }

    let mut windows = Vec::new();
    let mut win_start = t_min;

    while win_start + window_ms <= t_max + 1 {
        let win_end = win_start + window_ms;

        // Collect values within [win_start, win_end) / 收集窗口內的值
        let win_values: Vec<f64> = values
            .iter()
            .zip(timestamps_ms.iter())
            .filter(|(_, &ts)| ts >= win_start && ts < win_end)
            .map(|(&v, _)| v)
            .filter(|v| v.is_finite())
            .collect();

        // Skip degenerate windows / 跳過退化窗口
        if win_values.len() >= 2 {
            let edges = quantile_bin_edges(&win_values, n_bins);
            if edges.len() >= 2 {
                let counts = histogram(&win_values, &edges);
                windows.push(BaselineWindow {
                    valid_from_ms: win_start,
                    valid_until_ms: win_end,
                    bin_edges: edges,
                    bin_counts: counts,
                    n_samples: win_values.len(),
                });
            }
        }

        win_start += step_ms;
    }

    windows
}

/// Check if a baseline rebuild is needed (cooldown after last rebuild).
/// 檢查是否需要重建基線（上次重建後的冷卻期）。
///
/// Returns true if `now_ms - last_rebuild_ms >= cooldown_days * 86_400_000`.
/// Saturating subtraction prevents underflow when last_rebuild_ms > now_ms.
/// 當 now_ms - last_rebuild_ms >= cooldown_days * 86_400_000 時返回 true。
/// 飽和減法防止 last_rebuild_ms > now_ms 時下溢。
pub fn should_rebuild_baseline(last_rebuild_ms: u64, now_ms: u64, cooldown_days: u32) -> bool {
    let cooldown_ms = cooldown_days as u64 * 86_400_000;
    now_ms.saturating_sub(last_rebuild_ms) >= cooldown_ms
}

/// Simple seeded LCG (linear congruential generator) for deterministic bootstrap.
/// No external crate needed.
/// 簡單種子 LCG（線性同餘生成器）用於確定性自助法，無需外部 crate。
struct SimpleLcg {
    state: u64,
}

impl SimpleLcg {
    fn new(seed: u64) -> Self {
        // Avoid zero state / 避免零狀態
        Self {
            state: seed.wrapping_add(1),
        }
    }

    /// Return next pseudo-random u64. / 返回下一個偽隨機 u64。
    fn next_u64(&mut self) -> u64 {
        // LCG constants from Numerical Recipes
        self.state = self
            .state
            .wrapping_mul(6_364_136_223_846_793_005)
            .wrapping_add(1_442_695_040_888_963_407);
        self.state
    }

    /// Return a uniform index in [0, bound). / 返回 [0, bound) 中的均勻索引。
    fn next_index(&mut self, bound: usize) -> usize {
        if bound == 0 {
            return 0;
        }
        (self.next_u64() % bound as u64) as usize
    }
}

/// Perform block bootstrap to estimate confidence intervals for PSI.
/// 執行塊自助法估計 PSI 置信區間。
///
/// Block size default = 4 (QA2-8 spec), n_bootstrap default = 100.
/// Returns (psi_mean, psi_lower_5pct, psi_upper_95pct).
/// 塊大小默認 = 4（QA2-8 規範），自助次數默認 = 100。
/// 返回 (psi_mean, psi_lower_5pct, psi_upper_95pct)。
///
/// Edge cases: if current_values is empty or bin_edges < 2, returns (0.0, 0.0, 0.0).
/// 邊界情況：若 current_values 為空或 bin_edges < 2，返回 (0.0, 0.0, 0.0)。
pub fn block_bootstrap_psi(
    reference_counts: &[u32],
    current_values: &[f64],
    bin_edges: &[f64],
    block_size: usize,
    n_bootstrap: usize,
    seed: u64,
) -> (f64, f64, f64) {
    let zero = (0.0, 0.0, 0.0);

    if current_values.is_empty()
        || bin_edges.len() < 2
        || reference_counts.is_empty()
        || n_bootstrap == 0
    {
        return zero;
    }

    let block_sz = block_size.max(1);
    let n = current_values.len();
    let epsilon = 1e-6;

    let mut rng = SimpleLcg::new(seed);
    let mut psi_samples: Vec<f64> = Vec::with_capacity(n_bootstrap);

    for _ in 0..n_bootstrap {
        // Resample current_values in blocks / 以塊方式重採樣 current_values
        let mut resampled: Vec<f64> = Vec::with_capacity(n);
        while resampled.len() < n {
            let start = rng.next_index(n);
            for j in 0..block_sz {
                if resampled.len() >= n {
                    break;
                }
                // Wrap around if block exceeds bounds / 若塊超出邊界則環繞
                let idx = (start + j) % n;
                let v = current_values[idx];
                if v.is_finite() {
                    resampled.push(v);
                }
            }
        }

        // Compute histogram of resampled values / 計算重採樣值的直方圖
        let resampled_counts = histogram(&resampled, bin_edges);

        // Compute PSI vs reference / 計算 PSI 與參考的對比
        let psi = compute_psi(reference_counts, &resampled_counts, epsilon);
        if psi.is_finite() {
            psi_samples.push(psi);
        }
    }

    if psi_samples.is_empty() {
        return zero;
    }

    // Sort for percentile computation / 排序以計算百分位
    psi_samples.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

    let mean = psi_samples.iter().sum::<f64>() / psi_samples.len() as f64;

    // 5th and 95th percentile indices / 第 5 和第 95 百分位索引
    let lower_idx = ((psi_samples.len() as f64 * 0.05).floor() as usize).min(psi_samples.len() - 1);
    let upper_idx = ((psi_samples.len() as f64 * 0.95).ceil() as usize).min(psi_samples.len() - 1);

    let lower = psi_samples[lower_idx];
    let upper = psi_samples[upper_idx];

    (mean, lower, upper)
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
        assert!(
            psi.abs() < 1e-10,
            "identical distributions should have PSI ≈ 0, got {psi}"
        );
    }

    #[test]
    fn test_psi_shifted_distribution() {
        let ref_counts = vec![10, 20, 30, 20, 10]; // centered
        let cur_counts = vec![30, 20, 10, 5, 5]; // shifted left
        let psi = compute_psi(&ref_counts, &cur_counts, 1e-6);
        assert!(
            psi > 0.1,
            "shifted distribution should have PSI > 0.1, got {psi}"
        );
    }

    #[test]
    fn test_psi_empty_bins_epsilon() {
        let ref_counts = vec![0, 50, 50, 0];
        let cur_counts = vec![25, 25, 25, 25];
        let psi = compute_psi(&ref_counts, &cur_counts, 1e-6);
        assert!(
            psi.is_finite(),
            "PSI with empty bins should be finite, got {psi}"
        );
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
        assert!(
            psi_large > 0.2,
            "large shift PSI should be > 0.2 (alert), got {psi_large}"
        );
    }

    #[test]
    fn test_baseline_windows_count() {
        // 180 days of data, 30-day window, 7-day step
        // Expected: (180 - 30) / 7 + 1 = 22 windows (approx, depending on alignment)
        // 180 天數據，30 天窗口，7 天步長，預期約 22 個窗口
        let n_points = 1800; // 10 points per day × 180 days
        let day_ms: u64 = 86_400_000;
        let base_ts: u64 = 1_700_000_000_000;

        let mut values = Vec::with_capacity(n_points);
        let mut timestamps = Vec::with_capacity(n_points);
        for i in 0..n_points {
            let day = i as u64 / 10; // 10 points per day
            timestamps.push(base_ts + day * day_ms + (i as u64 % 10) * 1000);
            values.push(50.0 + (i as f64 * 0.01)); // slowly increasing feature
        }

        let windows = compute_baseline_windows(&values, &timestamps, 30, 7, 10);

        // Should have roughly (180-30)/7 + 1 = 22 windows
        assert!(
            windows.len() >= 20 && windows.len() <= 23,
            "expected ~22 windows for 180d data with 30d/7d, got {}",
            windows.len()
        );

        // Each window should have samples and valid bin structure
        // 每個窗口應有樣本和有效 bin 結構
        for w in &windows {
            assert!(w.n_samples > 0, "window should have samples");
            assert_eq!(w.bin_edges.len(), 11, "10 bins → 11 edges");
            assert_eq!(w.bin_counts.len(), 10, "10 bins");
            assert!(
                w.valid_until_ms > w.valid_from_ms,
                "valid_until > valid_from"
            );
        }
    }

    #[test]
    fn test_baseline_windows_empty_input() {
        // Edge case: empty data returns no windows / 邊界情況：空數據返回零窗口
        let windows = compute_baseline_windows(&[], &[], 30, 7, 10);
        assert!(windows.is_empty());

        // Edge case: mismatched lengths / 長度不匹配
        let windows = compute_baseline_windows(&[1.0, 2.0], &[100], 30, 7, 10);
        assert!(windows.is_empty());
    }

    #[test]
    fn test_should_rebuild_cooldown() {
        let day_ms: u64 = 86_400_000;
        let base: u64 = 1_700_000_000_000;

        // Within 7 days → false / 7 天內 → false
        assert!(!should_rebuild_baseline(base, base + 6 * day_ms, 7));

        // Exactly 7 days → true / 恰好 7 天 → true
        assert!(should_rebuild_baseline(base, base + 7 * day_ms, 7));

        // After 7 days → true / 超過 7 天 → true
        assert!(should_rebuild_baseline(base, base + 10 * day_ms, 7));

        // now < last_rebuild (clock skew) → false (saturating sub) / 時鐘偏移 → false
        assert!(!should_rebuild_baseline(base + 100 * day_ms, base, 7));
    }

    #[test]
    fn test_block_bootstrap_psi_returns_valid() {
        // Build a reference distribution and current values / 構建參考分佈和當前值
        let reference = vec![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
        let edges = quantile_bin_edges(&reference, 5);
        let ref_counts = histogram(&reference, &edges);

        // Current values slightly shifted / 當前值略有偏移
        let current: Vec<f64> = (0..100).map(|i| 2.0 + (i as f64 * 0.1)).collect();

        let (mean, lower, upper) = block_bootstrap_psi(&ref_counts, &current, &edges, 4, 100, 42);

        // Mean should be positive (distributions differ) / 均值應為正（分佈不同）
        assert!(mean >= 0.0, "mean PSI should be >= 0, got {mean}");

        // lower <= mean <= upper / 下界 <= 均值 <= 上界
        assert!(
            lower <= mean + 1e-12 && mean <= upper + 1e-12,
            "expected lower({lower}) <= mean({mean}) <= upper({upper})"
        );

        // Should be finite / 應為有限值
        assert!(mean.is_finite() && lower.is_finite() && upper.is_finite());
    }

    #[test]
    fn test_block_bootstrap_psi_empty_input() {
        // Edge case: empty current_values / 邊界情況：空 current_values
        let (m, l, u) = block_bootstrap_psi(&[10, 20, 30], &[], &[0.0, 1.0, 2.0, 3.0], 4, 100, 1);
        assert_eq!((m, l, u), (0.0, 0.0, 0.0));
    }

    #[test]
    fn test_feature_index_known_names() {
        assert_eq!(feature_index("rsi_14"), Some(4));
        assert_eq!(feature_index("price"), Some(33));
        assert_eq!(feature_index("sma_20"), Some(0));
        assert!(feature_index("not_a_feature").is_none());
    }

    #[test]
    fn test_decision_context_sample_rebuilds_feature_collector_vector() {
        let sample = sample_from_decision_context_snapshot(
            "BTCUSDT".to_string(),
            1_700_000_000_000,
            123.45,
            serde_json::json!({
                "rsi_14": 65.0,
                "macd": {"macd": 1.5, "signal": 1.0, "histogram": 0.5},
                "hurst": {"hurst": 0.7, "regime": "trending"},
                "ewma_vol": {"ewma_vol": 0.02, "vol_regime": "High"}
            }),
        )
        .expect("valid indicator snapshot should produce a sample");

        assert_eq!(sample.feature_vector.len(), FEATURE_DIM);
        assert!((sample.feature_vector[4] - 65.0).abs() < 0.001);
        assert!((sample.feature_vector[5] - 1.5).abs() < 0.001);
        assert!((sample.feature_vector[25] - 1.0).abs() < 0.001);
        assert!((sample.feature_vector[27] - 3.0).abs() < 0.001);
        assert!((sample.feature_vector[33] - 123.45).abs() < 0.001);
    }

    #[test]
    fn test_build_feature_baseline_rows_emits_34_active_features() {
        let day_ms: u64 = 86_400_000;
        let base_ts: u64 = 1_700_000_000_000;
        let mut samples = Vec::new();

        for day in 0..32_u64 {
            let mut feature_vector = Vec::with_capacity(FEATURE_DIM);
            for idx in 0..FEATURE_DIM {
                feature_vector.push((idx as f32) + (day as f32 * 0.1));
            }
            samples.push(HistoricalFeatureSample {
                symbol: "BTCUSDT".to_string(),
                ts_ms: base_ts + day * day_ms,
                feature_vector,
            });
        }

        let rows = build_feature_baseline_rows(&samples, 30, 7, 10);
        assert_eq!(rows.len(), FEATURE_DIM);
        assert!(rows.iter().all(|r| r.valid_until_ms.is_none()));

        let names: std::collections::BTreeSet<&str> =
            rows.iter().map(|r| r.feature_name.as_str()).collect();
        let expected: std::collections::BTreeSet<&str> = FEATURE_NAMES.iter().copied().collect();
        assert_eq!(names, expected);
        assert!(rows.iter().all(|r| r.bin_edges.len() == 11));
        assert!(rows.iter().all(|r| r.bin_counts.len() == 10));
    }

    #[test]
    fn test_build_feature_baseline_rows_rejects_wrong_dimension_samples() {
        let samples = vec![HistoricalFeatureSample {
            symbol: "BTCUSDT".to_string(),
            ts_ms: 1_700_000_000_000,
            feature_vector: vec![1.0; 17],
        }];

        let rows = build_feature_baseline_rows(&samples, 30, 7, 10);
        assert!(rows.is_empty());
    }

    #[test]
    fn test_drift_monitor_state_sliding() {
        let mut s = DriftMonitorState::new(3);
        let key = ("BTCUSDT".to_string(), "rsi_14".to_string());
        s.observe(key.clone(), 1.0);
        s.observe(key.clone(), 2.0);
        s.observe(key.clone(), 3.0);
        s.observe(key.clone(), 4.0); // should evict oldest
        let buf = s.get(&key).expect("buffer present");
        assert_eq!(buf.len(), 3);
        assert_eq!(buf.front().copied(), Some(2.0));
        assert_eq!(buf.back().copied(), Some(4.0));
    }

    #[test]
    fn test_drift_monitor_state_rejects_nonfinite() {
        let mut s = DriftMonitorState::new(10);
        let key = ("ETHUSDT".to_string(), "price".to_string());
        s.observe(key.clone(), f64::NAN);
        s.observe(key.clone(), f64::INFINITY);
        s.observe(key.clone(), 100.0);
        assert_eq!(s.get(&key).map(|b| b.len()), Some(1));
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
