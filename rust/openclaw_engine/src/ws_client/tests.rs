//! Unit tests for `ws_client` module.
//! `ws_client` 模組單元測試。
//!
//! MODULE_NOTE (EN): All tests use only the public surface exposed by the
//!   parent module (parsers, BACKOFF_POLICY constants, WsState, etc.) to
//!   keep them stable across future internal refactors.
//! MODULE_NOTE (中): 所有測試僅透過 parent 暴露的公開介面（parsers、
//!   BACKOFF_POLICY 常量、WsState 等）測試，以維持未來內部重構穩定性。

use super::connection::WsState;
use super::parsers::{
    extract_symbol_from_topic, parse_adl_notice_item, parse_kline_item, parse_liquidation_item,
    parse_orderbook_snapshot, parse_price_limit_item, parse_ticker_item, parse_trade_item,
};
use super::run_loop::{BACKOFF_POLICY, SUBSCRIBE_BATCH_SIZE};
use std::time::Duration;

#[test]
fn test_extract_symbol_trade_topic() {
    assert_eq!(
        extract_symbol_from_topic("publicTrade.BTCUSDT"),
        Some("BTCUSDT".into())
    );
}

#[test]
fn test_extract_symbol_kline_topic() {
    assert_eq!(
        extract_symbol_from_topic("kline.1.BTCUSDT"),
        Some("BTCUSDT".into())
    );
}

#[test]
fn test_extract_symbol_empty() {
    assert_eq!(extract_symbol_from_topic(""), None);
}

#[test]
fn test_parse_trade_item() {
    let item = serde_json::json!({
        "p": "65000.50",
        "v": "0.123",
        "T": 1700000000000_u64,
        "S": "Buy"
    });
    let event = parse_trade_item(&item, "publicTrade.BTCUSDT").unwrap();
    assert_eq!(event.symbol, "BTCUSDT");
    assert!((event.last_price - 65000.50).abs() < f64::EPSILON);
    assert_eq!(event.ts_ms, 1_700_000_000_000);
    assert!((event.volume_24h - 0.123).abs() < f64::EPSILON);
}

#[test]
fn test_parse_trade_item_missing_price() {
    let item = serde_json::json!({"v": "0.1"});
    assert!(parse_trade_item(&item, "publicTrade.BTCUSDT").is_none());
}

#[test]
fn test_parse_kline_item_confirmed() {
    let item = serde_json::json!({
        "start": 1700000000000_u64,
        "end": 1700000060000_u64,
        "open": "64500.0",
        "close": "65000.0",
        "high": "65100.0",
        "low": "64400.0",
        "volume": "100.5",
        "confirm": true,
    });
    let event = parse_kline_item(&item, "kline.1.BTCUSDT").unwrap();
    assert_eq!(event.symbol, "BTCUSDT");
    assert!((event.last_price - 65000.0).abs() < f64::EPSILON);
    assert!((event.volume_24h - 100.5).abs() < f64::EPSILON);
}

#[test]
fn test_parse_kline_item_unconfirmed_dropped() {
    let item = serde_json::json!({
        "start": 1700000000000_u64,
        "close": "65000.0",
        "volume": "100.5",
        "confirm": false,
    });
    assert!(parse_kline_item(&item, "kline.1.BTCUSDT").is_none());
}

#[test]
fn test_parse_kline_item_confirm_missing_treated_as_unconfirmed() {
    let item = serde_json::json!({
        "start": 1700000000000_u64,
        "close": "65000.0",
        "volume": "100.5",
    });
    assert!(parse_kline_item(&item, "kline.1.BTCUSDT").is_none());
}

#[test]
fn test_parse_kline_item_missing_close() {
    let item = serde_json::json!({"start": 1700000000000_u64, "confirm": true});
    assert!(parse_kline_item(&item, "kline.1.BTCUSDT").is_none());
}

