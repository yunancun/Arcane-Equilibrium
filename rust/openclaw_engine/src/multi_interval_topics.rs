//! Multi-interval public WebSocket topic string builder (pure).
//! 多時間框架公開 WebSocket 訂閱主題字串構建器（純函數）。
//!
//! MODULE_NOTE (EN): Pure topic-string construction for Bybit V5 public WS
//!   subscriptions across multiple kline intervals (1m, 5m, 15m, 60m), ticker,
//!   L2 orderbook and public trades. Deliberately has NO dependency on
//!   `WsClient` or any side-effectful type — the caller applies the returned
//!   topic strings to whatever WS client they hold. Behaviour contract is
//!   covered by the unit tests below; any deviation in the produced strings
//!   is a breaking change to the live subscription set.
//! MODULE_NOTE (中): 為 Bybit V5 公開 WS 訂閱純粹地構建主題字串 —
//!   涵蓋多個 K 線間隔（1m、5m、15m、60m）、ticker、L2 訂單簿與公開交易。
//!   刻意不依賴 `WsClient` 或任何帶副作用的型別，呼叫端自行把字串套用到
//!   其持有的 WS 客戶端。行為契約由下方單元測試守護；任何產生字串上的
//!   偏差都等同於 live 訂閱集合的破壞性變更。
//!
//! Renamed 2026-04-19 from `multi_interval_ws.rs` (E5-P2-3). The rename
//! reflects the pure-topic responsibility — the previous name implied this
//! module owned WS transport, which it never did.
//! 2026-04-19（E5-P2-3）自 `multi_interval_ws.rs` 更名。新檔名反映「純主題
//! 構建」職責 — 舊名暗示本模組擁有 WS 傳輸，但實際從未如此。

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
    // GAP: Liquidation / PriceLimit / AdlNotice variants removed 2026-04-06.
    // Bybit V5 returned "handler not found" for these topics, poisoning the
    // entire WS connection (commit 29fc1ef). No consumer exists.
}

// ---------------------------------------------------------------------------
// Pure topic builders / 純主題構建器
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
    // GAP: liquidation/price-limit/adl-notice topics permanently removed
    // (commit 29fc1ef) — Bybit returns "handler not found" which silently
    // poisons the entire WS connection. Re-add only after confirming a
    // working topic name on a stand-alone test connection.
    topics
}

/// Generate subscription lists for multiple symbols.
/// 為多個交易對生成訂閱列表。
pub fn multi_symbol_subscriptions(symbols: &[&str]) -> Vec<String> {
    symbols
        .iter()
        .flat_map(|s| full_subscription_list(s))
        .collect()
}

// ---------------------------------------------------------------------------
// Removed 2026-04-19 (E5-P2-3): `configure_multi_interval(ws, symbols)` used
// to mutate a `WsClient` in place. It had zero live callers across the
// Rust+Python workspace (main.rs drives subscriptions directly via
// `full_subscription_list`). Dropping it is what makes this module a pure
// topic builder — fulfilling the audit intent (docs/audits/2026-04-18 §五
// P2 "pure-function extraction"). Callers wanting the one-shot wrapper
// should call `multi_symbol_subscriptions` and iterate `ws.subscribe(..)`
// themselves (3 lines, keeps this module free of WsClient coupling).
// ---------------------------------------------------------------------------
// 2026-04-19（E5-P2-3）刪除 `configure_multi_interval(ws, symbols)`：
// 該函數原會就地改動 `WsClient`，但整個 Rust+Python 工作區零 live 呼叫
// （main.rs 直接用 `full_subscription_list` 驅動訂閱）。移除後本模組完全
// 擺脫 `WsClient` 耦合，成為純主題字串構建器，呼應 audit 的 "pure-function
// extraction" 意圖。若需一鍵包裝，請呼叫 `multi_symbol_subscriptions` 再
// 自行 `ws.subscribe(..)`（3 行即可，不需把 WsClient 耦合回本模組）。
// ---------------------------------------------------------------------------

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

    /// E5-P2-3 added: topic ordering is kline-intervals-first then
    /// ticker/orderbook/publicTrade; this is a behaviour contract because
    /// the WS subscribe frame sends them in order, which affects first-ack
    /// latency in live monitoring. Do not reorder without updating docs.
    /// E5-P2-3 新增：主題順序為先 kline（依 intervals 輸入順序）、再
    /// ticker / orderbook / publicTrade。此順序為行為契約，WS 訂閱幀會
    /// 依序送出，影響 live 監控首個 ack 的延遲觀測；改動必須同步文檔。
    #[test]
    fn test_full_subscription_list_ordering_contract() {
        let topics = full_subscription_list_with_intervals(
            "BTCUSDT",
            &[KlineInterval::Min5, KlineInterval::Min1],
        );
        assert_eq!(
            topics,
            vec![
                "kline.5.BTCUSDT".to_string(),
                "kline.1.BTCUSDT".to_string(),
                "tickers.BTCUSDT".to_string(),
                "orderbook.50.BTCUSDT".to_string(),
                "publicTrade.BTCUSDT".to_string(),
            ]
        );
    }

    /// E5-P2-3 added: multi-symbol ordering groups all topics of symbol[0]
    /// before symbol[1] — important for WS subscribe-batch ordering so that
    /// a first symbol's stream is up before the next is queued.
    /// E5-P2-3 新增：多交易對下，符號 0 的所有主題排在符號 1 之前 —
    /// 用於確保 WS 批次訂閱時第一個交易對的流先建立，再排隊下一個。
    #[test]
    fn test_multi_symbol_subscriptions_grouping_contract() {
        let topics = multi_symbol_subscriptions(&["BTCUSDT", "ETHUSDT"]);
        // First 7 entries must all be BTCUSDT topics, next 7 must all be ETHUSDT.
        for t in &topics[0..7] {
            assert!(t.ends_with("BTCUSDT"), "expected BTCUSDT prefix group, got {t}");
        }
        for t in &topics[7..14] {
            assert!(t.ends_with("ETHUSDT"), "expected ETHUSDT prefix group, got {t}");
        }
    }
}
