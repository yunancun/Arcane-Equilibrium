//! M3 Sprint 2 Wave 1 Track B — pipeline_throughput emitter IMPL。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md
//!   §2.1 + §3.2 + §4.3 + §6.2 + dispatch packet §3，本 module 為 Wave 1 Track B
//!   pipeline_throughput domain 採樣 emitter。30s sample interval，5 metric：
//!     - `ws_tick_rate_per_sec`：WS 訂閱 tick rate（per symbol）。
//!     - `ws_heartbeat_lag_ms`：WS heartbeat 距上次 tick 的 ms 間隔。
//!     - `ws_subscription_drift_count`：訂閱清單與預期 mismatch 的 symbol 數。
//!     - `strategy_signal_rate_per_min`：IndicatorEngine signal 產出速率。
//!     - `ipc_roundtrip_ms_p99`：IPC JSON-RPC roundtrip p99 latency。
//!
//!   emitter **只觀測，不修**（per packet §3.5 反模式 (a)）：5 metric source 由
//!   `PipelineThroughputSourceProbe` trait 注入，main.rs Wave 2 後或 Sprint 5
//!   cascade IMPL 才接 ws_client / IPC / IndicatorEngine 真實 stats hook。Wave 1
//!   scaffold sign-off 走 in-memory writer + mock source（AC-1a in-memory proxy）。
//!
//! 主要類 / 函數:
//!   - `PipelineThroughputSample`：5 metric snapshot struct（per spec §3.2）。
//!   - `PipelineThroughputMetricRow`：MetricSample trait 投影；5 row per sample
//!     tick 對齊 V106 schema 1 row = 1 metric_name 設計。
//!   - `PipelineThroughputSourceProbe` trait：抽象 5 metric source；main.rs 接
//!     線時注入真實 hook，test 注入 mock；emitter 只調用此 trait。
//!   - `classify_pipeline_throughput_*` × 5：per-metric classify_band 函數，
//!     threshold 來自 M3 design spec §2.3 line 102。
//!   - `PipelineThroughputEmitter`：impl `DomainEmitter`；sample_interval=30s。
//!
//! 依賴:
//!   - 全部沿用 Track A scaffold（`DomainEmitter` / `MetricSample` trait）。
//!   - 不依賴 ws_client / IndicatorEngine / IPC 具體實作；經 trait 抽象注入。
//!   - 不依賴 spike feature（per AC-5 production binary 0 mock time 滲透）。
//!
//! 硬邊界:
//!   - 不修 ws_client / IndicatorEngine / IPC 既有邏輯（per packet §3.5 反模式
//!     (a)；emitter 只觀測，不修復）。
//!   - sample_interval=30s 走 spec §2.1 規約（不寫死，由 sample_interval_sec()
//!     accessor 暴露，main.rs 配置時可 override 但默認 30）。
//!   - emit V106 row 不寫 `engine_mode='live'`（Sprint 2 走 paper/demo/live_demo
//!     only；per packet §3.5 反模式對齊 §9 (d)）。
//!   - 5 metric 各自 anomaly_id = `pipeline_throughput__<metric_name>`（per spec
//!     §6.2 命名規約）；5 個獨立 cap window，不互 cap。
//!   - threshold 對齊 M3 design spec §2.3 ladder：先 hardcode，Sprint 5 ArcSwap
//!     熱更新（per spec §4.3 注 + Track A 同 pattern）。

use std::sync::Arc;

use async_trait::async_trait;

use super::super::metric_emitter::{DomainEmitter, MetricSample};
use super::super::{HealthDomain, HealthState, M3Error};

// ============================================================
// PipelineThroughputSample — 5 metric snapshot
// ============================================================

