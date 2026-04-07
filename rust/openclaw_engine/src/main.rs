//! OpenClaw Engine entry point — tokio runtime, signal handling, startup/shutdown (R01-2).
//! OpenClaw 引擎入口 — tokio 運行時、信號處理、啟動/關閉序列。
//!
//! MODULE_NOTE (EN): Sets up multi-thread tokio runtime for IPC + WS + background tasks.
//!   SIGHUP triggers config hot-reload. SIGTERM/SIGINT triggers graceful shutdown.
//!   Event consumer feeds PriceEvents into TickPipeline for paper trading.
//! MODULE_NOTE (中): 設置多線程 tokio 運行時用於 IPC + WS + 後台任務。
//!   SIGHUP 觸發配置熱加載。SIGTERM/SIGINT 觸發優雅關閉。
//!   事件消費者將 PriceEvent 送入 TickPipeline 進行紙盤交易。

use openclaw_engine::account_manager::AccountManager;
use openclaw_engine::bybit_rest_client::{BybitEnvironment, BybitRestClient};
use openclaw_engine::config::{
    load_toml_or_default, BudgetConfig, ConfigManager, ConfigStore, LearningConfig, RiskConfig,
};
use openclaw_engine::event_consumer::SYMBOLS;
use openclaw_engine::ipc_server::IpcServer;
use openclaw_engine::strategies::{
    bb_breakout::BbBreakout, bb_reversion::BbReversion, grid_trading::GridTrading,
    ma_crossover::MaCrossover,
};
use openclaw_engine::tick_pipeline::TickPipeline;
use openclaw_engine::ws_client::WsClient;
use openclaw_types::PriceEvent;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

/// Engine version from Cargo.toml / 引擎版本（來自 Cargo.toml）
const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Price event channel buffer size / 價格事件通道緩衝區大小
const EVENT_CHANNEL_SIZE: usize = 4096;

// SYMBOLS moved to event_consumer.rs (Phase 1 Day 0-A extraction)
// STATUS_INTERVAL_SECS moved to event_consumer.rs

/// Read paper balance from env var or use default.
/// 從環境變量讀取紙盤餘額，若未設定則使用預設值。
fn paper_balance_from_env() -> Option<f64> {
    std::env::var("OPENCLAW_PAPER_BALANCE")
        .ok()
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|&b| b > 0.0)
}

/// Fetch USDT balance from Bybit Demo account via REST API.
/// 通過 REST API 從 Bybit Demo 帳戶讀取 USDT 餘額。
///
/// Falls back to env var OPENCLAW_PAPER_BALANCE, then $10,000 default.
/// 回退順序：環境變量 → $10,000 預設值。
async fn fetch_demo_balance() -> f64 {
    // 1. Explicit env var override takes precedence
    // 明確的環境變量覆蓋優先
    if let Some(env_bal) = paper_balance_from_env() {
        info!(
            balance = format!("{:.2}", env_bal),
            "using OPENCLAW_PAPER_BALANCE env override / 使用環境變量覆蓋餘額"
        );
        return env_bal;
    }

    // 2. Try reading from Bybit Demo API
    // 嘗試從 Bybit Demo API 讀取
    match BybitRestClient::new(BybitEnvironment::Demo, None, None) {
        Ok(client) if client.has_credentials() => {
            let acct = AccountManager::new();
            match acct.refresh_balance(&client).await {
                Ok(_) => {
                    let bal = acct.usdt_wallet_balance();
                    if bal > 0.0 {
                        info!(
                            balance = format!("{:.2}", bal),
                            "fetched Bybit Demo USDT balance / 已從 Bybit Demo 讀取 USDT 餘額"
                        );
                        return bal;
                    }
                    warn!("Bybit Demo USDT balance is 0, using default / Demo USDT 餘額為 0，使用預設值");
                }
                Err(e) => {
                    warn!(error = %e, "failed to fetch Bybit Demo balance, using default / 讀取 Demo 餘額失敗");
                }
            }
        }
        Ok(_) => {
            info!("no Bybit API credentials — using default balance / 無 API 憑證，使用預設餘額");
        }
        Err(e) => {
            warn!(error = %e, "failed to create Bybit client / 創建 Bybit 客戶端失敗");
        }
    }

    // 3. Fallback default
    let default = 10_000.0;
    info!(
        balance = format!("{:.2}", default),
        "using default paper balance / 使用預設紙盤餘額"
    );
    default
}

/// Parse replay CLI arguments from std::env::args().
/// 從命令行參數解析 replay 模式選項。
struct ReplayArgs {
    enabled: bool,
    input_path: Option<String>,
    output_path: Option<String>,
}

fn parse_replay_args() -> ReplayArgs {
    let args: Vec<String> = std::env::args().collect();
    let mut replay = ReplayArgs {
        enabled: false,
        input_path: None,
        output_path: None,
    };
    let mut i = 1;
    while i < args.len() {
        match args[i].as_str() {
            "--replay-mode" => replay.enabled = true,
            "--replay-input" => {
                i += 1;
                if i < args.len() {
                    replay.input_path = Some(args[i].clone());
                }
            }
            "--replay-output" => {
                i += 1;
                if i < args.len() {
                    replay.output_path = Some(args[i].clone());
                }
            }
            _ => {} // ignore unknown args / 忽略未知參數
        }
        i += 1;
    }
    replay
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
    //     TOML paths configurable via env overrides; fall back to settings/.
    //     ARCH-RC1 1C-2：載入 3 個統一 Config 並包入 ConfigStore。
    //     TOML 路徑可用環境變數覆蓋，否則使用 settings/。
    // ------------------------------------------------------------------
    let (risk_store, learning_store, budget_store) = match load_unified_configs() {
        Ok(s) => s,
        Err(e) => {
            error!(error = %e, "failed to load unified configs / 統一配置加載失敗");
            std::process::exit(1);
        }
    };
    // learning_store currently has no consumer (LearningConfig IPC endpoints
    // land in 1C-2-C). Keep the binding alive so the store doesn't drop.
    // learning_store 目前沒有消費者（LearningConfig IPC 端點在 1C-2-C），
    // 保留綁定以免 store 被釋放。
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
        risk_store,
        learning_store,
        budget_store,
    ));
}

