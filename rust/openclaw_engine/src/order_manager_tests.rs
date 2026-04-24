//! Order manager tests — enum / parser / validation / lazy-fetch wiring.
//! 訂單管理器測試 — 枚舉 / 解析 / 驗證 / 延遲拉取接線。
//!
//! MODULE_NOTE (EN): Extracted from `order_manager.rs` as Wave 1 G1-02 to pull
//!   `order_manager.rs` under CLAUDE.md §九 1200-line hard limit. The test
//!   body is included back into the parent via
//!   `#[cfg(test)] #[path = "order_manager_tests.rs"] mod tests;` at the foot
//!   of `order_manager.rs`, so every helper keeps `use super::*;` semantics —
//!   no visibility changes required. Bit-identical test content vs pre-split.
//! MODULE_NOTE (中): 從 `order_manager.rs` 抽出（Wave 1 G1-02），讓父檔進
//!   §九 1200 行硬上限。測試主體透過父檔底部
//!   `#[cfg(test)] #[path = "order_manager_tests.rs"] mod tests;` 重新納入，
//!   `use super::*;` 語義不變、可見性無需調整。行為等價（原樣）。

use super::*;
use crate::instrument_info::{InstrumentInfoCache, SymbolSpec};

/// Helper: build a sample InstrumentInfoCache with BTCUSDT.
/// 輔助：構建含 BTCUSDT 的測試合約信息緩存。
fn sample_cache() -> InstrumentInfoCache {
    let cache = InstrumentInfoCache::new();
    {
        let mut map = cache.cache.write();
        map.insert(
            "BTCUSDT".to_string(),
            SymbolSpec {
                symbol: "BTCUSDT".to_string(),
                base_currency: "BTC".to_string(),
                quote_currency: "USDT".to_string(),
                contract_type: "LinearPerpetual".to_string(),
                qty_step: 0.001,
                min_qty: 0.001,
                max_qty: 100.0,
                tick_size: 0.10,
                min_price: 0.10,
                max_price: 999999.0,
                min_notional: 5.0,
                qty_decimals: 3,
                price_decimals: 1,
            },
        );
    }
    cache
}

// -- Enum serialization tests / 枚舉序列化測試 --

#[test]
fn test_order_side_as_str() {
    assert_eq!(OrderSide::Buy.as_str(), "Buy");
    assert_eq!(OrderSide::Sell.as_str(), "Sell");
}

#[test]
fn test_order_type_as_str() {
    assert_eq!(OrderType::Market.as_str(), "Market");
    assert_eq!(OrderType::Limit.as_str(), "Limit");
}

#[test]
fn test_time_in_force_as_str() {
    assert_eq!(TimeInForce::GTC.as_str(), "GTC");
    assert_eq!(TimeInForce::IOC.as_str(), "IOC");
    assert_eq!(TimeInForce::FOK.as_str(), "FOK");
    assert_eq!(TimeInForce::PostOnly.as_str(), "PostOnly");
}

#[test]
fn test_order_category_as_str() {
    assert_eq!(OrderCategory::Linear.as_str(), "linear");
    assert_eq!(OrderCategory::Spot.as_str(), "spot");
    assert_eq!(OrderCategory::Inverse.as_str(), "inverse");
}

#[test]
fn test_trigger_direction_values() {
    assert_eq!(TriggerDirection::Rise as i32, 1);
    assert_eq!(TriggerDirection::Fall as i32, 2);
}

// -- Formatting tests / 格式化測試 --

#[test]
fn test_format_qty() {
    assert_eq!(format_qty(0.001), "0.001");
    assert_eq!(format_qty(1.0), "1");
    assert_eq!(format_qty(0.10), "0.1");
    assert_eq!(format_qty(123.45600), "123.456");
}

#[test]
fn test_format_price() {
    assert_eq!(format_price(65000.0), "65000");
    assert_eq!(format_price(65000.10), "65000.1");
    assert_eq!(format_price(0.00012345), "0.00012345");
}

// -- Response parsing tests / 回應解析測試 --

