//! Event consumer — feeds PriceEvents from WS into TickPipeline for paper trading.
//! 事件消費者 — 將 WS 的 PriceEvent 送入 TickPipeline 進行紙盤交易。
//!
//! MODULE_NOTE (EN): Extracted from main.rs (Phase 1 Day 0-A) to keep main.rs under
//!   800-line warning limit. Owns TickPipeline lifecycle: creates pipeline, registers
//!   strategies, runs kline bootstrap, then loops receiving PriceEvents.
//! MODULE_NOTE (中): 從 main.rs 提取（Phase 1 Day 0-A），保持 main.rs 在 800 行警告線下。
//!   擁有 TickPipeline 生命週期：創建管線、註冊策略、執行 K 線引導、然後循環接收 PriceEvent。

mod bootstrap;
mod dispatch;
mod execution_fill_helpers;
mod funding_settlement;
mod governor_cooldown;
pub mod handlers;
mod loop_exchange;
mod loop_handlers;
// MUST-FIX-2 Round 2 (2026-05-19/20)：halt-state restore helper 在 sibling
// crate test（tick_pipeline::tests::halt_ttl）內被呼叫 → pub(crate) 暴露足夠，
// 不需要 pub。
pub(crate) mod paper_state_restore;
mod pending_sweep;
mod setup;
mod status_report;
#[cfg(test)]
mod tests;
mod types;
// F4-RETURN Issue 1 (2026-04-26): split out of loop_handlers.rs to keep that
// file under §九 1200-line hard ceiling.
// F4-RETURN Issue 1（2026-04-26）：從 loop_handlers.rs 抽出，使其維持在
// §九 1200 行硬上限以下。
mod unattributed_emit;

use types::STATUS_INTERVAL_SECS;
pub use types::{EventConsumerDeps, ExchangeEvent, PendingOrder, PendingOrderEvent, SYMBOLS};

use std::time::Instant;
use tracing::info;

