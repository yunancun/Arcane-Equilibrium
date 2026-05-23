//! M3 metric emitter scheduler wire-up — Sprint 4+ Wave B 接線。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per Sprint 2 PM Phase 3e §4.1 item 2 + Sprint 4+ first Live Wave B
//!   dispatch（2026-05-23）：把 Wave A 完成的 6 個 DomainEmitter +
//!   MetricEmitterScheduler 接到 main.rs runtime；構造 PgHealthObservationWriter
//!   + HealthEventBus + EngineModeProvider + 6 emitter 後 spawn 為 tokio task。
//!
//!   設計邊界（Wave B scope）:
//!     - Track A `EngineRuntimeEmitter`：sysinfo + 30s sample；真實 wire-up。
//!     - Track B `PipelineThroughputEmitter`：placeholder probe（5 metric
//!       default 走 spec line 102 OK band 合法值，避誤升 DEGRADED；Sprint 5+
//!       wire-up 接 ws_client / IndicatorEngine / IPC real metric；per round 2
//!       HIGH-1 fix 2026-05-23）。
//!     - Track C `DatabasePoolEmitter`：sqlx PgPool + writer queue probe 0 +
//!       disk usage 走 sysinfo Disks；Wave B 真實 pool stats wire-up。
//!     - Track D `ApiLatencyEmitter`：REST + WS production wire-up
//!       （per PA-DRIFT-4 Sprint 5+ §4.2.1 完成）。REST half 由 Wave B 拉
//!       `shared_client.latency_histogram_handle()` +
//!       `ret_code_counter_handle()`；WS half 由 Sprint 5+ §4.2.1 接 caller-
//!       injected Arc（`BybitPrivateWs::new()` signature 改造 + `PrivateWs
//!       Bindings` 暴露 `dropout_counter` / `rtt_histogram` field +
//!       `SharedClientsBundle.shared_ws_dropout` / `shared_ws_rtt` extract
//!       Live > Demo 優先級鏈）。任一 source None 走全 placeholder fallback
//!       （paper-only / cold-start no-binding）。
//!     - Track E `StrategyQualityEmitter`：Sprint 5+ §4.3.1 Phase A wire-up
//!       (本 module 同檔內)；`RealStrategyQualitySourceProbe` +
//!       `StrategyQualityMetricsCache` real PG batch query 接 trading.signals /
//!       trading.fills / learning.lease_transitions SSOT；獨立 scheduler 不沿用
//!       `MetricEmitterScheduler`（per spec §4.4 line 638-643）。
//!       Wire-up 入口 `spawn_strategy_quality_scheduler` +
//!       `spawn_strategy_quality_update_task` 由 main.rs caller Wave C 階段呼。
//!     - Track F `RiskEnvelopeEmitter`：`RealRiskEnvelopeSourceProbe` +
//!       `PortfolioStateCache` 真實 wire-up；update task 走 300s tick
//!       placeholder no-op（fail-soft caller end；Wave C / Sprint 5+ 接 PaperState
//!       SSOT）。
//!
//! 主要 fn:
//!   - `spawn_metric_emitter_scheduler`：one-shot wire-up entry；main.rs 在
//!     auto_migrate 後 + 三 pipeline spawn 後呼此 fn 一次。
//!   - `spawn_portfolio_state_update_task`：300s tick task；每 tick 呼
//!     `PortfolioStateCache::update_from_pipeline_snapshot`。
//!   - `spawn_strategy_quality_scheduler`：Sprint 5+ §4.3.1 Phase A Wave C；
//!     獨立 spawn StrategyQualityScheduler 為 tokio task；返 cache handle 讓
//!     caller 同時 spawn update task。
//!   - `spawn_strategy_quality_update_task`：5 min tick PG batch query；走 1 個
//!     CTE join query 拿 25 pair × 5 metric snapshot 整 HashMap 覆寫 cache。
//!
//! 依賴:
//!   - sqlx PgPool（main.rs Phase 1 line ~615 後可拿）
//!   - shared_client `Option<Arc<BybitRestClient>>`（main_instruments 後可拿）
//!   - 6 emitter struct + scheduler 既有 API
//!   - tokio_util::sync::CancellationToken
//!
//! 硬邊界:
//!   - 不修 既有 bybit_rest_client / bybit_private_ws 業務邏輯（per dispatch
//!     §禁忌 — Wave A 已完成 instrumentation；本 round 只接線）。
//!   - 不修 既有 risk_verdict_ledger / position_snapshot 寫入邏輯（只加
//!     PortfolioStateCache update task）。
//!   - 不引 V### / spike feature / 跨進程 IPC。
//!   - OBSERVE-4 replay engine_mode → scheduler.run startup Err 必 propagate
//!     （不 swallow）。
//!   - F-2 NaN/inf caller sanitize（per PA-DRIFT-5 round 2 升級 P1 Wave B
//!     condition）在 cache 端 `update_from_pipeline_snapshot` 已守。

use std::collections::HashMap;
use std::sync::Arc;

use parking_lot::Mutex as ParkingMutex;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

use openclaw_engine::bybit_private_ws::{WsDropoutCounter, WsRttHistogram};
use openclaw_engine::bybit_rest_client::{
    BybitRestClient, RestLatencyHistogram, RetCodeCounter,
};
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::database::pool_wait_stats::PoolWaitStats;
use openclaw_engine::database::writer_queue_stats::WriterQueueStats;
use openclaw_engine::health::domains::api_latency::ApiLatencyEmitter;
use openclaw_engine::health::domains::api_latency_probe_impl::RealApiLatencySourceProbe;
use openclaw_engine::health::domains::database_pool::{
    DatabasePoolEmitter, PoolWaitP95Probe, WriterQueueProbe,
};
use openclaw_engine::health::domains::database_pool_probe_impl::{
    build_pool_wait_p95_probe, build_writer_queue_probe,
};
use openclaw_engine::health::domains::pipeline_throughput::{
    PipelineThroughputEmitter, PipelineThroughputSourceProbe,
};
use openclaw_engine::health::domains::pipeline_throughput_probe_impl::RealPipelineThroughputSource;
use openclaw_engine::health::domains::risk_envelope::RiskEnvelopeEmitter;
use openclaw_engine::health::domains::risk_envelope_probe_impl::{
    PortfolioStateCache, PositionExposure, RealRiskEnvelopeSourceProbe,
};
use openclaw_engine::health::domains::strategy_quality::{
    StrategyQualityEmitter, StrategyQualityScheduler,
};
use openclaw_engine::health::domains::strategy_quality_probe_impl::{
    RealStrategyQualitySourceProbe, StrategyQualityMetricsCache,
    StrategyQualityMetricsSnapshot,
};
use openclaw_engine::tick_pipeline::signal_stats::SignalStats;
use openclaw_engine::ws_client::stats::WsStats;
use openclaw_engine::event_consumer::SYMBOLS;
use openclaw_engine::health::event_bus::HealthEventBus;
use openclaw_engine::health::metric_emitter::{
    DomainEmitter, EngineModeProvider, EngineRuntimeEmitter, MetricEmitterScheduler,
};
use openclaw_engine::health::writer::PgHealthObservationWriter;
use openclaw_engine::health::M3Error;

// ============================================================
// Placeholder probe — Track B PipelineThroughput
// ============================================================
//
// 為什麼 placeholder（per Wave B scope §1 item 2）:
//   - main.rs Wave B 接線時 ws_client::stats() / indicator_engine::stats() /
//     ai_service_client::stats() 等 source 端 accessor 未在 main.rs 外暴露 Arc
//     handle（多在 pipeline 內部）；本 round 不擴 accessor scope（避破
//     dispatch §禁忌「不改既有業務邏輯」）。
//   - Sprint 5+ wire-up 時 caller 替換為 real probe（per
//     `pipeline_throughput.rs` line 343-352 接線分工：ws_client.stats().
//     tick_rate() / heartbeat_lag / subscription_drift / IndicatorEngine
//     signal_rate / IPC roundtrip p99）；本 placeholder API 不變（impl trait
//     同一個 signature）。
//
// 為什麼 5 metric default 走 OK band 合法值 而非 0（per 2026-05-23 round 2
// HIGH-1 fix；原 round 1 全 0 走 DEGRADED 染色 bug）:
//   - spec line 102 OK band 明文：「tick rate > 1/sec/symbol + ipc p99 < 5ms +
//     ws_subscription_drift_count = 0 + strategy_signal_rate_per_min ≥ 0.5」。
//   - `classify_pipeline_throughput_ws_tick_rate` ladder（per
//     `pipeline_throughput.rs:203`）：`< 0.5 = DEGRADED`，`< 1.0 = WARN`，
//     `>= 1.0 = OK`；tick_rate=0.0 走 DEGRADED 而非 OK。
//   - `classify_pipeline_throughput_signal_rate` ladder（per
//     `pipeline_throughput.rs:293`）：`< 0.1 = DEGRADED`，`< 0.5 = WARN`，
//     `>= 0.5 = OK`；signal_rate=0.0 走 DEGRADED 而非 OK。
//   - 後果：round 1 IMPL 5 metric 全 0 → V106 row 30 天連續 DEGRADED 染色，
//     違反「placeholder 不誤升」設計意圖（per `feedback_no_dead_params`
//     fail-soft 對齊「未接線 source 不應假陽性 alarm」）。
//   - round 2 HIGH-1 fix：5 metric 改 OK band 合法值
//     - `tick_rate=2.0` （>1.0 嚴格 OK，留 1.0 緩衝避 boundary 抖動）
//     - `heartbeat_lag_ms=0` （<=30000 OK band；原 0 即合法）
//     - `subscription_drift_count=0` （=0 OK band；原 0 即合法）
//     - `signal_rate=1.0` （>=0.5 嚴格 OK，留 0.5 緩衝避 boundary 抖動）
//     - `ipc_roundtrip_ms_p99=1.0` （<5.0 嚴格 OK；spec line 102 OK band 對齊；
//       dispatch §HIGH-1 fix (a) 給的「10」實際走 DEGRADED ladder，本 round
//       採用嚴格 OK 值 1.0；rationale 留 doc 給 PM 與 E2 review）
//   - Sprint 5+ wire-up 替換為 real probe 反映真實 ws_client / IndicatorEngine
//     / IPC metric；本 placeholder 5 default value 在 real source 接入瞬間
//     被替換，不再參與 V106 emit chain。