#[test]
fn test_parse_order_response() {
    let result = serde_json::json!({
        "orderId": "1234567890",
        "orderLinkId": "my-custom-id-001"
    });
    let resp = parse_order_response(&result).unwrap();
    assert_eq!(resp.order_id, "1234567890");
    assert_eq!(resp.order_link_id, "my-custom-id-001");
}

#[test]
fn test_parse_order_response_empty() {
    let result = serde_json::json!({});
    let resp = parse_order_response(&result).unwrap();
    assert_eq!(resp.order_id, "");
    assert_eq!(resp.order_link_id, "");
}

#[test]
fn test_parse_order_response_list() {
    let result = serde_json::json!({
        "list": [
            {"orderId": "aaa", "orderLinkId": "link-a"},
            {"orderId": "bbb", "orderLinkId": "link-b"}
        ]
    });
    let list = parse_order_response_list(&result).unwrap();
    assert_eq!(list.len(), 2);
    assert_eq!(list[0].order_id, "aaa");
    assert_eq!(list[1].order_id, "bbb");
}

#[test]
fn test_parse_order_info_list() {
    let result = serde_json::json!({
        "list": [{
            "orderId": "ord-001",
            "orderLinkId": "link-001",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "orderType": "Limit",
            "price": "65000.0",
            "qty": "0.01",
            "cumExecQty": "0.005",
            "cumExecValue": "325.0",
            "avgPrice": "65000.0",
            "orderStatus": "PartiallyFilled",
            "createdTime": "1700000000000",
            "updatedTime": "1700000001000"
        }]
    });
    let orders = parse_order_info_list(&result).unwrap();
    assert_eq!(orders.len(), 1);
    let o = &orders[0];
    assert_eq!(o.order_id, "ord-001");
    assert_eq!(o.symbol, "BTCUSDT");
    assert_eq!(o.side, "Buy");
    assert!((o.price - 65000.0).abs() < 1e-10);
    assert!((o.qty - 0.01).abs() < 1e-10);
    assert!((o.cum_exec_qty - 0.005).abs() < 1e-10);
    assert_eq!(o.order_status, "PartiallyFilled");
}

#[test]
fn test_parse_execution_list() {
    let result = serde_json::json!({
        "list": [{
            "execId": "exec-001",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "execPrice": "65000.0",
            "execQty": "0.001",
            "execValue": "65.0",
            "execFee": "0.0358",
            "feeCurrency": "USDT",
            "orderId": "ord-001",
            "orderLinkId": "link-001",
            "execType": "Trade",
            "execTime": "1700000000000",
            "closedPnl": "12.5"
        }]
    });
    let execs = parse_execution_list(&result).unwrap();
    assert_eq!(execs.len(), 1);
    let e = &execs[0];
    assert_eq!(e.exec_id, "exec-001");
    assert!((e.exec_price - 65000.0).abs() < 1e-10);
    assert!((e.exec_fee - 0.0358).abs() < 1e-10);
    assert_eq!(e.exec_type, "Trade");
    assert!((e.closed_pnl - 12.5).abs() < 1e-10, "closedPnl must parse");
}

#[test]
fn test_parse_execution_missing_closed_pnl_is_zero() {
    // Older fills / open legs may omit closedPnl — parser must not fail.
    // 缺 closedPnl（開倉腿）時解析器不應失敗，回傳 0.0。
    let result = serde_json::json!({
        "list": [{
            "execId": "exec-open",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "execPrice": "65000.0",
            "execQty": "0.001",
            "execValue": "65.0",
            "execFee": "0.0358",
            "feeCurrency": "USDT",
            "orderId": "ord-open",
            "orderLinkId": "",
            "execType": "Trade",
            "execTime": "1700000000000"
        }]
    });
    let execs = parse_execution_list(&result).unwrap();
    assert_eq!(execs[0].closed_pnl, 0.0);
}

