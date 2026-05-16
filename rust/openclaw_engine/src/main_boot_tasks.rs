//! Boot-time task spawn helpers — position reconciler (per-pipeline) and
//! StrategistScheduler (DB restore + AI-driven param tuner).
//! 啟動期任務 spawn 輔助 — per-pipeline 持倉對帳器 + StrategistScheduler
//! （DB 恢復 + AI 驅動參數調諧）。
//!
//! MODULE_NOTE (EN): Extracted from `main.rs` (G1-03 Wave 1) to bring the
//!   orchestration file under §九 1200-line hard limit. Both blocks are
//!   self-contained boot-time wiring: reconciler needs per-engine mirrors +
//!   the RiskConfig closure; scheduler needs demo_cmd_tx + ai_client +
//!   db_pool + DB restore of last-applied tuned params.
//! MODULE_NOTE (中): 從 `main.rs` 抽出（G1-03 Wave 1），為將 main.rs 壓在
//!   §九 1200 行硬上限下。兩個區塊皆為自足的 boot-time 接線：reconciler 需要
//!   per-engine mirror + RiskConfig 閉包；scheduler 需要 demo_cmd_tx + ai_client +
//!   db_pool + DB 恢復上次 applied tuned params。

use crate::startup::ExchangePipelineBindings;
use crate::tasks;
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::h_state_cache::poller::{
    make_invalidation_channel, spawn_h_state_poller, InvalidationSender, StubHStateFetcher,
    DEFAULT_POLL_INTERVAL,
};
use openclaw_engine::h_state_cache::{is_gateway_enabled, HStateCache};
use openclaw_engine::ipc_server::{
    DemoCmdSenderSlot, HStateCacheSlot, LiveCmdSenderSlot, PerEngineRiskStores,
};
use openclaw_engine::scanner::registry::SymbolRegistry;
use openclaw_engine::tick_pipeline::PipelineCommand;
use std::sync::Arc;
use std::time::Duration;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

/// Positions mirrors tuple: `(paper, demo, live)`.
/// 各引擎持倉鏡像三元組 `(paper, demo, live)`。
#[allow(clippy::type_complexity)]
pub(crate) type PositionsMirrors = (
    Arc<parking_lot::RwLock<std::collections::HashMap<String, bool>>>,
    Arc<parking_lot::RwLock<std::collections::HashMap<String, bool>>>,
    Arc<parking_lot::RwLock<std::collections::HashMap<String, bool>>>,
);

/// Build per-engine positions mirrors (paper / demo / live).
///
/// EN: Each mirror holds `(symbol → is_long)` for the engine's current
///   PaperState view; reconciler reads to suppress its own fresh-fill
///   false-positive Orphans; pipeline writes through PaperState helpers.
///   Built BEFORE reconciler spawn so OrphanHandlerConfig and EventConsumerDeps
///   share the same Arc.
/// 中: 每個 mirror 存 `(symbol → is_long)` 引擎當前 PaperState 視圖；對帳器
///   讀端抑制假 Orphan，引擎端經 PaperState helper 寫入。必須在 reconciler
///   spawn 之前建立，才能與 OrphanHandlerConfig / EventConsumerDeps 共享 Arc。
pub(crate) fn build_positions_mirrors() -> PositionsMirrors {
    (
        Arc::new(parking_lot::RwLock::new(std::collections::HashMap::new())),
        Arc::new(parking_lot::RwLock::new(std::collections::HashMap::new())),
        Arc::new(parking_lot::RwLock::new(std::collections::HashMap::new())),
    )
}

/// Per-exchange position reconciler spawner (Phase 6 + D23).
///
/// EN: Each engine's reconciler gets its own closure reading
///   `max_order_notional_usdt` from the matching per-engine RiskConfig store.
///   Scanner universe + edge estimates are shared (production pool).
///   If neither Live nor Demo is bound, logs a single info-line and returns.
/// 中: 每引擎對帳器獲得獨立 `max_order_notional_usdt` 閉包（讀自 per-engine
///   RiskConfig store）；scanner universe + edge estimates 共享（生產池）。
///   Live 與 Demo 皆未綁則單行 info log 退出。
#[allow(clippy::too_many_arguments)]
pub(crate) fn spawn_position_reconcilers(
    db_pool: &Arc<DbPool>,
    cancel: &CancellationToken,
    risk_stores: &PerEngineRiskStores,
    symbol_registry: &Arc<SymbolRegistry>,
    scanner_edge_estimates: &Arc<
        parking_lot::RwLock<openclaw_engine::edge_estimates::EdgeEstimates>,
    >,
    shared_instruments: &Option<Arc<openclaw_engine::instrument_info::InstrumentInfoCache>>,
    live_bindings: &Option<ExchangePipelineBindings>,
    demo_bindings: &Option<ExchangePipelineBindings>,
    live_cmd_slot: &LiveCmdSenderSlot,
    demo_cmd_slot: &DemoCmdSenderSlot,
    mirrors: &PositionsMirrors,
) {
    let (paper_mirror, demo_mirror, live_mirror) = mirrors;
    // ORPHAN-ADOPT-1 Phase 1：為每引擎構建 OrphanHandlerConfig。
    let build_orphan_cfg = |engine_key: &str| {
        let store = Arc::clone(risk_stores.select(engine_key));
        let mirror = match engine_key {
            "live" => Arc::clone(live_mirror),
            "demo" => Arc::clone(demo_mirror),
            _ => Arc::clone(paper_mirror),
        };
        openclaw_engine::position_reconciler::OrphanHandlerConfig {
            symbol_registry: Arc::clone(symbol_registry),
            edge_estimates: Arc::clone(scanner_edge_estimates),
            get_max_notional: Arc::new(move || store.load().limits.max_order_notional_usdt),
            engine_positions_mirror: mirror,
        }
    };

    // Live reconciler：透過 slot 間接讀取 cmd_tx（已有 pattern）。
    if let Some(ref live_b) = live_bindings {
        let slot = Arc::clone(live_cmd_slot);
        let cmd_tx_provider: openclaw_engine::position_reconciler::ReconcilerCommandTxProvider =
            Arc::new(move || slot.read().as_ref().cloned());
        tasks::spawn_position_reconciler_with_cmd_provider(
            &live_b.rest_client,
            db_pool,
            cancel,
            cmd_tx_provider,
            shared_instruments,
            &live_b.risk_level,
            live_b.env,
            Some(build_orphan_cfg("live")),
        );
        info!("position_reconciler spawned for Live / Live 持倉對帳器已啟動");
    }
    // Demo reconciler（WP-13 FA-P1-11）：改用 slot 間接讀取，對齊 live pattern，
    // 避免 by-value 值捕獲在 pipeline restart 後過時。
    if let Some(ref demo_b) = demo_bindings {
        let slot = Arc::clone(demo_cmd_slot);
        let cmd_tx_provider: openclaw_engine::position_reconciler::ReconcilerCommandTxProvider =
            Arc::new(move || slot.read().as_ref().cloned());
        tasks::spawn_position_reconciler_with_cmd_provider(
            &demo_b.rest_client,
            db_pool,
            cancel,
            cmd_tx_provider,
            shared_instruments,
            &demo_b.risk_level,
            demo_b.env,
            Some(build_orphan_cfg("demo")),
        );
        info!("position_reconciler spawned for Demo / Demo 持倉對帳器已啟動");
    }
    if live_bindings.is_none() && demo_bindings.is_none() {
        info!(
            "position_reconciler skipped (no exchange pipelines) / 持倉對帳器跳過（無交易所管線）"
        );
    }
}

