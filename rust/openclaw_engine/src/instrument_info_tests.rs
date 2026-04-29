//! Instrument info cache tests — SymbolSpec rounding + cache / SingleFlight.
//! 合約信息緩存測試 — SymbolSpec 取整 + 緩存 / SingleFlight。
//!
//! MODULE_NOTE (EN): Extracted from `instrument_info.rs` as Wave 1 G1-03 to
//!   pull `instrument_info.rs` under CLAUDE.md §九 1200-line hard limit. The
//!   test body is included back into the parent via
//!   `#[cfg(test)] #[path = "instrument_info_tests.rs"] mod tests;` at the
//!   foot of `instrument_info.rs`, so every helper keeps `use super::*;`
//!   semantics — no visibility changes required. Bit-identical test content
//!   vs pre-split.
//! MODULE_NOTE (中): 從 `instrument_info.rs` 抽出（Wave 1 G1-03），讓父檔進
//!   §九 1200 行硬上限。測試主體透過父檔底部
//!   `#[cfg(test)] #[path = "instrument_info_tests.rs"] mod tests;` 重新
//!   納入，`use super::*;` 語義不變、可見性無需調整。行為等價（原樣）。

use super::*;

fn sample_btc_spec() -> SymbolSpec {
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
    }
}

#[test]
fn test_round_qty() {
    let spec = sample_btc_spec();
    assert!((spec.round_qty(0.0056) - 0.005).abs() < 1e-10);
    assert!((spec.round_qty(0.0019) - 0.001).abs() < 1e-10);
    assert!((spec.round_qty(1.9999) - 1.999).abs() < 1e-10);
    assert!((spec.round_qty(0.0001) - 0.0).abs() < 1e-10); // below step
}

#[test]
fn test_round_qty_zero_negative() {
    let spec = sample_btc_spec();
    assert_eq!(spec.round_qty(0.0), 0.0);
    assert_eq!(spec.round_qty(-1.0), 0.0);
}

#[test]
fn test_round_price() {
    let spec = sample_btc_spec();
    // tick_size = 0.10, so 65000.55 → 65000.6
    assert!((spec.round_price(65000.55) - 65000.6).abs() < 1e-10);
    // 65000.04 → 65000.0
    assert!((spec.round_price(65000.04) - 65000.0).abs() < 1e-10);
}

#[test]
fn test_floor_price() {
    let spec = sample_btc_spec();
    assert!((spec.floor_price(65000.99) - 65000.9).abs() < 1e-10);
    assert!((spec.floor_price(65000.01) - 65000.0).abs() < 1e-10);
}

#[test]
fn test_ceil_price() {
    let spec = sample_btc_spec();
    assert!((spec.ceil_price(65000.01) - 65000.1).abs() < 1e-10);
    assert!((spec.ceil_price(65000.0) - 65000.0).abs() < 1e-10);
}

#[test]
fn test_validate_order_ok() {
    let spec = sample_btc_spec();
    let (ok, reason) = spec.validate_order(0.01, 65000.0);
    assert!(ok, "should be valid: {reason}");
}

#[test]
fn test_validate_order_qty_too_small() {
    let spec = sample_btc_spec();
    let (ok, reason) = spec.validate_order(0.0001, 65000.0);
    assert!(!ok);
    assert!(reason.contains("min_qty"));
}

#[test]
fn test_validate_order_qty_too_large() {
    let spec = sample_btc_spec();
    let (ok, reason) = spec.validate_order(200.0, 65000.0);
    assert!(!ok);
    assert!(reason.contains("max_qty"));
}

#[test]
fn test_validate_order_notional_too_small() {
    let spec = sample_btc_spec();
    // 0.001 * 1.0 = 0.001 < min_notional 5
    let (ok, reason) = spec.validate_order(0.001, 1.0);
    assert!(!ok);
    assert!(reason.contains("min_notional"));
}

#[test]
fn test_decimal_places_from_step() {
    assert_eq!(decimal_places_from_step(0.001), 3);
    assert_eq!(decimal_places_from_step(0.10), 1);
    assert_eq!(decimal_places_from_step(0.01), 2);
    assert_eq!(decimal_places_from_step(1.0), 0);
    assert_eq!(decimal_places_from_step(0.0), 0);
}

#[test]
fn test_round_to_decimals() {
    assert!((round_to_decimals(1.23456, 3) - 1.235).abs() < 1e-10);
    assert!((round_to_decimals(1.23456, 0) - 1.0).abs() < 1e-10);
    assert!((round_to_decimals(1.5, 0) - 2.0).abs() < 1e-10);
}

