//! Trading lifecycle writer — batch INSERT signals/intents/fills/funding/positions/verdicts/orders to PG.
//! 交易生命週期寫入器 — 批量 INSERT 信號/意圖/成交/資金費/持倉/風控裁定/訂單到 PG。
//!
//! MODULE_NOTE (EN): Async consumer for TradingMsg channel. Routes by variant type
//!   and batch-inserts to 8 trading.* tables (signals, intents, fills,
//!   funding_settlements, position_snapshots, risk_verdicts, orders,
//!   order_state_changes).
//!   Same pattern as market_writer: QueryBuilder::push_values + NaN sanitization.
//! MODULE_NOTE (中): TradingMsg 通道的異步消費者。按變體類型路由，
//!   批量插入到 8 個 trading.* 表（含 funding_settlements / risk_verdicts /
//!   orders / order_state_changes）。
//!   與 market_writer 相同模式。

use super::batch_insert::{batch_insert_chunked, BatchInsertOutcome};
use super::pool::DbPool;
use super::{sanitize_f64, sanitize_f64_or_zero, TradingMsg};
use sqlx::{Postgres, QueryBuilder};
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

/// Run the trading data writer task.
/// 運行交易數據寫入器任務。
pub async fn run_trading_writer(
    mut rx: mpsc::Receiver<TradingMsg>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    let mut signal_buf: Vec<TradingMsg> = Vec::with_capacity(32);
    let mut intent_buf: Vec<TradingMsg> = Vec::with_capacity(16);
    let mut fill_buf: Vec<TradingMsg> = Vec::with_capacity(16);
    let mut funding_buf: Vec<TradingMsg> = Vec::with_capacity(16);
    let mut pos_buf: Vec<TradingMsg> = Vec::with_capacity(16);
    let mut verdict_buf: Vec<TradingMsg> = Vec::with_capacity(16);
    let mut order_buf: Vec<TradingMsg> = Vec::with_capacity(16);
    let mut state_change_buf: Vec<TradingMsg> = Vec::with_capacity(16);

    let flush_interval = {
        let cfg = config.get();
        std::time::Duration::from_millis(cfg.database.batch_flush_interval_ms)
    };
    let mut flush_timer = tokio::time::interval(flush_interval);
    flush_timer.tick().await;

    info!("trading_writer started / 交易寫入器已啟動");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                if pool.is_available() {
                    flush_all(&pool, &mut signal_buf, &mut intent_buf, &mut fill_buf,
                              &mut funding_buf, &mut pos_buf, &mut verdict_buf,
                              &mut order_buf, &mut state_change_buf).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(m) => match &m {
                        TradingMsg::Signal { .. } => signal_buf.push(m),
                        TradingMsg::Intent { .. } => intent_buf.push(m),
                        TradingMsg::Fill { .. } => fill_buf.push(m),
                        TradingMsg::FundingSettlement { .. } => funding_buf.push(m),
                        TradingMsg::PositionSnapshot { .. } => pos_buf.push(m),
                        TradingMsg::RiskVerdict { .. } => verdict_buf.push(m),
                        TradingMsg::Order { .. } => order_buf.push(m),
                        TradingMsg::OrderStateChange { .. } => state_change_buf.push(m),
                    },
                    None => break,
                }
            }
        }
    }

    if pool.is_available() {
        flush_all(
            &pool,
            &mut signal_buf,
            &mut intent_buf,
            &mut fill_buf,
            &mut funding_buf,
            &mut pos_buf,
            &mut verdict_buf,
            &mut order_buf,
            &mut state_change_buf,
        )
        .await;
    }
    info!("trading_writer stopped / 交易寫入器已停止");
}

