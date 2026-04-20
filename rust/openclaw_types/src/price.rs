//! Price events, K-line bars, and OHLCV data.
//! 價格事件、K 線柱、OHLCV 數據。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// FIX-31: Typed price event kind — replaces stringly-typed metadata["type"].
/// FIX-31：類型化價格事件種類 — 取代字串型 metadata["type"]。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum PriceEventKind {
    /// Trade execution tick / 成交 tick
    Trade,
    /// Orderbook snapshot / 訂單簿快照
    Orderbook,
    /// Ticker update / 行情更新
    Ticker,
    /// Liquidation event / 強平事件
    Liquidation,
    /// Price limit update / 價格限制更新
    PriceLimit,
    /// ADL (auto-deleverage) notice / 自動減倉通知
    AdlNotice,
    /// REST poller fallback / REST 輪詢回退
    RestPoll,
}

/// Real-time price event from WebSocket.
/// 來自 WebSocket 的實時價格事件。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceEvent {
    pub symbol: String,
    pub last_price: f64,
    pub volume_24h: f64,
    /// 24h turnover in USD (from Bybit ticker). Used for dynamic slippage calculation.
    /// 24h 成交額（美元，來自 Bybit ticker）。用於動態滑點計算。
    #[serde(default)]
    pub turnover_24h: f64,
    pub ts_ms: u64,
    #[serde(default)]
    pub bid_price: f64,
    #[serde(default)]
    pub ask_price: f64,
    /// FIX-31: Typed event kind (preferred over metadata["type"]).
    /// FIX-31：類型化事件種類（優先於 metadata["type"]）。
    #[serde(default)]
    pub event_kind: Option<PriceEventKind>,
    // ── P-02: Structured payload fields — avoids HashMap alloc per tick ──
    // P-02：結構化載荷欄位 — 避免每 tick HashMap 分配。
    /// Trade side (for Trade events): "Buy" or "Sell".
    /// 成交方向（Trade 事件）："Buy" 或 "Sell"。
    #[serde(default)]
    pub trade_side: Option<String>,
    /// Trade quantity (for Trade events).
    /// 成交數量（Trade 事件）。
    #[serde(default)]
    pub trade_qty: Option<f64>,
    /// Top-5 bids (for Orderbook events): [(price, qty), ...].
    /// 前 5 檔買盤（Orderbook 事件）。
    #[serde(default)]
    pub bids5: Option<Vec<(f64, f64)>>,
    /// Top-5 asks (for Orderbook events): [(price, qty), ...].
    /// 前 5 檔賣盤（Orderbook 事件）。
    #[serde(default)]
    pub asks5: Option<Vec<(f64, f64)>>,
    /// ADL rank (for AdlNotice events).
    /// ADL 排名（AdlNotice 事件）。
    #[serde(default)]
    pub adl_rank: Option<u32>,
    /// Current funding rate (for Ticker events, from Bybit tickers stream).
    /// 當前資金費率（Ticker 事件，來自 Bybit tickers 流）。
    #[serde(default)]
    pub funding_rate: Option<f64>,
    /// OC-5: Index price for basis calculation (from Bybit tickers stream).
    /// OC-5：用於基差計算的指數價格（來自 Bybit tickers 流）。
    #[serde(default)]
    pub index_price: Option<f64>,
    /// EDGE-P2-2: Open interest (contract count, from Bybit tickers stream).
    /// Distinct from `openInterestValue` (USD notional = OI × mark price).
    /// None when tickers payload omits or carries an un-parseable value.
    /// EDGE-P2-2：未平倉合約數（來自 Bybit tickers 流，原始合約張數）。
    /// 不同於 `openInterestValue`（名義金額 = OI × 標記價）。解析失敗則為 None。
    #[serde(default)]
    pub open_interest: Option<f64>,
    /// Legacy metadata map — still populated for backward compat, but prefer structured fields.
    /// 舊版 metadata — 為向後兼容仍填充，但應優先使用結構化欄位。
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

