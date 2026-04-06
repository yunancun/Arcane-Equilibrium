//! Trading lifecycle writer — batch INSERT signals/intents/fills/positions to PG.
//! 交易生命週期寫入器 — 批量 INSERT 信號/意圖/成交/持倉到 PG。
//!
//! MODULE_NOTE (EN): Async consumer for TradingMsg channel. Routes by variant type
//!   and batch-inserts to 4 trading.* tables (signals, intents, fills, position_snapshots).
//!   Same pattern as market_writer: QueryBuilder::push_values + NaN sanitization.
//! MODULE_NOTE (中): TradingMsg 通道的異步消費者。按變體類型路由，
//!   批量插入到 4 個 trading.* 表。與 market_writer 相同模式。

use super::pool::DbPool;
use super::{sanitize_f64, sanitize_f64_or_zero, TradingMsg};
use sqlx::QueryBuilder;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

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
    let mut pos_buf: Vec<TradingMsg> = Vec::with_capacity(16);

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
                    flush_all(&pool, &mut signal_buf, &mut intent_buf, &mut fill_buf, &mut pos_buf).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(m) => match &m {
                        TradingMsg::Signal { .. } => signal_buf.push(m),
                        TradingMsg::Intent { .. } => intent_buf.push(m),
                        TradingMsg::Fill { .. } => fill_buf.push(m),
                        TradingMsg::PositionSnapshot { .. } => pos_buf.push(m),
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
            &mut pos_buf,
        )
        .await;
    }
    info!("trading_writer stopped / 交易寫入器已停止");
}

async fn flush_all(
    pool: &DbPool,
    signals: &mut Vec<TradingMsg>,
    intents: &mut Vec<TradingMsg>,
    fills: &mut Vec<TradingMsg>,
    positions: &mut Vec<TradingMsg>,
) {
    if !signals.is_empty() {
        flush_signals(pool, signals).await;
    }
    if !intents.is_empty() {
        flush_intents(pool, intents).await;
    }
    if !fills.is_empty() {
        flush_fills(pool, fills).await;
    }
    if !positions.is_empty() {
        flush_positions(pool, positions).await;
    }
}

/// Max rows per batch INSERT to stay under PostgreSQL's 65535 parameter limit.
/// 每批 INSERT 的最大行數，避免超過 PostgreSQL 65535 參數上限。
/// signals = 8 columns → 65535/8 = 8191, use 5000 as safe limit.
const SIGNAL_BATCH_MAX: usize = 5000;
const INTENT_BATCH_MAX: usize = 5000; // 10 columns → 6553 max
const FILL_BATCH_MAX: usize = 4000; // 12 columns → 5461 max
const POSITION_BATCH_MAX: usize = 5000; // 8 columns → 8191 max

async fn flush_signals(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            buf.clear();
            return;
        }
    };
    // Chunk to avoid exceeding PG parameter limit (65535 max)
    // 分塊避免超過 PG 參數上限
    for chunk in buf.chunks(SIGNAL_BATCH_MAX) {
        let mut qb: QueryBuilder<sqlx::Postgres> = QueryBuilder::new(
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
        match qb.build().execute(pg).await {
            Ok(r) => {
                pool.record_success();
                debug!(
                    rows = r.rows_affected(),
                    chunk_size = chunk.len(),
                    "signals flushed"
                );
            }
            Err(e) => {
                let _ = pool.record_failure();
                warn!(error = %e, "signals flush failed");
            }
        }
    }
    buf.clear();
}

async fn flush_intents(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            buf.clear();
            return;
        }
    };
    for chunk in buf.chunks(INTENT_BATCH_MAX) {
        let mut qb: QueryBuilder<sqlx::Postgres> = QueryBuilder::new(
            "INSERT INTO trading.intents (ts, intent_id, signal_id, context_id, symbol, side, qty, price, order_type, strategy_name) "
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
            }
        });
        qb.push(" ON CONFLICT (intent_id, ts) DO NOTHING");
        match qb.build().execute(pg).await {
            Ok(r) => {
                pool.record_success();
                debug!(rows = r.rows_affected(), "intents flushed");
            }
            Err(e) => {
                let _ = pool.record_failure();
                warn!(error = %e, "intents flush failed");
            }
        }
    }
    buf.clear();
}

