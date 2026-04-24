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
mod governor_cooldown;
pub mod handlers;
mod paper_state_restore;
mod pending_sweep;
mod setup;
#[cfg(test)]
mod tests;
mod types;

use pending_sweep::{classify_pending_sweep, PendingSweepAction};
use types::STATUS_INTERVAL_SECS;
pub use types::{EventConsumerDeps, ExchangeEvent, PendingOrder, SYMBOLS};

use crate::tick_pipeline::PipelineCommand;
use std::collections::HashMap;
use std::time::Instant;
use tracing::{error, info, warn};

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
        mut known_symbols,
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
                                // FILL-CONTEXT-LINKAGE-1: thread signal-time context_id
                                // from PendingOrder into apply_confirmed_fill so
                                // trading.fills.entry_context_id matches
                                // learning.decision_features.context_id.
                                // FILL-CONTEXT-LINKAGE-1：將 PendingOrder 帶的
                                // 訊號時刻 context_id 傳入 apply_confirmed_fill，
                                // 使 trading.fills.entry_context_id 與
                                // learning.decision_features.context_id 對齊。
                                pipeline.apply_confirmed_fill(
                                    &exec.symbol,
                                    po.is_long,
                                    exec_qty,
                                    exec_price,
                                    exec_fee,
                                    exec_ts,
                                    &po.strategy,
                                    &po.context_id,
                                    &po.order_link_id,
                                );
                                snapshot_writer.force_write(&pipeline.snapshot());

                                let fully_filled = po.cum_filled_qty >= po.qty * 0.999;
                                // Emit order state change: Working → Filled / PartiallyFilled.
                                // 發出訂單狀態轉換：Working → Filled / PartiallyFilled。
                                if let Some(ref tx) = order_tx {
                                    let em = pipeline.effective_engine_mode().to_string();
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
                                    // EDGE-P2-3 Phase 1B-2: classify Bybit's rejectReason
                                    // string (non-empty only on terminal status). Surface
                                    // PostOnly-cross at warn! so it's grep-able; route
                                    // the short category label into DB `reason` so the
                                    // audit log is queryable without parsing free-form
                                    // strings. Strategy callback wiring lands in 1B-3.
                                    // EDGE-P2-3 Phase 1B-2：分類 Bybit rejectReason 字串。
                                    // PostOnly-cross 以 warn! 顯性記錄；短標籤進 DB reason。
                                    let reject_category = crate::strategies::maker_rejection::classify(
                                        &order.reject_reason,
                                    );
                                    let reject_label = reject_category.label();
                                    if reject_category.is_post_only_cross() {
                                        warn!(
                                            order_link_id = %order.order_link_id,
                                            symbol = %order.symbol,
                                            status = %status,
                                            reject_reason = %order.reject_reason,
                                            "maker order rejected: PostOnly would have crossed \
                                             / maker 掛單遭拒：PostOnly 會越過 book"
                                        );
                                    } else if reject_category.is_backpressure() {
                                        warn!(
                                            order_link_id = %order.order_link_id,
                                            symbol = %order.symbol,
                                            status = %status,
                                            reject_reason = %order.reject_reason,
                                            "maker order rejected: account-level backpressure \
                                             / maker 掛單遭拒：帳戶級背壓"
                                        );
                                    }
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
                                        // EDGE-P2-3 Phase 1B-2: append classified reject label
                                        // when Bybit provided a rejectReason; keeps legacy
                                        // `exchange_status:{status}` prefix stable for any
                                        // consumer grepping the reason column.
                                        // 發出訂單狀態轉換：Working → Cancelled/Rejected。
                                        // 1B-2：若 Bybit 附 rejectReason，追加分類短標；保留
                                        // legacy `exchange_status:{status}` 前綴以維持下游相容。
                                        let reason_str = if order.reject_reason.is_empty() {
                                            format!("exchange_status:{}", status)
                                        } else {
                                            format!(
                                                "exchange_status:{}|reject={}|category={}",
                                                status, order.reject_reason, reject_label,
                                            )
                                        };
                                        if let Some(ref tx) = order_tx {
                                            let em = pipeline.effective_engine_mode().to_string();
                                            let _ = tx.try_send(crate::database::TradingMsg::OrderStateChange {
                                                order_id: po.order_link_id.clone(),
                                                ts_ms: openclaw_core::now_ms(),
                                                from_status: Some("Working".into()),
                                                to_status: status.to_string(),
                                                filled_qty: None,
                                                avg_price: None,
                                                reason: Some(reason_str),
                                                engine_mode: em,
                                            });
                                        }
                                    }
                                    warn!(
                                        order_link_id = %order.order_link_id,
                                        status = %status,
                                        reject_category = %reject_label,
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
                        let em = pipeline.effective_engine_mode().to_string();
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
                    // EDGE-P3-1 Step 7e: intercept the kill-switch variant so the
                    // production path runs the full two-phase commit + V014 audit.
                    // All other variants still flow through handle_paper_command.
                    // EDGE-P3-1 Step 7e：截獲 kill-switch 變體，跑完整兩階段 + V014 審計；
                    // 其餘變體仍走 handle_paper_command。
                    match cmd {
                        PipelineCommand::DisableEdgePredictorAll {
                            operator_token,
                            reason,
                            response_tx,
                        } => {
                            let em_for_audit = pipeline.effective_engine_mode();
                            handlers::handle_disable_edge_predictor_all(
                                operator_token,
                                reason,
                                response_tx,
                                &mut pipeline,
                                em_for_audit,
                                audit_pool.as_ref(),
                            );
                        }
                        // P1-5 A2: operator-driven drawdown baseline reset.
                        // In-memory reset is synchronous; DB row DELETE is awaited
                        // inline so Python receives confirmation only AFTER the
                        // persisted checkpoint is gone (avoids "looks reset but
                        // next restart resurrects old peak" race). If DB write
                        // fails, respond Err but keep the in-memory reset — the
                        // next writer cycle will try to UPSERT the NEW (= current
                        // balance) peak, effectively re-pinning the baseline
                        // somewhere safe.
                        // P1-5 A2：operator 重置 drawdown 基準。記憶體同步重置、
                        // DB DELETE 同步 await，讓 Python 在 row 真正刪除後才收到
                        // 確認；DB 失敗時仍保留記憶體重置，下個寫入週期會把新
                        // (=當前 balance) peak 重新 UPSERT。
                        PipelineCommand::ResetDrawdownBaseline { response_tx } => {
                            let em_for_reset = pipeline.effective_engine_mode().to_string();
                            let peak_before = pipeline.paper_state.peak_balance();
                            let balance_before = pipeline.paper_state.balance();
                            pipeline.paper_state.reset_drawdown_baseline();
                            let db_result = if let Some(pool) = audit_pool.as_ref() {
                                crate::paper_state::checkpoint::delete_checkpoint(
                                    pool,
                                    &em_for_reset,
                                )
                                .await
                            } else {
                                Ok(())
                            };
                            let reply = match db_result {
                                Ok(()) => {
                                    info!(
                                        engine_mode = %em_for_reset,
                                        peak_before,
                                        peak_after = pipeline.paper_state.peak_balance(),
                                        balance = balance_before,
                                        "P1-5 A2: drawdown baseline reset via IPC \
                                         / 已通過 IPC 重置 drawdown 基準"
                                    );
                                    snapshot_writer.force_write(&pipeline.snapshot());
                                    Ok(format!(
                                        "reset engine_mode={em_for_reset} \
                                         peak_before={peak_before:.2} \
                                         peak_after={balance_before:.2}"
                                    ))
                                }
                                Err(e) => {
                                    warn!(
                                        engine_mode = %em_for_reset,
                                        error = %e,
                                        "P1-5 A2: checkpoint DELETE failed (memory already reset) \
                                         / checkpoint 刪除失敗（記憶體已重置）"
                                    );
                                    Err(format!("DB delete failed: {e}"))
                                }
                            };
                            let _ = response_tx.send(reply);
                        }
                        other => {
                            handlers::handle_paper_command(
                                other,
                                &mut pipeline,
                                &mut snapshot_writer,
                                &mut pending_orders,
                            );
                        }
                    }
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

                        // EXT-1 + EDGE-P2-3 Phase 1B-3.2: Sweep timed-out pending orders (every 5s).
                        // Branch by TimeInForce:
                        //   - PostOnly maker: once elapsed >= po.maker_timeout_ms (default 45s),
                        //     spawn non-blocking REST cancel via orderLinkId + remove tracker row.
                        //   - Market (legacy): 5s soft warn / 60s hard remove (unchanged).
                        // Tracker row removal after cancel is intentional — if a race fills the
                        // order between our sweep and Bybit's cancel processing, the existing
                        // legacy hard-remove semantics apply (unmatched WS fill goes through the
                        // position reconciler). A stricter "wait-for-cancel-ack then remove"
                        // pattern is deferred to an FUP.
                        // EDGE-P2-3 Phase 1B-3.2：超時 pending order 掃描（每 5s）。
                        //   - PostOnly 掛單：elapsed >= maker_timeout_ms（預設 45s）→ 非阻塞 REST 取消 + 移除。
                        //   - Market（舊行為）：5s 軟警告 / 60s 硬移除，不變。
                        if !pending_orders.is_empty() && last_pending_check.elapsed() >= pending_timeout {
                            let now_ms = openclaw_core::now_ms();
                            let mut maker_to_cancel: Vec<(String, String, u64, u64)> = Vec::new();
                            let mut legacy_to_remove: Vec<String> = Vec::new();
                            for (key, po) in pending_orders.iter() {
                                let elapsed = now_ms.saturating_sub(po.sent_ts_ms);
                                match classify_pending_sweep(po, elapsed) {
                                    PendingSweepAction::MakerTimeoutCancel => {
                                        let deadline_ms = po.maker_timeout_ms.unwrap_or(45_000);
                                        maker_to_cancel.push((
                                            key.clone(),
                                            po.symbol.clone(),
                                            elapsed,
                                            deadline_ms,
                                        ));
                                    }
                                    PendingSweepAction::LegacyHardRemove => {
                                        error!(
                                            order_link_id = %key,
                                            symbol = %po.symbol,
                                            elapsed_ms = elapsed,
                                            "pending order hard timeout (>60s) — removing / 待處理訂單硬超時，移除"
                                        );
                                        legacy_to_remove.push(key.clone());
                                    }
                                    PendingSweepAction::LegacySoftWarn => {
                                        warn!(
                                            order_link_id = %key,
                                            symbol = %po.symbol,
                                            elapsed_ms = elapsed,
                                            filled = %po.cum_filled_qty,
                                            requested = %po.qty,
                                            "pending order soft timeout (>5s) / 待處理訂單軟超時"
                                        );
                                    }
                                    PendingSweepAction::Keep => {}
                                }
                            }
                            // Dispatch non-blocking cancels for timed-out PostOnly makers.
                            // 非阻塞派發超時 PostOnly 掛單取消。
                            for (link_id, symbol, elapsed, deadline_ms) in &maker_to_cancel {
                                warn!(
                                    order_link_id = %link_id,
                                    symbol = %symbol,
                                    elapsed_ms = elapsed,
                                    deadline_ms = deadline_ms,
                                    reason = "maker_timeout_cancel",
                                    "PostOnly maker timed out — cancelling via orderLinkId / PostOnly 掛單超時 — 以 orderLinkId 取消"
                                );
                                if let Some(ref client) = shared_client {
                                    let c = client.clone();
                                    let sym = symbol.clone();
                                    let lid = link_id.clone();
                                    tokio::spawn(async move {
                                        pending_sweep::cancel_resting_maker_order(c, sym, lid).await;
                                    });
                                }
                            }
                            // Remove maker rows we just dispatched cancels for.
                            // 移除剛派發取消的 maker 訂單記錄。
                            for (link_id, _, _, _) in &maker_to_cancel {
                                pending_orders.remove(link_id);
                            }
                            // Remove legacy Market hard-timeout rows.
                            // 移除舊 Market 硬超時記錄。
                            for key in &legacy_to_remove {
                                pending_orders.remove(key);
                            }
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

                            // P1-5 A2: piggy-back checkpoint UPSERT on the state-writer
                            // cadence (~30s per engine). Detached spawn so the event loop
                            // isn't blocked on the DB round-trip. `audit_pool.clone()` is
                            // cheap (Arc<Inner>). Fail-soft: warn logs live inside
                            // `write_checkpoint`, next tick will retry.
                            // P1-5 A2：在狀態寫入週期（每引擎 ~30s）順手 UPSERT checkpoint。
                            // 分離 spawn 避免阻塞事件迴圈；pool clone 為 Arc 廉價。
                            // fail-soft：write_checkpoint 內部 warn log，下週期重試。
                            if let Some(pool) = audit_pool.as_ref() {
                                let pool_clone = pool.clone();
                                let em = pipeline.effective_engine_mode().to_string();
                                let peak = pipeline.paper_state.peak_balance();
                                let session_start_ts_ms =
                                    pipeline.paper_state.session_start_ts_ms();
                                tokio::spawn(async move {
                                    if let Err(e) = crate::paper_state::checkpoint::write_checkpoint(
                                        &pool_clone,
                                        &em,
                                        peak,
                                        session_start_ts_ms,
                                    )
                                    .await
                                    {
                                        warn!(
                                            engine_mode = %em,
                                            error = %e,
                                            "P1-5 A2: checkpoint UPSERT failed (will retry next cycle) \
                                             / checkpoint 寫入失敗，下週期重試"
                                        );
                                    }
                                });
                            }

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
