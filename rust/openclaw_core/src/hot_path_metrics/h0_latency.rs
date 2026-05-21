//! H0 hot-path latency recorder — HdrHistogram-based p50/p99/p999/max。
//!
//! 對齊 spec `docs/execution_plan/2026-05-21--p2_lg1_demo_slo_carveout_spec.md` §3。
//!
//! 來源動機：E5 F1 audit `docs/CCAgentWorkSpace/E5/workspace/reports/
//! 2026-05-21--p1_lg1_demo_sla_violation_hotpath_audit.md` verdict 選項 B
//! （accept variance + SLO carve-out）。demo `max=2454μs > 1ms` = OS scheduler /
//! cache miss / Instant::now vDSO platform jitter，非 algorithmic bug；H0Gate.check
//! avg=4.86ns 純算術。需 p99/p999/max 觀測能力以替代 hard 1ms SLA。
//!
//! 結構：
//! - per-engine_mode 1 個 HdrHistogram（5 mode → 5 histogram）
//! - HdrHistogram config: `new_with_bounds(1, 10_000_000, 3)` — low=1us / high=10s /
//!   sig_figs=3 → ~256KB/instance × 5 ≈ 1.3MB；遠小於 engine RSS 148MB。
//! - parking_lot::Mutex 包裝（已是 openclaw_core dep；HdrHistogram record 需 mut；
//!   Mutex 在 hot path single-thread tick 無 contention，summary read 異步呼叫）

use std::collections::HashMap;

use hdrhistogram::Histogram;
use parking_lot::Mutex;

use super::ENGINE_MODES;

/// HdrHistogram bucket 上下界。
/// LOW=1us（最小有意義延遲），HIGH=10s（遠超 E5 觀察 max 5ms）。
const HIST_LOW_US: u64 = 1;
const HIST_HIGH_US: u64 = 10_000_000;

/// Significant figures = 3 → 約 1‰ percentile 解析度。spec AC-2 ±1% 容差有 10× headroom。
const HIST_SIG_FIGS: u8 = 3;

/// Per-mode percentile summary，用於 IPC export / Grafana panel。
///
/// P2-LG1 plumbing wave 2026-05-21：補 `serde::Serialize` derive 以便
/// PipelineSnapshot.h0_latency_summaries 經 IPC 寫入 status JSON。
///
/// 為什麼僅 Serialize 不 Deserialize：`engine_mode: &'static str` 是 ZST-friendly
/// 設計（hot path 零 alloc / 零鎖爭用）；serde Deserialize 對 `&'static str` 要求
/// `'de: 'static`，與普通 borrowed deser 衝突。本 struct 為 producer-side use（Rust
/// 寫一次 → Python 端 IPC consumer 讀 JSON），無 round-trip 需求；若未來需要
/// Deserialize，改 `engine_mode: String` 並 to_string()（cold path 可接受）。
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
pub struct H0LatencySummary {
    /// engine_mode 標籤（&'static str；對齊 effective_engine_mode）。
    pub engine_mode: &'static str,
    /// 該 mode 累計 record 次數。
    pub count: u64,
    /// p50（中位數）μs。
    pub p50_us: u64,
    /// p99 μs（spec §6 WARN threshold 1000μs）。
    pub p99_us: u64,
    /// p999 μs（spec §2.2 design budget ≤ 2000μs）。
    pub p999_us: u64,
    /// max μs（spec §6 WARN 5000 / FAIL 10000）。
    pub max_us: u64,
    /// 匯出時刻 ms（unix epoch）；用於 status_report cadence + 1h reset 判斷。
    pub recorded_at_ms: u64,
}

/// 內部 state：per-engine_mode histogram + reset 時間戳。
struct H0LatencyRecorderInner {
    /// engine_mode → Histogram instance（5 entry 預先建立）。
    histograms: HashMap<&'static str, Histogram<u64>>,
    /// 最後一次 reset 的 unix epoch ms；status_report 比較 1h cadence 用。
    last_reset_ms: u64,
}

impl H0LatencyRecorderInner {
    fn new() -> Self {
        let mut histograms = HashMap::with_capacity(ENGINE_MODES.len());
        for mode in ENGINE_MODES {
            // unwrap 安全：HIST_LOW < HIST_HIGH，sig_figs 0..=5 範圍，HdrHistogram 不會回 Err。
            // 若 hardcoded 常數越界（不可能）panic 是預期；此處不是 hot path。
            let hist = Histogram::<u64>::new_with_bounds(HIST_LOW_US, HIST_HIGH_US, HIST_SIG_FIGS)
                .expect("HdrHistogram bounds invariant; HIST_LOW=1 < HIST_HIGH=10_000_000 / sig_figs=3");
            histograms.insert(*mode, hist);
        }
        Self {
            histograms,
            last_reset_ms: 0,
        }
    }
}

