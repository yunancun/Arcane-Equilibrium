//! OpenClaw Engine entry point — tokio runtime, signal handling, startup/shutdown (R01-2).
//! OpenClaw 引擎入口 — tokio 運行時、信號處理、啟動/關閉序列。
//!
//! MODULE_NOTE (EN): Sets up multi-thread tokio runtime for IPC + WS + background tasks.
//!   SIGHUP triggers config hot-reload. SIGTERM/SIGINT triggers graceful shutdown.
//!   Event consumer feeds PriceEvents into TickPipeline for paper trading.
//! MODULE_NOTE (中): 設置多線程 tokio 運行時用於 IPC + WS + 後台任務。
//!   SIGHUP 觸發配置熱加載。SIGTERM/SIGINT 觸發優雅關閉。
//!   事件消費者將 PriceEvent 送入 TickPipeline 進行紙盤交易。

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
use tracing::{error, info, warn};

/// Engine version from Cargo.toml / 引擎版本（來自 Cargo.toml）
const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Price event channel buffer size / 價格事件通道緩衝區大小
const EVENT_CHANNEL_SIZE: usize = 4096;

/// Status report interval / 狀態報告間隔
const STATUS_INTERVAL_SECS: u64 = 30;

/// Symbols to track / 追蹤的交易對
const SYMBOLS: &[&str] = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];

/// Initial paper balance / 初始紙盤餘額
const PAPER_BALANCE: f64 = 10_000.0;

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

/// Async entry point running inside the multi-thread runtime.
/// 在多線程運行時內執行的異步入口。
async fn async_main(config: Arc<ConfigManager>) {
    let cancel = CancellationToken::new();

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
    // Start WS client — subscribe to all symbols
    // 啟動 WebSocket 客戶端 — 訂閱所有交易對
    // ------------------------------------------------------------------
    let mut ws_client = WsClient::new(Arc::clone(&config), event_tx, cancel.clone());
    for sym in SYMBOLS {
        ws_client.subscribe(format!("kline.1.{sym}"));
        ws_client.subscribe(format!("publicTrade.{sym}"));
    }
    let ws_handle = tokio::spawn(async move {
        ws_client.run().await;
    });

    // ------------------------------------------------------------------
    // Event consumer — feeds into TickPipeline for paper trading
    // 事件消費者 — 送入 TickPipeline 進行紙盤交易
    // ------------------------------------------------------------------
    let event_cancel = cancel.clone();
    let event_handle = tokio::spawn(async move {
        // Build pipeline / 構建管線
        let mut pipeline = TickPipeline::new(SYMBOLS);

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
            balance = PAPER_BALANCE,
            "pipeline ready — {} strategies on {} symbols / 管線就緒",
            pipeline.orchestrator.strategy_count(),
            SYMBOLS.len(),
        );

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

        // Shutdown: force-write final state / 關閉：強制寫入最終狀態
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
