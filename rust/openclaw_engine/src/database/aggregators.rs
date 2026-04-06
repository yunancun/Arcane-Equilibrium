//! 1-minute aggregators for trade and orderbook events.
//! 1 分鐘聚合器（trade 與 orderbook）。
//!
//! MODULE_NOTE (EN): Producer-side aggregation for the previously-idle
//!   `market.trade_agg_1m` and `market.ob_snapshots` writers (Session 11
//!   fix for idle writers #1 and #2). Each aggregator buckets per-symbol
//!   events into UTC-aligned 1-minute windows. When a new event arrives in
//!   a different bucket from the running one, the previous bucket is
//!   flushed to a `MarketDataMsg` and a fresh bucket begins. State is
//!   purely in-memory; aggregators are owned by `TickPipeline`.
//! MODULE_NOTE (中): 為先前空閒的 `market.trade_agg_1m` 與 `market.ob_snapshots`
//!   寫入器補上 producer 端的 1 分鐘聚合（Session 11 修復 idle writers #1/#2）。

use crate::database::MarketDataMsg;
use std::collections::HashMap;

/// Threshold above which a single trade qty is counted as "large".
/// Tunable per-asset later — kept simple for the first wiring.
/// 大單閾值（單筆 qty）— 第一版固定值，後續可按品種調參。
pub const LARGE_TRADE_QTY: f64 = 10.0;

/// Convert an epoch-millisecond timestamp into the start of its 1-minute UTC bucket.
/// 將毫秒時間戳對齊到所在 1 分鐘 UTC 桶起點。
fn bucket_start_ms(ts_ms: u64) -> u64 {
    let minute = 60_000;
    (ts_ms / minute) * minute
}

// ═══════════════════════════════════════════════════════════════════
// Trade aggregator / 成交聚合器
// ═══════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Default)]
struct TradeBucket {
    bucket_start_ms: u64,
    buy_volume: f64,
    sell_volume: f64,
    buy_count: i32,
    sell_count: i32,
    large_buy_count: i32,
    large_sell_count: i32,
    /// Accumulator for VWAP: sum(price * qty)
    px_qty_sum: f64,
    qty_sum: f64,
    max_single_qty: f64,
}

impl TradeBucket {
    fn new(bucket_start_ms: u64) -> Self {
        Self {
            bucket_start_ms,
            ..Default::default()
        }
    }

    fn record(&mut self, side: TradeSide, qty: f64, price: f64) {
        if !qty.is_finite() || qty <= 0.0 || !price.is_finite() || price <= 0.0 {
            return;
        }
        self.px_qty_sum += price * qty;
        self.qty_sum += qty;
        if qty > self.max_single_qty {
            self.max_single_qty = qty;
        }
        match side {
            TradeSide::Buy => {
                self.buy_volume += qty;
                self.buy_count += 1;
                if qty >= LARGE_TRADE_QTY {
                    self.large_buy_count += 1;
                }
            }
            TradeSide::Sell => {
                self.sell_volume += qty;
                self.sell_count += 1;
                if qty >= LARGE_TRADE_QTY {
                    self.large_sell_count += 1;
                }
            }
        }
    }

    fn vwap(&self) -> f64 {
        if self.qty_sum > 0.0 {
            self.px_qty_sum / self.qty_sum
        } else {
            0.0
        }
    }

    fn into_msg(self, symbol: String) -> MarketDataMsg {
        let vwap = self.vwap();
        MarketDataMsg::TradeAgg1m {
            ts_ms: self.bucket_start_ms,
            symbol,
            buy_volume: self.buy_volume,
            sell_volume: self.sell_volume,
            buy_count: self.buy_count,
            sell_count: self.sell_count,
            large_buy_count: self.large_buy_count,
            large_sell_count: self.large_sell_count,
            vwap,
            max_single_qty: self.max_single_qty,
        }
    }

    fn is_empty(&self) -> bool {
        self.buy_count == 0 && self.sell_count == 0
    }
}

/// Trade side as parsed from the WS topic.
/// 成交方向。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TradeSide {
    Buy,
    Sell,
}

