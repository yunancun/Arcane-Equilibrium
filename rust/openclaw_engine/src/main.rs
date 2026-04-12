//! OpenClaw Engine entry point — tokio runtime, signal handling, startup/shutdown (R01-2).
//! OpenClaw 引擎入口 — tokio 運行時、信號處理、啟動/關閉序列。
//!
//! MODULE_NOTE (EN): Sets up multi-thread tokio runtime for IPC + WS + background tasks.
//!   SIGHUP triggers config hot-reload. SIGTERM/SIGINT triggers graceful shutdown.
//!   Event consumer feeds PriceEvents into TickPipeline for paper trading.
//! MODULE_NOTE (中): 設置多線程 tokio 運行時用於 IPC + WS + 後台任務。
//!   SIGHUP 觸發配置熱加載。SIGTERM/SIGINT 觸發優雅關閉。
//!   事件消費者將 PriceEvent 送入 TickPipeline 進行紙盤交易。

mod startup;
mod tasks;

use openclaw_engine::account_manager::AccountManager;
use openclaw_engine::bybit_rest_client::{live_bybit_environment, BybitEnvironment, BybitRestClient};
use openclaw_engine::config::{
    load_toml_or_default, ConfigManager, ConfigStore,
};
use openclaw_engine::ipc_server::{IpcServer, PerEngineRiskStores};
use openclaw_engine::market_data_client::MarketDataClient;
use openclaw_engine::scanner::ScannerConfig;
use openclaw_engine::scanner::registry::SymbolRegistry;
use openclaw_engine::scanner::runner::ScannerRunner;
use openclaw_engine::tick_pipeline::{EngineEvent, PipelineHealth, PipelineKind};
use openclaw_engine::ws_client::WsClient;
use openclaw_types::PriceEvent;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{error, info, warn};

use startup::*;

