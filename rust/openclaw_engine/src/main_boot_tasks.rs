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
use openclaw_engine::ipc_server::PerEngineRiskStores;
use openclaw_engine::scanner::registry::SymbolRegistry;
use openclaw_engine::tick_pipeline::PipelineCommand;
use std::sync::Arc;
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
    live_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    demo_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    mirrors: &PositionsMirrors,
) {
    let (paper_mirror, demo_mirror, live_mirror) = mirrors;
    // ORPHAN-ADOPT-1 Phase 1: build per-engine OrphanHandlerConfig. Each
    // engine's reconciler gets its own closure reading max_order_notional_usdt
    // from the matching per-engine RiskConfig store; scanner universe and
    // edge estimates are shared (production pool).
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

    if let Some(ref live_b) = live_bindings {
        if let Some(ref tx) = live_cmd_tx {
            tasks::spawn_position_reconciler(
                &live_b.rest_client,
                db_pool,
                cancel,
                tx.clone(),
                shared_instruments,
                &live_b.risk_level,
                live_b.env,
                Some(build_orphan_cfg("live")),
            );
            info!("position_reconciler spawned for Live / Live 持倉對帳器已啟動");
        }
    }
    if let Some(ref demo_b) = demo_bindings {
        if let Some(ref tx) = demo_cmd_tx {
            tasks::spawn_position_reconciler(
                &demo_b.rest_client,
                db_pool,
                cancel,
                tx.clone(),
                shared_instruments,
                &demo_b.risk_level,
                demo_b.env,
                Some(build_orphan_cfg("demo")),
            );
            info!("position_reconciler spawned for Demo / Demo 持倉對帳器已啟動");
        }
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
    live_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    risk_stores: &PerEngineRiskStores,
) {
    let Some(demo_tx) = demo_cmd_tx.as_ref() else {
        info!(
            "StrategistScheduler not spawned — Demo engine not bound \
             / Demo 引擎未綁定，策略師排程器未啟動"
        );
        return;
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
    let restored = match openclaw_engine::strategist_scheduler::load_latest_applied_params(
        db_pool, demo_mode,
    )
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
    let scheduler = Arc::new(
        openclaw_engine::strategist_scheduler::StrategistScheduler::new(
            ai_client,
            demo_tx.clone(),
            openclaw_engine::tick_pipeline::PipelineKind::Demo,
            live_cmd_tx.clone(),
            Arc::clone(db_pool),
            cancel.clone(),
        )
        .with_risk_store(Arc::clone(&risk_stores.demo)),
    );
    tokio::spawn(scheduler.run_forever());
    info!(
        has_live_promote = live_cmd_tx.is_some(),
        "StrategistScheduler spawned — tune_target=Demo / 策略師排程器已啟動（調諧目標=Demo）",
    );
}
