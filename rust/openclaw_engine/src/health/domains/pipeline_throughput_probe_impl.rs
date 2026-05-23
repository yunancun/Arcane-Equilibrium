//! Sprint 5+ Wave 1 Track B real probe — `PipelineThroughputSourceProbe` 實裝。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes.md §2.5
//!   + parent_wave_b_placeholder `main_health_emitters.rs` L146-166：把 Wave B
//!   placeholder 5 metric default 替換成 source 端 hot-path 累計值。
//!
//!   Source 端：
//!     - `ws_tick_rate_per_sec` / `ws_heartbeat_lag_ms`：`WsStats`
//!       （`crate::ws_client::stats::WsStats`） — dispatch.rs hot path 累計。
//!     - `ws_subscription_drift_count`：caller 注入 expected / actual closure；
//!       expected 由 SymbolRegistry / config snapshot 決定，actual 由 WsClient
//!       `subscriptions_count()` accessor。
//!     - `strategy_signal_rate_per_min`：`SignalStats`
//!       （`crate::tick_pipeline::signal_stats::SignalStats`） — step_3_signals.rs
//!       hot path 累計。
//!     - `ipc_roundtrip_ms_p99`：**Sprint 5++ carry-over**；本 IMPL 保留 OK band
//!       placeholder 1.0ms（per spec §2.5 + dispatch packet 禁忌「不 IMPL
//!       `current_ipc_roundtrip_ms_p99()` real」）。
//!
//! 主要類 / 函數:
//!   - `RealPipelineThroughputSource`：impl `PipelineThroughputSourceProbe`。
//!   - `last_sample_tick_count` / `last_sample_signal_count`：last delta sample 緩存
//!     `parking_lot::Mutex<(last_count, last_sample_ms)>`；emitter 30s tick 內鎖
//!     ~5us，不在 hot path。
//!
//! 依賴:
//!   - `crate::ws_client::stats::WsStats`
//!   - `crate::tick_pipeline::signal_stats::SignalStats`
//!   - `super::pipeline_throughput::PipelineThroughputSourceProbe`
//!   - `parking_lot::Mutex`（既有 dep；非 hot path 鎖）
//!   - `chrono::Utc`（既有 dep）
//!
//! 硬邊界:
//!   - F-2 NaN/inf sanitize：tick_rate / signal_rate 除法走 elapsed 守線；
//!     elapsed < 最低門檻時返 OK band placeholder（不 panic、不 emit NaN）。
//!   - 0 trading 路徑滲透：只讀 Arc<WsStats>/Arc<SignalStats> 不改任何 mut
//!     state 路徑。
//!   - hot path 影響：reader 端走 `Ordering::Relaxed` load，30s sample tick 內
//!     1-2 atomic load + ~5us Mutex 鎖；對應 spec AC-4 `hot_path_baseline` 不退。
//!   - `current_ipc_roundtrip_ms_p99()` 不 IMPL real（spec §2.5 + dispatch packet
//!     defer Sprint 5++）。

use std::sync::Arc;

use parking_lot::Mutex;

use crate::tick_pipeline::signal_stats::SignalStats;
use crate::ws_client::stats::WsStats;

use super::pipeline_throughput::PipelineThroughputSourceProbe;

/// 取當前 wall-clock unix epoch ms。
///
/// 為什麼集中於此：emitter test 可注入固定 ts；production 走 SystemTime UNIX_EPOCH。
fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// 至少需累積這麼長的 elapsed 才算出 tick rate；不足時返 OK band placeholder。
///
/// 為什麼 1.0 sec：tick_rate 以秒為單位；elapsed < 1s 樣本量太小（per spec §5
/// E2 重點審查 #1 「elapsed < 1.0 short-circuit」）。
const TICK_RATE_MIN_ELAPSED_MS: u64 = 1_000;

/// 至少需累積這麼長的 elapsed 才算出 signal rate；不足時返 OK band placeholder。
///
/// 為什麼 30 sec（= 0.5 min）：signal rate 以分為單位；< 0.5min 樣本量過低，
/// 易產生抖動誤觸 DEGRADED 染色（per spec §2.5 「too short interval → OK band」）。
const SIGNAL_RATE_MIN_ELAPSED_MS: u64 = 30_000;

