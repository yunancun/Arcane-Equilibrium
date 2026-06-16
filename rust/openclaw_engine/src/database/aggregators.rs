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
// ObTopSampler — L1 top-of-book 取樣節流（sub-second 前向錄製）
// ═══════════════════════════════════════════════════════════════════

/// 默認最小取樣間隔（毫秒）。同 symbol 相鄰落盤至少間隔此值，除非 top-of-book
/// 有意義變化。可由 OPENCLAW_OB_TOP_SAMPLE_MS env 覆蓋。
/// Default min sample interval (ms) for ObTopSampler.
pub const OB_TOP_DEFAULT_SAMPLE_MS: u64 = 250;

#[derive(Debug, Clone, Copy)]
struct ObTopState {
    last_emit_ms: u64,
    best_bid: f64,
    bid_size: f64,
    best_ask: f64,
    ask_size: f64,
}

/// Per-symbol L1 top-of-book 取樣器。
///
/// 為什麼節流：orderbook.50 在熱門 symbol 上 update rate 極高，逐筆落盤 = full-rate
/// 爆儲存（TB/週級）。本取樣器以「時間節流」為主閘：保證同 symbol 相鄰 emit 間隔
/// 嚴格 ≥ `sample_interval_ms`（默認 250ms）—— 此上界對任意輸入恆成立，**不可被
/// 繞過**（這是儲存量 < 40GB 駐留與 E2 審查點 #2 的硬保證）。
///
/// 「有意義變化」在此作為**節流窗內的去重旁路**：時間閘未過時，若 top-of-book
/// 相對上次落盤值毫無變化，則連 emit 都省（不寫重複行）；但變化本身**不會**讓
/// 落盤頻率超過時間閘上界。PA §2.2 原文「250ms 或有意義變化」字面允許變化在
/// 窗內也 emit，但那會在熱門 symbol 上退化成 full-rate（違 E2 #2 與儲存估算）；
/// 故取最小安全解：時間閘為硬上界，變化僅決定「過閘後是否值得寫」。
/// 這仍補回 ObAggregator（每分鐘只留最後一筆）丟棄的 sub-minute 粒度。
///
/// 不變量：純 in-memory HashMap 查詢，開銷與 ObAggregator.record 同量級；
/// 不阻塞、不持鎖、無 await。狀態由 TickPipeline 擁有。
#[derive(Debug)]
pub struct ObTopSampler {
    states: HashMap<String, ObTopState>,
    sample_interval_ms: u64,
}

impl ObTopSampler {
    pub fn new(sample_interval_ms: u64) -> Self {
        Self {
            states: HashMap::new(),
            sample_interval_ms,
        }
    }

    /// 從 env 讀取取樣間隔（OPENCLAW_OB_TOP_SAMPLE_MS），缺省 250ms。
    pub fn from_env() -> Self {
        let interval = std::env::var("OPENCLAW_OB_TOP_SAMPLE_MS")
            .ok()
            .and_then(|s| s.parse::<u64>().ok())
            .filter(|&v| v > 0)
            .unwrap_or(OB_TOP_DEFAULT_SAMPLE_MS);
        Self::new(interval)
    }

    /// 接收一筆 OB 快照的 top-of-book，決定是否落盤。
    ///
    /// 回傳 `Some(MarketDataMsg::ObTop)` 代表通過取樣節流應落盤；`None` 代表被節流丟棄。
    /// 取樣規則：距上次同 symbol emit ≥ sample_interval_ms **或** top-of-book 有意義變化。
    pub fn record(
        &mut self,
        symbol: &str,
        bids: &[(f64, f64)],
        asks: &[(f64, f64)],
        ts_ms: u64,
    ) -> Option<MarketDataMsg> {
        // fail-soft：缺最優買賣一檔或非有限值不落盤（避免寫入髒值）。
        let (best_bid, bid_size) = *bids.first()?;
        let (best_ask, ask_size) = *asks.first()?;
        if !best_bid.is_finite()
            || !bid_size.is_finite()
            || !best_ask.is_finite()
            || !ask_size.is_finite()
        {
            return None;
        }

        let should_emit = match self.states.get(symbol) {
            None => true, // 首見 symbol 必落盤
            Some(prev) => {
                let elapsed = ts_ms.saturating_sub(prev.last_emit_ms);
                // 時間閘=硬上界：未過閘一律不 emit（保證相鄰 ts ≥ sample_interval_ms）。
                if elapsed < self.sample_interval_ms {
                    return None;
                }
                // 過閘後再以「有意義變化」去重：top-of-book 毫無變化則省略重複寫入。
                best_bid != prev.best_bid
                    || bid_size != prev.bid_size
                    || best_ask != prev.best_ask
                    || ask_size != prev.ask_size
            }
        };

        if !should_emit {
            return None;
        }

        self.states.insert(
            symbol.to_string(),
            ObTopState {
                last_emit_ms: ts_ms,
                best_bid,
                bid_size,
                best_ask,
                ask_size,
            },
        );

        Some(MarketDataMsg::ObTop {
            ts_ms,
            symbol: symbol.to_string(),
            best_bid,
            bid_size,
            best_ask,
            ask_size,
        })
    }

