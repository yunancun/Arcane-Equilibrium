//! Market data writer — async consumer for batch INSERT to 10 market.* tables.
//! 市場數據寫入器 — 批量 INSERT 到 10 個 market.* 表的異步消費者。
//!
//! MODULE_NOTE (EN): Receives MarketDataMsg from bounded channel, accumulates in
//!   memory buffers, flushes every batch_flush_interval_ms using QueryBuilder::push_values().
//!   On 3 consecutive PG failures, switches to JSONL fallback. Non-blocking to tick loop.
//! MODULE_NOTE (中): 從有界通道接收 MarketDataMsg，在內存緩衝區累積，
//!   每 batch_flush_interval_ms 使用 QueryBuilder::push_values() 刷新。
//!   連續 3 次 PG 失敗後切換到 JSONL 回退。不阻塞 tick 循環。

use super::pool::DbPool;
use super::{sanitize_f64, sanitize_f64_or_zero, MarketDataMsg};
use sqlx::QueryBuilder;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Run the market data writer task: receive from channel, batch flush to PG.
/// 運行市場數據寫入器任務：從通道接收，批量刷新到 PG。
pub async fn run_market_writer(
    mut rx: mpsc::Receiver<MarketDataMsg>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    let mut kline_buf: Vec<MarketDataMsg> = Vec::with_capacity(64);
    let mut ticker_buf: Vec<MarketDataMsg> = Vec::with_capacity(64);
    let mut other_buf: Vec<MarketDataMsg> = Vec::with_capacity(64);

    let flush_interval = {
        let cfg = config.get();
        std::time::Duration::from_millis(cfg.database.batch_flush_interval_ms)
    };
    let mut flush_timer = tokio::time::interval(flush_interval);
    flush_timer.tick().await; // skip first immediate tick

    info!("market_writer started / 市場數據寫入器已啟動");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                if pool.is_available() {
                    flush_all(&pool, &mut kline_buf, &mut ticker_buf, &mut other_buf).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(m) => {
                        match &m {
                            MarketDataMsg::KlineClose { .. } => kline_buf.push(m),
                            MarketDataMsg::TickerSnapshot { .. } => ticker_buf.push(m),
                            _ => other_buf.push(m),
                        }
                    }
                    None => break, // channel closed
                }
            }
        }
    }

    // Final flush on shutdown / 關閉時最後一次刷新
    if pool.is_available() {
        flush_all(&pool, &mut kline_buf, &mut ticker_buf, &mut other_buf).await;
    }
    info!("market_writer stopped / 市場數據寫入器已停止");
}

/// Flush all buffers to PG / 刷新所有緩衝區到 PG
async fn flush_all(
    pool: &DbPool,
    kline_buf: &mut Vec<MarketDataMsg>,
    ticker_buf: &mut Vec<MarketDataMsg>,
    other_buf: &mut Vec<MarketDataMsg>,
) {
    if !kline_buf.is_empty() {
        flush_klines(pool, kline_buf).await;
    }
    if !ticker_buf.is_empty() {
        flush_tickers(pool, ticker_buf).await;
    }
    if !other_buf.is_empty() {
        flush_other(pool, other_buf).await;
    }
}