/// ARCH-RC1 1C-2-A: Load RiskConfig / LearningConfig / BudgetConfig from
/// their TOML files, wrapping each in an `Arc<ConfigStore<T>>`. Paths resolve
/// to `settings/risk_control_rules/{risk,learning,budget}_config.toml` by
/// default; individual env vars override each path.
/// ARCH-RC1 1C-2-A：從 TOML 載入 3 個統一 Config，各自包入 Arc<ConfigStore>。
/// 預設路徑為 settings/risk_control_rules/；可用環境變數覆蓋個別路徑。
#[allow(clippy::type_complexity)]
fn load_unified_configs() -> Result<
    (
        Arc<ConfigStore<RiskConfig>>,
        Arc<ConfigStore<LearningConfig>>,
        Arc<ConfigStore<BudgetConfig>>,
    ),
    String,
> {
    use std::path::PathBuf;

    let base = std::env::var("OPENCLAW_RISK_CONFIG_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("settings/risk_control_rules"));
    let risk_path = std::env::var("OPENCLAW_RISK_CONFIG")
        .map(PathBuf::from)
        .unwrap_or_else(|_| base.join("risk_config.toml"));
    let learning_path = std::env::var("OPENCLAW_LEARNING_CONFIG")
        .map(PathBuf::from)
        .unwrap_or_else(|_| base.join("learning_config.toml"));
    let budget_path = std::env::var("OPENCLAW_BUDGET_CONFIG")
        .map(PathBuf::from)
        .unwrap_or_else(|_| base.join("budget_config.toml"));

    info!(
        risk = %risk_path.display(),
        learning = %learning_path.display(),
        budget = %budget_path.display(),
        "loading ARCH-RC1 unified configs / 載入 ARCH-RC1 統一配置"
    );

    let risk: RiskConfig = load_toml_or_default(&risk_path, |c: &RiskConfig| c.validate())
        .map_err(|e| format!("risk config: {}", e))?;
    let learning: LearningConfig =
        load_toml_or_default(&learning_path, |c: &LearningConfig| c.validate())
            .map_err(|e| format!("learning config: {}", e))?;
    let budget: BudgetConfig = load_toml_or_default(&budget_path, |c: &BudgetConfig| c.validate())
        .map_err(|e| format!("budget config: {}", e))?;

    info!(
        risk_version = risk.meta.version,
        learning_version = learning.meta.version,
        budget_version = budget.meta.version,
        "ARCH-RC1 unified configs loaded / 統一配置已載入"
    );

    Ok((
        Arc::new(ConfigStore::new(risk)),
        Arc::new(ConfigStore::new(learning)),
        Arc::new(ConfigStore::new(budget)),
    ))
}

/// Run the engine in replay mode: read historical ticks from JSONL,
/// process through TickPipeline, write CanaryRecords to output JSONL.
/// No WS connection, no IPC, no paper auth needed.
/// 回放模式：從 JSONL 讀取歷史 tick，通過 TickPipeline 處理，
/// 將 CanaryRecord 寫入輸出 JSONL。無需 WS 連線、IPC 或紙盤授權。
fn run_replay_mode(args: ReplayArgs) {
    use std::io::{BufRead, BufWriter, Write};

    let input_path = args.input_path.unwrap_or_else(|| {
        error!("--replay-input is required / --replay-input 為必填參數");
        std::process::exit(1);
    });
    let output_path = args.output_path.unwrap_or_else(|| {
        error!("--replay-output is required / --replay-output 為必填參數");
        std::process::exit(1);
    });

    info!(
        input = %input_path,
        output = %output_path,
        "replay: reading ticks / 回放：讀取 tick 數據"
    );

    // ------------------------------------------------------------------
    // 1. Build pipeline with same strategies as live mode
    //    構建與即時模式相同策略的管線
    // ------------------------------------------------------------------
    let mut pipeline = TickPipeline::new(SYMBOLS);

    // Register strategies (identical to live mode) / 註冊策略（與即時模式一致）
    pipeline.orchestrator.register(Box::new(MaCrossover::new()));
    pipeline.orchestrator.register(Box::new(BbReversion::new()));
    pipeline.orchestrator.register(Box::new(BbBreakout::new()));
    pipeline
        .orchestrator
        .register(Box::new(GridTrading::new_adaptive()));

    // Grant paper authorization / 授予紙盤授權
    match pipeline.grant_paper_auth() {
        Ok(()) => info!("replay: paper authorization granted / 回放：紙盤授權已授予"),
        Err(e) => {
            error!(error = %e, "replay: failed to grant paper auth / 回放：紙盤授權失敗");
            std::process::exit(1);
        }
    }

    let strategies = pipeline.orchestrator.active_strategy_names().join(", ");
    info!(
        strategies = %strategies,
        "replay: pipeline ready / 回放：管線就緒"
    );

    // ------------------------------------------------------------------
    // 2. Read input JSONL and process each tick
    //    讀取輸入 JSONL 並處理每個 tick
    // ------------------------------------------------------------------
    let in_file = match std::fs::File::open(&input_path) {
        Ok(f) => f,
        Err(e) => {
            error!(error = %e, path = %input_path, "replay: cannot open input / 回放：無法打開輸入文件");
            std::process::exit(1);
        }
    };
    let reader = std::io::BufReader::new(in_file);

    let out_file = match std::fs::File::create(&output_path) {
        Ok(f) => f,
        Err(e) => {
            error!(error = %e, path = %output_path, "replay: cannot create output / 回放：無法創建輸出文件");
            std::process::exit(1);
        }
    };
    let mut writer = BufWriter::new(out_file);

    let mut tick_count: u64 = 0;
    let mut record_count: u64 = 0;
    let start = std::time::Instant::now();

    for line_result in reader.lines() {
        let line = match line_result {
            Ok(l) => l,
            Err(e) => {
                warn!(error = %e, "replay: skipping unreadable line / 回放：跳過無法讀取的行");
                continue;
            }
        };
        let trimmed = line.trim();
        if trimmed.is_empty() {
            continue;
        }

        // Parse line as PriceEvent (format matches synthesize_ticks output)
        // 將行解析為 PriceEvent（格式匹配 synthesize_ticks 輸出）
        let event: PriceEvent = match serde_json::from_str(trimmed) {
            Ok(ev) => ev,
            Err(e) => {
                warn!(
                    error = %e,
                    line_num = tick_count + 1,
                    "replay: skipping unparseable tick / 回放：跳過無法解析的 tick"
                );
                continue;
            }
        };

        tick_count += 1;

        // Feed through pipeline / 送入管線處理
        if let Some(record) = pipeline.feed_replay_tick(&event) {
            if let Ok(json) = serde_json::to_string(&record) {
                let _ = writeln!(writer, "{}", json);
                record_count += 1;
            }
        }

        // Progress log every 10000 ticks / 每 10000 個 tick 記錄進度
        if tick_count % 10_000 == 0 {
            info!(
                ticks = tick_count,
                records = record_count,
                "replay: progress / 回放：進度"
            );
        }
    }

    // Flush output / 刷新輸出
    let _ = writer.flush();

    let elapsed = start.elapsed();
    info!(
        ticks = tick_count,
        records = record_count,
        elapsed_ms = elapsed.as_millis() as u64,
        fills = pipeline.stats.total_fills,
        intents = pipeline.stats.total_intents,
        output = %output_path,
        "replay complete / 回放完成"
    );
}

/// Async entry point running inside the multi-thread runtime.
/// 在多線程運行時內執行的異步入口。
async fn async_main(
    config: Arc<ConfigManager>,
    risk_store: Arc<ConfigStore<RiskConfig>>,
    learning_store: Arc<ConfigStore<LearningConfig>>,
    budget_store: Arc<ConfigStore<BudgetConfig>>,
) {
    let cancel = CancellationToken::new();

    // ------------------------------------------------------------------
    // Fetch initial balance from Bybit Demo API (or env / default)
    // 從 Bybit Demo API 讀取初始餘額（或環境變量 / 預設值）
    // ------------------------------------------------------------------
    let initial_balance = fetch_demo_balance().await;

    // ------------------------------------------------------------------
    // Price event channel / 價格事件通道
    // ------------------------------------------------------------------
    let (event_tx, event_rx) = mpsc::channel::<PriceEvent>(EVENT_CHANNEL_SIZE);

    // ------------------------------------------------------------------
    // Start IPC server / 啟動 IPC 服務器
    // ------------------------------------------------------------------
    // IPC server data_dir for file-based state reads (R06-A)
    // IPC 服務器數據目錄，用於基於文件的狀態讀取
    let ipc_data_dir =
        std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into());
    // Paper session command channel: IPC → event consumer
    // 紙盤 session 命令通道：IPC → 事件消費者
    let (paper_cmd_tx, paper_cmd_rx) = tokio::sync::mpsc::unbounded_channel();
    // Clone the command sender for the Phase 4.1 Teacher consumer loop wiring below.
    // 為下方 Phase 4.1 Teacher consumer loop 接線預先複製 command sender。
    let phase4_consumer_cmd_tx = paper_cmd_tx.clone();
    let mut ipc_server = IpcServer::new(
        Arc::clone(&config),
        cancel.clone(),
        ipc_data_dir,
        Some(paper_cmd_tx),
    );
    // ARCH-RC1 1C-2-C: wire unified Config stores into IPC for direct hot-reload writes.
    // ARCH-RC1 1C-2-C：將統一 Config stores 接入 IPC，供直接熱更新。
    ipc_server.set_config_stores(
        Arc::clone(&risk_store),
        Arc::clone(&learning_store),
        Arc::clone(&budget_store),
    );
    // Phase 4 (4-15): Grab the BudgetTracker slot handle before moving the server into
    // the spawn task; main will write the tracker into this slot once db_pool is ready.
    // Phase 4 (4-15)：在把 server 移入 spawn task 前先拿到 BudgetTracker 槽位句柄；
    // 主函數會在 db_pool 就緒後將 tracker 寫入此槽位。
    let budget_tracker_slot = ipc_server.budget_tracker_slot();
    // Phase 4.1: same pattern for the Teacher consumer loop handles.
    // Phase 4.1：同樣模式拿 Teacher consumer loop 句柄槽位。
    let teacher_loop_slot = ipc_server.teacher_loop_slot();
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
    if let Ok(rest_client) = BybitRestClient::new(BybitEnvironment::Demo, None, None) {
        if rest_client.has_credentials() {
            let (key, secret) = rest_client.credentials();
            api_credentials = Some((key.to_string(), secret.to_string()));
            let client_arc = Arc::new(rest_client);
            shared_client = Some(Arc::clone(&client_arc));

            // R-05: Load instrument info cache (lot sizes, tick sizes, min notional)
            // R-05：加載合約信息緩存（步長、tick 精度、最小名義值）
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
            // 項目 8：DCP — 斷連取消保護
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
            // 項目 7：為現有倉位啟用自動追加保證金
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

            // Item 2: Fetch dynamic per-symbol fee rates and keep AccountManager
            // alive so the engine can do live per-symbol lookups + periodic refresh.
            // 項目 2：拉取 per-symbol 動態費率，保活 AccountManager 用於後續查詢/刷新。
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

            // Periodic refresh: re-fetch fee rates every 6h to track VIP-tier changes.
            // VIP tier moves are rare (≪daily) so 6h is plenty; cancel-aware so
            // shutdown unwinds cleanly. Staleness monitor below will alarm if
            // refresh task dies or API is unreachable for >12h.
            // 每 6 小時刷新費率，追蹤 VIP 變動；接 cancel token 優雅退出。
            {
                let acct_refresh = Arc::clone(&acct);
                let client_refresh = Arc::clone(&client_arc);
                let cancel_refresh = cancel.clone();
                tokio::spawn(async move {
                    let mut tick =
                        tokio::time::interval(std::time::Duration::from_secs(6 * 3600));
                    tick.tick().await; // skip first immediate tick
                    loop {
                        tokio::select! {
                            _ = cancel_refresh.cancelled() => {
                                info!("fee_rate refresh task stopping (cancel) / 費率刷新任務停止");
                                break;
                            }
                            _ = tick.tick() => {
                                match acct_refresh
                                    .refresh_fee_rates(&*client_refresh, "linear")
                                    .await
                                {
                                    Ok(count) => info!(
                                        symbols = count,
                                        "fee rates refreshed (6h) / 費率已刷新"
                                    ),
                                    Err(e) => {
                                        warn!(error = %e, "fee rate refresh failed / 費率刷新失敗")
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // Staleness monitor: alarm if fee rates haven't refreshed in >12h
            // (refresh task dead or persistent API failure).
            // 費率新鮮度監控：>12h 未刷新告警（refresh task 掛了或 API 持續失敗）。
            {
                let acct_mon = Arc::clone(&acct);
                let cancel_mon = cancel.clone();
                tokio::spawn(async move {
                    let mut tick =
                        tokio::time::interval(std::time::Duration::from_secs(15 * 60));
                    tick.tick().await;
                    loop {
                        tokio::select! {
                            _ = cancel_mon.cancelled() => break,
                            _ = tick.tick() => {
                                let last = acct_mon.last_fee_refresh_ms();
                                if last == 0 { continue; }
                                let now = std::time::SystemTime::now()
                                    .duration_since(std::time::UNIX_EPOCH)
                                    .unwrap_or_default()
                                    .as_millis() as u64;
                                let age_h = (now.saturating_sub(last)) as f64 / 3_600_000.0;
                                if age_h > 12.0 {
                                    warn!(
                                        age_hours = format!("{:.1}", age_h),
                                        "fee rates STALE >12h — refresh task may be dead / 費率過期"
                                    );
                                }
                            }
                        }
                    }
                });
            }
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

    // ------------------------------------------------------------------
    // R-05: Periodic instrument info refresh (every 4 hours)
    // R-05：定期刷新合約信息（每 4 小時）
    // ------------------------------------------------------------------
    if let (Some(ref icache), Some(ref client)) = (&shared_instruments, &shared_client) {
        let refresh_cache = Arc::clone(icache);
        let refresh_client = Arc::clone(client);
        let refresh_cancel = cancel.clone();
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(std::time::Duration::from_secs(4 * 3600));
            interval.tick().await; // skip immediate first tick
            loop {
                tokio::select! {
                    _ = refresh_cancel.cancelled() => break,
                    _ = interval.tick() => {
                        match refresh_cache.refresh(&*refresh_client, "linear").await {
                            Ok(n) => info!(symbols = n, "instrument info refreshed / 品種規格已刷新"),
                            Err(e) => warn!(error = %e, "instrument refresh failed / 品種刷新失敗"),
                        }
                    }
                }
            }
        });
    }

    // ------------------------------------------------------------------
    // Start WS client — subscribe to all symbols (with extended topics if configured)
    // 啟動 WebSocket 客戶端 — 訂閱所有交易對（含擴展 topic）
    // ------------------------------------------------------------------
    // Build subscription list first (RE-2: needed for supervisor restart)
    // 先建立訂閱列表（RE-2：監管器重啟所需）
    let ws_subscriptions: Vec<String> = if cfg_snapshot.enable_extended_ws {
        let mut topics = Vec::new();
        for sym in SYMBOLS {
            // GAP: extended_subscription_list collapsed into full_subscription_list
            // 2026-04-06 — broken topics permanently removed.
            for topic in openclaw_engine::multi_interval_ws::full_subscription_list(sym) {
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
        for sym in SYMBOLS {
            topics.push(format!("kline.1.{sym}"));
            topics.push(format!("publicTrade.{sym}"));
        }
        topics
    };

    // RE-2: Supervisor wrapper — restarts WS on unexpected exit
    // RE-2：監管器包裝 — WS 意外退出時自動重啟
    let ws_handle = {
        let ws_config = Arc::clone(&config);
        let ws_cancel = cancel.clone();
        let ws_topics = ws_subscriptions.clone();
        tokio::spawn(async move {
            let mut supervisor_attempt: u32 = 0;
            loop {
                if ws_cancel.is_cancelled() {
                    break;
                }

                let mut ws_client =
                    WsClient::new(Arc::clone(&ws_config), event_tx.clone(), ws_cancel.clone());
                for topic in &ws_topics {
                    ws_client.subscribe(topic.clone());
                }
                ws_client.run().await;

                // If cancelled, exit cleanly / 如果已取消，正常退出
                if ws_cancel.is_cancelled() {
                    break;
                }

                // Unexpected exit — supervisor restart with backoff
                // 意外退出 — 監管器退避重啟
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
    // Item 5: Private WS + ExecutionListener (order/fill/position/wallet callbacks)
    // 項目 5：私有 WS + 執行監聽器（訂單/成交/持倉/餘額回調）
    // ------------------------------------------------------------------
    let _private_ws_handle = if let Some((api_key, api_secret)) = api_credentials {
        use openclaw_engine::bybit_private_ws::BybitPrivateWs;
        use openclaw_engine::event_consumer::ExchangeEvent;
        use openclaw_engine::execution_listener::ExecutionListener;
        use std::sync::RwLock;

        let (priv_tx, priv_rx) = mpsc::channel(512);
        // EXT-1: Channel for forwarding exchange events to event consumer
        let (exchange_event_tx, exchange_event_rx) = mpsc::unbounded_channel::<ExchangeEvent>();

        // Shared state updated by callbacks / 回調更新的共享狀態
        let bybit_balance: Arc<RwLock<Option<f64>>> = Arc::new(RwLock::new(None));
        let api_pnl: Arc<RwLock<std::collections::HashMap<String, f64>>> =
            Arc::new(RwLock::new(std::collections::HashMap::new()));

        let mut listener = ExecutionListener::new(priv_rx);

        // Item 3: on_balance_update → track Bybit sync balance
        // 項目 3：餘額更新回調 → 追蹤 Bybit 同步餘額
        let bal_ref = Arc::clone(&bybit_balance);
        listener.set_on_balance_update(move |wallet| {
            for coin_update in &wallet.coin {
                if coin_update.coin.eq_ignore_ascii_case("USDT") {
                    if let Ok(bal) = coin_update.wallet_balance.parse::<f64>() {
                        if let Ok(mut guard) = bal_ref.write() {
                            *guard = Some(bal);
                        }
                        info!(
                            equity = %coin_update.equity,
                            balance = %coin_update.wallet_balance,
                            "WS wallet update (USDT) / WS 錢包更新"
                        );
                    }
                    break;
                }
            }
        });

        // Item 4: on_position_update → track API unrealized PnL
        // 項目 4：持倉更新回調 → 追蹤 API 未實現損益
        let pnl_ref = Arc::clone(&api_pnl);
        listener.set_on_position_update(move |pos| {
            if let Ok(pnl) = pos.unrealised_pnl.parse::<f64>() {
                if let Ok(mut guard) = pnl_ref.write() {
                    guard.insert(pos.symbol.clone(), pnl);
                }
            }
            debug!(
                symbol = %pos.symbol,
                side = %pos.side,
                size = %pos.size,
                pnl = %pos.unrealised_pnl,
                "WS position update / WS 持倉更新"
            );
        });

        // Item 5: on_fill → log execution + EXT-1: forward to event consumer
        let fill_tx = exchange_event_tx.clone();
        listener.set_on_fill(move |exec| {
            info!(
                exec_id = %exec.exec_id,
                symbol = %exec.symbol,
                side = %exec.side,
                qty = %exec.exec_qty,
                price = %exec.exec_price,
                fee = %exec.exec_fee,
                "WS fill / WS 成交"
            );
            let _ = fill_tx.send(ExchangeEvent::Fill(exec));
        });

        // on_order_update → log status changes + EXT-1: forward to event consumer
        let order_tx = exchange_event_tx.clone();
        listener.set_on_order_update(move |order| {
            debug!(
                order_id = %order.order_id,
                symbol = %order.symbol,
                status = %order.order_status,
                link_id = %order.order_link_id,
                "WS order update / WS 訂單更新"
            );
            let _ = order_tx.send(ExchangeEvent::OrderUpdate(order));
        });

        // P0-3: Wire DCP/Disconnected events to event consumer
        // P0-3：將 DCP/斷連事件接入事件消費者
        let dcp_tx = exchange_event_tx.clone();
        listener.set_on_dcp(move || {
            let _ = dcp_tx.send(ExchangeEvent::DcpTriggered);
        });
        let disc_tx = exchange_event_tx;
        listener.set_on_disconnect(move || {
            let _ = disc_tx.send(ExchangeEvent::Disconnected);
        });

        // Spawn listener task / 啟動監聽器任務
        let listener_handle = tokio::spawn(async move {
            let mut listener = listener;
            listener.run().await;
        });

        // RE-2: Supervisor wrapper for private WS — restarts on unexpected exit
        // RE-2：私有 WS 監管器包裝 — 意外退出時自動重啟
        let priv_cancel = cancel.clone();
        let priv_ws_handle = {
            let api_key_owned = api_key.clone();
            let api_secret_owned = api_secret.clone();
            let sv_cancel = priv_cancel.clone();
            tokio::spawn(async move {
                let mut supervisor_attempt: u32 = 0;
                loop {
                    if sv_cancel.is_cancelled() {
                        break;
                    }

                    let priv_ws = BybitPrivateWs::new(
                        api_key_owned.clone(),
                        api_secret_owned.clone(),
                        BybitEnvironment::Demo,
                        sv_cancel.clone(),
                        priv_tx.clone(),
                    );
                    priv_ws.run().await;

                    if sv_cancel.is_cancelled() {
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
                        "Private WS supervisor restarting / 私有 WS 監管器重啟"
                    );
                    tokio::select! {
                        _ = sv_cancel.cancelled() => break,
                        _ = tokio::time::sleep(std::time::Duration::from_millis(delay_ms)) => {},
                    }
                }
            })
        };

        info!("Private WS + ExecutionListener started / 私有 WS + 執行監聯器已啟動");
        Some((
            priv_ws_handle,
            listener_handle,
            bybit_balance,
            api_pnl,
            exchange_event_rx,
        ))
    } else {
        info!("no credentials — Private WS skipped / 無憑證，跳過私有 WS");
        None
    };

    // Extract shared state Arcs for event consumer (H1+H2 fix: bridge WS data → pipeline)
    // 提取共享狀態 Arc 給事件消費者（H1+H2 修復：橋接 WS 數據 → 管線）
    // Extract shared state + exchange_event_rx from private WS handle
    // Keep WS/listener handles for shutdown, move exchange_event_rx out
    let (shared_bybit_balance, shared_api_pnl, shared_exchange_event_rx, _priv_handles) = {
        match _private_ws_handle {
            Some((ws_h, listener_h, bal, pnl, exch_rx)) => (
                Some(Arc::clone(&bal)),
                Some(Arc::clone(&pnl)),
                Some(exch_rx),
                Some((ws_h, listener_h)),
            ),
            None => (None, None, None, None),
        }
    };

    // ------------------------------------------------------------------
    // Event consumer — feeds into TickPipeline for paper trading
    // 事件消費者 — 送入 TickPipeline 進行紙盤交易
    // (Phase 1 Day 0-A: extracted to event_consumer.rs)
    // ------------------------------------------------------------------
    // ------------------------------------------------------------------
    // Phase 1: Database pool + writer tasks
    // Phase 1：資料��連接池 + 寫入器任務
    // ------------------------------------------------------------------
    let cfg_snap_db = config.get();
    let db_pool =
        Arc::new(openclaw_engine::database::pool::DbPool::connect(&cfg_snap_db.database).await);

    // Phase 4 (4-15): Initialize the AI BudgetTracker now that db_pool is ready and
    // inject it into the IPC server slot. If init fails, the slot stays None and
    // get_ai_budget_status fail-soft returns "uninitialized".
    // Phase 4 (4-15)：db_pool 就緒後初始化 AI BudgetTracker，並注入 IPC server 槽位。
    // 若初始化失敗，槽位保持 None，get_ai_budget_status fail-soft 回傳 "uninitialized"。
    if db_pool.is_available() {
        match openclaw_engine::ai_budget::BudgetTracker::new(Arc::clone(&db_pool)).await {
            Ok(tracker) => {
                budget_tracker_slot.write().await.replace(Arc::new(tracker));
                info!("BudgetTracker initialized / AI 預算追蹤器已初始化");
            }
            Err(e) => {
                warn!(error = %e, "BudgetTracker init failed, AI budget enforcement disabled / 預算追蹤器初始化失敗");
            }
        }
    } else {
        warn!("db_pool unavailable, BudgetTracker not started / db_pool 不可用，BudgetTracker 未啟動");
    }

    // ------------------------------------------------------------------
    // Phase 4 W-3/W-4: Construct LinUCB runtime + news context snapshot.
    // These are shared resources plumbed to TickPipeline via EventConsumerDeps,
    // and to the future News producer loop via the snapshot handle.
    // Phase 4 W-3/W-4：構造 LinUCB runtime + 新聞 context 快照。
    // 這些共享資源透過 EventConsumerDeps 接入 TickPipeline，並透過快照句柄
    // 供未來的 News producer loop 使用。
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

    // ------------------------------------------------------------------
    // Phase 4 W-1/W-2: Shared governance halted handle + guardian impl.
    // GovernanceCoreWrapper and GuardianHaltCheckImpl share the same
    // Arc<AtomicBool> so news-triggered halts are immediately visible to
    // the Teacher DirectiveApplier (single source of truth, no double-write).
    // The DirectiveApplier itself is not constructed here yet — it has no
    // live invoker (Claude API pull loop is a follow-up task); the wrappers
    // exist ready for that task to plug in.
    // Phase 4 W-1/W-2：共享 governance halted 句柄 + guardian impl。
    // GovernanceCoreWrapper 與 GuardianHaltCheckImpl 共享同一個
    // Arc<AtomicBool>，使新聞觸發的 halt 對 Teacher DirectiveApplier 立即可見
    // （單一真相源，無雙寫）。DirectiveApplier 本身尚未在此構造 —— 還沒有
    // live invoker（Claude API 拉取 loop 是後續任務）；wrapper 已就位供該
    // 任務直接插入。
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
        "Phase 4 governance+guardian wrappers constructed (sharing halted atomic) / W-1/W-2 wrappers 已構造"
    );
    // Keep guardian impl alive for future news pipeline wiring.
    // 保持 guardian impl 存活供未來新聞 pipeline 接線使用。
    let _phase4_guardian_impl = guardian_impl;

    // ------------------------------------------------------------------
    // Phase 4.1: Construct + spawn TeacherConsumerLoop (DEFAULT-OFF).
    // The loop ticks at the configured interval but skips all work until
    // operator flips the enabled flag via IPC AFTER E3 R6 audit PASSes.
    // Loop skipped entirely if BudgetTracker / db_pool is unavailable.
    //
    // Phase 4.1：構造並 spawn TeacherConsumerLoop（**預設關閉**）。
    // Loop 按設定間隔 tick，但在 operator 透過 IPC 翻開 enabled 旗標
    // （E3 R6 審計通過後）之前跳過所有工作。BudgetTracker 或 db_pool
    // 不可用時整個 loop 跳過構造。
    // ------------------------------------------------------------------
    if db_pool.is_available() {
        let budget_opt = budget_tracker_slot.read().await.clone();
        if let Some(budget) = budget_opt {
            use openclaw_engine::claude_teacher::{
                AnthropicClient, ClaudeTeacher, ConsumerLoopConfig, DirectiveApplier,
                GovernanceCheck, LlmClient, OutcomeTracker, PaperSessionCommandSink,
                StrategyIpcSink, TeacherConsumerLoop,
            };
            use std::sync::atomic::AtomicBool;
            let model = "claude-sonnet-4-5";
            let llm_client: Arc<dyn LlmClient + Send + Sync> =
                Arc::new(AnthropicClient::new(model));
            let teacher = Arc::new(ClaudeTeacher::new(
                llm_client,
                Some(Arc::clone(&budget)),
                Arc::clone(&db_pool),
                model,
            ));
            let governance_for_applier: Arc<dyn GovernanceCheck> =
                Arc::clone(&governance_wrapper) as Arc<dyn GovernanceCheck>;
            let ipc_sink: Arc<dyn StrategyIpcSink> =
                Arc::new(PaperSessionCommandSink::new(phase4_consumer_cmd_tx));
            let applier = Arc::new(DirectiveApplier::new(
                governance_for_applier,
                Some(ipc_sink),
                Arc::clone(&db_pool),
            ));
            let outcome_tracker = Arc::new(OutcomeTracker::new(Arc::clone(&db_pool)));
            // Default-off until E3 R6 PASS. Operator flips via IPC.
            // E3 R6 通過前預設關閉。Operator 透過 IPC 翻開。
            let enabled = Arc::new(AtomicBool::new(false));
            let consumer_loop = Arc::new(TeacherConsumerLoop::new(
                teacher,
                applier,
                Some(outcome_tracker),
                ConsumerLoopConfig::production_defaults(),
                Arc::clone(&enabled),
            ));
            // Inject handles into IPC slot BEFORE spawn so the handlers see
            // them as soon as the loop is alive.
            // 在 spawn 前先把句柄注入 IPC 槽位，loop 一啟動 handler 就看得見。
            {
                use openclaw_engine::ipc_server::TeacherLoopHandles;
                let handles = TeacherLoopHandles {
                    enabled: consumer_loop.enabled_handle(),
                    status: consumer_loop.status(),
                };
                teacher_loop_slot.write().await.replace(handles);
            }
            let _consumer_handle = Arc::clone(&consumer_loop).spawn();
            info!(
                "Phase 4.1 TeacherConsumerLoop spawned + IPC handles injected (DEFAULT-OFF; flip via set_teacher_loop_enabled after E3 R6 PASS) / consumer loop 已啟動，IPC 句柄已注入（預設關閉）"
            );
        } else {
            warn!("Phase 4.1 consumer loop skipped: BudgetTracker not initialized / 預算追蹤器未初始化，consumer loop 跳過");
        }
    } else {
        warn!("Phase 4.1 consumer loop skipped: db_pool unavailable / db_pool 不可用，consumer loop 跳過");
    }
    // Hold the governance wrapper alive (cloned into the applier above when
    // db_pool is available; this binding ensures it lives for the rest of main).
    // 保持 governance wrapper 存活（db_pool 可用時已被 clone 進 applier，
    // 此 binding 確保它在 main 餘下時間都存活）。
    let _phase4_governance_wrapper = governance_wrapper;

    let (market_tx, market_rx) = if db_pool.is_available() {
        let (tx, rx) = tokio::sync::mpsc::channel(4096);
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };
    let (feature_tx, feature_rx) = if db_pool.is_available() {
        let (tx, rx) = tokio::sync::mpsc::channel(2048);
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };

    // Spawn market writer task / 啟���市場數據寫入器任務
    if let Some(mrx) = market_rx {
        let mw_pool = Arc::clone(&db_pool);
        let mw_config = Arc::clone(&config);
        let mw_cancel = cancel.clone();
        tokio::spawn(openclaw_engine::database::market_writer::run_market_writer(
            mrx, mw_pool, mw_config, mw_cancel,
        ));
    }

    // Spawn feature writer task / 啟動特徵寫入器任務
    if let Some(frx) = feature_rx {
        let fw_pool = Arc::clone(&db_pool);
        let fw_config = Arc::clone(&config);
        let fw_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::feature_writer::run_feature_writer(
                frx, fw_pool, fw_config, fw_cancel,
            ),
        );
    }

    // Phase 2a: Trading lifecycle channel + writer task
    // Phase 2a：交易生命週期通道 + 寫入器任務
    let (trading_tx, trading_rx) = if db_pool.is_available() {
        let (tx, rx) = tokio::sync::mpsc::channel(4096);
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };
    if let Some(trx) = trading_rx {
        let tw_pool = Arc::clone(&db_pool);
        let tw_config = Arc::clone(&config);
        let tw_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::trading_writer::run_trading_writer(
                trx, tw_pool, tw_config, tw_cancel,
            ),
        );
    }

    // Phase 2a: Decision context channel + writer task
    let (context_tx, context_rx) = if db_pool.is_available() {
        let (tx, rx) = tokio::sync::mpsc::channel(1024);
        (Some(tx), Some(rx))
    } else {
        (None, None)
    };
    if let Some(crx) = context_rx {
        let cw_pool = Arc::clone(&db_pool);
        let cw_config = Arc::clone(&config);
        let cw_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::context_writer::run_context_writer(
                crx, cw_pool, cw_config, cw_cancel,
            ),
        );
    }

    // F-4 fix: Spawn REST pollers for funding/OI/LSR (requires API client + market channel)
    // F-4 修復：啟動 funding/OI/LSR REST 輪詢器
    if let (Some(ref client), Some(ref mtx)) = (&shared_client, &market_tx) {
        openclaw_engine::database::rest_poller::spawn_rest_pollers(
            Arc::clone(client),
            mtx.clone(),
            openclaw_engine::event_consumer::SYMBOLS,
            cancel.clone(),
        );
    }

    // F-5 fix: Spawn data quality monitor (uses shared last_tick_ms counter)
    // F-5 修復：啟動數據質量監控器
    let shared_last_tick_ms = Arc::new(std::sync::atomic::AtomicU64::new(0));
    if db_pool.is_available() {
        let qm_pool = Arc::clone(&db_pool);
        let qm_tick = Arc::clone(&shared_last_tick_ms);
        let qm_symbols: Vec<String> = openclaw_engine::event_consumer::SYMBOLS
            .iter()
            .map(|s| s.to_string())
            .collect();
        let qm_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::quality_writer::run_quality_monitor(
                qm_pool, qm_tick, qm_symbols, qm_cancel,
            ),
        );
    }

    // G3 1-13/14: Spawn drift detector (PSI + ADWIN)
    // G3 1-13/14：啟動漂移檢測器（PSI + ADWIN）
    if db_pool.is_available() {
        let dd_pool = Arc::clone(&db_pool);
        let dd_config = Arc::clone(&config);
        let dd_cancel = cancel.clone();
        tokio::spawn(
            openclaw_engine::database::drift_detector::run_drift_detector(
                dd_pool, dd_config, dd_cancel,
            ),
        );
    }

    // G3 1-16: Feature version init — insert v1.0 row on startup if PG available
    // G3 1-16：特徵版本初始化 — 啟動時插入 v1.0 行
    if db_pool.is_available() {
        if let Some(pg) = db_pool.get() {
            let _ = sqlx::query(
                "INSERT INTO features.versions (version, description, is_active) \
                 VALUES ('v1.0', 'Phase 1 initial: 34-dim IndicatorSnapshot', true) \
                 ON CONFLICT (version) DO NOTHING",
            )
            .execute(pg)
            .await;
            info!("feature version v1.0 registered / 特徵版本 v1.0 已註冊");
        }
    }

    let event_handle = {
        use openclaw_engine::event_consumer::{run_event_consumer, EventConsumerDeps};
        let deps = EventConsumerDeps {
            event_rx,
            config: Arc::clone(&config),
            cancel: cancel.clone(),
            initial_balance,
            taker_fee_rate: api_taker_fee,
            instruments: shared_instruments.clone(),
            bootstrap_client: shared_client.as_ref().map(Arc::clone),
            shared_client: shared_client.clone(),
            bybit_balance: shared_bybit_balance,
            api_pnl: shared_api_pnl,
            paper_cmd_rx: Some(paper_cmd_rx),
            market_data_tx: market_tx,
            feature_tx,
            last_tick_ms: Some(Arc::clone(&shared_last_tick_ms)),
            trading_tx,
            context_tx,
            exchange_event_rx: shared_exchange_event_rx,
            account_manager: shared_account_manager,
            // Phase 4 W-3/W-4 live plumbing / Phase 4 W-3/W-4 實時接線
            linucb_runtime: Some(Arc::clone(&shared_linucb_runtime)),
            news_snapshot: Some(Arc::clone(&shared_news_snapshot)),
            // ARCH-RC1 1C-2-B: live ConfigStore handles for hot-reload.
            // ARCH-RC1 1C-2-B：熱重載 ConfigStore 控制代碼。
            risk_store: Some(Arc::clone(&risk_store)),
            budget_store: Some(Arc::clone(&budget_store)),
        };
        tokio::spawn(run_event_consumer(deps))
    };

    info!(version = VERSION, "engine started / 引擎已啟動");

    // ------------------------------------------------------------------
    // Signal handling / 信號處理
    // ------------------------------------------------------------------
    signal_loop(&config, &cancel).await;

    // ------------------------------------------------------------------
    // Shutdown sequence / 關閉序列
    // ------------------------------------------------------------------
    info!("initiating shutdown / 開始關閉序列");

    // 1. Cancel all tasks / 取消所有任務
    cancel.cancel();

    // 2. Wait for tasks to finish (with timeout) / 等待任務完成（帶超時）
    let shutdown_timeout = tokio::time::Duration::from_secs(10);
    let _ = tokio::time::timeout(shutdown_timeout, async {
        let _ = ws_handle.await;
        let _ = ipc_handle.await;
        let _ = event_handle.await;
        // M4 fix: Await private WS handles if present
        // M4 修復：等待私有 WS 任務完成
        if let Some((priv_ws_h, listener_h)) = _priv_handles {
            let _ = priv_ws_h.await;
            let _ = listener_h.await;
        }
    })
    .await;

    // 3. Clean up socket file / 清理套接字文件
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

/// Listen for OS signals: SIGHUP → reload, SIGTERM/SIGINT → shutdown.
/// 監聽 OS 信號：SIGHUP → 重載，SIGTERM/SIGINT → 關閉。
async fn signal_loop(config: &Arc<ConfigManager>, cancel: &CancellationToken) {
    // Platform-specific signal handling / 平台特定信號處理
    #[cfg(unix)]
    {
        use tokio::signal::unix::{signal, SignalKind};
        let mut sighup =
            signal(SignalKind::hangup()).expect("failed to register SIGHUP / 註冊 SIGHUP 失敗");
        let mut sigterm = signal(SignalKind::terminate())
            .expect("failed to register SIGTERM / 註冊 SIGTERM 失敗");

        loop {
            tokio::select! {
                _ = sighup.recv() => {
                    info!("SIGHUP received — reloading config / 收到 SIGHUP — 重載配置");
                    match config.reload() {
                        Ok(()) => info!("config reloaded successfully / 配置重載成功"),
                        Err(e) => error!(error = %e, "config reload failed / 配置重載失敗"),
                    }
                }
                _ = sigterm.recv() => {
                    info!("SIGTERM received — shutting down / 收到 SIGTERM — 開始關閉");
                    break;
                }
                _ = tokio::signal::ctrl_c() => {
                    info!("SIGINT received — shutting down / 收到 SIGINT — 開始關閉");
                    break;
                }
                _ = cancel.cancelled() => {
                    break;
                }
            }
        }
    }

    // Non-Unix fallback (Windows/other) / 非 Unix 回退
    #[cfg(not(unix))]
    {
        tokio::select! {
            _ = tokio::signal::ctrl_c() => {
                info!("ctrl-c received — shutting down / 收到 ctrl-c — 開始關閉");
            }
            _ = cancel.cancelled() => {}
        }
    }
}

/// Print startup banner.
/// 打印啟動標語。
fn print_banner() {
    info!("==============================================");
    info!("  OpenClaw Engine v{}", VERSION);
    info!("  Mode: demo_only | Execution: disabled");
    info!("  Bybit V5 Linear — Rust Trading Engine");
    info!("==============================================");
}