/// StrategistScheduler boot: DB restore of last-applied tuned params, then
/// spawn the single scheduler tokio task.
///
/// EN (STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1, 2026-04-23):
///   - tune target = Demo (not Paper). Paper is disabled-by-default under
///     PAPER-DISABLE-1; its cmd channel is drained-and-dropped, causing the
///     scheduler's oneshot response to vanish and emit "channel closed"
///     warnings every 5 minutes.
///   - Live is passed as optional promote target (None when authorization.json
///     is unsigned / Live binding absent). Wiring present so Phase 5+ can add
///     the promotion trigger + criteria without touching this call site.
///   - If Demo is itself not bound, skip scheduler spawn entirely (single
///     info log). This handles dev scenarios where demo_bindings is None.
///
/// EN (STRATEGIST-PARAMS-PERSIST-1, 2026-04-23): restore last-known tuned
///   params from DB BEFORE spawning the scheduler. Without this, every engine
///   rebuild silently reverts tuned strategy params to TOML baseline,
///   resetting the AUTO-PROMOTE stability counter forever.
///   Fail-soft: DB unavailable / migration V019 not applied → empty vec,
///   log single warn, engine starts normally.
///
/// 中 (STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1):
///   - tune target = Demo（非 Paper）。Paper 預設禁用下其 cmd channel 被 drain-drop，
///     scheduler 的 oneshot response 跟著消失 → 每 5 分鐘噴 "channel closed" 假警。
///   - Live 作 optional promote target（authorization.json 未簽則為 None）。
///   - Demo 未綁則 scheduler 整個不 spawn（單行 info log）。
/// 中 (STRATEGIST-PARAMS-PERSIST-1): spawn scheduler 前先從 DB 恢復上次 tune 好
///   的參數，避免 rebuild 靜默回 TOML baseline 重置 AUTO-PROMOTE 計數器。
pub(crate) async fn spawn_strategist_scheduler(
    db_pool: &Arc<DbPool>,
    cancel: &CancellationToken,
    demo_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    demo_cmd_slot: &DemoCmdSenderSlot,
    live_cmd_slot: &LiveCmdSenderSlot,
    risk_stores: &PerEngineRiskStores,
) -> Option<Arc<openclaw_engine::strategist_scheduler::CycleCounters>> {
    let Some(demo_tx) = demo_cmd_tx.as_ref() else {
        info!(
            "StrategistScheduler not spawned — Demo engine not bound \
             / Demo 引擎未綁定，策略師排程器未啟動"
        );
        return None;
    };

    // STRATEGIST-PARAMS-PERSIST-1 (2026-04-23): restore last-known tuned
    // params from DB BEFORE spawning the scheduler. Without this, every
    // engine rebuild silently reverts tuned strategy params to TOML
    // baseline, resetting the AUTO-PROMOTE stability counter forever.
    //
    // Fail-soft: DB unavailable / migration V019 not applied → empty vec,
    // log single warn, engine starts normally. The system degrades to
    // pre-PERSIST-1 behaviour (TOML baseline) rather than failing to boot.
    //
    // BOOT-DEADLOCK-FIX (G6-FUP-TICK-PIPELINE-DEAD-1, 2026-04-25):
    //   The original implementation `await`d each `rx.await` per restored
    //   row on the calling (main) thread. But this fn is invoked BEFORE
    //   `main_pipelines::spawn_demo_pipeline`, so demo's event consumer is
    //   not yet draining `demo_cmd_tx`. The first `rx.await` therefore
    //   blocks forever, main thread never reaches pipeline spawn, and the
    //   engine sits with WS subscribed but tick_pipeline never created
    //   (no snapshot writes, watchdog reads stale snapshot as "crash").
    //   This was harmless when `learning.strategist_applied_params` was
    //   empty (first-boot path: `Ok(_)` arm). It became a hard deadlock
    //   the moment STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1 (`d8f5560` /
    //   `e47b1e9` / `5538e52`, 2026-04-24) wrote the first row.
    //   Fix: do the DB load synchronously (small bounded query, returns in
    //   ms), then dispatch the IPC fan-out + per-row audit-await in a
    //   spawned task. The unbounded `demo_cmd_tx` queues messages until
    //   demo pipeline drains them after bootstrap; the spawned task can
    //   wait for responses without blocking main thread. Scheduler's
    //   first cycle is 5 min later — plenty of buffer for restore to land.
    // BOOT-DEADLOCK-FIX：原寫法在主執行緒上對每筆 restored row 做 rx.await，
    // 但此函式在 demo pipeline spawn 之前被呼叫，主執行緒於是死鎖。
    // 改為：DB 載入在主執行緒（小查詢，毫秒級），IPC 派送 + 等待回應改丟
    // tokio::spawn，不阻塞主執行緒推進到 pipeline spawn。
    let demo_mode = openclaw_engine::tick_pipeline::PipelineKind::Demo.db_mode();
    let restored =
        match openclaw_engine::strategist_scheduler::load_latest_applied_params(db_pool, demo_mode)
            .await
        {
            Ok(rows) => rows,
            Err(e) => {
                warn!(
                    error = %e,
                    engine_mode = %demo_mode,
                    "STRATEGIST-PARAMS-PERSIST-1: restore query failed (fail-soft, \
                     continuing with TOML baseline) \
                     / 恢復查詢失敗（容錯跳過，使用 TOML baseline 啟動）"
                );
                Vec::new()
            }
        };

    if restored.is_empty() {
        info!(
            engine_mode = %demo_mode,
            "STRATEGIST-PARAMS-PERSIST-1: no tuned params to restore (first boot / clean DB) \
             / 無需恢復（首次啟動或空表）",
        );
    } else {
        let demo_tx_for_restore = demo_tx.clone();
        let demo_mode_owned = demo_mode.to_string();
        // BOOT-DEADLOCK-FIX: dispatch restore IPC + audit in background task.
        // BOOT-DEADLOCK-FIX：背景任務派送恢復 IPC，不阻主執行緒。
        tokio::spawn(async move {
            let total = restored.len();
            let mut ok = 0usize;
            for (strategy_name, params_json) in restored {
                let (tx, rx) = tokio::sync::oneshot::channel();
                if let Err(e) = demo_tx_for_restore.send(
                    openclaw_engine::tick_pipeline::PipelineCommand::UpdateStrategyParams {
                        strategy_name: strategy_name.clone(),
                        params_json,
                        response_tx: tx,
                    },
                ) {
                    warn!(
                        strategy = %strategy_name,
                        error = %e,
                        "STRATEGIST-PARAMS-PERSIST-1: restore IPC send failed \
                         / 恢復 IPC 發送失敗"
                    );
                    continue;
                }
                match rx.await {
                    Ok(Ok(_)) => {
                        ok += 1;
                    }
                    Ok(Err(e)) => {
                        warn!(
                            strategy = %strategy_name,
                            error = %e,
                            "STRATEGIST-PARAMS-PERSIST-1: restore handler rejected \
                             / 恢復 handler 拒絕"
                        );
                    }
                    Err(e) => {
                        warn!(
                            strategy = %strategy_name,
                            error = %e,
                            "STRATEGIST-PARAMS-PERSIST-1: restore response channel closed \
                             / 恢復回應 channel 已關閉"
                        );
                    }
                }
            }
            info!(
                n = ok,
                total,
                engine_mode = %demo_mode_owned,
                "STRATEGIST-PARAMS-PERSIST-1: restored N tuned params from DB \
                 / 從 DB 恢復 N 條已調參數",
            );
        });
    }

    let ai_client = Arc::new(openclaw_engine::ai_service_client::AiServiceClient::new());
    // STRATEGIST-TUNE-TARGET-CONFIG-1 (2026-04-25): wire the demo RiskConfig
    // store into the scheduler so each evaluation cycle reads
    // `strategist.max_param_delta_pct` from the live snapshot (IPC-hot-reloadable).
    // The scheduler tunes Demo, so the Demo store is the authoritative source.
    // STRATEGIST-TUNE-TARGET-CONFIG-1：把 demo RiskConfig store 接給 scheduler，
    // 每輪從 live snapshot 讀 max_param_delta_pct（IPC 熱重載）。
    // WP-13-LEFTOVER-1 (2026-05-16, FA-P1-11 補修)：注入 demo_cmd_slot 為
    // tune-target sender 來源。scheduler 內部 `tune_cmd_snapshot()` 每輪
    // fetch_current_params / apply_params 從 slot 讀最新 sender，pipeline
    // restart 後自動拿到新 channel（不需重 spawn scheduler）。owned
    // `tune_cmd_tx`（即 `demo_tx.clone()`）保留作為 slot try_read 爭用 / 啟動
    // 瞬間 None 的 fallback，與既有 promote slot pattern 對稱。
    let scheduler = Arc::new(
        openclaw_engine::strategist_scheduler::StrategistScheduler::new(
            ai_client,
            demo_tx.clone(),
            openclaw_engine::tick_pipeline::PipelineKind::Demo,
            None,
            Arc::clone(db_pool),
            cancel.clone(),
        )
        .with_promote_cmd_slot(Arc::clone(live_cmd_slot))
        .with_tune_cmd_slot(Arc::clone(demo_cmd_slot))
        .with_risk_store(Arc::clone(&risk_stores.demo)),
    );
    // G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25): grab the shared
    // CycleCounters Arc BEFORE moving the scheduler into run_forever. main.rs
    // hands this to `IpcServer::set_strategist_counters` so the
    // `get_strategist_cycle_metrics` IPC method can read live counters
    // without going through the pipeline command channel.
    // G3-11：在 scheduler move 進 run_forever 前抓 CycleCounters Arc，給 IPC server 讀。
    let counters = scheduler.cycle_counters();
    tokio::spawn(scheduler.run_forever());
    let has_live_promote = live_cmd_slot.read().as_ref().is_some();
    info!(
        has_live_promote,
        "StrategistScheduler spawned — tune_target=Demo / 策略師排程器已啟動（調諧目標=Demo）",
    );
    Some(counters)
}