/// Batch INSERT klines to market.klines / 批量插入 K 線到 market.klines
async fn flush_klines(pool: &DbPool, buf: &mut Vec<MarketDataMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => { buf.clear(); return; }
    };

    let mut qb: QueryBuilder<sqlx::Postgres> = QueryBuilder::new(
        "INSERT INTO market.klines (ts, open_ts_ms, close_ts_ms, symbol, timeframe, open, high, low, close, volume, turnover, tick_count) "
    );

    qb.push_values(buf.iter(), |mut b, msg| {
        if let MarketDataMsg::KlineClose { symbol, timeframe, bar } = msg {
            let ts = chrono::DateTime::from_timestamp_millis(bar.open_time_ms as i64)
                .unwrap_or_default();
            b.push_bind(ts);
            b.push_bind(bar.open_time_ms as i64);
            b.push_bind(bar.close_time_ms as i64);
            b.push_bind(symbol.as_str());
            b.push_bind(timeframe.as_str());
            b.push_bind(sanitize_f64_or_zero(bar.open) as f32);
            b.push_bind(sanitize_f64_or_zero(bar.high) as f32);
            b.push_bind(sanitize_f64_or_zero(bar.low) as f32);
            b.push_bind(sanitize_f64_or_zero(bar.close) as f32);
            b.push_bind(sanitize_f64(bar.volume).map(|v| v as f32));
            b.push_bind(sanitize_f64(bar.turnover).map(|v| v as f32));
            b.push_bind(bar.tick_count as i32);
        }
    });
    qb.push(" ON CONFLICT (symbol, timeframe, ts) DO NOTHING");

    match qb.build().execute(pg).await {
        Ok(r) => {
            pool.record_success();
            debug!(rows = r.rows_affected(), klines = buf.len(), "klines flushed / K 線已刷新");
        }
        Err(e) => {
            let should_fallback = pool.record_failure();
            warn!(error = %e, fallback = should_fallback, "kline flush failed / K 線刷新失敗");
        }
    }
    buf.clear();
}

/// Batch INSERT tickers to market.market_tickers / 批量插入行情到 market.market_tickers
async fn flush_tickers(pool: &DbPool, buf: &mut Vec<MarketDataMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => { buf.clear(); return; }
    };

    let mut qb: QueryBuilder<sqlx::Postgres> = QueryBuilder::new(
        "INSERT INTO market.market_tickers (ts, symbol, last_price, mark_price, index_price, best_bid, best_ask, bid_size, ask_size, volume_24h, turnover_24h, spread_bps, open_interest) "
    );

    qb.push_values(buf.iter(), |mut b, msg| {
        if let MarketDataMsg::TickerSnapshot {
            ts_ms, symbol, last_price, mark_price, index_price,
            best_bid, best_ask, bid_size, ask_size,
            volume_24h, turnover_24h, spread_bps, open_interest,
        } = msg {
            let ts = chrono::DateTime::from_timestamp_millis(*ts_ms as i64)
                .unwrap_or_default();
            b.push_bind(ts);
            b.push_bind(symbol.as_str());
            b.push_bind(sanitize_f64(*last_price).map(|v| v as f32));
            b.push_bind(sanitize_f64(*mark_price).map(|v| v as f32));
            b.push_bind(sanitize_f64(*index_price).map(|v| v as f32));
            b.push_bind(sanitize_f64(*best_bid).map(|v| v as f32));
            b.push_bind(sanitize_f64(*best_ask).map(|v| v as f32));
            b.push_bind(sanitize_f64(*bid_size).map(|v| v as f32));
            b.push_bind(sanitize_f64(*ask_size).map(|v| v as f32));
            b.push_bind(sanitize_f64(*volume_24h).map(|v| v as f32));
            b.push_bind(sanitize_f64(*turnover_24h).map(|v| v as f32));
            b.push_bind(sanitize_f64(*spread_bps).map(|v| v as f32));
            b.push_bind(sanitize_f64(*open_interest).map(|v| v as f32));
        }
    });
    qb.push(" ON CONFLICT (symbol, ts) DO NOTHING");

    match qb.build().execute(pg).await {
        Ok(r) => {
            pool.record_success();
            debug!(rows = r.rows_affected(), tickers = buf.len(), "tickers flushed / 行情已刷新");
        }
        Err(e) => {
            let should_fallback = pool.record_failure();
            warn!(error = %e, fallback = should_fallback, "ticker flush failed / 行情刷新失敗");
        }
    }
    buf.clear();
}

