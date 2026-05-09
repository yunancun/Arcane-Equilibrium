//! OpenClaw Engine entry point — tokio runtime, signal handling, startup/shutdown (R01-2).
//! OpenClaw 引擎入口 — tokio 運行時、信號處理、啟動/關閉序列。
//!
//! MODULE_NOTE (EN): Sets up multi-thread tokio runtime for IPC + WS + background tasks.
//!   SIGHUP triggers config hot-reload. SIGTERM/SIGINT triggers graceful shutdown.
//!   Event consumer feeds PriceEvents into TickPipeline for paper trading.
//! MODULE_NOTE (中): 設置多線程 tokio 運行時用於 IPC + WS + 後台任務。
//!   SIGHUP 觸發配置熱加載。SIGTERM/SIGINT 觸發優雅關閉。
//!   事件消費者將 PriceEvent 送入 TickPipeline 進行紙盤交易。

mod cost_edge_advisor_boot;
mod live_auth_watcher;
mod main_boot_tasks;
mod main_fanout;
mod main_instruments;
mod main_pipelines;
mod main_scanner_init;
mod main_shutdown;
mod main_watchdog;
mod main_ws;
mod pipeline_slot;
mod spawn_backoff;
mod startup;
mod tasks;

use openclaw_engine::bybit_rest_client::{live_bybit_environment, BybitEnvironment};
use openclaw_engine::config::{ConfigManager, ConfigStore};
use openclaw_engine::ipc_server::{
    EngineCommandChannels, IpcServer, LiveCmdSenderSlot, PerEngineRiskStores,
};
use openclaw_engine::market_data_client::MarketDataClient;
use openclaw_engine::scanner::runner::ScannerRunner;
use openclaw_engine::scanner::ScannerStrategyPolicyStores;
use openclaw_engine::secret_env;
use openclaw_engine::tick_pipeline::{EngineEvent, PipelineHealth, PipelineKind};
use openclaw_types::PriceEvent;
use parking_lot::{Mutex as ParkingMutex, RwLock as ParkingRwLock};
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{error, info, warn};

use startup::*;

// SYMBOLS moved to event_consumer.rs (Phase 1 Day 0-A extraction)
// STATUS_INTERVAL_SECS moved to event_consumer.rs

// ----------------------------------------------------------------------
// Crash-only pipeline wrapper / crash-only 管線包裝器
// ----------------------------------------------------------------------
// EN: Wraps an async pipeline Future so that an unwind panic is caught,
//   logged with panic payload, broadcast as EngineEvent::Crashed, and then
//   cancels the engine CancellationToken. We explicitly DO NOT try to
//   "isolate and keep running" the survivors because a panicked pipeline
//   may have left shared state (positions, reconciler baselines, account
//   snapshots) in an inconsistent state. Crash-only software: die cleanly,
//   let the external watchdog restart from a known-good boot.
//   Used by Paper + Demo pipelines running on the main tokio runtime.
//   Live pipeline has its own sync catch_unwind layer on a dedicated OS
//   thread (see L877+) and calls cancel.cancel() after the broadcast.
// 中: 包裝 async 管線 Future，捕獲 unwind panic 後：記 log + 廣播
//   EngineEvent::Crashed + 取消引擎 CancellationToken。我們**不**嘗試「隔離
//   倖存者繼續跑」，因為 panic 管線可能使共享狀態（倉位、reconciler 基線、
//   帳戶快照）進入不一致狀態。Crash-only software：乾淨死亡，讓外部 watchdog
//   從已知良好啟動點重啟。Paper + Demo 管線（共用主 tokio runtime）使用此函
//   數；Live 在獨立 OS 線程上有自己的 sync catch_unwind 層（見 L877+），也會
//   在廣播後呼叫 cancel.cancel()。
pub(crate) async fn run_pipeline_crash_only<F>(
    kind: PipelineKind,
    fut: F,
    health: Arc<std::sync::atomic::AtomicU8>,
    crash_tx: tokio::sync::broadcast::Sender<EngineEvent>,
    cancel: CancellationToken,
) where
    F: std::future::Future<Output = ()>,
{
    use futures_util::FutureExt;
    let result = std::panic::AssertUnwindSafe(fut).catch_unwind().await;
    if let Err(panic_info) = result {
        let msg = panic_info
            .downcast_ref::<&str>()
            .copied()
            .or_else(|| panic_info.downcast_ref::<String>().map(|s| s.as_str()))
            .unwrap_or("unknown panic payload");
        tracing::error!(
            target: "openclaw_engine::panic",
            kind = ?kind,
            panic = msg,
            "pipeline PANICKED (crash-only) — broadcasting Crashed + cancelling engine / \
             管線 panic（crash-only）— 廣播 Crashed + 取消引擎"
        );
        health.store(
            PipelineHealth::Down as u8,
            std::sync::atomic::Ordering::Relaxed,
        );
        let _ = crash_tx.send(EngineEvent::Crashed(kind));
        // Crash-only trigger: cancel the entire engine so watchdog restarts
        // from a clean state. A Down pipeline while others keep running is
        // exactly the "zombie 18-min" failure mode we are fixing.
        // Crash-only 觸發：取消整個引擎，讓 watchdog 從乾淨狀態重啟。一條管線
        // Down 但其他繼續跑正是我們要修的「殭屍 18 分鐘」故障模式。
        cancel.cancel();
    }
}