#[test]
fn test_parse_instrument_item() {
    let item = serde_json::json!({
        "symbol": "BTCUSDT",
        "baseCoin": "BTC",
        "quoteCoin": "USDT",
        "contractType": "LinearPerpetual",
        "lotSizeFilter": {
            "qtyStep": "0.001",
            "minOrderQty": "0.001",
            "maxOrderQty": "100",
            "minNotionalValue": "5"
        },
        "priceFilter": {
            "tickSize": "0.10",
            "minPrice": "0.10",
            "maxPrice": "999999.00"
        }
    });

    let spec = parse_instrument_item(&item).unwrap();
    assert_eq!(spec.symbol, "BTCUSDT");
    assert_eq!(spec.base_currency, "BTC");
    assert!((spec.qty_step - 0.001).abs() < 1e-10);
    assert!((spec.tick_size - 0.10).abs() < 1e-10);
    assert!((spec.min_notional - 5.0).abs() < 1e-10);
    assert_eq!(spec.qty_decimals, 3);
    assert_eq!(spec.price_decimals, 1);
}

#[test]
fn test_parse_instrument_item_missing_symbol() {
    let item = serde_json::json!({
        "baseCoin": "BTC",
        "lotSizeFilter": {"qtyStep": "0.001"},
        "priceFilter": {"tickSize": "0.10"}
    });
    assert!(parse_instrument_item(&item).is_none());
}

#[test]
fn test_cache_basic_operations() {
    let cache = InstrumentInfoCache::new();
    assert!(cache.is_empty());
    assert_eq!(cache.len(), 0);
    assert!(cache.get("BTCUSDT").is_none());
    assert!(cache.get_lot_size("BTCUSDT").is_none());
    assert!(cache.get_tick_size("BTCUSDT").is_none());
    assert!(cache.round_qty("BTCUSDT", 1.0).is_none());
    assert!(cache.round_price("BTCUSDT", 65000.0).is_none());
}

#[test]
fn test_cache_manual_insert_and_query() {
    let cache = InstrumentInfoCache::new();
    {
        let mut map = cache.cache.write();
        map.insert("BTCUSDT".to_string(), sample_btc_spec());
    }

    assert!(!cache.is_empty());
    assert_eq!(cache.len(), 1);
    assert!(cache.get("BTCUSDT").is_some());
    assert!((cache.get_lot_size("BTCUSDT").unwrap() - 0.001).abs() < 1e-10);
    assert!((cache.get_tick_size("BTCUSDT").unwrap() - 0.10).abs() < 1e-10);
    assert!((cache.round_qty("BTCUSDT", 0.0056).unwrap() - 0.005).abs() < 1e-10);
    assert!((cache.round_price("BTCUSDT", 65000.55).unwrap() - 65000.6).abs() < 1e-10);
    assert!(cache.symbols().contains(&"BTCUSDT".to_string()));
}

// -----------------------------------------------------------------------
// INSTR-PAGINATE-1 — pagination unit tests (pure parse_page)
// INSTR-PAGINATE-1 — 分頁單元測試（純 parse_page）
// -----------------------------------------------------------------------

fn sample_item(symbol: &str) -> serde_json::Value {
    serde_json::json!({
        "symbol": symbol,
        "baseCoin": "FOO",
        "quoteCoin": "USDT",
        "contractType": "LinearPerpetual",
        "lotSizeFilter": {
            "qtyStep": "0.001",
            "minOrderQty": "0.001",
            "maxOrderQty": "100",
            "minNotionalValue": "5"
        },
        "priceFilter": {
            "tickSize": "0.10",
            "minPrice": "0.10",
            "maxPrice": "999999.00"
        }
    })
}

#[test]
fn test_parse_page_single_page_empty_cursor_absent() {
    // result has no nextPageCursor field → next = None
    let result = serde_json::json!({
        "list": [sample_item("AAAUSDT"), sample_item("BBBUSDT")],
    });
    let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
    let (count, next) = parse_page(&result, &mut cache);
    assert_eq!(count, 2);
    assert_eq!(next, None);
    assert!(cache.contains_key("AAAUSDT"));
    assert!(cache.contains_key("BBBUSDT"));
}

#[test]
fn test_parse_page_empty_string_cursor_is_none() {
    // Bybit end-of-pages: nextPageCursor = "" → next = None
    let result = serde_json::json!({
        "list": [sample_item("ZZZUSDT")],
        "nextPageCursor": "",
    });
    let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
    let (count, next) = parse_page(&result, &mut cache);
    assert_eq!(count, 1);
    assert_eq!(next, None);
}