/// G3-08 H State Gateway Phase 1 (2026-04-26): conditionally spawn the
/// `HStateCache` + 10s poller daemon, gated by `OPENCLAW_H_STATE_GATEWAY=1`.
///
/// EN: DEFAULT-OFF: when the env-gate is missing or any value other than
///   `"1"` (strict comparison) this fn returns `None` immediately,
///   allocating zero memory and spawning zero tasks. Production stays at
///   the documented baseline (no IPC traffic, no thread overhead) until
///   operator opts in.
///
///   When env=1: build the cache (Arc<HStateCache>), the watch-channel
///   pair for invalidation hints, then spawn the periodic+invalidation
///   poll daemon. Caller is responsible for wiring the returned cache
///   Arc into `IpcServer::h_state_cache_slot()` and the sender into
///   `IpcServer::set_h_state_invalidation_sender()`.
///
///   Phase 1 deliberately uses [`StubHStateFetcher`] which returns an
///   empty `default()` snapshot (`version=0`). Sub-task B (parallel) +
///   Sub-task C (later session) replace the stub with a real Python
///   reverse-IPC client when their FastAPI route + handler land. Until
///   then the env=1 path is observable end-to-end (cargo test green,
///   IPC handlers live) but reads return empty data — exactly the
///   Phase 1 acceptance criterion.
///
/// 中: DEFAULT-OFF：env-gate 未設或值不是嚴格 `"1"` 時直接回 `None`，
///   不分配記憶體、不 spawn 任何 task。生產維持文件 baseline
///   （0 IPC 流量 / 0 thread 額外負載）直到 operator opt-in。
///
///   env=1 時：建 cache（Arc<HStateCache>）、建 watch-channel pair（給
///   invalidation hint）、spawn 週期 + invalidation 觸發的 poll daemon。
///   呼叫者負責把回傳的 cache Arc 接到
///   `IpcServer::h_state_cache_slot()`、把 sender 接到
///   `IpcServer::set_h_state_invalidation_sender()`。
///
///   Phase 1 故意用 [`StubHStateFetcher`] 回空 `default()` snapshot
///   （`version=0`）。Sub-task B（並行）+ Sub-task C（後續 session）等
///   Python reverse-IPC FastAPI route + handler 落地後再替換為真實
///   client。在那之前 env=1 路徑端到端可觀測（cargo test 綠 / IPC
///   handler live），但讀回是空 dict — 即 Phase 1 驗收標準。
pub(crate) fn spawn_h_state_poller_if_enabled(
    cache_slot: &HStateCacheSlot,
    cancel: &CancellationToken,
) -> Option<InvalidationSender> {
    if !is_gateway_enabled() {
        // Zero-overhead path / 零負擔路徑
        info!(
            "h_state_gateway disabled (OPENCLAW_H_STATE_GATEWAY != \"1\"), poller not spawned \
             / H State Gateway 未啟用，poller 未啟動",
        );
        return None;
    }

    let cache = HStateCache::new_arc();
    let (inv_tx, inv_rx) = make_invalidation_channel();
    // Phase 1 stub fetcher — Sub-task B/C replaces with real client.
    // Phase 1 stub fetcher — Sub-task B/C 替換為真實 client。
    let fetcher = Arc::new(StubHStateFetcher);

    let _handle = spawn_h_state_poller(
        Arc::clone(&cache),
        fetcher,
        DEFAULT_POLL_INTERVAL,
        inv_rx,
        cancel.clone(),
    );

    // Late-inject cache into the IPC slot so the three handlers
    // (query_h_state_full / get_h_state_status / invalidate_h_state)
    // pick it up automatically.
    // 將 cache 延後注入 IPC slot，讓三個 handler 自動接到。
    let cache_slot_clone = Arc::clone(cache_slot);
    tokio::spawn(async move {
        cache_slot_clone.write().await.replace(cache);
    });

    info!(
        poll_interval_ms = DEFAULT_POLL_INTERVAL.as_millis() as u64,
        fetcher = "stub (Phase 1)",
        "h_state_gateway spawned (env=1) — Phase 1 stub fetcher returns empty snapshots \
         / H State Gateway 已啟動（env=1）— Phase 1 stub fetcher 回空 snapshot",
    );

    Some(inv_tx)
}