#[test]
fn test_parse_orderbook_snapshot() {
    let data = vec![serde_json::json!({
        "s": "BTCUSDT",
        "b": [["65000.0", "1.5"], ["64999.0", "2.0"]],
        "a": [["65001.0", "0.8"], ["65002.0", "1.2"]],
        "ts": 1700000000000_u64
    })];
    let event = parse_orderbook_snapshot(&data, "orderbook.50.BTCUSDT").unwrap();
    assert_eq!(event.symbol, "BTCUSDT");
    assert!((event.bid_price - 65000.0).abs() < f64::EPSILON);
    assert!((event.ask_price - 65001.0).abs() < f64::EPSILON);
    assert!((event.last_price - 65000.5).abs() < f64::EPSILON); // mid price
    assert_eq!(event.metadata.get("type").unwrap(), "orderbook");
}

#[test]
fn test_parse_ticker_item() {
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "lastPrice": "65500.50",
        "volume24h": "12345.67",
        "bid1Price": "65500.0",
        "ask1Price": "65501.0",
        "ts": "1700000000000"
    });
    let event = parse_ticker_item(&item, "tickers.BTCUSDT").unwrap();
    assert_eq!(event.symbol, "BTCUSDT");
    assert!((event.last_price - 65500.50).abs() < f64::EPSILON);
    assert!((event.volume_24h - 12345.67).abs() < 0.01);
    assert!((event.bid_price - 65500.0).abs() < f64::EPSILON);
    assert_eq!(event.metadata.get("type").unwrap(), "ticker");
    // EDGE-P2-2: absent openInterest → None (no panic).
    // EDGE-P2-2：缺少 openInterest → None（不 panic）。
    assert!(event.open_interest.is_none());
}

/// W1 sub-task 3 (E1-γ, 2026-05-11): parser extracts nextFundingTime
/// (string-encoded i64 ms epoch); absent → None；malformed → None；非正整數 → None。
#[test]
fn test_parse_ticker_item_next_funding_ms() {
    // 1) absent → None
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "lastPrice": "65500.50",
        "volume24h": "12345.67",
        "bid1Price": "65500.0",
        "ask1Price": "65501.0",
        "ts": "1700000000000"
    });
    let ev = parse_ticker_item(&item, "tickers.BTCUSDT").unwrap();
    assert!(ev.next_funding_ms.is_none(), "absent → None");

    // 2) string-encoded ms epoch → Some
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "lastPrice": "65500.50",
        "volume24h": "12345.67",
        "bid1Price": "65500.0",
        "ask1Price": "65501.0",
        "ts": "1700000000000",
        "nextFundingTime": "1700000028800000"
    });
    let ev = parse_ticker_item(&item, "tickers.BTCUSDT").unwrap();
    assert_eq!(ev.next_funding_ms, Some(1_700_000_028_800_000));

    // 3) malformed string → None
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "lastPrice": "65500.50",
        "volume24h": "12345.67",
        "bid1Price": "65500.0",
        "ask1Price": "65501.0",
        "ts": "1700000000000",
        "nextFundingTime": "not-a-number"
    });
    let ev = parse_ticker_item(&item, "tickers.BTCUSDT").unwrap();
    assert!(ev.next_funding_ms.is_none(), "malformed → None");

    // 4) zero or negative → None (filter t > 0)
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "lastPrice": "65500.50",
        "volume24h": "12345.67",
        "bid1Price": "65500.0",
        "ask1Price": "65501.0",
        "ts": "1700000000000",
        "nextFundingTime": "0"
    });
    let ev = parse_ticker_item(&item, "tickers.BTCUSDT").unwrap();
    assert!(ev.next_funding_ms.is_none(), "zero → None");

    // 5) integer encoded (defensive — Bybit always uses string but be liberal)
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "lastPrice": "65500.50",
        "volume24h": "12345.67",
        "bid1Price": "65500.0",
        "ask1Price": "65501.0",
        "ts": "1700000000000",
        "nextFundingTime": 1_700_000_028_800_000_i64
    });
    let ev = parse_ticker_item(&item, "tickers.BTCUSDT").unwrap();
    assert_eq!(ev.next_funding_ms, Some(1_700_000_028_800_000));
}

/// EDGE-P2-2: parser extracts openInterest (string-encoded f64).
/// EDGE-P2-2：parser 正確提取 openInterest（字串 f64）。
#[test]
fn test_parse_ticker_item_open_interest() {
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "lastPrice": "65500.50",
        "volume24h": "12345.67",
        "bid1Price": "65500.0",
        "ask1Price": "65501.0",
        "ts": "1700000000000",
        "openInterest": "12345.678",
        "openInterestValue": "808717430.00"
    });
    let event = parse_ticker_item(&item, "tickers.BTCUSDT").unwrap();
    // Contract-count OI is plumbed through.
    assert!((event.open_interest.unwrap() - 12345.678).abs() < 1e-9);
}

