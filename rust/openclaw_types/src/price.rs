//! Price events, K-line bars, and OHLCV data.
//! 價格事件、K 線柱、OHLCV 數據。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Real-time price event from WebSocket.
/// 來自 WebSocket 的實時價格事件。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PriceEvent {
    pub symbol: String,
    pub last_price: f64,
    pub volume_24h: f64,
    pub ts_ms: u64,
    #[serde(default)]
    pub bid_price: f64,
    #[serde(default)]
    pub ask_price: f64,
    #[serde(default)]
    pub metadata: HashMap<String, String>,
}

impl PriceEvent {
    pub fn new(symbol: String, last_price: f64, ts_ms: u64) -> Self {
        Self {
            symbol,
            last_price,
            volume_24h: 0.0,
            ts_ms,
            bid_price: 0.0,
            ask_price: 0.0,
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