/// `RealPipelineThroughputSource` — 5 metric 真實 wire-up。
///
/// 為什麼 expected / actual 兩 closure：spec §2.5 + §2.1 分工 — `expected` 由
/// SymbolRegistry / config 來源解析（25 sym × 4 channel = 100 expected topic 等
/// 隨業務變動），`actual` 由 WsClient subscriptions HashSet len() 提供。
/// 用 closure 解藕 emitter 與 source 兩端的 lifetime / Arc shape。
pub struct RealPipelineThroughputSource {
    ws_stats: Arc<WsStats>,
    signal_stats: Arc<SignalStats>,
    /// 預期 subscription topic 總數；caller 注入 closure（依 SymbolRegistry / config）。
    expected_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
    /// 實際 subscription topic 總數；caller 注入 closure（依 WsClient.subscriptions_count）。
    actual_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
    /// 上次 sample 的 (tick_count_snapshot, sample_wall_clock_ms)。
    last_sample_tick: Mutex<(u64, u64)>,
    /// 上次 sample 的 (signal_count_snapshot, sample_wall_clock_ms)。
    last_sample_signal: Mutex<(u64, u64)>,
}

impl RealPipelineThroughputSource {
    /// 建立 real probe；start_sample_ms 為 0 表 cold-start（首次 sample 走
    /// elapsed < min threshold 走 OK band 不誤升）。
    pub fn new(
        ws_stats: Arc<WsStats>,
        signal_stats: Arc<SignalStats>,
        expected_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
        actual_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
    ) -> Self {
        let now = now_ms();
        Self {
            ws_stats,
            signal_stats,
            expected_topic_count,
            actual_topic_count,
            last_sample_tick: Mutex::new((0, now)),
            last_sample_signal: Mutex::new((0, now)),
        }
    }

    /// test 注入用：with explicit init ts。
    #[cfg(test)]
    pub fn new_with_init_ts(
        ws_stats: Arc<WsStats>,
        signal_stats: Arc<SignalStats>,
        expected_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
        actual_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
        init_ts_ms: u64,
    ) -> Self {
        Self {
            ws_stats,
            signal_stats,
            expected_topic_count,
            actual_topic_count,
            last_sample_tick: Mutex::new((0, init_ts_ms)),
            last_sample_signal: Mutex::new((0, init_ts_ms)),
        }
    }

    /// test 接點：用 caller 提供 now_ms 計算 tick_rate（避 wall-clock 依賴）。
    #[cfg(test)]
    fn tick_rate_at(&self, now: u64) -> f64 {
        compute_tick_rate(&self.ws_stats, &self.last_sample_tick, now)
    }

    #[cfg(test)]
    fn signal_rate_at(&self, now: u64) -> f64 {
        compute_signal_rate(&self.signal_stats, &self.last_sample_signal, now)
    }

    #[cfg(test)]
    fn heartbeat_lag_at(&self, now: u64) -> u32 {
        compute_heartbeat_lag(&self.ws_stats, now)
    }
}

/// 算 tick rate（delta count / elapsed sec）；elapsed 太短 / cold-start 返 OK
/// band placeholder 2.0（per Wave B HIGH-1 fix 範式 — 嚴格 OK 不抖動）。
fn compute_tick_rate(ws_stats: &WsStats, last_sample: &Mutex<(u64, u64)>, now: u64) -> f64 {
    let total = ws_stats.total_tick_count();
    let mut g = last_sample.lock();
    let (last_count, last_ms) = *g;
    let elapsed_ms = now.saturating_sub(last_ms);
    if elapsed_ms < TICK_RATE_MIN_ELAPSED_MS {
        // sample interval 太短：返 OK band placeholder（不更新 last_sample 避
        // 累積太小區間造成 emitter 第一次正式 sample 出現假抖動）。
        return 2.0;
    }
    let delta = total.saturating_sub(last_count);
    *g = (total, now);
    let elapsed_sec = (elapsed_ms as f64) / 1000.0;
    if elapsed_sec <= 0.0 {
        // double-safety: elapsed_sec 不會 <= 0（前一道 elapsed_ms >= 1000 守過），
        // 但留兜底避免 div-by-zero NaN（per spec §5 E2 #1 + F-2 sanitize）。
        return 2.0;
    }
    let rate = (delta as f64) / elapsed_sec;
    if rate.is_finite() {
        rate
    } else {
        // F-2 sanitize：NaN/inf fail-soft 返 OK band placeholder（per `feedback_
        // no_dead_params` + spec §5 E2 #1 boundary 抖動避免）。
        2.0
    }
}

