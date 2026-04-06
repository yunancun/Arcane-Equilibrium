//! Multi-interval public WebSocket subscription builder.
//! 多時間框架公開 WebSocket 訂閱構建器。
//!
//! MODULE_NOTE (EN): Extends the public WsClient by generating subscription lists
//!   for multiple kline intervals (1m, 5m, 15m, 60m), tickers, and L2 orderbook.
//!   Provides a convenience function to configure a WsClient with all desired topics
//!   for a given set of symbols.
//! MODULE_NOTE (中): 擴展公開 WsClient，為多個 K 線時間框架（1m、5m、15m、60m）、
//!   行情和 L2 訂單簿生成訂閱列表。提供便利函數，用所有所需主題
//!   為一組交易對配置 WsClient。

use crate::ws_client::WsClient;

// ---------------------------------------------------------------------------
// Subscription intervals / 訂閱時間框架
// ---------------------------------------------------------------------------

/// Supported kline intervals for multi-interval subscription.
/// 多時間框架訂閱支持的 K 線間隔。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum KlineInterval {
    /// 1 minute / 1 分鐘
    Min1,
    /// 5 minutes / 5 分鐘
    Min5,
    /// 15 minutes / 15 分鐘
    Min15,
    /// 1 hour / 1 小時
    Hour1,
}

impl KlineInterval {
    /// Get Bybit topic interval string (e.g., "1", "5", "15", "60").
    /// 取得 Bybit 主題間隔字串。
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Min1 => "1",
            Self::Min5 => "5",
            Self::Min15 => "15",
            Self::Hour1 => "60",
        }
    }
}

/// All default intervals for multi-interval subscription.
/// 多時間框架訂閱的所有默認間隔。
pub const DEFAULT_INTERVALS: &[KlineInterval] = &[
    KlineInterval::Min1,
    KlineInterval::Min5,
    KlineInterval::Min15,
    KlineInterval::Hour1,
];

// ---------------------------------------------------------------------------
// Topic types / 主題類型
// ---------------------------------------------------------------------------

/// Types of topics that can be subscribed to.
/// 可訂閱的主題類型。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum TopicType {
    /// Kline (candlestick) data / K 線（蠟燭圖）數據
    Kline,
    /// Ticker (latest price/volume snapshot) / 行情（最新價格/成交量快照）
    Ticker,
    /// L2 orderbook (50 levels) / L2 訂單簿（50 檔）
    Orderbook50,
    /// Public trades / 公開交易
    PublicTrade,
    /// Liquidation events / 清算事件
    Liquidation,
    /// Price limit updates / 價格限制更新
    PriceLimit,
    /// ADL alert notifications / ADL 通知
    AdlNotice,
}

// ---------------------------------------------------------------------------
// Subscription builder / 訂閱構建器
// ---------------------------------------------------------------------------

/// Build a list of kline subscription topics for a symbol across all given intervals.
/// 為一個交易對在所有給定間隔上構建 K 線訂閱主題列表。
///
/// Example: `kline_topics("BTCUSDT", &[Min1, Min5])` → `["kline.1.BTCUSDT", "kline.5.BTCUSDT"]`
pub fn kline_topics(symbol: &str, intervals: &[KlineInterval]) -> Vec<String> {
    intervals
        .iter()
        .map(|iv| format!("kline.{}.{}", iv.as_str(), symbol))
        .collect()
}

/// Build the ticker topic for a symbol.
/// 為一個交易對構建行情主題。
///
/// Example: `ticker_topic("BTCUSDT")` → `"tickers.BTCUSDT"`
pub fn ticker_topic(symbol: &str) -> String {
    format!("tickers.{}", symbol)
}

/// Build the L2 orderbook topic for a symbol (50 levels).
/// 為一個交易對構建 L2 訂單簿主題（50 檔）。
///
/// Example: `orderbook_topic("BTCUSDT")` → `"orderbook.50.BTCUSDT"`
pub fn orderbook_topic(symbol: &str) -> String {
    format!("orderbook.50.{}", symbol)
}

/// Build the public trade topic for a symbol.
/// 為一個交易對構建公開交易主題。
///
/// Example: `public_trade_topic("BTCUSDT")` → `"publicTrade.BTCUSDT"`
pub fn public_trade_topic(symbol: &str) -> String {
    format!("publicTrade.{}", symbol)
}

