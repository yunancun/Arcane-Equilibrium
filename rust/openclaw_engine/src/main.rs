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
use openclaw_engine::config::ConfigManager;
use openclaw_engine::ipc_server::IpcServer;
use openclaw_engine::persistence::{AuditWriter, StateWriter};
use openclaw_engine::strategies::{
    bb_breakout::BbBreakout, bb_reversion::BbReversion, grid_trading::GridTrading,
    ma_crossover::MaCrossover,
};
use openclaw_engine::tick_pipeline::TickPipeline;
use openclaw_engine::ws_client::WsClient;
use openclaw_types::PriceEvent;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

/// Engine version from Cargo.toml / 引擎版本（來自 Cargo.toml）
const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Price event channel buffer size / 價格事件通道緩衝區大小
const EVENT_CHANNEL_SIZE: usize = 4096;

/// Status report interval / 狀態報告間隔
const STATUS_INTERVAL_SECS: u64 = 30;

/// Symbols to track / 追蹤的交易對
const SYMBOLS: &[&str] = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];

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
        info!(balance = format!("{:.2}", env_bal), "using OPENCLAW_PAPER_BALANCE env override / 使用環境變量覆蓋餘額");
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
    info!(balance = format!("{:.2}", default), "using default paper balance / 使用預設紙盤餘額");
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
    // 2. Load config / 加載配置
    // ------------------------------------------------------------------
    let config = match ConfigManager::load(None) {
        Ok(c) => Arc::new(c),
        Err(e) => {
            error!(error = %e, "failed to load config / 配置加載失敗");
            std::process::exit(1);
        }
    };

    // ------------------------------------------------------------------
    // 3. Build multi-thread runtime / 構建多線程運行時
    // ------------------------------------------------------------------
    let runtime = tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .thread_name("oc-engine")
        .build()
        .expect("failed to build tokio runtime / 構建 tokio 運行時失敗");

    runtime.block_on(async_main(config));
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
    pipeline.orchestrator.register(Box::new(GridTrading::new_adaptive()));

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
async fn async_main(config: Arc<ConfigManager>) {
    let cancel = CancellationToken::new();

    // ------------------------------------------------------------------
    // Fetch initial balance from Bybit Demo API (or env / default)
    // 從 Bybit Demo API 讀取初始餘額（或環境變量 / 預設值）
    // ------------------------------------------------------------------
    let initial_balance = fetch_demo_balance().await;

    // ------------------------------------------------------------------
    // Price event channel / 價格事件通道
    // ------------------------------------------------------------------
    let (event_tx, mut event_rx) = mpsc::channel::<PriceEvent>(EVENT_CHANNEL_SIZE);

    // ------------------------------------------------------------------
    // Start IPC server / 啟動 IPC 服務器
    // ------------------------------------------------------------------
    // IPC server data_dir for file-based state reads (R06-A)
    // IPC 服務器數據目錄，用於基於文件的狀態讀取
    let ipc_data_dir = std::env::var("OPENCLAW_DATA_DIR")
        .unwrap_or_else(|_| "/tmp/openclaw".into());
    let ipc_server = IpcServer::new(Arc::clone(&config), cancel.clone(), ipc_data_dir);
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
    let mut shared_instruments: Option<Arc<openclaw_engine::instrument_info::InstrumentInfoCache>> = None;
    let cfg_snapshot = config.get();
    if let Ok(rest_client) = BybitRestClient::new(BybitEnvironment::Demo, None, None) {
        if rest_client.has_credentials() {
            let (key, secret) = rest_client.credentials();
            api_credentials = Some((key.to_string(), secret.to_string()));
            let client_arc = Arc::new(rest_client);
            shared_client = Some(Arc::clone(&client_arc));

            // R-05: Load instrument info cache (lot sizes, tick sizes, min notional)
            // R-05：加載合約信息緩存（步長、tick 精度、最小名義值）
            let instrument_cache = Arc::new(openclaw_engine::instrument_info::InstrumentInfoCache::new());
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
                    Ok(()) => info!(window = cfg_snapshot.dcp_time_window, "DCP enabled / DCP 已啟用"),
                    Err(e) => warn!(error = %e, "DCP setup failed (non-fatal) / DCP 設定失敗（非致命）"),
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
                                match pos_mgr.set_auto_add_margin(
                                    OrderCategory::Linear, &pos.symbol, 1, None,
                                ).await {
                                    Ok(()) => info!(symbol = %pos.symbol, "auto-margin enabled / 自動追保已啟用"),
                                    Err(e) => warn!(symbol = %pos.symbol, error = %e, "auto-margin failed / 自動追保失敗"),
                                }
                            }
                        }
                    }
                    Err(e) => warn!(error = %e, "failed to query positions for auto-margin / 查詢倉位失敗"),
                }
            }

            // Item 2: Fetch dynamic fee rates
            // 項目 2：獲取動態費率
            let acct = AccountManager::new();
            match acct.refresh_fee_rates(&*client_arc, "linear").await {
                Ok(count) => {
                    let rate = acct.taker_fee("BTCUSDT");
                    api_taker_fee = Some(rate);
                    info!(symbols = count, taker_rate = format!("{:.5}", rate), "fee rates loaded / 費率已加載");
                }
                Err(e) => warn!(error = %e, "fee rate fetch failed, using defaults / 費率獲取失敗，使用默認值"),
            }
        } else {
            info!("no Bybit credentials — skipping DCP/margin/fee setup / 無 API 憑證，跳過 API 設定");
        }
    } else {
        info!("Bybit client init failed — skipping API setup / Bybit 客戶端初始化失敗，跳過 API 設定");
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
            for topic in openclaw_engine::multi_interval_ws::extended_subscription_list(sym) {
                topics.push(topic);
            }
        }
        info!(topics_per_symbol = 10, "extended WS subscriptions / 擴展 WS 訂閱");
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
                if ws_cancel.is_cancelled() { break; }

                let mut ws_client = WsClient::new(
                    Arc::clone(&ws_config), event_tx.clone(), ws_cancel.clone(),
                );
                for topic in &ws_topics {
                    ws_client.subscribe(topic.clone());
                }
                ws_client.run().await;

                // If cancelled, exit cleanly / 如果已取消，正常退出
                if ws_cancel.is_cancelled() { break; }

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
        use openclaw_engine::execution_listener::ExecutionListener;
        use std::sync::RwLock;

        let (priv_tx, priv_rx) = mpsc::channel(512);

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

        // Item 5: on_fill → log execution
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
        });

        // on_order_update → log status changes
        listener.set_on_order_update(move |order| {
            debug!(
                order_id = %order.order_id,
                symbol = %order.symbol,
                status = %order.order_status,
                "WS order update / WS 訂單更新"
            );
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
                    if sv_cancel.is_cancelled() { break; }

                    let priv_ws = BybitPrivateWs::new(
                        api_key_owned.clone(),
                        api_secret_owned.clone(),
                        BybitEnvironment::Demo,
                        sv_cancel.clone(),
                        priv_tx.clone(),
                    );
                    priv_ws.run().await;

                    if sv_cancel.is_cancelled() { break; }

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
        Some((priv_ws_handle, listener_handle, bybit_balance, api_pnl))
    } else {
        info!("no credentials — Private WS skipped / 無憑證，跳過私有 WS");
        None
    };

    // Extract shared state Arcs for event consumer (H1+H2 fix: bridge WS data → pipeline)
    // 提取共享狀態 Arc 給事件消費者（H1+H2 修復：橋接 WS 數據 → 管線）
    let shared_bybit_balance = _private_ws_handle.as_ref().map(|h| Arc::clone(&h.2));
    let shared_api_pnl = _private_ws_handle.as_ref().map(|h| Arc::clone(&h.3));

    // ------------------------------------------------------------------
    // Event consumer — feeds into TickPipeline for paper trading
    // 事件消費者 — 送入 TickPipeline 進行紙盤交易
    // ------------------------------------------------------------------
    let event_cancel = cancel.clone();
    let bootstrap_client = shared_client.as_ref().map(Arc::clone);
    let event_handle = tokio::spawn(async move {
        // Build pipeline with Bybit Demo balance / 使用 Demo 餘額構建管線
        let mut pipeline = TickPipeline::with_balance(SYMBOLS, initial_balance);

        // Item 2: Set dynamic fee rate if available / 設定動態費率
        if let Some(rate) = api_taker_fee {
            pipeline.set_fee_rate(rate);
            info!(taker_rate = format!("{:.5}", rate), "pipeline using API fee rate / 管線使用 API 費率");
        }

        // R-05: Wire instrument cache into pipeline for precision rounding
        // R-05：將合約信息緩存接入管線，用於精度取整
        if let Some(ref icache) = shared_instruments {
            pipeline.set_instrument_cache(Arc::clone(icache));
            info!("pipeline using instrument cache for precision rounding / 管線使用合約信息緩存進行精度取整");
        }

        // Item 3: Bybit sync mode — set initial sync balance / 設定 Bybit 同步餘額
        if cfg_snapshot.balance_mode == "bybit_sync" {
            pipeline.paper_state.set_bybit_sync_balance(Some(initial_balance));
            info!(balance = format!("{:.2}", initial_balance), "bybit_sync mode — tracking Bybit Demo balance / 同步模式已啟用");
        }

        // Item 1: Server-side stop channel (dual-track stops)
        // 項目 1：伺服器端止損通道（雙軌止損）
        if cfg_snapshot.server_side_stops {
            let (stop_tx, mut stop_rx) = tokio::sync::mpsc::unbounded_channel::<
                openclaw_engine::tick_pipeline::StopRequest,
            >();
            pipeline.set_stop_channel(stop_tx);

            // Spawn async task to process stop requests via Bybit API
            // 啟動異步任務通過 Bybit API 處理止損請求
            tokio::spawn(async move {
                while let Some(req) = stop_rx.recv().await {
                    // In demo mode, log the request. In live, call set_trading_stop.
                    // Demo 模式下記錄請求。Live 模式下調用 set_trading_stop。
                    info!(
                        symbol = %req.symbol,
                        stop_loss = format!("{:.2}", req.stop_loss),
                        side = if req.is_long { "long" } else { "short" },
                        "server-side stop request dispatched / 伺服器端止損請求已派發"
                    );
                    // TODO: Live mode — call position_manager.set_trading_stop(req).await
                }
            });
            info!("dual-track stop channel active / 雙軌止損通道已啟用");
        }

        // Shadow order mode: dispatch paper fills as real Demo API orders for calibration
        // 影子訂單模式：將紙盤成交作為真實 Demo API 訂單派發，用於校準比較
        if cfg_snapshot.shadow_orders {
            if let Some(ref client) = shared_client {
                if let Some(ref icache) = shared_instruments {
                    use openclaw_engine::order_manager::{
                        OrderManager, OrderCategory, OrderSide, OrderType, CreateOrderRequest,
                    };
                    let (shadow_tx, mut shadow_rx) = tokio::sync::mpsc::unbounded_channel::<
                        openclaw_engine::tick_pipeline::ShadowOrderRequest,
                    >();
                    pipeline.set_shadow_channel(shadow_tx);

                    let order_mgr = OrderManager::new(Arc::clone(client), Arc::clone(icache));
                    tokio::spawn(async move {
                        while let Some(req) = shadow_rx.recv().await {
                            let side = if req.is_long { OrderSide::Buy } else { OrderSide::Sell };
                            let create_req = CreateOrderRequest {
                                category: OrderCategory::Linear,
                                symbol: req.symbol.clone(),
                                side,
                                order_type: OrderType::Market,
                                qty: req.qty,
                                price: None,
                                time_in_force: None,
                                reduce_only: if req.is_close { Some(true) } else { None },
                                close_on_trigger: None,
                                order_link_id: Some(format!("shadow_{}", req.paper_fill_ts)),
                                trigger_price: None,
                                trigger_direction: None,
                                take_profit: None,
                                stop_loss: None,
                                tp_trigger_by: None,
                                sl_trigger_by: None,
                            };
                            match order_mgr.place_order(create_req).await {
                                Ok(resp) => {
                                    info!(
                                        symbol = %req.symbol,
                                        order_id = %resp.order_id,
                                        shadow_type = if req.is_close { "close" } else { "open" },
                                        paper_price = format!("{:.2}", req.price),
                                        "shadow order placed / 影子訂單已下"
                                    );
                                }
                                Err(e) => {
                                    warn!(symbol = %req.symbol, error = %e, "shadow order failed / 影子訂單失敗");
                                }
                            }
                        }
                    });
                    info!("shadow order mode active / 影子訂單模式已啟用");
                } else {
                    warn!("shadow_orders enabled but no instrument cache — skipping / 影子訂單已啟用但無品種規格快取，跳過");
                }
            } else {
                warn!("shadow_orders enabled but no API credentials — skipping / 影子訂單已啟用但無 API 憑證，跳過");
            }
        }

        // Register strategies / 註冊策略
        pipeline.orchestrator.register(Box::new(MaCrossover::new()));
        pipeline.orchestrator.register(Box::new(BbReversion::new()));
        pipeline.orchestrator.register(Box::new(BbBreakout::new()));
        // Grid trading: adaptive mode — initializes ±10% around first price seen, then OU refines
        // 网格交易：自适应模式 — 首次价格 ±10% 初始化，OU 模型后续自动调整
        pipeline.orchestrator.register(Box::new(GridTrading::new_adaptive()));
        // funding_arb skipped — needs IPC (R-06)

        // Grant paper authorization / 授予紙盤授權
        match pipeline.grant_paper_auth() {
            Ok(()) => info!("paper authorization granted / 紙盤授權已授予"),
            Err(e) => {
                error!(error = %e, "failed to grant paper auth / 紙盤授權失敗");
                return;
            }
        }

        let strategies = pipeline.orchestrator.active_strategy_names().join(", ");
        info!(
            strategies = %strategies,
            symbols = ?SYMBOLS,
            balance = format!("{:.2}", initial_balance),
            "pipeline ready — {} strategies on {} symbols / 管線就緒",
            pipeline.orchestrator.strategy_count(),
            SYMBOLS.len(),
        );

        // Kline bootstrap: fetch 200 1m bars per symbol via REST (eliminates 30min cold start)
        // K 線引導：通過 REST 為每個幣種獲取 200 根 1 分鐘歷史 K 線（消除 30 分鐘冷啟動）
        if cfg_snapshot.kline_bootstrap {
            if let Some(ref client_arc) = bootstrap_client {
                let mdc = openclaw_engine::market_data_client::MarketDataClient::new(Arc::clone(client_arc));
                for &sym in SYMBOLS {
                    match mdc.get_klines("linear", sym, "1", None, None, Some(200)).await {
                        Ok(bars) => {
                            let now_ms = std::time::SystemTime::now()
                                .duration_since(std::time::UNIX_EPOCH)
                                .unwrap_or_default()
                                .as_millis() as u64;
                            // Convert market_data_client::KlineBar -> openclaw_core::klines::KlineBar
                            // Filter out the current unclosed bar (start_time + 60s > now)
                            // REST returns newest-first; sort oldest-first for buffer seeding
                            let mut core_bars: Vec<openclaw_core::klines::KlineBar> = bars
                                .iter()
                                .filter(|b| b.start_time + 60_000 <= now_ms)
                                .map(|b| {
                                    let mut kb = openclaw_core::klines::KlineBar {
                                        open_time_ms: b.start_time,
                                        close_time_ms: b.start_time + 60_000,
                                        open: b.open,
                                        high: b.high,
                                        low: b.low,
                                        close: b.close,
                                        volume: b.volume,
                                        turnover: b.turnover,
                                        tick_count: 1,
                                        is_closed: true,
                                    };
                                    kb
                                })
                                .collect();
                            core_bars.sort_by_key(|b| b.open_time_ms);
                            let count = pipeline.kline_manager.seed_bars(sym, "1m", core_bars);
                            info!(symbol = sym, bars = count, "kline bootstrap / K 線引導完成");
                        }
                        Err(e) => warn!(symbol = sym, error = %e, "kline bootstrap failed / K 線引導失敗"),
                    }
                }
            } else {
                info!("kline bootstrap skipped — no REST client / K 線引導跳過（無 REST 客戶端）");
            }
        }

        // Persistence / 持久化
        let data_dir = std::env::var("OPENCLAW_DATA_DIR")
            .unwrap_or_else(|_| "/tmp/openclaw".into());
        let data_path = PathBuf::from(&data_dir);
        if let Err(e) = std::fs::create_dir_all(&data_path) {
            warn!(error = %e, "failed to create data dir / 創建數據目錄失敗");
        }
        let mut state_writer = StateWriter::new(
            &data_path.join("paper_state.json"), 30_000,
        );
        // Full pipeline snapshot for IPC file-read (R06-A)
        // 完整管線快照供 IPC 文件讀取使用
        let mut snapshot_writer = StateWriter::new(
            &data_path.join("pipeline_snapshot.json"), 5_000,
        );
        let audit_writer = AuditWriter::new(
            &data_path.join("paper_audit.jsonl"),
        );

        // Canary mode: emit per-tick JSONL for comparison with Python shadow (R07-2)
        // 灰度模式：每 tick 輸出 JSONL 用於與 Python 影子進程比較
        let canary_mode = std::env::var("OPENCLAW_CANARY_MODE").unwrap_or_default() == "1";
        pipeline.canary_mode = canary_mode;
        let canary_writer = if canary_mode {
            let canary_path = data_path.join("engine_results.jsonl");
            info!(path = %canary_path.display(), "canary mode enabled / 灰度模式已啟用");
            Some(std::fs::OpenOptions::new()
                .create(true).append(true)
                .open(&canary_path)
                .expect("failed to open canary JSONL / 打開灰度 JSONL 失敗"))
        } else {
            None
        };

        // ----------------------------------------------------------
        // Initial snapshot: write once immediately so that the
        // watchdog does not flag snapshot-age timeout during the
        // startup window before the first tick arrives.
        // 初始快照：啟動時立即寫入一次，避免 watchdog 在首個 tick
        // 到達前因 snapshot age 超時而誤判引擎崩潰。
        // ----------------------------------------------------------
        {
            let init_snap = pipeline.snapshot();
            if snapshot_writer.force_write(&init_snap) {
                info!("initial pipeline snapshot written / 初始管線快照已寫入");
            } else {
                warn!("failed to write initial pipeline snapshot / 初始管線快照寫入失敗");
            }
        }

        let mut last_status = Instant::now();
        let status_interval = std::time::Duration::from_secs(STATUS_INTERVAL_SECS);
        let start_time = Instant::now();

        loop {
            tokio::select! {
                _ = event_cancel.cancelled() => break,
                event = event_rx.recv() => {
                    match event {
                        Some(ev) => {
                            let prev_fills = pipeline.stats.total_fills;
                            let canary_record = pipeline.on_tick(&ev);

                            // Write canary record if in canary mode (R07-2)
                            // 灰度模式下寫入灰度記錄
                            if let Some(record) = canary_record {
                                if let Some(ref canary_file) = canary_writer {
                                    use std::io::Write;
                                    let mut f = canary_file;
                                    if let Ok(json) = serde_json::to_string(&record) {
                                        let _ = writeln!(f, "{}", json);
                                    }
                                }
                            }

                            // Audit new fills / 審計新成交
                            if pipeline.stats.total_fills > prev_fills {
                                let snap = pipeline.paper_state.export_state();
                                let _ = audit_writer.append(&serde_json::json!({
                                    "ts": ev.ts_ms,
                                    "symbol": ev.symbol,
                                    "price": ev.last_price,
                                    "fills": pipeline.stats.total_fills,
                                    "balance": snap.balance,
                                    "positions": snap.positions.len(),
                                    "realized_pnl": snap.total_realized_pnl,
                                }));
                                info!(
                                    symbol = %ev.symbol,
                                    price = ev.last_price,
                                    fills = pipeline.stats.total_fills,
                                    balance = format!("{:.2}", snap.balance),
                                    positions = snap.positions.len(),
                                    "new fill / 新成交"
                                );
                            }

                            // H1+H2 fix: Sync WS shared state → paper_state
                            // H1+H2 修復：同步 WS 共享狀態 → 紙盤狀態
                            if let Some(ref bal_arc) = shared_bybit_balance {
                                if let Ok(guard) = bal_arc.read() {
                                    if let Some(bal) = *guard {
                                        pipeline.paper_state.set_bybit_sync_balance(Some(bal));
                                    }
                                }
                            }
                            if let Some(ref pnl_arc) = shared_api_pnl {
                                if let Ok(guard) = pnl_arc.read() {
                                    for (symbol, &pnl) in guard.iter() {
                                        pipeline.paper_state.set_api_unrealized_pnl(symbol, pnl);
                                    }
                                }
                            }

                            // Periodic status + persistence / 定期狀態報告 + 持久化
                            if last_status.elapsed() >= status_interval {
                                let status = pipeline.status();
                                let uptime = start_time.elapsed().as_secs();
                                info!(
                                    ticks = status.stats.total_ticks,
                                    fills = status.stats.total_fills,
                                    intents = status.stats.total_intents,
                                    stops = status.stats.total_stops,
                                    balance = format!("{:.2}", status.balance),
                                    positions = status.positions,
                                    symbols = status.symbols_tracked,
                                    uptime_secs = uptime,
                                    "status report / 狀態報告"
                                );
                                let snap = pipeline.paper_state.export_state();
                                state_writer.maybe_write(&snap);
                                // Write full pipeline snapshot for IPC (R06-A)
                                let full_snap = pipeline.snapshot();
                                snapshot_writer.maybe_write(&full_snap);
                                last_status = Instant::now();
                            }
                        }
                        None => break,
                    }
                }
            }
        }

        // Shutdown: close all open positions before final state write.
        // 關閉：先平掉所有持倉，再寫入最終狀態。
        let closed = pipeline.paper_state.close_all_positions();
        if closed > 0 {
            info!(
                closed = closed,
                "shutdown — closed all open positions at market / 關閉 — 已市價平掉所有持倉"
            );
        }

        // Force-write final state / 強制寫入最終狀態
        let snap = pipeline.paper_state.export_state();
        state_writer.force_write(&snap);
        let full_snap = pipeline.snapshot();
        snapshot_writer.force_write(&full_snap);
        let status = pipeline.status();
        info!(
            ticks = status.stats.total_ticks,
            fills = status.stats.total_fills,
            balance = format!("{:.2}", status.balance),
            uptime_secs = start_time.elapsed().as_secs(),
            "event consumer stopped — final state saved / 事件消費者已停止 — 最終狀態已保存"
        );
    });

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
        if let Some((priv_ws_h, listener_h, _, _)) = _private_ws_handle {
            let _ = priv_ws_h.await;
            let _ = listener_h.await;
        }
    })
    .await;

    // 3. Clean up socket file / 清理套接字文件
    let socket_path = &config.get().ipc_socket_path;
    if std::path::Path::new(socket_path).exists() {
        let _ = tokio::fs::remove_file(socket_path).await;
        info!(path = socket_path, "socket file cleaned up / 套接字文件已清理");
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
