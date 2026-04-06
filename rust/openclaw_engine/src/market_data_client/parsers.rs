//! Parsing helpers for Bybit V5 market data responses.
//! Bybit V5 市場數據回應的解析輔助函數。
//!
//! MODULE_NOTE (EN): Pure functions that convert Bybit's string-encoded JSON
//!   response payloads into strongly-typed structs. Extracted from
//!   market_data_client.rs for file size compliance.
//! MODULE_NOTE (中): 將 Bybit 字串編碼 JSON 回應負載轉換為強類型結構體的純函數。
//!   從 market_data_client.rs 中提取以符合文件大小限制。

use super::types::{KlineBar, OrderbookSnapshot, TickerInfo};
use crate::bybit_rest_client::BybitResult;

/// Parse a string field from a JSON value, returning empty string on failure.
/// 從 JSON 值中解析字串欄位，失敗時返回空字串。
pub(super) fn parse_str(obj: &serde_json::Value, field: &str) -> String {
    obj.get(field)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

/// Parse a string-encoded f64 field, returning 0.0 on failure.
/// 解析字串編碼的 f64 欄位，失敗時返回 0.0。
pub(super) fn parse_str_f64(obj: &serde_json::Value, field: &str) -> f64 {
    obj.get(field)
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0)
}

/// Parse kline list from Bybit response result.
/// 從 Bybit 回應結果中解析 K 線列表。
///
/// Bybit kline format: array of arrays:
///   [["1700000000000","65000","66000","64000","65500","100","6500000"], ...]
///   [startTime, open, high, low, close, volume, turnover]
/// Bybit K 線格式：數組的數組。
pub(super) fn parse_kline_list(result: &serde_json::Value) -> BybitResult<Vec<KlineBar>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let mut bars = Vec::with_capacity(list.len());
    for item in &list {
        if let Some(arr) = item.as_array() {
            if arr.len() >= 7 {
                bars.push(KlineBar {
                    start_time: arr[0]
                        .as_str()
                        .and_then(|s| s.parse::<u64>().ok())
                        .unwrap_or(0),
                    open: arr[1]
                        .as_str()
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0),
                    high: arr[2]
                        .as_str()
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0),
                    low: arr[3]
                        .as_str()
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0),
                    close: arr[4]
                        .as_str()
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0),
                    volume: arr[5]
                        .as_str()
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0),
                    turnover: arr[6]
                        .as_str()
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0),
                });
            }
        }
    }
    Ok(bars)
}

/// Parse ticker list from Bybit response result.
/// 從 Bybit 回應結果中解析行情列表。
pub(super) fn parse_ticker_list(result: &serde_json::Value) -> BybitResult<Vec<TickerInfo>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let mut tickers = Vec::with_capacity(list.len());
    for item in &list {
        tickers.push(TickerInfo {
            symbol: parse_str(item, "symbol"),
            last_price: parse_str_f64(item, "lastPrice"),
            bid1_price: parse_str_f64(item, "bid1Price"),
            ask1_price: parse_str_f64(item, "ask1Price"),
            volume_24h: parse_str_f64(item, "volume24h"),
            turnover_24h: parse_str_f64(item, "turnover24h"),
            high_price_24h: parse_str_f64(item, "highPrice24h"),
            low_price_24h: parse_str_f64(item, "lowPrice24h"),
            prev_price_24h: parse_str_f64(item, "prevPrice24h"),
            open_interest: parse_str_f64(item, "openInterest"),
            funding_rate: parse_str_f64(item, "fundingRate"),
            next_funding_time: parse_str(item, "nextFundingTime"),
        });
    }
    Ok(tickers)
}

/// Parse orderbook from Bybit response result.
/// 從 Bybit 回應結果中解析訂單簿。
///
/// Bybit orderbook format:
///   { "s": "BTCUSDT", "b": [["65000","1.5"], ...], "a": [["65001","0.8"], ...],
///     "ts": 1700000000000, "u": 12345 }
pub(super) fn parse_orderbook(result: &serde_json::Value) -> BybitResult<OrderbookSnapshot> {
    let symbol = parse_str(result, "s");
    let ts = result.get("ts").and_then(|v| v.as_u64()).unwrap_or(0);
    let update_id = result.get("u").and_then(|v| v.as_u64()).unwrap_or(0);

    let bids = parse_price_levels(result, "b");
    let asks = parse_price_levels(result, "a");

    Ok(OrderbookSnapshot {
        symbol,
        bids,
        asks,
        ts,
        update_id,
    })
}

/// Parse price levels from orderbook side (bids or asks).
/// 從訂單簿側（買盤或賣盤）解析價格層級。
///
/// Format: [["65000","1.5"], ["64999","2.0"], ...]
pub(super) fn parse_price_levels(obj: &serde_json::Value, field: &str) -> Vec<[f64; 2]> {
    obj.get(field)
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|level| {
                    let level_arr = level.as_array()?;
                    if level_arr.len() >= 2 {
                        let price = level_arr[0].as_str()?.parse::<f64>().ok()?;
                        let size = level_arr[1].as_str()?.parse::<f64>().ok()?;
                        Some([price, size])
                    } else {
                        None
                    }
                })
                .collect()
        })
        .unwrap_or_default()
}