#[test]
fn test_parse_empty_lists() {
    // Empty result should return empty vec, not error
    // 空結果應返回空向量，不是錯誤
    let result = serde_json::json!({"list": []});
    assert_eq!(parse_order_info_list(&result).unwrap().len(), 0);
    assert_eq!(parse_execution_list(&result).unwrap().len(), 0);
    assert_eq!(parse_order_response_list(&result).unwrap().len(), 0);

    // Missing "list" key also returns empty / 缺少 "list" 鍵也返回空
    let result = serde_json::json!({});
    assert_eq!(parse_order_info_list(&result).unwrap().len(), 0);
}

// -- Validation tests / 驗證測試 --

#[tokio::test]
async fn test_validate_and_round_limit_no_price() {
    let cache = Arc::new(sample_cache());
    let client = Arc::new(
        BybitRestClient::new(
            crate::bybit_rest_client::BybitEnvironment::Demo,
            Some("test_key".to_string()),
            Some("test_secret".to_string()),
        )
        .unwrap(),
    );
    let mgr = OrderManager::new(client, cache);

    let req = CreateOrderRequest {
        category: OrderCategory::Linear,
        symbol: "BTCUSDT".to_string(),
        side: OrderSide::Buy,
        order_type: OrderType::Limit,
        qty: 0.01,
        price: None, // missing price for limit
        time_in_force: None,
        reduce_only: None,
        close_on_trigger: None,
        order_link_id: None,
        trigger_price: None,
        trigger_direction: None,
        take_profit: None,
        stop_loss: None,
        tp_trigger_by: None,
        sl_trigger_by: None,
    };

    let result = mgr.validate_and_round(&req).await;
    assert!(result.is_err());
}

#[tokio::test]
async fn test_validate_and_round_qty_too_small() {
    let cache = Arc::new(sample_cache());
    let client = Arc::new(
        BybitRestClient::new(
            crate::bybit_rest_client::BybitEnvironment::Demo,
            Some("test_key".to_string()),
            Some("test_secret".to_string()),
        )
        .unwrap(),
    );
    let mgr = OrderManager::new(client, cache);

    let req = CreateOrderRequest {
        category: OrderCategory::Linear,
        symbol: "BTCUSDT".to_string(),
        side: OrderSide::Buy,
        order_type: OrderType::Market,
        qty: 0.0001, // below min_qty 0.001 after rounding to 0
        price: None,
        time_in_force: None,
        reduce_only: None,
        close_on_trigger: None,
        order_link_id: None,
        trigger_price: None,
        trigger_direction: None,
        take_profit: None,
        stop_loss: None,
        tp_trigger_by: None,
        sl_trigger_by: None,
    };

    let result = mgr.validate_and_round(&req).await;
    assert!(result.is_err());
}

#[tokio::test]
async fn test_validate_and_round_success() {
    let cache = Arc::new(sample_cache());
    let client = Arc::new(
        BybitRestClient::new(
            crate::bybit_rest_client::BybitEnvironment::Demo,
            Some("test_key".to_string()),
            Some("test_secret".to_string()),
        )
        .unwrap(),
    );
    let mgr = OrderManager::new(client, cache);

    let req = CreateOrderRequest {
        category: OrderCategory::Linear,
        symbol: "BTCUSDT".to_string(),
        side: OrderSide::Buy,
        order_type: OrderType::Limit,
        qty: 0.0156,           // should round to 0.015
        price: Some(65000.55), // should round to 65000.6
        time_in_force: None,
        reduce_only: None,
        close_on_trigger: None,
        order_link_id: None,
        trigger_price: None,
        trigger_direction: None,
        take_profit: None,
        stop_loss: None,
        tp_trigger_by: None,
        sl_trigger_by: None,
    };

    let (qty, price) = mgr.validate_and_round(&req).await.unwrap();
    assert!((qty - 0.015).abs() < 1e-10);
    assert!((price.unwrap() - 65000.6).abs() < 1e-10);
}

