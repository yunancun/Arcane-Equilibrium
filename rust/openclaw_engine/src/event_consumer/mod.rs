//! Event consumer — feeds PriceEvents from WS into TickPipeline for paper trading.
//! 事件消費者 — 將 WS 的 PriceEvent 送入 TickPipeline 進行紙盤交易。
//!
//! MODULE_NOTE (EN): Extracted from main.rs (Phase 1 Day 0-A) to keep main.rs under
//!   800-line warning limit. Owns TickPipeline lifecycle: creates pipeline, registers
//!   strategies, runs kline bootstrap, then loops receiving PriceEvents.
//! MODULE_NOTE (中): 從 main.rs 提取（Phase 1 Day 0-A），保持 main.rs 在 800 行警告線下。
//!   擁有 TickPipeline 生命週期：創建管線、註冊策略、執行 K 線引導、然後循環接收 PriceEvent。

#[cfg(test)]
mod tests;
mod dispatch;
mod handlers;
mod setup;
mod types;

use types::STATUS_INTERVAL_SECS;
pub use types::{EventConsumerDeps, ExchangeEvent, PendingOrder, SYMBOLS};

use crate::persistence::{AuditWriter, StateWriter};
use crate::strategies::{
    bb_breakout::BbBreakout, bb_reversion::BbReversion, grid_trading::GridTrading,
    ma_crossover::MaCrossover,
};
use crate::tick_pipeline::TickPipeline;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::mpsc;
use tracing::{error, info, warn};

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
        exchange_event_rx: _exchange_event_rx_field,
        account_manager,
    } = deps;
    let mut paper_cmd_rx = paper_cmd_rx;

    let cfg_snapshot = config.get();

    // Build pipeline with Bybit Demo balance / 使用 Demo 餘額構建管線
    let mut pipeline = TickPipeline::with_balance(SYMBOLS, initial_balance);

    // I-22: Pipeline wire-up extracted to setup helper.
    setup::wire_pipeline(
        &mut pipeline,
        &cfg_snapshot,
        taker_fee_rate,
        shared_instruments.as_ref(),
        market_data_tx,
        feature_tx,
        trading_tx,
        context_tx,
    );

    // Wire AccountManager for live per-symbol fee lookups (cost gate / Kelly / cost_ratio).
    if let Some(am) = account_manager {
        pipeline.set_account_manager(Arc::clone(&am));
        info!("pipeline using AccountManager for per-symbol fee rates / 接入動態費率");
    }

    // Item 3: Bybit sync mode — set initial sync balance / 設定 Bybit 同步餘額
    if cfg_snapshot.balance_mode == "bybit_sync" {
        pipeline
            .paper_state
            .set_bybit_sync_balance(Some(initial_balance));
        info!(
            balance = format!("{:.2}", initial_balance),
            "bybit_sync mode — tracking Bybit Demo balance / 同步模式已啟用"
        );
    }

    // Item 1: Server-side stop channel (dual-track stops)
    // 項目 1：伺服器端止損通道（雙軌止損）
    if cfg_snapshot.server_side_stops {
        let (stop_tx, mut stop_rx) =
            tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::StopRequest>();
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

    // EXT-1: Set trading mode on pipeline / 設定管線交易模式
    pipeline.set_trading_mode(cfg_snapshot.trading_mode);
    let is_exchange_mode = cfg_snapshot.trading_mode == crate::config::TradingMode::Exchange;
    if is_exchange_mode {
        info!("EXT-1: exchange mode active — orders sent to exchange, fills confirmed via WS / 交易所模式啟用");
    }

    // Order dispatch: shadow orders (paper_only) or primary orders (exchange mode)
    // 訂單派發：影子訂單（紙盤模式）或主訂單（交易所模式）
    let pending_reg_rx_slot = dispatch::spawn_order_dispatch(
        &mut pipeline,
        shared_client.as_ref(),
        shared_instruments.as_ref(),
        cfg_snapshot.shadow_orders || is_exchange_mode,
    );

    // Register strategies / 註冊策略
    pipeline.orchestrator.register(Box::new(MaCrossover::new()));
    pipeline.orchestrator.register(Box::new(BbReversion::new()));
    pipeline.orchestrator.register(Box::new(BbBreakout::new()));
    pipeline
        .orchestrator
        .register(Box::new(GridTrading::new_adaptive()));

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
                match mdc
                    .get_klines("linear", sym, "1", None, None, Some(200))
                    .await
                {
                    Ok(bars) => {
                        let now_ms = std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_millis() as u64;
                        let mut core_bars: Vec<openclaw_core::klines::KlineBar> = bars
                            .iter()
                            .filter(|b| b.start_time + 60_000 <= now_ms)
                            .map(|b| openclaw_core::klines::KlineBar {
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
                            })
                            .collect();
                        core_bars.sort_by_key(|b| b.open_time_ms);
                        let count = pipeline.kline_manager.seed_bars(sym, "1m", core_bars);
                        info!(symbol = sym, bars = count, "kline bootstrap / K 線引導完成");
                    }
                    Err(e) => {
                        warn!(symbol = sym, error = %e, "kline bootstrap failed / K 線引導失敗")
                    }
                }
            }
        } else {
            info!("kline bootstrap skipped — no REST client / K 線引導跳過（無 REST 客戶端）");
        }
    }

    // Persistence / 持久化
    let data_dir = std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into());
    let data_path = PathBuf::from(&data_dir);
    if let Err(e) = std::fs::create_dir_all(&data_path) {
        warn!(error = %e, "failed to create data dir / 創建數據目錄失敗");
    }
    let mut state_writer = StateWriter::new(&data_path.join("paper_state.json"), 30_000);
    let mut snapshot_writer = StateWriter::new(&data_path.join("pipeline_snapshot.json"), 5_000);
    let audit_writer = AuditWriter::new(&data_path.join("paper_audit.jsonl"));

    // Canary mode: emit per-tick JSONL for comparison with Python shadow (R07-2)
    // 灰度模式：每 tick 輸出 JSONL 用於與 Python 影子進程比較
    let canary_mode = std::env::var("OPENCLAW_CANARY_MODE").unwrap_or_default() == "1";
    pipeline.canary_mode = canary_mode;
    let canary_writer = if canary_mode {
        let canary_path = data_path.join("engine_results.jsonl");
        info!(path = %canary_path.display(), "canary mode enabled / 灰度模式已啟用");
        Some(
            std::fs::OpenOptions::new()
                .create(true)
                .append(true)
                .open(&canary_path)
                .expect("failed to open canary JSONL / 打開灰度 JSONL 失敗"),
        )
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

    // EXT-1: Pending order tracking for exchange mode
    // EXT-1：交易所模式的待處理訂單追蹤
    let mut pending_orders: HashMap<String, PendingOrder> = HashMap::new();
    // P0-1 fix: order_id → order_link_id mapping (populated from OrderUpdate, used in Fill matching)
    let mut order_id_to_link: HashMap<String, String> = HashMap::new();
    // P0-2 fix: exec_id dedup set (prevent duplicate fill application on WS reconnect)
    // P0-2 修復：exec_id 去重集合（防止 WS 重連時重複應用成交）
    let mut seen_exec_ids: std::collections::VecDeque<String> = std::collections::VecDeque::new();
    const MAX_SEEN_EXEC_IDS: usize = 500;
    let mut exchange_event_rx = _exchange_event_rx_field;
    let mut pending_reg_rx = pending_reg_rx_slot;
    let mut last_pending_check = Instant::now();
    let pending_timeout = std::time::Duration::from_secs(5);

    // ── Main event loop / 主事件循環 ──
    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,

            // ── EXT-1: Exchange events (fills/order updates) from ExecutionListener ──
            // ── EXT-1：來自執行監聽器的交易所事件（成交/訂單更新）──
            exchange_evt = async {
                if let Some(ref mut rx) = exchange_event_rx { rx.recv().await } else { std::future::pending().await }
            } => {
                match exchange_evt {
                    Some(ExchangeEvent::Fill(exec)) => {
                        // P0-2: Dedup by exec_id (prevent duplicate fill on WS reconnect)
                        if seen_exec_ids.iter().any(|id| id == &exec.exec_id) {
                            warn!(exec_id = %exec.exec_id, "duplicate fill skipped / 重複成交已跳過");
                            continue;
                        }
                        seen_exec_ids.push_back(exec.exec_id.clone());
                        if seen_exec_ids.len() > MAX_SEEN_EXEC_IDS {
                            seen_exec_ids.pop_front();
                        }

                        let exec_qty: f64 = exec.exec_qty.parse().unwrap_or(0.0);
                        let exec_price: f64 = exec.exec_price.parse().unwrap_or(0.0);
                        let exec_fee: f64 = exec.exec_fee.parse().unwrap_or(0.0);
                        let exec_ts: u64 = exec.exec_time.parse().unwrap_or(0);

                        info!(
                            exec_id = %exec.exec_id,
                            order_id = %exec.order_id,
                            symbol = %exec.symbol,
                            side = %exec.side,
                            qty = exec_qty,
                            price = exec_price,
                            fee = exec_fee,
                            "exchange fill received / 收到交易所成交"
                        );

                        // P0-1 fix: Match fill via order_id → order_link_id mapping
                        // OrderUpdate populates the mapping, Fill uses it
                        let matched_key = order_id_to_link.get(&exec.order_id).cloned()
                            .or_else(|| {
                                // Fallback: symbol+side match if no order_id mapping yet
                                let is_buy = exec.side == "Buy";
                                pending_orders.iter()
                                    .find(|(_, po)| po.symbol == exec.symbol && po.is_long == is_buy && po.cum_filled_qty < po.qty)
                                    .map(|(k, _)| k.clone())
                            });

                        if let Some(key) = matched_key {
                            if let Some(po) = pending_orders.get_mut(&key) {
                                po.cum_filled_qty += exec_qty;
                                pipeline.apply_confirmed_fill(
                                    &exec.symbol,
                                    po.is_long,
                                    exec_qty,
                                    exec_price,
                                    exec_fee,
                                    exec_ts,
                                    &po.strategy,
                                    &po.order_link_id,
                                );
                                snapshot_writer.force_write(&pipeline.snapshot());

                                if po.cum_filled_qty >= po.qty * 0.999 {
                                    info!(order_link_id = %key, "pending order fully filled, removing / 待處理訂單完全成交，移除");
                                    pending_orders.remove(&key);
                                }
                            }
                        } else {
                            warn!(
                                symbol = %exec.symbol, side = %exec.side,
                                "exchange fill has no matching pending order / 交易所成交無匹配的待處理訂單"
                            );
                        }
                    }
                    Some(ExchangeEvent::OrderUpdate(order)) => {
                        // P0-1: Build order_id → order_link_id mapping for fill matching
                        if !order.order_link_id.is_empty() && !order.order_id.is_empty() {
                            order_id_to_link.insert(order.order_id.clone(), order.order_link_id.clone());
                        }
                        // Match by order_link_id directly
                        if !order.order_link_id.is_empty() {
                            if let Some(po) = pending_orders.get_mut(&order.order_link_id) {
                                let status = &order.order_status;
                                info!(
                                    order_link_id = %order.order_link_id,
                                    status = %status,
                                    symbol = %order.symbol,
                                    "pending order status update / 待處理訂單狀態更新"
                                );
                                if status == "Cancelled" || status == "Rejected" || status == "Deactivated" {
                                    // P0-4: If this was a close order, clear pending_close flag
                                    // P0-4：如果是平倉訂單，清除待處理平倉標記
                                    if let Some(po) = pending_orders.get(&order.order_link_id) {
                                        if po.is_close {
                                            pipeline.clear_pending_close(&po.symbol);
                                            warn!(
                                                order_link_id = %order.order_link_id,
                                                symbol = %po.symbol,
                                                "close order {} — clearing pending_close / 平倉訂單{} — 清除待處理平倉",
                                                status, status,
                                            );
                                        }
                                    }
                                    warn!(
                                        order_link_id = %order.order_link_id,
                                        status = %status,
                                        "pending order failed — removing / 待處理訂單失敗，移除"
                                    );
                                    pending_orders.remove(&order.order_link_id);
                                }
                            }
                        }
                    }
                    Some(ExchangeEvent::DcpTriggered) => {
                        // DCP: Exchange auto-cancelled all orders
                        let count = pending_orders.len();
                        if count > 0 {
                            warn!(
                                count = count,
                                "DCP triggered — clearing {} pending orders / DCP 觸發，清除 {} 個待處理訂單",
                                count, count,
                            );
                            pending_orders.clear();
                        }
                        // Also clear pending_close flags since DCP cancelled close orders too
                        pipeline.clear_all_pending_close();
                        warn!("DCP triggered — exchange cancelled active orders, pending_close cleared");
                    }
                    Some(ExchangeEvent::Disconnected) => {
                        // Private WS disconnected — pending orders may be in unknown state
                        if !pending_orders.is_empty() {
                            warn!(
                                pending = pending_orders.len(),
                                "private WS disconnected with {} pending orders — reconcile on reconnect \
                                / 私有 WS 斷連，{} 個待處理訂單 — 重連後對賬",
                                pending_orders.len(), pending_orders.len(),
                            );
                        }
                    }
                    None => {} // channel closed
                }
            },

            // ── EXT-1: Pending order registration from dispatch task ──
            pending_reg = async {
                if let Some(ref mut rx) = pending_reg_rx { rx.recv().await } else { std::future::pending().await }
            } => {
                if let Some(po) = pending_reg {
                    info!(
                        order_link_id = %po.order_link_id, symbol = %po.symbol,
                        qty = %po.qty, strategy = %po.strategy,
                        "pending order registered / 待處理訂單已註冊"
                    );
                    pending_orders.insert(po.order_link_id.clone(), po);
                }
            },

            // ── Paper session commands from IPC / 來自 IPC 的紙盤 session 命令 ──
            cmd = async {
                if let Some(ref mut rx) = paper_cmd_rx { rx.recv().await } else { std::future::pending().await }
            } => {
                if let Some(cmd) = cmd {
                    handlers::handle_paper_command(
                        cmd,
                        &mut pipeline,
                        &mut snapshot_writer,
                        &mut pending_orders,
                    );
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
                                    // P0-5: In exchange mode, reconcile local balance from exchange
                                    // P0-5：交易所模式下，從交易所餘額對賬本地餘額
                                    if is_exchange_mode {
                                        if let Some(old_bal) = pipeline.paper_state.reconcile_balance_from_exchange(bal) {
                                            warn!(
                                                old = format!("{:.2}", old_bal),
                                                new = format!("{:.2}", bal),
                                                "balance reconciled from exchange / 餘額已從交易所對賬"
                                            );
                                        }
                                    }
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

                        // EXT-1: Check for timed-out pending orders (every 5s)
                        if !pending_orders.is_empty() && last_pending_check.elapsed() >= pending_timeout {
                            let now_ms = std::time::SystemTime::now()
                                .duration_since(std::time::UNIX_EPOCH)
                                .unwrap_or_default()
                                .as_millis() as u64;
                            let stale_keys: Vec<String> = pending_orders
                                .iter()
                                .filter(|(_, po)| now_ms.saturating_sub(po.sent_ts_ms) > 5000)
                                .map(|(k, _)| k.clone())
                                .collect();
                            for key in &stale_keys {
                                if let Some(po) = pending_orders.get(key) {
                                    let elapsed = now_ms.saturating_sub(po.sent_ts_ms);
                                    if elapsed > 60_000 {
                                        // P1-1 fix: Hard timeout — remove after 60s
                                        error!(
                                            order_link_id = %key,
                                            symbol = %po.symbol,
                                            elapsed_ms = elapsed,
                                            "pending order hard timeout (>60s) — removing / 待處理訂單硬超時，移除"
                                        );
                                    } else {
                                        warn!(
                                            order_link_id = %key,
                                            symbol = %po.symbol,
                                            elapsed_ms = elapsed,
                                            filled = %po.cum_filled_qty,
                                            requested = %po.qty,
                                            "pending order soft timeout (>5s) / 待處理訂單軟超時"
                                        );
                                    }
                                }
                            }
                            // P1-1: Remove orders that exceeded hard timeout / 移除超過硬超時的訂單
                            pending_orders.retain(|_, po| now_ms.saturating_sub(po.sent_ts_ms) <= 60_000);
                            // Clean stale order_id mappings: only keep those with active pending orders
                            // 清理過期 order_id 映射：僅保留有活躍待處理訂單的
                            if order_id_to_link.len() > 50 {
                                let active_links: std::collections::HashSet<&String> =
                                    pending_orders.keys().collect();
                                order_id_to_link.retain(|_, link| active_links.contains(link));
                            }
                            last_pending_check = Instant::now();
                        }

                        // RRC-1-A2: Periodic H0Gate risk snapshot update (every status interval).
                        // RRC-1-A2：定期更新 H0 門控風控快照（每狀態報告間隔）。
                        if last_status.elapsed() >= status_interval {
                            let positions = pipeline.paper_state.positions();
                            let position_count = positions.len() as u32;
                            let balance = pipeline.paper_state.export_state().balance;
                            let total_exposure_pct = if balance > 0.0 {
                                let total_notional: f64 = positions.iter().map(|p| {
                                    let price = pipeline.latest_prices().get(&p.symbol)
                                        .copied().unwrap_or(p.entry_price);
                                    p.qty * price
                                }).sum();
                                (total_notional / balance * 100.0).min(999.0)
                            } else {
                                0.0
                            };
                            pipeline.h0_gate.update_risk(openclaw_types::H0GateRiskSnapshot {
                                open_position_count: position_count,
                                total_exposure_pct,
                                cooldown_until_ts_ms: 0,
                                kill_switch_active: false,
                                snapshot_ts_ms: std::time::SystemTime::now()
                                    .duration_since(std::time::UNIX_EPOCH)
                                    .unwrap_or_default()
                                    .as_millis() as u64,
                            });

                            let status = pipeline.status();
                            let uptime = start_time.elapsed().as_secs();
                            let h0_stats = pipeline.h0_gate.get_stats();
                            // PNL-2: invariant — every tick must run H0Gate.check.
                            // PNL-2：不變量 — 每個 tick 必須走過 H0Gate.check。
                            // If ticks > 0 but checks == 0 → stale binary or wiring regression.
                            // 若 ticks > 0 而 checks == 0 → stale binary 或接線退化。
                            if status.stats.total_ticks > 0 && h0_stats.total_checks == 0 {
                                warn!(
                                    ticks = status.stats.total_ticks,
                                    "PNL-2 invariant violated: ticks>0 but H0Gate checks==0 — stale binary? / H0 門控未執行"
                                );
                            }
                            info!(
                                ticks = status.stats.total_ticks,
                                fills = status.stats.total_fills,
                                intents = status.stats.total_intents,
                                stops = status.stats.total_stops,
                                balance = format!("{:.2}", status.balance),
                                positions = status.positions,
                                symbols = status.symbols_tracked,
                                uptime_secs = uptime,
                                h0_checks = h0_stats.total_checks,
                                h0_blocked = h0_stats.total_blocked(),
                                h0_shadow_would_block = h0_stats.shadow_would_block,
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