/// 算 signal rate per minute；同 compute_tick_rate 但以 60s 為單位 + min elapsed
/// 30s 守線（per Wave B HIGH-1 fix 1.0 OK band 對齊）。
fn compute_signal_rate(
    signal_stats: &SignalStats,
    last_sample: &Mutex<(u64, u64)>,
    now: u64,
) -> f64 {
    let total = signal_stats.signals_emitted_total();
    let mut g = last_sample.lock();
    let (last_count, last_ms) = *g;
    let elapsed_ms = now.saturating_sub(last_ms);
    if elapsed_ms < SIGNAL_RATE_MIN_ELAPSED_MS {
        return 1.0;
    }
    let delta = total.saturating_sub(last_count);
    *g = (total, now);
    let elapsed_min = (elapsed_ms as f64) / 60_000.0;
    if elapsed_min <= 0.0 {
        return 1.0;
    }
    let rate = (delta as f64) / elapsed_min;
    if rate.is_finite() {
        rate
    } else {
        1.0
    }
}

/// 算 heartbeat lag ms；cold-start (last_tick_ms == 0) 返 0 OK band；計算結果
/// cap 在 u32::MAX 避溢出。
fn compute_heartbeat_lag(ws_stats: &WsStats, now: u64) -> u32 {
    let last_tick_ms = ws_stats.last_tick_ms();
    if last_tick_ms == 0 {
        // cold-start: 從未收 tick；OK band 0 ms（per Wave B HIGH-1 fix 範式）。
        return 0;
    }
    // saturating_sub 防 clock skew 倒退；min u32::MAX 防 cap。
    now.saturating_sub(last_tick_ms).min(u32::MAX as u64) as u32
}

impl PipelineThroughputSourceProbe for RealPipelineThroughputSource {
    fn current_ws_tick_rate_per_sec(&self) -> f64 {
        compute_tick_rate(&self.ws_stats, &self.last_sample_tick, now_ms())
    }

    fn current_ws_heartbeat_lag_ms(&self) -> u32 {
        compute_heartbeat_lag(&self.ws_stats, now_ms())
    }

    fn current_ws_subscription_drift_count(&self) -> u32 {
        let expected = (self.expected_topic_count)();
        let actual = (self.actual_topic_count)();
        expected.abs_diff(actual)
    }

    fn current_strategy_signal_rate_per_min(&self) -> f64 {
        compute_signal_rate(&self.signal_stats, &self.last_sample_signal, now_ms())
    }

    fn current_ipc_roundtrip_ms_p99(&self) -> f64 {
        // Sprint 5++ carry-over：IPC stats infrastructure 獨立工作量（per spec
        // §2.5 + dispatch packet 禁忌「不 IMPL real」）。
        // OK band placeholder 對齊 Wave B HIGH-1 fix 1.0ms（< 5.0 嚴格 OK）。
        1.0
    }
}