/// P-10: Parallel flush — each buffer writes to an independent table, no cross-deps.
/// P-10：並行 flush — 各緩衝區寫入獨立表，無交叉依賴。
async fn flush_all(
    pool: &DbPool,
    signals: &mut Vec<TradingMsg>,
    intents: &mut Vec<TradingMsg>,
    fills: &mut Vec<TradingMsg>,
    funding: &mut Vec<TradingMsg>,
    positions: &mut Vec<TradingMsg>,
    verdicts: &mut Vec<TradingMsg>,
    orders: &mut Vec<TradingMsg>,
    state_changes: &mut Vec<TradingMsg>,
) {
    tokio::join!(
        async {
            if !signals.is_empty() {
                flush_signals(pool, signals).await;
            }
        },
        async {
            if !intents.is_empty() {
                flush_intents(pool, intents).await;
            }
        },
        async {
            if !fills.is_empty() {
                flush_fills(pool, fills).await;
            }
        },
        async {
            if !funding.is_empty() {
                flush_funding_settlements(pool, funding).await;
            }
        },
        async {
            if !positions.is_empty() {
                flush_positions(pool, positions).await;
            }
        },
        async {
            if !verdicts.is_empty() {
                flush_verdicts(pool, verdicts).await;
            }
        },
        async {
            if !orders.is_empty() {
                flush_orders(pool, orders).await;
            }
        },
        async {
            if !state_changes.is_empty() {
                flush_order_state_changes(pool, state_changes).await;
            }
        },
    );
}

// Column counts per table — the `batch_insert` helper uses these to derive
// `chunk_rows = clamp(65535 / cols, 1, 10000)` centrally, so the old per-table
// `*_BATCH_MAX` constants are no longer needed as a second source of truth.
// 每表欄位數 — `batch_insert` 以此集中推算 chunk_rows，取代先前各表硬編碼常數。
const SIGNAL_COLS: usize = 8;
const INTENT_COLS: usize = 12; // includes details JSONB
const FILL_COLS: usize = 22; // includes execution reference/slippage (V028)
const FUNDING_SETTLEMENT_COLS: usize = 13; // includes raw JSONB
const POSITION_COLS: usize = 9;
const VERDICT_COLS: usize = 12; // includes risk_level/check arrays + details
const ORDER_COLS: usize = 11;
const STATE_CHANGE_COLS: usize = 8;

fn should_clear_buffer(table: &str, outcome: BatchInsertOutcome, pending_rows: usize) -> bool {
    if outcome.all_ok() {
        true
    } else {
        warn!(
            table = table,
            pending_rows = pending_rows,
            rows_affected = outcome.rows_affected,
            failed_chunks = outcome.failed_chunks,
            "trading_writer flush incomplete — retaining buffer for retry \
             / trading_writer 寫入未完成 — 保留 buffer 下輪重試"
        );
        false
    }
}

async fn flush_signals(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "trading.signals flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };
    let outcome = batch_insert_chunked(
        pg,
        pool,
        "trading.signals",
        buf.as_slice(),
        SIGNAL_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO trading.signals (ts, signal_id, symbol, strategy_name, timeframe, signal_type, strength, context_id) "
            );
            qb.push_values(chunk.iter(), |mut b, msg| {
                if let TradingMsg::Signal {
                    signal_id,
                    ts_ms,
                    symbol,
                    strategy_name,
                    timeframe,
                    signal_type,
                    strength,
                    context_id,
                } = msg
                {
                    b.push_bind(
                        chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                    );
                    b.push_bind(signal_id.as_str());
                    b.push_bind(symbol.as_str());
                    b.push_bind(strategy_name.as_str());
                    b.push_bind(timeframe.as_str());
                    b.push_bind(signal_type.as_str());
                    b.push_bind(sanitize_f64(*strength).map(|v| v as f32));
                    b.push_bind(context_id.as_str());
                }
            });
            qb.push(" ON CONFLICT (signal_id, ts) DO NOTHING");
            qb
        },
    )
    .await;
    if should_clear_buffer("trading.signals", outcome, buf.len()) {
        buf.clear();
    }
}