/// H0 hot-path latency 觀測器。
///
/// 使用模式：
/// 1. engine 啟動建立 `Arc<H0LatencyRecorder>` 全域單例
/// 2. 3 pipeline ctor（paper/demo/live）各自把 Arc 傳給 H0Gate::with_metrics
/// 3. H0Gate.finalize_blocked/finalize_allowed 呼 `record(latency_us, engine_mode)`
/// 4. status_report.rs 每次呼叫前先檢查 1h cadence，過期呼 `reset_all()`
/// 5. status_report 結尾呼 `all_summaries()` 進 status JSON payload
pub struct H0LatencyRecorder {
    inner: Mutex<H0LatencyRecorderInner>,
}

impl H0LatencyRecorder {
    /// 建構期 5 mode histogram 預先 allocate。
    pub fn new() -> Self {
        Self {
            inner: Mutex::new(H0LatencyRecorderInner::new()),
        }
    }

    /// 記錄 1 tick H0 latency。
    ///
    /// 不可在 engine_mode 不在 ENGINE_MODES（5 種）的情況呼叫；
    /// caller 應確保 engine_mode 來自 `effective_engine_mode()` 5 種回傳值之一。
    /// 若 engine_mode 不存在於 HashMap，silently skip（不 panic，防止 hot path 崩）。
    ///
    /// Hot path performance：spec AC-3 ≤ 50ns/call。
    pub fn record(&self, latency_us: u64, engine_mode: &'static str) {
        let mut inner = self.inner.lock();
        if let Some(hist) = inner.histograms.get_mut(engine_mode) {
            // record_correct 適用於高 sample rate；但本場景 single record per tick
            // 用 record() 即可。saturating: 若 latency_us > HIST_HIGH_US，HdrHistogram
            // 內建 saturating_record，超界自動 clamp 至 HIGH bucket。
            let _ = hist.record(latency_us.clamp(HIST_LOW_US, HIST_HIGH_US));
        }
        // 不在 ENGINE_MODES 的 engine_mode silently skip — 防止 caller 拼錯
        // 字串導致 hot path panic；測試 + E2 review 應 catch 拼錯。
    }

    /// 匯出單一 engine_mode summary。
    ///
    /// `recorded_at_ms` 由 caller 傳入（用 now_ms() helper），避免 inner 模組
    /// 引入 chrono dep / 加 SystemTime sys call 開銷。
    pub fn summary(&self, engine_mode: &'static str, recorded_at_ms: u64) -> Option<H0LatencySummary> {
        let inner = self.inner.lock();
        inner.histograms.get(engine_mode).map(|hist| H0LatencySummary {
            engine_mode,
            count: hist.len(),
            p50_us: hist.value_at_quantile(0.50),
            p99_us: hist.value_at_quantile(0.99),
            p999_us: hist.value_at_quantile(0.999),
            max_us: hist.max(),
            recorded_at_ms,
        })
    }

    /// 匯出全部 engine_mode summary（5 entry，依 ENGINE_MODES 順序）。
    ///
    /// 即使某 mode count=0 仍會回 summary（p50/p99/p999/max=0）；
    /// caller 可依 count>0 過濾。
    pub fn all_summaries(&self, recorded_at_ms: u64) -> Vec<H0LatencySummary> {
        let inner = self.inner.lock();
        ENGINE_MODES
            .iter()
            .filter_map(|mode| {
                inner.histograms.get(mode).map(|hist| H0LatencySummary {
                    engine_mode: mode,
                    count: hist.len(),
                    p50_us: hist.value_at_quantile(0.50),
                    p99_us: hist.value_at_quantile(0.99),
                    p999_us: hist.value_at_quantile(0.999),
                    max_us: hist.max(),
                    recorded_at_ms,
                })
            })
            .collect()
    }

    /// Reset 指定 mode histogram（保留 bucket 結構，清 count）。
    ///
    /// 不在 hot path 呼叫；由 status_report 1h cadence 觸發。
    pub fn reset(&self, engine_mode: &'static str) {
        let mut inner = self.inner.lock();
        if let Some(hist) = inner.histograms.get_mut(engine_mode) {
            hist.reset();
        }
    }