// ============================================================
// Tests
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;
    use crate::health::domains::pipeline_throughput::{
        classify_pipeline_throughput_heartbeat_lag_ms,
        classify_pipeline_throughput_ipc_roundtrip_ms_p99,
        classify_pipeline_throughput_signal_rate,
        classify_pipeline_throughput_subscription_drift,
        classify_pipeline_throughput_ws_tick_rate,
    };
    use crate::health::HealthState;

    fn make_probe(
        expected: u32,
        actual: u32,
        init_ts_ms: u64,
    ) -> (Arc<WsStats>, Arc<SignalStats>, RealPipelineThroughputSource) {
        let ws = Arc::new(WsStats::new());
        let sig = Arc::new(SignalStats::new());
        let expected_closure: Arc<dyn Fn() -> u32 + Send + Sync> = Arc::new(move || expected);
        let actual_closure: Arc<dyn Fn() -> u32 + Send + Sync> = Arc::new(move || actual);
        let probe = RealPipelineThroughputSource::new_with_init_ts(
            Arc::clone(&ws),
            Arc::clone(&sig),
            expected_closure,
            actual_closure,
            init_ts_ms,
        );
        (ws, sig, probe)
    }

    /// 5-sym × 1 tick/sec × 5 sec = 25 tick / 5 sec = 5.0 tick/sec/aggregate；
    /// emitter 端不除以 sym 數（per spec §2.1 註解 "per second per symbol" 已平均
    /// — 由 spec 設計，本 probe 維持 aggregate rate 對齊 classify ladder）。
    #[test]
    fn test_tick_rate_basic_delta_computation() {
        let (ws, _sig, probe) = make_probe(100, 100, 0);
        // 5 sec 內累 25 tick → 5.0 tick/sec
        for i in 0..25 {
            ws.inc_tick(i * 200); // 任意 ts，inc_tick 內只 fetch_add
        }
        let rate = probe.tick_rate_at(5_000);
        // delta=25 / elapsed=5sec = 5.0
        assert!((rate - 5.0).abs() < 1e-9, "rate={}", rate);
        // classify 端應走 OK band（>= 1.0）
        assert_eq!(
            classify_pipeline_throughput_ws_tick_rate(rate),
            HealthState::HealthOk
        );
    }

    /// elapsed < 1 sec → OK band placeholder 2.0；cold-start window 不誤升。
    #[test]
    fn test_tick_rate_too_short_elapsed_returns_ok_placeholder() {
        let (ws, _sig, probe) = make_probe(0, 0, 0);
        for i in 0..1000 {
            ws.inc_tick(i);
        }
        // elapsed = 500ms < 1000ms 門檻
        let rate = probe.tick_rate_at(500);
        assert!((rate - 2.0).abs() < 1e-9, "cold-start placeholder; rate={}", rate);
        assert_eq!(
            classify_pipeline_throughput_ws_tick_rate(rate),
            HealthState::HealthOk
        );
    }

    /// 0 inc_tick + elapsed >= 1s → delta=0 → rate=0.0 → classify DEGRADED 發信。
    #[test]
    fn test_tick_rate_zero_delta_emits_degraded() {
        let (_ws, _sig, probe) = make_probe(0, 0, 0);
        // ws_stats 從未 inc_tick → tick_count=0
        let rate = probe.tick_rate_at(5_000);
        assert!(rate.abs() < 1e-9, "zero delta → 0 rate; got {}", rate);
        // classify: 0.0 < 0.5 → DEGRADED（per pipeline_throughput.rs:203 ladder）
        assert_eq!(
            classify_pipeline_throughput_ws_tick_rate(rate),
            HealthState::HealthDegraded
        );
    }

    /// heartbeat lag cold-start (last_tick_ms=0) → 0 OK band。
    #[test]
    fn test_heartbeat_lag_cold_start_returns_zero() {
        let (_ws, _sig, probe) = make_probe(0, 0, 0);
        let lag = probe.heartbeat_lag_at(60_000_000);
        assert_eq!(lag, 0, "cold-start 走 0 OK band placeholder");
        assert_eq!(
            classify_pipeline_throughput_heartbeat_lag_ms(lag),
            HealthState::HealthOk
        );
    }

    /// heartbeat lag real：last_tick=t0, now=t0+45s → lag=45000ms (WARN band)。
    #[test]
    fn test_heartbeat_lag_real_computes_correctly() {
        let (ws, _sig, probe) = make_probe(0, 0, 0);
        ws.inc_tick(1_700_000_000_000);
        let lag = probe.heartbeat_lag_at(1_700_000_045_000); // +45 sec
        assert_eq!(lag, 45_000);
        // 45000 ms 對應 WARN band（per pipeline_throughput.rs:237 ladder
        // 30000 < lag <= 60000 = WARN）
        assert_eq!(
            classify_pipeline_throughput_heartbeat_lag_ms(lag),
            HealthState::HealthWarn
        );
    }

    /// heartbeat lag overflow cap：last_tick=1, now=1+u32::MAX+1 不 panic 不 wrap。
    #[test]
    fn test_heartbeat_lag_saturates_at_u32_max() {
        let (ws, _sig, probe) = make_probe(0, 0, 0);
        ws.inc_tick(1);
        // now - last = u32::MAX + 100 > u32::MAX
        let now = 1u64 + u32::MAX as u64 + 100;
        let lag = probe.heartbeat_lag_at(now);
        assert_eq!(lag, u32::MAX, "overflow 必 cap u32::MAX 不 wrap");
    }

    /// subscription drift：expected=100 actual=95 → drift=5。
    #[test]
    fn test_subscription_drift_computes_abs_diff() {
        let (_ws, _sig, probe) = make_probe(100, 95, 0);
        let drift = probe.current_ws_subscription_drift_count();
        assert_eq!(drift, 5);
        // classify: 5 > 0 → DEGRADED（per pipeline_throughput.rs:264 ladder
        // = 0 OK / >0 DEGRADED）
        assert_eq!(
            classify_pipeline_throughput_subscription_drift(drift),
            HealthState::HealthDegraded
        );
    }

    /// subscription drift reversed：actual > expected 同樣 abs_diff（非負）。
    #[test]
    fn test_subscription_drift_reversed_actual_exceeds_expected() {
        let (_ws, _sig, probe) = make_probe(95, 100, 0);
        let drift = probe.current_ws_subscription_drift_count();
        assert_eq!(drift, 5);
    }

    /// signal rate basic：accumulate 60 signals over 60sec = 60/min。
    #[test]
    fn test_signal_rate_basic_delta_computation() {
        let (_ws, sig, probe) = make_probe(0, 0, 0);
        sig.inc_signal_batch(60, 60_000);
        let rate = probe.signal_rate_at(60_000); // elapsed = 60sec = 1min
        assert!((rate - 60.0).abs() < 1e-9, "rate={}", rate);
        assert_eq!(
            classify_pipeline_throughput_signal_rate(rate),
            HealthState::HealthOk
        );
    }

    /// signal rate too short elapsed → OK band placeholder 1.0。
    #[test]
    fn test_signal_rate_too_short_elapsed_returns_ok_placeholder() {
        let (_ws, sig, probe) = make_probe(0, 0, 0);
        sig.inc_signal_batch(1000, 10_000);
        // elapsed = 10sec < 30sec 門檻
        let rate = probe.signal_rate_at(10_000);
        assert!((rate - 1.0).abs() < 1e-9, "got {}", rate);
    }

    /// signal rate zero delta → 0 → classify DEGRADED（per pipeline_throughput.rs:293
    /// 0 < 0.1 → DEGRADED）。
    #[test]
    fn test_signal_rate_zero_delta_emits_degraded() {
        let (_ws, _sig, probe) = make_probe(0, 0, 0);
        // 不 inc_signal_batch，停 60 秒
        let rate = probe.signal_rate_at(60_000);
        assert!(rate.abs() < 1e-9);
        assert_eq!(
            classify_pipeline_throughput_signal_rate(rate),
            HealthState::HealthDegraded
        );
    }

    /// IPC roundtrip p99 走 Sprint 5++ placeholder 1.0；classify OK band 守線。
    #[test]
    fn test_ipc_p99_returns_placeholder_until_sprint_5pp() {
        let (_ws, _sig, probe) = make_probe(0, 0, 0);
        let p99 = probe.current_ipc_roundtrip_ms_p99();
        assert!((p99 - 1.0).abs() < 1e-9);
        assert_eq!(
            classify_pipeline_throughput_ipc_roundtrip_ms_p99(p99),
            HealthState::HealthOk
        );
    }

    /// 整合：5 metric snapshot 對齊 probe trait 5 method。
    #[test]
    fn test_trait_impl_invokes_all_5_accessors() {
        let (ws, sig, _) = make_probe(0, 0, 0);
        // 走 trait impl 路徑（非 test backdoor _at fn）
        let expected_closure: Arc<dyn Fn() -> u32 + Send + Sync> = Arc::new(|| 100);
        let actual_closure: Arc<dyn Fn() -> u32 + Send + Sync> = Arc::new(|| 100);
        let probe = RealPipelineThroughputSource::new(
            Arc::clone(&ws),
            Arc::clone(&sig),
            expected_closure,
            actual_closure,
        );

        // trait method 必 return finite f64 / u32 不 panic
        let tick = probe.current_ws_tick_rate_per_sec();
        let lag = probe.current_ws_heartbeat_lag_ms();
        let drift = probe.current_ws_subscription_drift_count();
        let sig_rate = probe.current_strategy_signal_rate_per_min();
        let p99 = probe.current_ipc_roundtrip_ms_p99();

        assert!(tick.is_finite(), "tick rate must be finite");
        assert!(sig_rate.is_finite(), "signal rate must be finite");
        assert!(p99.is_finite(), "ipc p99 must be finite");
        assert!(lag <= u32::MAX);
        assert_eq!(drift, 0); // expected == actual
    }
}