async fn flush_fills(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            buf.clear();
            return;
        }
    };
    for chunk in buf.chunks(FILL_BATCH_MAX) {
        let mut qb: QueryBuilder<sqlx::Postgres> = QueryBuilder::new(
            "INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, fee, realized_pnl, is_paper, strategy_name, context_id) "
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
                realized_pnl,
                strategy_name,
                context_id,
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
                b.push_bind(sanitize_f64_or_zero(*realized_pnl) as f32);
                b.push_bind(true); // is_paper = always true in demo mode
                b.push_bind(strategy_name.as_str());
                b.push_bind(context_id.as_str());
            }
        });
        qb.push(" ON CONFLICT (fill_id, ts) DO NOTHING");
        match qb.build().execute(pg).await {
            Ok(r) => {
                pool.record_success();
                debug!(rows = r.rows_affected(), "fills flushed");
            }
            Err(e) => {
                let _ = pool.record_failure();
                warn!(error = %e, "fills flush failed");
            }
        }
    }
    buf.clear();
}

async fn flush_positions(pool: &DbPool, buf: &mut Vec<TradingMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            buf.clear();
            return;
        }
    };
    for chunk in buf.chunks(POSITION_BATCH_MAX) {
        let mut qb: QueryBuilder<sqlx::Postgres> = QueryBuilder::new(
            "INSERT INTO trading.position_snapshots (ts, symbol, side, qty, entry_price, mark_price, unrealized_pnl, is_paper) "
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
                b.push_bind(true); // is_paper
            }
        });
        qb.push(" ON CONFLICT (symbol, side, ts) DO NOTHING");
        match qb.build().execute(pg).await {
            Ok(r) => {
                pool.record_success();
                debug!(rows = r.rows_affected(), "positions flushed");
            }
            Err(e) => {
                let _ = pool.record_failure();
                warn!(error = %e, "positions flush failed");
            }
        }
    }
    buf.clear();
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
            realized_pnl: 0.0,
            strategy_name: "ma".into(),
            context_id: "c1".into(),
        };
        assert!(matches!(fill, TradingMsg::Fill { .. }));
    }

    #[test]
    fn test_batch_limits_under_pg_param_max() {
        // Verify batch constants stay under PG 65535 param limit
        // 驗證批次常數不超過 PG 65535 參數上限
        assert!(
            SIGNAL_BATCH_MAX * 8 <= 65535,
            "signals batch exceeds PG limit"
        );
        assert!(
            INTENT_BATCH_MAX * 10 <= 65535,
            "intents batch exceeds PG limit"
        );
        assert!(FILL_BATCH_MAX * 12 <= 65535, "fills batch exceeds PG limit");
        assert!(
            POSITION_BATCH_MAX * 8 <= 65535,
            "positions batch exceeds PG limit"
        );
    }

    #[test]
    fn test_batch_routing() {
        let mut sigs = Vec::new();
        let mut intents = Vec::new();
        let mut fills = Vec::new();
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
                realized_pnl: 0.0,
                strategy_name: "ma".into(),
                context_id: "c1".into(),
            },
            TradingMsg::PositionSnapshot {
                ts_ms: 0,
                symbol: "BTC".into(),
                side: "Long".into(),
                qty: 0.1,
                entry_price: 50000.0,
                mark_price: 50100.0,
                unrealized_pnl: 10.0,
            },
        ];

        for m in msgs {
            match &m {
                TradingMsg::Signal { .. } => sigs.push(m),
                TradingMsg::Intent { .. } => intents.push(m),
                TradingMsg::Fill { .. } => fills.push(m),
                TradingMsg::PositionSnapshot { .. } => positions.push(m),
            }
        }

        assert_eq!(sigs.len(), 1);
        assert_eq!(intents.len(), 1);
        assert_eq!(fills.len(), 1);
        assert_eq!(positions.len(), 1);
    }
}
