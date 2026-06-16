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
use super::pool::{pool_acquire_with_stats, DbPool};
use super::pool_wait_stats::PoolWaitStats;
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
/// 65535 上限僅 535 參數；V-migration 加一欄就靜默越界。FND-4 P3 接上 funding_rate
/// 後為 14 欄，顯式壓到 4000 行，仍保留 9_535 參數裕度。
const TICKER_CHUNK_MAX_ROWS: usize = 4000;

// Column counts per table — consumed by batch_insert helper to derive chunk size.
// 各表欄位數 — 交由 batch_insert helper 推導分塊大小。
const KLINE_COLS: usize = 12;
const TICKER_COLS: usize = 14;
const OB_COLS: usize = 8;
const TRADE_AGG_COLS: usize = 10;
const LIQUIDATION_COLS: usize = 5;
pub(crate) const LIQUIDATION_CONFLICT_TARGET: &str = "(symbol, ts, side, qty, price)";
const MIN_LIQUIDATION_TS_MS: u64 = 946_684_800_000; // 2000-01-01T00:00:00Z
const MAX_LIQUIDATION_TS_MS: u64 = 4_102_444_800_000; // 2100-01-01T00:00:00Z
const FUNDING_COLS: usize = 4;
const OI_COLS: usize = 4;
const LSR_COLS: usize = 5;
const REGIME_SNAP_COLS: usize = 5;
const REGIME_TRANS_COLS: usize = 6;
// Sub-second 前向錄製：market.trades 5 欄 / market.ob_top 6 欄。
// 5/6 欄經 chunk_rows_for_columns clamp 到 MAX_CHUNK_ROWS=10000，遠低 65535 參數上限。
const RAW_TRADE_COLS: usize = 5;
const OB_TOP_COLS: usize = 6;

#[derive(Debug, Clone, Copy)]
struct LiquidationRow<'a> {
    ts: chrono::DateTime<chrono::Utc>,
    symbol: &'a str,
    side: &'a str,
    qty: f32,
    price: f32,
}

fn valid_liquidation_real(value: f64) -> Option<f32> {
    (value.is_finite() && value > 0.0 && value <= f32::MAX as f64).then_some(value as f32)
}

fn validated_liquidation_row(msg: &MarketDataMsg) -> Option<LiquidationRow<'_>> {
    let MarketDataMsg::Liquidation {
        ts_ms,
        symbol,
        side,
        qty,
        price,
    } = msg
    else {
        return None;
    };
    if !matches!(side.as_str(), "Buy" | "Sell") {
        return None;
    }
    if !(MIN_LIQUIDATION_TS_MS..=MAX_LIQUIDATION_TS_MS).contains(ts_ms) {
        return None;
    }
    let ts = chrono::DateTime::from_timestamp_millis(*ts_ms as i64)?;
    Some(LiquidationRow {
        ts,
        symbol: symbol.as_str(),
        side: side.as_str(),
        qty: valid_liquidation_real(*qty)?,
        price: valid_liquidation_real(*price)?,
    })
}

fn sanitize_optional_f32(value: Option<f64>) -> Option<f32> {
    value.and_then(sanitize_f64).map(|v| v as f32)
}