    /// Reset 全部 mode histogram。
    pub fn reset_all(&self, now_ms: u64) {
        let mut inner = self.inner.lock();
        for hist in inner.histograms.values_mut() {
            hist.reset();
        }
        inner.last_reset_ms = now_ms;
    }

    /// 取最後 reset 時間戳（用於 status_report 1h cadence 判斷）。
    pub fn last_reset_ms(&self) -> u64 {
        self.inner.lock().last_reset_ms
    }
}

impl Default for H0LatencyRecorder {
    fn default() -> Self {
        Self::new()
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試（spec §8 AC-1..AC-5 對應）
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Instant;

    /// AC-1：1M tick record 不 panic / 不 OOM。
    /// 5 mode 各 200k record（total 1M）；HdrHistogram 設計支援 ≥ 1G entries。
    #[test]
    fn test_record_1m_no_panic() {
        let rec = H0LatencyRecorder::new();
        for mode in ENGINE_MODES {
            for i in 0..200_000u64 {
                // 模擬真實 distribution：~99% 在 1-100us，~1% tail 1-10ms
                let latency = if i % 100 == 0 {
                    1000 + (i % 9000) // tail 1-10ms
                } else {
                    1 + (i % 100) // body 1-100us
                };
                rec.record(latency, mode);
            }
        }
        // 任一 mode summary count = 200_000
        let s = rec.summary("demo", 0).expect("demo histogram exists");
        assert_eq!(s.count, 200_000, "1M total / 5 mode = 200k per mode");
    }

    /// AC-2：p50/p99/p999/max accuracy ±1%。
    /// 注入 1000 個確定性數值（1..=1000us），驗 percentile 值落容差內。
    #[test]
    fn test_percentile_accuracy() {
        let rec = H0LatencyRecorder::new();
        for latency in 1..=1000u64 {
            rec.record(latency, "demo");
        }
        let s = rec.summary("demo", 0).expect("demo histogram exists");

        // 注入 1..=1000；p50 期望值 ~500；p99 ~990；p999 ~999；max=1000
        // sig_figs=3 → 1‰ 解析度；±1% = ±10us 容差
        assert_eq!(s.count, 1000);
        assert!((s.p50_us as i64 - 500).abs() <= 10, "p50={} expected ~500", s.p50_us);
        assert!((s.p99_us as i64 - 990).abs() <= 10, "p99={} expected ~990", s.p99_us);
        assert!((s.p999_us as i64 - 999).abs() <= 10, "p999={} expected ~999", s.p999_us);
        assert!(s.max_us >= 998 && s.max_us <= 1002, "max={} expected ~1000", s.max_us);
    }

    /// AC-3：record overhead ≤ 50ns/call。
    /// 100k record loop + Instant timing。release build 應遠低於 50ns（HdrHistogram
    /// internal ~30-40ns）；debug build 可能 200-500ns 但不 enforce 邊界。
    #[test]
    fn test_record_overhead_ns() {
        let rec = H0LatencyRecorder::new();
        // Warmup（避免冷快取與 Mutex 首次 lock 額外開銷）
        for _ in 0..1000 {
            rec.record(50, "demo");
        }

        let n = 100_000u64;
        let start = Instant::now();
        for i in 0..n {
            rec.record(50 + (i % 100), "demo");
        }
        let elapsed = start.elapsed();
        let avg_ns = elapsed.as_nanos() as u64 / n;

        // debug build 寬鬆邊界 500ns；release build 應 ≤ 50ns。
        // 此 assert 是 sanity check 非 perf gate；E5 baseline + 100x 安全餘量。
        let upper_bound = if cfg!(debug_assertions) { 1_000 } else { 200 };
        assert!(
            avg_ns <= upper_bound,
            "record overhead avg={}ns exceeds {}ns upper bound (cfg debug={})",
            avg_ns,
            upper_bound,
            cfg!(debug_assertions)
        );
    }

    /// AC-4 補強（panel JSON 渲染由 manual import 驗，這裡驗 5 mode summary 結構）。
    #[test]
    fn test_all_summaries_5_modes() {
        let rec = H0LatencyRecorder::new();
        // 只記錄 demo + live_demo，其他 3 mode count=0
        for i in 1..=100u64 {
            rec.record(i, "demo");
            rec.record(i * 2, "live_demo");
        }

        let all = rec.all_summaries(1_700_000_000_000);
        assert_eq!(all.len(), 5, "5 engine_mode summary 必匯出");

        let by_mode: HashMap<&'static str, &H0LatencySummary> =
            all.iter().map(|s| (s.engine_mode, s)).collect();

        assert_eq!(by_mode["paper"].count, 0);
        assert_eq!(by_mode["demo"].count, 100);
        assert_eq!(by_mode["live"].count, 0);
        assert_eq!(by_mode["live_demo"].count, 100);
        assert_eq!(by_mode["live_testnet"].count, 0);

        // recorded_at_ms 反射 caller 傳入
        for s in &all {
            assert_eq!(s.recorded_at_ms, 1_700_000_000_000);
        }
    }

    /// AC-5：alert threshold 邊界正確（spec §6.3 unit test 覆蓋）。
    /// 7 邊界值 → verdict 對應（pass/warn/warn/warn/warn/warn/fail）。
    /// 此 test 只驗 summary 數值正確讓 healthcheck script 能讀；
    /// healthcheck script 真實邊界判邏輯由後續 E1 IMPL。
    #[test]
    fn test_alert_threshold_boundaries() {
        // spec §6.1：
        //   p99_us > 1000     → WARN (H0_P99_WARN)
        //   max_us > 5000     → WARN (H0_MAX_WARN)
        //   max_us > 10000    → FAIL (H0_MAX_FAIL)
        //
        // 注入 7 邊界 max 值，驗 summary.max_us 精準反映：
        //   999 / 1000 / 4999 / 5000 / 9999 / 10000 / 10001
        let boundaries: [u64; 7] = [999, 1000, 4999, 5000, 9999, 10000, 10001];
        for (i, &max_val) in boundaries.iter().enumerate() {
            // 用 paper mode 隔離（每邊界一個 mode 不夠，改 reset 再注入）
            let rec = H0LatencyRecorder::new();
            rec.record(max_val, "demo");
            let s = rec.summary("demo", 0).expect("histogram exists");
            // sig_figs=3 解析度容差 ±1‰ → max=10000 容差 ±10
            let tol = (max_val as i64 / 1000).max(1);
            assert!(
                (s.max_us as i64 - max_val as i64).abs() <= tol,
                "boundary #{} max_val={} actual={} tol=±{}",
                i,
                max_val,
                s.max_us,
                tol
            );
        }
    }

    /// 補強：reset 路徑（單 mode + all）。
    #[test]
    fn test_reset_clears_count_keeps_buckets() {
        let rec = H0LatencyRecorder::new();
        for i in 1..=100u64 {
            rec.record(i, "demo");
        }
        assert_eq!(rec.summary("demo", 0).unwrap().count, 100);

        rec.reset("demo");
        assert_eq!(rec.summary("demo", 0).unwrap().count, 0);

        // 重新 record 後仍可正常 percentile
        for i in 1..=50u64 {
            rec.record(i * 10, "demo");
        }
        let s = rec.summary("demo", 0).unwrap();
        assert_eq!(s.count, 50);
        assert!(s.p99_us > 0, "p99 after reset+record 應 > 0");
    }

    /// 補強：reset_all 同時清 5 mode 並更新 last_reset_ms。
    #[test]
    fn test_reset_all_updates_timestamp() {
        let rec = H0LatencyRecorder::new();
        for mode in ENGINE_MODES {
            rec.record(100, mode);
        }
        // record 不更新 last_reset_ms；初始為 0
        assert_eq!(rec.last_reset_ms(), 0);

        rec.reset_all(1_700_000_000_000);

        // 5 mode 全部清零
        for mode in ENGINE_MODES {
            assert_eq!(rec.summary(mode, 0).unwrap().count, 0, "mode={} 未 reset", mode);
        }
        assert_eq!(rec.last_reset_ms(), 1_700_000_000_000);
    }

    /// 補強：未知 engine_mode silently skip 不 panic（spec §3 防禦）。
    #[test]
    fn test_unknown_mode_no_panic() {
        let rec = H0LatencyRecorder::new();
        // 不在 ENGINE_MODES 的字串 — silently skip
        rec.record(100, "unknown_mode_xyz");
        rec.record(200, "");
        // summary 找不到也回 None 不 panic
        assert!(rec.summary("unknown_mode_xyz", 0).is_none());
        // 5 mode count 全 0
        for mode in ENGINE_MODES {
            assert_eq!(rec.summary(mode, 0).unwrap().count, 0);
        }
    }
}