/// F6 PH5-WIRE-1 RELOAD env-gate flag (DEFAULT-OFF, strict "1" semantics).
const ENV_EDGE_RELOAD_FLAG: &str = "OPENCLAW_EDGE_RELOAD";
/// F6 reload daemon override interval in seconds.
const ENV_EDGE_RELOAD_INTERVAL_SECS: &str = "OPENCLAW_EDGE_RELOAD_INTERVAL_SECS";
/// Default reload interval — 1h, mirrors Python `edge_estimator_scheduler` cycle.
const DEFAULT_EDGE_RELOAD_INTERVAL: Duration = Duration::from_secs(3600);
/// Floor on reload interval (60s) — prevents misconfig DoS on IPC channel.
const MIN_EDGE_RELOAD_INTERVAL_SECS: u64 = 60;
/// Buffer-1 manual trigger channel — coalesces rapid IPC requests into single fan-out.
const EDGE_RELOAD_SIGNAL_BUFFER: usize = 1;

/// EN: F6 PH5-WIRE-1 RELOAD daemon spawner — periodic + manual trigger
///   reloader for the on-disk edge estimates snapshot. Mirrors the
///   `spawn_h_state_poller_if_enabled` pattern (G3-08 Phase 1A) for
///   structural consistency. Strict env-gate `OPENCLAW_EDGE_RELOAD == "1"`
///   (DEFAULT-OFF). Returns `None` when disabled (zero memory / zero spawn).
///   Returns `Some(Sender<()>)` when enabled, for IPC dispatch to wire as
///   the manual reload trigger. The daemon owns clones of the per-pipeline
///   `cmd_tx` (paper / demo / live) and fans out
///   `PipelineCommand::ReloadEdgeEstimates` to each available pipeline.
///   Each engine reads its own mode-specific JSON inside
///   `handle_reload_edge_estimates` — structural mode isolation: paper
///   exploration cells can never reach demo/live cost_gate.
///
/// 中: F6 PH5-WIRE-1 RELOAD daemon spawner — 週期 + 手動 trigger 兩條重載
///   路徑共用 handler 的對外接線函式。沿用 `spawn_h_state_poller_if_enabled`
///   pattern（G3-08 Phase 1A）。嚴格 env-gate `OPENCLAW_EDGE_RELOAD == "1"`
///   （DEFAULT-OFF）。關閉時回 `None`（0 記憶體 / 0 spawn）；啟用時回
///   `Some(Sender<()>)` 給 IPC dispatch 接為 manual trigger。Daemon 持有
///   per-pipeline `cmd_tx` clone（paper/demo/live），對每個可用管線 fan-out
///   `PipelineCommand::ReloadEdgeEstimates`。每個引擎在
///   `handle_reload_edge_estimates` 內讀自己模式對應 JSON — 結構性模式隔離。
///
/// WP-13-LEFTOVER-1 (2026-05-16, FA-P1-11 補修)：`demo_cmd_tx` 由 by-value
/// `Option<UnboundedSender<_>>` 改為 `Option<DemoCmdSenderSlot>`，對齊 live
/// slot pattern。Reloader loop 每次 dispatch 從 slot 讀最新 sender，避免
/// boot-time 值捕獲在 demo pipeline restart 後過時。Paper 路徑保留 by-value
/// （paper 預設關 + 無 paper slot 基礎設施，本 PA 不擴 scope）。
pub(crate) fn spawn_edge_estimates_reloader_if_enabled(
    paper_cmd_tx: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    demo_cmd_slot: Option<DemoCmdSenderSlot>,
    live_cmd_slot: Option<LiveCmdSenderSlot>,
    cancel: &CancellationToken,
) -> Option<tokio::sync::mpsc::Sender<()>> {
    if !is_edge_reload_enabled() {
        info!(
            "edge_estimates_reloader disabled (OPENCLAW_EDGE_RELOAD != \"1\"), daemon not spawned \
             / Edge 估計重載 daemon 未啟用，daemon 未啟動",
        );
        return None;
    }
    if paper_cmd_tx.is_none() && demo_cmd_slot.is_none() && live_cmd_slot.is_none() {
        warn!(
            "edge_estimates_reloader env=1 but no pipeline cmd_tx bound — \
             daemon not spawned / env=1 但無管線 cmd_tx 綁定，daemon 未啟動"
        );
        return None;
    }

    let interval_dur = resolve_reload_interval();
    let (signal_tx, signal_rx) = tokio::sync::mpsc::channel::<()>(EDGE_RELOAD_SIGNAL_BUFFER);
    let cancel_for_task = cancel.clone();

    tokio::spawn(run_edge_estimates_reloader_loop(
        paper_cmd_tx,
        demo_cmd_slot,
        live_cmd_slot,
        interval_dur,
        signal_rx,
        cancel_for_task,
    ));

    info!(
        interval_secs = interval_dur.as_secs(),
        "F6 PH5-WIRE-1 RELOAD: edge estimates reloader daemon spawned (env=1) \
         / Edge 估計重載 daemon 已啟動（env=1）"
    );

    Some(signal_tx)
}

