//! Market data writer — async consumer for batch INSERT to 10 market.* tables.
//! 市場數據寫入器 — 批量 INSERT 到 10 個 market.* 表的異步消費者。
//!
//! MODULE_NOTE (EN): Receives MarketDataMsg from bounded channel, accumulates in
//!   memory buffers, flushes every batch_flush_interval_ms using QueryBuilder::push_values().
//!   On 3 consecutive PG failures, switches to JSONL fallback. Non-blocking to tick loop.
//! MODULE_NOTE (中): 從有界通道接收 MarketDataMsg，在內存緩衝區累積，
//!   每 batch_flush_interval_ms 使用 QueryBuilder::push_values() 刷新。
//!   連續 3 次 PG 失敗後切換到 JSONL 回退。不阻塞 tick 循環。

use super::batch_insert::{batch_insert_chunked, batch_insert_chunked_with_override};
use super::fallback::FallbackWriter;
use super::pool::DbPool;
use super::{sanitize_f64, sanitize_f64_or_zero, MarketDataMsg};
use sqlx::{Postgres, QueryBuilder};
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

/// Latent-bug fix (FA-2 Risk #1): ticker buffer had 13 cols × 5000 rows = 65000
/// params — 535 params below the 65535 PG cap, one V-migration column addition
/// from silently overflowing. Explicit 4000-row cap keeps 13_535 params of
/// headroom for future column additions.
/// 潛在 bug 修復（FA-2 風險 #1）：ticker 原本 13 欄 × 5000 行 = 65000 參數，距
/// 65535 上限僅 535 參數；V-migration 加一欄就靜默越界。顯式壓到 4000 行，保留
/// 13_535 參數裕度。
const TICKER_CHUNK_MAX_ROWS: usize = 4000;

// Column counts per table — consumed by batch_insert helper to derive chunk size.
// 各表欄位數 — 交由 batch_insert helper 推導分塊大小。
const KLINE_COLS: usize = 12;
const TICKER_COLS: usize = 13;
const OB_COLS: usize = 8;
const TRADE_AGG_COLS: usize = 10;
const FUNDING_COLS: usize = 4;
const OI_COLS: usize = 4;
const LSR_COLS: usize = 5;
const REGIME_SNAP_COLS: usize = 5;
const REGIME_TRANS_COLS: usize = 6;

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

    // F-6 fix: JSONL fallback writer for when PG fails 3+ times
    // F-6 修復：PG 失敗 3+ 次時的 JSONL 回退寫入器
    let fallback_dir = PathBuf::from(
        std::env::var("OPENCLAW_DATA_DIR").unwrap_or_else(|_| "/tmp/openclaw".into()),
    )
    .join("fallback");
    let mut fallback = FallbackWriter::new(&fallback_dir);
    let mut in_fallback_mode = false;

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
                if pool.is_available() && !in_fallback_mode {
                    flush_all(&pool, &mut kline_buf, &mut ticker_buf, &mut other_buf).await;
                    // F-6: Switch to fallback after 3 consecutive PG failures
                    if pool.failure_count() >= 3 {
                        in_fallback_mode = true;
                        warn!("switching to JSONL fallback / 切換到 JSONL 回退");
                    }
                } else {
                    // Fallback mode: write to JSONL file
                    write_to_fallback(&mut fallback, &mut kline_buf, &mut ticker_buf, &mut other_buf);
                    // Try to recover on each cycle
                    if pool.is_available() && pool.health_check().await {
                        in_fallback_mode = false;
                        pool.record_success();
                        info!("PG recovered, exiting fallback / PG 已恢復");
                    }
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
                    None => break,
                }
            }
        }
    }

    // Final flush
    if pool.is_available() && !in_fallback_mode {
        flush_all(&pool, &mut kline_buf, &mut ticker_buf, &mut other_buf).await;
    } else {
        write_to_fallback(
            &mut fallback,
            &mut kline_buf,
            &mut ticker_buf,
            &mut other_buf,
        );
    }
    if fallback.total_lines() > 0 {
        info!(
            lines = fallback.total_lines(),
            "fallback lines written / 回退行已寫入"
        );
    }
    info!("market_writer stopped / 市場數據寫入器已停止");
}