    pub fn len(&self) -> usize {
        self.states.len()
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
        agg.record(
            "BTCUSDT",
            TradeSide::Buy,
            LARGE_TRADE_QTY + 1.0,
            50_000.0,
            0,
        );
        agg.record(
            "BTCUSDT",
            TradeSide::Sell,
            LARGE_TRADE_QTY * 2.0,
            50_000.0,
            0,
        );
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

    // ── ObTopSampler 取樣節流測試 ──

    fn ob_top_ts(msg: &MarketDataMsg) -> u64 {
        match msg {
            MarketDataMsg::ObTop { ts_ms, .. } => *ts_ms,
            _ => panic!("expected ObTop"),
        }
    }

    #[test]
    fn test_ob_top_sampler_first_event_always_emits() {
        let mut s = ObTopSampler::new(250);
        let bids = vec![(100.0, 5.0)];
        let asks = vec![(101.0, 7.0)];
        let m = s.record("BTCUSDT", &bids, &asks, 1_000).expect("first emits");
        match m {
            MarketDataMsg::ObTop {
                symbol,
                best_bid,
                bid_size,
                best_ask,
                ask_size,
                ts_ms,
            } => {
                assert_eq!(symbol, "BTCUSDT");
                assert!((best_bid - 100.0).abs() < f64::EPSILON);
                assert!((bid_size - 5.0).abs() < f64::EPSILON);
                assert!((best_ask - 101.0).abs() < f64::EPSILON);
                assert!((ask_size - 7.0).abs() < f64::EPSILON);
                assert_eq!(ts_ms, 1_000);
            }
            _ => panic!("expected ObTop"),
        }
    }

    #[test]
    fn test_ob_top_sampler_throttle_is_hard_upper_bound() {
        // 時間閘=硬上界：窗內即使 top-of-book 變化也不得 emit（防 full-rate 爆儲存，E2 #2）。
        let mut s = ObTopSampler::new(250);
        let bids0 = vec![(100.0, 5.0)];
        let asks0 = vec![(101.0, 7.0)];
        assert!(s.record("BTCUSDT", &bids0, &asks0, 1_000).is_some()); // 首筆 emit @1000
        // 1010ms：距上次 10ms < 250ms，即使價量變化也必須被節流丟棄。
        let bids1 = vec![(100.5, 6.0)];
        let asks1 = vec![(101.5, 8.0)];
        assert!(s.record("BTCUSDT", &bids1, &asks1, 1_010).is_none());
        // 1100ms：仍在窗內（距 1000ms 才 100ms），丟棄。
        assert!(s.record("BTCUSDT", &bids1, &asks1, 1_100).is_none());
        // 1250ms：距上次 emit 恰 250ms 過閘 + 有變化 → emit。
        let m = s.record("BTCUSDT", &bids1, &asks1, 1_250).expect("gate passed");
        assert_eq!(ob_top_ts(&m), 1_250);
    }

    #[test]
    fn test_ob_top_sampler_dedup_unchanged_after_gate() {
        // 過閘後若 top-of-book 毫無變化則去重（不寫重複行）。
        let mut s = ObTopSampler::new(250);
        let bids = vec![(100.0, 5.0)];
        let asks = vec![(101.0, 7.0)];
        assert!(s.record("BTCUSDT", &bids, &asks, 1_000).is_some());
        // 1300ms：過閘但完全相同 → 去重，不 emit（last_emit_ms 維持 1000）。
        assert!(s.record("BTCUSDT", &bids, &asks, 1_300).is_none());
        // 1600ms：距首筆 emit 600ms 過閘 + size 變化 → emit。
        let bids2 = vec![(100.0, 9.0)];
        let m = s.record("BTCUSDT", &bids2, &asks, 1_600).expect("changed emits");
        assert_eq!(ob_top_ts(&m), 1_600);
    }

    #[test]
    fn test_ob_top_sampler_per_symbol_independent() {
        // 不同 symbol 各自獨立計時，互不影響。
        let mut s = ObTopSampler::new(250);
        let bids = vec![(100.0, 5.0)];
        let asks = vec![(101.0, 7.0)];
        assert!(s.record("BTCUSDT", &bids, &asks, 1_000).is_some());
        assert!(s.record("ETHUSDT", &bids, &asks, 1_000).is_some()); // 各自首筆都 emit
        assert_eq!(s.len(), 2);
        // BTCUSDT 窗內丟棄，ETHUSDT 同窗內也丟棄，互不解鎖。
        assert!(s.record("BTCUSDT", &bids, &asks, 1_050).is_none());
        assert!(s.record("ETHUSDT", &bids, &asks, 1_050).is_none());
    }

    #[test]
    fn test_ob_top_sampler_rejects_empty_and_non_finite() {
        let mut s = ObTopSampler::new(250);
        let bids = vec![(100.0, 5.0)];
        let asks = vec![(101.0, 7.0)];
        assert!(s.record("BTCUSDT", &[], &asks, 1_000).is_none()); // 缺 bid
        assert!(s.record("BTCUSDT", &bids, &[], 1_000).is_none()); // 缺 ask
        let nan_bids = vec![(f64::NAN, 5.0)];
        assert!(s.record("BTCUSDT", &nan_bids, &asks, 1_000).is_none()); // 非有限
        assert_eq!(s.len(), 0); // 全被拒，無狀態寫入
    }

    #[test]
    fn test_ob_top_sampler_throttle_caps_emit_rate() {
        // 1 秒內 100 筆全變化的 tick @10ms cadence，250ms 閘下至多 ~4 筆 emit。
        let mut s = ObTopSampler::new(250);
        let mut emits = 0;
        for i in 0..100u64 {
            let ts = 1_000 + i * 10; // 1000..1990ms
            let bids = vec![(100.0 + i as f64 * 0.01, 5.0)];
            let asks = vec![(101.0 + i as f64 * 0.01, 7.0)];
            if s.record("BTCUSDT", &bids, &asks, ts).is_some() {
                emits += 1;
            }
        }
        // 990ms 跨度 / 250ms 閘 + 首筆 → 上界 ~5；證明遠低於 full-rate 100。
        assert!(emits <= 5, "throttle must cap emits, got {emits}");
        assert!(emits >= 4, "should emit roughly every 250ms, got {emits}");
    }
}