/// EN: Strict env-gate check — accepts only literal `"1"`.
/// 中: 嚴格 env-gate 檢查 — 只接受字面值 `"1"`。
fn is_edge_reload_enabled() -> bool {
    std::env::var(ENV_EDGE_RELOAD_FLAG).as_deref() == Ok("1")
}

/// EN: Resolve reload interval — env override `OPENCLAW_EDGE_RELOAD_INTERVAL_SECS`
///   if parseable as `u64 >= 60`; else default 1h. Floor prevents IPC DoS.
/// 中: 解析重載週期 — env 變數 ≥ 60 時用之，否則預設 1h；下限防 IPC DoS。
fn resolve_reload_interval() -> Duration {
    std::env::var(ENV_EDGE_RELOAD_INTERVAL_SECS)
        .ok()
        .and_then(|s| s.parse::<u64>().ok())
        .filter(|&secs| secs >= MIN_EDGE_RELOAD_INTERVAL_SECS)
        .map(Duration::from_secs)
        .unwrap_or(DEFAULT_EDGE_RELOAD_INTERVAL)
}

/// EN: Inner reload loop — periodic + manual trigger. Skip the immediate
///   first tick so boot-time inject's snapshot stands until first
///   scheduled reload. Send failures warn-and-continue; daemon never panics.
/// 中: 內層 reload loop — 週期 + 手動 trigger。跳過立即第一個 tick；
///   send 失敗 warn 後續跑、絕不 panic。
async fn run_edge_estimates_reloader_loop(
    paper_cmd_tx: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    demo_cmd_slot: Option<DemoCmdSenderSlot>,
    live_cmd_slot: Option<LiveCmdSenderSlot>,
    interval_dur: Duration,
    mut signal_rx: tokio::sync::mpsc::Receiver<()>,
    cancel: CancellationToken,
) {
    let mut interval = tokio::time::interval(interval_dur);
    interval.tick().await;
    loop {
        let trigger_label: &'static str = tokio::select! {
            biased;
            _ = cancel.cancelled() => {
                info!(
                    "F6 PH5-WIRE-1 RELOAD: reloader daemon shutting down on cancel \
                     / Edge 重載 daemon 收到 cancel 退出"
                );
                break;
            }
            _ = interval.tick() => "periodic",
            recv_result = signal_rx.recv() => {
                if recv_result.is_none() {
                    warn!(
                        "F6 PH5-WIRE-1 RELOAD: manual signal channel closed — \
                         continuing periodic reload only \
                         / 手動 signal channel 已關閉 — 僅以週期重載繼續運行"
                    );
                    let (_dead_tx, dead_rx) = tokio::sync::mpsc::channel::<()>(1);
                    signal_rx = dead_rx;
                    continue;
                }
                "manual"
            }
        };
        dispatch_reload_command(&paper_cmd_tx, &demo_cmd_slot, &live_cmd_slot, trigger_label);
    }
}