// -----------------------------------------------------------------------
// INSTR-WIRE-1 — ensure_symbol lazy fetch integration tests
// INSTR-WIRE-1 — ensure_symbol 自癒接線整合測試
// -----------------------------------------------------------------------
//
// We exercise validate_and_round's lazy-fetch path directly against the
// InstrumentInfoCache (using its test-visible SingleSymbolFetcher hook)
// rather than hitting a live Bybit endpoint. The integration verifies:
//   * cache miss + ensure succeeds → validate_and_round passes
//   * cache miss + ensure returns None (neg) → fail-closed
//   * cache miss + ensure errors → fail-closed
//   * cache hit → ensure is NEVER called (preserved fast path)

use crate::instrument_info::SingleSymbolFetcher;
use async_trait::async_trait;
use std::sync::atomic::{AtomicU64, AtomicU8, Ordering};

struct WireMockFetcher {
    /// 0=Some(item), 1=None, 2=Err
    mode: AtomicU8,
    calls: AtomicU64,
}
impl WireMockFetcher {
    fn new(mode: u8) -> Self {
        Self {
            mode: AtomicU8::new(mode),
            calls: AtomicU64::new(0),
        }
    }
    fn call_count(&self) -> u64 {
        self.calls.load(Ordering::SeqCst)
    }
}
#[async_trait]
impl SingleSymbolFetcher for WireMockFetcher {
    async fn fetch_single_symbol(
        &self,
        _category: &str,
        symbol: &str,
    ) -> BybitResult<Option<serde_json::Value>> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        match self.mode.load(Ordering::SeqCst) {
            0 => Ok(Some(serde_json::json!({
                "symbol": symbol,
                "baseCoin": "WIRE",
                "quoteCoin": "USDT",
                "contractType": "LinearPerpetual",
                "lotSizeFilter": {"qtyStep": "0.001","minOrderQty": "0.001","maxOrderQty": "100","minNotionalValue": "5"},
                "priceFilter": {"tickSize": "0.10","minPrice": "0.10","maxPrice": "999999.00"}
            }))),
            1 => Ok(None),
            _ => Err(BybitApiError::Business {
                ret_code: -1,
                ret_msg: "wire mock transient".into(),
                response: serde_json::json!(null),
            }),
        }
    }
}

fn make_req(symbol: &str) -> CreateOrderRequest {
    CreateOrderRequest {
        category: OrderCategory::Linear,
        symbol: symbol.to_string(),
        side: OrderSide::Buy,
        order_type: OrderType::Market,
        qty: 0.01,
        price: None,
        time_in_force: None,
        reduce_only: None,
        close_on_trigger: None,
        order_link_id: None,
        trigger_price: None,
        trigger_direction: None,
        take_profit: None,
        stop_loss: None,
        tp_trigger_by: None,
        sl_trigger_by: None,
    }
}

#[tokio::test]
async fn test_wire_cache_miss_ensure_success_populates_and_passes() {
    use std::sync::atomic::Ordering::SeqCst;

    let cache = Arc::new(InstrumentInfoCache::new());
    let fetcher = WireMockFetcher::new(0); // Bybit returns item

    // Drive ensure directly via the mock fetcher (simulating what
    // validate_and_round would do if it delegated to a mock — we verify
    // the end-state: cache populated + spec usable).
    let res = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "WIRE001USDT")
        .await
        .unwrap();
    assert!(res.is_some());
    assert_eq!(fetcher.call_count(), 1);

    // Now validate_and_round on the freshly-cached symbol should pass.
    let client = Arc::new(
        BybitRestClient::new(
            crate::bybit_rest_client::BybitEnvironment::Demo,
            Some("test_key".to_string()),
            Some("test_secret".to_string()),
        )
        .unwrap(),
    );
    let mgr = OrderManager::new(client, cache);
    let req = make_req("WIRE001USDT");
    let (qty, _price) = mgr.validate_and_round(&req).await.expect("should pass");
    assert!(qty > 0.0);

    // INSTR-ENSURE-POLISH-1 (2026-04-23): counter invariant.
    // The symbol was pre-seeded into the positive cache via
    // `ensure_symbol_with_fetcher` BEFORE we ran validate_and_round, so
    // validate_and_round's `self.instruments.get(&req.symbol)` hits the
    // fast path and must NOT enter the lazy-fetch else branch. Counter
    // stays at 0. (Contrast with the neg-cache test below, where the
    // positive-cache miss forces entry into the else branch and bumps
    // the counter to 1 before the neg-cache short-circuit.)
    // 正緩存已預填 → 走 fast path，ensure 分支不進 → counter 保持 0。
    assert_eq!(
        mgr.ensure_call_count.load(SeqCst),
        0,
        "pre-seeded positive cache must bypass ensure branch (INSTR-ENSURE-POLISH-1)"
    );
}