/// Sprint 5+ §4.3.5 Track B real probe builder（per spec §2.6）。
///
/// 為什麼 Option 注入：
///   - 既有 caller（test / paper-only / cold-start no-binding）未必接 health pipeline；
///     任一 Arc None → fallback `PlaceholderPipelineThroughputSource`，0 行為退化。
///   - all-Some：5 metric 中 4 真實 + 1 placeholder（ipc_p99 延 Sprint 5++）；V106 row
///     真實升 alpha。
///
/// 為什麼三 source 同 None 走 placeholder fallback（per `feedback_no_dead_params`）：
///   - 半接通 mixed real/placeholder 會誤導 reviewer 認為「半連線是合法狀態」；
///     統一走 placeholder fallback 讓 V106 row 中性表態。
fn build_real_pipeline_throughput_probe(
    ws_stats: Arc<WsStats>,
    signal_stats: Arc<SignalStats>,
    expected_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
    actual_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
) -> RealPipelineThroughputSource {
    RealPipelineThroughputSource::new(ws_stats, signal_stats, expected_topic_count, actual_topic_count)
}

/// 構造 Track B `PipelineThroughputEmitter`：mandatory Arc 注入 real probe。
///
/// 為什麼 round 2 改 mandatory Arc（per spec §2.6 + Operator round 2 instruction）:
///   - round 1 走 `&Option<Arc<...>>` 容忍模式，導致 caller 端 main.rs 4 None
///     直接走全 placeholder fallback，V106 row 仍 100% placeholder（違 AC-3）。
///   - round 2 強制 caller wire-up：caller (spawn_metric_emitter_scheduler) 在
///     db_pool 不可用 / signal 端缺失時自行構造 `PlaceholderPipelineThroughput
///     Source` Box，emitter 端 signature 不再容納 None；type-level enforce 真接通。
///   - 對齊 spec §2.6 mandatory Arc + `feedback_no_dead_params` 反假陽性原則。
fn build_pipeline_throughput_emitter(
    ws_stats: Arc<WsStats>,
    signal_stats: Arc<SignalStats>,
    expected_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
    actual_topic_count: Arc<dyn Fn() -> u32 + Send + Sync>,
) -> Box<dyn DomainEmitter> {
    let probe = build_real_pipeline_throughput_probe(
        ws_stats,
        signal_stats,
        expected_topic_count,
        actual_topic_count,
    );
    Box::new(PipelineThroughputEmitter::new(probe))
}

/// caller 端 fallback：spawn_metric_emitter_scheduler 在 source 缺失時呼此 fn
/// 構造 placeholder emitter；保留 round 1 的 5 metric OK band 默認值（避誤升
/// DEGRADED），但**只在 caller 明確走 fallback 路徑時使用**。
fn build_pipeline_throughput_placeholder_emitter() -> Box<dyn DomainEmitter> {
    Box::new(PipelineThroughputEmitter::new(PlaceholderPipelineThroughputSource))
}

struct PlaceholderPipelineThroughputSource;

impl PipelineThroughputSourceProbe for PlaceholderPipelineThroughputSource {
    fn current_ws_tick_rate_per_sec(&self) -> f64 {
        // OK band 合法值（>1.0；spec line 102 OK band「tick rate > 1/sec/symbol」）。
        // Sprint 5+ wire-up 走 ws_client.stats().tick_rate()。
        2.0
    }
    fn current_ws_heartbeat_lag_ms(&self) -> u32 {
        // OK band 合法值（<=30000；spec line 102 OK band heartbeat 心跳節奏正常）。
        // Sprint 5+ wire-up 走 now() - ws_client.stats().last_tick_at()。
        0
    }
    fn current_ws_subscription_drift_count(&self) -> u32 {
        // OK band 合法值（=0；spec line 102 OK band「ws_subscription_drift_count
        // = 0」）。Sprint 5+ wire-up 走 ws_client.stats().expected_topic_count() -
        // actual_topic_count()。
        0
    }
    fn current_strategy_signal_rate_per_min(&self) -> f64 {
        // OK band 合法值（>=0.5；spec line 102 OK band「strategy_signal_rate_per
        // _min ≥ 0.5」）。Sprint 5+ wire-up 走 indicator_engine.stats().
        // signal_count_in_last_minute()。
        1.0
    }
    fn current_ipc_roundtrip_ms_p99(&self) -> f64 {
        // OK band 合法值（<5.0；spec line 102 OK band「ipc p99 < 5ms」）。
        // Sprint 5+ wire-up 走 ai_service_client.stats().roundtrip_p99_ms()
        // 或 IPC histogram p99 helper。
        1.0
    }
}

// ============================================================
// Track D — REST + WS production wire-up（Sprint 5+ §4.2.1 完成）
// ============================================================
//
// 為什麼 hybrid 已升級為 full production wire-up（per PA-DRIFT-4 Sprint 5+
// §4.2.1 spec §3.4）:
//   - REST half real wire-up 由 Wave B 完成：`shared_client.latency_histogram_
//     handle()` + `ret_code_counter_handle()` 由 BybitRestClient 直接 expose
//     Arc（main_instruments 後可拿）。
//   - WS half production wire-up 由 Sprint 5+ §4.2.1 完成：BybitPrivateWs::
//     new() signature 改為 caller external Arc 注入；`startup/private_ws.rs`
//     supervisor 在 spawn 前構造 Arc 後跨 attempt 共享同 instance，並透過
//     `PrivateWsBindings` 返 caller；main_instruments 端走 Live > Demo 優先級
//     extract `shared_ws_dropout` + `shared_ws_rtt`，透傳本 fn 注入 probe。
//
// 為什麼選 Option A caller-injected Arc 而非 Option B install_external_
// handles() 兩步式（per spec §2.1 對照）:
//   - type-level enforcement：BybitPrivateWs::new() 新增 2 個 Arc 參數，caller
//     必傳；compile 強制無「忘 install」回退半實裝陷阱可能。
//   - 0 race window：supervisor 構造瞬間即接通 production probe；不存在 install
//     前 default Arc 接 measurement 又被 swap 丟失 risk。
//   - 對齊既有 SharedClientsBundle 從 binding extract shared Arc 的 pattern
//     （main_instruments.rs:70-81）— 子模塊純消費，main.rs 編排。
//
// fallback path（shared_ws_dropout / shared_ws_rtt 任一 None）:
//   - paper-only / cold-start no-binding 啟動時 PrivateWsBindings 不存在；
//     shared_ws_dropout / shared_ws_rtt 為 None。
//   - 此時 build_api_latency_emitter 走全 placeholder fallback（4 個 fresh
//     0-state Arc）；V106 row 仍 emit（不缺 row）但內容為 placeholder。
//   - 進入 production binding（live / demo）後 shared Arc 接通，V106 row 自動
//     反映 production WS metric；不需 restart emitter scheduler。

/// 構造 Track D `RealApiLatencySourceProbe`：REST + WS production wire-up。
///
/// PA-DRIFT-4 Sprint 5+ §4.2.1：WS half 接 caller-injected Arc（取代 Wave B
/// fresh 0-state placeholder）。
///
/// caller 端責任（main.rs）：從 `SharedClientsBundle.shared_ws_dropout` /
/// `shared_ws_rtt` 拿 Arc 透傳；本 fn 內走 `Arc::clone` 共享同 instance。
fn build_real_api_latency_probe(
    shared_client: &Arc<BybitRestClient>,
    shared_ws_dropout: &Arc<WsDropoutCounter>,
    shared_ws_rtt: &Arc<WsRttHistogram>,
) -> RealApiLatencySourceProbe {
    let rest_latency: Arc<RestLatencyHistogram> = shared_client.latency_histogram_handle();
    let ret_code_counter: Arc<RetCodeCounter> = shared_client.ret_code_counter_handle();
    // PA-DRIFT-4 Sprint 5+ §4.2.1：caller-injected production WS Arc clone
    // （取代 Wave B `Arc::new(WsDropoutCounter::new())` placeholder）。
    let ws_dropout: Arc<WsDropoutCounter> = Arc::clone(shared_ws_dropout);
    let ws_rtt: Arc<WsRttHistogram> = Arc::clone(shared_ws_rtt);
    RealApiLatencySourceProbe::new(rest_latency, ret_code_counter, ws_dropout, ws_rtt)
}