/// Run the market data writer task: receive from channel, batch flush to PG.
/// 運行市場數據寫入器任務：從通道接收，批量刷新到 PG。
///
/// Sprint 5+ Track C round 2 caller wire-up：可選 `pool_wait_stats` Arc 注入
/// 後，每次 flush_timer tick 前透過 `pool_acquire_with_stats` 拿一條短暫的
/// connection 計時樣本，反映當下 pool acquire backlog；釋放後再走既有 flush
/// 路徑（`execute(pg)` 內部各自 acquire 不重複計時）。
/// None = 既有 caller / test 不接 health pipeline 走 0 行為退化（per spec §3.4
/// `caller 端 opt-in 切換即可`）。
pub async fn run_market_writer(
    mut rx: mpsc::Receiver<MarketDataMsg>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
    pool_wait_stats: Option<Arc<PoolWaitStats>>,
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
                    // Sprint 5+ Track C round 2：在實際 flush 之前先拿一條短暫
                    // connection 計時樣本，反映 pool acquire wait 真實 latency。
                    // 為什麼這裡 sample：buf 非空 = 即將進行 SQL execute；此時
                    // acquire 與 flush 路徑面對的 backlog 一致，p95 反映實際生產
                    // 路徑的 contention（per `feedback_no_dead_params` 真實樣本）。
                    if let Some(ref pw_stats) = pool_wait_stats {
                        if let Some(pg_ref) = pool.get() {
                            if !kline_buf.is_empty() || !ticker_buf.is_empty() || !other_buf.is_empty() {
                                // record_wait_ms 由 pool_acquire_with_stats 內部處理；
                                // 樣本拿到後 drop 立即還 connection（非長租）。
                                let _ = pool_acquire_with_stats(pg_ref, pw_stats).await;
                            }
                        }
                    }
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
/// Latent-bug fix (FA-2 Risk #1): ticker now has 14 columns; without an override,
/// natural chunk size would still sit near the 65535-param cap. The explicit
/// 4000 cap pins the per-batch param count to 56000, leaving 9_535 headroom.
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
                "INSERT INTO market.market_tickers (ts, symbol, last_price, mark_price, index_price, funding_rate, best_bid, best_ask, bid_size, ask_size, volume_24h, turnover_24h, spread_bps, open_interest) "
            );
            qb.push_values(chunk.iter(), |mut b, msg| {
                if let MarketDataMsg::TickerSnapshot {
                    ts_ms,
                    symbol,
                    last_price,
                    mark_price,
                    index_price,
                    funding_rate,
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
                    b.push_bind(sanitize_optional_f32(*mark_price));
                    b.push_bind(sanitize_optional_f32(*index_price));
                    b.push_bind(sanitize_optional_f32(*funding_rate));
                    b.push_bind(sanitize_f64(*best_bid).map(|v| v as f32));
                    b.push_bind(sanitize_f64(*best_ask).map(|v| v as f32));
                    b.push_bind(sanitize_f64(*bid_size).map(|v| v as f32));
                    b.push_bind(sanitize_f64(*ask_size).map(|v| v as f32));
                    b.push_bind(sanitize_f64(*volume_24h).map(|v| v as f32));
                    b.push_bind(sanitize_f64(*turnover_24h).map(|v| v as f32));
                    b.push_bind(sanitize_f64(*spread_bps).map(|v| v as f32));
                    b.push_bind(sanitize_optional_f32(*open_interest));
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
    let mut liquidations = Vec::new();
    let mut funding = Vec::new();
    let mut oi = Vec::new();
    let mut lsr = Vec::new();
    let mut regime_snap = Vec::new();
    let mut regime_trans = Vec::new();
    let mut raw_trades = Vec::new();
    let mut ob_top = Vec::new();

    for msg in buf.drain(..) {
        match msg {
            m @ MarketDataMsg::ObSnapshot { .. } => ob.push(m),
            m @ MarketDataMsg::TradeAgg1m { .. } => trades.push(m),
            m @ MarketDataMsg::Liquidation { .. } => liquidations.push(m),
            m @ MarketDataMsg::FundingRate { .. } => funding.push(m),
            m @ MarketDataMsg::OpenInterest { .. } => oi.push(m),
            m @ MarketDataMsg::LongShortRatio { .. } => lsr.push(m),
            m @ MarketDataMsg::RegimeSnapshot { .. } => regime_snap.push(m),
            m @ MarketDataMsg::RegimeTransition { .. } => regime_trans.push(m),
            m @ MarketDataMsg::RawTrade { .. } => raw_trades.push(m),
            m @ MarketDataMsg::ObTop { .. } => ob_top.push(m),
            _ => {} // kline/ticker handled by dedicated flushers
        }
    }

    if !ob.is_empty() {
        flush_ob_snapshots(pg, pool, &ob).await;
    }
    if !trades.is_empty() {
        flush_trade_agg(pg, pool, &trades).await;
    }
    if !liquidations.is_empty() {
        flush_liquidations(pg, pool, &liquidations).await;
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
    if !raw_trades.is_empty() {
        flush_raw_trades(pg, pool, &raw_trades).await;
    }
    if !ob_top.is_empty() {
        flush_ob_top(pg, pool, &ob_top).await;
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

// ── Sub-second 前向錄製：market.trades + market.ob_top ──

#[derive(Debug, Clone, Copy)]
struct RawTradeRow<'a> {
    ts: chrono::DateTime<chrono::Utc>,
    symbol: &'a str,
    side: &'a str,
    price: f32,
    qty: f32,
}

/// 校驗一筆 RawTrade → RawTradeRow。
///
/// 為什麼 fail-soft 丟整筆：market.trades 全欄 REAL NOT NULL，任一欄非有限值若以
/// NULL 綁定會違反 NOT NULL 並使整個 batch abort（牽連無辜行）；故非法 row 直接丟棄。
fn validated_raw_trade_row(msg: &MarketDataMsg) -> Option<RawTradeRow<'_>> {
    let MarketDataMsg::RawTrade {
        ts_ms,
        symbol,
        side,
        price,
        qty,
    } = msg
    else {
        return None;
    };
    let ts = chrono::DateTime::from_timestamp_millis(*ts_ms as i64)?;
    let price = sanitize_f64(*price)? as f32;
    let qty = sanitize_f64(*qty)? as f32;
    Some(RawTradeRow {
        ts,
        symbol: symbol.as_str(),
        side: side.as_str(),
        price,
        qty,
    })
}

/// Batch INSERT 逐筆成交到 market.trades（5 欄，5-tuple PK ON CONFLICT DO NOTHING）。
/// mirror flush_liquidations：先 validate-collect 再 chunk insert。
async fn flush_raw_trades(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    let rows: Vec<_> = buf.iter().filter_map(validated_raw_trade_row).collect();
    if rows.is_empty() {
        return;
    }
    batch_insert_chunked(
        pg,
        pool,
        "market.trades",
        rows.as_slice(),
        RAW_TRADE_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> =
                QueryBuilder::new("INSERT INTO market.trades (ts, symbol, side, price, qty) ");
            qb.push_values(chunk, |mut b, row| {
                b.push_bind(row.ts);
                b.push_bind(row.symbol);
                b.push_bind(row.side);
                b.push_bind(row.price);
                b.push_bind(row.qty);
            });
            qb.push(" ON CONFLICT (symbol, ts, side, price, qty) DO NOTHING");
            qb
        },
    )
    .await;
}

#[derive(Debug, Clone, Copy)]
struct ObTopRow<'a> {
    ts: chrono::DateTime<chrono::Utc>,
    symbol: &'a str,
    best_bid: f32,
    bid_size: f32,
    best_ask: f32,
    ask_size: f32,
}

/// 校驗一筆 ObTop → ObTopRow。market.ob_top 全欄 REAL NOT NULL，同 raw trade
/// fail-soft：任一欄非有限值丟整筆。
fn validated_ob_top_row(msg: &MarketDataMsg) -> Option<ObTopRow<'_>> {
    let MarketDataMsg::ObTop {
        ts_ms,
        symbol,
        best_bid,
        bid_size,
        best_ask,
        ask_size,
    } = msg
    else {
        return None;
    };
    let ts = chrono::DateTime::from_timestamp_millis(*ts_ms as i64)?;
    Some(ObTopRow {
        ts,
        symbol: symbol.as_str(),
        best_bid: sanitize_f64(*best_bid)? as f32,
        bid_size: sanitize_f64(*bid_size)? as f32,
        best_ask: sanitize_f64(*best_ask)? as f32,
        ask_size: sanitize_f64(*ask_size)? as f32,
    })
}