impl PriceEvent {
    pub fn new(symbol: String, last_price: f64, ts_ms: u64) -> Self {
        Self {
            symbol,
            last_price,
            volume_24h: 0.0,
            turnover_24h: 0.0,
            ts_ms,
            bid_price: 0.0,
            ask_price: 0.0,
            event_kind: None,
            trade_side: None,
            trade_qty: None,
            bids5: None,
            asks5: None,
            adl_rank: None,
            funding_rate: None,
            index_price: None,
            // EDGE-P2-2: open_interest defaults to None (ticker-only field).
            // EDGE-P2-2：open_interest 預設 None（僅 tickers 事件會填充）。
            open_interest: None,
            metadata: HashMap::new(),
        }
    }

    /// Check if price event is fresh (< max_age_ms old).
    /// 檢查價格事件是否新鮮。
    pub fn is_fresh(&self, max_age_ms: u64, now_ms: u64) -> bool {
        now_ms.saturating_sub(self.ts_ms) < max_age_ms
    }
}

/// OHLCV aggregated candle data.
/// OHLCV 聚合蠟燭數據。
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq)]
pub struct OHLCV {
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

impl OHLCV {
    pub fn new(open: f64, high: f64, low: f64, close: f64, volume: f64) -> Self {
        Self {
            open,
            high,
            low,
            close,
            volume,
        }
    }

    pub fn typical_price(&self) -> f64 {
        (self.high + self.low + self.close) / 3.0
    }

    pub fn range(&self) -> f64 {
        self.high - self.low
    }
}

/// Single K-line bar.
/// 單根 K 線柱。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct KlineBar {
    pub open_time_ms: u64,
    pub close_time_ms: u64,
    pub ohlcv: OHLCV,
    pub turnover: f64,
    pub tick_count: u32,
    pub is_closed: bool,
}

impl KlineBar {
    pub fn new(
        open_time_ms: u64,
        close_time_ms: u64,
        open: f64,
        high: f64,
        low: f64,
        close: f64,
        volume: f64,
    ) -> Self {
        Self {
            open_time_ms,
            close_time_ms,
            ohlcv: OHLCV::new(open, high, low, close, volume),
            turnover: 0.0,
            tick_count: 1,
            is_closed: false,
        }
    }
}

/// Historical kline data for a symbol+timeframe pair.
/// 特定交易對+時間框架的歷史 K 線數據。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Kline {
    pub symbol: String,
    pub timeframe: String,
    pub bars: Vec<KlineBar>,
}

impl Kline {
    pub fn new(symbol: String, timeframe: String) -> Self {
        Self {
            symbol,
            timeframe,
            bars: Vec::new(),
        }
    }

    pub fn closes(&self) -> Vec<f64> {
        self.bars.iter().map(|b| b.ohlcv.close).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_price_event_serde_roundtrip() {
        let ev = PriceEvent::new("BTCUSDT".into(), 65000.0, 1_700_000_000_000);
        let json = serde_json::to_string(&ev).unwrap();
        let de: PriceEvent = serde_json::from_str(&json).unwrap();
        assert_eq!(de.symbol, "BTCUSDT");
        assert!((de.last_price - 65000.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_price_event_freshness() {
        let ev = PriceEvent::new("ETHUSDT".into(), 3000.0, 1000);
        assert!(ev.is_fresh(500, 1400));
        assert!(!ev.is_fresh(500, 1600));
    }

    #[test]
    fn test_ohlcv_typical_price() {
        let o = OHLCV::new(100.0, 110.0, 90.0, 105.0, 1000.0);
        let tp = o.typical_price();
        assert!((tp - 101.666_666_666_666_67).abs() < 1e-10);
    }

    #[test]
    fn test_kline_bar_serde_roundtrip() {
        let bar = KlineBar::new(0, 60000, 100.0, 110.0, 90.0, 105.0, 500.0);
        let json = serde_json::to_string(&bar).unwrap();
        let de: KlineBar = serde_json::from_str(&json).unwrap();
        assert_eq!(de.ohlcv.close, 105.0);
    }
}
