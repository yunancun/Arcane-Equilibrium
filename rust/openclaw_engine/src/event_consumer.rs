//! Event consumer — feeds PriceEvents from WS into TickPipeline for paper trading.
//! 事件消費者 — 將 WS 的 PriceEvent 送入 TickPipeline 進行紙盤交易。
//!
//! MODULE_NOTE (EN): Extracted from main.rs (Phase 1 Day 0-A) to keep main.rs under
//!   800-line warning limit. Owns TickPipeline lifecycle: creates pipeline, registers
//!   strategies, runs kline bootstrap, then loops receiving PriceEvents.
//! MODULE_NOTE (中): 從 main.rs 提取（Phase 1 Day 0-A），保持 main.rs 在 800 行警告線下。
//!   擁有 TickPipeline 生命週期：創建管線、註冊策略、執行 K 線引導、然後循環接收 PriceEvent。

use crate::config::ConfigManager;
use crate::instrument_info::InstrumentInfoCache;
use crate::persistence::{AuditWriter, StateWriter};
use crate::strategies::{
    bb_breakout::BbBreakout, bb_reversion::BbReversion, grid_trading::GridTrading,
    ma_crossover::MaCrossover,
};
use crate::tick_pipeline::{PaperSessionCommand, TickPipeline};
use openclaw_types::PriceEvent;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{error, info, warn};

use crate::bybit_rest_client::BybitRestClient;

/// Symbols tracked by the engine / 引擎追蹤的交易對
pub const SYMBOLS: &[&str] = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];

/// Status report interval (seconds) / 狀態報告間隔（秒）
const STATUS_INTERVAL_SECS: u64 = 30;

/// Dependencies bundle for the event consumer (W1 fix: avoids 9+ parameter function).
/// 事件消費者依賴集合（W1 修復：避免 9+ 參數的函數）。
pub struct EventConsumerDeps {
    pub event_rx: mpsc::Receiver<PriceEvent>,
    pub config: Arc<ConfigManager>,
    pub cancel: CancellationToken,
    pub initial_balance: f64,
    pub taker_fee_rate: Option<f64>,
    pub instruments: Option<Arc<InstrumentInfoCache>>,
    pub bootstrap_client: Option<Arc<BybitRestClient>>,
    pub shared_client: Option<Arc<BybitRestClient>>,
    pub bybit_balance: Option<Arc<std::sync::RwLock<Option<f64>>>>,
    pub api_pnl: Option<Arc<std::sync::RwLock<HashMap<String, f64>>>>,
    /// Paper session command receiver — IPC sends Pause/Resume/CloseAll/Reset.
    /// 紙盤 session 命令接收端 — IPC 發送 Pause/Resume/CloseAll/Reset。
    pub paper_cmd_rx: Option<mpsc::UnboundedReceiver<PaperSessionCommand>>,
    /// Phase 1: Channel to dispatch market data to async PG writer.
    /// Phase 1：市場數據派發通道。
    pub market_data_tx: Option<tokio::sync::mpsc::Sender<crate::database::MarketDataMsg>>,
    /// Phase 1: Channel to dispatch feature snapshots to async PG writer.
    /// Phase 1：特徵快照派發通道。
    pub feature_tx: Option<tokio::sync::mpsc::Sender<crate::feature_collector::FeatureSnapshot>>,
    /// Phase 1 (F-5): Shared last_tick_ms for quality monitor staleness detection.
    /// Phase 1（F-5）：共享 last_tick_ms 用於質量監控器過期檢測。
    pub last_tick_ms: Option<Arc<std::sync::atomic::AtomicU64>>,
    /// Phase 2a: Channel for trading lifecycle events (signals/intents/fills).
    /// Phase 2a：交易生命週期事件通道。
    pub trading_tx: Option<tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
    /// Phase 2a: Channel for decision context snapshots.
    /// Phase 2a：決策上下文快照通道。
    pub context_tx: Option<tokio::sync::mpsc::Sender<crate::database::DecisionContextMsg>>,
}

