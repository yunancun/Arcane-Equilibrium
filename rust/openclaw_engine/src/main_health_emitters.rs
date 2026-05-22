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
//!     - Track B `PipelineThroughputEmitter`：placeholder probe（全返 0；
//!       Sprint 5+ wire-up）。
//!     - Track C `DatabasePoolEmitter`：sqlx PgPool + writer queue probe 0 +
//!       disk usage 走 sysinfo Disks；Wave B 真實 pool stats wire-up。
//!     - Track D `ApiLatencyEmitter`：REST half 真實 wire-up（`shared_client.
//!       latency_histogram_handle()` + `ret_code_counter_handle()`）；WS half
//!       placeholder（per Wave B BybitPrivateWs supervisor 內部重建 Arc，外部
//!       注入非本 round scope；Wave C / Sprint 5+ amend follow-up）。
//!     - Track E `StrategyQualityEmitter`：本 Wave B skip（per dispatch §NOT in
//!       scope；StrategyQualityScheduler 走獨立 scheduler，由 Sprint 5+ wire-up）。
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

use std::sync::Arc;

use parking_lot::Mutex as ParkingMutex;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

use openclaw_engine::bybit_private_ws::{WsDropoutCounter, WsRttHistogram};
use openclaw_engine::bybit_rest_client::{
    BybitRestClient, RestLatencyHistogram, RetCodeCounter,
};
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::health::domains::api_latency::ApiLatencyEmitter;
use openclaw_engine::health::domains::api_latency_probe_impl::RealApiLatencySourceProbe;
use openclaw_engine::health::domains::database_pool::{
    DatabasePoolEmitter, PoolWaitP95Probe, WriterQueueProbe,
};
use openclaw_engine::health::domains::pipeline_throughput::{
    PipelineThroughputEmitter, PipelineThroughputSourceProbe,
};
use openclaw_engine::health::domains::risk_envelope::RiskEnvelopeEmitter;
use openclaw_engine::health::domains::risk_envelope_probe_impl::{
    PortfolioStateCache, PositionExposure, RealRiskEnvelopeSourceProbe,
};
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
//   - 全返 0：emitter 端 5-sample mean=0 走 OK band，不誤升 WARN/DEGRADED。
//   - Sprint 5+ wire-up 時 caller 替換為 real probe；本 placeholder API 不變
//     (impl trait 同一個 signature)。

struct PlaceholderPipelineThroughputSource;

impl PipelineThroughputSourceProbe for PlaceholderPipelineThroughputSource {
    fn current_ws_tick_rate_per_sec(&self) -> f64 {
        // placeholder：Sprint 5+ wire-up 走 ws_client.stats().tick_rate()。
        0.0
    }
    fn current_ws_heartbeat_lag_ms(&self) -> u32 {
        0
    }
    fn current_ws_subscription_drift_count(&self) -> u32 {
        0
    }
    fn current_strategy_signal_rate_per_min(&self) -> f64 {
        0.0
    }
    fn current_ipc_roundtrip_ms_p99(&self) -> f64 {
        0.0
    }
}

// ============================================================
// Placeholder probe — Track D WS half (REST half 走 real)
// ============================================================
//
// 為什麼 hybrid（REST real + WS placeholder）:
//   - `shared_client.latency_histogram_handle()` + `ret_code_counter_handle()`
//     由 BybitRestClient 直接 expose Arc（main_instruments 後可拿）→ REST 半邊
//     real wire-up 無風險。
//   - BybitPrivateWs 在 startup/private_ws.rs supervisor 內每次重建（per attempt
//     新 Arc<WsDropoutCounter> + Arc<WsRttHistogram>）；main.rs 外部無法穩定拿
//     handle 注入 probe（needs supervisor signature 變更 = 破 dispatch §禁忌
//     「不改既有 bybit_private_ws 業務邏輯」）。
//   - Wave B placeholder：本 round 走 `WsDropoutCounter::new()` + `WsRttHistogram
//     ::new()` 0-state instance；count() / percentile_pair() 均返 0 → emitter
//     classify 走 OK band，不誤升。
//   - Wave C / Sprint 5+ amend follow-up：BybitPrivateWs supervisor 改為外部
//     注入 Arc handle pattern（per Track D `ApiLatencyEmitter::new(probe)` API
//     不變；只換 probe 內部 ws_dropout/ws_rtt 為 external Arc clone）。