impl TradeSide {
    pub fn parse(s: &str) -> Option<Self> {
        match s {
            "Buy" | "buy" | "BUY" => Some(TradeSide::Buy),
            "Sell" | "sell" | "SELL" => Some(TradeSide::Sell),
            _ => None,
        }
    }
}

/// Per-symbol 1-minute trade aggregator. Returns a flushed `MarketDataMsg`
/// whenever a new tick crosses the bucket boundary.
/// 按交易對的 1 分鐘成交聚合器，跨桶時返回前一桶的 flush。
#[derive(Debug, Default)]
pub struct TradeAggregator {
    buckets: HashMap<String, TradeBucket>,
}

impl TradeAggregator {
    pub fn new() -> Self {
        Self::default()
    }

    /// Record a trade. If the trade falls into a new bucket relative to the
    /// running one, the previous bucket is returned for flushing.
    /// 記錄一筆成交，若跨越分鐘邊界則返回上一桶用於落盤。
    pub fn record(
        &mut self,
        symbol: &str,
        side: TradeSide,
        qty: f64,
        price: f64,
        ts_ms: u64,
    ) -> Option<MarketDataMsg> {
        let bucket_ts = bucket_start_ms(ts_ms);
        let mut flushed = None;
        let entry = self
            .buckets
            .entry(symbol.to_string())
            .or_insert_with(|| TradeBucket::new(bucket_ts));
        if entry.bucket_start_ms != bucket_ts {
            // Flush the previous bucket and start a fresh one.
            // 落盤上一桶，開新桶。
            let prev = std::mem::replace(entry, TradeBucket::new(bucket_ts));
            if !prev.is_empty() {
                flushed = Some(prev.into_msg(symbol.to_string()));
            }
        }
        entry.record(side, qty, price);
        flushed
    }

    /// Flush all running buckets (e.g. on shutdown).
    /// 落盤所有運行中的桶。
    pub fn drain(&mut self) -> Vec<MarketDataMsg> {
        let mut out = Vec::new();
        let snapshot: Vec<(String, TradeBucket)> = self.buckets.drain().collect();
        for (sym, b) in snapshot {
            if !b.is_empty() {
                out.push(b.into_msg(sym));
            }
        }
        out
    }

    pub fn len(&self) -> usize {
        self.buckets.len()
    }
}

// ═══════════════════════════════════════════════════════════════════
// Orderbook aggregator / 訂單簿聚合器
// ═══════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Default)]
struct ObBucket {
    bucket_start_ms: u64,
    /// Last computed snapshot (we want the most recent OB state per minute,
    /// not an average — averaging order-book depths is meaningless).
    /// 桶內最新一筆 OB 狀態（深度不可平均）。
    imbalance_ratio: f64,
    weighted_mid: f64,
    spread_bps: f64,
    bid_depth_5: f64,
    ask_depth_5: f64,
    depth_ratio: f64,
    has_data: bool,
}

impl ObBucket {
    fn new(bucket_start_ms: u64) -> Self {
        Self {
            bucket_start_ms,
            ..Default::default()
        }
    }

    fn record(&mut self, bids: &[(f64, f64)], asks: &[(f64, f64)]) {
        if bids.is_empty() || asks.is_empty() {
            return;
        }
        let bid_depth_5: f64 = bids.iter().take(5).map(|(_, q)| q).sum();
        let ask_depth_5: f64 = asks.iter().take(5).map(|(_, q)| q).sum();
        if bid_depth_5 <= 0.0 || ask_depth_5 <= 0.0 {
            return;
        }
        let total = bid_depth_5 + ask_depth_5;
        let imbalance_ratio = (bid_depth_5 - ask_depth_5) / total;
        let weighted_mid = (bids[0].0 * ask_depth_5 + asks[0].0 * bid_depth_5) / total;
        let mid = (bids[0].0 + asks[0].0) * 0.5;
        let spread_bps = if mid > 0.0 {
            (asks[0].0 - bids[0].0) / mid * 10_000.0
        } else {
            0.0
        };
        let depth_ratio = bid_depth_5 / ask_depth_5;

        self.imbalance_ratio = imbalance_ratio;
        self.weighted_mid = weighted_mid;
        self.spread_bps = spread_bps;
        self.bid_depth_5 = bid_depth_5;
        self.ask_depth_5 = ask_depth_5;
        self.depth_ratio = depth_ratio;
        self.has_data = true;
    }