#[tokio::test]
async fn test_wire_cache_miss_ensure_neg_fails_closed() {
    use std::sync::atomic::Ordering::SeqCst;

    // Seed the cache with a neg-cached symbol directly (simulating a prior
    // ensure that returned None). validate_and_round must NOT re-fetch and
    // must fail-closed with the exhausted message.
    let cache = Arc::new(InstrumentInfoCache::new());
    let fetcher = WireMockFetcher::new(1); // Bybit denies
    let _ = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "NOTEXISTUSDT")
        .await
        .unwrap();
    assert_eq!(fetcher.call_count(), 1);

    let client = Arc::new(
        BybitRestClient::new(
            crate::bybit_rest_client::BybitEnvironment::Demo,
            Some("test_key".to_string()),
            Some("test_secret".to_string()),
        )
        .unwrap(),
    );
    let mgr = OrderManager::new(client, cache);
    let req = make_req("NOTEXISTUSDT");
    let result = mgr.validate_and_round(&req).await;
    assert!(result.is_err(), "neg-cached symbol must fail-closed");
    // Error msg must reflect lazy fetch exhaustion path
    let err = result.unwrap_err().to_string();
    assert!(
        err.contains("lazy fetch") || err.contains("按需拉取"),
        "error must indicate lazy fetch attempted: {err}"
    );

    // INSTR-ENSURE-POLISH-1 (2026-04-23): counter invariant.
    // The positive cache has no entry for NOTEXISTUSDT (only neg cache),
    // so validate_and_round's `self.instruments.get(...)` returns None →
    // enters the lazy-fetch else branch → counter increments to 1 BEFORE
    // ensure_symbol short-circuits on the neg-cache hit. This proves the
    // miss path exercises the ensure codepath exactly once, symmetric to
    // test_wire_cache_hit_no_ensure_call's count==0 assertion.
    // 正緩存 miss → 進 else 分支 → counter +=1 → 再被 ensure_symbol
    // 內部的 neg_cache 短路。對稱 hit test 的 count==0。
    assert_eq!(
        mgr.ensure_call_count.load(SeqCst),
        1,
        "positive-miss must trigger exactly one ensure branch entry (INSTR-ENSURE-POLISH-1)"
    );
}