/// Build the liquidation topic for a symbol.
/// 為一個交易對構建清算主題。
///
/// Example: `liquidation_topic("BTCUSDT")` → `"liquidation.BTCUSDT"`
pub fn liquidation_topic(symbol: &str) -> String {
    format!("liquidation.{}", symbol)
}

/// Build the price limit topic for a symbol.
/// 為一個交易對構建價格限制主題。
///
/// Example: `price_limit_topic("BTCUSDT")` → `"price-limit.BTCUSDT"`
pub fn price_limit_topic(symbol: &str) -> String {
    format!("price-limit.{}", symbol)
}

/// Build the ADL notice topic for a symbol.
/// 為一個交易對構建 ADL 通知主題。
///
/// Example: `adl_notice_topic("BTCUSDT")` → `"adl-notice.BTCUSDT"`
pub fn adl_notice_topic(symbol: &str) -> String {
    format!("adl-notice.{}", symbol)
}

/// Generate the full subscription list for a symbol with all topic types.
/// 為一個交易對生成包含所有主題類型的完整訂閱列表。
///
/// Includes: klines (all default intervals) + ticker + orderbook + publicTrade
/// 包含：K 線（所有默認間隔）+ 行情 + 訂單簿 + 公開交易
pub fn full_subscription_list(symbol: &str) -> Vec<String> {
    full_subscription_list_with_intervals(symbol, DEFAULT_INTERVALS)
}

/// Generate the full subscription list for a symbol with custom intervals.
/// 為一個交易對使用自定義間隔生成完整訂閱列表。
pub fn full_subscription_list_with_intervals(
    symbol: &str,
    intervals: &[KlineInterval],
) -> Vec<String> {
    let mut topics = kline_topics(symbol, intervals);
    topics.push(ticker_topic(symbol));
    topics.push(orderbook_topic(symbol));
    topics.push(public_trade_topic(symbol));
    // REMOVED: liquidation topic — Bybit returns "handler not found" which poisons
    // the entire WS connection (all other subscriptions stop receiving data).
    // 已移除：liquidation topic — Bybit 返回 "handler not found"，會毒化整個 WS 連接。
    // Note: price-limit and adl-notice are opt-in via `extended_subscription_list()`.
    // 注意：price-limit 和 adl-notice 通過 `extended_subscription_list()` 可選訂閱。
    topics
}

/// Extended subscription list including price-limit and ADL notice (opt-in).
/// 擴展訂閱列表，包含 price-limit 和 ADL notice（可選）。
pub fn extended_subscription_list(symbol: &str) -> Vec<String> {
    // REMOVED: price-limit and adl-notice — Bybit returns "handler not found"
    // which poisons the entire WS connection (all other subscriptions stop receiving data).
    // 已移除：price-limit 和 adl-notice — Bybit 返回 "handler not found"，會毒化整個 WS 連接。
    full_subscription_list(symbol)
}

/// Generate subscription lists for multiple symbols.
/// 為多個交易對生成訂閱列表。
pub fn multi_symbol_subscriptions(symbols: &[&str]) -> Vec<String> {
    symbols
        .iter()
        .flat_map(|s| full_subscription_list(s))
        .collect()
}

