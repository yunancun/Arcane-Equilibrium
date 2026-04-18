//! Tests for market_data_client — parsing and serialization round-trips.
//! 市場數據客戶端測試 — 解析和序列化往返測試。

use super::*;
use parsers::{
    parse_kline_list, parse_orderbook, parse_price_levels, parse_str, parse_str_f64,
    parse_ticker_list,
};

/// Test parsing kline list from Bybit response format.
/// 測試從 Bybit 回應格式解析 K 線列表。
#[test]
fn test_parse_kline_list() {
    let result = serde_json::json!({
        "list": [
            ["1700000000000", "65000.5", "66000", "64000", "65500.25", "100.5", "6500000"],
            ["1700003600000", "65500.25", "67000", "65000", "66800", "200", "13200000"]
        ]
    });
    let bars = parse_kline_list(&result).unwrap();
    assert_eq!(bars.len(), 2);
    assert_eq!(bars[0].start_time, 1700000000000);
    assert!((bars[0].open - 65000.5).abs() < 1e-10);
    assert!((bars[0].high - 66000.0).abs() < 1e-10);
    assert!((bars[0].low - 64000.0).abs() < 1e-10);
    assert!((bars[0].close - 65500.25).abs() < 1e-10);
    assert!((bars[0].volume - 100.5).abs() < 1e-10);
    assert!((bars[0].turnover - 6500000.0).abs() < 1e-10);
    assert_eq!(bars[1].start_time, 1700003600000);
}

/// Test parsing kline with empty list.
/// 測試解析空 K 線列表。
#[test]
fn test_parse_kline_empty() {
    let result = serde_json::json!({"list": []});
    let bars = parse_kline_list(&result).unwrap();
    assert!(bars.is_empty());
}

/// Test parsing kline with missing list field.
/// 測試解析缺少 list 欄位的 K 線。
#[test]
fn test_parse_kline_missing_list() {
    let result = serde_json::json!({});
    let bars = parse_kline_list(&result).unwrap();
    assert!(bars.is_empty());
}

/// Test parsing kline with short arrays (graceful skip).
/// 測試解析短數組的 K 線（優雅跳過）。
#[test]
fn test_parse_kline_short_array() {
    let result = serde_json::json!({
        "list": [
            ["1700000000000", "65000"],
            ["1700003600000", "65500.25", "67000", "65000", "66800", "200", "13200000"]
        ]
    });
    let bars = parse_kline_list(&result).unwrap();
    assert_eq!(bars.len(), 1); // First item skipped due to < 7 elements
}

/// Test parsing ticker list.
/// 測試解析行情列表。
#[test]
fn test_parse_ticker_list() {
    let result = serde_json::json!({
        "list": [{
            "symbol": "BTCUSDT",
            "lastPrice": "65000.50",
            "bid1Price": "65000.00",
            "ask1Price": "65001.00",
            "volume24h": "50000.5",
            "turnover24h": "3250000000",
            "highPrice24h": "66000",
            "lowPrice24h": "64000",
            "prevPrice24h": "64500",
            "openInterest": "120000",
            "fundingRate": "0.0001",
            "nextFundingTime": "1700006400000",
            "price24hPcnt": "0.0077"
        }]
    });
    let tickers = parse_ticker_list(&result).unwrap();
    assert_eq!(tickers.len(), 1);
    assert_eq!(tickers[0].symbol, "BTCUSDT");
    assert!((tickers[0].last_price - 65000.50).abs() < 1e-10);
    assert!((tickers[0].bid1_price - 65000.0).abs() < 1e-10);
    assert!((tickers[0].ask1_price - 65001.0).abs() < 1e-10);
    assert!((tickers[0].volume_24h - 50000.5).abs() < 1e-10);
    assert!((tickers[0].funding_rate - 0.0001).abs() < 1e-10);
    assert_eq!(tickers[0].next_funding_time, "1700006400000");
    assert!((tickers[0].price_change_24h_pct - 0.0077).abs() < 1e-10);
}