/// F-6: Write buffered messages to JSONL fallback file.
/// F-6：將緩衝消息寫入 JSONL 回退文件。
fn write_to_fallback(
    fallback: &mut FallbackWriter,
    kline_buf: &mut Vec<MarketDataMsg>,
    ticker_buf: &mut Vec<MarketDataMsg>,
    other_buf: &mut Vec<MarketDataMsg>,
) {
    for buf in [kline_buf as &mut Vec<_>, ticker_buf, other_buf] {
        for msg in buf.drain(..) {
            if let Ok(json) = serde_json::to_string(&msg) {
                fallback.write_line(&json);
            }
        }
    }
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
        None => {
            buf.clear();
            return;
        }
    };
    batch_insert_chunked(pg, pool, "market.klines", buf.as_slice(), KLINE_COLS, |chunk| {
        let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
            "INSERT INTO market.klines (ts, open_ts_ms, close_ts_ms, symbol, timeframe, open, high, low, close, volume, turnover, tick_count) "
        );
        qb.push_values(chunk.iter(), |mut b, msg| {
            if let MarketDataMsg::KlineClose {
                symbol,
                timeframe,
                bar,
            } = msg
            {
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
        qb
    })
    .await;
    buf.clear();
}

/// Batch INSERT tickers to market.market_tickers with explicit 4000-row chunk cap.
/// 批量插入行情到 market.market_tickers，顯式套用 4000 行分塊上限。
///
/// Latent-bug fix (FA-2 Risk #1): ticker has 13 columns; without an override,
/// natural chunk size would be 5041 rows (= 65533 params). A single V-migration
/// column addition could push us over 65535 silently. The explicit 4000 cap
/// pins the per-batch param count to 52000, leaving 13_535 headroom.
async fn flush_tickers(pool: &DbPool, buf: &mut Vec<MarketDataMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            buf.clear();
            return;
        }
    };
    batch_insert_chunked_with_override(
        pg,
        pool,
        "market.market_tickers",
        buf.as_slice(),
        TICKER_COLS,
        TICKER_CHUNK_MAX_ROWS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO market.market_tickers (ts, symbol, last_price, mark_price, index_price, best_bid, best_ask, bid_size, ask_size, volume_24h, turnover_24h, spread_bps, open_interest) "
            );
            qb.push_values(chunk.iter(), |mut b, msg| {
                if let MarketDataMsg::TickerSnapshot {
                    ts_ms,
                    symbol,
                    last_price,
                    mark_price,
                    index_price,
                    best_bid,
                    best_ask,
                    bid_size,
                    ask_size,
                    volume_24h,
                    turnover_24h,
                    spread_bps,
                    open_interest,
                } = msg
                {
                    let ts = chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default();
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
            qb
        },
    )
    .await;
    buf.clear();
}

/// Flush other market data types — route by variant, batch per type.
/// 刷新其他市場數據類型 — 按變體路由，每類型批量寫入。
async fn flush_other(pool: &DbPool, buf: &mut Vec<MarketDataMsg>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            buf.clear();
            return;
        }
    };

    // Group by type for batch efficiency / 按類型分組以提高批量效率
    let mut ob = Vec::new();
    let mut trades = Vec::new();
    let mut funding = Vec::new();
    let mut oi = Vec::new();
    let mut lsr = Vec::new();
    let mut regime_snap = Vec::new();
    let mut regime_trans = Vec::new();

    for msg in buf.drain(..) {
        match msg {
            m @ MarketDataMsg::ObSnapshot { .. } => ob.push(m),
            m @ MarketDataMsg::TradeAgg1m { .. } => trades.push(m),
            m @ MarketDataMsg::FundingRate { .. } => funding.push(m),
            m @ MarketDataMsg::OpenInterest { .. } => oi.push(m),
            m @ MarketDataMsg::LongShortRatio { .. } => lsr.push(m),
            m @ MarketDataMsg::RegimeSnapshot { .. } => regime_snap.push(m),
            m @ MarketDataMsg::RegimeTransition { .. } => regime_trans.push(m),
            _ => {} // kline/ticker handled by dedicated flushers
        }
    }

    if !ob.is_empty() {
        flush_ob_snapshots(pg, pool, &ob).await;
    }
    if !trades.is_empty() {
        flush_trade_agg(pg, pool, &trades).await;
    }
    if !funding.is_empty() {
        flush_funding(pg, pool, &funding).await;
    }
    if !oi.is_empty() {
        flush_oi(pg, pool, &oi).await;
    }
    if !lsr.is_empty() {
        flush_lsr(pg, pool, &lsr).await;
    }
    if !regime_snap.is_empty() {
        flush_regime_snapshots(pg, pool, &regime_snap).await;
    }
    if !regime_trans.is_empty() {
        flush_regime_transitions(pg, pool, &regime_trans).await;
    }
}