/// Flush other market data types (funding, OI, LSR, regime, liquidation, etc.)
/// G2 will expand this with per-type flush functions.
/// 刷新其他市場數據類型。G2 將擴展為各類型的刷新函數。
async fn flush_other(pool: &DbPool, buf: &mut Vec<MarketDataMsg>) {
    // G2 placeholder: will be implemented in tasks 1-07, 1-08, 1-09
    // G2 佔位：將在任務 1-07, 1-08, 1-09 中實現
    if !buf.is_empty() {
        debug!(count = buf.len(), "other market msgs deferred to G2 / 其他市場消息延後到 G2");
    }
    buf.clear();
}

#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::klines::KlineBar;

    fn make_kline_msg(symbol: &str, tf: &str) -> MarketDataMsg {
        MarketDataMsg::KlineClose {
            symbol: symbol.into(),
            timeframe: tf.into(),
            bar: KlineBar {
                open_time_ms: 1700000000000,
                close_time_ms: 1700000060000,
                open: 50000.0,
                high: 50100.0,
                low: 49900.0,
                close: 50050.0,
                volume: 100.0,
                turnover: 5000000.0,
                tick_count: 50,
                is_closed: true,
            },
        }
    }

    fn make_ticker_msg(symbol: &str) -> MarketDataMsg {
        MarketDataMsg::TickerSnapshot {
            ts_ms: 1700000000000,
            symbol: symbol.into(),
            last_price: 50000.0,
            mark_price: 50001.0,
            index_price: 49999.0,
            best_bid: 49999.5,
            best_ask: 50000.5,
            bid_size: 10.0,
            ask_size: 12.0,
            volume_24h: 1e9,
            turnover_24h: 5e13,
            spread_bps: 2.0,
            open_interest: 1e6,
        }
    }

    #[test]
    fn test_msg_routing() {
        let kline = make_kline_msg("BTCUSDT", "1m");
        let ticker = make_ticker_msg("BTCUSDT");
        let funding = MarketDataMsg::FundingRate {
            ts_ms: 0, symbol: "BTC".into(), funding_rate: 0.01, funding_rate_daily: 0.03,
        };
        assert!(matches!(kline, MarketDataMsg::KlineClose { .. }));
        assert!(matches!(ticker, MarketDataMsg::TickerSnapshot { .. }));
        assert!(!matches!(funding, MarketDataMsg::KlineClose { .. }));
        assert!(!matches!(funding, MarketDataMsg::TickerSnapshot { .. }));
    }

    #[test]
    fn test_batch_accumulation() {
        let mut kline_buf = Vec::new();
        let mut ticker_buf = Vec::new();
        let mut other_buf = Vec::new();

        let msgs = vec![
            make_kline_msg("BTCUSDT", "1m"),
            make_ticker_msg("ETHUSDT"),
            make_kline_msg("SOLUSDT", "5m"),
            MarketDataMsg::FundingRate { ts_ms: 0, symbol: "X".into(), funding_rate: 0.0, funding_rate_daily: 0.0 },
        ];

        for m in msgs {
            match &m {
                MarketDataMsg::KlineClose { .. } => kline_buf.push(m),
                MarketDataMsg::TickerSnapshot { .. } => ticker_buf.push(m),
                _ => other_buf.push(m),
            }
        }

        assert_eq!(kline_buf.len(), 2);
        assert_eq!(ticker_buf.len(), 1);
        assert_eq!(other_buf.len(), 1);
    }

    #[test]
    fn test_nan_sanitization_in_kline() {
        let msg = MarketDataMsg::KlineClose {
            symbol: "TEST".into(),
            timeframe: "1m".into(),
            bar: KlineBar {
                open_time_ms: 0,
                close_time_ms: 60000,
                open: f64::NAN,
                high: f64::INFINITY,
                low: 100.0,
                close: 101.0,
                volume: f64::NEG_INFINITY,
                turnover: 0.0,
                tick_count: 1,
                is_closed: true,
            },
        };
        if let MarketDataMsg::KlineClose { bar, .. } = &msg {
            assert_eq!(sanitize_f64_or_zero(bar.open), 0.0);
            assert_eq!(sanitize_f64_or_zero(bar.high), 0.0);
            assert_eq!(sanitize_f64(bar.volume), None);
        }
    }
}