/// 構造 Track D `ApiLatencyEmitter`：三 source 任一缺席走全 placeholder。
///
/// 為什麼 partial-Some 也走全 placeholder fallback（per spec §3.4 改動 2
/// rationale）:
///   - 三 source `shared_client` / `shared_ws_dropout` / `shared_ws_rtt` 需
///     同時存在才能 emit production-aligned 4 metric；任一 None = pipeline
///     binding 半接通狀態。
///   - partial-Some 走 mixed real/placeholder 會誤導 reviewer 認為「半連線」
///     是合法狀態（per `feedback_no_dead_params` 反假陽性）；統一走全
///     placeholder fallback 讓 V106 row 中性表態（不誤升、不誤稱真接通）。
///   - 三 source 同源（main_instruments live > demo 優先級鏈），實務上要嘛
///     all-Some 要嘛 all-None；partial 是極端冷啟動 race window 才可能撞。
fn build_api_latency_emitter(
    shared_client: &Option<Arc<BybitRestClient>>,
    shared_ws_dropout: &Option<Arc<WsDropoutCounter>>,
    shared_ws_rtt: &Option<Arc<WsRttHistogram>>,
) -> Box<dyn DomainEmitter> {
    match (shared_client, shared_ws_dropout, shared_ws_rtt) {
        (Some(client), Some(dropout), Some(rtt)) => {
            let probe = build_real_api_latency_probe(client, dropout, rtt);
            Box::new(ApiLatencyEmitter::new(probe))
        }
        _ => {
            // 全 placeholder fallback：任一 None 走 4 個 0-state Arc。
            // V106 row 仍 emit 但 OK band；paper-only / cold-start no-binding。
            let probe = RealApiLatencySourceProbe::new(
                Arc::new(RestLatencyHistogram::new()),
                Arc::new(RetCodeCounter::new()),
                Arc::new(WsDropoutCounter::new()),
                Arc::new(WsRttHistogram::new()),
            );
            Box::new(ApiLatencyEmitter::new(probe))
        }
    }
}

// ============================================================
// Track A engine_runtime heartbeat probe
// ============================================================
//
// 為什麼 placeholder true（per Wave B scope §1 item 1）:
//   - Track A heartbeat_probe 接 IPC heartbeat watcher 是 Sprint 5+ cascade 工作
//     （per spec §3 IPC heartbeat 邊界）；本 Wave B 走「process alive == true」
//     fallback：當前進程在執行 = heartbeat live。
//   - 不寫死 true 隱式 fail-loud：process 本身 dead = engine restart loop（per
//     既有 watchdog mechanism）；本 emitter 觀測層不獨立檢 heartbeat dead。
//   - Sprint 5+ wire-up 時 caller 替換為真實 ipc_heartbeat_check() closure。

fn build_engine_runtime_emitter() -> Box<dyn DomainEmitter> {
    // 為什麼 std::process::id()：emitter 觀測「當前 engine 進程」；對齊
    // `EngineRuntimeEmitter::new(pid, heartbeat_probe)` 文檔 D1。
    let pid = std::process::id();
    let heartbeat_probe = || true; // Wave B placeholder（per module note）
    Box::new(EngineRuntimeEmitter::new(pid, heartbeat_probe))
}

// ============================================================
// Track C database_pool emitter — sqlx Pool + sysinfo Disks
// ============================================================
//
// 為什麼 writer_queue / pool_wait_p95 走 placeholder closure（per Track C
// MODULE_NOTE line 44-58「未接 source 時 caller 必傳 placeholder」設計）:
//   - writer_queue source 端是 task-local Vec buffer（market_writer.rs 等），
//     跨 task 觀測需新增 Arc<AtomicUsize> hook；本 Wave B 不擴 writer 邏輯
//     scope（per dispatch §禁忌「不改既有業務邏輯」）。
//   - pool_wait_p95 source 端是 sqlx 內部 metric；sqlx 0.8 未暴露 hot path
//     histogram accessor；本 Wave B placeholder closure 返 0；Sprint 5+ wire-up
//     時 caller 替換為 real probe。
//   - 兩者全返 0 → emitter classify 走 OK band，不誤升 WARN/DEGRADED。

/// Sprint 5+ §4.3.6 Track C real probe builder（per spec §3.5）。
///
/// 為什麼 round 2 改 mandatory Arc（per spec §3.5 + Operator round 2 instruction）:
///   - round 1 走 `&Option<Arc<...>>` 容忍模式，導致 caller 端 main.rs 2 None
///     直接走 0u32 closure fallback，V106 writer_queue / pool_wait p95 row 仍
///     100% placeholder。
///   - round 2 強制 caller wire-up：caller 在 DB 不可用時自行構造 0u32 closure
///     fallback；emitter 端 signature 不再容納 None。
///   - 對齊 spec §3.5 mandatory Arc + `feedback_no_dead_params` 反假陽性原則。
fn build_database_pool_emitter(
    db_pool: &Arc<DbPool>,
    pool_max_conn: u32,
    data_dir_mount: &str,
    writer_queue_stats: Arc<WriterQueueStats>,
    pool_wait_stats: Arc<PoolWaitStats>,
) -> Box<dyn DomainEmitter> {
    let writer_queue_probe: WriterQueueProbe = build_writer_queue_probe(writer_queue_stats);
    let pool_wait_p95_probe: PoolWaitP95Probe = build_pool_wait_p95_probe(pool_wait_stats);
    Box::new(DatabasePoolEmitter::new(
        Arc::clone(db_pool),
        pool_max_conn,
        data_dir_mount.to_string(),
        writer_queue_probe,
        pool_wait_p95_probe,
    ))
}

/// caller 端 fallback：在 DB 不可用 / source Arc 缺失時走 0u32 closure
/// placeholder（既有 Wave B 範式）；只在 caller 明確走 fallback 路徑時使用。
fn build_database_pool_placeholder_emitter(
    db_pool: &Arc<DbPool>,
    pool_max_conn: u32,
    data_dir_mount: &str,
) -> Box<dyn DomainEmitter> {
    let writer_queue_probe: WriterQueueProbe = Arc::new(|| 0u32);
    let pool_wait_p95_probe: PoolWaitP95Probe = Arc::new(|| 0u32);
    Box::new(DatabasePoolEmitter::new(
        Arc::clone(db_pool),
        pool_max_conn,
        data_dir_mount.to_string(),
        writer_queue_probe,
        pool_wait_p95_probe,
    ))
}

// ============================================================
// Track F risk_envelope emitter — RealRiskEnvelopeSourceProbe
// ============================================================
//
// 為什麼共享 PortfolioStateCache 而非 per-mode 獨立（per PA-DRIFT-5 round 1
// report §4.3 carry-over #3 PM 拍板待定，本 Wave B 採「engine-wide single
// cache」）：
//   - 既有 risk_verdict_ledger / position_snapshot SSOT calculator 是 per-engine
//     (live/demo/paper) 獨立；但 emitter 端 metric_name `risk_envelope__*` 共
//     用 anomaly_id space（per spec §6.2 命名規約）。
//   - Wave B 採單一 cache：避 emitter 多 instance 重複 spawn / V106 row 重複；
//     per `feedback_env_config_independence` 三環境 risk_config 獨立原則由
//     caller 端 update task 注入合適來源解析（live/demo/paper merge to single
//     emitter view）。
//   - Sprint 5+ wire-up 階段若 PM 拍板獨立 cache，本 fn 構造可加 mode 參數，
//     並各自 spawn update task；本 round 不擴 scope。

/// 構造 Track F `RiskEnvelopeEmitter` + 共享 `PortfolioStateCache` Arc 句柄。
///
/// 返 (emitter, cache_handle)：caller 在 spawn scheduler 同時 spawn update task，
/// 兩者共享同 cache Arc。
fn build_risk_envelope_emitter() -> (
    Box<dyn DomainEmitter>,
    Arc<ParkingMutex<PortfolioStateCache>>,
) {
    let cache = Arc::new(ParkingMutex::new(PortfolioStateCache::new()));
    let probe = RealRiskEnvelopeSourceProbe::new(Arc::clone(&cache));
    let emitter = RiskEnvelopeEmitter::new(probe);
    (Box::new(emitter), cache)
}

// ============================================================
// 6 emitter 構造 + scheduler spawn
// ============================================================