// SYMBOLS moved to event_consumer.rs (Phase 1 Day 0-A extraction)
// STATUS_INTERVAL_SECS moved to event_consumer.rs

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
        let estimates = openclaw_engine::edge_estimates::EdgeEstimates::load_from_env_or_default(&base);
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
    let live_bindings = build_exchange_pipeline(
        PipelineKind::Live,
        live_bybit_environment(),
        cancel.clone(),
        &cfg_snapshot_pipelines,
    ).await;
    let demo_bindings = build_exchange_pipeline(
        PipelineKind::Demo,
        BybitEnvironment::Demo,
        cancel.clone(),
        &cfg_snapshot_pipelines,
    ).await;
    drop(cfg_snapshot_pipelines);

    // Log pipeline availability / 記錄管線可用性
    info!(
        live = live_bindings.is_some(),
        demo = demo_bindings.is_some(),
        paper = true,
        "3E-ARCH: pipeline availability detected / 管線可用性偵測完成"
    );

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

    let mut ipc_server = IpcServer::new(
        Arc::clone(&config),
        cancel.clone(),
        ipc_data_dir,
        {
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
        },
    );
    ipc_server.set_config_stores(
        risk_stores.clone(),
        Arc::clone(&learning_store),
        Arc::clone(&budget_store),
    );
    ipc_server.set_scanner_registry(Arc::clone(&symbol_registry));
    let budget_tracker_slot = ipc_server.budget_tracker_slot();
    let teacher_loop_slot = ipc_server.teacher_loop_slot();
    let audit_pool_slot = ipc_server.audit_pool_slot();
    let ipc_handle = tokio::spawn(async move {
        if let Err(e) = ipc_server.run().await {
            error!(error = %e, "IPC server error / IPC 服務器錯誤");
        }
    });

    // ------------------------------------------------------------------
    // 3E-ARCH: Shared REST client = highest-priority exchange pipeline's client.
    // Used by Scanner, InstrumentRefresh, fee refresh tasks.
    // 共享 REST 客戶端 = 最高優先級交易所管線的客戶端。
    // ------------------------------------------------------------------
    let shared_client: Option<Arc<BybitRestClient>> = live_bindings
        .as_ref()
        .map(|b| Arc::clone(&b.rest_client))
        .or_else(|| demo_bindings.as_ref().map(|b| Arc::clone(&b.rest_client)));

    let shared_account_manager: Option<Arc<AccountManager>> = live_bindings
        .as_ref()
        .map(|b| Arc::clone(&b.account_manager))
        .or_else(|| demo_bindings.as_ref().map(|b| Arc::clone(&b.account_manager)));

    let mut shared_instruments: Option<Arc<openclaw_engine::instrument_info::InstrumentInfoCache>> =
        None;

    // R-05: Load instrument info cache using shared client.
    if let Some(ref client) = shared_client {
        let instrument_cache =
            Arc::new(openclaw_engine::instrument_info::InstrumentInfoCache::new());
        match instrument_cache.refresh(&**client, "linear").await {
            Ok(count) => {
                shared_instruments = Some(Arc::clone(&instrument_cache));
                info!(symbols = count, "instrument info loaded / 品種規格已加載");
            }
            Err(e) => warn!(error = %e, "instrument info fetch failed / 品種規格加載失敗"),
        }

        // Spawn fee rate refresh + staleness monitor using shared client's account manager.
        if let Some(ref acct) = shared_account_manager {
            tasks::spawn_fee_rate_tasks(acct, client, &cancel);
        }
    } else {
        info!("no exchange clients — skipping instrument/fee setup / 無交易所客戶端，跳過品種/費率設定");
    }

    // MAJOR-4: Paper balance uses unified priority.
    // 紙盤餘額統一優先級解析。
    let paper_balance = resolve_paper_initial_balance().await;

    // R-05: Periodic instrument info refresh (every 4 hours)
    if let (Some(ref icache), Some(ref client)) = (&shared_instruments, &shared_client) {
        tasks::spawn_instrument_refresh(icache, client, &cancel);
    }

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
    // Start WS client — subscribe to all symbols
    // 啟動 WebSocket 客戶端 — 訂閱所有交易對
    // ------------------------------------------------------------------
    let cfg_snapshot = config.get();
    let ws_subscriptions: Vec<String> = if cfg_snapshot.enable_extended_ws {
        let mut topics = Vec::new();
        for sym in symbol_registry.snapshot() {
            for topic in openclaw_engine::multi_interval_ws::full_subscription_list(&sym) {
                topics.push(topic);
            }
        }
        info!(
            topics_per_symbol = 10,
            "extended WS subscriptions / 擴展 WS 訂閱"
        );
        topics
    } else {
        let mut topics = Vec::new();
        for sym in symbol_registry.snapshot() {
            topics.push(format!("kline.1.{sym}"));
            topics.push(format!("publicTrade.{sym}"));
        }
        topics
    };

    // RE-2: Supervisor wrapper — restarts WS on unexpected exit.
    let ws_handle = {
        let ws_config = Arc::clone(&config);
        let ws_cancel = cancel.clone();
        let initial_topics = ws_subscriptions.clone();
        let registry_for_supervisor = Arc::clone(&symbol_registry);
        let relay_for_supervisor = Arc::clone(&current_ws_client_tx);
        let extended_ws = cfg_snapshot.enable_extended_ws;
        tokio::spawn(async move {
            let mut supervisor_attempt: u32 = 0;
            loop {
                if ws_cancel.is_cancelled() {
                    break;
                }

                let topics: Vec<String> = if supervisor_attempt == 0 {
                    initial_topics.clone()
                } else if extended_ws {
                    registry_for_supervisor.snapshot().into_iter().flat_map(|sym| {
                        openclaw_engine::multi_interval_ws::full_subscription_list(&sym)
                    }).collect()
                } else {
                    registry_for_supervisor.snapshot().into_iter().flat_map(|sym| {
                        vec![format!("kline.1.{sym}"), format!("publicTrade.{sym}")]
                    }).collect()
                };

                let mut ws_client =
                    WsClient::new(Arc::clone(&ws_config), event_tx.clone(), ws_cancel.clone());
                for topic in &topics {
                    ws_client.subscribe(topic.clone());
                }
                let inner_tx = ws_client.with_topic_change_channel();
                *relay_for_supervisor.lock().await = Some(inner_tx);

                ws_client.run().await;

                *relay_for_supervisor.lock().await = None;

                if ws_cancel.is_cancelled() {
                    break;
                }

                supervisor_attempt = supervisor_attempt.saturating_add(1);
                let delay_ms = std::cmp::min(
                    5000_u64.saturating_mul(2_u64.saturating_pow(supervisor_attempt.min(4))),
                    60_000,
                );
                warn!(
                    delay_ms = delay_ms,
                    attempt = supervisor_attempt,
                    "WS supervisor restarting / WS 監管器重啟"
                );
                tokio::select! {
                    _ = ws_cancel.cancelled() => break,
                    _ = tokio::time::sleep(std::time::Duration::from_millis(delay_ms)) => {},
                }
            }
        })
    };

    // 3E-ARCH: Private WS bindings are now inside ExchangePipelineBindings (D21).
    // 私有 WS 綁定已在 ExchangePipelineBindings 內（D21）。

    // ------------------------------------------------------------------
    // Phase 1: Database pool + writer tasks
    // Phase 1：資料庫連接池 + 寫入器任務
    // ------------------------------------------------------------------
    let cfg_snap_db = config.get();
    let db_pool =
        Arc::new(openclaw_engine::database::pool::DbPool::connect(&cfg_snap_db.database).await);

    // Initialize BudgetTracker + audit pool
    tasks::init_budget_and_audit(&db_pool, &budget_tracker_slot, &audit_pool_slot).await;

    // ------------------------------------------------------------------
    // Phase 4: LinUCB runtime + news context snapshot + governance wrappers
    // ------------------------------------------------------------------
    let shared_linucb_runtime = Arc::new(
        openclaw_engine::linucb::LinUcbRuntime::cold_start_v1_15(),
    );
    info!(
        active_version = shared_linucb_runtime.arm_space_version(),
        feature_schema_hash = shared_linucb_runtime.feature_schema_hash(),
        "LinUcbRuntime cold-started / LinUCB runtime 冷啟動"
    );

    let shared_news_snapshot = Arc::new(
        openclaw_engine::news::NewsContextSnapshot::new(),
    );
    info!(
        "NewsContextSnapshot constructed (default severity 0.0) / 新聞 context 快照已建立"
    );

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
    let guardian_impl = Arc::new(
        openclaw_engine::news::GuardianHaltCheckImpl::new(Arc::clone(&shared_halted_handle)),
    );
    info!(
        "Phase 4 governance+guardian wrappers constructed / W-1/W-2 wrappers 已構造"
    );

    // Phase 4.1: Spawn TeacherConsumerLoop (DEFAULT-OFF)
    tasks::spawn_teacher_consumer_loop(
        &db_pool,
        &budget_tracker_slot,
        teacher_loop_slot,
        phase4_consumer_cmd_tx,
        &governance_wrapper,
    ).await;
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
    let (market_tx, feature_tx, trading_tx, context_tx) = tasks::spawn_db_writers(
        &db_pool,
        &config,
        &cancel,
        &symbol_registry,
        &shared_client,
        &shared_last_tick_ms,
    ).await;

    // ------------------------------------------------------------------
    // Phase 6 + D23: Per-exchange position reconciler.
    // Phase 6 + D23：每條交易所管線獨立持倉對帳器。
    // ------------------------------------------------------------------
    if let Some(ref live_b) = live_bindings {
        if let Some(ref tx) = live_cmd_tx {
            tasks::spawn_position_reconciler(
                &live_b.rest_client,
                &db_pool,
                &cancel,
                tx.clone(),
                &shared_instruments,
                &live_b.risk_level,
                live_b.env,
            );
            info!("position_reconciler spawned for Live / Live 持倉對帳器已啟動");
        }
    }
    if let Some(ref demo_b) = demo_bindings {
        if let Some(ref tx) = demo_cmd_tx {
            tasks::spawn_position_reconciler(
                &demo_b.rest_client,
                &db_pool,
                &cancel,
                tx.clone(),
                &shared_instruments,
                &demo_b.risk_level,
                demo_b.env,
            );
            info!("position_reconciler spawned for Demo / Demo 持倉對帳器已啟動");
        }
    }
    if live_bindings.is_none() && demo_bindings.is_none() {
        info!("position_reconciler skipped (no exchange pipelines) / 持倉對帳器跳過（無交易所管線）");
    }

    // ------------------------------------------------------------------
    // 3E-ARCH: Three-pipeline fan-out + independent spawn
    // 3E-ARCH：三管線扇出 + 獨立 spawn
    // ------------------------------------------------------------------
    use openclaw_engine::event_consumer::{run_event_consumer, EventConsumerDeps};

    // is_primary priority: Live > Demo > Paper
    let has_live = live_bindings.is_some();
    let has_demo = demo_bindings.is_some();

    // D10/D20: Bounded fan-out — one WS source, N pipeline receivers.
    // Buffer sizes: Paper/Demo 1024 for headroom during burst ticks;
    // Live 512 (smaller = fail-fast under lag — real-money pipeline should
    // never accumulate a deep backlog; dropped ticks are logged at warn level).
    // D10/D20：有界扇出 — 一個 WS 來源，N 個管線接收者。
    // 緩衝區大小：Paper/Demo 1024 提供突發 tick 容量；
    // Live 512（較小 = 延遲時快速失敗 — 實盤管線不應累積深度積壓，
    // 丟棄的 tick 以 warn 級別記錄）。
    let (paper_event_tx, paper_event_rx) = mpsc::channel::<Arc<PriceEvent>>(1024);
    let demo_event_channel = if has_demo { Some(mpsc::channel::<Arc<PriceEvent>>(1024)) } else { None };
    let live_event_channel = if has_live { Some(mpsc::channel::<Arc<PriceEvent>>(512)) } else { None };

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
    let paper_health = Arc::new(std::sync::atomic::AtomicU8::new(PipelineHealth::Running as u8));
    let paper_risk_level = Arc::new(std::sync::atomic::AtomicU8::new(
        openclaw_core::sm::risk_gov::RiskLevel::Normal.value(),
    ));

    // Fan-out task: read from single event_rx, broadcast Arc-wrapped events to all pipelines.
    // 扇出任務：從單一 event_rx 讀取，向所有管線廣播 Arc 包裝的事件。
    {
        let paper_tx = paper_event_tx;
        let demo_tx = demo_event_channel.as_ref().map(|(tx, _)| tx.clone());
        let live_tx = live_event_channel.as_ref().map(|(tx, _)| tx.clone());
        let fan_cancel = cancel.clone();
        tokio::spawn(async move {
            let barrier_timeout = tokio::time::Duration::from_secs(60);
            let barrier_result = tokio::time::timeout(barrier_timeout, async {
                let _ = paper_ready_rx.await;
                if let Some(rx) = demo_ready_rx {
                    let _ = rx.await;
                }
                if let Some(rx) = live_ready_rx {
                    let _ = rx.await;
                }
            }).await;

            if barrier_result.is_err() {
                tracing::error!(
                    "fan-out: pipeline init timed out after 60s, starting anyway \
                     / 管線初始化超時 60s，仍然啟動扇出"
                );
            } else {
                tracing::info!(
                    "fan-out: all pipelines ready, starting tick distribution \
                     / 所有管線就緒，開始 tick 分發"
                );
            }

            let mut event_rx = event_rx;
            loop {
                tokio::select! {
                    _ = fan_cancel.cancelled() => break,
                    evt = event_rx.recv() => {
                        match evt {
                            Some(price_event) => {
                                let arc_event = Arc::new(price_event);
                                if paper_tx.try_send(Arc::clone(&arc_event)).is_err() {
                                    tracing::debug!(
                                        "fan-out: paper pipeline lagging, tick dropped / Paper 管線延遲，tick 已丟棄"
                                    );
                                }
                                if let Some(ref dtx) = demo_tx {
                                    if dtx.try_send(Arc::clone(&arc_event)).is_err() {
                                        tracing::debug!(
                                            "fan-out: demo pipeline lagging, tick dropped / Demo 管線延遲，tick 已丟棄"
                                        );
                                    }
                                }
                                if let Some(ref ltx) = live_tx {
                                    if ltx.try_send(arc_event).is_err() {
                                        tracing::warn!(
                                            "fan-out: live pipeline lagging, tick dropped / Live 管線延遲，tick 已丟棄"
                                        );
                                    }
                                }
                            }
                            None => break,
                        }
                    }
                }
            }
            tracing::info!("fan-out task stopped / 扇出任務已停止");
        });
    }

    // ------------------------------------------------------------------
    // Spawn Paper pipeline (always starts)
    // 啟動 Paper 管線（始終啟動）
    // ------------------------------------------------------------------
    let paper_deps = EventConsumerDeps {
        pipeline_kind: PipelineKind::Paper,
        event_rx: paper_event_rx,
        config: Arc::clone(&config),
        cancel: cancel.clone(),
        initial_balance: paper_balance,
        paper_initial_balance: None,
        taker_fee_rate: live_bindings.as_ref().and_then(|b| b.taker_fee)
            .or_else(|| demo_bindings.as_ref().and_then(|b| b.taker_fee)),
        instruments: shared_instruments.clone(),
        bootstrap_client: shared_client.clone(), // Paper uses shared REST for kline bootstrap
        shared_client: None,
        bybit_balance: None,
        api_pnl: None,
        pipeline_cmd_rx: Some(paper_cmd_rx),
        market_data_tx: market_tx,
        feature_tx,
        last_tick_ms: Some(Arc::clone(&shared_last_tick_ms)),
        trading_tx: trading_tx.clone(),
        context_tx: context_tx.clone(),
        exchange_event_rx: None,
        seed_positions: Vec::new(), // Paper has no exchange-side positions to seed
        account_manager: None,
        linucb_runtime: Some(Arc::clone(&shared_linucb_runtime)),
        news_snapshot: Some(Arc::clone(&shared_news_snapshot)),
        risk_store: Some(Arc::clone(&risk_stores.paper)),
        budget_store: Some(Arc::clone(&budget_store)),
        audit_pool: db_pool.get().cloned(),
        symbol_registry: Some(Arc::clone(&symbol_registry)),
        scanner_store: Some(Arc::clone(&scanner_store)),
        shared_risk_level: Some(Arc::clone(&paper_risk_level)),
        is_primary: !has_live && !has_demo,
        ready_tx: Some(paper_ready_tx),
        global_exposure_usdt: None,
        cross_engine_tx: Some(cross_engine_tx.clone()),
        cross_engine_rx: Some(cross_engine_tx.subscribe()),
        pipeline_health: Some(Arc::clone(&paper_health)),
    };
    let paper_handle = tokio::spawn(run_event_consumer(paper_deps));
    info!("paper pipeline spawned / Paper 管線已啟動");

    // ------------------------------------------------------------------
    // Spawn Demo pipeline (conditional — if demo API key exists)
    // 啟動 Demo 管線（條件性 — 若 demo API key 存在）
    // ------------------------------------------------------------------
    let demo_handle: Option<tokio::task::JoinHandle<()>> = if let Some(demo_b) = demo_bindings {
        let (_, demo_event_rx) = demo_event_channel.expect("demo channel must exist");
        // B-1 Phase 2: capture seed_positions before move into deps below.
        // B-1 Phase 2：在 demo_b 被 move 進 deps 之前先取出 seed_positions。
        let demo_seed_positions = demo_b.seed_positions.clone();
        let demo_deps = EventConsumerDeps {
            pipeline_kind: PipelineKind::Demo,
            event_rx: demo_event_rx,
            config: Arc::clone(&config),
            cancel: cancel.clone(),
            initial_balance: demo_b.initial_balance,
            paper_initial_balance: None,
            taker_fee_rate: demo_b.taker_fee,
            instruments: shared_instruments.clone(),
            bootstrap_client: Some(Arc::clone(&demo_b.rest_client)),
            shared_client: Some(Arc::clone(&demo_b.rest_client)),
            bybit_balance: Some(demo_b.ws_bindings.bybit_balance),
            api_pnl: Some(demo_b.ws_bindings.api_pnl),
            pipeline_cmd_rx: demo_cmd_rx,
            // D19: Demo does not write market/feature DB (Paper handles that).
            market_data_tx: None,
            feature_tx: None,
            last_tick_ms: Some(Arc::clone(&shared_last_tick_ms)),
            trading_tx: trading_tx.clone(),
            context_tx: context_tx.clone(),
            exchange_event_rx: Some(demo_b.ws_bindings.exchange_event_rx),
            seed_positions: demo_seed_positions,
            account_manager: Some(demo_b.account_manager),
            linucb_runtime: Some(Arc::clone(&shared_linucb_runtime)),
            news_snapshot: Some(Arc::clone(&shared_news_snapshot)),
            risk_store: Some(Arc::clone(&risk_stores.demo)),
            budget_store: Some(Arc::clone(&budget_store)),
            audit_pool: db_pool.get().cloned(),
            symbol_registry: Some(Arc::clone(&symbol_registry)),
            scanner_store: Some(Arc::clone(&scanner_store)),
            shared_risk_level: Some(Arc::clone(&demo_b.risk_level)),
            is_primary: !has_live,
            ready_tx: demo_ready_tx,
            global_exposure_usdt: Some(Arc::clone(&global_exposure_usdt)),
            cross_engine_tx: Some(cross_engine_tx.clone()),
            cross_engine_rx: Some(cross_engine_tx.subscribe()),
            pipeline_health: Some(Arc::clone(&demo_b.health)),
        };
        let h = tokio::spawn(run_event_consumer(demo_deps));
        info!("demo pipeline spawned / Demo 管線已啟動");
        Some(h)
    } else {
        None
    };

    // ------------------------------------------------------------------
    // Spawn Live pipeline (conditional — D17: dedicated OS thread + catch_unwind)
    // 啟動 Live 管線（條件性 — D17：獨立 OS 線程 + catch_unwind）
    // ------------------------------------------------------------------
    let live_thread_handle: Option<std::thread::JoinHandle<()>> = if let Some(live_b) = live_bindings {
        let (_, live_event_rx) = live_event_channel.expect("live channel must exist");
        // B-1 Phase 2: capture seed_positions before move into deps below.
        // B-1 Phase 2：在 live_b 被 move 進 deps 之前先取出 seed_positions。
        let live_seed_positions = live_b.seed_positions.clone();
        let live_deps = EventConsumerDeps {
            pipeline_kind: PipelineKind::Live,
            event_rx: live_event_rx,
            config: Arc::clone(&config),
            cancel: cancel.clone(),
            initial_balance: live_b.initial_balance,
            paper_initial_balance: None,
            taker_fee_rate: live_b.taker_fee,
            instruments: shared_instruments.clone(),
            bootstrap_client: Some(Arc::clone(&live_b.rest_client)),
            shared_client: Some(Arc::clone(&live_b.rest_client)),
            bybit_balance: Some(live_b.ws_bindings.bybit_balance),
            api_pnl: Some(live_b.ws_bindings.api_pnl),
            pipeline_cmd_rx: live_cmd_rx,
            // D19: Live does not write market/feature DB.
            market_data_tx: None,
            feature_tx: None,
            last_tick_ms: Some(Arc::clone(&shared_last_tick_ms)),
            trading_tx: trading_tx.clone(),
            context_tx: context_tx.clone(),
            exchange_event_rx: Some(live_b.ws_bindings.exchange_event_rx),
            seed_positions: live_seed_positions,
            account_manager: Some(live_b.account_manager),
            linucb_runtime: Some(Arc::clone(&shared_linucb_runtime)),
            news_snapshot: Some(Arc::clone(&shared_news_snapshot)),
            risk_store: Some(Arc::clone(&risk_stores.live)),
            budget_store: Some(Arc::clone(&budget_store)),
            audit_pool: db_pool.get().cloned(),
            symbol_registry: Some(Arc::clone(&symbol_registry)),
            scanner_store: Some(Arc::clone(&scanner_store)),
            shared_risk_level: Some(Arc::clone(&live_b.risk_level)),
            is_primary: true,
            ready_tx: live_ready_tx,
            global_exposure_usdt: Some(Arc::clone(&global_exposure_usdt)),
            cross_engine_tx: Some(cross_engine_tx.clone()),
            cross_engine_rx: Some(cross_engine_tx.subscribe()),
            pipeline_health: Some(Arc::clone(&live_b.health)),
        };

        // D17: Live runs on dedicated OS thread with catch_unwind for panic isolation.
        // D17：Live 在獨立 OS 線程運行，catch_unwind 隔離 panic。
        let live_cancel = cancel.clone();
        let live_crash_tx = cross_engine_tx.clone();
        let live_health_ref = Arc::clone(&live_b.health);
        let thread_handle = std::thread::Builder::new()
            .name("oc-live-rt".into())
            .spawn(move || {
                // worker_threads(4): bumped from 2 (2026-04-11) after observing
                // 1808 "live pipeline lagging, tick dropped" warnings in a single
                // session. Live runs WS reader + tick consumer + dispatch task +
                // reconciler poller + private WS auth/heartbeat concurrently;
                // 2 workers serialized them too tightly and the bounded tick
                // channel overflowed under bursty market data. 4 workers gives
                // headroom while keeping Live's runtime isolated from main
                // (paper/demo + scanner + everything else still on default rt).
                // worker_threads(4)：2026-04-11 從 2 提升 — 一個 session 觀察到
                // 1808 條 "live pipeline lagging, tick dropped" 警告。Live 同時跑
                // WS reader + tick consumer + 派發任務 + reconciler poller + 私有
                // WS auth/heartbeat，2 workers 串行化過緊導致 bounded tick 通道
                // 在突發行情下溢出。4 workers 留出餘裕，仍保持 Live runtime 與
                // 主 runtime（paper/demo + scanner 等）的隔離。
                let live_rt = tokio::runtime::Builder::new_multi_thread()
                    .worker_threads(4)
                    .enable_all()
                    .thread_name("oc-live")
                    .build()
                    .expect("failed to build live runtime / 構建 live runtime 失敗");
                let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
                    live_rt.block_on(async {
                        run_event_consumer(live_deps).await;
                        live_cancel.cancelled().await;
                    });
                }));
                if let Err(panic_info) = result {
                    let msg = panic_info
                        .downcast_ref::<&str>()
                        .copied()
                        .or_else(|| panic_info.downcast_ref::<String>().map(|s| s.as_str()))
                        .unwrap_or("unknown panic");
                    tracing::error!(
                        kind = "live",
                        panic = msg,
                        "M-4: live pipeline PANICKED — broadcasting Crashed / Live 管線 panic — 廣播 Crashed"
                    );
                    live_health_ref.store(
                        PipelineHealth::Down as u8,
                        std::sync::atomic::Ordering::Relaxed,
                    );
                    let _ = live_crash_tx
                        .send(EngineEvent::Crashed(PipelineKind::Live));
                }
            })
            .expect("failed to spawn live thread / 啟動 live 線程失敗");

        info!("live pipeline spawned (dedicated OS thread) / Live 管線已啟動（獨立 OS 線程）");
        Some(thread_handle)
    } else {
        None
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
    // Signal handling / 信號處理
    // ------------------------------------------------------------------
    signal_loop(&config, &cancel).await;

    // ------------------------------------------------------------------
    // MAJOR-3: Ordered shutdown sequence (Live → Demo → Paper)
    // MAJOR-3：有序關閉序列（Live → Demo → Paper）
    // ------------------------------------------------------------------
    info!("initiating shutdown / 開始關閉序列");

    cancel.cancel();

    let shutdown_timeout = tokio::time::Duration::from_secs(10);
    let _ = tokio::time::timeout(shutdown_timeout, async {
        let _ = ws_handle.await;
        let _ = ipc_handle.await;

        // D17: Join Live OS thread first.
        // D17：先等待 Live OS 線程結束。
        if let Some(th) = live_thread_handle {
            info!("joining live runtime thread / 等待 live runtime 線程結束");
            let _ = th.join();
        }

        // Demo pipeline (tokio task).
        if let Some(dh) = demo_handle {
            info!("draining demo pipeline / 排空 Demo 管線");
            match dh.await {
                Err(e) if e.is_panic() => {
                    error!("demo pipeline panicked during shutdown / Demo 管線關閉時 panic")
                }
                _ => {}
            }
        }

        // Paper pipeline (tokio task).
        info!("draining paper pipeline / 排空 Paper 管線");
        match paper_handle.await {
            Err(e) if e.is_panic() => {
                error!("paper pipeline panicked during shutdown / Paper 管線關閉時 panic")
            }
            _ => {}
        }
    })
    .await;

    // Clean up socket file
    let socket_path = &config.get().ipc_socket_path;
    if std::path::Path::new(socket_path).exists() {
        let _ = tokio::fs::remove_file(socket_path).await;
        info!(
            path = socket_path,
            "socket file cleaned up / 套接字文件已清理"
        );
    }

    info!(version = VERSION, "engine stopped / 引擎已停止");
}