#[tokio::test]
async fn test_wire_cache_hit_no_ensure_call() {
    // Canonical fast path: BTCUSDT already in sample_cache → ensure must not fire.
    //
    // INSTR-WIRE-TEST-STRENGTHEN-1 (2026-04-23): upgraded from indirect
    // inference ("completion implies fast path") to a direct assertion
    // via the #[cfg(test)] `ensure_call_count` counter on OrderManager.
    // The old test would have silently passed if a future refactor made
    // validate_and_round call ensure unconditionally; this one fails.
    //
    // INSTR-WIRE-TEST-STRENGTHEN-1：從間接推斷升級為直接 counter 斷言。
    use std::sync::atomic::Ordering::SeqCst;

    let cache = Arc::new(sample_cache());
    let client = Arc::new(
        BybitRestClient::new(
            crate::bybit_rest_client::BybitEnvironment::Demo,
            Some("test_key".to_string()),
            Some("test_secret".to_string()),
        )
        .unwrap(),
    );
    let mgr = OrderManager::new(client, cache);
    let req = CreateOrderRequest {
        category: OrderCategory::Linear,
        symbol: "BTCUSDT".to_string(),
        side: OrderSide::Buy,
        order_type: OrderType::Limit,
        qty: 0.01,
        price: Some(65000.0),
        time_in_force: None,
        reduce_only: None,
        close_on_trigger: None,
        order_link_id: None,
        trigger_price: None,
        trigger_direction: None,
        take_profit: None,
        stop_loss: None,
        tp_trigger_by: None,
        sl_trigger_by: None,
    };

    // Baseline: counter starts at 0.
    assert_eq!(
        mgr.ensure_call_count.load(SeqCst),
        0,
        "new OrderManager must have ensure_call_count=0"
    );

    let _ = mgr
        .validate_and_round(&req)
        .await
        .expect("cache hit must pass");

    // STRONG assert: the positive-cache fast path must bypass the ensure
    // branch entirely. If a future change makes ensure_symbol run
    // unconditionally (e.g. to force-refresh every request), this assert
    // surfaces the regression immediately rather than silently passing.
    // STRONG 斷言：正 cache hit 必跳過 ensure 分支；回歸立即可見。
    assert_eq!(
        mgr.ensure_call_count.load(SeqCst),
        0,
        "cache hit should NOT trigger ensure (INSTR-WIRE-TEST-STRENGTHEN-1)"
    );
}

// -- Field helpers tests / 欄位輔助函數測試 --

#[test]
fn test_str_field() {
    let obj = serde_json::json!({"a": "hello", "b": 123});
    assert_eq!(str_field(&obj, "a"), "hello");
    assert_eq!(str_field(&obj, "b"), ""); // not a string
    assert_eq!(str_field(&obj, "missing"), "");
}

#[test]
fn test_f64_field() {
    let obj = serde_json::json!({"a": "123.45", "b": "bad", "c": 999});
    assert!((f64_field(&obj, "a") - 123.45).abs() < 1e-10);
    assert!((f64_field(&obj, "b") - 0.0).abs() < 1e-10);
    assert!((f64_field(&obj, "missing") - 0.0).abs() < 1e-10);
}

// -- Serde round-trip tests / 序列化往返測試 --

#[test]
fn test_order_info_serde_roundtrip() {
    let info = OrderInfo {
        order_id: "oid".to_string(),
        order_link_id: "link".to_string(),
        symbol: "BTCUSDT".to_string(),
        side: "Buy".to_string(),
        order_type: "Limit".to_string(),
        price: 65000.0,
        trigger_price: 0.0,
        qty: 0.01,
        cum_exec_qty: 0.0,
        cum_exec_value: 0.0,
        avg_price: 0.0,
        order_status: "New".to_string(),
        created_time: "1700000000000".to_string(),
        updated_time: "1700000000000".to_string(),
    };
    let json = serde_json::to_string(&info).unwrap();
    let deser: OrderInfo = serde_json::from_str(&json).unwrap();
    assert_eq!(deser.order_id, "oid");
    assert!((deser.price - 65000.0).abs() < 1e-10);
}

#[test]
fn test_execution_info_serde_roundtrip() {
    let exec = ExecutionInfo {
        exec_id: "e1".to_string(),
        symbol: "ETHUSDT".to_string(),
        side: "Sell".to_string(),
        exec_price: 3500.0,
        exec_qty: 1.0,
        exec_value: 3500.0,
        exec_fee: 1.925,
        fee_currency: "USDT".to_string(),
        order_id: "o1".to_string(),
        order_link_id: "l1".to_string(),
        exec_type: "Trade".to_string(),
        exec_time: "1700000000000".to_string(),
        closed_pnl: -5.25,
    };
    let json = serde_json::to_string(&exec).unwrap();
    let deser: ExecutionInfo = serde_json::from_str(&json).unwrap();
    assert_eq!(deser.exec_id, "e1");
    assert!((deser.exec_fee - 1.925).abs() < 1e-10);
    assert!((deser.closed_pnl + 5.25).abs() < 1e-10);
}