/// Wave B one-shot wire-up entry：構造 6 emitter + scheduler + spawn 為 tokio
/// task；同時 spawn PortfolioStateCache 300s update tick task。
///
/// 為什麼 one-shot entry：
///   - main.rs caller 在 db_pool ready 後（line ~616）+ 三 pipeline spawn 後
///     呼此 fn 一次；wire-up 邏輯不散到 main.rs 多處。
///   - 對齊既有 main_pipelines / main_boot_tasks / main_fanout 抽 fn 範式
///     （main.rs 專注頂層編排）。
///
/// 為什麼 Track B/E 走 placeholder/skip：
///   - Track B PipelineThroughput：source 端（ws_client/IndicatorEngine/IPC
///     stats）accessor 未在 main.rs 外暴露 Arc handle（多在 pipeline 內部）；
///     Wave B 不擴 accessor scope。
///   - Track E StrategyQualityScheduler 是獨立 scheduler（不沿用
///     MetricEmitterScheduler）；wire-up 25 sym × 5 strategy probe 設計獨立，
///     由 Sprint 5+ wire-up（per dispatch §NOT in scope）。
///
/// 為什麼 OBSERVE-4 propagate Err 不 swallow：
///   - per spec line 199-216 OBSERVE-4 設計合約：replay engine_mode 啟動撞
///     scheduler.run 必 fail-loud Err；caller 端見 Err 應立即看到設計違反，
///     不 silently swallow。
///   - 本 fn 走 `tokio::spawn` 後 handle.await 不 await（emitter 是長 running
///     task）；scheduler.run startup Err 在 tokio task 內 log + 立即 break。
///   - replay engine_mode 由 engine bootstrap line 211-216 已 short-circuit
///     `run_replay_mode + return`；本 fn 接到時必為非 replay 4 值（caller 端
///     責任）。
#[allow(clippy::too_many_arguments)]
pub(crate) fn spawn_metric_emitter_scheduler(
    db_pool: &Arc<DbPool>,
    pool_max_conn: u32,
    data_dir_mount: &str,
    shared_client: &Option<Arc<BybitRestClient>>,
    // PA-DRIFT-4 Sprint 5+ §4.2.1：WS supervisor instrumentation Arc 注入。
    // caller 端 main.rs 從 SharedClientsBundle 透傳 Live > Demo 優先級提取
    // 的 Arc；本 fn 走 build_api_latency_emitter match arm 構造 production-
    // aligned probe（取代 Wave B fresh 0-state placeholder）。
    shared_ws_dropout: &Option<Arc<WsDropoutCounter>>,
    shared_ws_rtt: &Option<Arc<WsRttHistogram>>,
    // Sprint 5+ §4.3.5 Track B real probe — ws_client hot-path 統計與 strategy
    // signal 累計。caller 端 main.rs 在 ws_client.attach_ws_stats() +
    // pipeline.set_signal_stats() 後透傳同 Arc。任一 None → placeholder fallback。
    ws_stats: &Option<Arc<WsStats>>,
    signal_stats: &Option<Arc<SignalStats>>,
    expected_topic_count: Option<Arc<dyn Fn() -> u32 + Send + Sync>>,
    actual_topic_count: Option<Arc<dyn Fn() -> u32 + Send + Sync>>,
    // Sprint 5+ §4.3.6 Track C real probe — writer queue depth + pool wait p95。
    // caller 端 main.rs 在 tasks.rs market_tx 包 Arc + WriterQueueStats / Pool
    // WaitStats ctor 後透傳同 Arc。任一 None → placeholder fallback。
    writer_queue_stats: &Option<Arc<WriterQueueStats>>,
    pool_wait_stats: &Option<Arc<PoolWaitStats>>,
    engine_mode_str: &'static str,
    cancel: &CancellationToken,
) -> (
    Arc<ParkingMutex<PortfolioStateCache>>,
    Arc<HealthEventBus>,
) {
    // Step 1: PgHealthObservationWriter 包 sqlx PgPool。
    let pg_pool = match db_pool.get() {
        Some(p) => p.clone(),
        None => {
            warn!(
                target = "m3.health.wireup",
                "M3 metric emitter wire-up skipped: DbPool disconnected at boot \
                 (PG unreachable). V106 emit chain disabled until db restored."
            );
            // 返回空 cache + event_bus 維持 API 不變；caller 端 wire-up 仍 land。
            return (
                Arc::new(ParkingMutex::new(PortfolioStateCache::new())),
                Arc::new(HealthEventBus::new()),
            );
        }
    };
    let writer = Arc::new(PgHealthObservationWriter::new(pg_pool));

    // Step 2: HealthEventBus（Sprint 5 cascade subscribe 預埋；本 round 不接
    // subscriber）。
    let event_bus = Arc::new(HealthEventBus::new());

    // Step 3: EngineModeProvider closure。
    //
    // 為什麼 `&'static str` 參數而非 Arc<...> dynamic provider：
    //   - main.rs 啟動瞬間 engine_mode 由 effective_engine_mode(kind, env) 決定；
    //     runtime 切換需重新 spawn scheduler（不在本 Wave B scope；Sprint 5+
    //     amend follow-up）。
    //   - 對齊 既有 `effective_engine_mode` 返 `&'static str` 4 值 white-list。
    let mode_str = engine_mode_str.to_string();
    let engine_mode: EngineModeProvider = Arc::new(move || mode_str.clone());

    // Step 4: 構造 6 emitter（A real / B real (Sprint 5+ §4.3.5 round 2 caller
    // wire-up 完成 — 4/5 metric real + ipc_p99 placeholder) / C real (Sprint 5+
    // §4.3.6 round 2 caller wire-up 完成) / D real (Sprint 5+ §4.2.1) / E skip
    // / F real）。
    let engine_runtime = build_engine_runtime_emitter();

    // Sprint 5+ §4.3.5 Track B round 2 caller wire-up：mandatory Arc 注入。
    // 任一 source None 走 caller-side placeholder fallback（per spec §2.6 +
    // Operator round 2 instruction 「emitter signature 不再容納 None；fallback
    // 由 caller 構造」）。
    let pipeline_throughput: Box<dyn DomainEmitter> = match (
        ws_stats,
        signal_stats,
        expected_topic_count,
        actual_topic_count,
    ) {
        (Some(ws), Some(sig), Some(exp), Some(act)) => build_pipeline_throughput_emitter(
            Arc::clone(ws),
            Arc::clone(sig),
            exp.clone(),
            act.clone(),
        ),
        _ => {
            warn!(
                target = "m3.health.wireup",
                "M3 PipelineThroughput Track B caller wire-up incomplete: \
                 source Arc 缺失 → 走 PlaceholderPipelineThroughputSource fallback \
                 (5 metric OK band default)"
            );
            build_pipeline_throughput_placeholder_emitter()
        }
    };

    // Sprint 5+ §4.3.6 Track C round 2 caller wire-up：mandatory Arc 注入。
    // 兩 source 任一 None 走 caller-side 0u32 closure placeholder（既有 Wave B
    // 範式）。spawn_db_writers 在 DB 不可用時返 None None，此處走 fallback。
    let database_pool: Box<dyn DomainEmitter> = match (writer_queue_stats, pool_wait_stats) {
        (Some(wq), Some(pw)) => build_database_pool_emitter(
            db_pool,
            pool_max_conn,
            data_dir_mount,
            Arc::clone(wq),
            Arc::clone(pw),
        ),
        _ => {
            warn!(
                target = "m3.health.wireup",
                "M3 DatabasePool Track C caller wire-up incomplete: \
                 WriterQueueStats / PoolWaitStats Arc 缺失 → 走 0u32 placeholder \
                 closure fallback（既有 Wave B 範式）"
            );
            build_database_pool_placeholder_emitter(db_pool, pool_max_conn, data_dir_mount)
        }
    };
    // PA-DRIFT-4 Sprint 5+ §4.2.1：transmit ws Arc through to api_latency
    // emitter；三 source 同 None 走 placeholder fallback（paper-only / cold-
    // start no-binding）。
    let api_latency =
        build_api_latency_emitter(shared_client, shared_ws_dropout, shared_ws_rtt);
    // Track E skip per dispatch §NOT in scope。
    let (risk_envelope, portfolio_cache) = build_risk_envelope_emitter();

    let emitters: Vec<Box<dyn DomainEmitter>> = vec![
        engine_runtime,
        pipeline_throughput,
        database_pool,
        api_latency,
        risk_envelope,
    ];

    // Step 5: 建立 scheduler 後 spawn tokio task。
    // 為什麼 emitter_count 動態計算（per round 2 LOW-2 fix；原 round 1 hardcoded
    // = 5，Sprint 5+ Track E wire-up 後會 drift）:
    //   - emitters vec 構造後 length = 當前實際 spawn emitter 數；Sprint 5+ Track
    //     E StrategyQualityEmitter wire-up 後 vec.push 自動反映。
    //   - 對齊 §九 反模式「assert/log 數值 hardcoded 會 drift」。
    let emitter_count_for_log = emitters.len();
    let scheduler =
        MetricEmitterScheduler::new(emitters, writer, Arc::clone(&event_bus), engine_mode);
    let scheduler_cancel = cancel.clone();
    let mode_for_log = engine_mode_str.to_string();
    tokio::spawn(async move {
        info!(
            target = "m3.health.wireup",
            engine_mode = %mode_for_log,
            emitter_count = emitter_count_for_log,
            "M3 MetricEmitterScheduler spawning (Track A real + B placeholder + C real \
             + D real (REST + WS production wire-up per Sprint 5+ §4.2.1) + F real; \
             Track E independent scheduler wire-up via spawn_strategy_quality_scheduler)"
        );
        match scheduler.run(scheduler_cancel).await {
            Ok(()) => {
                info!(
                    target = "m3.health.wireup",
                    "M3 MetricEmitterScheduler graceful shutdown"
                );
            }
            Err(M3Error::ReplaySubprocessForbidden) => {
                // OBSERVE-4 fail-loud：replay engine_mode 撞 scheduler startup
                // guard；caller bootstrap 端 line 211-216 已防 replay 路徑進
                // async_main，本分支只發生在 caller 設計違反。tracing::error
                // 留 audit trail；scheduler task 自然結束，不 panic（避破
                // engine main loop）。
                tracing::error!(
                    target = "m3.health.wireup",
                    "M3 MetricEmitterScheduler OBSERVE-4 guard tripped — \
                     engine_mode='replay' forbidden by V106 CHECK (spec line 199-216). \
                     This is a wire-up bug; caller must ensure replay subprocess does \
                     not spawn metric scheduler."
                );
            }
            Err(e) => {
                tracing::error!(
                    target = "m3.health.wireup",
                    error = %e,
                    "M3 MetricEmitterScheduler unexpected error"
                );
            }
        }
    });

    (portfolio_cache, event_bus)
}