/// Batch INSERT L1 top-of-book 取樣到 market.ob_top（6 欄，2-tuple PK ON CONFLICT DO NOTHING）。
async fn flush_ob_top(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    let rows: Vec<_> = buf.iter().filter_map(validated_ob_top_row).collect();
    if rows.is_empty() {
        return;
    }
    batch_insert_chunked(pg, pool, "market.ob_top", rows.as_slice(), OB_TOP_COLS, |chunk| {
        let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
            "INSERT INTO market.ob_top (ts, symbol, best_bid, bid_size, best_ask, ask_size) ",
        );
        qb.push_values(chunk, |mut b, row| {
            b.push_bind(row.ts);
            b.push_bind(row.symbol);
            b.push_bind(row.best_bid);
            b.push_bind(row.bid_size);
            b.push_bind(row.best_ask);
            b.push_bind(row.ask_size);
        });
        qb.push(" ON CONFLICT (symbol, ts) DO NOTHING");
        qb
    })
    .await;
}

// ── 1-08: liquidation + funding + OI + LSR ──

async fn flush_liquidations(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    let rows: Vec<_> = buf.iter().filter_map(validated_liquidation_row).collect();
    if rows.is_empty() {
        return;
    }
    batch_insert_chunked(
        pg,
        pool,
        "market.liquidations",
        rows.as_slice(),
        LIQUIDATION_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO market.liquidations (ts, symbol, side, qty, price) ",
            );
            qb.push_values(chunk, |mut b, row| {
                b.push_bind(row.ts);
                b.push_bind(row.symbol);
                b.push_bind(row.side);
                b.push_bind(row.qty);
                b.push_bind(row.price);
            });
            qb.push(" ON CONFLICT ");
            qb.push(LIQUIDATION_CONFLICT_TARGET);
            qb.push(" DO NOTHING");
            qb
        },
    )
    .await;
}