#[test]
fn test_parse_page_non_empty_cursor_propagates() {
    let result = serde_json::json!({
        "list": [sample_item("AAAUSDT")],
        "nextPageCursor": "page2_cursor",
    });
    let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
    let (count, next) = parse_page(&result, &mut cache);
    assert_eq!(count, 1);
    assert_eq!(next, Some("page2_cursor".to_string()));
}

#[test]
fn test_parse_page_missing_list_returns_zero() {
    let result = serde_json::json!({"nextPageCursor": "c1"});
    let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
    let (count, next) = parse_page(&result, &mut cache);
    assert_eq!(count, 0);
    assert_eq!(next, Some("c1".to_string()));
}

#[test]
fn test_parse_page_three_page_concatenation() {
    // Simulate the three-page loop the refresh() cursor loop would drive.
    // Pages cursor chain: "" → "c1" → "c2" → "" (terminal).
    // 模擬 refresh() cursor 迴圈跑三頁：空 → c1 → c2 → 空。
    let page1 = serde_json::json!({
        "list": [sample_item("AAAUSDT"), sample_item("BBBUSDT")],
        "nextPageCursor": "c1",
    });
    let page2 = serde_json::json!({
        "list": [sample_item("CCCUSDT"), sample_item("DDDUSDT"), sample_item("EEEUSDT")],
        "nextPageCursor": "c2",
    });
    let page3 = serde_json::json!({
        "list": [sample_item("FFFUSDT")],
        "nextPageCursor": "",
    });

    let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
    let mut total = 0usize;
    let mut pages_iter = 0usize;
    let mut cursor: Option<String> = None;
    for page in [&page1, &page2, &page3] {
        pages_iter += 1;
        let (c, next) = parse_page(page, &mut cache);
        total += c;
        cursor = next;
        if cursor.is_none() {
            break;
        }
    }

    assert_eq!(total, 6);
    assert_eq!(pages_iter, 3);
    assert_eq!(cursor, None);
    assert_eq!(cache.len(), 6);
    for s in [
        "AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT", "FFFUSDT",
    ] {
        assert!(cache.contains_key(s), "missing {s}");
    }
}

#[test]
fn test_parse_page_cursor_chain_terminates() {
    // Page with `nextPageCursor` field absent entirely should also terminate.
    let result = serde_json::json!({
        "list": [sample_item("ONLYUSDT")],
    });
    let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
    let (_c, next) = parse_page(&result, &mut cache);
    assert!(next.is_none(), "absent nextPageCursor must terminate");
}

// -----------------------------------------------------------------------
// INSTR-ENSURE-1 — ensure_symbol unit tests (mock SingleSymbolFetcher)
// INSTR-ENSURE-1 — ensure_symbol 單元測試（mock SingleSymbolFetcher）
// -----------------------------------------------------------------------

use std::sync::atomic::{AtomicU64, AtomicU8, Ordering};

/// Mock fetcher — programmable response + REST call counter.
/// Mock fetcher — 可編程回應 + REST 呼叫計數器。
struct MockFetcher {
    /// 0 = Ok(Some(item)), 1 = Ok(None), 2 = Err transient, 3 = Err 5xx
    mode: AtomicU8,
    /// Counts every call to fetch_single_symbol
    calls: Arc<AtomicU64>,
    /// Optional per-call delay to force concurrency overlap
    delay_ms: u64,
}

impl MockFetcher {
    fn new(mode: u8) -> Self {
        Self {
            mode: AtomicU8::new(mode),
            calls: Arc::new(AtomicU64::new(0)),
            delay_ms: 0,
        }
    }
    fn with_delay(mode: u8, delay_ms: u64) -> Self {
        Self {
            mode: AtomicU8::new(mode),
            calls: Arc::new(AtomicU64::new(0)),
            delay_ms,
        }
    }
    fn set_mode(&self, m: u8) {
        self.mode.store(m, Ordering::SeqCst);
    }
    fn call_count(&self) -> u64 {
        self.calls.load(Ordering::SeqCst)
    }
}