// `exec_batch` helper was removed — its role is now played by
// `batch_insert::batch_insert_chunked` which also enforces the 65535-param guard.
// `exec_batch` 已移除，角色由 `batch_insert_chunked` 擔任且同時強制 65535 參數上限。

// ── 1-07: ob_snapshots + trade_agg_1m ──

async fn flush_ob_snapshots(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    batch_insert_chunked(pg, pool, "market.ob_snapshots", buf, OB_COLS, |chunk| {
        let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
            "INSERT INTO market.ob_snapshots (ts, symbol, imbalance_ratio, weighted_mid, spread_bps, bid_depth_5, ask_depth_5, depth_ratio) "
        );
        qb.push_values(chunk, |mut b, msg| {
            if let MarketDataMsg::ObSnapshot {
                ts_ms,
                symbol,
                imbalance_ratio,
                weighted_mid,
                spread_bps,
                bid_depth_5,
                ask_depth_5,
                depth_ratio,
            } = msg
            {
                b.push_bind(
                    chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                );
                b.push_bind(symbol.as_str());
                b.push_bind(sanitize_f64(*imbalance_ratio).map(|v| v as f32));
                b.push_bind(sanitize_f64(*weighted_mid).map(|v| v as f32));
                b.push_bind(sanitize_f64(*spread_bps).map(|v| v as f32));
                b.push_bind(sanitize_f64(*bid_depth_5).map(|v| v as f32));
                b.push_bind(sanitize_f64(*ask_depth_5).map(|v| v as f32));
                b.push_bind(sanitize_f64(*depth_ratio).map(|v| v as f32));
            }
        });
        qb.push(" ON CONFLICT (symbol, ts) DO NOTHING");
        qb
    })
    .await;
}

async fn flush_trade_agg(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    batch_insert_chunked(pg, pool, "market.trade_agg_1m", buf, TRADE_AGG_COLS, |chunk| {
        let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
            "INSERT INTO market.trade_agg_1m (ts, symbol, buy_volume, sell_volume, buy_count, sell_count, large_buy_count, large_sell_count, vwap, max_single_qty) "
        );
        qb.push_values(chunk, |mut b, msg| {
            if let MarketDataMsg::TradeAgg1m {
                ts_ms,
                symbol,
                buy_volume,
                sell_volume,
                buy_count,
                sell_count,
                large_buy_count,
                large_sell_count,
                vwap,
                max_single_qty,
            } = msg
            {
                b.push_bind(
                    chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                );
                b.push_bind(symbol.as_str());
                b.push_bind(sanitize_f64(*buy_volume).map(|v| v as f32));
                b.push_bind(sanitize_f64(*sell_volume).map(|v| v as f32));
                b.push_bind(*buy_count);
                b.push_bind(*sell_count);
                b.push_bind(*large_buy_count);
                b.push_bind(*large_sell_count);
                b.push_bind(sanitize_f64(*vwap).map(|v| v as f32));
                b.push_bind(sanitize_f64(*max_single_qty).map(|v| v as f32));
            }
        });
        qb.push(" ON CONFLICT (symbol, ts) DO NOTHING");
        qb
    })
    .await;
}

// ── 1-08: funding + OI + LSR ──
// (liquidations writer deleted 2026-04-06: no producer, no consumer, table reserved)

async fn flush_funding(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    batch_insert_chunked(pg, pool, "market.funding_rates", buf, FUNDING_COLS, |chunk| {
        let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
            "INSERT INTO market.funding_rates (ts, symbol, funding_rate, funding_rate_daily) ",
        );
        qb.push_values(chunk, |mut b, msg| {
            if let MarketDataMsg::FundingRate {
                ts_ms,
                symbol,
                funding_rate,
                funding_rate_daily,
            } = msg
            {
                b.push_bind(
                    chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                );
                b.push_bind(symbol.as_str());
                b.push_bind(sanitize_f64_or_zero(*funding_rate) as f32);
                b.push_bind(sanitize_f64(*funding_rate_daily).map(|v| v as f32));
            }
        });
        qb.push(" ON CONFLICT (symbol, ts) DO NOTHING");
        qb
    })
    .await;
}