/// Run the event consumer loop: build pipeline, register strategies, process ticks.
/// 運行事件消費者循環：構建管線、註冊策略、處理 tick。
pub async fn run_event_consumer(deps: EventConsumerDeps) {
    let EventConsumerDeps {
        mut event_rx,
        config,
        cancel,
        initial_balance,
        taker_fee_rate,
        instruments: shared_instruments,
        bootstrap_client,
        shared_client,
        bybit_balance: shared_bybit_balance,
        api_pnl: shared_api_pnl,
        paper_cmd_rx,
        market_data_tx,
        feature_tx,
        last_tick_ms: shared_last_tick_ms,
        trading_tx,
        context_tx,
    } = deps;
    let mut paper_cmd_rx = paper_cmd_rx;

    let cfg_snapshot = config.get();

    // Build pipeline with Bybit Demo balance / 使用 Demo 餘額構建管線
    let mut pipeline = TickPipeline::with_balance(SYMBOLS, initial_balance);

    // Item 2: Set dynamic fee rate if available / 設定動態費率
    if let Some(rate) = taker_fee_rate {
        pipeline.set_fee_rate(rate);
        info!(taker_rate = format!("{:.5}", rate), "pipeline using API fee rate / 管線使用 API 費率");
    }

    // R-05: Wire instrument cache into pipeline for precision rounding
    // R-05：將合約信息緩存接入管線，用於精度取整
    if let Some(ref icache) = shared_instruments {
        pipeline.set_instrument_cache(Arc::clone(icache));
        info!("pipeline using instrument cache for precision rounding / 管線使用合約信息緩存進行精度取整");
    }

    // Phase 1: Wire market data + feature channels into pipeline
    // Phase 1：將市場數據 + 特徵通道接入管線
    if let Some(tx) = market_data_tx {
        pipeline.set_market_data_channel(tx);
        info!("pipeline market_data channel wired / 管線市場數據通道已接入");
    }
    if let Some(tx) = feature_tx {
        pipeline.set_feature_channel(tx);
        info!("pipeline feature channel wired / 管線特徵通道已接入");
    }
    if let Some(tx) = trading_tx {
        pipeline.set_trading_channel(tx);
        info!("pipeline trading channel wired / 管線交易通道已接入");
    }
    if let Some(tx) = context_tx {
        pipeline.set_context_channel(tx);
        info!("pipeline context channel wired / 管線上下文通道已接入");
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
            crate::tick_pipeline::StopRequest,
        >();
        pipeline.set_stop_channel(stop_tx);

        tokio::spawn(async move {
            while let Some(req) = stop_rx.recv().await {
                info!(
                    symbol = %req.symbol,
                    stop_loss = format!("{:.2}", req.stop_loss),
                    side = if req.is_long { "long" } else { "short" },
                    "server-side stop request dispatched / 伺服器端止損請求已派發"
                );
            }
        });
        info!("dual-track stop channel active / 雙軌止損通道已啟用");
    }

    // Shadow order mode: dispatch paper fills as real Demo API orders for calibration
    // 影子訂單模式：將紙盤成交作為真實 Demo API 訂單派發，用於校準比較
    if cfg_snapshot.shadow_orders {
        if let Some(ref client) = shared_client {
            if let Some(ref icache) = shared_instruments {
                use crate::order_manager::{
                    OrderManager, OrderCategory, OrderSide, OrderType, CreateOrderRequest,
                };
                let (shadow_tx, mut shadow_rx) = tokio::sync::mpsc::unbounded_channel::<
                    crate::tick_pipeline::ShadowOrderRequest,
                >();
                pipeline.set_shadow_channel(shadow_tx);

                let order_mgr = OrderManager::new(Arc::clone(client), Arc::clone(icache));
                tokio::spawn(async move {
                    let mut shadow_seq: u32 = 0;
                    while let Some(req) = shadow_rx.recv().await {
                        // Skip zero-qty orders (instrument rounding reduced qty to 0)
                        // 跳過零數量訂單（合約精度取整後數量為 0）
                        if req.qty <= 0.0 {
                            warn!(symbol = %req.symbol, "shadow order skipped: qty=0 / 影子訂單跳過：qty=0");
                            continue;
                        }
                        shadow_seq = shadow_seq.wrapping_add(1);
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
                            order_link_id: Some(format!("sh_{}_{}", req.paper_fill_ts, shadow_seq)),
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
    pipeline.orchestrator.register(Box::new(GridTrading::new_adaptive()));

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
            let mdc = crate::market_data_client::MarketDataClient::new(Arc::clone(client_arc));
            for &sym in SYMBOLS {
                match mdc.get_klines("linear", sym, "1", None, None, Some(200)).await {
                    Ok(bars) => {
                        let now_ms = std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_millis() as u64;
                        let mut core_bars: Vec<openclaw_core::klines::KlineBar> = bars
                            .iter()
                            .filter(|b| b.start_time + 60_000 <= now_ms)
                            .map(|b| {
                                openclaw_core::klines::KlineBar {
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
                                }
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

    // Initial snapshot for watchdog / 初始快照供 watchdog 使用
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

    // ── Main event loop / 主事件循環 ──
    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,

            // ── Paper session commands from IPC / 來自 IPC 的紙盤 session 命令 ──
            cmd = async {
                if let Some(ref mut rx) = paper_cmd_rx { rx.recv().await } else { std::future::pending().await }
            } => {
                match cmd {
                    Some(PaperSessionCommand::Pause) => {
                        pipeline.paper_paused = true;
                        info!("paper trading PAUSED via IPC / 紙盤交易已通過 IPC 暫停");
                        // Force snapshot so GUI sees paused state immediately
                        snapshot_writer.force_write(&pipeline.snapshot());
                    }
                    Some(PaperSessionCommand::Resume) => {
                        pipeline.paper_paused = false;
                        info!("paper trading RESUMED via IPC / 紙盤交易已通過 IPC 恢復");
                        snapshot_writer.force_write(&pipeline.snapshot());
                    }
                    Some(PaperSessionCommand::CloseAll) => {
                        let closed = pipeline.paper_state.close_all_positions();
                        info!(closed = closed, "IPC close_all_positions / IPC 全部平倉");
                        snapshot_writer.force_write(&pipeline.snapshot());
                    }
                    Some(PaperSessionCommand::Reset { new_balance }) => {
                        pipeline.paper_state = crate::paper_state::PaperState::new(new_balance);
                        pipeline.stats = crate::tick_pipeline::TickStats::default();
                        pipeline.paper_paused = false;
                        info!(balance = format!("{:.2}", new_balance), "IPC reset paper state / IPC 重置紙盤狀態");
                        snapshot_writer.force_write(&pipeline.snapshot());
                    }
                    // ── Phase 3b: Strategy parameter IPC commands / 策略參數 IPC 命令 ──
                    Some(PaperSessionCommand::UpdateStrategyParams { strategy_name, params_json, response_tx }) => {
                        let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                            Some(strategy) => {
                                match strategy.update_params_json(&params_json) {
                                    Ok(()) => {
                                        info!(strategy = %strategy_name, "strategy params updated via IPC / 策略參數已通過 IPC 更新");
                                        snapshot_writer.force_write(&pipeline.snapshot());
                                        Ok(format!("params updated for {}", strategy_name))
                                    }
                                    Err(e) => Err(format!("validation failed: {e}"))
                                }
                            }
                            None => Err(format!("strategy not found: {strategy_name}"))
                        };
                        let _ = response_tx.send(result);
                    }
                    Some(PaperSessionCommand::GetStrategyParams { strategy_name, response_tx }) => {
                        let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                            Some(strategy) => Ok(strategy.get_params_json()),
                            None => Err(format!("strategy not found: {strategy_name}"))
                        };
                        let _ = response_tx.send(result);
                    }
                    Some(PaperSessionCommand::GetParamRanges { strategy_name, response_tx }) => {
                        let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                            Some(strategy) => Ok(strategy.param_ranges_json()),
                            None => Err(format!("strategy not found: {strategy_name}"))
                        };
                        let _ = response_tx.send(result);
                    }
                    None => {} // channel closed, ignore / 通道關閉，忽略
                }
            },

            event = event_rx.recv() => {
                match event {
                    Some(ev) => {
                        // F-5: Update shared last_tick_ms for quality monitor
                        if let Some(ref tick_ms) = shared_last_tick_ms {
                            tick_ms.store(ev.ts_ms, std::sync::atomic::Ordering::Relaxed);
                        }
                        let prev_fills = pipeline.stats.total_fills;
                        let canary_record = pipeline.on_tick(&ev);

                        // Write canary record if in canary mode (R07-2)
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

    // Shutdown: close all open positions before final state write
    // 關閉：先平掉所有持倉，再寫入最終狀態
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
}