// ============================================================
// PortfolioStateCache 300s update task
// ============================================================

/// spawn PortfolioStateCache update task (300s tick；對齊 risk_envelope emitter
/// sample_interval_sec=300)。
///
/// 為什麼 placeholder no-op tick 設計（per Wave B scope §2）:
///   - 操作員指示「接 既有 risk_verdict_ledger + position_snapshot + fill_writer
///     event stream」；但既有 SSOT 不暴露 main.rs 級 Arc handle（per
///     dispatch §禁忌「不改既有寫入邏輯」）：
///       - PaperState 在每 pipeline 內部 own；main.rs 外無共享 Arc。
///       - trading_tx `mpsc::Sender<TradingMsg>` 走 trading_writer → DB；無旁路
///         subscribe channel。
///       - positions_mirror 只暴露 `HashMap<symbol, is_long>`，不含 qty /
///         entry_price / unrealized_pnl（無法投影 PositionExposure）。
///   - 本 Wave B 構造 update task 走「300s tick + no-op push」：
///       * `now_ms`：wall-clock ms 推進，維持 sliding window 24h drain 正確。
///       * `equity_usd=0.0`：no-op equity；不污染 cache（fail-soft fall back 對
///         齊 spec line 247-269 max_dd peak>0 計算保護）。
///       * `new_fills=[]`：no fill push；cum_pnl 24h 維持 0（OK band）。
///       * `latest_exposures=Vec::new()`：position_count_active=0，
///         concentration_top1_pct=0（OK band）。
///   - 效果：cache update task alive + V106 emit 路徑 alive，但 risk_envelope
///     5 metric 全 OK band；emitter sample tick 仍走 5 row INSERT（per
///     emitter sample_interval_sec=300）。
///   - Wave C / Sprint 5+ amend follow-up：caller 接 PaperState SSOT；本 task
///     signature 不變（cache Arc 是 SSOT；update 內部邏輯由 caller 提供）。
///
/// 為什麼 spawn 而非直接 entry：
///   - update task 是長 running tokio task；spawn 後 caller 不需 await。
///   - 共用 cancel token；engine 整體 shutdown 時自然 break tick loop。
///
/// F-2 NaN/inf sanitize 守線（per PA-DRIFT-5 round 2 升級 P1 Wave B condition）:
///   - 本 placeholder no-op tick 全 push 0.0 finite 值；不會撞 NaN/inf；
///     sanitize 守線 已在 `update_from_pipeline_snapshot` 內部執行（per
///     risk_envelope_probe_impl.rs F-2 fix）。
///   - Wave C / Sprint 5+ amend follow-up 接 PaperState SSOT 時，caller 端需
///     確保 realized_pnl / equity / notional 為 finite；若 source 端產 NaN/inf，
///     cache 端 sanitize 守線 直接 skip + fail-loud warn log（per
///     risk_envelope_probe_impl.rs F-2 sanitize）。
pub(crate) fn spawn_portfolio_state_update_task(
    cache: Arc<ParkingMutex<PortfolioStateCache>>,
    cancel: &CancellationToken,
) {
    let task_cancel = cancel.clone();
    tokio::spawn(async move {
        info!(
            target = "m3.health.wireup",
            tick_secs = 300,
            "PortfolioStateCache 300s update task spawning (Wave B placeholder \
             no-op; Sprint 5+ wire-up replaces with PaperState SSOT)"
        );

        // 對齊 risk_envelope emitter sample_interval_sec=300。
        let mut interval = tokio::time::interval(std::time::Duration::from_secs(300));
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

        loop {
            tokio::select! {
                _ = interval.tick() => {
                    let now_ms = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|d| d.as_millis() as u64)
                        .unwrap_or(0);
                    // Wave B placeholder no-op：fail-soft 0 sample push 推進
                    // sliding window drain。
                    // F-4 per_symbol_mid_prices 空 HashMap = cold-start，無 mid
                    // price 觀測；對齊 placeholder 0.0 OK band；Sprint 5+ §4.2
                    // PaperState SSOT wire-up 後此 caller 由 mid price source 提供
                    // 真實 HashMap（per PA spec §4 line 262）。
                    let equity_usd = 0.0_f64;
                    let new_fills: Vec<(u64, f64)> = Vec::new();
                    let latest_exposures: Vec<PositionExposure> = Vec::new();
                    let per_symbol_mid_prices: std::collections::HashMap<String, f64> =
                        std::collections::HashMap::new();
                    {
                        let mut guard = cache.lock();
                        guard.update_from_pipeline_snapshot(
                            now_ms,
                            equity_usd,
                            &new_fills,
                            latest_exposures,
                            &per_symbol_mid_prices,
                        );
                    }
                }
                _ = task_cancel.cancelled() => {
                    info!(
                        target = "m3.health.wireup",
                        "PortfolioStateCache update task cancelled"
                    );
                    break;
                }
            }
        }
    });
}

// ============================================================
// Track E strategy_quality scheduler — RealStrategyQualitySourceProbe + cache
// （Sprint 5+ §4.3.1 Phase A Wave C wire-up）
// ============================================================
//
// 為什麼獨立 scheduler 而非合入 `spawn_metric_emitter_scheduler`（per spec §4.4
// line 638-643）:
//   - `MetricEmitterScheduler` 內部 `state_machines: HashMap<(HealthDomain,
//     String), HealthStateMachine>` 是 (domain, metric_name) 鍵；strategy_quality
//     需要 (domain, metric_name, strategy, symbol) 4-tuple 鍵，會破壞 scheduler
//     既有 hash key shape。
//   - 對齊既有 `StrategyQualityScheduler::run` 範式（strategy_quality.rs line
//     565-810）獨立 tokio task spawn。
//
// 為什麼 25 pair 動態生成 而非硬編碼（per spec §6 反問 #6 + 反模式 (e)）:
//   - SYMBOLS 來自 `event_consumer::types::SYMBOLS` 5 元素 const（BTCUSDT /
//     ETHUSDT / SOLUSDT / XRPUSDT / DOGEUSDT）；strategy 5 元素 const 對齊
//     strategy_params_*.toml 5 [section]（ma_crossover / bb_reversion /
//     bb_breakout / grid_trading / funding_arb）。
//   - 25 pair 是 cartesian product；某些 pair runtime 永遠 inactive（如
//     funding_arb 配 non-funding 對；emitter 端走 fail-soft default OK band）。
//
// 為什麼 PG batch query 而非增量 IPC subscribe（per spec §3.2 reasoning）:
//   - 既有 strategy_engine / fill_writer / lease audit 寫端是 batch INSERT；
//     emitter 端只觀測，不擴 IPC channel scope（per PA-DRIFT-5 Wave B 同
//     reasoning）。
//   - 5 min tick × 1 CTE join query × 5 metric 拿完 25 pair；對 PG load 可忽略
//     （per spec §6 反問 #4 latency 5-10ms 對比 5 parallel query 25-50ms）。

/// 5 strategy 名稱（對齊 strategy_params_*.toml 5 [section]）。
///
/// 為什麼 const 而非 caller 注入:
///   - 5 strategy 是 production strategy_engine 編譯時固定枚舉；無 runtime 動態
///     新增 / 移除路徑（per `feedback_no_dead_params` 反假可配置）。
///   - 對齊既有 sprint2_track_e_strategy_quality.rs `make_25_pairs()` test fixture
///     5 strategy 範式（其中 test 用 "grid" / "ma" 簡化字串；production 走 toml
///     正名）。
const STRATEGY_QUALITY_STRATEGIES: &[&str] = &[
    "ma_crossover",
    "bb_reversion",
    "bb_breakout",
    "grid_trading",
    "funding_arb",
];

