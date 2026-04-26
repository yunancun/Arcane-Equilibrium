//! Bybit WS message parsers.
//! Bybit WebSocket 消息解析器。
//!
//! MODULE_NOTE (EN): Pure functions that turn parsed JSON values into
//!   `PriceEvent`s. No I/O, no state. One parser per Bybit topic family
//!   (publicTrade / kline / orderbook / tickers / liquidation / price-limit /
//!   adl-notice). `extract_symbol_from_topic` is the shared topic-suffix
//!   helper. `now_ms` is re-exported from `openclaw_core` (S-04).
//! MODULE_NOTE (中): 純函數 — JSON → `PriceEvent`，無 I/O 無狀態。每個 Bybit
//!   topic 家族一個 parser。`extract_symbol_from_topic` 是共用 suffix helper。

// S-04: use shared now_ms() from openclaw_core instead of local copy.
// S-04：使用 openclaw_core 的共用 now_ms() 取代本地副本。
pub(super) use openclaw_core::now_ms;
use openclaw_types::{PriceEvent, PriceEventKind};

/// Parse a Bybit public trade item into PriceEvent.
/// 將 Bybit 公開交易項目解析為 PriceEvent。
pub(super) fn parse_trade_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
    let symbol = extract_symbol_from_topic(topic)?;
    let price = item
        .get("p")
        .and_then(|v| v.as_str())?
        .parse::<f64>()
        .ok()?;
    let ts = item
        .get("T")
        .and_then(|v| {
            v.as_u64()
                .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
        })
        .unwrap_or_else(now_ms);
    let volume = item
        .get("v")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);
    // Side is "Buy" or "Sell" — preserved in metadata so the trade aggregator
    // can compute buy/sell volume splits and large-trade flags.
    // 方向（Buy/Sell）— 保留在 metadata 中，供 trade aggregator 計算多空成交量。
    let side = item
        .get("S")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let mut event = PriceEvent::new(symbol, price, ts);
    event.volume_24h = volume;
    event.event_kind = Some(PriceEventKind::Trade);
    // P-02: populate structured fields (preferred over metadata)
    event.trade_qty = Some(volume);
    if !side.is_empty() {
        event.trade_side = Some(side.clone());
        event.metadata.insert("side".into(), side);
    }
    event.metadata.insert("type".into(), "trade".into());
    event.metadata.insert("qty".into(), volume.to_string());
    Some(event)
}

/// Parse a Bybit kline item into PriceEvent (uses close price).
/// 將 Bybit K 線項目解析為 PriceEvent（使用收盤價）。
///
/// Only returns Some for **confirmed** candles (confirm == true).
/// Unconfirmed candles are dropped — real-time prices come via publicTrade.
/// 只返回**已確認**的 K 線（confirm == true）。
/// 未確認的 K 線被丟棄 — 實時價格通過 publicTrade 獲取。
pub(super) fn parse_kline_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
    // Drop unconfirmed candles to avoid false signals on incomplete data
    // 丟棄未確認 K 線，避免不完整數據產生虛假信號
    let confirmed = item
        .get("confirm")
        .and_then(|v| v.as_bool())
        .unwrap_or(false);
    if !confirmed {
        return None;
    }

    let symbol = extract_symbol_from_topic(topic)?;
    let close = item
        .get("close")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())?;
    let ts = item
        .get("start")
        .and_then(|v| {
            v.as_u64()
                .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
        })
        .unwrap_or_else(now_ms);
    let volume = item
        .get("volume")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);

    let mut event = PriceEvent::new(symbol, close, ts);
    event.volume_24h = volume;
    Some(event)
}