#[async_trait]
impl SingleSymbolFetcher for MockFetcher {
    async fn fetch_single_symbol(
        &self,
        _category: &str,
        symbol: &str,
    ) -> BybitResult<Option<serde_json::Value>> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        if self.delay_ms > 0 {
            tokio::time::sleep(Duration::from_millis(self.delay_ms)).await;
        }
        match self.mode.load(Ordering::SeqCst) {
            0 => Ok(Some(sample_item(symbol))),
            1 => Ok(None),
            2 => Err(BybitApiError::Business {
                ret_code: -1,
                ret_msg: "simulated transient error".into(),
                response: serde_json::json!(null),
            }),
            _ => Err(BybitApiError::Business {
                ret_code: 10002,
                ret_msg: "simulated 5xx".into(),
                response: serde_json::json!(null),
            }),
        }
    }
}

#[tokio::test]
async fn test_ensure_symbol_positive_cache_hit_no_fetch() {
    let cache = InstrumentInfoCache::new();
    {
        let mut map = cache.cache.write();
        map.insert("BTCUSDT".to_string(), sample_btc_spec());
    }
    let fetcher = MockFetcher::new(0);

    let got = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "BTCUSDT")
        .await
        .unwrap();
    assert!(got.is_some());
    assert_eq!(fetcher.call_count(), 0, "positive cache hit must not fetch");
}

#[tokio::test]
async fn test_ensure_symbol_fetch_inserts_positive_cache() {
    let cache = InstrumentInfoCache::new();
    let fetcher = MockFetcher::new(0);

    let got = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "AAAUSDT")
        .await
        .unwrap();
    assert!(got.is_some());
    assert_eq!(fetcher.call_count(), 1);
    assert!(cache.get("AAAUSDT").is_some(), "spec must be cached");

    // Second call — positive cache served, no new fetch
    let _ = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "AAAUSDT")
        .await
        .unwrap();
    assert_eq!(
        fetcher.call_count(),
        1,
        "second call must hit positive cache"
    );
}

#[tokio::test]
async fn test_ensure_symbol_neg_cache_blocks_refetch() {
    let cache = InstrumentInfoCache::new();
    let fetcher = MockFetcher::new(1); // Bybit says "not found"

    let got = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "FAKE__USDT")
        .await
        .unwrap();
    assert!(got.is_none());
    assert_eq!(fetcher.call_count(), 1);

    // Second call within TTL — neg cache hit, no new fetch
    let got2 = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "FAKE__USDT")
        .await
        .unwrap();
    assert!(got2.is_none());
    assert_eq!(
        fetcher.call_count(),
        1,
        "neg cache hit must not trigger fetch"
    );
}

#[tokio::test]
async fn test_ensure_symbol_transient_error_not_neg_cached() {
    let cache = InstrumentInfoCache::new();
    let fetcher = MockFetcher::new(3); // simulated 5xx-like

    let r1 = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "FOOBAR")
        .await;
    assert!(r1.is_err(), "transient error must propagate");
    assert_eq!(fetcher.call_count(), 1);

    // Neg cache must NOT contain FOOBAR
    assert!(
        !cache.neg_cache_hit("FOOBAR"),
        "transient errors must not poison neg cache"
    );

    // Second call — fetcher is called again (retry allowed because
    // no neg cache poisoning + not in positive cache)
    let _ = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "FOOBAR")
        .await;
    assert_eq!(
        fetcher.call_count(),
        2,
        "transient error must permit retry on next call"
    );
}

#[tokio::test]
async fn test_ensure_symbol_singleflight_dedup() {
    // 10 concurrent tasks request the same symbol — only 1 REST call should issue.
    let cache = Arc::new(InstrumentInfoCache::new());
    // Use a per-call delay so tasks overlap in the inflight slot.
    let fetcher = Arc::new(MockFetcher::with_delay(0, 50));

    let mut handles = Vec::new();
    for _ in 0..10 {
        let c = Arc::clone(&cache);
        let f = Arc::clone(&fetcher);
        handles.push(tokio::spawn(async move {
            c.ensure_symbol_with_fetcher(&*f, "linear", "RACEUSDT")
                .await
                .map(|o| o.is_some())
        }));
    }

    let results: Vec<_> = futures_util::future::join_all(handles).await;
    for r in results {
        assert!(r.unwrap().unwrap(), "every task must see a positive result");
    }

    assert_eq!(
        fetcher.call_count(),
        1,
        "singleflight must dedup concurrent fetches to 1 REST call"
    );
    assert!(cache.get("RACEUSDT").is_some());
}