/// EN: Fan-out helper — sends `ReloadEdgeEstimates` to each bound `cmd_tx`.
/// 中: Fan-out 工具函式 — 對每個綁定 `cmd_tx` 發送 `ReloadEdgeEstimates`。
///
/// WP-13-LEFTOVER-1 (2026-05-16)：demo 與 live 皆採 slot 路徑（每次讀快照），
/// paper 沿用 by-value（paper 預設關 + 無 paper slot 基礎設施，不擴 scope）。
fn dispatch_reload_command(
    paper_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    demo_cmd_slot: &Option<DemoCmdSenderSlot>,
    live_cmd_slot: &Option<LiveCmdSenderSlot>,
    trigger: &'static str,
) {
    let paper_ok = try_send_reload(paper_cmd_tx, "paper");
    let demo_ok = try_send_reload_from_demo_slot(demo_cmd_slot);
    let live_ok = try_send_reload_from_slot(live_cmd_slot);
    info!(
        trigger,
        paper_ok,
        demo_ok,
        live_ok,
        "F6 PH5-WIRE-1 RELOAD: dispatch fan-out / 重載 fan-out 派發完成"
    );
}

/// WP-13-LEFTOVER-1 (2026-05-16)：從 demo slot 讀最新 sender 後嘗試發送
/// `ReloadEdgeEstimates`。Slot 未接 / 為 None / channel 關閉皆回 false（不 panic）。
/// 結構對齊 `try_send_reload_from_slot`（live）以保持 fan-out 三引擎對稱。
fn try_send_reload_from_demo_slot(demo_cmd_slot: &Option<DemoCmdSenderSlot>) -> bool {
    let Some(slot) = demo_cmd_slot.as_ref() else {
        return false;
    };
    let tx = slot.read().clone();
    try_send_reload(&tx, "demo")
}

fn try_send_reload_from_slot(live_cmd_slot: &Option<LiveCmdSenderSlot>) -> bool {
    let Some(slot) = live_cmd_slot.as_ref() else {
        return false;
    };
    let tx = slot.read().clone();
    try_send_reload(&tx, "live")
}

/// EN: Single-pipeline send helper. Returns true on accept, false on
///   not-bound or channel closed (warned). `unbounded_send` does not block.
/// 中: 單管線發送工具函式。接受回 true，未綁 / channel 關閉回 false。
///   `unbounded_send` 不阻塞。
fn try_send_reload(
    cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    engine: &'static str,
) -> bool {
    let Some(tx) = cmd_tx.as_ref() else {
        return false;
    };
    match tx.send(PipelineCommand::ReloadEdgeEstimates) {
        Ok(()) => true,
        Err(e) => {
            warn!(
                engine,
                error = %e,
                "F6 PH5-WIRE-1 RELOAD: send failed (channel closed?) — skipping this engine \
                 / 發送失敗（channel 已關？）— 跳過此引擎"
            );
            false
        }
    }
}

#[cfg(test)]
mod edge_reload_tests {
    use super::*;
    use std::sync::Mutex;

    /// Serialise tests that mutate ENV_EDGE_RELOAD_FLAG / interval env-var.
    /// 序列化會 mutate env 變數的測試。
    static ENV_GUARD: Mutex<()> = Mutex::new(());

    fn make_cmd_channel() -> (
        tokio::sync::mpsc::UnboundedSender<PipelineCommand>,
        tokio::sync::mpsc::UnboundedReceiver<PipelineCommand>,
    ) {
        tokio::sync::mpsc::unbounded_channel()
    }

    /// WP-13-LEFTOVER-1 (2026-05-16)：用既有 sender 構造預填的 demo slot；
    /// 取代測試中先前直接傳 `Some(UnboundedSender<_>)` 的舊路徑。
    fn make_filled_demo_slot(
        tx: tokio::sync::mpsc::UnboundedSender<PipelineCommand>,
    ) -> DemoCmdSenderSlot {
        Arc::new(parking_lot::RwLock::new(Some(tx)))
    }