async fn flush_intents(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "trading.intents flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };
    let outcome = batch_insert_chunked(
        pg,
        pool,
        "trading.intents",
        buf.as_slice(),
        INTENT_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO trading.intents (ts, intent_id, signal_id, context_id, symbol, side, qty, price, order_type, strategy_name, engine_mode, details) "
            );
            qb.push_values(chunk.iter(), |mut b, msg| {
                if let TradingMsg::Intent {
                    intent_id,
                    ts_ms,
                    signal_id,
                    context_id,
                    symbol,
                    side,
                    qty,
                    price,
                    order_type,
                    strategy_name,
                    engine_mode,
                    details,
                } = msg
                {
                    b.push_bind(
                        chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                    );
                    b.push_bind(intent_id.as_str());
                    b.push_bind(signal_id.as_str());
                    b.push_bind(context_id.as_str());
                    b.push_bind(symbol.as_str());
                    b.push_bind(side.as_str());
                    b.push_bind(sanitize_f64(*qty).map(|v| v as f32));
                    b.push_bind(sanitize_f64(*price).map(|v| v as f32));
                    b.push_bind(order_type.as_str());
                    b.push_bind(strategy_name.as_str());
                    b.push_bind(engine_mode.as_str());
                    b.push_bind(details.clone());
                }
            });
            qb.push(" ON CONFLICT (intent_id, ts) DO NOTHING");
            qb
        },
    )
    .await;
    if should_clear_buffer("trading.intents", outcome, buf.len()) {
        buf.clear();
    }
}

async fn flush_fills(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "trading.fills flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };
    let outcome = batch_insert_chunked(
        pg,
        pool,
        "trading.fills",
        buf.as_slice(),
        FILL_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, fee, fee_rate, reference_price, reference_ts_ms, reference_source, slippage_bps, liquidity_role, fill_latency_ms, realized_pnl, is_paper, strategy_name, context_id, entry_context_id, engine_mode, exit_source) "
            );
            qb.push_values(chunk.iter(), |mut b, msg| {
                if let TradingMsg::Fill {
                    fill_id,
                    ts_ms,
                    order_id,
                    symbol,
                    side,
                    qty,
                    price,
                    fee,
                    fee_rate,
                    reference_price,
                    reference_ts_ms,
                    reference_source,
                    slippage_bps,
                    liquidity_role,
                    fill_latency_ms,
                    realized_pnl,
                    strategy_name,
                    context_id,
                    entry_context_id,
                    engine_mode,
                    exit_source,
                } = msg
                {
                    b.push_bind(
                        chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                    );
                    b.push_bind(fill_id.as_str());
                    b.push_bind(order_id.as_str());
                    b.push_bind(symbol.as_str());
                    b.push_bind(side.as_str());
                    b.push_bind(sanitize_f64_or_zero(*qty) as f32);
                    b.push_bind(sanitize_f64_or_zero(*price) as f32);
                    b.push_bind(sanitize_f64_or_zero(*fee) as f32);
                    b.push_bind(sanitize_f64_or_zero(*fee_rate) as f32);
                    b.push_bind(reference_price.as_ref().and_then(|v| sanitize_f64(*v)));
                    b.push_bind(reference_ts_ms.map(|v| v as i64));
                    b.push_bind(reference_source.as_deref());
                    b.push_bind(slippage_bps.as_ref().and_then(|v| sanitize_f64(*v)));
                    b.push_bind(liquidity_role.as_deref());
                    b.push_bind(fill_latency_ms.map(|v| v as i64));
                    b.push_bind(sanitize_f64_or_zero(*realized_pnl) as f32);
                    // DEPRECATED: is_paper derived from engine_mode (compat with Grafana).
                    // 已棄用：is_paper 由 engine_mode 派生（兼容 Grafana）。
                    b.push_bind(engine_mode != "live");
                    b.push_bind(strategy_name.as_str());
                    b.push_bind(context_id.as_str());
                    // EDGE-P3-1 R2: entry_context_id — NULL when empty (open fills,
                    // pre-V017 restored positions, orphan adopts). Close fills carry
                    // the opening entry's context_id for ML training JOIN.
                    // EDGE-P3-1 R2：entry_context_id — 空串寫 NULL（開倉、pre-V017 還原、
                    // orphan adopt）；平倉 fill 攜帶開倉 entry 的 context_id 供 ML JOIN。
                    if entry_context_id.is_empty() {
                        b.push_bind(None::<String>);
                    } else {
                        b.push_bind(Some(entry_context_id.as_str().to_string()));
                    }
                    b.push_bind(engine_mode.as_str());
                    // INFRA-PREBUILD-1 Part A: Combine Layer ExitSource tag
                    // (V021 trading.fills.exit_source). None → NULL (open
                    // fill or non-Combine exit path like HARD STOP).
                    // INFRA-PREBUILD-1 A 部：Combine Layer ExitSource 標籤。
                    // None → NULL（開倉 fill 或非 Combine 退場如 HARD STOP）。
                    b.push_bind(exit_source.as_deref());
                }
            });
            qb.push(" ON CONFLICT (fill_id, ts) DO NOTHING");
            qb
        },
    )
    .await;
    if should_clear_buffer("trading.fills", outcome, buf.len()) {
        buf.clear();
    }
}