#[tokio::test]
async fn test_ensure_symbol_neg_cache_ttl_expiry_then_refetch() {
    // Same flow as test_ensure_symbol_neg_cache_blocks_refetch, but we
    // manually expire the neg cache entry to prove the TTL gate works.
    let cache = InstrumentInfoCache::new();
    let fetcher = MockFetcher::new(1);

    let _ = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "EXPIREUSDT")
        .await
        .unwrap();
    assert_eq!(fetcher.call_count(), 1);

    // Force-expire: rewrite entry with an Instant well beyond TTL.
    {
        let mut guard = cache.negative_cache.write();
        guard.insert(
            "EXPIREUSDT".to_string(),
            Instant::now()
                .checked_sub(NEG_CACHE_TTL + Duration::from_secs(1))
                .expect("test clock subtraction"),
        );
    }

    // Bybit flips to "found"
    fetcher.set_mode(0);
    let got = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "EXPIREUSDT")
        .await
        .unwrap();
    assert!(got.is_some());
    assert_eq!(
        fetcher.call_count(),
        2,
        "TTL-expired neg entry must allow refetch"
    );
}

/// Test ETH-style spec with different precision.
/// 測試 ETH 風格的規格（不同精度）。
#[test]
fn test_eth_spec_rounding() {
    let spec = SymbolSpec {
        symbol: "ETHUSDT".to_string(),
        base_currency: "ETH".to_string(),
        quote_currency: "USDT".to_string(),
        contract_type: "LinearPerpetual".to_string(),
        qty_step: 0.01,
        min_qty: 0.01,
        max_qty: 1000.0,
        tick_size: 0.01,
        min_price: 0.01,
        max_price: 99999.0,
        min_notional: 5.0,
        qty_decimals: 2,
        price_decimals: 2,
    };
    assert!((spec.round_qty(1.234) - 1.23).abs() < 1e-10);
    assert!((spec.round_price(3500.555) - 3500.56).abs() < 1e-10);
}

// -----------------------------------------------------------------------
// INSTR-ENSURE-FIX-1 — regression tests for E2 review findings
// INSTR-ENSURE-FIX-1 — E2 review 回歸測試
// -----------------------------------------------------------------------

