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
    // Start IPC server / 啟動 IPC 服務器
    // ------------------------------------------------------------------
    let ipc_data_dir =
        std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into());
    let (primary_cmd_tx, pipeline_cmd_rx) = tokio::sync::mpsc::unbounded_channel();
    let phase4_consumer_cmd_tx = primary_cmd_tx.clone();
    let scanner_pipeline_cmd_tx = primary_cmd_tx.clone();
    let reconciler_cmd_tx = primary_cmd_tx.clone();
    // Phase 6: shared atomic for reconciler to read current risk level without IPC.
    // Phase 6：共享原子量供對帳器無 IPC 讀取當前風控級別。
    let shared_risk_level = Arc::new(std::sync::atomic::AtomicU8::new(
        openclaw_core::sm::risk_gov::RiskLevel::Normal.value(),
    ));
    // 3E-3: Paper-alongside command channel
    let (pipeline_cmd_tx_paper, pipeline_cmd_rx_paper) = tokio::sync::mpsc::unbounded_channel();
    let mut ipc_server = IpcServer::new(
        Arc::clone(&config),
        cancel.clone(),
        ipc_data_dir,
        {
            // 3E-10.1: Build EngineCommandChannels based on API key detection.
            use openclaw_engine::ipc_server::EngineCommandChannels;
            let ipc_primary_kind = determine_primary_kind();
            let mut channels = EngineCommandChannels::default();
            match ipc_primary_kind.db_mode() {
                "paper" => {
                    channels.paper = Some(primary_cmd_tx.clone());
                }
                "demo" => {
                    channels.demo = Some(primary_cmd_tx.clone());
                    channels.paper = Some(pipeline_cmd_tx_paper.clone());
                }
                "live" => {
                    channels.live = Some(primary_cmd_tx.clone());
                    channels.paper = Some(pipeline_cmd_tx_paper.clone());
                }
                _ => {
                    channels.paper = Some(primary_cmd_tx.clone());
                }
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
    // Bybit API integration — DCP, auto-margin, fee rates (Items 2/7/8)
    // Bybit API 整合 — 斷連保護、自動追加保證金、動態費率
    // ------------------------------------------------------------------
    let mut api_taker_fee: Option<f64> = None;
    let mut api_credentials: Option<(String, String)> = None;
    let mut shared_client: Option<Arc<BybitRestClient>> = None;
    let mut shared_instruments: Option<Arc<openclaw_engine::instrument_info::InstrumentInfoCache>> =
        None;
    let mut shared_account_manager: Option<Arc<AccountManager>> = None;
    let cfg_snapshot = config.get();
    let primary_kind_early = determine_primary_kind();
    let bybit_env = match primary_kind_early {
        PipelineKind::Live => live_bybit_environment(),
        PipelineKind::Demo | PipelineKind::Paper => BybitEnvironment::Demo,
    };

    let initial_balance = fetch_exchange_balance(bybit_env).await;

    // MAJOR-4: Paper balance uses unified priority.
    let paper_initial_balance: Option<f64> = if primary_kind_early == PipelineKind::Live {
        Some(resolve_paper_initial_balance().await)
    } else {
        None
    };

    if let Ok(rest_client) = BybitRestClient::new(bybit_env, None, None) {
        if rest_client.has_credentials() {
            let (key, secret) = rest_client.credentials();
            api_credentials = Some((key.to_string(), secret.to_string()));
            let client_arc = Arc::new(rest_client);
            shared_client = Some(Arc::clone(&client_arc));

            // R-05: Load instrument info cache
            let instrument_cache =
                Arc::new(openclaw_engine::instrument_info::InstrumentInfoCache::new());
            match instrument_cache.refresh(&*client_arc, "linear").await {
                Ok(count) => {
                    shared_instruments = Some(Arc::clone(&instrument_cache));
                    info!(symbols = count, "instrument info loaded / 品種規格已加載");
                }
                Err(e) => warn!(error = %e, "instrument info fetch failed / 品種規格加載失敗"),
            }

            // Item 8: DCP — Disconnected Cancel Protection
            if cfg_snapshot.dcp_enabled {
                use openclaw_engine::platform_client::PlatformClient;
                let platform = PlatformClient::new(Arc::clone(&client_arc));
                match platform.set_dcp(cfg_snapshot.dcp_time_window).await {
                    Ok(()) => info!(
                        window = cfg_snapshot.dcp_time_window,
                        "DCP enabled / DCP 已啟用"
                    ),
                    Err(e) => {
                        warn!(error = %e, "DCP setup failed (non-fatal) / DCP 設定失敗（非致命）")
                    }
                }
            }

            // Item 7: Auto-add-margin for existing positions
            if cfg_snapshot.auto_add_margin {
                use openclaw_engine::order_manager::OrderCategory;
                use openclaw_engine::position_manager::PositionManager;
                let pos_mgr = PositionManager::new(Arc::clone(&client_arc));
                match pos_mgr.get_positions(OrderCategory::Linear, None).await {
                    Ok(positions) => {
                        for pos in &positions {
                            if pos.size > 0.0 {
                                match pos_mgr
                                    .set_auto_add_margin(
                                        OrderCategory::Linear,
                                        &pos.symbol,
                                        1,
                                        None,
                                    )
                                    .await
                                {
                                    Ok(()) => {
                                        info!(symbol = %pos.symbol, "auto-margin enabled / 自動追保已啟用")
                                    }
                                    Err(e) => {
                                        warn!(symbol = %pos.symbol, error = %e, "auto-margin failed / 自動追保失敗")
                                    }
                                }
                            }
                        }
                    }
                    Err(e) => {
                        warn!(error = %e, "failed to query positions for auto-margin / 查詢倉位失敗")
                    }
                }
            }

            // Item 2: Fetch dynamic per-symbol fee rates
            let acct = Arc::new(AccountManager::new());
            match acct.refresh_fee_rates(&*client_arc, "linear").await {
                Ok(count) => {
                    let rate = acct.taker_fee("BTCUSDT");
                    api_taker_fee = Some(rate);
                    info!(
                        symbols = count,
                        taker_rate = format!("{:.5}", rate),
                        "fee rates loaded / 費率已加載"
                    );
                }
                Err(e) => {
                    warn!(error = %e, "fee rate fetch failed, using defaults / 費率獲取失敗，使用默認值")
                }
            }
            shared_account_manager = Some(Arc::clone(&acct));

            // Spawn fee rate refresh + staleness monitor
            tasks::spawn_fee_rate_tasks(&acct, &client_arc, &cancel);
        } else {
            info!(
                "no Bybit credentials — skipping DCP/margin/fee setup / 無 API 憑證，跳過 API 設定"
            );
        }
    } else {
        info!(
            "Bybit client init failed — skipping API setup / Bybit 客戶端初始化失敗，跳過 API 設定"
        );
    }

    // R-05: Periodic instrument info refresh (every 4 hours)
    if let (Some(ref icache), Some(ref client)) = (&shared_instruments, &shared_client) {
        tasks::spawn_instrument_refresh(icache, client, &cancel);
    }

    // ------------------------------------------------------------------
    // Scanner D4: Spawn ScannerRunner (requires market REST client)
    // 掃描器 D4：啟動 ScannerRunner（需要市場 REST 客戶端）
    // ------------------------------------------------------------------
    if let Some(ref client) = shared_client {
        let market_client = Arc::new(MarketDataClient::new(Arc::clone(client)));
        let runner = ScannerRunner::new(
            Arc::clone(&symbol_registry),
            market_client,
            Arc::clone(&scanner_edge_estimates),
            Arc::clone(&scanner_store),
            scanner_ws_tx,
            scanner_pipeline_cmd_tx,
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

    // ------------------------------------------------------------------
    // 3E D21: Per-pipeline private WS supervisor
    // ------------------------------------------------------------------
    let primary_ws_bindings: Option<startup::PrivateWsBindings> =
        if let Some((api_key, api_secret)) = api_credentials {
            Some(spawn_private_ws_supervisor(
                api_key,
                api_secret,
                bybit_env,
                match bybit_env {
                    BybitEnvironment::Demo | BybitEnvironment::Testnet => "demo",
                    BybitEnvironment::Mainnet | BybitEnvironment::LiveDemo => "live",
                },
                cancel.clone(),
            ))
        } else {
            info!("no credentials — Private WS skipped / 無憑證，跳過私有 WS");
            None
        };

    let (shared_bybit_balance, shared_api_pnl, shared_exchange_event_rx) = match primary_ws_bindings
    {
        Some(bindings) => (
            Some(Arc::clone(&bindings.bybit_balance)),
            Some(Arc::clone(&bindings.api_pnl)),
            Some(bindings.exchange_event_rx),
        ),
        None => (None, None, None),
    };

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
    // Phase 6: spawn position reconciler with auto-contraction action layer.
    // Phase 6：spawn 持倉對帳器（含自動降級動作層）。
    // ------------------------------------------------------------------
    if let Some(client) = shared_client.as_ref() {
        tasks::spawn_position_reconciler(
            client,
            &db_pool,
            &cancel,
            reconciler_cmd_tx,
            &shared_instruments,
            &shared_risk_level,
            bybit_env,
        );
    } else {
        info!("position_reconciler skipped (no REST client) / 持倉對帳器跳過（無 REST 客戶端）");
    }

    // ------------------------------------------------------------------
    // 3E-2b-α: Multi-pipeline spawn skeleton + bounded fan-out
    // ------------------------------------------------------------------
    use openclaw_engine::event_consumer::{run_event_consumer, EventConsumerDeps};

    let primary_kind = determine_primary_kind();
    let spawn_paper_alongside = primary_kind != PipelineKind::Paper;

    // 3E D10/D20: Bounded fan-out — one WS source, N pipeline receivers.
    let primary_buf = if primary_kind == PipelineKind::Live { 512 } else { 1024 };
    let (primary_event_tx, primary_event_rx) = mpsc::channel::<Arc<PriceEvent>>(primary_buf);
    let paper_alongside_channel: Option<(
        mpsc::Sender<Arc<PriceEvent>>,
        mpsc::Receiver<Arc<PriceEvent>>,
    )> = if spawn_paper_alongside {
        Some(mpsc::channel(1024))
    } else {
        None
    };

    // MAJOR-2: Create ready channels so fan-out waits for pipeline initialization.
    let (primary_ready_tx, primary_ready_rx) = tokio::sync::oneshot::channel::<()>();
    let (paper_ready_tx, paper_ready_rx) = if spawn_paper_alongside {
        let (tx, rx) = tokio::sync::oneshot::channel::<()>();
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };

    // Fan-out task: read from single event_rx, broadcast Arc-wrapped events.
    {
        let primary_tx = primary_event_tx;
        let paper_tx = paper_alongside_channel
            .as_ref()
            .map(|(tx, _)| tx.clone());
        let fan_cancel = cancel.clone();
        tokio::spawn(async move {
            let barrier_timeout = tokio::time::Duration::from_secs(60);
            let barrier_result = tokio::time::timeout(barrier_timeout, async {
                let _ = primary_ready_rx.await;
                if let Some(rx) = paper_ready_rx {
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
                                if primary_tx.try_send(Arc::clone(&arc_event)).is_err() {
                                    tracing::warn!(
                                        kind = %primary_kind,
                                        "fan-out: primary pipeline lagging, tick dropped / 主管線延遲，tick 已丟棄"
                                    );
                                }
                                if let Some(ref ptx) = paper_tx {
                                    if ptx.try_send(arc_event).is_err() {
                                        tracing::debug!(
                                            "fan-out: paper pipeline lagging, tick dropped / Paper 管線延遲，tick 已丟棄"
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
    // Per-pipeline command channels + risk level atomics
    // ------------------------------------------------------------------
    let pipeline_cmd_rx_paper_opt = if spawn_paper_alongside {
        Some(pipeline_cmd_rx_paper)
    } else {
        None
    };
    let paper_risk_level: Option<Arc<std::sync::atomic::AtomicU8>> = if spawn_paper_alongside {
        Some(Arc::new(std::sync::atomic::AtomicU8::new(
            openclaw_core::sm::risk_gov::RiskLevel::Normal.value(),
        )))
    } else {
        None
    };

    // BLOCKER-3 D15: Shared cross-engine global exposure atomic.
    let global_exposure_usdt = Arc::new(std::sync::atomic::AtomicU64::new(0));

    // BLOCKER-2 D6: Cross-engine event broadcast channel + per-pipeline health atomics.
    let (cross_engine_tx, _) = tokio::sync::broadcast::channel::<EngineEvent>(16);
    let primary_health = Arc::new(std::sync::atomic::AtomicU8::new(
        PipelineHealth::Running as u8,
    ));
    let paper_health: Option<Arc<std::sync::atomic::AtomicU8>> = if spawn_paper_alongside {
        Some(Arc::new(std::sync::atomic::AtomicU8::new(
            PipelineHealth::Running as u8,
        )))
    } else {
        None
    };

    // ------------------------------------------------------------------
    // Spawn primary pipeline
    // ------------------------------------------------------------------
    let primary_deps = EventConsumerDeps {
        pipeline_kind: primary_kind,
        event_rx: primary_event_rx,
        config: Arc::clone(&config),
        cancel: cancel.clone(),
        initial_balance,
        paper_initial_balance,
        taker_fee_rate: api_taker_fee,
        instruments: shared_instruments.clone(),
        bootstrap_client: shared_client.as_ref().map(Arc::clone),
        shared_client: shared_client.clone(),
        bybit_balance: shared_bybit_balance,
        api_pnl: shared_api_pnl,
        pipeline_cmd_rx: Some(pipeline_cmd_rx),
        market_data_tx: if primary_kind == PipelineKind::Paper { market_tx.clone() } else { None },
        feature_tx: if primary_kind == PipelineKind::Paper { feature_tx.clone() } else { None },
        last_tick_ms: Some(Arc::clone(&shared_last_tick_ms)),
        trading_tx: trading_tx.clone(),
        context_tx: context_tx.clone(),
        exchange_event_rx: shared_exchange_event_rx,
        account_manager: shared_account_manager.clone(),
        linucb_runtime: Some(Arc::clone(&shared_linucb_runtime)),
        news_snapshot: Some(Arc::clone(&shared_news_snapshot)),
        risk_store: {
            let store = match primary_kind {
                PipelineKind::Live => Arc::clone(&risk_stores.live),
                PipelineKind::Demo => Arc::clone(&risk_stores.demo),
                PipelineKind::Paper => Arc::clone(&risk_stores.paper),
            };
            Some(store)
        },
        budget_store: Some(Arc::clone(&budget_store)),
        audit_pool: db_pool.get().cloned(),
        symbol_registry: Some(Arc::clone(&symbol_registry)),
        scanner_store: Some(Arc::clone(&scanner_store)),
        shared_risk_level: Some(Arc::clone(&shared_risk_level)),
        is_primary: true,
        ready_tx: Some(primary_ready_tx),
        global_exposure_usdt: if primary_kind.is_exchange() {
            Some(Arc::clone(&global_exposure_usdt))
        } else {
            None
        },
        cross_engine_tx: Some(cross_engine_tx.clone()),
        cross_engine_rx: Some(cross_engine_tx.subscribe()),
        pipeline_health: Some(Arc::clone(&primary_health)),
    };

    // BLOCKER-4 D17: Live pipeline → dedicated runtime; Demo/Paper → shared runtime.
    let event_handle: tokio::task::JoinHandle<()>;
    let _live_thread_handle: Option<std::thread::JoinHandle<()>>;

    if primary_kind == PipelineKind::Live {
        let live_cancel = cancel.clone();
        let live_crash_tx = cross_engine_tx.clone();
        let thread_handle = std::thread::Builder::new()
            .name("oc-live-rt".into())
            .spawn(move || {
                let live_rt = tokio::runtime::Builder::new_multi_thread()
                    .worker_threads(2)
                    .enable_all()
                    .thread_name("oc-live")
                    .build()
                    .expect("failed to build live runtime / 構建 live runtime 失敗");
                live_rt.block_on(async {
                    run_event_consumer(primary_deps).await;
                    live_cancel.cancelled().await;
                });
            })
            .expect("failed to spawn live thread / 啟動 live 線程失敗");

        let shutdown_cancel = cancel.clone();
        event_handle = tokio::spawn(async move {
            shutdown_cancel.cancelled().await;
            drop(live_crash_tx);
        });
        _live_thread_handle = Some(thread_handle);
    } else {
        let crash_tx = cross_engine_tx.clone();
        let crash_kind = primary_kind;
        event_handle = tokio::spawn(async move {
            run_event_consumer(primary_deps).await;
            let _ = crash_tx;
            let _ = crash_kind;
        });
        _live_thread_handle = None;
    }
    info!(kind = %primary_kind, "primary pipeline spawned / 主管線已啟動");

    // ------------------------------------------------------------------
    // Spawn Paper-alongside pipeline (when primary is Demo or Live)
    // ------------------------------------------------------------------
    let _paper_handle = if spawn_paper_alongside {
        let (_, paper_event_rx) = paper_alongside_channel.unwrap();
        let pipeline_cmd_rx_paper = pipeline_cmd_rx_paper_opt.unwrap();
        let paper_rl = paper_risk_level.unwrap();
        let paper_balance = paper_initial_balance.unwrap_or(initial_balance);
        let deps = EventConsumerDeps {
            pipeline_kind: PipelineKind::Paper,
            event_rx: paper_event_rx,
            config: Arc::clone(&config),
            cancel: cancel.clone(),
            initial_balance: paper_balance,
            paper_initial_balance: None,
            taker_fee_rate: api_taker_fee,
            instruments: shared_instruments.clone(),
            bootstrap_client: None,
            shared_client: None,
            bybit_balance: None,
            api_pnl: None,
            pipeline_cmd_rx: Some(pipeline_cmd_rx_paper),
            market_data_tx: market_tx,
            feature_tx,
            last_tick_ms: Some(Arc::clone(&shared_last_tick_ms)),
            trading_tx,
            context_tx,
            exchange_event_rx: None,
            account_manager: None,
            linucb_runtime: Some(Arc::clone(&shared_linucb_runtime)),
            news_snapshot: Some(Arc::clone(&shared_news_snapshot)),
            risk_store: Some(Arc::clone(&risk_stores.paper)),
            budget_store: Some(Arc::clone(&budget_store)),
            audit_pool: db_pool.get().cloned(),
            symbol_registry: Some(Arc::clone(&symbol_registry)),
            scanner_store: Some(Arc::clone(&scanner_store)),
            shared_risk_level: Some(paper_rl),
            is_primary: false,
            ready_tx: paper_ready_tx,
            global_exposure_usdt: None,
            cross_engine_tx: Some(cross_engine_tx.clone()),
            cross_engine_rx: Some(cross_engine_tx.subscribe()),
            pipeline_health: paper_health,
        };
        let h = tokio::spawn(run_event_consumer(deps));
        info!("paper-alongside pipeline spawned / Paper 伴隨管線已啟動");
        Some(h)
    } else {
        None
    };

    info!(version = VERSION, "engine started / 引擎已啟動");

    // ------------------------------------------------------------------
    // Signal handling / 信號處理
    // ------------------------------------------------------------------
    signal_loop(&config, &cancel).await;

    // ------------------------------------------------------------------
    // MAJOR-3: Ordered shutdown sequence (Live → Demo → Paper)
    // ------------------------------------------------------------------
    info!("initiating shutdown / 開始關閉序列");

    cancel.cancel();

    let shutdown_timeout = tokio::time::Duration::from_secs(10);
    let _ = tokio::time::timeout(shutdown_timeout, async {
        let _ = ws_handle.await;
        let _ = ipc_handle.await;

        if spawn_paper_alongside {
            info!(kind = %primary_kind, "draining primary pipeline / 排空主管線");
            let _ = event_handle.await;

            if let Some(ph) = _paper_handle {
                info!("draining paper-alongside pipeline / 排空 Paper 伴隨管線");
                let _ = ph.await;
            }
        } else {
            let _ = event_handle.await;
        }
    })
    .await;

    // BLOCKER-4 D17: Join the dedicated Live thread if it was spawned.
    if let Some(th) = _live_thread_handle {
        info!("joining live runtime thread / 等待 live runtime 線程結束");
        let _ = th.join();
    }

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