async fn flush_funding_settlements(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "trading.funding_settlements flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };
    let outcome = batch_insert_chunked(
        pg,
        pool,
        "trading.funding_settlements",
        buf.as_slice(),
        FUNDING_SETTLEMENT_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO trading.funding_settlements \
                 (ts, settlement_id, exec_id, symbol, side, amount, fee_currency, \
                  exec_value, exec_price, exec_qty, strategy_name, engine_mode, raw) ",
            );
            qb.push_values(chunk.iter(), |mut b, msg| {
                if let TradingMsg::FundingSettlement {
                    settlement_id,
                    ts_ms,
                    exec_id,
                    symbol,
                    side,
                    amount,
                    fee_currency,
                    exec_value,
                    exec_price,
                    exec_qty,
                    strategy_name,
                    engine_mode,
                    raw,
                } = msg
                {
                    b.push_bind(
                        chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                    );
                    b.push_bind(settlement_id.as_str());
                    b.push_bind(exec_id.as_str());
                    b.push_bind(symbol.as_str());
                    b.push_bind(side.as_str());
                    b.push_bind(sanitize_f64_or_zero(*amount));
                    b.push_bind(fee_currency.as_str());
                    b.push_bind(sanitize_f64_or_zero(*exec_value));
                    b.push_bind(sanitize_f64_or_zero(*exec_price));
                    b.push_bind(sanitize_f64_or_zero(*exec_qty));
                    b.push_bind(strategy_name.as_str());
                    b.push_bind(engine_mode.as_str());
                    b.push_bind(raw.clone());
                }
            });
            qb.push(" ON CONFLICT (settlement_id, ts) DO NOTHING");
            qb
        },
    )
    .await;
    if should_clear_buffer("trading.funding_settlements", outcome, buf.len()) {
        buf.clear();
    }
}

async fn flush_positions(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "trading.position_snapshots flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };
    let outcome = batch_insert_chunked(
        pg,
        pool,
        "trading.position_snapshots",
        buf.as_slice(),
        POSITION_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO trading.position_snapshots (ts, symbol, side, qty, entry_price, mark_price, unrealized_pnl, is_paper, engine_mode) "
            );
            qb.push_values(chunk.iter(), |mut b, msg| {
                if let TradingMsg::PositionSnapshot {
                    ts_ms,
                    symbol,
                    side,
                    qty,
                    entry_price,
                    mark_price,
                    unrealized_pnl,
                    engine_mode,
                } = msg
                {
                    b.push_bind(
                        chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                    );
                    b.push_bind(symbol.as_str());
                    b.push_bind(side.as_str());
                    b.push_bind(sanitize_f64(*qty).map(|v| v as f32));
                    b.push_bind(sanitize_f64(*entry_price).map(|v| v as f32));
                    b.push_bind(sanitize_f64(*mark_price).map(|v| v as f32));
                    b.push_bind(sanitize_f64(*unrealized_pnl).map(|v| v as f32));
                    // DEPRECATED: is_paper derived from engine_mode (compat with Grafana).
                    // 已棄用：is_paper 由 engine_mode 派生（兼容 Grafana）。
                    b.push_bind(engine_mode != "live");
                    b.push_bind(engine_mode.as_str());
                }
            });
            qb.push(" ON CONFLICT (symbol, side, ts) DO NOTHING");
            qb
        },
    )
    .await;
    if should_clear_buffer("trading.position_snapshots", outcome, buf.len()) {
        buf.clear();
    }
}