    fn into_msg(self, symbol: String) -> Option<MarketDataMsg> {
        if !self.has_data {
            return None;
        }
        Some(MarketDataMsg::ObSnapshot {
            ts_ms: self.bucket_start_ms,
            symbol,
            imbalance_ratio: self.imbalance_ratio,
            weighted_mid: self.weighted_mid,
            spread_bps: self.spread_bps,
            bid_depth_5: self.bid_depth_5,
            ask_depth_5: self.ask_depth_5,
            depth_ratio: self.depth_ratio,
        })
    }
}

/// Per-symbol 1-minute orderbook aggregator.
/// 按交易對的 1 分鐘 OB 聚合器。
#[derive(Debug, Default)]
pub struct ObAggregator {
    buckets: HashMap<String, ObBucket>,
}

impl ObAggregator {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn record(
        &mut self,
        symbol: &str,
        bids: &[(f64, f64)],
        asks: &[(f64, f64)],
        ts_ms: u64,
    ) -> Option<MarketDataMsg> {
        let bucket_ts = bucket_start_ms(ts_ms);
        let mut flushed = None;
        let entry = self
            .buckets
            .entry(symbol.to_string())
            .or_insert_with(|| ObBucket::new(bucket_ts));
        if entry.bucket_start_ms != bucket_ts {
            let prev = std::mem::replace(entry, ObBucket::new(bucket_ts));
            flushed = prev.into_msg(symbol.to_string());
        }
        entry.record(bids, asks);
        flushed
    }

    pub fn drain(&mut self) -> Vec<MarketDataMsg> {
        let mut out = Vec::new();
        let snapshot: Vec<(String, ObBucket)> = self.buckets.drain().collect();
        for (sym, b) in snapshot {
            if let Some(msg) = b.into_msg(sym) {
                out.push(msg);
            }
        }
        out
    }

    pub fn len(&self) -> usize {
        self.buckets.len()
    }
}