/// 構造 25 (strategy, symbol) pair list（5 strategy × 5 SYMBOLS）。
///
/// 為什麼此設計（per spec §4.1 line 690-701）:
///   - 對齊既有 `event_consumer::types::SYMBOLS` 5 symbol（其他模塊已 IMPL 採用）。
///   - 5 strategy 對齊 strategy_params_*.toml 5 [section]。
///   - 25 pair 是 (5 strategy × 5 symbol) cartesian product；某些 pair runtime
///     永遠 inactive（funding_arb × non-funding symbol；emitter 端 fail-soft 走
///     default OK band 不誤升）。
fn build_strategy_quality_pair_list() -> Vec<(String, String)> {
    let mut pairs = Vec::with_capacity(STRATEGY_QUALITY_STRATEGIES.len() * SYMBOLS.len());
    for strategy in STRATEGY_QUALITY_STRATEGIES {
        for symbol in SYMBOLS {
            pairs.push((strategy.to_string(), symbol.to_string()));
        }
    }
    pairs
}

/// 構造 Track E `StrategyQualityScheduler` + 共享 `StrategyQualityMetricsCache`
/// Arc 句柄。
///
/// 返 (scheduler, cache_handle)：caller 同時 spawn scheduler.run + cache update
/// task；兩者共享同 cache Arc。None 時表 DbPool 斷線；caller 端 skip wire-up。
///
/// 為什麼複用 event_bus（caller 端傳入）:
///   - 6 domain 共享 1 event_bus（Sprint 5+ cascade subscriber 預埋）；
///     `spawn_metric_emitter_scheduler` 返 (cache, event_bus_arc)；本 fn 接同
///     event_bus 避免分裂 cascade subscribe 兩條鏈。
fn build_strategy_quality_scheduler(
    db_pool: &Arc<DbPool>,
    engine_mode: EngineModeProvider,
    event_bus: Arc<HealthEventBus>,
) -> Option<(
    StrategyQualityScheduler,
    Arc<ParkingMutex<StrategyQualityMetricsCache>>,
)> {
    let pg_pool = match db_pool.get() {
        Some(p) => p.clone(),
        None => {
            warn!(
                target = "m3.health.wireup",
                "Track E StrategyQualityScheduler skipped: DbPool disconnected at boot"
            );
            return None;
        }
    };
    let writer: Arc<dyn openclaw_engine::health::writer::HealthObservationWriter> =
        Arc::new(PgHealthObservationWriter::new(pg_pool));

    let cache = Arc::new(ParkingMutex::new(StrategyQualityMetricsCache::new()));
    let probe = RealStrategyQualitySourceProbe::new(Arc::clone(&cache));
    let pairs = build_strategy_quality_pair_list();
    let emitter = StrategyQualityEmitter::new(probe, pairs);
    let scheduler = StrategyQualityScheduler::new(emitter, writer, event_bus, engine_mode);

    Some((scheduler, cache))
}

/// Wave C wire-up entry：spawn `StrategyQualityScheduler.run` 為 tokio task。
///
/// 為什麼分離 fn 而非合入 `spawn_metric_emitter_scheduler`（per spec §4.1 line
/// 738-749）:
///   - `StrategyQualityScheduler` 是 6 domain 中唯一獨立 scheduler（per spec
///     §4.4 line 638-643；strategy_quality.rs line 542-556）；不沿用
///     `MetricEmitterScheduler::run_domain_loop` 因 25 instance per-(strategy,
///     symbol) SM 與 single-SM 路徑 hash key shape 不同。
///   - main.rs caller 端兩 spawn entry：原 5 emitter 走 `spawn_metric_emitter_
///     scheduler`，Track E 走本 fn；對齊既有 5 emitter wire-up 後 + 加一 entry
///     不破 5 emitter scope。
///
/// 為什麼複用 event_bus（caller 端傳入）:
///   - 6 domain 共享 1 event_bus（Sprint 5+ cascade subscriber 預埋）；
///     避免分裂 cascade subscribe 兩條鏈。
///
/// OBSERVE-4 propagate Err 不 swallow（per既有 `spawn_metric_emitter_scheduler`
/// 範式 + spec line 199-216）:
///   - scheduler.run 啟動時 OBSERVE-4 guard 撞 replay →
///     Err(ReplaySubprocessForbidden) log error 不 panic；caller 端 tokio task
///     自然結束。
pub(crate) fn spawn_strategy_quality_scheduler(
    db_pool: &Arc<DbPool>,
    engine_mode_str: &'static str,
    event_bus: Arc<HealthEventBus>,
    cancel: &CancellationToken,
) -> Option<Arc<ParkingMutex<StrategyQualityMetricsCache>>> {
    let mode_str = engine_mode_str.to_string();
    let engine_mode: EngineModeProvider = Arc::new(move || mode_str.clone());

    let (scheduler, cache) = build_strategy_quality_scheduler(db_pool, engine_mode, event_bus)?;

    let scheduler_cancel = cancel.clone();
    let mode_for_log = engine_mode_str.to_string();
    tokio::spawn(async move {
        info!(
            target = "m3.health.wireup",
            engine_mode = %mode_for_log,
            domain = "strategy_quality",
            pair_count = 25,
            "Track E StrategyQualityScheduler spawning (independent scheduler; \
             25 (strategy, symbol) pair × 4 band metric SM + 1 telemetry signal_count \
             + 1 aggregate SM)"
        );
        match scheduler.run(scheduler_cancel).await {
            Ok(()) => {
                info!(
                    target = "m3.health.wireup",
                    "Track E StrategyQualityScheduler graceful shutdown"
                );
            }
            Err(M3Error::ReplaySubprocessForbidden) => {
                tracing::error!(
                    target = "m3.health.wireup",
                    "Track E StrategyQualityScheduler OBSERVE-4 guard tripped — \
                     engine_mode='replay' forbidden"
                );
            }
            Err(e) => {
                tracing::error!(
                    target = "m3.health.wireup",
                    error = %e,
                    "Track E StrategyQualityScheduler unexpected error"
                );
            }
        }
    });

    Some(cache)
}

/// 跑 1 batch 5 query (1 big CTE join) → 整 HashMap update cache。
///
/// 為什麼分離 helper（per spec §3.2 line 514-557）:
///   - test 端可直接呼此 fn 用 mocked PG pool（per既有 `RealRiskEnvelopeSourceProbe`
///     test pattern）；spawn 端只負責 tick + cancel。
///   - Path A 推薦（per spec §2.6）：1 big CTE join query 端 5-10ms round-trip
///     對比 5 parallel query 25-50ms 差異 negligible；query 複雜度由 PA spec
///     literal 對齊保 IMPL drift risk 可控。
///
/// fail-soft 對齊（per spec §3.2）:
///   - DbPool 斷線 → log warn + return Ok（不返 Err 避免 spam log；cache 保留
///     stale snapshot 到下次 tick）。
///   - PG query fail → return Err；caller spawn 端 warn log + cache stale。
///   - 整 batch 5 query 都成功 → 整 HashMap 替換；fail-soft sanitize 在 cache
///     `update_batch` 內守 F-2 NaN/inf。
async fn run_strategy_quality_query_batch(
    cache: &Arc<ParkingMutex<StrategyQualityMetricsCache>>,
    db_pool: &Arc<DbPool>,
) -> Result<(), sqlx::Error> {
    let pool = match db_pool.get() {
        Some(p) => p.clone(),
        None => {
            tracing::warn!(
                target = "m3.health.strategy_quality",
                "StrategyQualityMetricsCache update skip: DbPool disconnected"
            );
            return Ok(()); // fail-soft；不返 Err
        }
    };

    // Path A: 1 big CTE join query 拿 25 pair × 5 metric snapshot（per spec §2.6）。
    let rows = sqlx::query_as::<_, StrategyQualityRow>(STRATEGY_QUALITY_BATCH_QUERY)
        .fetch_all(&pool)
        .await?;

    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);

    let snapshots: HashMap<(String, String), StrategyQualityMetricsSnapshot> = rows
        .into_iter()
        .map(|r| {
            (
                (r.strategy_name, r.symbol),
                StrategyQualityMetricsSnapshot {
                    fill_rate_intent_ratio: r.fill_rate_intent_ratio,
                    slippage_bps_p95: r.slippage_bps_p95,
                    decision_lease_grant_rate: r.decision_lease_grant_rate,
                    // PG i32 → Rust u32（spec §3.2 line 569 conversion；i32 0..=
                    // 2147483647 全 fit u32；dormant_minutes ≥ 0 不會負）。
                    dormant_minutes: r.dormant_minutes.max(0) as u32,
                    signal_count_24h: r.signal_count_24h.max(0) as u32,
                    last_update_ts_ms: now_ms,
                },
            )
        })
        .collect();

    cache.lock().update_batch(now_ms, snapshots);
    Ok(())
}