fn main() {
    // ------------------------------------------------------------------
    // 0. Install rustls crypto provider / 安裝 rustls 加密提供者
    // ------------------------------------------------------------------
    rustls::crypto::ring::default_provider()
        .install_default()
        .expect("failed to install rustls crypto provider");

    // ------------------------------------------------------------------
    // 1. Initialize tracing / 初始化日誌追蹤
    // ------------------------------------------------------------------
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info")),
        )
        .with_target(true)
        .with_thread_ids(true)
        .init();

    // ------------------------------------------------------------------
    // 1a. Install panic hook / 安裝 panic 捕獲 hook
    // ------------------------------------------------------------------
    // EN: Captures any unwind panic and writes it to tracing with backtrace
    //   before the process dies. Without this hook, tokio task panics die
    //   silently — the 2026-04-14 incident (engine dead 18 min, no log trace)
    //   was root-caused to this gap. Covers main thread + tokio task panics
    //   that unwind to the runtime. Does NOT cover abort(), SIGKILL, or OOM.
    // 中: 捕獲所有 unwind panic 並在進程死亡前寫入 tracing + backtrace。沒有此
    //   hook，tokio task panic 會靜默死亡 — 2026-04-14 引擎死亡 18 分鐘無日誌
    //   痕跡的根因就是這個缺口。覆蓋主執行緒 + unwind 到 runtime 的 tokio task
    //   panic。不覆蓋 abort()、SIGKILL、OOM。
    std::panic::set_hook(Box::new(|info| {
        let backtrace = std::backtrace::Backtrace::force_capture();
        let location = info
            .location()
            .map(|l| format!("{}:{}:{}", l.file(), l.line(), l.column()))
            .unwrap_or_else(|| "<unknown>".to_string());
        let payload = info
            .payload()
            .downcast_ref::<&str>()
            .map(|s| s.to_string())
            .or_else(|| info.payload().downcast_ref::<String>().cloned())
            .unwrap_or_else(|| "<non-string panic payload>".to_string());
        tracing::error!(
            target: "openclaw_engine::panic",
            thread = ?std::thread::current().id(),
            thread_name = std::thread::current().name().unwrap_or("<unnamed>"),
            location = %location,
            payload = %payload,
            backtrace = %backtrace,
            "PANIC captured / panic 已捕獲",
        );
        // Force flush so the tracing write lands on disk before the process
        // aborts or is restarted. tracing_subscriber uses stdout (redirected
        // to engine.log by restart_all.sh), which is fully buffered when the
        // target is a file.
        // 強制 flush 確保 tracing 寫入在進程 abort 或被重啟前落盤。
        // tracing_subscriber 使用 stdout（由 restart_all.sh 重定向至 engine.log），
        // 目標為檔案時為全緩衝。
        use std::io::Write;
        let _ = std::io::stdout().flush();
        let _ = std::io::stderr().flush();
    }));

    print_banner();

    // ------------------------------------------------------------------
    // 1b. Check for replay mode / 檢查是否為回放模式
    // ------------------------------------------------------------------
    let replay_args = parse_replay_args();
    if replay_args.enabled {
        info!("replay mode activated / 回放模式已啟用");
        run_replay_mode(replay_args);
        return;
    }

    // ------------------------------------------------------------------
    // 1c. PIPELINE-SLOT-1 Phase 1: consume the restart-kind sentinel written
    //     by `restart_all.sh`. On Manual restart we clear authorization.json
    //     so Operator must re-approve Live after any operator-initiated
    //     push. Crashes / watchdog / systemd auto-restarts do NOT run the
    //     script and therefore do NOT clear the authorization.
    // 1c. PIPELINE-SLOT-1 Phase 1：消費 `restart_all.sh` 寫入的 sentinel。
    //     手動重啟會清空 authorization.json，強迫 operator 每次手動推送後
    //     重新批准 Live。崩潰 / watchdog / systemd 自動重啟不會跑該 shell，
    //     也不會清授權。
    // ------------------------------------------------------------------
    let _restart_kind = startup::consume_restart_sentinel_and_clear_live_auth_if_manual();

    // ------------------------------------------------------------------
    // 2. Load engine bootstrap config (EngineBootstrap from engine.toml)
    //    加載引擎啟動配置
    // ------------------------------------------------------------------
    let config = match ConfigManager::load(None) {
        Ok(c) => Arc::new(c),
        Err(e) => {
            error!(error = %e, "failed to load config / 配置加載失敗");
            std::process::exit(1);
        }
    };

    // ------------------------------------------------------------------
    // 2b. ARCH-RC1 1C-2: Load 3 unified Configs and wrap in ConfigStores.
    //     ARCH-RC1 1C-2：載入 3 個統一 Config 並包入 ConfigStore。
    // ------------------------------------------------------------------
    let (risk_stores, learning_store, budget_store) = match load_unified_configs() {
        Ok(s) => s,
        Err(e) => {
            error!(error = %e, "failed to load unified configs / 統一配置加載失敗");
            std::process::exit(1);
        }
    };
    // learning_store is consumed by the A2 news pipeline scheduler (hot-reload gate).
    // learning_store 由 A2 新聞管線排程器使用（熱重載 gate）。
    let _learning_store_held = Arc::clone(&learning_store);

    // ------------------------------------------------------------------
    // 3. Build multi-thread runtime / 構建多線程運行時
    // ------------------------------------------------------------------
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .thread_name("oc-engine")
        .build()
        .expect("failed to build tokio runtime / 構建 tokio 運行時失敗");

    runtime.block_on(async_main(
        config,
        risk_stores,
        learning_store,
        budget_store,
    ));
}