// ═══════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bucket_alignment() {
        assert_eq!(bucket_start_ms(0), 0);
        assert_eq!(bucket_start_ms(59_999), 0);
        assert_eq!(bucket_start_ms(60_000), 60_000);
        assert_eq!(bucket_start_ms(60_001), 60_000);
        assert_eq!(bucket_start_ms(120_000), 120_000);
    }

    #[test]
    fn test_trade_side_parse() {
        assert_eq!(TradeSide::parse("Buy"), Some(TradeSide::Buy));
        assert_eq!(TradeSide::parse("sell"), Some(TradeSide::Sell));
        assert_eq!(TradeSide::parse(""), None);
        assert_eq!(TradeSide::parse("Unknown"), None);
    }

    #[test]
    fn test_trade_aggregator_same_bucket_no_flush() {
        let mut agg = TradeAggregator::new();
        let f1 = agg.record("BTCUSDT", TradeSide::Buy, 1.0, 50_000.0, 0);
        let f2 = agg.record("BTCUSDT", TradeSide::Sell, 0.5, 50_010.0, 30_000);
        assert!(f1.is_none());
        assert!(f2.is_none());
        assert_eq!(agg.len(), 1);
    }

    #[test]
    fn test_trade_aggregator_flushes_on_minute_boundary() {
        let mut agg = TradeAggregator::new();
        agg.record("BTCUSDT", TradeSide::Buy, 2.0, 50_000.0, 1_000);
        agg.record("BTCUSDT", TradeSide::Sell, 1.0, 50_100.0, 10_000);
        // Cross into next minute
        let flushed = agg.record("BTCUSDT", TradeSide::Buy, 0.1, 50_200.0, 65_000);
        let msg = flushed.expect("flush should produce a message");
        match msg {
            MarketDataMsg::TradeAgg1m {
                ts_ms,
                symbol,
                buy_volume,
                sell_volume,
                buy_count,
                sell_count,
                vwap,
                max_single_qty,
                ..
            } => {
                assert_eq!(ts_ms, 0);
                assert_eq!(symbol, "BTCUSDT");
                assert!((buy_volume - 2.0).abs() < 1e-9);
                assert!((sell_volume - 1.0).abs() < 1e-9);
                assert_eq!(buy_count, 1);
                assert_eq!(sell_count, 1);
                // VWAP = (50000*2 + 50100*1) / 3 ≈ 50033.33
                assert!((vwap - (50_000.0 * 2.0 + 50_100.0) / 3.0).abs() < 1e-6);
                assert!((max_single_qty - 2.0).abs() < 1e-9);
            }
            _ => panic!("expected TradeAgg1m"),
        }
    }

    #[test]
    fn test_trade_aggregator_large_trade_flag() {
        let mut agg = TradeAggregator::new();
        agg.record("BTCUSDT", TradeSide::Buy, LARGE_TRADE_QTY + 1.0, 50_000.0, 0);
        agg.record("BTCUSDT", TradeSide::Sell, LARGE_TRADE_QTY * 2.0, 50_000.0, 0);
        agg.record("BTCUSDT", TradeSide::Buy, 0.5, 50_000.0, 0);
        let drained = agg.drain();
        assert_eq!(drained.len(), 1);
        match &drained[0] {
            MarketDataMsg::TradeAgg1m {
                large_buy_count,
                large_sell_count,
                ..
            } => {
                assert_eq!(*large_buy_count, 1);
                assert_eq!(*large_sell_count, 1);
            }
            _ => panic!("expected TradeAgg1m"),
        }
    }

    #[test]
    fn test_trade_aggregator_rejects_invalid() {
        let mut agg = TradeAggregator::new();
        agg.record("BTCUSDT", TradeSide::Buy, 0.0, 50_000.0, 0);
        agg.record("BTCUSDT", TradeSide::Buy, f64::NAN, 50_000.0, 0);
        agg.record("BTCUSDT", TradeSide::Buy, 1.0, -1.0, 0);
        let drained = agg.drain();
        assert!(drained.is_empty());
    }

    #[test]
    fn test_ob_aggregator_computes_aggregates() {
        let mut agg = ObAggregator::new();
        let bids = vec![
            (100.0, 5.0),
            (99.5, 4.0),
            (99.0, 3.0),
            (98.5, 2.0),
            (98.0, 1.0),
        ];
        let asks = vec![
            (100.5, 4.0),
            (101.0, 3.0),
            (101.5, 2.0),
            (102.0, 1.0),
            (102.5, 0.5),
        ];
        agg.record("BTCUSDT", &bids, &asks, 0);
        // Cross minute boundary to flush
        let flushed = agg.record("BTCUSDT", &bids, &asks, 60_001);
        let msg = flushed.expect("first bucket should flush");
        match msg {
            MarketDataMsg::ObSnapshot {
                ts_ms,
                bid_depth_5,
                ask_depth_5,
                spread_bps,
                imbalance_ratio,
                ..
            } => {
                assert_eq!(ts_ms, 0);
                assert!((bid_depth_5 - 15.0).abs() < 1e-9);
                assert!((ask_depth_5 - 10.5).abs() < 1e-9);
                assert!(imbalance_ratio > 0.0); // bid-heavy
                // spread = 0.5 / 100.25 * 10000 ≈ 49.875
                assert!((spread_bps - 0.5 / 100.25 * 10_000.0).abs() < 1e-6);
            }
            _ => panic!("expected ObSnapshot"),
        }
    }

    #[test]
    fn test_ob_aggregator_skips_empty_sides() {
        let mut agg = ObAggregator::new();
        let bids: Vec<(f64, f64)> = vec![];
        let asks = vec![(100.0, 1.0)];
        let _ = agg.record("BTCUSDT", &bids, &asks, 0);
        let drained = agg.drain();
        assert!(drained.is_empty());
    }

    #[test]
    fn test_ob_aggregator_multi_symbol_independent() {
        let mut agg = ObAggregator::new();
        let bids = vec![(100.0, 1.0)];
        let asks = vec![(101.0, 1.0)];
        agg.record("BTCUSDT", &bids, &asks, 0);
        agg.record("ETHUSDT", &bids, &asks, 0);
        assert_eq!(agg.len(), 2);
        let drained = agg.drain();
        assert_eq!(drained.len(), 2);
    }
}