/// sqlx::FromRow target struct for STRATEGY_QUALITY_BATCH_QUERY。
///
/// 為什麼 i32 而非 u32（per spec §3.2 line 569）:
///   - PG `EXTRACT(EPOCH FROM ...) / 60.0` 返 numeric；cast `::int` 為 PG int4
///     ＝ Rust i32（sqlx 0.8 PG int4 → i32）；caller 端 max(0) as u32 對齊
///     trait API。
///   - COUNT(*) 也 cast `::int`；Rust i32；同樣 caller 端 max(0) as u32。
///   - `EXTRACT(EPOCH FROM ...)` 可能 NULL（無 row 時）→ sqlx 端會 Option；本
///     query CTE 端 COALESCE 已 fold 為 0，FromRow 視為 non-Option。
#[derive(sqlx::FromRow)]
struct StrategyQualityRow {
    strategy_name: String,
    symbol: String,
    fill_rate_intent_ratio: f64,
    slippage_bps_p95: f64,
    decision_lease_grant_rate: f64,
    dormant_minutes: i32,
    signal_count_24h: i32,
}

/// spawn StrategyQualityMetricsCache update task (300s tick；對齊
/// strategy_quality emitter sample_interval_sec=300)。
///
/// 為什麼 5 min tick 對齊 emitter sample interval（per spec §6 反問 #3）:
///   - update tick 比 sample tick 慢 → emitter sample 時拿不到 fresh data，走
///     fail-soft default OK band 失能。
///   - update tick 比 sample tick 快 → cache 多餘 update 浪費 PG load。
///   - 300s 對齊是 Pareto-optimal。
///
/// 為什麼啟動立即跑一次 update（per spec §3.2 line 483-487）:
///   - emitter sample_interval=300s；若 update task 也 300s 後第一次跑，前 300s
///     window V106 row 全 default OK band（fail-soft 但 misleading）；首次 update
///     立即執行避此空窗。
///
/// graceful fail：5 query 任一 fail → 整 batch 不 update cache；保留 stale 直到
/// 下次 tick；fail-loud warn log（per F-2 sanitize 對齊）。
pub(crate) fn spawn_strategy_quality_update_task(
    cache: Arc<ParkingMutex<StrategyQualityMetricsCache>>,
    db_pool: Arc<DbPool>,
    cancel: &CancellationToken,
) {
    let task_cancel = cancel.clone();
    tokio::spawn(async move {
        info!(
            target = "m3.health.wireup",
            tick_secs = 300,
            domain = "strategy_quality",
            "StrategyQualityMetricsCache 300s update task spawning (Sprint 5+ \
             §4.3.1 Phase A Wave C; 1 big CTE join query × 25 pair × 5 metric)"
        );

        // 啟動立即跑一次 update（避免首 300s window 全 default OK band）。
        if let Err(e) = run_strategy_quality_query_batch(&cache, &db_pool).await {
            tracing::warn!(
                target = "m3.health.strategy_quality",
                error = %e,
                "StrategyQualityMetricsCache initial batch update failed; cache stale until next tick"
            );
        }

        let mut interval = tokio::time::interval(std::time::Duration::from_secs(300));
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        // tokio interval 第 1 tick 立即觸發；用 first_tick consume 對齊「啟動立即
        // 跑 + 之後 300s 等 1 個完整週期」語意。
        interval.tick().await;

        loop {
            tokio::select! {
                _ = interval.tick() => {
                    if let Err(e) = run_strategy_quality_query_batch(&cache, &db_pool).await {
                        tracing::warn!(
                            target = "m3.health.strategy_quality",
                            error = %e,
                            "StrategyQualityMetricsCache batch update failed; cache stale until next tick"
                        );
                    }
                }
                _ = task_cancel.cancelled() => {
                    info!(
                        target = "m3.health.wireup",
                        "StrategyQualityMetricsCache update task cancelled"
                    );
                    break;
                }
            }
        }
    });
}

/// 25 pair × 5 metric batch query（per spec §2.6 Path A 整合 SSOT）。
///
/// CTE 結構（per spec §3.2 line 578-643）:
///   sig_count, fill_count, dormant, strategy_ctx, lease_grants 5 CTE +
///   FULL OUTER JOIN coalesce 出 25 pair × 5 metric snapshot。
///
/// engine_mode 4 值對齊 V106 CHECK：'paper', 'demo', 'live_demo', 'live'；
/// 對齊 lease_transitions schema 仍用 'live_mainnet'（per spec §3.2 line 621）。
///
/// fail-soft OK band 對齊（per spec §2.1-§2.3）:
///   - sig_n = 0 (cold start / dormant 策略) → fill_rate_intent_ratio = 1.0
///   - requested_n = 0 → decision_lease_grant_rate = 1.0
///   - 對齊 trait doc line 424「probe 失敗返 OK-band 值」。
const STRATEGY_QUALITY_BATCH_QUERY: &str = r#"
WITH
sig_count AS (
    SELECT strategy_name, symbol, COUNT(*)::int AS sig_n
    FROM trading.signals
    WHERE ts >= NOW() - INTERVAL '24 hours'
      AND signal_type IN ('LONG', 'SHORT')
      AND strategy_name IS NOT NULL
    GROUP BY strategy_name, symbol
),
fill_count AS (
    SELECT strategy_name, symbol,
        COUNT(*)::int AS fill_n,
        percentile_cont(0.95) WITHIN GROUP (ORDER BY ABS(slippage_bps))
            FILTER (WHERE slippage_bps IS NOT NULL) AS slip_p95
    FROM trading.fills
    WHERE ts >= NOW() - INTERVAL '24 hours'
      AND engine_mode IN ('paper', 'demo', 'live_demo', 'live')
      AND strategy_name IS NOT NULL
    GROUP BY strategy_name, symbol
),
dormant AS (
    SELECT strategy_name, symbol,
        EXTRACT(EPOCH FROM (NOW() - MAX(ts))) / 60.0 AS dormant_min
    FROM trading.fills
    WHERE engine_mode IN ('paper', 'demo', 'live_demo', 'live')
      AND strategy_name IS NOT NULL
    GROUP BY strategy_name, symbol
),
strategy_ctx AS (
    SELECT DISTINCT context_id, strategy_name, symbol
    FROM trading.signals
    WHERE ts >= NOW() - INTERVAL '24 hours'
      AND strategy_name IS NOT NULL
      AND context_id IS NOT NULL
),
lease_grants AS (
    SELECT
        sc.strategy_name, sc.symbol,
        COUNT(*) FILTER (WHERE lt.to_state = 'REGISTERED')::int AS requested_n,
        COUNT(*) FILTER (WHERE lt.to_state = 'ACTIVE')::int AS granted_n
    FROM learning.lease_transitions lt
    JOIN strategy_ctx sc ON lt.context_id = sc.context_id
    WHERE lt.created_at >= NOW() - INTERVAL '24 hours'
      AND lt.engine_mode IN ('paper', 'demo', 'live_demo', 'live_mainnet')
    GROUP BY sc.strategy_name, sc.symbol
)
SELECT
    COALESCE(sc.strategy_name, fc.strategy_name, dm.strategy_name, lg.strategy_name)
        AS strategy_name,
    COALESCE(sc.symbol, fc.symbol, dm.symbol, lg.symbol) AS symbol,
    CASE WHEN COALESCE(sc.sig_n, 0) > 0
         THEN COALESCE(fc.fill_n, 0)::float8 / sc.sig_n
         ELSE 1.0
    END AS fill_rate_intent_ratio,
    COALESCE(fc.slip_p95, 0.0)::float8 AS slippage_bps_p95,
    CASE WHEN COALESCE(lg.requested_n, 0) > 0
         THEN lg.granted_n::float8 / lg.requested_n
         ELSE 1.0
    END AS decision_lease_grant_rate,
    LEAST(COALESCE(dm.dormant_min, 0.0), 2147483647.0)::int AS dormant_minutes,
    COALESCE(sc.sig_n, 0)::int AS signal_count_24h
FROM sig_count sc
FULL OUTER JOIN fill_count fc USING (strategy_name, symbol)
FULL OUTER JOIN dormant dm USING (strategy_name, symbol)
FULL OUTER JOIN lease_grants lg USING (strategy_name, symbol)
WHERE COALESCE(sc.strategy_name, fc.strategy_name, dm.strategy_name, lg.strategy_name) IS NOT NULL;
"#;