/// Test parsing orderbook snapshot.
/// 測試解析訂單簿快照。
#[test]
fn test_parse_orderbook() {
    let result = serde_json::json!({
        "s": "BTCUSDT",
        "b": [["65000.0", "1.5"], ["64999.5", "2.0"]],
        "a": [["65001.0", "0.8"], ["65002.0", "1.2"]],
        "ts": 1700000000000_u64,
        "u": 12345_u64
    });
    let ob = parse_orderbook(&result).unwrap();
    assert_eq!(ob.symbol, "BTCUSDT");
    assert_eq!(ob.bids.len(), 2);
    assert_eq!(ob.asks.len(), 2);
    assert!((ob.bids[0][0] - 65000.0).abs() < 1e-10);
    assert!((ob.bids[0][1] - 1.5).abs() < 1e-10);
    assert!((ob.asks[0][0] - 65001.0).abs() < 1e-10);
    assert_eq!(ob.ts, 1700000000000);
    assert_eq!(ob.update_id, 12345);
}

/// Test parsing orderbook with empty sides.
/// 測試解析空側的訂單簿。
#[test]
fn test_parse_orderbook_empty() {
    let result = serde_json::json!({"s": "ETHUSDT", "b": [], "a": [], "ts": 0, "u": 0});
    let ob = parse_orderbook(&result).unwrap();
    assert_eq!(ob.symbol, "ETHUSDT");
    assert!(ob.bids.is_empty());
    assert!(ob.asks.is_empty());
}

/// Test parsing funding records.
/// 測試解析資金費率記錄。
#[test]
fn test_parse_funding_record() {
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "fundingRate": "0.00015",
        "fundingRateTimestamp": "1700006400000"
    });
    let record = FundingRecord {
        symbol: parse_str(&item, "symbol"),
        funding_rate: parse_str_f64(&item, "fundingRate"),
        funding_rate_timestamp: parse_str(&item, "fundingRateTimestamp"),
    };
    assert_eq!(record.symbol, "BTCUSDT");
    assert!((record.funding_rate - 0.00015).abs() < 1e-10);
}

/// Test parsing long/short ratio record.
/// 測試解析多空比記錄。
#[test]
fn test_parse_long_short_record() {
    let item = serde_json::json!({
        "buyRatio": "0.55",
        "sellRatio": "0.45",
        "timestamp": "1700000000"
    });
    let record = LongShortRecord {
        buy_ratio: parse_str_f64(&item, "buyRatio"),
        sell_ratio: parse_str_f64(&item, "sellRatio"),
        timestamp: parse_str(&item, "timestamp"),
    };
    assert!((record.buy_ratio - 0.55).abs() < 1e-10);
    assert!((record.sell_ratio - 0.45).abs() < 1e-10);
}

/// Test parsing risk limit tier.
/// 測試解析風險限額層級。
#[test]
fn test_parse_risk_limit_tier() {
    let item = serde_json::json!({
        "id": 1,
        "symbol": "BTCUSDT",
        "riskLimitValue": "2000000",
        "maxLeverage": "100",
        "initialMargin": "0.01",
        "maintenanceMargin": "0.005"
    });
    let tier = RiskLimitTier {
        id: item.get("id").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
        symbol: parse_str(&item, "symbol"),
        risk_limit_value: parse_str_f64(&item, "riskLimitValue"),
        max_leverage: parse_str_f64(&item, "maxLeverage"),
        initial_margin: parse_str_f64(&item, "initialMargin"),
        maintenance_margin: parse_str_f64(&item, "maintenanceMargin"),
    };
    assert_eq!(tier.id, 1);
    assert_eq!(tier.symbol, "BTCUSDT");
    assert!((tier.risk_limit_value - 2000000.0).abs() < 1e-10);
    assert!((tier.max_leverage - 100.0).abs() < 1e-10);
}