/// 構造 Track D `RealApiLatencySourceProbe`：REST half real + WS half placeholder。
///
/// 為什麼 wrapper fn 而非 inline:
///   - main.rs caller 端 clean call site（一行注入）；placeholder Arc 構造邏輯
///     封裝避 noise。
///   - 未來 Wave C amend 時 caller signature 不變；只在本 fn 內換 WS Arc 來源。
fn build_real_api_latency_probe(
    shared_client: &Arc<BybitRestClient>,
) -> RealApiLatencySourceProbe {
    let rest_latency: Arc<RestLatencyHistogram> = shared_client.latency_histogram_handle();
    let ret_code_counter: Arc<RetCodeCounter> = shared_client.ret_code_counter_handle();
    // WS half placeholder：fresh 0-state instance（per module note）。
    let ws_dropout: Arc<WsDropoutCounter> = Arc::new(WsDropoutCounter::new());
    let ws_rtt: Arc<WsRttHistogram> = Arc::new(WsRttHistogram::new());
    RealApiLatencySourceProbe::new(rest_latency, ret_code_counter, ws_dropout, ws_rtt)
}

/// 構造 Track D `ApiLatencyEmitter`：shared_client 缺席時走全 placeholder probe。
///
/// 為什麼 fallback：main_instruments 端 live/demo 均不 bind 時 shared_client 為
/// None；emitter 仍構造（0 sample row 比缺 emitter 少干涉 V106 emitter chain）。
fn build_api_latency_emitter(
    shared_client: &Option<Arc<BybitRestClient>>,
) -> Box<dyn DomainEmitter> {
    match shared_client {
        Some(client) => {
            let probe = build_real_api_latency_probe(client);
            Box::new(ApiLatencyEmitter::new(probe))
        }
        None => {
            // 全 placeholder：4 個 0-state instance；REST 半邊 fallback。
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

fn build_database_pool_emitter(
    db_pool: &Arc<DbPool>,
    pool_max_conn: u32,
    data_dir_mount: &str,
) -> Box<dyn DomainEmitter> {
    // placeholder：Sprint 5+ wire-up 走 market_writer.rs Vec<MarketDataMsg> len。
    let writer_queue_probe: WriterQueueProbe = Arc::new(|| 0u32);
    // placeholder：Sprint 5+ wire-up 走 sqlx Pool acquire wait time histogram。
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

    // Step 4: 構造 6 emitter（A real / B placeholder / C real / D hybrid / E
    // skip / F real）。
    let engine_runtime = build_engine_runtime_emitter();
    let pipeline_throughput: Box<dyn DomainEmitter> =
        Box::new(PipelineThroughputEmitter::new(PlaceholderPipelineThroughputSource));
    let database_pool = build_database_pool_emitter(db_pool, pool_max_conn, data_dir_mount);
    let api_latency = build_api_latency_emitter(shared_client);
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
    let scheduler =
        MetricEmitterScheduler::new(emitters, writer, Arc::clone(&event_bus), engine_mode);
    let scheduler_cancel = cancel.clone();
    let mode_for_log = engine_mode_str.to_string();
    tokio::spawn(async move {
        info!(
            target = "m3.health.wireup",
            engine_mode = %mode_for_log,
            emitter_count = 5,
            "M3 MetricEmitterScheduler spawning (Track A real + B placeholder + C real \
             + D REST-real/WS-placeholder + F real; Track E skip per Sprint 5+ wire-up)"
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
                    let equity_usd = 0.0_f64;
                    let new_fills: Vec<(u64, f64)> = Vec::new();
                    let latest_exposures: Vec<PositionExposure> = Vec::new();
                    {
                        let mut guard = cache.lock();
                        guard.update_from_pipeline_snapshot(
                            now_ms,
                            equity_usd,
                            &new_fills,
                            latest_exposures,
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
// 測試（inline 為 wire-up 入口屬性驗）
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// 驗 PlaceholderPipelineThroughputSource 全返 0（fail-soft OK band 對齊）。
    #[test]
    fn test_placeholder_pipeline_throughput_returns_zero() {
        let p = PlaceholderPipelineThroughputSource;
        assert_eq!(p.current_ws_tick_rate_per_sec(), 0.0);
        assert_eq!(p.current_ws_heartbeat_lag_ms(), 0);
        assert_eq!(p.current_ws_subscription_drift_count(), 0);
        assert_eq!(p.current_strategy_signal_rate_per_min(), 0.0);
        assert_eq!(p.current_ipc_roundtrip_ms_p99(), 0.0);
    }

    /// 驗 build_risk_envelope_emitter 返同一 cache Arc（caller update task / probe
    /// 共享）。
    #[test]
    fn test_build_risk_envelope_emitter_returns_shared_cache() {
        let (_emitter, cache1) = build_risk_envelope_emitter();
        // 寫一個值
        {
            let mut guard = cache1.lock();
            guard.update_from_pipeline_snapshot(
                1_700_000_000_000,
                100.0,
                &[(1_700_000_000_000, 5.0)],
                vec![PositionExposure { notional_usd: 50.0 }],
            );
        }
        // 驗 cache 內容對外 visible。
        assert_eq!(cache1.lock().position_count_active(), 1);
        assert!((cache1.lock().cum_pnl_24h_usd() - 5.0).abs() < 1e-9);
    }
}