/// B-1 race regression — direct white-box test for the lost-wakeup fix.
///
/// Background — on the old code the follower registers its `.notified()`
/// waker AFTER releasing the inflight mutex:
///
/// ```text
///   // OLD (buggy):
///   drop(inflight_mutex);
///   notify.notified().await;    // <-- only registers HERE
/// ```
///
/// If the leader completes between the two steps and calls
/// `notify_waiters()`, the follower's waker isn't yet in the intrusive
/// list. Because `Notify::notify_waiters()` does NOT store a permit
/// for future subscribers, the notification is lost → follower hangs
/// on `.await` indefinitely.
///
/// This test constructs the exact race by **hand-placing** a stale
/// InflightEntry with `done=true` into the inflight map (simulating
/// "leader already finished + notified before follower started"),
/// then calls ensure_symbol and asserts it does NOT hang. The
/// production follower path must observe `done` via Acquire and skip
/// the `.await`; on the old code (plain `.notified().await`) this
/// exact shape is a guaranteed hang — no race randomness required.
///
/// We also run a looser end-to-end stress scenario with many
/// contenders colliding under a shared start-barrier to catch any
/// other ordering regressions.
///
/// B-1 lost-wakeup 回歸（白盒）：手動放「已完成」的 InflightEntry，
/// 直接驗證 follower 觀察 done=true 跳 await；再做多 contender 壓測覆蓋。
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn test_ensure_symbol_race_regression_leader_fast() {
    use tokio::sync::Barrier;

    // -------------------------------------------------------------------
    // Part 1 — white-box: stale-done entry must not hang the follower.
    // Part 1 — 白盒：已完成的 entry 必須讓 follower 不 hang。
    // -------------------------------------------------------------------
    {
        let cache = Arc::new(InstrumentInfoCache::new());

        // Step 1: pre-populate the positive cache (simulate leader's
        // cache insert).
        {
            let mut map = cache.cache.write();
            map.insert("STALEUSDT".to_string(), sample_btc_spec());
        }

        // Step 2: hand-place a stale InflightEntry with done=true into
        // the inflight map. This is the exact state that would exist
        // if the leader had (a) installed the entry, (b) set done=true,
        // (c) called notify_waiters(), (d) released the inflight mutex
        // to remove the slot — but where some "follower" observer had
        // cloned the Arc<InflightEntry> before the leader removed the
        // slot from the map. The follower holds a ref to the stale
        // entry. On old code, it would call `.notified().await` on a
        // Notify whose notification has already been flushed → hang.
        //
        // We avoid the "slot is removed" cleanup path by leaving the
        // entry in place so that a new ensure_symbol call finds it as
        // a follower.
        // 手動放入一個已 done=true 的 InflightEntry。對舊 code 是必 hang 的
        // 情境（notify_waiters 已發過、當前 Notify 無 permit）。新 code 先
        // enable 再 Acquire 讀 done → true → 跳 await。
        let stale_entry = Arc::new(InflightEntry::new());
        stale_entry.done.store(true, Ordering::Release);
        // Emit a notify_waiters() to simulate the permit being "flushed"
        // — with no current waiters, notify_waiters is a no-op-ish
        // state bump that does NOT leave a permit for future subscribers.
        // This is exactly the scenario that breaks old-code followers.
        // 發 notify_waiters()：無 waiter 等於無效，不留 permit，正是破壞舊
        // code follower 的情境。
        stale_entry.notify.notify_waiters();
        {
            let mut inflight = cache.inflight.lock();
            inflight.insert("STALEUSDT".to_string(), Arc::clone(&stale_entry));
        }

        // Dummy fetcher that must never be called (positive cache hit
        // path in follower flow — done=true triggers re-check of caches
        // which finds the pre-populated positive entry).
        struct NeverCalledFetcher;
        #[async_trait]
        impl SingleSymbolFetcher for NeverCalledFetcher {
            async fn fetch_single_symbol(
                &self,
                _category: &str,
                _symbol: &str,
            ) -> BybitResult<Option<serde_json::Value>> {
                panic!("fetcher must not be called: positive cache already seeded");
            }
        }

        // ensure_symbol with the stale done-entry must return quickly.
        // On old code (plain `.notified().await`) this hangs forever
        // because no permit is waiting and no new notify will arrive.
        // 1s timeout surfaces old-code hang as a test failure.
        // 舊 code 會 hang（無 permit、無後續 notify）；新 code 立即返回。
        //
        // Note: Step 1 seeded the positive cache, so ensure_symbol's
        // very first check (positive cache fast path) should return
        // BEFORE we even hit the follower path. To actually force the
        // follower path, we need to clear the positive cache check —
        // but that check is unconditional. So instead we verify a
        // DIFFERENT arrangement: remove the positive cache entry, keep
        // the stale done-entry, and assert ensure_symbol returns None
        // (follower wakes via done=true, re-checks both caches, neither
        // has an entry, returns None — no hang).
        // 註：positive cache 會先被檢查導致捷徑返回。為強迫走 follower
        // 路徑，我們移除正 cache、保留 done entry，驗證 ensure 回 None
        // 且不 hang。
        {
            let mut map = cache.cache.write();
            map.remove("STALEUSDT");
        }

        let fetcher = NeverCalledFetcher;
        let result = tokio::time::timeout(
            Duration::from_secs(1),
            cache.ensure_symbol_with_fetcher(&fetcher, "linear", "STALEUSDT"),
        )
        .await;
        match result {
            Ok(Ok(opt)) => assert!(
                opt.is_none(),
                "follower observing done=true with empty caches must return None"
            ),
            Ok(Err(e)) => panic!("unexpected Err: {e:?}"),
            Err(_) => panic!(
                "B-1 REGRESSION: follower hung on .notified().await — done=true flag was not observed before await"
            ),
        }
    }

    // -------------------------------------------------------------------
    // Part 2 — end-to-end stress: many contenders collide, none may hang.
    // Part 2 — 端到端壓測：多 contender 同時衝擊，零 hang。
    // -------------------------------------------------------------------
    const ROUNDS: usize = 100;
    const CONTENDERS: usize = 8;

    /// Micro-delay fetcher — just enough `.await` (yield_now) to force
    /// the runtime to re-schedule, creating interleaving opportunities.
    /// Micro-delay fetcher：一次 yield_now，製造執行緒重排機會。
    struct YieldFetcher {
        calls: Arc<AtomicU64>,
    }
    #[async_trait]
    impl SingleSymbolFetcher for YieldFetcher {
        async fn fetch_single_symbol(
            &self,
            _category: &str,
            symbol: &str,
        ) -> BybitResult<Option<serde_json::Value>> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            tokio::task::yield_now().await;
            Ok(Some(sample_item(symbol)))
        }
    }

    for round in 0..ROUNDS {
        let cache = Arc::new(InstrumentInfoCache::new());
        let calls = Arc::new(AtomicU64::new(0));
        let fetcher = Arc::new(YieldFetcher {
            calls: Arc::clone(&calls),
        });
        let start_barrier = Arc::new(Barrier::new(CONTENDERS + 1));

        let mut handles = Vec::with_capacity(CONTENDERS);
        for idx in 0..CONTENDERS {
            let c = Arc::clone(&cache);
            let f = Arc::clone(&fetcher);
            let bar = Arc::clone(&start_barrier);
            handles.push(tokio::spawn(async move {
                bar.wait().await;
                let r = tokio::time::timeout(
                    Duration::from_secs(1),
                    c.ensure_symbol_with_fetcher(&*f, "linear", "RACEUSDT"),
                )
                .await;
                (idx, r)
            }));
        }

        start_barrier.wait().await;

        for h in handles {
            let (idx, joined) = h.await.expect("task join");
            match joined {
                Ok(Ok(opt)) => assert!(
                    opt.is_some(),
                    "round {round} task {idx}: must observe positive cache"
                ),
                Ok(Err(e)) => panic!("round {round} task {idx}: ensure returned Err {e:?}"),
                Err(_elapsed) => {
                    panic!("round {round} task {idx}: TIMEOUT — B-1 lost-wakeup regression")
                }
            }
        }

        assert!(
            cache.get("RACEUSDT").is_some(),
            "round {round}: positive cache must be populated"
        );
    }
}