async fn flush_oi(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    batch_insert_chunked(pg, pool, "market.open_interest", buf, OI_COLS, |chunk| {
        let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
            "INSERT INTO market.open_interest (ts, symbol, open_interest, oi_value) ",
        );
        qb.push_values(chunk, |mut b, msg| {
            if let MarketDataMsg::OpenInterest {
                ts_ms,
                symbol,
                open_interest,
                oi_value,
            } = msg
            {
                b.push_bind(
                    chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                );
                b.push_bind(symbol.as_str());
                b.push_bind(sanitize_f64_or_zero(*open_interest) as f32);
                b.push_bind(sanitize_f64(*oi_value).map(|v| v as f32));
            }
        });
        qb.push(" ON CONFLICT (symbol, ts) DO NOTHING");
        qb
    })
    .await;
}

async fn flush_lsr(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    batch_insert_chunked(pg, pool, "market.long_short_ratio", buf, LSR_COLS, |chunk| {
        let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
            "INSERT INTO market.long_short_ratio (ts, symbol, buy_ratio, sell_ratio, ratio) ",
        );
        qb.push_values(chunk, |mut b, msg| {
            if let MarketDataMsg::LongShortRatio {
                ts_ms,
                symbol,
                buy_ratio,
                sell_ratio,
                ratio,
            } = msg
            {
                b.push_bind(
                    chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                );
                b.push_bind(symbol.as_str());
                b.push_bind(sanitize_f64(*buy_ratio).map(|v| v as f32));
                b.push_bind(sanitize_f64(*sell_ratio).map(|v| v as f32));
                b.push_bind(sanitize_f64(*ratio).map(|v| v as f32));
            }
        });
        qb.push(" ON CONFLICT (symbol, ts) DO NOTHING");
        qb
    })
    .await;
}

// ── 1-09: regime_snapshots + regime_transitions ──

async fn flush_regime_snapshots(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    batch_insert_chunked(
        pg,
        pool,
        "market.regime_snapshots",
        buf,
        REGIME_SNAP_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO market.regime_snapshots (ts, symbol, timeframe, regime, confidence) ",
            );
            qb.push_values(chunk, |mut b, msg| {
                if let MarketDataMsg::RegimeSnapshot {
                    ts_ms,
                    symbol,
                    timeframe,
                    regime,
                    confidence,
                } = msg
                {
                    b.push_bind(
                        chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                    );
                    b.push_bind(symbol.as_str());
                    b.push_bind(timeframe.as_str());
                    b.push_bind(regime.as_str());
                    b.push_bind(sanitize_f64(*confidence).map(|v| v as f32));
                }
            });
            qb.push(" ON CONFLICT (symbol, timeframe, ts) DO NOTHING");
            qb
        },
    )
    .await;
}

async fn flush_regime_transitions(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    batch_insert_chunked(
        pg,
        pool,
        "market.regime_transitions",
        buf,
        REGIME_TRANS_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO market.regime_transitions (ts, symbol, timeframe, from_regime, to_regime, trigger_reason) "
            );
            qb.push_values(chunk, |mut b, msg| {
                if let MarketDataMsg::RegimeTransition {
                    ts_ms,
                    symbol,
                    timeframe,
                    from_regime,
                    to_regime,
                    trigger_reason,
                } = msg
                {
                    b.push_bind(
                        chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default(),
                    );
                    b.push_bind(symbol.as_str());
                    b.push_bind(timeframe.as_str());
                    b.push_bind(from_regime.as_str());
                    b.push_bind(to_regime.as_str());
                    b.push_bind(trigger_reason.as_str());
                }
            });
            qb.push(" ON CONFLICT (symbol, timeframe, ts) DO NOTHING");
            qb
        },
    )
    .await;
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
            ts_ms: 0,
            symbol: "BTC".into(),
            funding_rate: 0.01,
            funding_rate_daily: 0.03,
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
            MarketDataMsg::FundingRate {
                ts_ms: 0,
                symbol: "X".into(),
                funding_rate: 0.0,
                funding_rate_daily: 0.0,
            },
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