/// Parse orderbook snapshot — extract best bid/ask into a PriceEvent.
/// 解析訂單簿快照 — 提取最優買賣價到 PriceEvent。
///
/// Bybit orderbook: {"topic":"orderbook.50.BTCUSDT","type":"snapshot","data":{"s":"BTCUSDT","b":[["price","qty"],...],"a":[...],"u":123,"seq":456}}
pub(super) fn parse_orderbook_snapshot(
    data: &[serde_json::Value],
    topic: &str,
) -> Option<PriceEvent> {
    let symbol = extract_symbol_from_topic(topic)?;
    // Orderbook data is a single object, not an array of items.
    // The "data" array in process_message may contain the object directly,
    // or the snapshot object may be the first element.
    // 訂單簿數據是單個對象。
    let obj = data.first()?;

    let bids = obj.get("b").and_then(|v| v.as_array())?;
    let asks = obj.get("a").and_then(|v| v.as_array())?;

    let best_bid = bids
        .first()
        .and_then(|b| b.as_array())
        .and_then(|arr| arr.first())
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);

    let best_ask = asks
        .first()
        .and_then(|a| a.as_array())
        .and_then(|arr| arr.first())
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);

    let mid_price = if best_bid > 0.0 && best_ask > 0.0 {
        (best_bid + best_ask) / 2.0
    } else {
        best_bid.max(best_ask)
    };

    let ts = obj
        .get("ts")
        .and_then(|v| {
            v.as_u64()
                .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
        })
        .unwrap_or_else(now_ms);

    // Extract top-5 levels for the orderbook aggregator (idle writer #1).
    // 提取前 5 檔深度供 OB 聚合器使用（idle writer #1 修復）。
    let parse_levels = |arr: &[serde_json::Value]| -> Vec<(f64, f64)> {
        arr.iter()
            .take(5)
            .filter_map(|lvl| {
                let lvl = lvl.as_array()?;
                let price = lvl.first()?.as_str()?.parse::<f64>().ok()?;
                let qty = lvl.get(1)?.as_str()?.parse::<f64>().ok()?;
                Some((price, qty))
            })
            .collect()
    };
    let bid_levels = parse_levels(bids);
    let ask_levels = parse_levels(asks);

    let mut event = PriceEvent::new(symbol, mid_price, ts);
    event.bid_price = best_bid;
    event.ask_price = best_ask;
    event.event_kind = Some(PriceEventKind::Orderbook);
    // P-02: Populate structured fields directly — avoids serde round-trip in consumers.
    // P-02：直接填充結構化欄位 — 消費端免 serde 反序列化。
    event.bids5 = Some(bid_levels.clone());
    event.asks5 = Some(ask_levels.clone());
    // Legacy metadata — kept for backward compat until all consumers migrated.
    // 舊版 metadata — 保留向後兼容直到所有消費端遷移完畢。
    event.metadata.insert("type".into(), "orderbook".into());
    if let Ok(s) = serde_json::to_string(&bid_levels) {
        event.metadata.insert("bids5".into(), s);
    }
    if let Ok(s) = serde_json::to_string(&ask_levels) {
        event.metadata.insert("asks5".into(), s);
    }
    Some(event)
}

/// Parse ticker snapshot — last price, 24h volume, best bid/ask.
/// 解析行情快照 — 最新價、24h 成交量、最優買賣價。
///
/// Bybit ticker: {"topic":"tickers.BTCUSDT","data":{"symbol":"BTCUSDT","lastPrice":"65000","volume24h":"12345",...}}
pub(super) fn parse_ticker_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
    let symbol = extract_symbol_from_topic(topic)?;
    let last_price = item
        .get("lastPrice")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())?;
    let volume = item
        .get("volume24h")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);
    let bid = item
        .get("bid1Price")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);
    let ask = item
        .get("ask1Price")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);
    let ts = item
        .get("ts")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<u64>().ok())
        .or_else(|| item.get("ts").and_then(|v| v.as_u64()))
        .unwrap_or_else(now_ms);

    let turnover = item
        .get("turnover24h")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);

    // EDGE-P1-2: Extract funding rate from tickers stream (Bybit linear perps).
    // EDGE-P1-2：從 tickers 流提取資金費率（Bybit 線性永續）。
    let funding_rate = item
        .get("fundingRate")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok());

    // OC-5: Extract index price from tickers for FundingArb basis calculation.
    // OC-5：從 tickers 提取指數價格，用於 FundingArb 基差計算。
    let index_price = item
        .get("indexPrice")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|&p| p > 0.0);

    // EDGE-P2-2: Extract open interest (contract count, string-encoded f64).
    // Bybit sometimes emits null/missing on early snapshots — treat as None
    // (fail-closed, no panic). `openInterestValue` is a separate USD notional
    // field we deliberately ignore here; we want raw contract-count deltas.
    // Reject NaN/Inf/negative (non-finite or <0 never legitimate for OI);
    // `0.0` is legitimate (fully closed market segment) so use `>= 0.0`.
    // EDGE-P2-2：提取未平倉合約數（字串編碼 f64；早期 snapshot 可能 null/缺失）。
    // fail-closed 回 None，絕不 panic。`openInterestValue` 是 USD 名義金額，另一欄位，
    // 此處只採合約張數（用於差分估算倉位變化方向）。
    // 拒絕 NaN/Inf/負值（OI 不可能為非有限數或負數）；`0.0` 合法（完全關閉市場段），
    // 故使用 `>= 0.0` 而非 `> 0.0`（對照 index_price 用 `> 0.0`）。
    let open_interest = item
        .get("openInterest")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|p| p.is_finite() && *p >= 0.0);

    let mut event = PriceEvent::new(symbol, last_price, ts);
    event.volume_24h = volume;
    event.turnover_24h = turnover;
    event.bid_price = bid;
    event.ask_price = ask;
    event.funding_rate = funding_rate;
    event.index_price = index_price;
    event.open_interest = open_interest;
    event.event_kind = Some(PriceEventKind::Ticker);
    event.metadata.insert("type".into(), "ticker".into());
    Some(event)
}