/// Async entry point running inside the multi-thread runtime.
/// 在多線程運行時內執行的異步入口。
async fn async_main(
    config: Arc<ConfigManager>,
    risk_stores: PerEngineRiskStores,
    learning_store: Arc<ConfigStore<openclaw_engine::config::LearningConfig>>,
    budget_store: Arc<ConfigStore<openclaw_engine::config::BudgetConfig>>,
) {
    let cancel = CancellationToken::new();

    // ------------------------------------------------------------------
    // Scanner D4: pre-init extracted to `main_scanner_init.rs` (MAIN-RS-PRE-
    //   EXISTING-CLEANUP P2, 2026-04-28). Loads ScannerConfig (fail-soft →
    //   defaults), builds ConfigStore + SymbolRegistry seeded with pinned
    //   symbols, loads EdgeEstimates, sets up persistent ScannerRunner→
    //   WsClient relay channel + spawns relay task.
    // 掃描器 D4：前置初始化已抽至 `main_scanner_init.rs`（MAIN-RS-PRE-
    //   EXISTING-CLEANUP P2，2026-04-28）。詳見該 sibling 模組。
    // ------------------------------------------------------------------
    let main_scanner_init::ScannerInitBundle {
        scanner_store,
        symbol_registry,
        edge_estimates: scanner_edge_estimates,
        ws_topic_change_tx: scanner_ws_tx,
        current_ws_client_tx,
    } = main_scanner_init::init_scanner();

    // ------------------------------------------------------------------
    // Price event channel / 價格事件通道
    // ------------------------------------------------------------------
    let (event_tx, event_rx) = mpsc::channel::<PriceEvent>(EVENT_CHANNEL_SIZE);

    // ------------------------------------------------------------------
    // 3E-ARCH: Build exchange pipeline bindings independently (D1).
    // Paper always starts. Demo/Live start if their API keys exist.
    // 3E-ARCH：獨立構建每條交易所管線綁定（D1）。
    // Paper 始終啟動。Demo/Live 依 API key 存在性獨立啟動。
    // ------------------------------------------------------------------
    let cfg_snapshot_pipelines = config.get();
    // PIPELINE-SLOT-1 Phase 2: each slot owns a slot-scoped child cancel token
    // (not engine-wide) so LiveAuthWatcher teardown cancels the event-consumer
    // main loop without collateral damage to demo/paper.
    // Phase 2：槽位持有 slot-scoped 子 token，teardown 只取消目標管線。
    let live_slot = Arc::new(pipeline_slot::PipelineSlot::new_empty(
        pipeline_slot::SlotKind::Live,
    ));
    let demo_slot = Arc::new(pipeline_slot::PipelineSlot::new_empty(
        pipeline_slot::SlotKind::Demo,
    ));
    // Boot tries Live try_spawn; if authorized, direct spawn path follows.
    // Watcher handles (None, None) + mid-session respawn. (2026-04-27 fix)
    // Boot 嘗試 try_spawn；授權 → 直接 spawn；否則 watcher 接管。
    let (live_bindings, live_slot_cancel) = match live_slot
        .try_spawn(&pipeline_slot::SpawnConfig {
            kind: pipeline_slot::SlotKind::Live,
            env: live_bybit_environment(),
            parent_shutdown_token: cancel.clone(),
            cfg_snapshot: &cfg_snapshot_pipelines,
        })
        .await
    {
        Ok(Some(out)) => (Some(out.bindings), Some(out.slot_cancel_token)),
        Ok(None) => (None, None),
        // AlreadySpawned cannot happen — we just created the slot. Any future
        // SpawnError variant is treated as "build_exchange_pipeline returned
        // None": log structured, continue without Live.
        Err(e) => {
            tracing::error!(error = %e, "live slot spawn errored unexpectedly / live 槽啟動錯誤");
            (None, None)
        }
    };
    let (demo_bindings, demo_slot_cancel) = match demo_slot
        .try_spawn(&pipeline_slot::SpawnConfig {
            kind: pipeline_slot::SlotKind::Demo,
            env: BybitEnvironment::Demo,
            parent_shutdown_token: cancel.clone(),
            cfg_snapshot: &cfg_snapshot_pipelines,
        })
        .await
    {
        Ok(Some(out)) => (Some(out.bindings), Some(out.slot_cancel_token)),
        Ok(None) => (None, None),
        Err(e) => {
            tracing::error!(error = %e, "demo slot spawn errored unexpectedly / demo 槽啟動錯誤");
            (None, None)
        }
    };
    // PIPELINE-SLOT-1 Phase 2/3: Hold slot Arcs for the Live auth watcher
    // (Live only) AND for the ordered shutdown sequence — both `live_slot`
    // and `demo_slot` are torn down explicitly after the engine-wide cancel
    // so their owned task handles (WS supervisor / listener / balance refresh)
    // join deterministically instead of relying on tokio-runtime drop to abort
    // them. E2 MAJOR #3 fix: Phase 2 teardown() promises "clean shutdown" — we
    // must actually invoke it at engine-wide shutdown, not just on auth revoke.
    // Paper is NOT yet wired through PipelineSlot (future deferral).
    //
    // PIPELINE-SLOT-1 Phase 2：保留兩個 slot 的 Arc — Live slot 供 5 分鐘授權
    // 重驗 loop 使用，**兩者**都在關機時顯式呼叫 `teardown()` 以確定性 join
    // 槽位擁有的任務 handle，不依賴 tokio runtime drop 粗暴中止。E2 MAJOR #3
    // 修復：Phase 2 teardown() 承諾「乾淨關閉」 — 引擎關機時必須實際呼叫，
    // 不是僅授權撤銷時呼叫。Paper 尚未接入 PipelineSlot（Phase 3 延後）。
    drop(cfg_snapshot_pipelines);

    // Log pipeline availability / 記錄管線可用性
    info!(
        live = live_bindings.is_some(),
        demo = demo_bindings.is_some(),
        paper = true,
        "3E-ARCH: pipeline availability detected / 管線可用性偵測完成"
    );

    // ------------------------------------------------------------------
    // FIX-10: IPC HMAC mandatory for Live — if Live pipeline is active,
    // OPENCLAW_IPC_SECRET or OPENCLAW_IPC_SECRET_FILE MUST be set. Fail-closed: panic on startup.
    // FIX-10：Live 管線啟動時 IPC HMAC 認證強制——無密鑰直接 panic。
    // ------------------------------------------------------------------
    if live_bindings.is_some() && secret_env::var_or_file("OPENCLAW_IPC_SECRET").is_none() {
        panic!(
            "FATAL: Live pipeline detected but OPENCLAW_IPC_SECRET is not set. \
             IPC HMAC authentication is mandatory for Live trading. \
             Set OPENCLAW_IPC_SECRET_FILE or OPENCLAW_IPC_SECRET before starting with Live credentials. \
             / Live 管線偵測到但 OPENCLAW_IPC_SECRET(_FILE) 未設置。Live 交易必須啟用 IPC HMAC 認證。"
        );
    }

    // ------------------------------------------------------------------
    // Start IPC server / 啟動 IPC 服務器
    // ------------------------------------------------------------------
    let ipc_data_dir =
        std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into());

    // 3E-ARCH: Independent command channels per pipeline.
    // paper/demo: boot-time fixed. live: slot rotated by LiveAuthWatcher.
    // 3E-ARCH：paper/demo boot 固定；live 改 slot 由 LiveAuthWatcher 輪替。
    let (paper_cmd_tx, paper_cmd_rx) = tokio::sync::mpsc::unbounded_channel();
    let (demo_cmd_tx, demo_cmd_rx) = if demo_bindings.is_some() {
        let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };
    // Live command sender slot — populated by the watcher / boot closure
    // path (see `live_pipeline_spawner` later). IPC + scanner / phase4
    // reads via `EngineCommandChannels::live_snapshot()`.
    // Live 命令 sender slot — watcher / boot closure 填入；IPC + scanner /
    // phase4 經 `EngineCommandChannels::live_snapshot()` 讀取。
    let live_cmd_slot: LiveCmdSenderSlot = Arc::new(ParkingRwLock::new(None));

    // Boot-time live command channel: Some if boot authorized, None otherwise.
    // When Some, mirror into live_cmd_slot so IPC/scanner see boot sender.
    // LIVE-RECONCILER-STALE-CMD-TX P1 TODO: reconcilers hold this by-value.
    // Boot-time live 命令通道：授權 → Some（同時寫 slot）；否則 None。
    let (live_cmd_tx, live_cmd_rx) = if live_bindings.is_some() {
        let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
        // Mirror into slot so IPC / scanner / phase4 see the same sender.
        // 寫入 slot，IPC / scanner / phase4 即見。
        *live_cmd_slot.write() = Some(tx.clone());
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };

    let mut engine_cmd_channels = EngineCommandChannels::default();
    engine_cmd_channels.paper = Some(paper_cmd_tx.clone());
    if let Some(ref tx) = demo_cmd_tx {
        engine_cmd_channels.demo = Some(tx.clone());
    }
    // live owned field stays None; live_slot below provides the dynamic
    // snapshot path. Teacher routing clones this bundle but defaults to Demo.
    // owned `live` 留 None；live_slot 提供動態快照路徑。Teacher route clone 此
    // bundle，但默認目標為 Demo。
    engine_cmd_channels.live_slot = Some(Arc::clone(&live_cmd_slot));

    let mut ipc_server = IpcServer::new(
        Arc::clone(&config),
        cancel.clone(),
        ipc_data_dir,
        engine_cmd_channels.clone(),
    );
    ipc_server.set_config_stores(
        risk_stores.clone(),
        Arc::clone(&learning_store),
        Arc::clone(&budget_store),
    );
    ipc_server.set_scanner_registry(Arc::clone(&symbol_registry));

    // Two-stage watcher construction: pre-create IPC trigger handle now
    // (must wire before IPC.run() accepts connections), assemble full watcher
    // later (after writers/Arc bundle ready). See live_auth_watcher::pre_create_trigger.
    // 兩階段 watcher：IPC handle 先接線；full watcher 待 writers 就緒後組裝。
    let (live_auth_trigger_handle, live_auth_ipc_trigger_rx) =
        live_auth_watcher::LiveAuthWatcher::pre_create_trigger();
    ipc_server.set_live_auth_recheck_sender(live_auth_trigger_handle.sender());
    ipc_server.set_live_cmd_sender_slot(Arc::clone(&live_cmd_slot));

    let budget_tracker_slot = ipc_server.budget_tracker_slot();
    let teacher_loop_slot = ipc_server.teacher_loop_slot();
    let audit_pool_slot = ipc_server.audit_pool_slot();
    // G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25): grab the counters
    // slot before detaching IPC server so we can write the scheduler's
    // CycleCounters Arc into it after `spawn_strategist_scheduler` returns
    // below. Mirrors the late-injection pattern used by budget/teacher/audit.
    // G3-11：在 IPC server detach 前取 slot handle，scheduler spawn 後 late-inject counters。
    let strategist_counters_slot = ipc_server.strategist_counters_slot();

    // G3-08 H State Gateway Phase 1 (2026-04-26): gated by
    // OPENCLAW_H_STATE_GATEWAY=1 (DEFAULT-OFF). Must run before IPC detach
    // because set_h_state_invalidation_sender requires &mut self.
    // G3-08：受 OPENCLAW_H_STATE_GATEWAY=1 控管；IPC detach 前完成。
    let h_state_cache_slot_handle = ipc_server.h_state_cache_slot();
    if let Some(h_state_inv_tx) =
        main_boot_tasks::spawn_h_state_poller_if_enabled(&h_state_cache_slot_handle, &cancel)
    {
        ipc_server.set_h_state_invalidation_sender(h_state_inv_tx);
    }

    // G3-09 cost_edge_advisor — see sibling `cost_edge_advisor_boot`
    // for full doc / G3-09 cost_edge_advisor — 詳見 sibling 模組。
    let cost_edge_advisor_slot_handle = ipc_server.cost_edge_advisor_slot();
    let cost_edge_advisor_db_pool_slot = cost_edge_advisor_boot::create_db_pool_slot();
    cost_edge_advisor_boot::spawn_cost_edge_advisor_if_enabled(
        &cost_edge_advisor_slot_handle,
        &h_state_cache_slot_handle,
        &risk_stores,
        &cancel,
        &cost_edge_advisor_db_pool_slot,
    );

    // F6 PH5-WIRE-1 RELOAD (2026-04-26): grab slot handle BEFORE IPC server
    // detaches. main.rs late-injects the daemon's manual-trigger sender
    // after the daemon is spawned (post-detach, pipelines must exist for
    // fan-out). Mirrors `h_state_cache_slot` G3-08 Phase 1 pattern.
    // F6：在 IPC server detach 前取 slot handle，main.rs 在 daemon spawn 後
    // late-inject manual trigger sender。對齊 h_state_cache_slot G3-08 pattern。
    let edge_reload_sender_slot_handle = ipc_server.edge_reload_sender_slot();

    let ipc_handle = tokio::spawn(async move {
        if let Err(e) = ipc_server.run().await {
            error!(error = %e, "IPC server error / IPC 服務器錯誤");
        }
    });

    // 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: Live auth watcher
    // spawn moved further below (after `live_pipeline_spawner` closure is
    // constructed). The watcher receiver was pre-created at the top of
    // this function via `pre_create_trigger`; the IPC handle has been
    // wired since then.
    //
    // 2026-04-27：watcher spawn 下移（待 `live_pipeline_spawner` closure
    // 組好）。Receiver 已於本函式上方 `pre_create_trigger` 預建，IPC
    // handle 也已接好。

    // ------------------------------------------------------------------
    // 3E-ARCH shared REST client + instrument info + fee-rate tasks init —
    // extracted to `main_instruments.rs` (G1-03 Wave 1). Picks highest-
    // priority exchange pipeline (Live > Demo) as shared client; runs
    // INSTR-WIRE-1 fail-closed startup refresh (0 symbols or Err →
    // cancel + 500ms drain + exit(1)); resolves paper balance (MAJOR-4);
    // spawns 4h instrument refresh + fee rate tasks.
    // 3E-ARCH 共享 REST 客戶端 + 品種 + 費率任務初始化 — 抽至
    // `main_instruments.rs`（G1-03 Wave 1）。
    // ------------------------------------------------------------------
    let main_instruments::SharedClientsBundle {
        shared_client,
        shared_account_manager,
        shared_instruments,
        paper_balance,
    } = main_instruments::init_shared_clients_and_instruments(
        &cancel,
        &live_bindings,
        &demo_bindings,
    )
    .await;

    // ------------------------------------------------------------------
    // Public WS supervisor — extracted to `main_ws.rs` (G1-03 Wave 1).
    // Builds subscription list (extended vs minimal) from
    // symbol_registry + config.enable_extended_ws, spawns RE-2 supervisor
    // that auto-restarts WsClient on unexpected exit with exponential
    // backoff. Returns JoinHandle for shutdown sequence.
    // 公有 WS supervisor — 抽至 `main_ws.rs`（G1-03 Wave 1）。
    // 從 registry + `enable_extended_ws` 建初始 topics，spawn RE-2 supervisor
    // 自動重啟 WsClient（指數退避）。
    // ------------------------------------------------------------------
    let ws_handle = main_ws::spawn_ws_supervisor(
        &config,
        &cancel,
        &symbol_registry,
        &current_ws_client_tx,
        event_tx.clone(),
    );

    // ------------------------------------------------------------------
    // Phase 1: Database pool + writer tasks
    // Phase 1：資料庫連接池 + 寫入器任務
    // ------------------------------------------------------------------
    let cfg_snap_db = config.get();
    let db_pool =
        Arc::new(openclaw_engine::database::pool::DbPool::connect(&cfg_snap_db.database).await);

    // G3-09 Phase B late-inject DbPool / G3-09 Phase B：late-inject DbPool。
    cost_edge_advisor_boot::inject_db_pool(&cost_edge_advisor_db_pool_slot, &db_pool).await;

    // Phase 2 (2026-04-24 V023 postmortem): opt-in auto-migrate.
    // Default OFF; set OPENCLAW_AUTO_MIGRATE=1 to run `sql/migrations/V*.sql`
    // through a hand-parsed Migrator before any writer task depends on a
    // specific schema revision. Seeds `_sqlx_migrations` from the canary
    // `learning.model_registry` table when the tracker is empty but V023 has
    // already been applied via the legacy manual `psql < V*.sql` path. Aborts
    // startup on error to make silent-noop classes of bugs loud.
    // 2026-04-24 V023 postmortem 後新加：opt-in 自動遷移。
    // 預設關；設 OPENCLAW_AUTO_MIGRATE=1 才於依賴 schema 的 writer 啟動前
    // 套用 `sql/migrations/V*.sql`（自刻 parser 認 Flyway V###__ 格式）。
    // 若 `_sqlx_migrations` 空而 V023 canary 已建，seed legacy 已套用狀態。
    // 失敗直接中止啟動，讓靜默 noop 類錯誤顯性化。
    {
        let base_dir = std::env::var("OPENCLAW_BASE_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| std::path::PathBuf::from("."));
        match openclaw_engine::database::migrations::MigrationRunner::run_if_enabled(
            db_pool.get(),
            &base_dir,
        )
        .await
        {
            Ok(outcome) => info!(
                ?outcome,
                "auto_migrate runner completed / 自動遷移執行器已完成"
            ),
            Err(e) => {
                error!(
                    error = %e,
                    "auto_migrate runner failed — aborting startup \
                     / 自動遷移失敗，中止啟動"
                );
                std::process::exit(1);
            }
        }
    }

    // Initialize BudgetTracker + audit pool
    tasks::init_budget_and_audit(&db_pool, &budget_tracker_slot, &audit_pool_slot).await;

    // ------------------------------------------------------------------
    // Phase 4: LinUCB runtime + news context snapshot + governance wrappers
    // ------------------------------------------------------------------
    let shared_linucb_runtime =
        openclaw_engine::linucb::LinUcbRuntime::load_active_or_cold_start(db_pool.as_ref()).await;
    info!(
        active_version = shared_linucb_runtime.arm_space_version(),
        feature_schema_hash = shared_linucb_runtime.feature_schema_hash(),
        "LinUcbRuntime initialized / LinUCB runtime 已初始化"
    );

    let shared_news_snapshot = Arc::new(openclaw_engine::news::NewsContextSnapshot::new());
    info!("NewsContextSnapshot constructed (default severity 0.0) / 新聞 context 快照已建立");

    let governance_wrapper = Arc::new(
        openclaw_engine::claude_teacher::GovernanceCoreWrapper::with_defaults(vec![
            "ma_crossover".to_string(),
            "bb_reversion".to_string(),
            "bb_breakout".to_string(),
            "grid_trading".to_string(),
            "funding_arb".to_string(),
        ]),
    );
    let shared_halted_handle = governance_wrapper.halted_handle();
    let guardian_impl = Arc::new(openclaw_engine::news::GuardianHaltCheckImpl::new(
        Arc::clone(&shared_halted_handle),
    ));
    info!("Phase 4 governance+guardian wrappers constructed / W-1/W-2 wrappers 已構造");

    // Phase 4.1: Spawn TeacherConsumerLoop (DEFAULT-OFF)
    tasks::spawn_teacher_consumer_loop(
        &db_pool,
        &budget_tracker_slot,
        teacher_loop_slot,
        engine_cmd_channels.clone(),
        &governance_wrapper,
    )
    .await;
    let _phase4_governance_wrapper = governance_wrapper;

    // A2: NewsPipeline 60s scheduler
    tasks::spawn_news_pipeline(
        &db_pool,
        &learning_store,
        &cancel,
        &shared_news_snapshot,
        guardian_impl,
    );

    // ------------------------------------------------------------------
    // DB writer tasks (market, feature, trading, context, pollers, monitors)
    // ------------------------------------------------------------------
    let shared_last_tick_ms = Arc::new(std::sync::atomic::AtomicU64::new(0));
    let (
        market_tx,
        feature_tx,
        trading_tx,
        context_tx,
        decision_feature_tx,
        // W-AUDIT-4b-M1 split (V082)：candidate evaluation log channel
        decision_feature_evaluation_tx,
        shadow_fill_tx,
        exit_feature_tx,
        shadow_exit_tx,
        agent_spine_tx,
        agent_spine_mode,
    ) = tasks::spawn_db_writers(
        &db_pool,
        &config,
        &cancel,
        &symbol_registry,
        &shared_client,
        &shared_last_tick_ms,
    )
    .await;
    let lease_transition_tx = Some(
        openclaw_engine::database::lease_transition_writer::spawn_lease_transition_pipeline(
            Arc::clone(&db_pool),
            Arc::clone(&config),
            cancel.clone(),
        ),
    );

    // ------------------------------------------------------------------
    // Scanner D4: Spawn ScannerRunner (requires market REST client + DB writer)
    // 掃描器 D4：啟動 ScannerRunner（需要市場 REST 客戶端 + DB writer）
    // ------------------------------------------------------------------
    // 3E-ARCH: Scanner broadcasts AddSymbol/RemoveSymbol to ALL pipelines and
    // persists each scan snapshot for strategy-intent attribution.
    // 掃描器向所有管線廣播 AddSymbol/RemoveSymbol，並持久化每次 scan snapshot。
    if let Some(ref client) = shared_client {
        let scanner_cmd_tx = paper_cmd_tx.clone();
        let market_client = Arc::new(MarketDataClient::new(Arc::clone(client)));
        let runner = ScannerRunner::new(
            Arc::clone(&symbol_registry),
            market_client,
            Arc::clone(&scanner_edge_estimates),
            Arc::clone(&scanner_store),
            shared_account_manager.clone(),
            ScannerStrategyPolicyStores::new(
                Arc::clone(&risk_stores.paper),
                Arc::clone(&risk_stores.demo),
                Arc::clone(&risk_stores.live),
            ),
            scanner_ws_tx,
            scanner_cmd_tx,
            trading_tx.clone(),
            cancel.clone(),
        );
        tokio::spawn(runner.run());
        info!("ScannerRunner spawned / 掃描器已啟動");
    } else {
        warn!("ScannerRunner skipped: no REST client (pinned symbols only) / 掃描器跳過：無 REST 客戶端（僅固定交易對）");
    }

    // ------------------------------------------------------------------
    // Phase 6 + D23 per-exchange position reconciler — extracted to
    // `main_boot_tasks.rs` (G1-03 Wave 1). Builds per-engine positions
    // mirrors (for PaperState view suppression of false-positive Orphans)
    // and spawns per-engine reconcilers with their own RiskConfig closure.
    // Phase 6 + D23 per-exchange 持倉對帳器 — 抽至 `main_boot_tasks.rs`。
    // 建立 per-engine mirror（PaperState 視圖以抑制假 Orphan）+ spawn
    // per-engine reconciler（各自 RiskConfig 閉包）。
    // ------------------------------------------------------------------
    let positions_mirrors = main_boot_tasks::build_positions_mirrors();
    let (paper_positions_mirror, demo_positions_mirror, live_positions_mirror) = (
        Arc::clone(&positions_mirrors.0),
        Arc::clone(&positions_mirrors.1),
        Arc::clone(&positions_mirrors.2),
    );
    main_boot_tasks::spawn_position_reconcilers(
        &db_pool,
        &cancel,
        &risk_stores,
        &symbol_registry,
        &scanner_edge_estimates,
        &shared_instruments,
        &live_bindings,
        &demo_bindings,
        &live_cmd_slot,
        &demo_cmd_tx,
        &positions_mirrors,
    );

    // ------------------------------------------------------------------
    // FIX-34: Decision outcome backfill writer (5min interval).
    // FIX-34：決策結果回填寫入器（5 分鐘間隔）。
    // ------------------------------------------------------------------
    tasks::spawn_outcome_backfiller(&db_pool, &cancel);

    // ------------------------------------------------------------------
    // B0/R3-1 StrategistScheduler — extracted to `main_boot_tasks.rs`
    // (G1-03 Wave 1). Restores last-applied tuned params from DB
    // (STRATEGIST-PARAMS-PERSIST-1, 2026-04-23) then spawns the single
    // scheduler tokio task (tune_target=Demo, optional live_promote).
    // B0/R3-1 StrategistScheduler — 抽至 `main_boot_tasks.rs`。
    // 從 DB 恢復 last-applied tuned params 後 spawn scheduler。
    // ------------------------------------------------------------------
    let strategist_counters = main_boot_tasks::spawn_strategist_scheduler(
        &db_pool,
        &cancel,
        &demo_cmd_tx,
        &live_cmd_slot,
        &risk_stores,
    )
    .await;
    // G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1: late-inject the scheduler's
    // shared `CycleCounters` Arc into the IPC slot. `None` means scheduler
    // wasn't spawned (Demo unbound) — slot stays empty and IPC method
    // returns `{"status":"scheduler_unavailable"}` (fail-soft).
    // G3-11：scheduler counters Arc 寫入 IPC slot；None 則 IPC 回 scheduler_unavailable。
    if let Some(counters) = strategist_counters {
        strategist_counters_slot.write().await.replace(counters);
    }

    // ------------------------------------------------------------------
    // 3E-ARCH: Three-pipeline fan-out + independent spawn
    // (Deps + run_event_consumer now consumed inside `main_pipelines.rs`.)
    // 3E-ARCH：三管線扇出 + 獨立 spawn（Deps + run_event_consumer 在
    // `main_pipelines.rs` 內部消費）。
    // ------------------------------------------------------------------

    // ENGINE-HEAL-FIX-PHASE1 R1: Spawn the dedicated canary writer task once.
    // Returns a clonable handle; each pipeline gets a clone. When the feature
    // is off the handle is a cheap no-op (`is_enabled() == false`) so producers
    // skip record build entirely. Reads OPENCLAW_CANARY_MODE / DISABLE_CANARY_DUMP
    // / CANARY_ROTATE_MB / CANARY_MAX_ROTATED at spawn time.
    // ENGINE-HEAL-FIX-PHASE1 R1：啟動單一專用灰度寫入任務，回傳 clonable handle，
    // 每條管線 clone 一份。功能關閉時為廉價 no-op，producer 直接跳過記錄構建。
    let canary_data_path = std::path::PathBuf::from(
        std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into()),
    );
    let canary_handle = openclaw_engine::canary_writer::spawn(canary_data_path, cancel.clone());

    // EDGE-P3-1 Phase B #1: Per-engine EdgePredictorStore. One container, three
    // Arc<EdgePredictorStore> slots (paper/demo/live). Each pipeline receives
    // exactly one slot so ML-MIT can IPC-swap a paper model without touching
    // demo/live artifacts (§6.5 promotion chain). Construction is infallible
    // and cheap (three ArcSwap<Option<_>> maps); cloning is Arc<...>::clone.
    // The runtime cost is zero until `use_edge_predictor=true` AND a model is
    // actually swapped in via `PipelineCommand::SetEdgePredictorShadow`.
    // EDGE-P3-1 Phase B #1：逐引擎 EdgePredictorStore 容器（paper/demo/live 三槽）。
    // 每條管線領一個 Arc 槽，ML-MIT 熱換 paper 模型不影響 demo/live。
    let per_engine_predictors =
        std::sync::Arc::new(openclaw_engine::edge_predictor::PerEnginePredictors::new());

    // is_primary priority: Live > Demo > Paper
    let has_live = live_bindings.is_some();
    let has_demo = demo_bindings.is_some();

    // D10/D20: Bounded fan-out — one WS source, N pipeline receivers.
    // All pipelines use 1024 slots (~3.5s at 280 tps) for transient-burst headroom.
    // "Fail-fast under lag" for Live is enforced by Fix 4's 120s WS-stale watchdog,
    // not by under-sizing this channel — 512 vs 1024 made no difference during the
    // 2026-04-15 02:03 self-cancel (both would have dropped under the ~2h cumulative
    // stall), but 1024 absorbs short spikes (<1s) cleanly instead of dropping ~500
    // extra ticks and feeding stale prices into strategies.
    // D10/D20：有界扇出 — 一個 WS 來源，N 個管線接收者。
    // 所有管線統一 1024（~3.5s @ 280 tps）吸收短促突發。Live 的「延遲快速失敗」
    // 由 Fix 4 的 120s WS-stale watchdog 執行，不靠此通道的欠配置；2026-04-15
    // 事故證實 512 vs 1024 在長時間壓力下都會丟（那是 consumer 端的同步 I/O 卡住），
    // 但 1024 在短尖峰下能乾淨吸收，避免策略消費到 ~500 個陳舊的 tick。
    let (paper_event_tx, paper_event_rx) = mpsc::channel::<Arc<PriceEvent>>(1024);
    let demo_event_channel = if has_demo {
        Some(mpsc::channel::<Arc<PriceEvent>>(1024))
    } else {
        None
    };
    // 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: live event channel
    // is now fully slot-based. The closure (boot Some path + watcher
    // respawn) builds a fresh channel each invocation, writes the sender
    // into `live_event_slot`, and moves the receiver into the OS thread
    // running `run_event_consumer`. Boot does NOT pre-build the channel
    // here — fan-out reads the slot per-tick, so the slot starting empty
    // (live_bindings None at boot) is exactly the "Live not yet up"
    // semantic we want.
    //
    // 2026-04-27 修復：live event 通道完全 slot 化。Closure（boot Some 與
    // watcher respawn）每次建新通道、寫 sender 入 `live_event_slot`、把
    // receiver move 進跑 `run_event_consumer` 的 OS 線程。Boot 不在此處
    // 預建通道 — fan-out 每 tick 讀 slot，slot 初始空（boot live_bindings
    // None）正是「Live 尚未上線」語意。
    let live_event_slot: main_fanout::LiveEventSenderSlot = Arc::new(ParkingRwLock::new(None));

    // MAJOR-2: Ready barriers — tx goes to pipeline deps, rx goes to fan-out.
    let (paper_ready_tx, paper_ready_rx) = tokio::sync::oneshot::channel::<()>();
    let (demo_ready_tx, demo_ready_rx) = if has_demo {
        let (tx, rx) = tokio::sync::oneshot::channel::<()>();
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };
    // 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: live ready barrier
    // is built per-spawn inside the spawner closure (boot Some + watcher
    // respawn share the closure). Fan-out is invoked with `None` for
    // `live_ready_rx`; fan-out's barrier step skips the live arm and
    // proceeds — paper / demo barriers still gate ordered init. The
    // ready_tx the closure builds fires when the freshly-spawned event
    // consumer initializes; nobody awaits it (we drop the rx) because
    // fan-out is already running by then.
    //
    // 2026-04-27 修復：live ready barrier 由 spawner closure 每次 spawn 內建
    // （boot Some 與 watcher respawn 共用 closure）。fan-out 以 `None`
    // 接 `live_ready_rx`，barrier 步驟跳過 live arm；paper / demo barrier
    // 仍守住有序初始化。Closure 內建 ready_tx 在 event consumer 初始化時
    // fire，無人 await（rx 直接 drop）— 屆時 fan-out 早已運行。
    let live_ready_rx: Option<tokio::sync::oneshot::Receiver<()>> = None;

    // BLOCKER-3 D15: Shared cross-engine global exposure atomic.
    let global_exposure_usdt = Arc::new(std::sync::atomic::AtomicU64::new(0));

    // BLOCKER-2 D6: Cross-engine event broadcast channel.
    let (cross_engine_tx, _) = tokio::sync::broadcast::channel::<EngineEvent>(16);

    // Paper pipeline health atomic.
    let paper_health = Arc::new(std::sync::atomic::AtomicU8::new(
        PipelineHealth::Running as u8,
    ));
    let paper_risk_level = Arc::new(std::sync::atomic::AtomicU8::new(
        openclaw_core::sm::risk_gov::RiskLevel::Normal.value(),
    ));

    // Fan-out task extracted to `main_fanout.rs` (G1-03 Wave 1).
    // Consumes upstream event_rx and paper/demo/live senders (moved),
    // awaits ready barriers (60s timeout) then distributes Arc-wrapped
    // ticks to each pipeline. Bounded channel overflow = tick drop
    // (logged debug/warn; Fix 4 120s WS-stale watchdog handles sustained).
    // 扇出任務已抽至 `main_fanout.rs`（G1-03 Wave 1）。
    main_fanout::spawn_fan_out(
        cancel.clone(),
        event_rx,
        paper_event_tx,
        demo_event_channel.as_ref().map(|(tx, _)| tx.clone()),
        // 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: live receiver
        // is now a slot rotated by the watcher.
        // 2026-04-27：live 接收端為 watcher 輪替的 slot。
        Arc::clone(&live_event_slot),
        paper_ready_rx,
        demo_ready_rx,
        live_ready_rx,
    );

    // ------------------------------------------------------------------
    // 3E-ARCH pipeline spawns extracted to `main_pipelines.rs` (G1-03 Wave 1).
    //   * `spawn_paper_pipeline` handles opt-in paper (OPENCLAW_ENABLE_PAPER=1)
    //     with DISABLED-marker fallback, drain-task, or full crash-only spawn.
    //   * `spawn_demo_pipeline` wraps demo deps + crash-only wrapper.
    //   * `spawn_live_pipeline` spawns live on a dedicated OS thread with
    //     catch_unwind isolation and engine-wide cancel on panic.
    // 3E-ARCH 管線啟動已抽出至 `main_pipelines.rs`（G1-03 Wave 1）：三管線個別
    // spawn fn 封裝 EventConsumerDeps 構建與 crash-only 包裝。
    // ------------------------------------------------------------------
    let spawn_ctx = main_pipelines::PipelineSpawnContext {
        config: &config,
        cancel: &cancel,
        instruments: &shared_instruments,
        shared_client: &shared_client,
        risk_stores: &risk_stores,
        budget_store: &budget_store,
        audit_pool: db_pool.get().cloned(),
        symbol_registry: &symbol_registry,
        scanner_store: &scanner_store,
        shared_linucb_runtime: &shared_linucb_runtime,
        shared_news_snapshot: &shared_news_snapshot,
        shared_last_tick_ms: &shared_last_tick_ms,
        canary_handle: &canary_handle,
        per_engine_predictors: &per_engine_predictors,
        cross_engine_tx: &cross_engine_tx,
        global_exposure_usdt: &global_exposure_usdt,
        has_live,
        has_demo,
    };
    let writers = main_pipelines::WriterSenders {
        market_tx: market_tx.clone(),
        feature_tx: feature_tx.clone(),
        trading_tx: trading_tx.clone(),
        context_tx: context_tx.clone(),
        decision_feature_tx: decision_feature_tx.clone(),
        // W-AUDIT-4b-M1 split (V082)：candidate evaluation log channel
        decision_feature_evaluation_tx: decision_feature_evaluation_tx.clone(),
        shadow_fill_tx: shadow_fill_tx.clone(),
        exit_feature_tx: exit_feature_tx.clone(),
        shadow_exit_tx: shadow_exit_tx.clone(),
        agent_spine_tx: agent_spine_tx.clone(),
        agent_spine_mode,
        lease_transition_tx: lease_transition_tx.clone(),
    };

    let paper_handle = main_pipelines::spawn_paper_pipeline(
        &spawn_ctx,
        &writers,
        main_pipelines::PaperChannels {
            event_rx: paper_event_rx,
            cmd_tx: paper_cmd_tx.clone(),
            cmd_rx: paper_cmd_rx,
            ready_tx: paper_ready_tx,
            health: Arc::clone(&paper_health),
            risk_level: Arc::clone(&paper_risk_level),
            positions_mirror: Arc::clone(&paper_positions_mirror),
            initial_balance: paper_balance,
        },
        &live_bindings,
        &demo_bindings,
    );

    // PIPELINE-SLOT-1 Phase 2 (E2 BLOCKER #1 fix): pair `demo_bindings` with
    // `demo_slot_cancel` via tuple pattern — the invariant "both Some or both
    // None" is structural; `(Some, None) | (None, Some)` is unreachable but
    // handled defensively (log + skip, never panic).
    // PIPELINE-SLOT-1 Phase 2（E2 BLOCKER #1 修復）：以 tuple 配對 demo bindings
    // 與 slot cancel；結構不變式保證「同時 Some 或同時 None」。
    let demo_handle: Option<tokio::task::JoinHandle<()>> = match (demo_bindings, demo_slot_cancel) {
        (Some(demo_b), Some(demo_slot_cancel_token)) => {
            let (_, demo_event_rx) = demo_event_channel.expect("demo channel must exist");
            Some(main_pipelines::spawn_demo_pipeline(
                &spawn_ctx,
                &writers,
                main_pipelines::DemoChannels {
                    bindings: demo_b,
                    slot_cancel: demo_slot_cancel_token,
                    event_rx: demo_event_rx,
                    cmd_tx: demo_cmd_tx.clone(),
                    cmd_rx: demo_cmd_rx,
                    ready_tx: demo_ready_tx,
                    positions_mirror: Arc::clone(&demo_positions_mirror),
                },
            ))
        }
        (None, None) => None,
        (Some(_), None) | (None, Some(_)) => {
            tracing::error!(
                "demo bindings/slot-cancel pairing invariant violated — skipping Demo spawn \
                     / Demo bindings/slot-cancel 配對不變式違反 — 跳過 Demo 啟動"
            );
            None
        }
    };

    // ------------------------------------------------------------------
    // LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN (2026-04-27): spawner closure
    // extracted to main_pipelines::build_live_pipeline_spawner (BLOCKER-1).
    // Boot Some → direct spawn via spawn_ctx (reused, no duplication).
    // Boot None / mid-session → LiveAuthWatcher decides_once.
    // ------------------------------------------------------------------
    let live_thread_handle_slot: live_auth_watcher::LiveThreadHandleSlot =
        Arc::new(ParkingMutex::new(None));

    // Build the live pipeline spawner via main_pipelines::build_live_pipeline_spawner.
    // BLOCKER-1 (E2 round-2, 2026-04-27): extracted from async_main to bring
    // main.rs under the §九 1200-line hard cap. The spawner closure is invoked
    // by LiveAuthWatcher on every successful slot try_spawn.
    //
    // BLOCKER-1（E2 round-2，2026-04-27）：spawner closure 抽至
    // main_pipelines::build_live_pipeline_spawner，讓 main.rs 回到 §九
    // 1200 行硬上限以內。
    let live_pipeline_spawner: live_auth_watcher::LivePipelineSpawner =
        main_pipelines::build_live_pipeline_spawner(main_pipelines::LiveSpawnBundle {
            config: Arc::clone(&config),
            cancel: cancel.clone(),
            instruments: shared_instruments.clone(),
            shared_client: shared_client.clone(),
            risk_stores: risk_stores.clone(),
            budget_store: Arc::clone(&budget_store),
            audit_pool: db_pool.get().cloned(),
            symbol_registry: Arc::clone(&symbol_registry),
            scanner_store: Arc::clone(&scanner_store),
            shared_linucb_runtime: Arc::clone(&shared_linucb_runtime),
            shared_news_snapshot: Arc::clone(&shared_news_snapshot),
            shared_last_tick_ms: Arc::clone(&shared_last_tick_ms),
            canary_handle: canary_handle.clone(),
            per_engine_predictors: Arc::clone(&per_engine_predictors),
            cross_engine_tx: cross_engine_tx.clone(),
            global_exposure_usdt: Arc::clone(&global_exposure_usdt),
            live_positions_mirror: Arc::clone(&live_positions_mirror),
            live_cmd_slot: Arc::clone(&live_cmd_slot),
            live_event_slot: Arc::clone(&live_event_slot),
            has_demo,
            market_tx: market_tx.clone(),
            feature_tx: feature_tx.clone(),
            trading_tx: trading_tx.clone(),
            context_tx: context_tx.clone(),
            decision_feature_tx: decision_feature_tx.clone(),
            // W-AUDIT-4b-M1 split (V082)：candidate evaluation log channel
            decision_feature_evaluation_tx: decision_feature_evaluation_tx.clone(),
            shadow_fill_tx: shadow_fill_tx.clone(),
            exit_feature_tx: exit_feature_tx.clone(),
            shadow_exit_tx: shadow_exit_tx.clone(),
            agent_spine_tx: agent_spine_tx.clone(),
            agent_spine_mode,
            lease_transition_tx: lease_transition_tx.clone(),
        });

    // Boot Some: direct spawn using pre-built channels. Reuses the `spawn_ctx`
    // + `writers` constructed above (BLOCKER-1 duplication eliminated per E2
    // round-2). The pre-built channels are essential for reconcilers / scheduler
    // that capture cmd_tx by-value at boot — they cannot be rotated through the
    // spawner closure (LIVE-RECONCILER-STALE-CMD-TX P1 TODO).
    //
    // Boot None: watcher decides_once and spawns when authorization becomes valid.
    //
    // Boot Some：使用預建通道直接 spawn，重用上方 spawn_ctx + writers（BLOCKER-1
    // 去重複，per E2 round-2）。預建通道供 reconciler / scheduler boot-time 值捕獲
    // — 不能走 spawner closure 輪換（LIVE-RECONCILER-STALE-CMD-TX P1 TODO）。
    // Boot None：watcher 在授權生效後決策並 spawn。
    if let (Some(live_b), Some(live_slot_cancel_token)) = (live_bindings, live_slot_cancel) {
        let (boot_live_event_tx, boot_live_event_rx) = mpsc::channel::<Arc<PriceEvent>>(1024);
        *live_event_slot.write() = Some(boot_live_event_tx);
        let (boot_live_ready_tx, _boot_live_ready_rx) = tokio::sync::oneshot::channel::<()>();
        let live_channels = main_pipelines::LiveChannels {
            bindings: live_b,
            slot_cancel: live_slot_cancel_token,
            event_rx: boot_live_event_rx,
            cmd_tx: live_cmd_tx.clone(),
            cmd_rx: live_cmd_rx,
            ready_tx: Some(boot_live_ready_tx),
            positions_mirror: Arc::clone(&live_positions_mirror),
        };
        let handle = main_pipelines::spawn_live_pipeline(&spawn_ctx, &writers, live_channels);
        *live_thread_handle_slot.lock() = Some(handle);
        info!(
            "boot-time Live pipeline spawned (direct path, reused spawn_ctx) \
             / boot-time Live 管線已啟動（直接路徑，重用 spawn_ctx）"
        );
    } else {
        info!(
            "boot-time Live pipeline NOT spawned (no authorization at boot); \
             LiveAuthWatcher will spawn via spawner closure when authorization becomes valid \
             / boot 時無授權；watcher 於授權生效時經 spawner closure 啟動"
        );
    }

    // ------------------------------------------------------------------
    // 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN: assemble the
    // watcher with the spawner closure + thread-handle slot. The IPC
    // trigger handle was wired earlier (before IPC server detached); we
    // reuse the matching receiver here via `from_parts`.
    // 2026-04-27：以 spawner closure + thread-handle slot 組裝 watcher。
    // IPC trigger handle 上面已接，本處透過 `from_parts` 接 receiver。
    // BLOCKER-2 (2026-04-27): pass live_cmd_slot and live_event_slot into
    // the watcher so that teardown arm can clear them. This prevents the
    // governance broadcast loop (set_system_mode) and fan-out from
    // delivering commands/ticks to a dead pipeline after teardown.
    //
    // BLOCKER-2（2026-04-27）：傳入 live_cmd_slot / live_event_slot，
    // 讓 teardown arm 清空兩個 slot，防止 governance broadcast 迴圈
    // 和 fan-out 在 teardown 後仍往死管線投命令 / tick。
    let live_auth_watcher = live_auth_watcher::LiveAuthWatcher::from_parts(
        Arc::clone(&live_slot) as Arc<dyn live_auth_watcher::SpawnOp>,
        Arc::clone(&config),
        live_bybit_environment(),
        cancel.clone(),
        live_auth_ipc_trigger_rx,
        Some(Arc::clone(&live_pipeline_spawner)),
        Some(Arc::clone(&live_thread_handle_slot)),
        Some(Arc::clone(&live_cmd_slot)),
        Some(Arc::clone(&live_event_slot)),
    );

    // Spawn the watcher run loop. From here on, mid-session authorization
    // changes (renew / revoke) drive Live respawn / teardown via the
    // closure path above.
    // 啟動 watcher run loop。中途授權變化（renew / revoke）驅動 Live
    // respawn / teardown 經上方 closure 路徑。
    let _live_auth_watcher_handle = tokio::spawn(live_auth_watcher.run());
    info!(
        env = ?live_bybit_environment(),
        boot_live_up = live_thread_handle_slot.lock().is_some(),
        "PIPELINE-SLOT-1 Phase 3 + 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN \
         watcher spawned (polls 5s, backoff 1s→60s; spawner closure injected) \
         / watcher 已啟動（5s 輪詢，1s→60s 退避；spawner closure 已注入）"
    );

    // ------------------------------------------------------------------
    // F6 PH5-WIRE-1 RELOAD (2026-04-26): edge estimates reload daemon,
    // gated by OPENCLAW_EDGE_RELOAD=1 (DEFAULT-OFF). Returns Some(tx)
    // when env=1; late-injects into IPC slot for manual reload trigger.
    // F6：邊際估計重載 daemon，受 OPENCLAW_EDGE_RELOAD=1 控管。
    // ------------------------------------------------------------------
    let edge_reload_signal_tx = main_boot_tasks::spawn_edge_estimates_reloader_if_enabled(
        Some(paper_cmd_tx.clone()),
        demo_cmd_tx.clone(),
        Some(Arc::clone(&live_cmd_slot)),
        &cancel,
    );
    if let Some(signal_tx) = edge_reload_signal_tx {
        // Late-inject sender into IPC slot so subsequent `reload_edge_estimates`
        // IPC requests are forwarded to the running daemon. Same pattern as
        // strategist counters / budget tracker / h_state_cache.
        // 將 sender 延後注入 IPC slot，後續 `reload_edge_estimates` IPC 請求
        // 即可轉發到運行中 daemon。對齊 strategist counters / budget tracker /
        // h_state_cache slot 注入 pattern。
        edge_reload_sender_slot_handle
            .write()
            .await
            .replace(signal_tx);
        info!(
            "F6 PH5-WIRE-1 RELOAD: reloader sender late-injected into IPC slot; \
             manual `reload_edge_estimates` IPC method now live \
             / 重載 sender 已 late-inject 至 IPC slot；\
             手動 `reload_edge_estimates` IPC method live"
        );
    }

    info!(
        version = VERSION,
        pipelines = format!(
            "paper{}{}",
            if has_demo { "+demo" } else { "" },
            if has_live { "+live" } else { "" }
        ),
        "engine started / 引擎已啟動"
    );

    // LiveAuthWatcher (spawned above) drives periodic re-verify every 5s +
    // immediate IPC fast-path; handles teardown AND respawn (LIVE-GATE-BINDING-1 +
    // PIPELINE-SLOT-1 Phase 3, 2026-04-18/19). No explicit ticker here.
    // LiveAuthWatcher 已在上方 spawn，負責 5s 輪詢 + IPC 快路徑觸發。

    // Tick-stale watchdog — extracted to main_watchdog.rs (G1-03 Wave 1).
    // tick-stale watchdog 已抽至 main_watchdog.rs。
    main_watchdog::spawn_tick_stale_watchdog(&shared_last_tick_ms, &cancel);

    // ------------------------------------------------------------------
    // Signal handling / 信號處理
    // ------------------------------------------------------------------
    signal_loop(&config, &cancel).await;

    // Ordered shutdown — extracted to main_shutdown.rs (G1-03 Wave 1).
    // Take latest Live OS thread handle from watcher slot before join.
    // 有序關閉已抽至 main_shutdown.rs；先從 watcher slot 取最新 handle。
    let live_thread_handle = live_thread_handle_slot.lock().take();
    main_shutdown::run_ordered_shutdown(
        &config,
        &cancel,
        main_shutdown::ShutdownHandles {
            live_slot,
            demo_slot,
            ws_handle,
            ipc_handle,
            live_thread_handle,
            demo_handle,
            paper_handle,
        },
    )
    .await;

    info!(version = VERSION, "engine stopped / 引擎已停止");
}
