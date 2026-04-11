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
pub mod handlers;
mod setup;
mod types;

use types::STATUS_INTERVAL_SECS;
pub use types::{EventConsumerDeps, ExchangeEvent, PendingOrder, SYMBOLS};

use crate::persistence::{AuditWriter, StateWriter};
use crate::strategies::StrategyFactory;
use crate::tick_pipeline::TickPipeline;
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Instant;
use tracing::{error, info, warn};

/// Run the event consumer loop: build pipeline, register strategies, process ticks.
/// 運行事件消費者循環：構建管線、註冊策略、處理 tick。
pub async fn run_event_consumer(deps: EventConsumerDeps) {
    let EventConsumerDeps {
        pipeline_kind,
        mut event_rx,
        config,
        cancel,
        initial_balance,
        paper_initial_balance,
        taker_fee_rate,
        instruments: shared_instruments,
        bootstrap_client,
        shared_client,
        bybit_balance: shared_bybit_balance,
        api_pnl: shared_api_pnl,
        pipeline_cmd_rx,
        market_data_tx,
        feature_tx,
        last_tick_ms: shared_last_tick_ms,
        trading_tx,
        context_tx,
        exchange_event_rx: _exchange_event_rx_field,
        account_manager,
        linucb_runtime,
        news_snapshot,
        risk_store,
        budget_store,
        audit_pool,
        symbol_registry,
        scanner_store: _scanner_store,
        shared_risk_level,
    } = deps;
    let mut pipeline_cmd_rx = pipeline_cmd_rx;

    let cfg_snapshot = config.get();

    // Build pipeline with kind-appropriate governance + balance (3E-2a)
    // 以 kind 對應的治理 + 餘額構建管線（3E-2a）
    let mut pipeline = TickPipeline::with_kind(SYMBOLS, initial_balance, pipeline_kind);

    // D2/D3: Track known symbols so we can diff against registry and call
    // pipeline.add_symbol / remove_symbol when the scanner changes the universe.
    // Seeded from the static SYMBOLS list; diverges as scanner runs.
    // D2/D3：追蹤已知交易對，以便在掃描器更新品類時差分並調用
    // pipeline.add_symbol / remove_symbol。從靜態 SYMBOLS 初始化。
    let mut known_symbols: std::collections::HashSet<String> =
        SYMBOLS.iter().map(|s| s.to_string()).collect();

    // D3: Channel for async kline bootstrap results (spawned task → main loop).
    // D3：異步 K 線引導結果通道（生成任務 → 主循環）。
    let (kline_seed_tx, mut kline_seed_rx) =
        tokio::sync::mpsc::channel::<(String, Vec<openclaw_core::klines::KlineBar>)>(8);

    // ── ARCH-RC1 1C-4 B1: restore governor de-escalation cooldown from V014 ──
    // Every successful operator de-escalation already writes a V014 row
    // (event_type='governor_de_escalate', payload.result='applied'). On startup
    // we replay the most recent one — if it falls inside the 24h window, the
    // cooldown survives a restart. Fail-soft: PG missing / query failure logs
    // a warn and starts fresh; other guards (whitelist, step, hold, CB/MR) keep
    // operating, so cooldown is a defence-in-depth layer not a single-point gate.
    // ARCH-RC1 1C-4 B1：從 V014 還原 governor 降級冷卻。每次 operator 成功降級
    // 都寫了 V014 row，啟動時 replay 最新一筆，若在 24h 窗口內則沿用，使重啟
    // 不會靜默重置 24h cooldown。fail-soft：PG 不可用或查詢失敗時 warn 並從零
    // 開始，其他守衛照常生效。
    if let Some(pool) = audit_pool.as_ref() {
        let now_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        match load_governor_cooldown_from_audit(pool, now_ms).await {
            Some(ts_ms) => {
                pipeline.set_last_governor_de_escalation_ms(Some(ts_ms));
                let remaining_ms = TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS
                    .saturating_sub(now_ms.saturating_sub(ts_ms));
                info!(
                    last_ts_ms = ts_ms,
                    remaining_ms,
                    "ARCH-RC1 1C-4 B1: restored governor de-escalation cooldown from V014 \
                     / 從 V014 還原 governor 降級冷卻"
                );
            }
            None => {
                info!(
                    "ARCH-RC1 1C-4 B1: no active governor cooldown in V014 (cold start) \
                     / V014 內無活躍 governor 冷卻（冷啟動）"
                );
            }
        }
    } else {
        warn!(
            "ARCH-RC1 1C-4 B1: audit pool unavailable; governor cooldown starts fresh \
             (fail-soft) / 審計 pool 不可用，governor 冷卻將從零開始（fail-soft）"
        );
    }

    // Clone trading_tx before moving into pipeline — event loop needs it for
    // order lifecycle DB writes (trading.orders + order_state_changes).
    // 在移入 pipeline 前克隆，供事件循環寫入 trading.orders + order_state_changes。
    let order_tx = trading_tx.clone();

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

    // Phase 4 W-3: Wire LinUCB runtime (read-only arm selection, metadata only).
    // Phase 4 W-3：接入 LinUCB 運行時（唯讀 arm 選擇，僅 metadata）。
    if let Some(rt) = linucb_runtime {
        pipeline.set_linucb_runtime(rt);
        info!("pipeline using LinUcbRuntime for arm metadata / 接入 LinUCB runtime");
    }

    // Phase 4 W-4: Wire shared NewsContextSnapshot (news_severity + hours_since_last_major_news).
    // Phase 4 W-4：接入共享 NewsContextSnapshot（news_severity + hours_since_last_major_news）。
    if let Some(snap) = news_snapshot {
        pipeline.set_news_snapshot(snap);
        info!("pipeline using NewsContextSnapshot for news context / 接入新聞快照");
    }

    // ARCH-RC1 1C-2-B: Wire live RiskConfig + BudgetConfig stores.
    // First tick after this point reads the real operator-authored config
    // and hot-reloads automatically on every IPC patch that bumps the version.
    // ARCH-RC1 1C-2-B：接入 live RiskConfig + BudgetConfig store，
    // 此後每次 tick 即讀真實 operator 配置；IPC patch 令版本上升時自動熱重載。
    if let Some(store) = risk_store {
        pipeline.set_risk_store(store);
        info!("pipeline wired to live RiskConfig ConfigStore / 接入 RiskConfig 熱重載");
    }
    if let Some(store) = budget_store {
        pipeline.set_budget_store(store);
        info!("pipeline wired to live BudgetConfig ConfigStore / 接入 BudgetConfig 熱重載");
    }

    // PH5-WIRE-1: Load JS shrunk edge estimates from settings/edge_estimates.json.
    // Cold-start (file absent) → empty estimates → ATR×0.2 fallback remains active.
    // PH5-WIRE-1：從 settings/edge_estimates.json 加載 JS 收縮邊際估計。
    // 冷啟動（文件缺失）→ 空估計 → ATR×0.2 回退保持激活。
    {
        let base = std::env::var("OPENCLAW_BASE_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| {
                // Engine is launched from srv/ (restart_all.sh cd's there before exec).
                // current_dir() == srv/ → srv/settings/edge_estimates.json is correct.
                // 引擎從 srv/ 目錄啟動（restart_all.sh 在 exec 前 cd 到該目錄）。
                std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."))
            });
        let estimates = crate::edge_estimates::EdgeEstimates::load_from_env_or_default(&base);
        if estimates.is_populated() {
            info!(
                n_cells = estimates.n_cells(),
                grand_mean_bps = estimates.grand_mean_bps(),
                "PH5-WIRE-1: JS edge estimates loaded / JS 邊際估計已加載"
            );
        } else {
            info!("PH5-WIRE-1: no edge snapshot — cold-start ATR×0.2 fallback / 無快照，ATR 回退");
        }
        pipeline.set_edge_estimates(estimates);
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

        // P9: Clone shared client for exchange-side conditional stop orders
        // (Principle #9 dual-rail: local stop + exchange stop).
        // Paper mode: no client → log only. Demo/Live: call Bybit trading-stop API.
        // P9：Clone 共享客戶端用於交易所端條件止損單
        // （根原則 #9 雙軌止損：本地止損 + 交易所止損）。
        // 紙盤模式無客戶端僅記錄；Demo/Live 調用 Bybit API。
        let stop_client = shared_client.clone();

        tokio::spawn(async move {
            // Create PositionManager once if exchange client is available.
            // 若交易所客戶端可用，一次性創建 PositionManager。
            let pos_mgr = stop_client
                .map(crate::position_manager::PositionManager::new);

            while let Some(req) = stop_rx.recv().await {
                info!(
                    symbol = %req.symbol,
                    stop_loss = format!("{:.2}", req.stop_loss),
                    side = if req.is_long { "long" } else { "short" },
                    "server-side stop request dispatched / 伺服器端止損請求已派發"
                );

                // P9: Place exchange-side conditional stop (dual-rail, Principle #9).
                // Fail-closed on API error: local StopManager remains active.
                // P9：放置交易所端條件止損（雙軌，根原則 #9）。
                // API 失敗時 fail-closed：本地 StopManager 仍生效。
                if let Some(ref mgr) = pos_mgr {
                    let stop_req = crate::position_manager::TradingStopRequest {
                        category: crate::order_manager::OrderCategory::Linear,
                        symbol: req.symbol.clone(),
                        take_profit: None,
                        stop_loss: Some(req.stop_loss),
                        tp_trigger_by: None,
                        sl_trigger_by: Some("LastPrice".to_string()),
                        trailing_stop: None,
                        active_price: None,
                        position_idx: Some(0), // one-way mode / 單向模式
                    };
                    match mgr.set_trading_stop(stop_req).await {
                        Ok(()) => {
                            info!(
                                symbol = %req.symbol,
                                stop_loss = format!("{:.2}", req.stop_loss),
                                "P9: exchange stop-loss set / 交易所止損已設置"
                            );
                        }
                        Err(e) => {
                            warn!(
                                symbol = %req.symbol,
                                error = %e,
                                "P9: exchange stop-loss failed (local stop active) \
                                 / 交易所止損失敗（本地止損生效）"
                            );
                        }
                    }
                }
            }
        });
        info!("dual-track stop channel active / 雙軌止損通道已啟用");
    }

    // EXT-1: Set trading mode on pipeline / 設定管線交易模式
    pipeline.set_trading_mode(cfg_snapshot.trading_mode);

    // When trading_mode=Live, update paper mode (PaperOnly) balance to the demo slot value.
    // Must be done AFTER set_trading_mode(), because set_trading_mode() calls
    // sync_direct_to_mode_state(old=PaperOnly) which would overwrite any earlier update.
    // After set_trading_mode(Live): mode_states[PaperOnly] has balance=initial_balance (live).
    // We replace it with the demo slot balance so paper always mirrors the Demo account.
    // Live 模式下更新 paper 模式餘額為 demo 槽數值。必須在 set_trading_mode() 之後執行，
    // 因為 set_trading_mode() 會調用 sync_direct_to_mode_state(PaperOnly) 覆蓋較早的更新。
    if let Some(paper_bal) = paper_initial_balance {
        if cfg_snapshot.trading_mode == crate::config::TradingMode::Live {
            if let Some(ms) = pipeline.get_mode_state_mut(crate::config::TradingMode::PaperOnly) {
                ms.paper_state = crate::paper_state::PaperState::new(paper_bal);
                info!(
                    balance = paper_bal,
                    "paper mode balance updated to demo account value (live mode) \
                     / paper 模式餘額已更新為 demo 帳號數值（live 模式）"
                );
            }
        }
    }

    // Exchange mode = any mode that routes real orders to an exchange (Demo or Live)
    // 交易所模式 = 向交易所發送真實訂單的任何模式（Demo 或 Live）
    let is_exchange_mode = matches!(
        cfg_snapshot.trading_mode,
        crate::config::TradingMode::Demo | crate::config::TradingMode::Live
    );
    if is_exchange_mode {
        info!(
            mode = %cfg_snapshot.trading_mode,
            "EXT-1: exchange mode active — orders sent to exchange, fills confirmed via WS / 交易所模式啟用"
        );
    }

    // Order dispatch: shadow orders (paper_only) or primary orders (exchange mode)
    // 訂單派發：影子訂單（紙盤模式）或主訂單（交易所模式）
    let pending_reg_rx_slot = dispatch::spawn_order_dispatch(
        &mut pipeline,
        shared_client.as_ref(),
        shared_instruments.as_ref(),
        cfg_snapshot.shadow_orders || is_exchange_mode,
    );

    // Register strategies via factory (3E-9: single registration point)
    // 通過工廠註冊策略（3E-9：唯一註冊點）
    for strategy in StrategyFactory::create_all() {
        pipeline.orchestrator.register(strategy);
    }

    // Grant paper authorization (redundant for Paper/Demo since with_kind() auto-grants,
    // but kept for backward compat until 3E-4 cleans up). Harmless double-grant.
    // 授予紙盤授權（Paper/Demo 用 with_kind() 已自動授權，保留向後兼容直到 3E-4 清理）
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

            // ── D3: Receive async kline bootstrap results and seed pipeline ──
            // ── D3：接收異步 K 線引導結果並植入管線 ──
            seed = kline_seed_rx.recv() => {
                if let Some((sym, bars)) = seed {
                    let count = pipeline.kline_manager.seed_bars(&sym, "1m", bars);
                    info!(symbol = %sym, bars = count,
                          "dynamic kline bootstrap complete / 動態 K 線引導完成");
                }
            },

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

                                let fully_filled = po.cum_filled_qty >= po.qty * 0.999;
                                // Emit order state change: Working → Filled / PartiallyFilled.
                                // 發出訂單狀態轉換：Working → Filled / PartiallyFilled。
                                if let Some(ref tx) = order_tx {
                                    let em = pipeline.trading_mode.db_mode().to_string();
                                    let to_status = if fully_filled { "Filled" } else { "PartiallyFilled" };
                                    let _ = tx.try_send(crate::database::TradingMsg::OrderStateChange {
                                        order_id: po.order_link_id.clone(),
                                        ts_ms: exec_ts,
                                        from_status: Some("Working".into()),
                                        to_status: to_status.into(),
                                        filled_qty: Some(po.cum_filled_qty),
                                        avg_price: Some(exec_price),
                                        reason: None,
                                        engine_mode: em,
                                    });
                                }

                                if fully_filled {
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
                                        // Emit order state change: Working → Cancelled/Rejected.
                                        // 發出訂單狀態轉換：Working → Cancelled/Rejected。
                                        if let Some(ref tx) = order_tx {
                                            let em = pipeline.trading_mode.db_mode().to_string();
                                            let _ = tx.try_send(crate::database::TradingMsg::OrderStateChange {
                                                order_id: po.order_link_id.clone(),
                                                ts_ms: std::time::SystemTime::now()
                                                    .duration_since(std::time::UNIX_EPOCH)
                                                    .map(|d| d.as_millis() as u64)
                                                    .unwrap_or(0),
                                                from_status: Some("Working".into()),
                                                to_status: status.to_string(),
                                                filled_qty: None,
                                                avg_price: None,
                                                reason: Some(format!("exchange_status:{}", status)),
                                                engine_mode: em,
                                            });
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
                    // Emit Order row when exchange confirms Working state.
                    // 訂單進入 Working 狀態時寫入 trading.orders。
                    if let Some(ref tx) = order_tx {
                        let em = pipeline.trading_mode.db_mode().to_string();
                        let _ = tx.try_send(crate::database::TradingMsg::Order {
                            order_id: po.order_link_id.clone(),
                            ts_ms: po.sent_ts_ms,
                            symbol: po.symbol.clone(),
                            side: if po.is_long { "Buy".into() } else { "Sell".into() },
                            order_type: "Market".into(),
                            qty: po.qty,
                            strategy_name: po.strategy.clone(),
                            is_close: po.is_close,
                            engine_mode: em.clone(),
                        });
                        let _ = tx.try_send(crate::database::TradingMsg::OrderStateChange {
                            order_id: po.order_link_id.clone(),
                            ts_ms: po.sent_ts_ms,
                            from_status: Some("Submitted".into()),
                            to_status: "Working".into(),
                            filled_qty: None,
                            avg_price: None,
                            reason: None,
                            engine_mode: em,
                        });
                    }
                    pending_orders.insert(po.order_link_id.clone(), po);
                }
            },

            // ── Paper session commands from IPC / 來自 IPC 的紙盤 session 命令 ──
            cmd = async {
                if let Some(ref mut rx) = pipeline_cmd_rx { rx.recv().await } else { std::future::pending().await }
            } => {
                if let Some(cmd) = cmd {
                    handlers::handle_paper_command(
                        cmd,
                        &mut pipeline,
                        &mut snapshot_writer,
                        &mut pending_orders,
                    );
                    // Phase 6: sync governor risk level to shared atomic for reconciler.
                    // Phase 6：同步 governor 風控級別到共享原子量供對帳器讀取。
                    if let Some(ref rl) = shared_risk_level {
                        rl.store(
                            pipeline.governance.risk.snapshot_level().value(),
                            std::sync::atomic::Ordering::Relaxed,
                        );
                    }
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
                                    // P0-5: Reconcile local balance from exchange only in the mode
                                    // that actually owns this WS connection (Demo or Live).
                                    // Use pipeline.trading_mode dynamically — the mode may have
                                    // been switched via IPC (SwitchMode) after startup, in which
                                    // case the static is_exchange_mode flag would be stale and
                                    // would incorrectly overwrite the paper simulation balance
                                    // with the live/demo exchange balance.
                                    // P0-5：僅在擁有此 WS 連接的模式（Demo 或 Live）下對賬本地餘額。
                                    // 使用 pipeline.trading_mode 動態計算 — 模式可能已通過 IPC
                                    // （SwitchMode）在啟動後切換。使用靜態 is_exchange_mode 標誌
                                    // 會導致紙盤模擬餘額被交易所餘額錯誤覆蓋。
                                    let current_is_exchange = matches!(
                                        pipeline.trading_mode,
                                        crate::config::TradingMode::Demo | crate::config::TradingMode::Live
                                    );
                                    if current_is_exchange {
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

                            // D2: Diff registry vs known_symbols → add/remove from pipeline.
                            // Runs every status interval (30s); scanner cycle is 30 min,
                            // so changes are reflected within one interval.
                            // D2：差分注冊表與 known_symbols → 從管線增減交易對。
                            // 每狀態報告間隔（30s）執行；掃描器週期 30 分鐘，
                            // 變更在一個間隔內反映。
                            if let Some(ref reg) = symbol_registry {
                                let current: std::collections::HashSet<String> =
                                    reg.snapshot().into_iter().collect();
                                let to_add: Vec<String> = current
                                    .difference(&known_symbols)
                                    .cloned()
                                    .collect();
                                let to_remove: Vec<String> = known_symbols
                                    .difference(&current)
                                    .cloned()
                                    .collect();

                                for sym in &to_remove {
                                    pipeline.remove_symbol(sym);
                                    known_symbols.remove(sym);
                                    info!(symbol = %sym,
                                          "D2: scanner removed symbol from pipeline \
                                           / 掃描器從管線移除交易對");
                                }

                                for sym in &to_add {
                                    pipeline.add_symbol(sym);
                                    known_symbols.insert(sym.clone());
                                    info!(symbol = %sym,
                                          "D2: scanner added symbol to pipeline \
                                           / 掃描器向管線添加交易對");

                                    // D3: Spawn async kline bootstrap for new symbol.
                                    // D3：為新交易對生成異步 K 線引導。
                                    if cfg_snapshot.kline_bootstrap {
                                        if let Some(ref client_arc) = bootstrap_client {
                                            let sym_owned = sym.clone();
                                            let client_clone =
                                                std::sync::Arc::clone(client_arc);
                                            let seed_tx = kline_seed_tx.clone();
                                            tokio::spawn(async move {
                                                let mdc = crate::market_data_client::MarketDataClient::new(client_clone);
                                                match mdc
                                                    .get_klines(
                                                        "linear",
                                                        &sym_owned,
                                                        "1",
                                                        None,
                                                        None,
                                                        Some(200),
                                                    )
                                                    .await
                                                {
                                                    Ok(bars) => {
                                                        let now_ms =
                                                            std::time::SystemTime::now()
                                                                .duration_since(
                                                                    std::time::UNIX_EPOCH,
                                                                )
                                                                .unwrap_or_default()
                                                                .as_millis()
                                                                as u64;
                                                        let mut core_bars: Vec<
                                                            openclaw_core::klines::KlineBar,
                                                        > = bars
                                                            .iter()
                                                            .filter(|b| {
                                                                b.start_time + 60_000
                                                                    <= now_ms
                                                            })
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
                                                        core_bars
                                                            .sort_by_key(|b| b.open_time_ms);
                                                        let _ = seed_tx
                                                            .send((sym_owned, core_bars))
                                                            .await;
                                                    }
                                                    Err(e) => {
                                                        warn!(
                                                            symbol = %sym_owned,
                                                            error = %e,
                                                            "D3: dynamic kline bootstrap failed \
                                                             / 動態 K 線引導失敗"
                                                        );
                                                    }
                                                }
                                            });
                                        }
                                    }
                                }
                            }

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

// ──────────────────────────────────────────────────────────────────────────────
// ARCH-RC1 1C-4 B1 — Governor de-escalation cooldown PG persistence helpers
// ARCH-RC1 1C-4 B1 — Governor 降級冷卻 PG 持久化輔助函數
// ──────────────────────────────────────────────────────────────────────────────

/// EN: Pure decision function — given a stored ts (from V014) and the current
///     wall clock, decide whether the cooldown is still active. Extracted as a
///     standalone fn so it is unit-testable without a PG fixture.
///     Returns Some(stored_ts) when the cooldown is still active; None when
///     the cooldown has expired or the stored ts is in the future
///     (clock-skew → ignore the row, treat as expired so we don't pin a
///     bogus future cooldown forever).
/// 中文: 純決策函數 — 給定 V014 存的 ts 與當前時間，判斷冷卻是否仍生效。
///       抽成獨立函數以便不依賴 PG fixture 做單測。冷卻仍活躍回 Some，
///       過期或時鐘倒退（stored_ts > now）回 None（避免錯誤地永久 pin 未來冷卻）。
fn cooldown_ts_if_active(stored_ts_ms: i64, now_ms: u64, cooldown_ms: u64) -> Option<u64> {
    if stored_ts_ms < 0 {
        return None;
    }
    let ts = stored_ts_ms as u64;
    if ts > now_ms {
        // Clock skew — V014 row claims a timestamp in the future. Refuse to
        // honour it; let cooldown start fresh and let the next legitimate
        // de-escalation overwrite the row.
        // 時鐘倒退 — V014 row 聲稱未來時間戳，拒絕沿用，讓下次合法降級覆蓋。
        return None;
    }
    let elapsed = now_ms.saturating_sub(ts);
    if elapsed < cooldown_ms {
        Some(ts)
    } else {
        None
    }
}

/// EN: Query V014 for the most recent successful operator de-escalation and
///     return its ts_ms iff the 24h cooldown is still active. Fail-soft: any
///     SQL error logs a warn and returns None — the engine still starts but
///     the cooldown begins from zero. Other guards (whitelist, step rule,
///     5-min hold, CB/MR lockout) remain active so this is defence-in-depth.
/// 中文: 查 V014 取最近一筆 operator 成功降級記錄，僅當 24h 冷卻仍活躍時返回
///       ts_ms。fail-soft：SQL 失敗記 warn 並回 None，引擎照常啟動但冷卻從零
///       開始；其他守衛（白名單/步進/5min hold/CB+MR 鎖死）持續生效，
///       這只是 defence-in-depth 層。
async fn load_governor_cooldown_from_audit(
    pool: &sqlx::PgPool,
    now_ms: u64,
) -> Option<u64> {
    let row: Result<Option<(i64,)>, sqlx::Error> = sqlx::query_as(
        "SELECT ts_ms FROM observability.engine_events \
         WHERE event_type = 'governor_de_escalate' \
           AND payload->>'result' = 'applied' \
         ORDER BY ts_ms DESC LIMIT 1",
    )
    .fetch_optional(pool)
    .await;
    match row {
        Ok(Some((ts,))) => cooldown_ts_if_active(
            ts,
            now_ms,
            TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS,
        ),
        Ok(None) => None,
        Err(e) => {
            warn!(error = %e, "ARCH-RC1 1C-4 B1: V014 governor cooldown query failed (fail-soft) / V014 governor 冷卻查詢失敗（fail-soft）");
            None
        }
    }
}

#[cfg(test)]
mod cooldown_tests {
    use super::cooldown_ts_if_active;

    const COOLDOWN_MS: u64 = 24 * 60 * 60 * 1000;

    #[test]
    fn fresh_cooldown_within_window_returns_some() {
        // 1h ago — well inside the 24h window.
        let now = 1_000_000_000_000u64;
        let stored = (now - 3_600_000) as i64;
        assert_eq!(cooldown_ts_if_active(stored, now, COOLDOWN_MS), Some(stored as u64));
    }

    #[test]
    fn expired_cooldown_returns_none() {
        // 25h ago — past the window.
        let now = 1_000_000_000_000u64;
        let stored = (now - 25 * 3_600_000) as i64;
        assert_eq!(cooldown_ts_if_active(stored, now, COOLDOWN_MS), None);
    }

    #[test]
    fn boundary_at_exactly_cooldown_treated_as_expired() {
        let now = 1_000_000_000_000u64;
        let stored = (now - COOLDOWN_MS) as i64;
        // elapsed == cooldown → not <, so None.
        assert_eq!(cooldown_ts_if_active(stored, now, COOLDOWN_MS), None);
    }

    #[test]
    fn future_timestamp_clock_skew_returns_none() {
        // V014 row claims a timestamp 1h in the future — refuse to honour.
        let now = 1_000_000_000_000u64;
        let stored = (now + 3_600_000) as i64;
        assert_eq!(cooldown_ts_if_active(stored, now, COOLDOWN_MS), None);
    }

    #[test]
    fn negative_stored_ts_returns_none() {
        // Defensive: V014 column is BIGINT so a corrupt row could be negative.
        let now = 1_000_000_000_000u64;
        assert_eq!(cooldown_ts_if_active(-1, now, COOLDOWN_MS), None);
    }
}