/// EDGE-P2-2: malformed openInterest string → None (fail-closed, no panic).
/// EDGE-P2-2：openInterest 格式異常 → None（fail-closed，不 panic）。
#[test]
fn test_parse_ticker_item_open_interest_malformed() {
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "lastPrice": "65500.50",
        "volume24h": "12345.67",
        "bid1Price": "65500.0",
        "ask1Price": "65501.0",
        "ts": "1700000000000",
        "openInterest": "not-a-number"
    });
    let event = parse_ticker_item(&item, "tickers.BTCUSDT").unwrap();
    assert!(event.open_interest.is_none());
}

/// EDGE-P2-2 FUP: NaN / Infinity / negative OI → None (parser hardening).
/// `0.0` is legitimate (fully closed segment) and must be preserved.
/// EDGE-P2-2 FUP：NaN / Infinity / 負值 → None；`0.0` 為合法值必須保留。
#[test]
fn test_parse_ticker_item_open_interest_nan_inf_rejected() {
    let base = |oi: &str| {
        serde_json::json!({
            "symbol": "BTCUSDT",
            "lastPrice": "65500.50",
            "volume24h": "12345.67",
            "bid1Price": "65500.0",
            "ask1Price": "65501.0",
            "ts": "1700000000000",
            "openInterest": oi
        })
    };
    // NaN → rejected.
    let ev = parse_ticker_item(&base("NaN"), "tickers.BTCUSDT").unwrap();
    assert!(
        ev.open_interest.is_none(),
        "NaN openInterest must be rejected"
    );
    // +Infinity → rejected.
    let ev = parse_ticker_item(&base("Infinity"), "tickers.BTCUSDT").unwrap();
    assert!(
        ev.open_interest.is_none(),
        "+Inf openInterest must be rejected"
    );
    // -Infinity → rejected.
    let ev = parse_ticker_item(&base("-Infinity"), "tickers.BTCUSDT").unwrap();
    assert!(
        ev.open_interest.is_none(),
        "-Inf openInterest must be rejected"
    );
    // Negative finite → rejected.
    let ev = parse_ticker_item(&base("-5.0"), "tickers.BTCUSDT").unwrap();
    assert!(
        ev.open_interest.is_none(),
        "negative openInterest must be rejected"
    );
    // Zero → legitimate, preserved (fully closed market segment).
    let ev = parse_ticker_item(&base("0"), "tickers.BTCUSDT").unwrap();
    assert_eq!(
        ev.open_interest,
        Some(0.0),
        "zero openInterest is legitimate and must be preserved"
    );
    // Also guard the decimal zero spelling.
    let ev = parse_ticker_item(&base("0.0"), "tickers.BTCUSDT").unwrap();
    assert_eq!(ev.open_interest, Some(0.0));
}

#[test]
fn test_parse_liquidation_item() {
    let item = serde_json::json!({
        "price": "64000.0",
        "side": "Sell",
        "size": "2.5",
        "updatedTime": 1700000000000_u64
    });
    let event = parse_liquidation_item(&item, "liquidation.BTCUSDT").unwrap();
    assert_eq!(event.symbol, "BTCUSDT");
    assert!((event.last_price - 64000.0).abs() < f64::EPSILON);
    assert_eq!(event.metadata.get("type").unwrap(), "liquidation");
    assert_eq!(event.metadata.get("side").unwrap(), "Sell");
    assert_eq!(event.metadata.get("qty").unwrap(), "2.5");
}

#[test]
fn test_parse_price_limit_item() {
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "maxPrice": "70000.0",
        "minPrice": "60000.0",
        "ts": 1700000000000_u64
    });
    let event = parse_price_limit_item(&item).unwrap();
    assert_eq!(event.symbol, "BTCUSDT");
    assert_eq!(event.metadata.get("type").unwrap(), "price_limit");
    assert_eq!(event.metadata.get("max_price").unwrap(), "70000.0");
    assert_eq!(event.metadata.get("min_price").unwrap(), "60000.0");
}

