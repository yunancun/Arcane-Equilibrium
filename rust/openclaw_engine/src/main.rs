//! OpenClaw Engine entry point — tokio runtime, signal handling, startup/shutdown (R01-2).
//! OpenClaw 引擎入口 — tokio 運行時、信號處理、啟動/關閉序列。
//!
//! MODULE_NOTE (EN): Sets up multi-thread tokio runtime for IPC + WS + background tasks.
//!   SIGHUP triggers config hot-reload. SIGTERM/SIGINT triggers graceful shutdown.
//!   Event consumer feeds PriceEvents into TickPipeline for paper trading.
//! MODULE_NOTE (中): 設置多線程 tokio 運行時用於 IPC + WS + 後台任務。
//!   SIGHUP 觸發配置熱加載。SIGTERM/SIGINT 觸發優雅關閉。
//!   事件消費者將 PriceEvent 送入 TickPipeline 進行紙盤交易。

mod live_auth_watcher;
mod main_boot_tasks;
mod main_fanout;
mod main_instruments;
mod main_pipelines;
mod main_shutdown;
mod main_watchdog;
mod main_ws;
mod pipeline_slot;
mod spawn_backoff;
mod startup;
mod tasks;

use openclaw_engine::bybit_rest_client::{live_bybit_environment, BybitEnvironment};
use openclaw_engine::config::{load_toml_or_default, ConfigManager, ConfigStore};
use openclaw_engine::ipc_server::{IpcServer, PerEngineRiskStores};
use openclaw_engine::market_data_client::MarketDataClient;
use openclaw_engine::scanner::registry::SymbolRegistry;
use openclaw_engine::scanner::runner::ScannerRunner;
use openclaw_engine::scanner::ScannerConfig;
use openclaw_engine::tick_pipeline::{EngineEvent, PipelineHealth, PipelineKind};
use openclaw_types::PriceEvent;
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
    // Scanner D4: Load ScannerConfig + build SymbolRegistry
    // 掃描器 D4：加載 ScannerConfig + 構建 SymbolRegistry
    // ------------------------------------------------------------------
    let scanner_config_path = {
        let base = std::env::var("OPENCLAW_RISK_CONFIG_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| std::path::PathBuf::from("settings/risk_control_rules"));
        std::env::var("OPENCLAW_SCANNER_CONFIG")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| base.join("scanner_config.toml"))
    };
    let scanner_cfg: ScannerConfig =
        load_toml_or_default(&scanner_config_path, |c: &ScannerConfig| c.validate())
            .unwrap_or_else(|e| {
                warn!(error = %e, "scanner config load failed, using defaults / 掃描器配置加載失敗，使用默認值");
                ScannerConfig::default()
            });
    info!(
        max_symbols = scanner_cfg.universe.max_symbols,
        pinned = ?scanner_cfg.universe.pinned_symbols,
        interval_secs = scanner_cfg.scheduling.scan_interval_secs,
        "scanner config loaded / 掃描器配置已加載"
    );
    let scanner_store: Arc<ConfigStore<ScannerConfig>> =
        Arc::new(ConfigStore::new(scanner_cfg).with_toml_persist(scanner_config_path));
    let pinned_syms = scanner_store.load().universe.pinned_symbols.clone();
    let symbol_registry = Arc::new(SymbolRegistry::new(
        pinned_syms.clone(), // initial_symbols = pinned (pre-scanner state)
        pinned_syms,         // pinned (never removed by anti-churn)
    ));

    // Scanner D4: Load EdgeEstimates for scanner scorer.
    // 掃描器 D4：為掃描器評分器加載邊際估計。
    let scanner_edge_estimates = {
        let base = std::env::var("OPENCLAW_BASE_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| std::path::PathBuf::from("."));
        let estimates =
            openclaw_engine::edge_estimates::EdgeEstimates::load_from_env_or_default(&base);
        Arc::new(parking_lot::RwLock::new(estimates))
    };

    // Scanner D4: Relay channel — ScannerRunner sends to a persistent channel;
    // a relay task forwards to the current WsClient's sender (refreshed on each restart).
    // 掃描器 D4：中繼通道 — ScannerRunner 發送到持久通道；
    // 中繼任務將消息轉發到當前 WsClient 的發送端（每次重啟時刷新）。
    let (scanner_ws_tx, mut scanner_ws_rx) =
        tokio::sync::mpsc::unbounded_channel::<openclaw_engine::ws_client::WsTopicChange>();
    let current_ws_client_tx: Arc<
        tokio::sync::Mutex<
            Option<tokio::sync::mpsc::UnboundedSender<openclaw_engine::ws_client::WsTopicChange>>,
        >,
    > = Arc::new(tokio::sync::Mutex::new(None));
    {
        let relay_arc = Arc::clone(&current_ws_client_tx);
        tokio::spawn(async move {
            while let Some(change) = scanner_ws_rx.recv().await {
                let guard = relay_arc.lock().await;
                if let Some(tx) = guard.as_ref() {
                    let _ = tx.send(change);
                } else {
                    tracing::debug!("[scanner relay] WsClient not ready — topic change dropped, will retry on next scan");
                }
            }
        });
    }

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
    // PIPELINE-SLOT-1 Phase 2: slots own each pipeline's cancel token and
    // task handles. `try_spawn` derives a slot-scoped child from the engine-
    // wide shutdown token, threads it into `build_exchange_pipeline`, and
    // returns both the bindings and a clone of the child token. We store
    // the child token next to each slot for later use:
    //   * `live_slot_cancel` → threaded into the Live OS thread's
    //     `live_cancel` AND into `live_deps.cancel` (EventConsumerDeps)
    //     so the Phase-3 `LiveAuthWatcher`'s `live_slot.teardown()` cancels
    //     the Live event-consumer main loop, not just the WS supervisor
    //     / listener / balance-refresh tasks. Pre-Phase-2-fix wiring passed
    //     the engine-wide `cancel` clone into `live_deps.cancel`, which
    //     meant teardown left the event consumer running and still
    //     dispatching orders — a skin-deep teardown. (E2 BLOCKER #1.)
    //   * `demo_slot_cancel` → threaded into `demo_deps.cancel` for the
    //     same reason — consistency + future safety if a demo-scoped
    //     teardown path appears. Demo is never torn down mid-session in
    //     Phase 2, so behaviour is unchanged on the happy path; binding
    //     to the child is strictly more correct because cancelling the
    //     engine-wide parent still cascades down to this child (tokio-util
    //     CancellationToken contract), so SIGTERM still stops Demo cleanly.
    //
    // PIPELINE-SLOT-1 Phase 2：槽位擁有每條管線的 cancel token 與任務
    // handle。`try_spawn` 從引擎級 shutdown token 派生槽位子 token，傳入
    // `build_exchange_pipeline`，並回傳 bindings + 子 token clone。我們把
    // 子 token 與 slot 一起保留備用：
    //   * `live_slot_cancel` → 串進 Live OS 線程的 `live_cancel` **以及**
    //     `live_deps.cancel`（EventConsumerDeps），讓 Phase 3 `LiveAuthWatcher` 的
    //     `live_slot.teardown()` 也能取消 Live event-consumer 主迴圈，
    //     不僅是 WS supervisor / listener / balance-refresh。修復前 wiring
    //     把引擎級 `cancel` clone 給 `live_deps.cancel`，導致 teardown 後
    //     event consumer 仍在跑、仍在下單 — 皮毛式 teardown。（E2 BLOCKER #1）
    //   * `demo_slot_cancel` → 串進 `demo_deps.cancel`，理由同上（一致性
    //     + 未來若出現 demo-scoped teardown 路徑時的安全性）。Phase 2
    //     不會中途拆 Demo，happy path 行為不變；綁定子 token 仍嚴格更正確，
    //     因為取消引擎級父 token 會連帶子 token（tokio-util 契約），
    //     SIGTERM 依舊乾淨停 Demo。
    let live_slot = Arc::new(pipeline_slot::PipelineSlot::new_empty(
        pipeline_slot::SlotKind::Live,
    ));
    let demo_slot = Arc::new(pipeline_slot::PipelineSlot::new_empty(
        pipeline_slot::SlotKind::Demo,
    ));
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
    // OPENCLAW_IPC_SECRET MUST be set. Fail-closed: panic on startup.
    // FIX-10：Live 管線啟動時 IPC HMAC 認證強制——無密鑰直接 panic。
    // ------------------------------------------------------------------
    if live_bindings.is_some() && std::env::var("OPENCLAW_IPC_SECRET").is_err() {
        panic!(
            "FATAL: Live pipeline detected but OPENCLAW_IPC_SECRET is not set. \
             IPC HMAC authentication is mandatory for Live trading. \
             Set OPENCLAW_IPC_SECRET env var before starting with Live credentials. \
             / Live 管線偵測到但 OPENCLAW_IPC_SECRET 未設置。Live 交易必須啟用 IPC HMAC 認證。"
        );
    }

    // ------------------------------------------------------------------
    // Start IPC server / 啟動 IPC 服務器
    // ------------------------------------------------------------------
    let ipc_data_dir =
        std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into());

    // 3E-ARCH: Independent command channels per pipeline.
    // 3E-ARCH：每條管線獨立的命令通道。
    let (paper_cmd_tx, paper_cmd_rx) = tokio::sync::mpsc::unbounded_channel();
    let (demo_cmd_tx, demo_cmd_rx) = if demo_bindings.is_some() {
        let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };
    let (live_cmd_tx, live_cmd_rx) = if live_bindings.is_some() {
        let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };

    let phase4_consumer_cmd_tx = paper_cmd_tx.clone();

    let mut ipc_server = IpcServer::new(Arc::clone(&config), cancel.clone(), ipc_data_dir, {
        use openclaw_engine::ipc_server::EngineCommandChannels;
        let mut channels = EngineCommandChannels::default();
        channels.paper = Some(paper_cmd_tx.clone());
        if let Some(ref tx) = demo_cmd_tx {
            channels.demo = Some(tx.clone());
        }
        if let Some(ref tx) = live_cmd_tx {
            channels.live = Some(tx.clone());
        }
        channels
    });
    ipc_server.set_config_stores(
        risk_stores.clone(),
        Arc::clone(&learning_store),
        Arc::clone(&budget_store),
    );
    ipc_server.set_scanner_registry(Arc::clone(&symbol_registry));

    // ------------------------------------------------------------------
    // PIPELINE-SLOT-1 Phase 3: construct Live authorization watcher and
    // wire its IPC trigger into the IPC server before `.run()` starts.
    //
    // Why here, before `ipc_server.run()` spawn?
    //   * `set_live_auth_recheck_sender` must land before any connection
    //     is accepted so the `trigger_live_auth_recheck` method can find
    //     the sender — otherwise Python's first post-renew trigger after
    //     boot would get `watcher_disabled`.
    //   * The watcher itself uses `live_slot` + `config` + engine-wide
    //     cancel token, all of which are ready by this point.
    //
    // The watcher replaces the Phase 2 5-min re-verify loop (removed
    // below). It polls every 5 seconds, tears down on auth invalidation,
    // AND respawns on renewal (gated by exponential backoff).
    //
    // PIPELINE-SLOT-1 Phase 3：構造 Live 授權 watcher 並在 `ipc_server.run()`
    // spawn 前接入 IPC trigger。
    //   * `set_live_auth_recheck_sender` 必須在接受任何連線前完成，否則
    //     Python 開機後首次 post-renew trigger 會收到 `watcher_disabled`。
    //   * Watcher 自身所需 `live_slot` + `config` + 引擎級 cancel token 此時已就緒。
    //
    // Watcher 取代 Phase 2 的 5 分鐘重驗 loop（下方已移除）。每 5 秒輪詢，
    // 授權失效時 teardown，授權恢復時 respawn（經指數退避閘）。
    // ------------------------------------------------------------------
    let (live_auth_watcher, live_auth_trigger_handle) =
        live_auth_watcher::LiveAuthWatcher::new(
            Arc::clone(&live_slot) as Arc<dyn live_auth_watcher::SpawnOp>,
            Arc::clone(&config),
            live_bybit_environment(),
            cancel.clone(),
        );
    ipc_server.set_live_auth_recheck_sender(live_auth_trigger_handle.sender());

    let budget_tracker_slot = ipc_server.budget_tracker_slot();
    let teacher_loop_slot = ipc_server.teacher_loop_slot();
    let audit_pool_slot = ipc_server.audit_pool_slot();
    // G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25): grab the counters
    // slot before detaching IPC server so we can write the scheduler's
    // CycleCounters Arc into it after `spawn_strategist_scheduler` returns
    // below. Mirrors the late-injection pattern used by budget/teacher/audit.
    // G3-11：在 IPC server detach 前取 slot handle，scheduler spawn 後 late-inject counters。
    let strategist_counters_slot = ipc_server.strategist_counters_slot();
    let ipc_handle = tokio::spawn(async move {
        if let Err(e) = ipc_server.run().await {
            error!(error = %e, "IPC server error / IPC 服務器錯誤");
        }
    });

    // Spawn the Live auth watcher task. Its `run()` future owns `self`,
    // so we spawn it after `ipc_server.run()` is detached. The watcher
    // exits cleanly when the engine-wide `cancel` token fires.
    // 起 Live 授權 watcher 任務。`run()` future 持有 `self`，故在
    // `ipc_server.run()` detach 後 spawn。引擎級 `cancel` token 觸發時乾淨退出。
    let _live_auth_watcher_handle = tokio::spawn(live_auth_watcher.run());
    info!(
        env = ?live_bybit_environment(),
        "PIPELINE-SLOT-1 Phase 3 Live auth watcher spawned (polls 5s, \
         backoff 1s→60s) / Phase 3 Live 授權 watcher 已啟動（5s 輪詢，1s→60s 退避）"
    );

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
        shared_account_manager: _shared_account_manager,
        shared_instruments,
        paper_balance,
    } = main_instruments::init_shared_clients_and_instruments(
        &cancel,
        &live_bindings,
        &demo_bindings,
    )
    .await;

    // ------------------------------------------------------------------
    // Scanner D4: Spawn ScannerRunner (requires market REST client)
    // 掃描器 D4：啟動 ScannerRunner（需要市場 REST 客戶端）
    // ------------------------------------------------------------------
    // 3E-ARCH: Scanner broadcasts AddSymbol/RemoveSymbol to ALL pipelines.
    // 掃描器向所有管線廣播 AddSymbol/RemoveSymbol。
    if let Some(ref client) = shared_client {
        // Build a fan-out sender that sends to all pipeline cmd channels.
        let scanner_cmd_tx = paper_cmd_tx.clone();
        let market_client = Arc::new(MarketDataClient::new(Arc::clone(client)));
        let runner = ScannerRunner::new(
            Arc::clone(&symbol_registry),
            market_client,
            Arc::clone(&scanner_edge_estimates),
            Arc::clone(&scanner_store),
            scanner_ws_tx,
            scanner_cmd_tx,
            cancel.clone(),
        );
        tokio::spawn(runner.run());
        info!("ScannerRunner spawned / 掃描器已啟動");
    } else {
        warn!("ScannerRunner skipped: no REST client (pinned symbols only) / 掃描器跳過：無 REST 客戶端（僅固定交易對）");
    }

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

    // 3E-ARCH: Private WS bindings are now inside ExchangePipelineBindings (D21).
    // 私有 WS 綁定已在 ExchangePipelineBindings 內（D21）。

    // 3E-ARCH: Private WS bindings are now inside ExchangePipelineBindings (D21).
    // 私有 WS 綁定已在 ExchangePipelineBindings 內（D21）。

    // ------------------------------------------------------------------
    // Phase 1: Database pool + writer tasks
    // Phase 1：資料庫連接池 + 寫入器任務
    // ------------------------------------------------------------------
    let cfg_snap_db = config.get();
    let db_pool =
        Arc::new(openclaw_engine::database::pool::DbPool::connect(&cfg_snap_db.database).await);

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
        Arc::new(openclaw_engine::linucb::LinUcbRuntime::cold_start_v1_15());
    info!(
        active_version = shared_linucb_runtime.arm_space_version(),
        feature_schema_hash = shared_linucb_runtime.feature_schema_hash(),
        "LinUcbRuntime cold-started / LinUCB runtime 冷啟動"
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
        phase4_consumer_cmd_tx,
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
        shadow_fill_tx,
        exit_feature_tx,
        shadow_exit_tx,
    ) = tasks::spawn_db_writers(
        &db_pool,
        &config,
        &cancel,
        &symbol_registry,
        &shared_client,
        &shared_last_tick_ms,
    )
    .await;

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
        &live_cmd_tx,
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
        &live_cmd_tx,
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
    let live_event_channel = if has_live {
        Some(mpsc::channel::<Arc<PriceEvent>>(1024))
    } else {
        None
    };

    // MAJOR-2: Ready barriers — tx goes to pipeline deps, rx goes to fan-out.
    let (paper_ready_tx, paper_ready_rx) = tokio::sync::oneshot::channel::<()>();
    let (demo_ready_tx, demo_ready_rx) = if has_demo {
        let (tx, rx) = tokio::sync::oneshot::channel::<()>();
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };
    let (live_ready_tx, live_ready_rx) = if has_live {
        let (tx, rx) = tokio::sync::oneshot::channel::<()>();
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };

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
        live_event_channel.as_ref().map(|(tx, _)| tx.clone()),
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
        shadow_fill_tx: shadow_fill_tx.clone(),
        exit_feature_tx: exit_feature_tx.clone(),
        shadow_exit_tx: shadow_exit_tx.clone(),
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
    let demo_handle: Option<tokio::task::JoinHandle<()>> =
        match (demo_bindings, demo_slot_cancel) {
            (Some(demo_b), Some(demo_slot_cancel_token)) => {
                let (_, demo_event_rx) =
                    demo_event_channel.expect("demo channel must exist");
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

    // PIPELINE-SLOT-1 Phase 2/3: same Option-pair invariant for Live.
    // PIPELINE-SLOT-1 Phase 2/3：Live 同樣以 Option-pair 強制不變式。
    let live_thread_handle: Option<std::thread::JoinHandle<()>> =
        match (live_bindings, live_slot_cancel) {
            (Some(live_b), Some(live_slot_cancel_token)) => {
                let (_, live_event_rx) =
                    live_event_channel.expect("live channel must exist");
                Some(main_pipelines::spawn_live_pipeline(
                    &spawn_ctx,
                    &writers,
                    main_pipelines::LiveChannels {
                        bindings: live_b,
                        slot_cancel: live_slot_cancel_token,
                        event_rx: live_event_rx,
                        cmd_tx: live_cmd_tx.clone(),
                        cmd_rx: live_cmd_rx,
                        ready_tx: live_ready_tx,
                        positions_mirror: Arc::clone(&live_positions_mirror),
                    },
                ))
            }
            (None, None) => None,
            (Some(_), None) | (None, Some(_)) => {
                tracing::error!(
                    "live bindings/slot-cancel pairing invariant violated — skipping Live spawn \
                     / Live bindings/slot-cancel 配對不變式違反 — 跳過 Live 啟動"
                );
                None
            }
        };

    info!(
        version = VERSION,
        pipelines = format!(
            "paper{}{}",
            if has_demo { "+demo" } else { "" },
            if has_live { "+live" } else { "" }
        ),
        "engine started / 引擎已啟動"
    );

    // ------------------------------------------------------------------
    // LIVE-GATE-BINDING-1 (2026-04-18) → PIPELINE-SLOT-1 Phase 3 (2026-04-19):
    // periodic re-verify is now driven by `LiveAuthWatcher` (spawned above
    // near `ipc_server.run()`). It polls authorization.json every 5s and —
    // unlike the Phase 2 300s ticker it replaces — handles BOTH invalidation
    // teardown AND operator-renew respawn, gated by an exponential backoff
    // so a persistently-failing `build_exchange_pipeline` does not storm
    // Bybit. IPC fast-path `trigger_live_auth_recheck` from Python's
    // `/auth/renew` and `/auth/revoke` routes keeps TTR under 100ms.
    //
    // LIVE-GATE-BINDING-1 (2026-04-18) → PIPELINE-SLOT-1 Phase 3 (2026-04-19)：
    // 定期重驗授權由 `LiveAuthWatcher`（上方 `ipc_server.run()` 附近 spawn）驅動。
    // 5s 輪詢 authorization.json，與 Phase 2 300s ticker 的差異：**同時**處理
    // 失效 teardown 與 operator renew respawn，並以指數退避閘防止持續失敗
    // 敲死 Bybit。Python `/auth/renew`、`/auth/revoke` 路由經 IPC 快路徑
    // `trigger_live_auth_recheck` 讓 TTR 壓在 100ms 內。

    // ------------------------------------------------------------------
    // Fix 4 (2026-04-14) tick-stale watchdog — extracted to `main_watchdog.rs`
    // (G1-03 Wave 1). Polls shared_last_tick_ms every 30s; if a tick has ever
    // arrived and no new tick for ≥120s, flushes stdout/stderr and triggers
    // engine-wide cancel. Covers WS disconnect + event_consumer zombie cases.
    // Fix 4 (2026-04-14) tick-stale watchdog — 已抽至 `main_watchdog.rs`
    // （G1-03 Wave 1），每 30s 輪詢；曾收過 tick 且 ≥120s 無新 tick → cancel。
    // ------------------------------------------------------------------
    main_watchdog::spawn_tick_stale_watchdog(&shared_last_tick_ms, &cancel);

    // ------------------------------------------------------------------
    // Signal handling / 信號處理
    // ------------------------------------------------------------------
    signal_loop(&config, &cancel).await;

    // ------------------------------------------------------------------
    // MAJOR-3 ordered shutdown (Live → Demo → Paper) extracted to
    // `main_shutdown.rs` (G1-03 Wave 1). Cancels engine-wide token, awaits
    // slot teardowns (E2 MAJOR #3 deterministic join), drains handles under
    // 10s timeout, removes IPC socket file.
    // MAJOR-3 有序關閉（Live → Demo → Paper）已抽至 `main_shutdown.rs`
    // （G1-03 Wave 1）：cancel + slot teardown + handle drain + socket cleanup。
    // ------------------------------------------------------------------
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