/// Parse liquidation event — forced liquidation on the market.
/// 解析清算事件 — 市場上的強制清算。
///
/// Bybit liquidation: {"topic":"liquidation.BTCUSDT","data":{"symbol":"BTCUSDT","side":"Buy","price":"65000","qty":"0.5","updatedTime":...}}
pub(super) fn parse_liquidation_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
    let symbol = extract_symbol_from_topic(topic)?;
    let price = item
        .get("price")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())?;
    let qty = item.get("size").and_then(|v| v.as_str()).unwrap_or("0");
    let side = item
        .get("side")
        .and_then(|v| v.as_str())
        .unwrap_or("Unknown");
    let ts = item
        .get("updatedTime")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);

    let mut event = PriceEvent::new(symbol, price, ts);
    event.event_kind = Some(PriceEventKind::Liquidation);
    event.metadata.insert("type".into(), "liquidation".into());
    event.metadata.insert("side".into(), side.into());
    event.metadata.insert("qty".into(), qty.into());
    Some(event)
}

/// Parse price limit update — max buy / min sell boundaries.
/// 解析價格限制更新 — 最高買入/最低賣出邊界。
pub(super) fn parse_price_limit_item(item: &serde_json::Value) -> Option<PriceEvent> {
    let symbol = item.get("symbol").and_then(|v| v.as_str())?.to_string();
    let max_price = item.get("maxPrice").and_then(|v| v.as_str()).unwrap_or("0");
    let min_price = item.get("minPrice").and_then(|v| v.as_str()).unwrap_or("0");
    let ts = item.get("ts").and_then(|v| v.as_u64()).unwrap_or(0);

    let mid = max_price.parse::<f64>().unwrap_or(0.0);
    let mut event = PriceEvent::new(symbol, mid, ts);
    event.event_kind = Some(PriceEventKind::PriceLimit);
    event.metadata.insert("type".into(), "price_limit".into());
    event.metadata.insert("max_price".into(), max_price.into());
    event.metadata.insert("min_price".into(), min_price.into());
    Some(event)
}

/// Parse ADL (Auto-Deleveraging) notice — position at risk of forced reduction.
/// 解析 ADL 通知 — 持倉面臨強制減倉風險。
pub(super) fn parse_adl_notice_item(item: &serde_json::Value) -> Option<PriceEvent> {
    let symbol = item.get("symbol").and_then(|v| v.as_str())?.to_string();
    let adl_rank = item
        .get("adlRankIndicator")
        .and_then(|v| {
            v.as_i64()
                .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
        })
        .unwrap_or(0);
    let side = item
        .get("side")
        .and_then(|v| v.as_str())
        .unwrap_or("Unknown");
    let ts = item.get("ts").and_then(|v| v.as_u64()).unwrap_or(0);

    let mut event = PriceEvent::new(symbol, 0.0, ts);
    event.event_kind = Some(PriceEventKind::AdlNotice);
    // P-02: Structured field — avoids string parse in consumers.
    // P-02：結構化欄位 — 消費端免字串解析。
    event.adl_rank = Some(adl_rank as u32);
    // Legacy metadata — kept for backward compat.
    event.metadata.insert("type".into(), "adl_notice".into());
    event
        .metadata
        .insert("adl_rank".into(), adl_rank.to_string());
    event.metadata.insert("side".into(), side.into());
    Some(event)
}

/// Extract symbol from topic string like "publicTrade.BTCUSDT" → "BTCUSDT".
/// 從主題字串中提取交易對，如 "publicTrade.BTCUSDT" → "BTCUSDT"。
pub(super) fn extract_symbol_from_topic(topic: &str) -> Option<String> {
    // Format: "prefix.SYMBOL" or "prefix.interval.SYMBOL"
    // Zero-allocation: rsplit returns last segment first / 零分配
    let sym = topic.rsplit('.').next()?;
    if sym.is_empty() {
        return None;
    }
    Some(sym.to_string())
}