/// Flush Guardian risk verdicts to trading.risk_verdicts.
/// 將 Guardian 風控裁定批量寫入 trading.risk_verdicts。
async fn flush_verdicts(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "trading.risk_verdicts flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };
    let outcome = batch_insert_chunked(
        pg,
        pool,
        "trading.risk_verdicts",
        buf.as_slice(),
        VERDICT_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO trading.risk_verdicts \
                 (ts, verdict_id, intent_id, context_id, symbol, verdict, risk_level, \
                  checks_passed, checks_failed, reason, details, engine_mode) ",
            );
            qb.push_values(chunk.iter(), |mut b, msg| {
                if let TradingMsg::RiskVerdict {
                    verdict_id,
                    ts_ms,
                    intent_id,
                    context_id,
                    symbol,
                    verdict,
                    risk_score,
                    risk_level,
                    checks_passed,
                    checks_failed,
                    reasons,
                    modified_qty,
                    engine_mode,
                } = msg
                {
                    b.push_bind(
                        chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                    );
                    b.push_bind(verdict_id.as_str());
                    b.push_bind(intent_id.as_str());
                    b.push_bind(context_id.as_str());
                    b.push_bind(symbol.as_str());
                    b.push_bind(verdict.as_str());
                    b.push_bind(risk_level.as_deref());
                    b.push_bind(checks_passed);
                    b.push_bind(checks_failed);
                    // Flatten reasons into a single reason string / 將 reasons 合併為單一字串
                    b.push_bind(reasons.join("; "));
                    // Store risk_score + modified_qty as JSONB details / 詳細資訊存為 JSONB
                    b.push_bind(serde_json::json!({
                        "risk_score": sanitize_f64(*risk_score),
                        "modified_qty": modified_qty,
                    }));
                    b.push_bind(engine_mode.as_str());
                }
            });
            qb.push(" ON CONFLICT (verdict_id, ts) DO NOTHING");
            qb
        },
    )
    .await;
    if should_clear_buffer("trading.risk_verdicts", outcome, buf.len()) {
        buf.clear();
    }
}

/// Flush exchange orders to trading.orders.
/// 將交易所訂單批量寫入 trading.orders。
async fn flush_orders(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "trading.orders flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };
    let outcome = batch_insert_chunked(
        pg,
        pool,
        "trading.orders",
        buf.as_slice(),
        ORDER_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO trading.orders \
                 (ts, order_id, symbol, side, order_type, qty, strategy_name, \
                  category, is_paper, status, engine_mode) ",
            );
            qb.push_values(chunk.iter(), |mut b, msg| {
                if let TradingMsg::Order {
                    order_id,
                    ts_ms,
                    symbol,
                    side,
                    order_type,
                    qty,
                    strategy_name,
                    is_close: _,
                    engine_mode,
                } = msg
                {
                    b.push_bind(
                        chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                    );
                    b.push_bind(order_id.as_str());
                    b.push_bind(symbol.as_str());
                    b.push_bind(side.as_str());
                    b.push_bind(order_type.as_str());
                    b.push_bind(sanitize_f64_or_zero(*qty) as f32);
                    b.push_bind(strategy_name.as_str());
                    b.push_bind("linear"); // Bybit USDT perp default / USDT 永續默認
                                           // DEPRECATED is_paper derived from engine_mode (Grafana compat)
                    b.push_bind(engine_mode != "live");
                    b.push_bind("Working"); // order enters this table when exchange confirms
                    b.push_bind(engine_mode.as_str());
                }
            });
            qb.push(" ON CONFLICT (order_id, ts) DO NOTHING");
            qb
        },
    )
    .await;
    if should_clear_buffer("trading.orders", outcome, buf.len()) {
        buf.clear();
    }
}