/// P1-1 regression — parse failure must NOT populate neg cache.
///
/// Old behaviour: Bybit returns 200 + item whose schema doesn't match
/// our parser → we insert the symbol into the neg cache for 60s. If a
/// Bybit field rename causes parse failure for EVERY symbol, the whole
/// engine is blacked out for 60s (M-1 fail-closed rejects all orders).
///
/// New behaviour: parse failure returns a transient Err (still
/// fail-closes the current order via M-1) but leaves the neg cache
/// clean, so the next call issues a fresh fetch. If Bybit fixes the
/// schema, the engine self-heals within one tick.
///
/// P1-1 回歸：parse 失敗**不**入 neg cache，避免 Bybit schema 漂移 60s
/// 全引擎拒單。
#[tokio::test]
async fn test_ensure_symbol_parse_fail_not_neg_cached() {
    /// Mock fetcher: first call returns 200 + item missing
    /// `lotSizeFilter` (schema drift simulation). Subsequent calls
    /// return a valid item (Bybit "recovered").
    /// 第一次回 200 但少欄位（模擬 schema 漂移）；後續恢復正常 schema。
    struct FlipSchemaFetcher {
        calls: Arc<AtomicU64>,
    }
    #[async_trait]
    impl SingleSymbolFetcher for FlipSchemaFetcher {
        async fn fetch_single_symbol(
            &self,
            _category: &str,
            symbol: &str,
        ) -> BybitResult<Option<serde_json::Value>> {
            let n = self.calls.fetch_add(1, Ordering::SeqCst);
            if n == 0 {
                // Missing `lotSizeFilter` — parse_instrument_item will
                // short-circuit with None on the `item.get("lotSizeFilter")?`.
                // 缺 lotSizeFilter → parse_instrument_item 早退 None。
                Ok(Some(serde_json::json!({
                    "symbol": symbol,
                    "baseCoin": "FOO",
                    "quoteCoin": "USDT",
                    "contractType": "LinearPerpetual",
                    "priceFilter": {
                        "tickSize": "0.10",
                        "minPrice": "0.10",
                        "maxPrice": "999999.00"
                    }
                })))
            } else {
                Ok(Some(sample_item(symbol)))
            }
        }
    }

    let cache = InstrumentInfoCache::new();
    let fetcher = FlipSchemaFetcher {
        calls: Arc::new(AtomicU64::new(0)),
    };
    let calls = Arc::clone(&fetcher.calls);

    // First call — schema is broken, parser rejects, must surface Err.
    // 首呼：schema 壞，parser 拒，必須回 Err。
    let r1 = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "DRIFTUSDT")
        .await;
    assert!(
        r1.is_err(),
        "parse failure must surface as Err, not Ok(None) (otherwise neg cache poisoning)"
    );
    if let Err(BybitApiError::Business { ret_msg, .. }) = &r1 {
        assert!(
            ret_msg.contains("parse"),
            "error message should mention parse failure: {ret_msg}"
        );
    }

    // Neg cache must be clean — this is the core P1-1 assertion.
    // 負緩存必須乾淨 — P1-1 的核心 assertion。
    assert!(
        !cache.neg_cache_hit("DRIFTUSDT"),
        "parse failure must NOT poison neg cache"
    );
    assert_eq!(calls.load(Ordering::SeqCst), 1);

    // Second call — schema is good, must hit API again and succeed.
    // 次呼：schema 恢復，必須再打 API 並成功。
    let r2 = cache
        .ensure_symbol_with_fetcher(&fetcher, "linear", "DRIFTUSDT")
        .await
        .expect("second call must succeed");
    assert!(r2.is_some(), "self-heal: second call must cache the spec");
    assert_eq!(
        calls.load(Ordering::SeqCst),
        2,
        "neg cache must not have blocked the retry"
    );
    assert!(
        cache.get("DRIFTUSDT").is_some(),
        "positive cache must now hold the symbol"
    );
}