/// Run the event consumer loop: build pipeline, register strategies, process ticks.
/// 運行事件消費者循環：構建管線、註冊策略、處理 tick。
pub async fn run_event_consumer(deps: EventConsumerDeps) {
    // G1-02 Step 3 (2026-04-24): all pre-loop setup extracted to `bootstrap::bootstrap_runtime`.
    // G1-02 Step 3（2026-04-24）：所有 pre-loop 設置抽入 `bootstrap::bootstrap_runtime`。
    let bootstrap::BootstrappedRuntime {
        mut pipeline,
        mut state_writer,
        mut snapshot_writer,
        audit_writer,
        mut kline_seed_rx,
        kline_seed_tx,
        pending_reg_rx_slot,
        data_path: _data_path,
        kind_tag: _kind_tag,
        order_tx,
        known_symbols,
        cfg_snapshot,
        bootstrap_client,
        symbol_registry,
        pipeline_kind,
        mut event_rx,
        cancel,
        shared_client,
        shared_bybit_balance,
        shared_api_pnl,
        shared_last_tick_ms,
        exchange_event_rx,
        mut pipeline_cmd_rx,
        audit_pool,
        shared_risk_level,
        cross_engine_tx,
        cross_engine_rx,
        pipeline_health,
        canary_handle,
    } = bootstrap::bootstrap_runtime(deps).await;

    // G1-02 Step 2a (2026-04-24): 7 loop-internal mut fields bundled into
    // `LoopState` so the select! arms can pass a single `&mut state` borrow
    // instead of juggling 7 individual bindings. `MAX_SEEN_EXEC_IDS` is
    // now `LoopState::MAX_SEEN_EXEC_IDS`.
    // G1-02 Step 2a（2026-04-24）：7 個 loop-internal mut 欄位合併進
    // `LoopState`，select! arm 可傳單一 `&mut state` 借用。
    let mut state = loop_handlers::LoopState::new(known_symbols);
    let status_interval = std::time::Duration::from_secs(STATUS_INTERVAL_SECS);
    let start_time = Instant::now();

    let mut exchange_event_rx = exchange_event_rx;
    let mut pending_reg_rx = pending_reg_rx_slot;
    let pending_timeout = std::time::Duration::from_secs(5);

    // AMD-2026-05-02-01 Track H E-1 retrofit (HIGH-2 ExpiryGuardian sweep):
    // Periodic Decision Lease & Authorization expiry sweeper — invokes the
    // existing `GovernanceCore::check_expiry()` SM transition path every 60s
    // so RouterLeaseGuard Drop release-failures and orphan TTL'd leases do
    // not accumulate (otherwise lease objects leak in SM-02 Active forever
    // until engine restart). Per-pipeline scope: each ModeState (paper/demo/
    // live) sweeps its own GovernanceCore — preserving multi-mode isolation.
    // AMD-2026-05-02-01 Track H E-1 retrofit（HIGH-2 ExpiryGuardian sweep）：
    // 每 60s 觸發 `GovernanceCore::check_expiry()` 對 lease + auth 過期掃描。
    // RouterLeaseGuard Drop release 失敗的 lease + 過期 TTL lease 不會永久卡在
    // SM-02 Active；per-pipeline 範圍尊重 paper/demo/live 多模式隔離。
    let mut lease_sweep_interval = tokio::time::interval(std::time::Duration::from_secs(60));
    lease_sweep_interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    // Consume the immediate-fire first tick so the sweeper does not run during
    // bootstrap before the SM has any leases.
    // 消耗 interval 立即觸發的第一次 tick；避免 bootstrap 前 SM 0 lease 時誤掃。
    lease_sweep_interval.tick().await;

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

            // ── BLOCKER-2 D6: Cross-engine crash/CB event handler (Arm A) ──
            // ── BLOCKER-2 D6：跨引擎崩潰/熔斷事件處理（Arm A）──
            engine_evt = async {
                if let Some(ref mut rx) = cross_engine_rx { rx.recv().await } else { std::future::pending().await }
            } => {
                loop_handlers::handle_cross_engine_event(engine_evt, &mut pipeline, pipeline_kind);
            },

            // ── D3: Receive async kline bootstrap results and seed pipeline (Arm B) ──
            // ── D3：接收異步 K 線引導結果並植入管線（Arm B）──
            seed = kline_seed_rx.recv() => {
                loop_handlers::handle_kline_seed(seed, &mut pipeline);
            },

            // ── EXT-1: Exchange events (fills/order updates) from ExecutionListener (Arm C) ──
            // ── EXT-1：來自執行監聽器的交易所事件（成交/訂單更新）（Arm C）──
            // F4-RETURN Issue 2 (2026-04-26): handle_exchange_event is async —
            // back-pressure for F4-1 audit emit. arm body is async context.
            // F4-RETURN Issue 2（2026-04-26）：handle_exchange_event 改 async（背壓）。
            exchange_evt = async {
                if let Some(ref mut rx) = exchange_event_rx { rx.recv().await } else { std::future::pending().await }
            } => {
                loop_handlers::handle_exchange_event(
                    exchange_evt,
                    &mut pipeline,
                    &mut snapshot_writer,
                    &mut state,
                    order_tx.as_ref(),
                ).await;
            },

            // ── EXT-1: Pending order registration from dispatch task (Arm D) ──
            // ── EXT-1：dispatch task 推送的 pending order 註冊（Arm D）──
            pending_reg = async {
                if let Some(ref mut rx) = pending_reg_rx { rx.recv().await } else { std::future::pending().await }
            } => {
                loop_handlers::handle_pending_registration(
                    pending_reg,
                    &mut pipeline,
                    &mut state,
                    order_tx.as_ref(),
                );
            },

            // ── Paper session commands from IPC (Arm E) ──
            // ── 來自 IPC 的紙盤 session 命令（Arm E）──
            cmd = async {
                if let Some(ref mut rx) = pipeline_cmd_rx { rx.recv().await } else { std::future::pending().await }
            } => {
                loop_handlers::handle_pipeline_command(
                    cmd,
                    &mut pipeline,
                    &mut snapshot_writer,
                    &mut state,
                    audit_pool.as_ref(),
                    shared_risk_level.as_ref(),
                    _cross_engine_tx.as_ref(),
                    pipeline_kind,
                ).await;
            },

            event = event_rx.recv() => {
                let flow = loop_handlers::handle_tick_event(
                    event,
                    &mut pipeline,
                    &mut state_writer,
                    &mut snapshot_writer,
                    &audit_writer,
                    &mut state,
                    start_time,
                    status_interval,
                    pending_timeout,
                    shared_last_tick_ms.as_ref(),
                    shared_bybit_balance.as_ref(),
                    shared_api_pnl.as_ref(),
                    &canary_handle,
                    shared_client.as_ref(),
                    audit_pool.as_ref(),
                    symbol_registry.as_ref(),
                    &cfg_snapshot,
                    bootstrap_client.as_ref(),
                    &kline_seed_tx,
                );
                if flow.is_break() {
                    break;
                }
            }

            // ── AMD-2026-05-02-01 Track H E-1 retrofit Arm: lease & auth sweep ──
            // ── AMD-2026-05-02-01 Track H E-1 retrofit Arm：lease + auth 掃描 ──
            // HIGH-2 ExpiryGuardian sweep — every 60s invoke check_expiry() on
            // this pipeline's GovernanceCore. Logs at INFO when any expiry
            // transitions actually fire so operator/healthcheck can audit
            // sweep effectiveness; otherwise silent. fail-soft: never breaks
            // the loop or affects tick path.
            // HIGH-2 ExpiryGuardian sweep — 每 60s 對本 pipeline 的 GovernanceCore
            // 執行 check_expiry()。有 expiry 觸發時 INFO log 供 operator / healthcheck
            // 審計掃描有效性；無觸發時靜默。fail-soft：不影響 tick path。
            _ = lease_sweep_interval.tick() => {
                let (auth_expired, lease_expired) = pipeline.governance.check_expiry();
                if !auth_expired.is_empty() || !lease_expired.is_empty() {
                    tracing::info!(
                        target: "openclaw_engine::governance::expiry_sweep",
                        pipeline_kind = ?pipeline_kind,
                        auth_expired = auth_expired.len(),
                        lease_expired = lease_expired.len(),
                        "Decision Lease / Auth expiry sweep transitioned objects \
                         / 租約 / 授權過期掃描已轉換物件"
                    );
                }
            }
        }
    }

    // Shutdown: close all open positions before final state write.
    // Feed realized PnL into the sizer so the window captures end-of-session
    // outcomes (DYNAMIC-RISK-1 BUG-1 fix). The sizer persists only in-memory,
    // but recording keeps semantics consistent with the paper close-all path.
    // 關閉：先平掉所有持倉；把實現 PnL 餵入 sizer，語義對齊 paper close-all。
    let results = pipeline.paper_state.close_all_positions();
    for (_, pnl) in &results {
        if *pnl != 0.0 {
            pipeline.dynamic_risk_sizer.record_closed_trade(*pnl);
        }
    }
    let closed = results.len();
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