/// Configure a WsClient with multi-interval subscriptions for the given symbols.
/// 為給定交易對配置具有多時間框架訂閱的 WsClient。
///
/// Adds all default topics (klines, ticker, orderbook, publicTrade) for each symbol.
/// 為每個交易對添加所有默認主題。
pub fn configure_multi_interval(ws: &mut WsClient, symbols: &[&str]) {
    let topics = multi_symbol_subscriptions(symbols);
    for topic in topics {
        ws.subscribe(topic);
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Test kline topic generation for single symbol, all default intervals.
    /// 測試單個交易對、所有默認間隔的 K 線主題生成。
    #[test]
    fn test_kline_topics_default() {
        let topics = kline_topics("BTCUSDT", DEFAULT_INTERVALS);
        assert_eq!(topics.len(), 4);
        assert_eq!(topics[0], "kline.1.BTCUSDT");
        assert_eq!(topics[1], "kline.5.BTCUSDT");
        assert_eq!(topics[2], "kline.15.BTCUSDT");
        assert_eq!(topics[3], "kline.60.BTCUSDT");
    }

    /// Test kline topic generation with custom intervals.
    /// 測試自定義間隔的 K 線主題生成。
    #[test]
    fn test_kline_topics_custom() {
        let topics = kline_topics("ETHUSDT", &[KlineInterval::Min1, KlineInterval::Hour1]);
        assert_eq!(topics.len(), 2);
        assert_eq!(topics[0], "kline.1.ETHUSDT");
        assert_eq!(topics[1], "kline.60.ETHUSDT");
    }

    /// Test ticker and orderbook topic formatting.
    /// 測試行情和訂單簿主題格式化。
    #[test]
    fn test_ticker_and_orderbook_topics() {
        assert_eq!(ticker_topic("BTCUSDT"), "tickers.BTCUSDT");
        assert_eq!(orderbook_topic("BTCUSDT"), "orderbook.50.BTCUSDT");
        assert_eq!(public_trade_topic("BTCUSDT"), "publicTrade.BTCUSDT");
    }

    /// Test full subscription list for a single symbol.
    /// 測試單個交易對的完整訂閱列表。
    #[test]
    fn test_full_subscription_list() {
        let topics = full_subscription_list("BTCUSDT");
        // 4 klines + ticker + orderbook + publicTrade = 7 (liquidation removed: Bybit handler not found)
        assert_eq!(topics.len(), 7);
        assert!(topics.contains(&"kline.1.BTCUSDT".to_string()));
        assert!(topics.contains(&"kline.5.BTCUSDT".to_string()));
        assert!(topics.contains(&"kline.15.BTCUSDT".to_string()));
        assert!(topics.contains(&"kline.60.BTCUSDT".to_string()));
        assert!(topics.contains(&"tickers.BTCUSDT".to_string()));
        assert!(topics.contains(&"orderbook.50.BTCUSDT".to_string()));
        assert!(topics.contains(&"publicTrade.BTCUSDT".to_string()));
    }

    #[test]
    fn test_extended_subscription_list() {
        let topics = extended_subscription_list("BTCUSDT");
        // Extended now equals full (price-limit + adl-notice also removed: Bybit handler not found)
        assert_eq!(topics.len(), 7);
    }

    /// Test multi-symbol subscription list.
    /// 測試多交易對訂閱列表。
    #[test]
    fn test_multi_symbol_subscriptions() {
        let topics = multi_symbol_subscriptions(&["BTCUSDT", "ETHUSDT"]);
        // 7 topics per symbol * 2 symbols = 14
        assert_eq!(topics.len(), 14);
        assert!(topics.contains(&"kline.1.BTCUSDT".to_string()));
        assert!(topics.contains(&"kline.1.ETHUSDT".to_string()));
        assert!(topics.contains(&"tickers.ETHUSDT".to_string()));
        assert!(topics.contains(&"orderbook.50.BTCUSDT".to_string()));
    }

    /// Test KlineInterval as_str values.
    /// 測試 KlineInterval as_str 值。
    #[test]
    fn test_interval_as_str() {
        assert_eq!(KlineInterval::Min1.as_str(), "1");
        assert_eq!(KlineInterval::Min5.as_str(), "5");
        assert_eq!(KlineInterval::Min15.as_str(), "15");
        assert_eq!(KlineInterval::Hour1.as_str(), "60");
    }

    /// Test empty symbol list produces empty subscription.
    /// 測試空交易對列表產生空訂閱。
    #[test]
    fn test_empty_symbols() {
        let topics = multi_symbol_subscriptions(&[]);
        assert!(topics.is_empty());
    }

    /// Test empty intervals produces only non-kline topics.
    /// 測試空間隔只產生非 K 線主題。
    #[test]
    fn test_empty_intervals() {
        let topics = full_subscription_list_with_intervals("BTCUSDT", &[]);
        // 0 klines + ticker + orderbook + publicTrade = 3 (liquidation removed)
        assert_eq!(topics.len(), 3);
        assert!(topics.contains(&"tickers.BTCUSDT".to_string()));
        assert!(topics.contains(&"orderbook.50.BTCUSDT".to_string()));
        assert!(topics.contains(&"publicTrade.BTCUSDT".to_string()));
    }
}