// -----------------------------------------------------------------------
// INSTR-ENSURE-FORCE-1 — ensure_symbol_force regression tests
// INSTR-ENSURE-FORCE-1 — 強制重拉規格的回歸測試
// -----------------------------------------------------------------------

/// force=true MUST bypass the positive cache fast path and invoke the
/// fetcher. force=false (same state) MUST NOT.
/// force=true 必繞正 cache；force=false 同情境不打網。
#[tokio::test]
async fn test_ensure_symbol_force_bypasses_positive_cache() {
    // Pre-seed positive cache. Normal ensure_symbol would short-circuit
    // on Step 1 — this test proves force=true skips that step.
    // 先放正 cache。若 force=true 仍短路，fetcher 不會被呼叫 → 測試失敗。
    let cache = InstrumentInfoCache::new();
    {
        let mut map = cache.cache.write();
        map.insert("FORCEUSDT".to_string(), sample_btc_spec());
    }

    let fetcher = MockFetcher::new(0); // mode 0 = Ok(Some(sample_item))

    // force=false: positive cache hit, fetcher NOT called.
    let r = cache
        .ensure_symbol_with_fetcher_opts(&fetcher, "linear", "FORCEUSDT", false)
        .await
        .expect("force=false ok");
    assert!(r.is_some(), "force=false must return the cached spec");
    assert_eq!(
        fetcher.call_count(),
        0,
        "force=false: positive cache fast path must skip fetcher"
    );

    // force=true: bypass fast path, fetcher MUST be called exactly once.
    let r2 = cache
        .ensure_symbol_with_fetcher_opts(&fetcher, "linear", "FORCEUSDT", true)
        .await
        .expect("force=true ok");
    assert!(r2.is_some(), "force=true must still return a spec");
    assert_eq!(
        fetcher.call_count(),
        1,
        "force=true must bypass positive cache and call fetcher"
    );

    // Subsequent force=false call returns cached spec (the fresh one
    // written by the force=true call); no additional fetch.
    // 後續 force=false 直接走 cache，呼叫計數不變。
    let _ = cache
        .ensure_symbol_with_fetcher_opts(&fetcher, "linear", "FORCEUSDT", false)
        .await
        .expect("ok");
    assert_eq!(fetcher.call_count(), 1);
}

/// force=true still collapses concurrent same-symbol calls into a single
/// REST hit via the singleflight inflight slot. Critical: without this,
/// a burst of tick-invalid errors could fan out N parallel force-refresh
/// REST calls for the same symbol and blow the rate limit.
/// force=true 仍遵守 singleflight；同 symbol N 併發只 1 次 REST。
#[tokio::test]
async fn test_ensure_symbol_force_still_respects_singleflight() {
    let cache = Arc::new(InstrumentInfoCache::new());
    // Delay the fetcher so all 10 contenders are guaranteed to overlap
    // in the inflight slot. Matches singleflight_dedup test style.
    // 加延遲讓 10 個 task 全部重疊在 inflight 槽位。
    let fetcher = Arc::new(MockFetcher::with_delay(0, 50));

    let mut handles = Vec::new();
    for _ in 0..10 {
        let c = Arc::clone(&cache);
        let f = Arc::clone(&fetcher);
        handles.push(tokio::spawn(async move {
            c.ensure_symbol_with_fetcher_opts(&*f, "linear", "FORCERACE", true)
                .await
                .map(|o| o.is_some())
        }));
    }

    let results: Vec<_> = futures_util::future::join_all(handles).await;
    for r in results {
        assert!(
            r.unwrap().unwrap(),
            "every force=true contender must see a positive result"
        );
    }

    assert_eq!(
        fetcher.call_count(),
        1,
        "force=true singleflight: 10 concurrent must collapse to 1 REST"
    );
    assert!(cache.get("FORCERACE").is_some());
}