async fn flush_funding(pg: &sqlx::PgPool, pool: &DbPool, buf: &[MarketDataMsg]) {
    batch_insert_chunked(
        pg,
        pool,
        "market.funding_rates",
        buf,
        FUNDING_COLS,
        |chunk| {
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
        },
    )
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
    batch_insert_chunked(
        pg,
        pool,
        "market.long_short_ratio",
        buf,
        LSR_COLS,
        |chunk| {
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
        },
    )
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
            mark_price: Some(50001.0),
            index_price: Some(49999.0),
            funding_rate: Some(-0.0001),
            best_bid: 49999.5,
            best_ask: 50000.5,
            bid_size: 10.0,
            ask_size: 12.0,
            volume_24h: 1e9,
            turnover_24h: 5e13,
            spread_bps: 2.0,
            open_interest: Some(1e6),
        }
    }

    fn make_liquidation_msg() -> MarketDataMsg {
        MarketDataMsg::Liquidation {
            ts_ms: 1_700_000_000_000,
            symbol: "BTCUSDT".into(),
            side: "Buy".into(),
            qty: 0.5,
            price: 64_000.0,
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
    fn test_liquidation_msg_and_conflict_target_contract() {
        let msg = make_liquidation_msg();
        assert!(matches!(msg, MarketDataMsg::Liquidation { .. }));
        assert_eq!(
            LIQUIDATION_CONFLICT_TARGET,
            "(symbol, ts, side, qty, price)"
        );
    }

    #[test]
    fn test_validated_liquidation_row_accepts_clean_payload() {
        let msg = make_liquidation_msg();
        let row = validated_liquidation_row(&msg).unwrap();
        assert_eq!(row.symbol, "BTCUSDT");
        assert_eq!(row.side, "Buy");
        assert!((row.qty - 0.5).abs() < f32::EPSILON);
        assert!((row.price - 64_000.0).abs() < f32::EPSILON);
    }

    #[test]
    fn test_validated_liquidation_row_rejects_invalid_ts_side_qty_price() {
        let mut msg = make_liquidation_msg();
        if let MarketDataMsg::Liquidation { ts_ms, .. } = &mut msg {
            *ts_ms = 0;
        }
        assert!(validated_liquidation_row(&msg).is_none());

        let mut msg = make_liquidation_msg();
        if let MarketDataMsg::Liquidation { ts_ms, .. } = &mut msg {
            *ts_ms = 99_999_999_999_999;
        }
        assert!(validated_liquidation_row(&msg).is_none());

        let mut msg = make_liquidation_msg();
        if let MarketDataMsg::Liquidation { side, .. } = &mut msg {
            *side = "Unknown".into();
        }
        assert!(validated_liquidation_row(&msg).is_none());

        for bad_qty in [0.0, f64::NAN] {
            let mut msg = make_liquidation_msg();
            if let MarketDataMsg::Liquidation { qty, .. } = &mut msg {
                *qty = bad_qty;
            }
            assert!(validated_liquidation_row(&msg).is_none());
        }

        for bad_price in [0.0, f64::NAN] {
            let mut msg = make_liquidation_msg();
            if let MarketDataMsg::Liquidation { price, .. } = &mut msg {
                *price = bad_price;
            }
            assert!(validated_liquidation_row(&msg).is_none());
        }
    }

    // ── Sub-second 前向錄製：RawTrade / ObTop 測試 ──

    fn make_raw_trade_msg() -> MarketDataMsg {
        MarketDataMsg::RawTrade {
            ts_ms: 1_700_000_000_000,
            symbol: "BTCUSDT".into(),
            side: "Buy".into(),
            price: 64_000.0,
            qty: 0.5,
        }
    }

    fn make_ob_top_msg() -> MarketDataMsg {
        MarketDataMsg::ObTop {
            ts_ms: 1_700_000_000_000,
            symbol: "BTCUSDT".into(),
            best_bid: 63_999.5,
            bid_size: 10.0,
            best_ask: 64_000.5,
            ask_size: 12.0,
        }
    }

    #[test]
    fn test_recorder_col_counts_are_param_cap_safe() {
        // 5/6 欄經 chunk 數學夾到 MAX_CHUNK_ROWS=10000，距 65535 巨大裕度。
        assert_eq!(RAW_TRADE_COLS, 5);
        assert_eq!(OB_TOP_COLS, 6);
        let raw_chunk = crate::database::batch_insert::chunk_rows_for_columns(RAW_TRADE_COLS);
        let ob_chunk = crate::database::batch_insert::chunk_rows_for_columns(OB_TOP_COLS);
        assert_eq!(raw_chunk, 10_000); // 65535/5=13107 clamp 10000
        assert_eq!(ob_chunk, 10_000); // 65535/6=10922 clamp 10000
        assert!(raw_chunk * RAW_TRADE_COLS <= 65_535);
        assert!(ob_chunk * OB_TOP_COLS <= 65_535);
    }

    #[test]
    fn test_validated_raw_trade_row_accepts_clean_payload() {
        let msg = make_raw_trade_msg();
        let row = validated_raw_trade_row(&msg).unwrap();
        assert_eq!(row.symbol, "BTCUSDT");
        assert_eq!(row.side, "Buy");
        assert!((row.price - 64_000.0).abs() < f32::EPSILON);
        assert!((row.qty - 0.5).abs() < f32::EPSILON);
    }

    #[test]
    fn test_validated_raw_trade_row_rejects_non_finite() {
        for bad in [f64::NAN, f64::INFINITY, f64::NEG_INFINITY] {
            let mut msg = make_raw_trade_msg();
            if let MarketDataMsg::RawTrade { price, .. } = &mut msg {
                *price = bad;
            }
            assert!(validated_raw_trade_row(&msg).is_none());
            let mut msg = make_raw_trade_msg();
            if let MarketDataMsg::RawTrade { qty, .. } = &mut msg {
                *qty = bad;
            }
            assert!(validated_raw_trade_row(&msg).is_none());
        }
    }

    #[test]
    fn test_validated_ob_top_row_accepts_and_rejects() {
        let clean = make_ob_top_msg();
        let row = validated_ob_top_row(&clean).unwrap();
        assert_eq!(row.symbol, "BTCUSDT");
        assert!((row.best_bid - 63_999.5).abs() < 1.0);
        // 任一欄非有限值 → 整筆丟棄（NOT NULL fail-soft）。
        for bad in [f64::NAN, f64::INFINITY] {
            let mut msg = make_ob_top_msg();
            if let MarketDataMsg::ObTop { ask_size, .. } = &mut msg {
                *ask_size = bad;
            }
            assert!(validated_ob_top_row(&msg).is_none());
        }
    }

    #[test]
    fn test_recorder_variants_serialize_for_jsonl_fallback() {
        // PA §3.2：JSONL fallback 經 serde::Serialize 自動覆蓋；驗兩變體可序列化。
        let raw = serde_json::to_string(&make_raw_trade_msg()).expect("RawTrade serializes");
        assert!(raw.contains("RawTrade") && raw.contains("BTCUSDT"));
        let ob = serde_json::to_string(&make_ob_top_msg()).expect("ObTop serializes");
        assert!(ob.contains("ObTop") && ob.contains("best_bid"));
    }

    #[test]
    fn test_recorder_variants_route_to_other_buf() {
        // RawTrade/ObTop 不是 kline/ticker，應路由進 other_buf（flush_other 處理）。
        for m in [make_raw_trade_msg(), make_ob_top_msg()] {
            assert!(!matches!(m, MarketDataMsg::KlineClose { .. }));
            assert!(!matches!(m, MarketDataMsg::TickerSnapshot { .. }));
        }
        assert!(matches!(make_raw_trade_msg(), MarketDataMsg::RawTrade { .. }));
        assert!(matches!(make_ob_top_msg(), MarketDataMsg::ObTop { .. }));
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
    fn test_ticker_forward_evidence_fields_are_nullable() {
        let msg = make_ticker_msg("BTCUSDT");
        if let MarketDataMsg::TickerSnapshot {
            mark_price,
            index_price,
            funding_rate,
            open_interest,
            ..
        } = msg
        {
            assert_eq!(mark_price, Some(50001.0));
            assert_eq!(index_price, Some(49999.0));
            assert_eq!(funding_rate, Some(-0.0001));
            assert_eq!(open_interest, Some(1e6));
        } else {
            panic!("expected ticker snapshot");
        }
    }

    #[test]
    fn test_sanitize_optional_f32_keeps_zero_and_negative_funding_semantics() {
        assert_eq!(sanitize_optional_f32(Some(0.0)), Some(0.0));
        assert_eq!(sanitize_optional_f32(Some(-0.0001)), Some(-0.0001_f32));
        assert_eq!(sanitize_optional_f32(None), None);
        assert_eq!(sanitize_optional_f32(Some(f64::NAN)), None);
        assert_eq!(sanitize_optional_f32(Some(f64::INFINITY)), None);
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