// ============================================================
// 測試（inline 為 wire-up 入口屬性驗）
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// 驗 PlaceholderPipelineThroughputSource 5 default 值對齊 spec line 102 OK
    /// band（per round 2 HIGH-1 fix；原 round 1 全 0 導致 tick_rate/signal_rate
    /// 走 DEGRADED 染色 bug）。
    #[test]
    fn test_placeholder_pipeline_throughput_default_in_ok_band() {
        use openclaw_engine::health::domains::pipeline_throughput::{
            classify_pipeline_throughput_heartbeat_lag_ms,
            classify_pipeline_throughput_ipc_roundtrip_ms_p99,
            classify_pipeline_throughput_signal_rate,
            classify_pipeline_throughput_subscription_drift,
            classify_pipeline_throughput_ws_tick_rate,
        };
        use openclaw_engine::health::HealthState;

        let p = PlaceholderPipelineThroughputSource;
        // 5 default 值對齊 spec line 102 OK band 合法值（無 boundary 抖動）。
        assert_eq!(p.current_ws_tick_rate_per_sec(), 2.0);
        assert_eq!(p.current_ws_heartbeat_lag_ms(), 0);
        assert_eq!(p.current_ws_subscription_drift_count(), 0);
        assert_eq!(p.current_strategy_signal_rate_per_min(), 1.0);
        assert_eq!(p.current_ipc_roundtrip_ms_p99(), 1.0);

        // 5 metric classify 結果 全 HealthOk（不誤升 DEGRADED/WARN）。
        assert_eq!(
            classify_pipeline_throughput_ws_tick_rate(p.current_ws_tick_rate_per_sec()),
            HealthState::HealthOk,
            "tick_rate=2.0 應走 OK band（>=1.0）"
        );
        assert_eq!(
            classify_pipeline_throughput_heartbeat_lag_ms(p.current_ws_heartbeat_lag_ms()),
            HealthState::HealthOk,
            "heartbeat_lag=0ms 應走 OK band（<=30000）"
        );
        assert_eq!(
            classify_pipeline_throughput_subscription_drift(
                p.current_ws_subscription_drift_count()
            ),
            HealthState::HealthOk,
            "subscription_drift=0 應走 OK band"
        );
        assert_eq!(
            classify_pipeline_throughput_signal_rate(
                p.current_strategy_signal_rate_per_min()
            ),
            HealthState::HealthOk,
            "signal_rate=1.0/min 應走 OK band（>=0.5）"
        );
        assert_eq!(
            classify_pipeline_throughput_ipc_roundtrip_ms_p99(
                p.current_ipc_roundtrip_ms_p99()
            ),
            HealthState::HealthOk,
            "ipc_p99=1.0ms 應走 OK band（<5.0）"
        );
    }

    /// 驗 build_risk_envelope_emitter 返同一 cache Arc（caller update task / probe
    /// 共享）。
    #[test]
    fn test_build_risk_envelope_emitter_returns_shared_cache() {
        let (_emitter, cache1) = build_risk_envelope_emitter();
        // 寫一個值（F-4 mid_prices 傳空 HashMap 對齊 placeholder cold-start）
        {
            let mut guard = cache1.lock();
            guard.update_from_pipeline_snapshot(
                1_700_000_000_000,
                100.0,
                &[(1_700_000_000_000, 5.0)],
                vec![PositionExposure { notional_usd: 50.0 }],
                &std::collections::HashMap::new(),
            );
        }
        // 驗 cache 內容對外 visible。
        assert_eq!(cache1.lock().position_count_active(), 1);
        assert!((cache1.lock().cum_pnl_24h_usd() - 5.0).abs() < 1e-9);
    }

    // ============================================================
    // Track E strategy_quality wire-up tests
    // ============================================================

    /// 驗 build_strategy_quality_pair_list 返 25 pair (5 strategy × 5 symbol)。
    ///
    /// 為什麼此 test:
    ///   - 對齊 spec §3.3 反問 #6「25 pair 來源是否硬編碼？」結論：caller 端從
    ///     event_consumer::SYMBOLS 動態生成；非 probe impl 內硬編碼。
    ///   - sprint5_wave_c_strategy_quality_wireup.rs integration test 端可重用
    ///     此 helper 驗 25 pair 完整對齊 STRATEGY_QUALITY_STRATEGIES × SYMBOLS。
    #[test]
    fn test_build_strategy_quality_pair_list_returns_25_unique_pairs() {
        let pairs = build_strategy_quality_pair_list();
        // 5 × 5 = 25
        assert_eq!(pairs.len(), 25, "5 strategy × 5 symbol = 25 pair");
        // 5 strategy 全在
        let unique_strategies: std::collections::HashSet<&str> =
            pairs.iter().map(|(s, _)| s.as_str()).collect();
        assert_eq!(unique_strategies.len(), 5);
        for s in STRATEGY_QUALITY_STRATEGIES {
            assert!(
                unique_strategies.contains(s),
                "strategy {} 必在 pair list",
                s
            );
        }
        // 5 symbol 全在
        let unique_symbols: std::collections::HashSet<&str> =
            pairs.iter().map(|(_, s)| s.as_str()).collect();
        assert_eq!(unique_symbols.len(), 5);
        for sym in SYMBOLS {
            assert!(
                unique_symbols.contains(*sym),
                "symbol {} 必在 pair list",
                sym
            );
        }
        // 25 unique tuple（無重複）
        let unique_pairs: std::collections::HashSet<(String, String)> =
            pairs.iter().cloned().collect();
        assert_eq!(unique_pairs.len(), 25, "25 pair 必全 unique");
    }

    /// 驗 STRATEGY_QUALITY_BATCH_QUERY 字串包含 5 CTE + 4 engine_mode + 4 lease state。
    ///
    /// 為什麼此 test:
    ///   - 對齊 spec AC-4「PG query string + result row parse」；Mac mock 無法
    ///     跑 real PG，但可驗 query literal 對齊 spec §3.2 + 反模式 (j) 不改
    ///     既有 engine_mode IN filter。
    ///   - 防 IMPL 後 query 被「順手優化」改 engine_mode list 或 lease state name
    ///     導致 24h drift。
    #[test]
    fn test_strategy_quality_batch_query_contains_all_required_clauses() {
        let q = STRATEGY_QUALITY_BATCH_QUERY;
        // 5 CTE 名
        assert!(q.contains("sig_count AS"), "sig_count CTE 必存在");
        assert!(q.contains("fill_count AS"), "fill_count CTE 必存在");
        assert!(q.contains("dormant AS"), "dormant CTE 必存在");
        assert!(q.contains("strategy_ctx AS"), "strategy_ctx CTE 必存在");
        assert!(q.contains("lease_grants AS"), "lease_grants CTE 必存在");
        // 5 SSOT 表
        assert!(q.contains("trading.signals"), "走 trading.signals SSOT");
        assert!(q.contains("trading.fills"), "走 trading.fills SSOT");
        assert!(
            q.contains("learning.lease_transitions"),
            "走 learning.lease_transitions SSOT"
        );
        // engine_mode 4 值 fills 端
        assert!(
            q.contains("'paper', 'demo', 'live_demo', 'live'"),
            "fills/dormant engine_mode 4 值對齊 V106 CHECK"
        );
        // lease_transitions engine_mode 用 live_mainnet（per spec §3.2 line 621）
        assert!(
            q.contains("'live_mainnet'"),
            "lease_transitions engine_mode 用 live_mainnet"
        );
        // 4 lease state name
        assert!(q.contains("'REGISTERED'"), "走 REGISTERED state");
        assert!(q.contains("'ACTIVE'"), "走 ACTIVE state");
        // signal_type 2 值
        assert!(
            q.contains("'LONG', 'SHORT'"),
            "signal_type 排除 CLOSE/HOLD"
        );
        // p95 percentile
        assert!(
            q.contains("percentile_cont(0.95)"),
            "slippage 走 p95 percentile_cont"
        );
        // 5 FULL OUTER JOIN
        assert_eq!(
            q.matches("FULL OUTER JOIN").count(),
            3,
            "3 FULL OUTER JOIN 把 sig_count / fill_count / dormant / lease_grants 4 CTE 合"
        );
        // fail-soft OK band default
        assert!(
            q.contains("ELSE 1.0"),
            "sig_n=0 / requested_n=0 → fail-soft OK band 1.0"
        );
        // dormant u32 cap
        assert!(
            q.contains("LEAST(COALESCE(dm.dormant_min, 0.0), 2147483647.0)"),
            "dormant_minutes cap i32::MAX 避免 overflow"
        );
    }

    /// 驗 STRATEGY_QUALITY_STRATEGIES 5 const 對齊 strategy_params_*.toml
    /// section name（per spec §4.1 line 690-695）。
    ///
    /// 為什麼此 test:
    ///   - 對齊 spec §4.1 + 反模式 (e)「strategy/symbol 名硬編碼禁」；本 const
    ///     在 production toml strategy section 同 IMPL，不破壞 single SSOT。
    ///   - 防 IMPL 後常見「順手 rename」（如 ma_crossover → ma）造成 24h
    ///     query strategy_name JOIN 落空。
    #[test]
    fn test_strategy_quality_strategies_align_with_toml_sections() {
        // 5 strategy 必含這些 production name；若 IMPL 端「rename」必先撞此 test。
        assert!(STRATEGY_QUALITY_STRATEGIES.contains(&"ma_crossover"));
        assert!(STRATEGY_QUALITY_STRATEGIES.contains(&"bb_reversion"));
        assert!(STRATEGY_QUALITY_STRATEGIES.contains(&"bb_breakout"));
        assert!(STRATEGY_QUALITY_STRATEGIES.contains(&"grid_trading"));
        assert!(STRATEGY_QUALITY_STRATEGIES.contains(&"funding_arb"));
        assert_eq!(
            STRATEGY_QUALITY_STRATEGIES.len(),
            5,
            "5 strategy 對齊 toml 5 [section]"
        );
    }
}