/// Test parsing recent trade.
/// 測試解析近期成交。
#[test]
fn test_parse_recent_trade() {
    let item = serde_json::json!({
        "execId": "abc123",
        "symbol": "BTCUSDT",
        "price": "65000.50",
        "size": "0.01",
        "side": "Buy",
        "time": "1700000000000",
        "isBlockTrade": false
    });
    let trade = RecentTrade {
        exec_id: parse_str(&item, "execId"),
        symbol: parse_str(&item, "symbol"),
        price: parse_str_f64(&item, "price"),
        size: parse_str_f64(&item, "size"),
        side: parse_str(&item, "side"),
        time: parse_str(&item, "time"),
        is_block_trade: item
            .get("isBlockTrade")
            .and_then(|v| v.as_bool())
            .unwrap_or(false),
    };
    assert_eq!(trade.exec_id, "abc123");
    assert!((trade.price - 65000.50).abs() < 1e-10);
    assert!(!trade.is_block_trade);
}

/// Test helper parse_str_f64 with various inputs.
/// 測試輔助函數 parse_str_f64 的各種輸入。
#[test]
fn test_parse_str_f64_various() {
    let obj = serde_json::json!({"a": "123.45", "b": "bad", "c": 999, "d": ""});
    assert!((parse_str_f64(&obj, "a") - 123.45).abs() < 1e-10);
    assert!((parse_str_f64(&obj, "b") - 0.0).abs() < 1e-10);
    assert!((parse_str_f64(&obj, "c") - 0.0).abs() < 1e-10); // not a string
    assert!((parse_str_f64(&obj, "d") - 0.0).abs() < 1e-10); // empty string
    assert!((parse_str_f64(&obj, "missing") - 0.0).abs() < 1e-10);
}

/// Test helper parse_str with missing field.
/// 測試輔助函數 parse_str 處理缺失欄位。
#[test]
fn test_parse_str_missing() {
    let obj = serde_json::json!({"a": "hello"});
    assert_eq!(parse_str(&obj, "a"), "hello");
    assert_eq!(parse_str(&obj, "missing"), "");
}

/// Test price level parsing for orderbook.
/// 測試訂單簿價格層級解析。
#[test]
fn test_parse_price_levels() {
    let obj = serde_json::json!({
        "levels": [["100.5", "2.0"], ["99.5", "3.0"], ["bad", "1.0"]]
    });
    let levels = parse_price_levels(&obj, "levels");
    // "bad" entry is filtered out / "bad" 條目被過濾
    assert_eq!(levels.len(), 2);
    assert!((levels[0][0] - 100.5).abs() < 1e-10);
    assert!((levels[1][1] - 3.0).abs() < 1e-10);
}

/// Test struct serialization round-trip (KlineBar).
/// 測試結構體序列化往返（KlineBar）。
#[test]
fn test_kline_bar_serde() {
    let bar = KlineBar {
        start_time: 1700000000000,
        open: 65000.0,
        high: 66000.0,
        low: 64000.0,
        close: 65500.0,
        volume: 100.0,
        turnover: 6500000.0,
    };
    let json = serde_json::to_string(&bar).unwrap();
    let deser: KlineBar = serde_json::from_str(&json).unwrap();
    assert_eq!(deser.start_time, bar.start_time);
    assert!((deser.open - bar.open).abs() < 1e-10);
}

/// Test TickerInfo default fields when JSON has missing values.
/// 測試 JSON 缺失值時 TickerInfo 的默認欄位。
#[test]
fn test_ticker_partial_fields() {
    let result = serde_json::json!({
        "list": [{"symbol": "XRPUSDT", "lastPrice": "0.55"}]
    });
    let tickers = parse_ticker_list(&result).unwrap();
    assert_eq!(tickers.len(), 1);
    assert_eq!(tickers[0].symbol, "XRPUSDT");
    assert!((tickers[0].last_price - 0.55).abs() < 1e-10);
    // Missing fields default to 0.0 / 缺失欄位默認為 0.0
    assert!((tickers[0].bid1_price - 0.0).abs() < 1e-10);
    assert!((tickers[0].funding_rate - 0.0).abs() < 1e-10);
}
