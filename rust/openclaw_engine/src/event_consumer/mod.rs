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
mod governor_cooldown;
pub mod handlers;
mod paper_state_restore;
mod setup;
mod types;

use types::STATUS_INTERVAL_SECS;
pub use types::{EventConsumerDeps, ExchangeEvent, PendingOrder, SYMBOLS};

use crate::persistence::{AuditWriter, DualStateWriter, StateWriter};
use crate::strategies::StrategyFactory;
use crate::tick_pipeline::{PipelineKind, TickPipeline};
use governor_cooldown::load_governor_cooldown_from_audit;
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
        paper_initial_balance: _paper_initial_balance,
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
        exchange_event_rx,
        seed_positions,
        account_manager,
        linucb_runtime,
        news_snapshot,
        risk_store,
        budget_store,
        audit_pool,
        symbol_registry,
        scanner_store: _, // D-03: unused — ScannerConfig read via scanner_runner, not event_consumer
        shared_risk_level,
        is_primary,
        ready_tx,
        global_exposure_usdt,
        cross_engine_tx,
        cross_engine_rx,
        pipeline_health,
        canary_handle,
    } = deps;
    let mut pipeline_cmd_rx = pipeline_cmd_rx;

    // D19 safety assertion: only Paper pipeline writes market/feature DB.
    // Exchange pipelines (Demo/Live) must receive None to prevent duplicate writes.
    // D19 安全斷言：僅 Paper 管線寫入市場/特徵 DB。
    // 交易所管線（Demo/Live）必須收到 None 以防止重複寫入。
    if pipeline_kind.is_exchange() {
        assert!(
            market_data_tx.is_none() && feature_tx.is_none(),
            "D19 violation: exchange pipeline ({:?}) must not write market/feature DB",
            pipeline_kind,
        );
    }

    let cfg_snapshot = config.get();

    // Build pipeline with kind-appropriate governance + balance (3E-2a)
    // 以 kind 對應的治理 + 餘額構建管線（3E-2a）
    let mut pipeline = TickPipeline::with_kind(SYMBOLS, initial_balance, pipeline_kind);

    // QoL-1: Restore cumulative paper_state counters from trading.fills before
    // the first tick; details + fail-soft log are in paper_state_restore.
    // QoL-1：首個 tick 前從 trading.fills 還原累計指標；細節見 helper。
    paper_state_restore::restore_paper_counters(&mut pipeline, pipeline_kind, audit_pool.as_ref()).await;

    // B-1 Phase 2: Seed paper_state with exchange positions captured at startup.
    // Without this, inactive symbols never get WS PositionUpdate → snapshot=0.
    // B-1 Phase 2：以啟動時抓到的交易所持倉 seed paper_state（Paper 管線 no-op）。
    if !seed_positions.is_empty() {
        let count = pipeline.paper_state.import_positions(seed_positions);
        info!(
            kind = %pipeline_kind,
            seeded = count,
            "B-1 Phase 2: paper_state seeded from exchange snapshot \
             / 已用交易所快照種入 paper_state"
        );
    }

    // D2/D3: Track known symbols for scanner universe diff.
    // D2/D3：追蹤已知交易對，用於掃描器品類差分。
    let mut known_symbols: std::collections::HashSet<String> =
        SYMBOLS.iter().map(|s| s.to_string()).collect();

    // D3: Channel for async kline bootstrap results (spawned task → main loop).
    // D3：異步 K 線引導結果通道（生成任務 → 主循環）。
    let (kline_seed_tx, mut kline_seed_rx) =
        tokio::sync::mpsc::channel::<(String, Vec<openclaw_core::klines::KlineBar>)>(8);

    // ARCH-RC1 1C-4 B1: restore governor de-escalation cooldown from V014.
    // See governor_cooldown.rs for logic details.
    // ARCH-RC1 1C-4 B1：從 V014 還原 governor 降級冷卻。邏輯詳見 governor_cooldown.rs。
    if let Some(pool) = audit_pool.as_ref() {
        let now_ms = openclaw_core::now_ms();
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
        // Load mode-specific edge estimates: paper → edge_estimates_paper.json (isolated),
        // demo/live → edge_estimates.json (production). Paper exploration data must not
        // pollute demo/live cost_gate decisions — this breaks the degenerative feedback loop
        // where paper's noisy negative-edge fills drag down shrunk_bps for all modes.
        // 加載模式特定邊際估計：paper 隔離，demo/live 用生產數據。
        // Paper 探索數據不得污染 demo/live cost_gate 決策。
        let base = std::env::var("OPENCLAW_BASE_DIR")
            .map(std::path::PathBuf::from)
            .unwrap_or_else(|_| {
                std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."))
            });
        let mode = pipeline_kind.db_mode();
        let estimates = crate::edge_estimates::EdgeEstimates::load_for_mode(&base, mode);
        if estimates.is_populated() {
            info!(
                mode,
                n_cells = estimates.n_cells(),
                grand_mean_bps = estimates.grand_mean_bps(),
                "PH5-WIRE-1: JS edge estimates loaded / JS 邊際估計已加載"
            );
        } else {
            info!(mode, "PH5-WIRE-1: no edge snapshot — cold-start ATR×0.2 fallback / 無快照，ATR 回退");
        }
        pipeline.set_edge_estimates(estimates);
    }

    // BLOCKER-3 D15: Wire global exposure atomic (exchange pipelines only).
    // BLOCKER-3 D15：接入全局曝險原子量（僅交易所管線）。
    if let Some(ge) = global_exposure_usdt {
        pipeline.set_global_exposure(ge);
        info!("pipeline wired to global notional cap / 接入全局名目上限");
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

    // 3E-4: pipeline_kind is set at construction via with_kind() — no runtime set_trading_mode.
    // 3E-4：pipeline_kind 在構造時通過 with_kind() 設定 — 無運行時 set_trading_mode。

    // Exchange mode = pipeline connects to real exchange (Demo or Live).
    // 交易所模式 = 管線連接真實交易所（Demo 或 Live）。
    let is_exchange_mode = pipeline.pipeline_kind.is_exchange();
    if is_exchange_mode {
        info!(
            kind = %pipeline.pipeline_kind,
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

    // Register strategies via factory (3E-9 + BLOCKER-8: per-engine TOML params)
    // 通過工廠註冊策略（3E-9 + BLOCKER-8：每引擎 TOML 參數）
    for strategy in StrategyFactory::create_for_engine(deps.pipeline_kind) {
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

    // MAJOR-2: Signal that this pipeline has completed initialization.
    // Fan-out task waits for all pipelines before distributing ticks.
    // MAJOR-2：通知此管線已完成初始化。扇出任務等所有管線就緒後才分發 tick。
    if let Some(tx) = ready_tx {
        let _ = tx.send(());
    }

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
                        let now_ms = openclaw_core::now_ms();
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
    // 3E-5: per-engine snapshot filenames derived from pipeline_kind.
    // Primary pipeline also writes pipeline_snapshot.json for backward compat (IPC server, watchdog).
    // 3E-5：每個引擎的快照文件名由 pipeline_kind 決定。
    // 主管線同時寫入 pipeline_snapshot.json 保持向後兼容（IPC 伺服器、看門狗）。
    let kind_tag = pipeline.pipeline_kind.db_mode(); // "paper" | "demo" | "live"
    let per_engine_snapshot = format!("pipeline_snapshot_{kind_tag}.json");
    // Stagger snapshot debounce intervals per-engine to avoid I/O contention
    // when all three pipelines flush in the same window.
    // 每引擎錯開快照去抖間隔，避免三管線同時刷新時的 I/O 爭用。
    let (state_interval_ms, snapshot_interval_ms) = match pipeline.pipeline_kind {
        PipelineKind::Paper => (30_000, 5_000),
        PipelineKind::Demo  => (31_000, 5_500),
        PipelineKind::Live  => (29_000, 4_500),
    };
    let mut state_writer = StateWriter::new(&data_path.join(format!("{kind_tag}_state.json")), state_interval_ms);
    let primary_writer = StateWriter::new(&data_path.join(&per_engine_snapshot), snapshot_interval_ms);
    // Backward compat: primary pipeline also writes pipeline_snapshot.json
    // 向後兼容：主管線同時寫入 pipeline_snapshot.json
    let compat_writer = if is_primary {
        Some(StateWriter::new(&data_path.join("pipeline_snapshot.json"), 5_000))
    } else {
        None
    };
    let mut snapshot_writer = DualStateWriter::new(primary_writer, compat_writer);
    let audit_writer = AuditWriter::new(&data_path.join(format!("{kind_tag}_audit.jsonl")));

    // ENGINE-HEAL-FIX-PHASE1 R1: Canary write moved off this hot path. The shared
    // CanaryWriterHandle (spawned once in main.rs) owns the BufWriter + flush timer
    // + size rotation; we just `try_send(record)` here. `is_enabled()` reflects the
    // env-flag decision made at spawn time — kept identical to the previous
    // local env check so `pipeline.canary_mode` semantics are unchanged.
    // ENGINE-HEAL-FIX-PHASE1 R1：灰度寫盤已移出本熱路徑。共享 CanaryWriterHandle
    // （main.rs 啟動時 spawn 一次）擁有 BufWriter + flush 定時器 + 大小輪轉；
    // 此處僅 `try_send(record)`。`is_enabled()` 反映 spawn 時決定的旗標狀態。
    pipeline.canary_mode = canary_handle.is_enabled();

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
    // P0-2 fix: exec_id dedup (prevent duplicate fill application on WS reconnect)
    // FIX-33: HashSet for O(1) lookup + VecDeque for eviction ordering (was O(n) scan).
    // P0-2 修復：exec_id 去重（防止 WS 重連時重複應用成交）
    // FIX-33：HashSet O(1) 查找 + VecDeque 淘汰順序（原為 O(n) 線性掃描）。
    let mut seen_exec_set: std::collections::HashSet<String> = std::collections::HashSet::new();
    let mut seen_exec_order: std::collections::VecDeque<String> = std::collections::VecDeque::new();
    const MAX_SEEN_EXEC_IDS: usize = 500;
    let mut exchange_event_rx = exchange_event_rx;
    let mut pending_reg_rx = pending_reg_rx_slot;
    let mut last_pending_check = Instant::now();
    let pending_timeout = std::time::Duration::from_secs(5);

    // ── Main event loop / 主事件循環 ──
    // BLOCKER-2 D6: Shadow local copies for the select! loop.
    let mut cross_engine_rx = cross_engine_rx;
    let _cross_engine_tx = cross_engine_tx;
    let _pipeline_health = pipeline_health;

    // BLOCKER-2 D6: Set health to Running at loop start.
    if let Some(ref h) = _pipeline_health {
        h.store(
            crate::tick_pipeline::PipelineHealth::Running as u8,
            std::sync::atomic::Ordering::Relaxed,
        );
    }

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,

            // ── BLOCKER-2 D6: Cross-engine crash/CB event handler ──
            // ── BLOCKER-2 D6：跨引擎崩潰/熔斷事件處理 ──
            engine_evt = async {
                if let Some(ref mut rx) = cross_engine_rx { rx.recv().await } else { std::future::pending().await }
            } => {
                match engine_evt {
                    Ok(crate::tick_pipeline::EngineEvent::Crashed(crashed_kind)) => {
                        warn!(
                            this = %pipeline_kind, crashed = %crashed_kind,
                            "BLOCKER-2: peer pipeline crashed — escalating to Cautious (60s) \
                             / 對等管線崩潰 — 升級至 Cautious（60s）"
                        );
                        // Cascade: escalate this pipeline's risk to Cautious.
                        // 級聯：將本管線風控升級至 Cautious。
                        let duration_s = if crashed_kind == crate::tick_pipeline::PipelineKind::Paper { 60 } else { 120 };
                        let _ = pipeline.governance.risk.reconciler_escalate_to(
                            openclaw_core::sm::risk_gov::RiskLevel::Cautious,
                            &format!("cross_engine_cascade: {} crashed, hold {}s", crashed_kind, duration_s),
                        );
                    }
                    Ok(crate::tick_pipeline::EngineEvent::CircuitBreakerTripped(cb_kind)) => {
                        warn!(
                            this = %pipeline_kind, cb = %cb_kind,
                            "BLOCKER-2: peer pipeline hit circuit breaker — escalating to Cautious \
                             / 對等管線觸發熔斷 — 升級至 Cautious"
                        );
                        let _ = pipeline.governance.risk.reconciler_escalate_to(
                            openclaw_core::sm::risk_gov::RiskLevel::Cautious,
                            &format!("cross_engine_cascade: {} circuit_breaker", cb_kind),
                        );
                    }
                    Err(_) => {
                        // Sender dropped — all peers gone, no more events.
                    }
                }
            },

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
                        // FIX-33: O(1) HashSet lookup instead of O(n) VecDeque scan.
                        if seen_exec_set.contains(&exec.exec_id) {
                            warn!(exec_id = %exec.exec_id, "duplicate fill skipped / 重複成交已跳過");
                            continue;
                        }
                        seen_exec_set.insert(exec.exec_id.clone());
                        seen_exec_order.push_back(exec.exec_id.clone());
                        if seen_exec_order.len() > MAX_SEEN_EXEC_IDS {
                            if let Some(old) = seen_exec_order.pop_front() {
                                seen_exec_set.remove(&old);
                            }
                        }

                        let exec_qty: f64 = exec.exec_qty.parse().unwrap_or(0.0);
                        let exec_price: f64 = exec.exec_price.parse().unwrap_or(0.0);
                        let exec_ts: u64 = exec.exec_time.parse().unwrap_or(0);

                        // FIX-19: execution.fast topic omits execFee/feeRate fields.
                        // When the field is empty or unparseable, estimate fee from
                        // notional × per-symbol fee rate so PnL accounting stays correct.
                        // FIX-19b: Use pipeline.intent_processor.fee_rate(symbol) for
                        // per-symbol resolution (AccountManager → legacy → constant).
                        // FIX-19：execution.fast 不帶 execFee，空值時用名義值×手續費率估算。
                        // FIX-19b：改用 per-symbol 費率（AccountManager → 單一費率 → 常量）。
                        let exec_fee: f64 = {
                            let parsed = exec.exec_fee.parse::<f64>().unwrap_or(0.0);
                            if parsed == 0.0 && exec_qty > 0.0 && exec_price > 0.0 {
                                let fee_rate = pipeline.intent_processor.fee_rate(&exec.symbol);
                                let estimated = exec_qty * exec_price * fee_rate;
                                if estimated > 0.0 {
                                    tracing::debug!(
                                        exec_id = %exec.exec_id,
                                        symbol = %exec.symbol,
                                        notional = exec_qty * exec_price,
                                        fee_rate,
                                        estimated_fee = estimated,
                                        "FIX-19b: execFee missing, estimated from per-symbol rate \
                                         / execFee 缺失，使用 per-symbol 費率估算"
                                    );
                                }
                                estimated
                            } else {
                                parsed
                            }
                        };

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
                                    let em = pipeline.pipeline_kind.db_mode().to_string();
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
                            if let Some(_po) = pending_orders.get_mut(&order.order_link_id) {
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
                                            let em = pipeline.pipeline_kind.db_mode().to_string();
                                            let _ = tx.try_send(crate::database::TradingMsg::OrderStateChange {
                                                order_id: po.order_link_id.clone(),
                                                ts_ms: openclaw_core::now_ms(),
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
                    Some(ExchangeEvent::PositionUpdate(pos)) => {
                        // B-1 Phase 2: Mirror exchange position state into paper_state.
                        // size==0 → remove; size>0 → upsert with avg_price as entry.
                        // We treat side=="None" / empty side as "flat" (size==0 path).
                        // B-1 Phase 2：將交易所持倉狀態映射回 paper_state。
                        // size==0 視為平倉並移除；size>0 則 upsert（avg_price 作為入場價）。
                        // side=="None" 或空字串視為 flat（走 size==0 邏輯）。
                        let size: f64 = pos.size.parse().unwrap_or(0.0);
                        let avg_price: f64 = pos.avg_price.parse().unwrap_or(0.0);
                        let is_long = pos.side.eq_ignore_ascii_case("Buy");
                        let now_ms = openclaw_core::now_ms();
                        // Bybit returns side=="None" when the position is flat — coerce
                        // size to 0 so upsert removes any stale local entry.
                        // Bybit 在持倉為空時回傳 side=="None"，強制 size 為 0 以移除舊條目。
                        let effective_size = if pos.side.eq_ignore_ascii_case("None") || pos.side.is_empty() {
                            0.0
                        } else {
                            size
                        };
                        let changed = pipeline.paper_state.upsert_position_from_exchange(
                            &pos.symbol,
                            is_long,
                            effective_size,
                            avg_price,
                            now_ms,
                        );
                        if changed {
                            info!(
                                symbol = %pos.symbol,
                                side = %pos.side,
                                size = effective_size,
                                avg_price = avg_price,
                                kind = %pipeline.pipeline_kind,
                                "B-1 Phase 2: paper_state synced from WS position update \
                                 / paper_state 已根據 WS 持倉更新同步"
                            );
                            snapshot_writer.force_write(&pipeline.snapshot());
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
                        let em = pipeline.pipeline_kind.db_mode().to_string();
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
                    let current_level = pipeline.governance.risk.snapshot_level();
                    if let Some(ref rl) = shared_risk_level {
                        rl.store(
                            current_level.value(),
                            std::sync::atomic::Ordering::Relaxed,
                        );
                    }

                    // BLOCKER-2 D6: Broadcast CircuitBreaker event to peer pipelines.
                    // BLOCKER-2 D6：向對等管線廣播熔斷事件。
                    if current_level == openclaw_core::sm::risk_gov::RiskLevel::CircuitBreaker {
                        if let Some(ref tx) = _cross_engine_tx {
                            let _ = tx.send(crate::tick_pipeline::EngineEvent::CircuitBreakerTripped(pipeline_kind));
                        }
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

                        // ENGINE-HEAL-FIX-PHASE1 R1: Hand the record to the dedicated
                        // canary writer task — non-blocking. On channel-full the record
                        // is dropped with a warn (handled inside try_send); the event
                        // loop never blocks on file I/O.
                        // ENGINE-HEAL-FIX-PHASE1 R1：交給專用灰度寫入任務（非阻塞）；
                        // 通道滿則 warn 丟棄，事件循環絕不阻塞於檔案 I/O。
                        if let Some(record) = canary_record {
                            canary_handle.try_send(record);
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
                        // BLOCKER-6: parking_lot RwLock — read()/write() return guards directly.
                        // BLOCKER-6：parking_lot RwLock — read()/write() 直接回傳 guard。
                        if let Some(ref bal_arc) = shared_bybit_balance {
                            let maybe_bal = *bal_arc.read();
                            if let Some(bal) = maybe_bal {
                                pipeline.paper_state.set_bybit_sync_balance(Some(bal));
                                // P0-5: Reconcile local balance from exchange only in exchange pipelines.
                                // 3E-4: pipeline_kind is immutable — no dynamic mode check needed.
                                // P0-5：僅在交易所管線中對賬本地餘額。3E-4：pipeline_kind 不可變。
                                let current_is_exchange = pipeline.pipeline_kind.is_exchange();
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
                        if let Some(ref pnl_arc) = shared_api_pnl {
                            let guard = pnl_arc.read();
                            for (symbol, &pnl) in guard.iter() {
                                pipeline.paper_state.set_api_unrealized_pnl(symbol, pnl);
                            }
                        }

                        // EXT-1: Check for timed-out pending orders (every 5s)
                        if !pending_orders.is_empty() && last_pending_check.elapsed() >= pending_timeout {
                            let now_ms = openclaw_core::now_ms();
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
                            // R-02: Cross-check pipeline pending_close_symbols against open positions.
                            // Clears stale flags for symbols whose close fill was already processed.
                            // R-02：與實際持倉交叉驗證，清理已成交但標記未清除的 pending-close 殘留。
                            pipeline.reconcile_pending_exchange_orders();
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
                                snapshot_ts_ms: openclaw_core::now_ms(),
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
                                                            openclaw_core::now_ms();
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
    // BLOCKER-2 D6: Mark pipeline as Down on exit.
    // BLOCKER-2 D6：退出時標記管線為 Down。
    if let Some(ref h) = _pipeline_health {
        h.store(
            crate::tick_pipeline::PipelineHealth::Down as u8,
            std::sync::atomic::Ordering::Relaxed,
        );
    }

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