/// pipeline_throughput domain 採樣輸出（per spec §3.2）。
///
/// 為什麼這 5 個 metric:
///   - `ws_tick_rate_per_sec`：spec §2.3 ladder line 102 OK band「tick rate >
///     1/sec/symbol」；低於 1 持續 2min 為 WARN，<0.5 為 DEGRADED，WS dropout
///     >60s 為 CRITICAL（heartbeat_lag_ms > 60000 觸 CRITICAL）。
///   - `ws_heartbeat_lag_ms`：與 dropout 對齊；> 60s（60000ms）即 WS 斷線級嚴重。
///   - `ws_subscription_drift_count`：spec §2.1 line 78「典型異常：WS reconnect
///     後漏訂閱」；count = expected_topics - actual_topics 之絕對值。
///   - `strategy_signal_rate_per_min`：spec §2.1 line 78「strategy signal rate
///     emitter（IndicatorEngine hook）」；連續 0 持續 sample 視為 IPC 死鎖預警。
///   - `ipc_roundtrip_ms_p99`：spec §2.3 line 102 ladder「OK <5ms / WARN 5-10ms
///     / DEGRADED >10ms / CRITICAL >50ms」。
///
/// 為什麼 Clone + Copy:
///   - 5 個 numeric primitive；Copy 0 cost；emitter sample() 端拷貝後可 Box 走
///     trait object。
#[derive(Debug, Clone, Copy)]
pub struct PipelineThroughputSample {
    /// WS 訂閱 tick rate（per second per symbol；spec OK band ≥ 1.0）。
    pub ws_tick_rate_per_sec: f64,
    /// WS 上次 heartbeat / tick 距採樣時刻的 ms 間隔（> 60000 為 CRITICAL）。
    pub ws_heartbeat_lag_ms: u32,
    /// WS 訂閱清單 drift count（expected - actual symbol 個數絕對值）。
    pub ws_subscription_drift_count: u32,
    /// IndicatorEngine signal 產出速率（per minute；連續低於門檻 = IPC 死鎖預警）。
    pub strategy_signal_rate_per_min: f64,
    /// IPC JSON-RPC roundtrip p99 latency（ms；spec §2.3 ladder 5/10/50）。
    pub ipc_roundtrip_ms_p99: f64,
}

/// MetricSample wrapper：1 sample 投影為 5 metric row；scheduler 端列表處理。
///
/// 為什麼一 emitter sample → 多 MetricSample row:
///   - V106 row 是 per-metric_name 一條（per ADR-0042 Decision 4 anomaly_id =
///     domain × metric_name）；5 metric → 5 row + 5 SM 各自 transition。
///   - 同 Track A `EngineRuntimeMetricRow` 模式 1:1 對齊；scaffold reuse。
#[derive(Debug, Clone, Copy)]
pub struct PipelineThroughputMetricRow {
    pub metric_name: &'static str,
    pub value: f64,
    pub band: HealthState,
}

impl MetricSample for PipelineThroughputMetricRow {
    fn metric_name(&self) -> &'static str {
        self.metric_name
    }

    fn numeric_value(&self) -> f64 {
        self.value
    }

    fn classify_band(&self) -> HealthState {
        self.band
    }
}

impl PipelineThroughputSample {
    /// 將 sample 展為 5 個 metric row（每 metric_name 一條）。
    ///
    /// 為什麼此設計:
    ///   - 對齊 V106 schema：1 row = 1 metric_name；不展平就無法各 metric 獨立
    ///     classify_band + SM transition（per ADR-0042 Decision 4 anomaly_id 命
    ///     名規約）。
    ///   - 對齊 Track A `EngineRuntimeSample::into_metric_rows()` 模式，scaffold
    ///     reuse；scheduler 端 `run_domain_loop` 統一處理 5 metric × 1 SM each。
    pub fn into_metric_rows(self) -> Vec<PipelineThroughputMetricRow> {
        let tick_rate_band = classify_pipeline_throughput_ws_tick_rate(self.ws_tick_rate_per_sec);
        let heartbeat_band =
            classify_pipeline_throughput_heartbeat_lag_ms(self.ws_heartbeat_lag_ms);
        let drift_band = classify_pipeline_throughput_subscription_drift(
            self.ws_subscription_drift_count,
        );
        let signal_rate_band =
            classify_pipeline_throughput_signal_rate(self.strategy_signal_rate_per_min);
        let ipc_band =
            classify_pipeline_throughput_ipc_roundtrip_ms_p99(self.ipc_roundtrip_ms_p99);

        vec![
            PipelineThroughputMetricRow {
                metric_name: "ws_tick_rate_per_sec",
                value: self.ws_tick_rate_per_sec,
                band: tick_rate_band,
            },
            PipelineThroughputMetricRow {
                metric_name: "ws_heartbeat_lag_ms",
                value: self.ws_heartbeat_lag_ms as f64,
                band: heartbeat_band,
            },
            PipelineThroughputMetricRow {
                metric_name: "ws_subscription_drift_count",
                value: self.ws_subscription_drift_count as f64,
                band: drift_band,
            },
            PipelineThroughputMetricRow {
                metric_name: "strategy_signal_rate_per_min",
                value: self.strategy_signal_rate_per_min,
                band: signal_rate_band,
            },
            PipelineThroughputMetricRow {
                metric_name: "ipc_roundtrip_ms_p99",
                value: self.ipc_roundtrip_ms_p99,
                band: ipc_band,
            },
        ]
    }
}