#[test]
fn test_parse_adl_notice_item() {
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "side": "Buy",
        "adlRankIndicator": 4,
        "ts": 1700000000000_u64
    });
    let event = parse_adl_notice_item(&item).unwrap();
    assert_eq!(event.symbol, "BTCUSDT");
    // P-02: Verify structured field is populated.
    assert_eq!(event.adl_rank, Some(4));
    // Legacy metadata still populated for backward compat.
    assert_eq!(event.metadata.get("type").unwrap(), "adl_notice");
    assert_eq!(event.metadata.get("adl_rank").unwrap(), "4");
    assert_eq!(event.metadata.get("side").unwrap(), "Buy");
}

#[test]
fn test_ws_state_display() {
    assert_eq!(format!("{}", WsState::Connected), "Connected");
    assert_eq!(format!("{}", WsState::Reconnecting), "Reconnecting");
    assert_eq!(format!("{}", WsState::Disconnected), "Disconnected");
    assert_eq!(format!("{}", WsState::Connecting), "Connecting");
}

#[test]
fn test_backoff_calculation() {
    let base: u64 = 3000;
    // attempt 1: 3000 * 2^1 = 6000
    let delay1 = BACKOFF_POLICY.next_delay_with_base(base, 1);
    assert_eq!(delay1, Duration::from_millis(6000));
    // attempt 5: 3000 * 2^5 = 96000 → capped at 60000
    let delay5 = BACKOFF_POLICY.next_delay_with_base(base, 5);
    assert_eq!(delay5, Duration::from_millis(BACKOFF_POLICY.max_ms));
}

/// EN: Subscribe batch size matches Bybit per-call limit (10);
///     BACKOFF_POLICY carries the same numeric constants as pre-extraction.
/// 中文: 訂閱批次大小符合 Bybit 每次調用限制（10）；
///     BACKOFF_POLICY 承載與提取前相同的數值常量。
#[test]
fn test_subscribe_batch_size_constant() {
    assert_eq!(SUBSCRIBE_BATCH_SIZE, 10);
    assert_eq!(BACKOFF_POLICY.max_ms, 60_000);
    assert_eq!(BACKOFF_POLICY.multiplier, 2);
}

/// EN: Backoff progression — monotonically increasing until cap.
/// 中文: 退避遞增 — 單調遞增直到上限。
#[test]
fn test_backoff_monotonic_progression() {
    let base: u64 = 3000;
    let mut prev = Duration::from_millis(0);
    for attempt in 1..=10u32 {
        let delay = BACKOFF_POLICY.next_delay_with_base(base, attempt);
        assert!(
            delay >= prev,
            "delay should be monotonically non-decreasing"
        );
        assert!(
            delay <= Duration::from_millis(BACKOFF_POLICY.max_ms),
            "delay should never exceed max"
        );
        prev = delay;
    }
    // After enough attempts, should be capped at max
    assert_eq!(prev, Duration::from_millis(BACKOFF_POLICY.max_ms));
}

/// EN: extract_symbol handles multi-segment topics (kline.interval.SYMBOL).
/// 中文: extract_symbol 處理多段主題（kline.interval.SYMBOL）。
#[test]
fn test_extract_symbol_multi_segment() {
    // 3-segment: kline.1.BTCUSDT → BTCUSDT
    assert_eq!(
        extract_symbol_from_topic("kline.1.BTCUSDT"),
        Some("BTCUSDT".into())
    );
    // 2-segment: tickers.ETHUSDT → ETHUSDT
    assert_eq!(
        extract_symbol_from_topic("tickers.ETHUSDT"),
        Some("ETHUSDT".into())
    );
    // 3-segment orderbook: orderbook.50.XRPUSDT → XRPUSDT
    assert_eq!(
        extract_symbol_from_topic("orderbook.50.XRPUSDT"),
        Some("XRPUSDT".into())
    );
    // Edge: trailing dot → empty segment → None
    assert_eq!(extract_symbol_from_topic("kline.1."), None);
    // Single segment (no dot) → just the string itself
    assert_eq!(extract_symbol_from_topic("BTCUSDT"), Some("BTCUSDT".into()));
}