    #[tokio::test]
    async fn spawner_returns_none_when_env_disabled() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        std::env::remove_var(ENV_EDGE_RELOAD_FLAG);
        let cancel = CancellationToken::new();
        let (paper_tx, _paper_rx) = make_cmd_channel();
        let result = spawn_edge_estimates_reloader_if_enabled(Some(paper_tx), None, None, &cancel);
        assert!(
            result.is_none(),
            "spawner must return None when env-gate is unset"
        );
    }

    #[tokio::test]
    async fn spawner_rejects_non_strict_one_values() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        for val in ["true", "yes", "on", "0", " 1", "1 "] {
            std::env::set_var(ENV_EDGE_RELOAD_FLAG, val);
            let cancel = CancellationToken::new();
            let (paper_tx, _paper_rx) = make_cmd_channel();
            let result =
                spawn_edge_estimates_reloader_if_enabled(Some(paper_tx), None, None, &cancel);
            assert!(
                result.is_none(),
                "spawner must reject env-gate value {:?} (only strict \"1\" enables)",
                val
            );
        }
        std::env::remove_var(ENV_EDGE_RELOAD_FLAG);
    }

    #[tokio::test]
    async fn spawner_returns_none_when_no_pipelines_bound() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        std::env::set_var(ENV_EDGE_RELOAD_FLAG, "1");
        let cancel = CancellationToken::new();
        let result = spawn_edge_estimates_reloader_if_enabled(None, None, None, &cancel);
        assert!(
            result.is_none(),
            "spawner must return None when no cmd_tx bound (env=1)"
        );
        std::env::remove_var(ENV_EDGE_RELOAD_FLAG);
    }

    #[tokio::test]
    async fn spawner_returns_sender_when_enabled_with_pipeline() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        std::env::set_var(ENV_EDGE_RELOAD_FLAG, "1");
        std::env::set_var(ENV_EDGE_RELOAD_INTERVAL_SECS, "60");
        let cancel = CancellationToken::new();
        let (demo_tx, _demo_rx) = make_cmd_channel();
        let demo_slot = make_filled_demo_slot(demo_tx);
        let result = spawn_edge_estimates_reloader_if_enabled(None, Some(demo_slot), None, &cancel);
        assert!(result.is_some(), "spawner must return Some when enabled");
        cancel.cancel();
        tokio::task::yield_now().await;
        std::env::remove_var(ENV_EDGE_RELOAD_FLAG);
        std::env::remove_var(ENV_EDGE_RELOAD_INTERVAL_SECS);
    }

    #[tokio::test]
    async fn manual_trigger_fans_out_to_bound_pipelines() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        std::env::set_var(ENV_EDGE_RELOAD_FLAG, "1");
        std::env::set_var(ENV_EDGE_RELOAD_INTERVAL_SECS, "3600");
        let cancel = CancellationToken::new();
        let (demo_tx, mut demo_rx) = make_cmd_channel();
        let (live_tx, mut live_rx) = make_cmd_channel();
        let demo_slot = make_filled_demo_slot(demo_tx);
        let live_slot: LiveCmdSenderSlot = Arc::new(parking_lot::RwLock::new(Some(live_tx)));
        let signal_tx = spawn_edge_estimates_reloader_if_enabled(
            None,
            Some(demo_slot),
            Some(live_slot),
            &cancel,
        )
        .expect("daemon spawned");

        signal_tx.try_send(()).expect("trigger fits buffer-1");

        let demo_msg = tokio::time::timeout(Duration::from_secs(2), demo_rx.recv())
            .await
            .expect("demo recv didn't time out")
            .expect("demo recv yielded a message");
        let live_msg = tokio::time::timeout(Duration::from_secs(2), live_rx.recv())
            .await
            .expect("live recv didn't time out")
            .expect("live recv yielded a message");
        assert!(matches!(demo_msg, PipelineCommand::ReloadEdgeEstimates));
        assert!(matches!(live_msg, PipelineCommand::ReloadEdgeEstimates));

        cancel.cancel();
        tokio::task::yield_now().await;
        std::env::remove_var(ENV_EDGE_RELOAD_FLAG);
        std::env::remove_var(ENV_EDGE_RELOAD_INTERVAL_SECS);
    }

    /// WP-13-LEFTOVER-1 (2026-05-16) 回歸防禦：證明 demo slot 改 by-value
    /// → slot 後，pipeline restart 後新 sender 被 reloader 即時讀到。場景：
    /// 1. spawn daemon 時 demo slot 為 None，paper 為唯一綁定
    /// 2. 後續寫入 demo slot（模擬 pipeline 之後 attach / 或 restart 重綁）
    /// 3. trigger 後 demo 收到 ReloadEdgeEstimates（並非 boot-time 值捕獲）
    #[tokio::test]
    async fn manual_trigger_reads_demo_slot_dynamically() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        std::env::set_var(ENV_EDGE_RELOAD_FLAG, "1");
        std::env::set_var(ENV_EDGE_RELOAD_INTERVAL_SECS, "3600");
        let cancel = CancellationToken::new();
        let (paper_tx, mut paper_rx) = make_cmd_channel();
        // demo slot 啟動時為空；後續注入新 sender 模擬 pipeline restart。
        let demo_slot: DemoCmdSenderSlot = Arc::new(parking_lot::RwLock::new(None));
        let signal_tx = spawn_edge_estimates_reloader_if_enabled(
            Some(paper_tx),
            Some(Arc::clone(&demo_slot)),
            None,
            &cancel,
        )
        .expect("daemon spawned");

        let (demo_tx, mut demo_rx) = make_cmd_channel();
        *demo_slot.write() = Some(demo_tx);

        signal_tx.try_send(()).expect("trigger fits buffer-1");

        let paper_msg = tokio::time::timeout(Duration::from_secs(2), paper_rx.recv())
            .await
            .expect("paper recv didn't time out")
            .expect("paper recv yielded a message");
        let demo_msg = tokio::time::timeout(Duration::from_secs(2), demo_rx.recv())
            .await
            .expect("demo recv didn't time out")
            .expect("demo recv yielded a message");
        assert!(matches!(paper_msg, PipelineCommand::ReloadEdgeEstimates));
        assert!(matches!(demo_msg, PipelineCommand::ReloadEdgeEstimates));

        cancel.cancel();
        tokio::task::yield_now().await;
        std::env::remove_var(ENV_EDGE_RELOAD_FLAG);
        std::env::remove_var(ENV_EDGE_RELOAD_INTERVAL_SECS);
    }

    /// WP-13-LEFTOVER-1 (2026-05-16) 回歸防禦：demo slot 未接時
    /// `try_send_reload_from_demo_slot` 必回 false（fail-safe）。
    #[test]
    fn try_send_reload_from_demo_slot_returns_false_when_unbound() {
        let result = try_send_reload_from_demo_slot(&None);
        assert!(!result, "demo slot 未接時必回 false");
    }

    /// WP-13-LEFTOVER-1 (2026-05-16) 回歸防禦：demo slot 為 Some 但內層 None
    /// （pipeline 尚未綁 / teardown 中）時必回 false。
    #[test]
    fn try_send_reload_from_demo_slot_returns_false_when_inner_none() {
        let demo_slot: DemoCmdSenderSlot = Arc::new(parking_lot::RwLock::new(None));
        let result = try_send_reload_from_demo_slot(&Some(demo_slot));
        assert!(!result, "demo slot 內層 None 時必回 false");
    }

    #[tokio::test]
    async fn manual_trigger_reads_live_slot_dynamically() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        std::env::set_var(ENV_EDGE_RELOAD_FLAG, "1");
        std::env::set_var(ENV_EDGE_RELOAD_INTERVAL_SECS, "3600");
        let cancel = CancellationToken::new();
        let (paper_tx, mut paper_rx) = make_cmd_channel();
        let live_slot: LiveCmdSenderSlot = Arc::new(parking_lot::RwLock::new(None));
        let signal_tx = spawn_edge_estimates_reloader_if_enabled(
            Some(paper_tx),
            None,
            Some(Arc::clone(&live_slot)),
            &cancel,
        )
        .expect("daemon spawned");

        let (live_tx, mut live_rx) = make_cmd_channel();
        *live_slot.write() = Some(live_tx);

        signal_tx.try_send(()).expect("trigger fits buffer-1");

        let paper_msg = tokio::time::timeout(Duration::from_secs(2), paper_rx.recv())
            .await
            .expect("paper recv didn't time out")
            .expect("paper recv yielded a message");
        let live_msg = tokio::time::timeout(Duration::from_secs(2), live_rx.recv())
            .await
            .expect("live recv didn't time out")
            .expect("live recv yielded a message");
        assert!(matches!(paper_msg, PipelineCommand::ReloadEdgeEstimates));
        assert!(matches!(live_msg, PipelineCommand::ReloadEdgeEstimates));

        cancel.cancel();
        tokio::task::yield_now().await;
        std::env::remove_var(ENV_EDGE_RELOAD_FLAG);
        std::env::remove_var(ENV_EDGE_RELOAD_INTERVAL_SECS);
    }

    #[tokio::test]
    async fn manual_trigger_coalesces_rapid_requests() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        std::env::set_var(ENV_EDGE_RELOAD_FLAG, "1");
        std::env::set_var(ENV_EDGE_RELOAD_INTERVAL_SECS, "3600");
        let cancel = CancellationToken::new();
        let (demo_tx, mut demo_rx) = make_cmd_channel();
        let demo_slot = make_filled_demo_slot(demo_tx);
        let signal_tx =
            spawn_edge_estimates_reloader_if_enabled(None, Some(demo_slot), None, &cancel)
                .expect("daemon spawned");

        let first = signal_tx.try_send(());
        assert!(first.is_ok(), "first trigger fits");
        for _ in 0..4 {
            let attempt = signal_tx.try_send(());
            assert!(
                matches!(
                    attempt,
                    Err(tokio::sync::mpsc::error::TrySendError::Full(_))
                ),
                "subsequent rapid trigger must coalesce (Full)"
            );
        }

        let msg = tokio::time::timeout(Duration::from_secs(2), demo_rx.recv())
            .await
            .expect("recv didn't time out")
            .expect("got message");
        assert!(matches!(msg, PipelineCommand::ReloadEdgeEstimates));

        let second = tokio::time::timeout(Duration::from_millis(150), demo_rx.recv()).await;
        assert!(
            second.is_err(),
            "rapid trigger must not produce >=2 fan-outs"
        );

        cancel.cancel();
        tokio::task::yield_now().await;
        std::env::remove_var(ENV_EDGE_RELOAD_FLAG);
        std::env::remove_var(ENV_EDGE_RELOAD_INTERVAL_SECS);
    }

    #[test]
    fn try_send_reload_returns_false_on_closed_channel() {
        let (tx, rx) = make_cmd_channel();
        drop(rx);
        let result = try_send_reload(&Some(tx), "demo");
        assert!(
            !result,
            "try_send_reload must return false when receiver dropped"
        );
    }

    #[test]
    fn try_send_reload_returns_false_when_unbound() {
        let result = try_send_reload(&None, "live");
        assert!(!result, "unbound cmd_tx must yield false");
    }

    #[test]
    fn resolve_reload_interval_respects_env_override() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        std::env::set_var(ENV_EDGE_RELOAD_INTERVAL_SECS, "300");
        let interval = resolve_reload_interval();
        assert_eq!(interval, Duration::from_secs(300));
        std::env::remove_var(ENV_EDGE_RELOAD_INTERVAL_SECS);
    }

    #[test]
    fn resolve_reload_interval_floors_below_minimum() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        for sub_floor in ["0", "1", "30", "59"] {
            std::env::set_var(ENV_EDGE_RELOAD_INTERVAL_SECS, sub_floor);
            let interval = resolve_reload_interval();
            assert_eq!(
                interval, DEFAULT_EDGE_RELOAD_INTERVAL,
                "sub-floor {:?} must fall back to default",
                sub_floor
            );
        }
        std::env::remove_var(ENV_EDGE_RELOAD_INTERVAL_SECS);
    }

    #[test]
    fn resolve_reload_interval_falls_back_on_garbage() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        std::env::set_var(ENV_EDGE_RELOAD_INTERVAL_SECS, "not_a_number");
        let interval = resolve_reload_interval();
        assert_eq!(interval, DEFAULT_EDGE_RELOAD_INTERVAL);
        std::env::remove_var(ENV_EDGE_RELOAD_INTERVAL_SECS);
    }

    #[test]
    fn is_edge_reload_enabled_strict_one_only() {
        let _guard = ENV_GUARD.lock().expect("env guard not poisoned");
        std::env::set_var(ENV_EDGE_RELOAD_FLAG, "1");
        assert!(is_edge_reload_enabled());
        for val in ["true", "0", "yes", " 1", "1 ", ""] {
            std::env::set_var(ENV_EDGE_RELOAD_FLAG, val);
            assert!(!is_edge_reload_enabled(), "value {:?} must be off", val);
        }
        std::env::remove_var(ENV_EDGE_RELOAD_FLAG);
        assert!(!is_edge_reload_enabled());
    }
}