/// Flush order state changes to trading.order_state_changes.
/// 將訂單狀態轉換批量寫入 trading.order_state_changes。
async fn flush_order_state_changes(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "trading.order_state_changes flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };
    let outcome = batch_insert_chunked(
        pg,
        pool,
        "trading.order_state_changes",
        buf.as_slice(),
        STATE_CHANGE_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO trading.order_state_changes \
                 (ts, order_id, from_status, to_status, filled_qty, avg_price, reason, engine_mode) ",
            );
            qb.push_values(chunk.iter(), |mut b, msg| {
                if let TradingMsg::OrderStateChange {
                    order_id,
                    ts_ms,
                    from_status,
                    to_status,
                    filled_qty,
                    avg_price,
                    reason,
                    engine_mode,
                } = msg
                {
                    b.push_bind(
                        chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                    );
                    b.push_bind(order_id.as_str());
                    b.push_bind(from_status.as_deref());
                    b.push_bind(to_status.as_str());
                    b.push_bind(filled_qty.and_then(sanitize_f64).map(|v| v as f32));
                    b.push_bind(avg_price.and_then(sanitize_f64).map(|v| v as f32));
                    b.push_bind(reason.as_deref());
                    b.push_bind(engine_mode.as_str());
                }
            });
            qb.push(" ON CONFLICT (order_id, ts, to_status) DO NOTHING");
            qb
        },
    )
    .await;
    if should_clear_buffer("trading.order_state_changes", outcome, buf.len()) {
        buf.clear();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trading_msg_routing() {
        let sig = TradingMsg::Signal {
            signal_id: "s1".into(),
            ts_ms: 0,
            symbol: "BTC".into(),
            strategy_name: "ma".into(),
            timeframe: "1m".into(),
            signal_type: "LONG".into(),
            strength: 0.8,
            context_id: "c1".into(),
        };
        assert!(matches!(sig, TradingMsg::Signal { .. }));

        let fill = TradingMsg::Fill {
            fill_id: "f1".into(),
            ts_ms: 0,
            order_id: "o1".into(),
            symbol: "BTC".into(),
            side: "Buy".into(),
            qty: 0.1,
            price: 50000.0,
            fee: 2.75,
            fee_rate: 0.00055,
            reference_price: None,
            reference_ts_ms: None,
            reference_source: None,
            slippage_bps: None,
            liquidity_role: None,
            fill_latency_ms: None,
            realized_pnl: 0.0,
            strategy_name: "ma".into(),
            context_id: "c1".into(),
            entry_context_id: String::new(),
            engine_mode: "paper".into(),
            exit_source: None,
        };
        assert!(matches!(fill, TradingMsg::Fill { .. }));

        let funding = TradingMsg::FundingSettlement {
            settlement_id: "funding-f1".into(),
            ts_ms: 0,
            exec_id: "f1".into(),
            symbol: "BTC".into(),
            side: "Sell".into(),
            amount: 1.25,
            fee_currency: "USDT".into(),
            exec_value: 100.0,
            exec_price: 100.0,
            exec_qty: 1.0,
            strategy_name: "funding_arb".into(),
            engine_mode: "demo".into(),
            raw: None,
        };
        assert!(matches!(funding, TradingMsg::FundingSettlement { .. }));
    }

    #[test]
    fn test_batch_limits_under_pg_param_max() {
        // Post-refactor: chunk size is computed centrally via
        // `batch_insert::chunk_rows_for_columns`. This test pins the column
        // counts so a schema drift (V-migration adding a column) that we forget
        // to update here surfaces as a test diff rather than silently edging
        // toward the 65535 ceiling.
        // 重構後：分塊大小由 `batch_insert::chunk_rows_for_columns` 集中計算；
        // 本測試固定各表欄位數，避免 schema 漂移後無感逼近 65535 上限。
        use super::super::batch_insert::chunk_rows_for_columns;
        assert!(
            chunk_rows_for_columns(SIGNAL_COLS) * SIGNAL_COLS <= 65535,
            "signals batch would exceed PG limit"
        );
        assert!(
            chunk_rows_for_columns(INTENT_COLS) * INTENT_COLS <= 65535,
            "intents batch would exceed PG limit"
        );
        assert!(
            chunk_rows_for_columns(FILL_COLS) * FILL_COLS <= 65535,
            "fills batch would exceed PG limit"
        );
        assert!(
            chunk_rows_for_columns(FUNDING_SETTLEMENT_COLS) * FUNDING_SETTLEMENT_COLS <= 65535,
            "funding settlements batch would exceed PG limit"
        );
        assert!(
            chunk_rows_for_columns(POSITION_COLS) * POSITION_COLS <= 65535,
            "positions batch would exceed PG limit"
        );
        assert!(
            chunk_rows_for_columns(VERDICT_COLS) * VERDICT_COLS <= 65535,
            "verdicts batch would exceed PG limit"
        );
        assert!(
            chunk_rows_for_columns(ORDER_COLS) * ORDER_COLS <= 65535,
            "orders batch would exceed PG limit"
        );
        assert!(
            chunk_rows_for_columns(STATE_CHANGE_COLS) * STATE_CHANGE_COLS <= 65535,
            "state_changes batch would exceed PG limit"
        );
    }

    #[test]
    fn test_batch_routing() {
        let mut sigs = Vec::new();
        let mut intents = Vec::new();
        let mut fills = Vec::new();
        let mut funding = Vec::new();
        let mut positions = Vec::new();

        let msgs: Vec<TradingMsg> = vec![
            TradingMsg::Signal {
                signal_id: "s1".into(),
                ts_ms: 0,
                symbol: "BTC".into(),
                strategy_name: "ma".into(),
                timeframe: "1m".into(),
                signal_type: "LONG".into(),
                strength: 0.8,
                context_id: "c1".into(),
            },
            TradingMsg::Intent {
                intent_id: "i1".into(),
                ts_ms: 0,
                signal_id: "s1".into(),
                context_id: "c1".into(),
                symbol: "BTC".into(),
                side: "Buy".into(),
                qty: 0.1,
                price: 50000.0,
                order_type: "market".into(),
                strategy_name: "ma".into(),
                engine_mode: "paper".into(),
                details: Some(serde_json::json!({"strategy": "ma", "confidence": 0.5})),
            },
            TradingMsg::Fill {
                fill_id: "f1".into(),
                ts_ms: 0,
                order_id: "o1".into(),
                symbol: "BTC".into(),
                side: "Buy".into(),
                qty: 0.1,
                price: 50000.0,
                fee: 2.75,
                fee_rate: 0.00055,
                reference_price: None,
                reference_ts_ms: None,
                reference_source: None,
                slippage_bps: None,
                liquidity_role: None,
                fill_latency_ms: None,
                realized_pnl: 0.0,
                strategy_name: "ma".into(),
                context_id: "c1".into(),
                entry_context_id: String::new(),
                engine_mode: "paper".into(),
                exit_source: None,
            },
            TradingMsg::FundingSettlement {
                settlement_id: "funding-f1".into(),
                ts_ms: 0,
                exec_id: "f1".into(),
                symbol: "BTC".into(),
                side: "Sell".into(),
                amount: 1.25,
                fee_currency: "USDT".into(),
                exec_value: 100.0,
                exec_price: 100.0,
                exec_qty: 1.0,
                strategy_name: "funding_arb".into(),
                engine_mode: "demo".into(),
                raw: None,
            },
            TradingMsg::PositionSnapshot {
                ts_ms: 0,
                symbol: "BTC".into(),
                side: "Long".into(),
                qty: 0.1,
                entry_price: 50000.0,
                mark_price: 50100.0,
                unrealized_pnl: 10.0,
                engine_mode: "paper".into(),
            },
        ];

        let mut verdicts = Vec::new();
        let mut orders = Vec::new();
        let mut state_changes = Vec::new();
        for m in msgs {
            match &m {
                TradingMsg::Signal { .. } => sigs.push(m),
                TradingMsg::Intent { .. } => intents.push(m),
                TradingMsg::Fill { .. } => fills.push(m),
                TradingMsg::FundingSettlement { .. } => funding.push(m),
                TradingMsg::PositionSnapshot { .. } => positions.push(m),
                TradingMsg::RiskVerdict { .. } => verdicts.push(m),
                TradingMsg::Order { .. } => orders.push(m),
                TradingMsg::OrderStateChange { .. } => state_changes.push(m),
            }
        }

        assert_eq!(sigs.len(), 1);
        assert_eq!(intents.len(), 1);
        assert_eq!(fills.len(), 1);
        assert_eq!(funding.len(), 1);
        assert_eq!(positions.len(), 1);
        assert_eq!(verdicts.len(), 0);
        assert_eq!(orders.len(), 0);
        assert_eq!(state_changes.len(), 0);
    }
}