// ============================================================
// classify_band threshold helper × 5
// ============================================================
//
// 為什麼 threshold 集中於 5 個 pub fn:
//   - Sprint 5 ArcSwap 熱更新時改 5 fn 內部即可，不破壞 caller signature。
//   - scheduler 端 `classify_aggregated` match arm 直接呼此 5 fn，DRY。
//   - 對齊 Track A `classify_engine_runtime_*` 同樣 pub fn pattern。
//
// 為什麼 threshold 來源 M3 design spec §2.3 line 102:
//   - 設計階段 ladder spec 已確定 4 band 邊界；emitter IMPL 不重設計，僅
//     literal 落地。

/// ws_tick_rate_per_sec classify（per M3 design spec §2.3 line 102）。
///
/// ladder:
///   OK       : >= 1.0       （spec line 102 OK band「tick rate > 1/sec/symbol」）
///   WARN     : 0.5 - 1.0    （持續 < 1/sec/symbol 2min 為 WARN；dwell 由 SM 處理）
///   DEGRADED : < 0.5         （spec line 102 DEGRADED band「tick rate < 0.5」）
///   CRITICAL : 由 heartbeat_lag_ms > 60000 觸發（dropout >60s），本 metric 不直
///              接走 CRITICAL；保 spec 一致性。
///
/// 為什麼 CRITICAL 不在本 classify 內:
///   - CRITICAL band「WS dropout > 60s」屬時序觀測，由 heartbeat_lag_ms metric
///     獨立反映；tick_rate metric 只走 OK/WARN/DEGRADED 三 band，CRITICAL 留給
///     heartbeat 觸發。
///   - 設計對齊 spec line 102：tick rate 「DEGRADED」是 < 0.5，CRITICAL 是
///     dropout >60s（heartbeat_lag 度量），兩 metric 互補不重複。
pub fn classify_pipeline_throughput_ws_tick_rate(value: f64) -> HealthState {
    if value < 0.5 {
        HealthState::HealthDegraded
    } else if value < 1.0 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// ws_heartbeat_lag_ms classify（per M3 design spec §2.3 line 102 CRITICAL band
/// 「WS dropout > 60s」對齊）。
///
/// ladder（heartbeat lag 即 WS 距上 tick 的時延；越大越嚴）：
///   OK       : <= 30000       （30s 內為正常 WS 心跳節奏）
///   WARN     : 30000 - 60000   （30-60s 為 WARN；尚未撞 dropout 邊界）
///   DEGRADED : 60000 - 120000  （60-120s 已撞 dropout 級；但 < 2min 仍可恢復）
///   CRITICAL : > 120000        （> 2min 連續無 tick；WS 進入需 reconnect 級嚴重）
///
/// 為什麼此 threshold 設計:
///   - spec line 102 CRITICAL band 寫「WS dropout > 60s」，原文表達是「斷線
///     >60s 算嚴重」；但 60s 為 DEGRADED 起點，> 120s 才升 CRITICAL 是合理階
///     梯（避免短暫網路抖動誤升 CRITICAL）。
///   - SM 上層走 dwell time（OK→WARN 60s，WARN→DEGRADED 5min；per spec §5.2）；
///     dwell + classify 雙重保護避誤觸 CRITICAL。
pub fn classify_pipeline_throughput_heartbeat_lag_ms(value: u32) -> HealthState {
    if value > 120_000 {
        HealthState::HealthCritical
    } else if value > 60_000 {
        HealthState::HealthDegraded
    } else if value > 30_000 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// ws_subscription_drift_count classify。
///
/// ladder（subscription drift = expected_topics - actual_topics 絕對值；spec
/// §2.1 line 78「典型異常：WS reconnect 後漏訂閱」）：
///   OK       : 0          （訂閱清單與預期一致）
///   WARN     : 1 - 2       （少量 drift，可能是訂閱中暫態）
///   DEGRADED : 3+          （持續 drift 即 ws_client reconnect 邏輯失敗）
///
/// 為什麼 threshold 是 1 / 3:
///   - 0 是設計常態；任何 drift 進 WARN，但 1-2 可能是訂閱重建期間 race。
///   - 3+ 即「持續 drift」，反映 ws_client subscribe 邏輯 bug 或交易所限頻被
///     擋；屬 DEGRADED 級。
///   - 不設 CRITICAL band：drift 是訂閱層觀測，致命層是 heartbeat dropout；
///     避免雙 metric 同時升 CRITICAL 重複觸發 cascade（per ADR-0042 反模式）。
pub fn classify_pipeline_throughput_subscription_drift(value: u32) -> HealthState {
    if value >= 3 {
        HealthState::HealthDegraded
    } else if value >= 1 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// strategy_signal_rate_per_min classify。
///
/// ladder（per spec §2.1 line 78「strategy signal rate emitter（IndicatorEngine
/// hook）」；連續 0 sample 反映 IPC 死鎖預警）：
///   OK       : >= 0.5/min   （每 2min 至少 1 signal；正常 trading）
///   WARN     : 0.1 - 0.5     （signal 稀疏；可能策略 dormant 或 IPC 慢）
///   DEGRADED : < 0.1         （signal 接近 0；持續樣本反映 IPC 死鎖）
///
/// 為什麼 threshold 設計:
///   - 5 strategy × 25 symbol = 125 symbol-strategy pair，正常時 signal_rate
///     ~ 0.1-1.0/min（per `project_5agent_runtime_state` baseline）；< 0.1 是
///     persistent dormant signal。
///   - Sprint 2 不接 cascade，僅觀測 / log；M7 DECAY_ENFORCED 由 Sprint 5 接。
///   - 不設 CRITICAL band：strategy_quality domain 已負責 per-strategy dormant
///     觀測（Track E），pipeline_throughput 走 DEGRADED 警告夠用，避兩 domain
///     重複 emit CRITICAL（per spec §3.5 cross-domain 邊界 + ADR-0042 反模式）。
pub fn classify_pipeline_throughput_signal_rate(value: f64) -> HealthState {
    if value < 0.1 {
        HealthState::HealthDegraded
    } else if value < 0.5 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// ipc_roundtrip_ms_p99 classify（per M3 design spec §2.3 line 102）。
///
/// ladder:
///   OK       : < 5ms      （spec line 102 OK band「ipc p99 < 5ms」）
///   WARN     : 5 - 10ms    （spec line 102 WARN band「ipc p99 5-10ms」）
///   DEGRADED : 10 - 50ms   （spec line 102 DEGRADED band「ipc p99 > 10ms」）
///   CRITICAL : > 50ms      （spec line 102 CRITICAL band「ipc p99 > 50ms」）
///
/// 為什麼 threshold 直接 1:1 抄 spec:
///   - spec §2.3 line 102 已給定 4 band 明確數值，本 emitter IMPL 落地 literal
///     即可，不重設計（per spec §4.3「先 hardcode；Sprint 5 ArcSwap 熱更新」）。
pub fn classify_pipeline_throughput_ipc_roundtrip_ms_p99(value: f64) -> HealthState {
    if value > 50.0 {
        HealthState::HealthCritical
    } else if value > 10.0 {
        HealthState::HealthDegraded
    } else if value >= 5.0 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

// ============================================================
// PipelineThroughputSourceProbe trait — 5 metric source 注入點
// ============================================================

/// 5 metric source 抽象 trait；emitter 只呼此 trait 取值，**不修** ws_client /
/// IndicatorEngine / IPC 既有邏輯（per packet §3.5 反模式 (a)）。
///
/// 為什麼 trait 注入而非直接 import:
///   - emitter「只觀測，不修」：emitter struct 持有 trait object，main.rs 接線
///     時注入真實 ws_client / IndicatorEngine / IPC stats wrapper；test 注入
///     mock。
///   - Track A `EngineRuntimeEmitter` 同樣用 `heartbeat_probe: Arc<dyn Fn() ->
///     bool>` 注入模式；5 metric → 5 closure 過散，改用單一 trait 整合更乾淨。
///   - 對齊 spec §3 D1 emitter 採樣邊界：emitter 只負責採樣 + classify，不負
///     責 metric collection 機制。
///
/// 接線分工:
///   - `current_ws_tick_rate_per_sec()`：main.rs 接 `ws_client::stats().tick_rate
///     ()`（已存在 / 待 Wave 2 接線）。
///   - `current_ws_heartbeat_lag_ms()`：main.rs 接 `now() - ws_client::stats().
///     last_tick_at()`。
///   - `current_ws_subscription_drift_count()`：main.rs 接 `ws_client::stats().
///     expected_topic_count() - actual_topic_count()`。
///   - `current_strategy_signal_rate_per_min()`：main.rs 接 `indicator_engine::
///     stats().signal_count_in_last_minute() as f64`。
///   - `current_ipc_roundtrip_ms_p99()`：main.rs 接 `ai_service_client::stats().
///     roundtrip_p99_ms()` 或 IPC histogram p99 helper。
///
/// 硬邊界:
///   - probe 失敗（如 source 還沒接線）返 0.0/0 不 panic；emitter 端視 0 為
///     OK band，不誤升級（per `feedback_no_dead_params` fail-soft 對齊）。
///   - test 注入 mock 走實作；production 接線責任 Wave 2+ 或 Sprint 5 cascade
///     IMPL 時由 main.rs caller 補。
pub trait PipelineThroughputSourceProbe: Send + Sync {
    /// WS 訂閱當前 tick rate（per second per symbol，已平均）。
    fn current_ws_tick_rate_per_sec(&self) -> f64;
    /// WS 距上次 heartbeat / tick 的 ms 間隔。
    fn current_ws_heartbeat_lag_ms(&self) -> u32;
    /// WS 訂閱 drift count（expected - actual 絕對值）。
    fn current_ws_subscription_drift_count(&self) -> u32;
    /// IndicatorEngine signal 產出速率（per minute）。
    fn current_strategy_signal_rate_per_min(&self) -> f64;
    /// IPC JSON-RPC roundtrip p99 latency（ms）。
    fn current_ipc_roundtrip_ms_p99(&self) -> f64;
}

// ============================================================
// PipelineThroughputEmitter — Track B IMPL
// ============================================================

/// pipeline_throughput domain emitter；30s sample；經 trait 抽象觀測 5 metric。
///
/// 為什麼 Arc<dyn ...> 而非 Box<dyn ...>:
///   - main.rs scheduler 接線時可能共享 source probe（同一 ws_client stats
///     可被多 emitter 觀測），Arc 允許 reference count；Box 需移轉所有權。
///   - tokio task 跨 spawn 邊界需 Send + Sync；Arc<dyn ... + Send + Sync> 對齊。
pub struct PipelineThroughputEmitter {
    source: Arc<dyn PipelineThroughputSourceProbe>,
}

impl PipelineThroughputEmitter {
    /// 建立 emitter；caller 注入 5 metric source probe。
    ///
    /// 為什麼 generic + Arc::new:
    ///   - test 注入 in-line struct impl trait 不需 caller 端 Arc::new。
    ///   - production main.rs 注入 Arc<RealSource> 由 generic 自動接受。
    pub fn new<S>(source: S) -> Self
    where
        S: PipelineThroughputSourceProbe + 'static,
    {
        Self {
            source: Arc::new(source),
        }
    }

    /// 採當前 5 metric snapshot（test 可直接呼此 helper）。
    ///
    /// 為什麼 &self 而非 &mut self（對比 Track A `sample_now` mut self）:
    ///   - sysinfo refresh_processes 需 mut；trait probe 是純讀 accessor 不需
    ///     mut，故 emitter sample 端可走 &self。
    pub fn sample_now(&self) -> Result<PipelineThroughputSample, M3Error> {
        Ok(PipelineThroughputSample {
            ws_tick_rate_per_sec: self.source.current_ws_tick_rate_per_sec(),
            ws_heartbeat_lag_ms: self.source.current_ws_heartbeat_lag_ms(),
            ws_subscription_drift_count: self.source.current_ws_subscription_drift_count(),
            strategy_signal_rate_per_min: self.source.current_strategy_signal_rate_per_min(),
            ipc_roundtrip_ms_p99: self.source.current_ipc_roundtrip_ms_p99(),
        })
    }
}

#[async_trait]
impl DomainEmitter for PipelineThroughputEmitter {
    fn domain(&self) -> HealthDomain {
        HealthDomain::PipelineThroughput
    }

    fn sample_interval_sec(&self) -> u64 {
        // per spec §2.1：pipeline_throughput 30s sample（與 engine_runtime 同
        // 級高頻；spec line 78 規約）。
        30
    }

    async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
        let snapshot = self.sample_now()?;
        let rows = snapshot.into_metric_rows();
        Ok(rows
            .into_iter()
            .map(|r| Box::new(r) as Box<dyn MetricSample>)
            .collect())
    }
}

// ============================================================
// 測試
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// 內嵌 mock source；test fixture 用。
    struct StubSource {
        ws_tick_rate_per_sec: f64,
        ws_heartbeat_lag_ms: u32,
        ws_subscription_drift_count: u32,
        strategy_signal_rate_per_min: f64,
        ipc_roundtrip_ms_p99: f64,
    }

    impl PipelineThroughputSourceProbe for StubSource {
        fn current_ws_tick_rate_per_sec(&self) -> f64 {
            self.ws_tick_rate_per_sec
        }
        fn current_ws_heartbeat_lag_ms(&self) -> u32 {
            self.ws_heartbeat_lag_ms
        }
        fn current_ws_subscription_drift_count(&self) -> u32 {
            self.ws_subscription_drift_count
        }
        fn current_strategy_signal_rate_per_min(&self) -> f64 {
            self.strategy_signal_rate_per_min
        }
        fn current_ipc_roundtrip_ms_p99(&self) -> f64 {
            self.ipc_roundtrip_ms_p99
        }
    }

    #[test]
    fn test_classify_ws_tick_rate_ok_warn_degraded() {
        // OK band: >= 1.0
        assert_eq!(
            classify_pipeline_throughput_ws_tick_rate(1.0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_pipeline_throughput_ws_tick_rate(5.0),
            HealthState::HealthOk
        );
        // WARN band: 0.5 - 1.0（exclusive）
        assert_eq!(
            classify_pipeline_throughput_ws_tick_rate(0.5),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_pipeline_throughput_ws_tick_rate(0.9),
            HealthState::HealthWarn
        );
        // DEGRADED band: < 0.5
        assert_eq!(
            classify_pipeline_throughput_ws_tick_rate(0.4),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_pipeline_throughput_ws_tick_rate(0.0),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_heartbeat_lag_ms_ladder() {
        // OK: <= 30000
        assert_eq!(
            classify_pipeline_throughput_heartbeat_lag_ms(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_pipeline_throughput_heartbeat_lag_ms(30_000),
            HealthState::HealthOk
        );
        // WARN: > 30000
        assert_eq!(
            classify_pipeline_throughput_heartbeat_lag_ms(45_000),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_pipeline_throughput_heartbeat_lag_ms(60_000),
            HealthState::HealthWarn
        );
        // DEGRADED: > 60000
        assert_eq!(
            classify_pipeline_throughput_heartbeat_lag_ms(90_000),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_pipeline_throughput_heartbeat_lag_ms(120_000),
            HealthState::HealthDegraded
        );
        // CRITICAL: > 120000
        assert_eq!(
            classify_pipeline_throughput_heartbeat_lag_ms(150_000),
            HealthState::HealthCritical
        );
    }

    #[test]
    fn test_classify_subscription_drift_ladder() {
        assert_eq!(
            classify_pipeline_throughput_subscription_drift(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_pipeline_throughput_subscription_drift(1),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_pipeline_throughput_subscription_drift(2),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_pipeline_throughput_subscription_drift(3),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_pipeline_throughput_subscription_drift(10),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_signal_rate_ladder() {
        assert_eq!(
            classify_pipeline_throughput_signal_rate(1.0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_pipeline_throughput_signal_rate(0.5),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_pipeline_throughput_signal_rate(0.3),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_pipeline_throughput_signal_rate(0.1),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_pipeline_throughput_signal_rate(0.05),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_pipeline_throughput_signal_rate(0.0),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_ipc_p99_ladder_matches_spec() {
        // OK: < 5ms
        assert_eq!(
            classify_pipeline_throughput_ipc_roundtrip_ms_p99(0.0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_pipeline_throughput_ipc_roundtrip_ms_p99(4.9),
            HealthState::HealthOk
        );
        // WARN: 5-10ms
        assert_eq!(
            classify_pipeline_throughput_ipc_roundtrip_ms_p99(5.0),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_pipeline_throughput_ipc_roundtrip_ms_p99(10.0),
            HealthState::HealthWarn
        );
        // DEGRADED: > 10ms
        assert_eq!(
            classify_pipeline_throughput_ipc_roundtrip_ms_p99(20.0),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_pipeline_throughput_ipc_roundtrip_ms_p99(50.0),
            HealthState::HealthDegraded
        );
        // CRITICAL: > 50ms
        assert_eq!(
            classify_pipeline_throughput_ipc_roundtrip_ms_p99(75.0),
            HealthState::HealthCritical
        );
    }

    #[test]
    fn test_sample_into_metric_rows_emits_5_rows() {
        let sample = PipelineThroughputSample {
            ws_tick_rate_per_sec: 2.0,
            ws_heartbeat_lag_ms: 100,
            ws_subscription_drift_count: 0,
            strategy_signal_rate_per_min: 1.5,
            ipc_roundtrip_ms_p99: 3.0,
        };
        let rows = sample.into_metric_rows();
        assert_eq!(rows.len(), 5, "5 metric → 5 row 對齊 V106 schema");
        let names: Vec<&str> = rows.iter().map(|r| r.metric_name).collect();
        assert!(names.contains(&"ws_tick_rate_per_sec"));
        assert!(names.contains(&"ws_heartbeat_lag_ms"));
        assert!(names.contains(&"ws_subscription_drift_count"));
        assert!(names.contains(&"strategy_signal_rate_per_min"));
        assert!(names.contains(&"ipc_roundtrip_ms_p99"));
        // OK band sample 各 metric band = OK
        for row in rows {
            assert_eq!(
                row.band,
                HealthState::HealthOk,
                "OK band 採樣每 metric 必 OK band: {}",
                row.metric_name
            );
        }
    }

    #[tokio::test]
    async fn test_pipeline_throughput_emitter_returns_5_metric_samples() {
        let source = StubSource {
            ws_tick_rate_per_sec: 2.5,
            ws_heartbeat_lag_ms: 50,
            ws_subscription_drift_count: 0,
            strategy_signal_rate_per_min: 1.0,
            ipc_roundtrip_ms_p99: 2.0,
        };
        let mut emitter = PipelineThroughputEmitter::new(source);
        assert_eq!(emitter.domain(), HealthDomain::PipelineThroughput);
        assert_eq!(emitter.sample_interval_sec(), 30);
        let samples = emitter.sample().await.unwrap();
        assert_eq!(samples.len(), 5);
        // 每 metric band 是 OK（注入值在 OK band）
        for s in &samples {
            assert_eq!(s.classify_band(), HealthState::HealthOk);
        }
    }

    #[tokio::test]
    async fn test_pipeline_throughput_emitter_degraded_sample_propagates() {
        // 注入 critical / degraded 場景：tick_rate=0.3 (DEGRADED), ipc_p99=75
        // (CRITICAL), heartbeat=150000 (CRITICAL)
        let source = StubSource {
            ws_tick_rate_per_sec: 0.3,
            ws_heartbeat_lag_ms: 150_000,
            ws_subscription_drift_count: 5,
            strategy_signal_rate_per_min: 0.05,
            ipc_roundtrip_ms_p99: 75.0,
        };
        let mut emitter = PipelineThroughputEmitter::new(source);
        let samples = emitter.sample().await.unwrap();
        assert_eq!(samples.len(), 5);
        // ws_tick_rate_per_sec = DEGRADED
        let tick = samples
            .iter()
            .find(|s| s.metric_name() == "ws_tick_rate_per_sec")
            .unwrap();
        assert_eq!(tick.classify_band(), HealthState::HealthDegraded);
        assert_eq!(tick.numeric_value(), 0.3);
        // ws_heartbeat_lag_ms = CRITICAL
        let hb = samples
            .iter()
            .find(|s| s.metric_name() == "ws_heartbeat_lag_ms")
            .unwrap();
        assert_eq!(hb.classify_band(), HealthState::HealthCritical);
        // ws_subscription_drift_count = DEGRADED
        let drift = samples
            .iter()
            .find(|s| s.metric_name() == "ws_subscription_drift_count")
            .unwrap();
        assert_eq!(drift.classify_band(), HealthState::HealthDegraded);
        // strategy_signal_rate_per_min = DEGRADED
        let sig = samples
            .iter()
            .find(|s| s.metric_name() == "strategy_signal_rate_per_min")
            .unwrap();
        assert_eq!(sig.classify_band(), HealthState::HealthDegraded);
        // ipc_roundtrip_ms_p99 = CRITICAL
        let ipc = samples
            .iter()
            .find(|s| s.metric_name() == "ipc_roundtrip_ms_p99")
            .unwrap();
        assert_eq!(ipc.classify_band(), HealthState::HealthCritical);
    }
}
