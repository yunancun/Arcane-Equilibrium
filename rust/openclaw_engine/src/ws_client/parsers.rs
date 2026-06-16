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

const MIN_LIQUIDATION_TS_MS: u64 = 946_684_800_000; // 2000-01-01T00:00:00Z
const MAX_LIQUIDATION_TS_MS: u64 = 4_102_444_800_000; // 2100-01-01T00:00:00Z

fn sane_liquidation_ts_ms(ts: u64) -> Option<u64> {
    (MIN_LIQUIDATION_TS_MS..=MAX_LIQUIDATION_TS_MS)
        .contains(&ts)
        .then_some(ts)
}

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

/// Parse a Bybit kline item into a `KlineConfirm` PriceEvent carrying the FULL
/// authoritative OHLCV+turnover of the closed candle.
/// 將 Bybit K 線項目解析為攜帶完整權威 OHLCV+成交額的 `KlineConfirm` PriceEvent。
///
/// Only returns Some for **confirmed** candles (confirm == true).
/// Unconfirmed candles are dropped — real-time prices come via publicTrade.
/// 只返回**已確認**的 K 線（confirm == true）。
/// 未確認的 K 線被丟棄 — 實時價格通過 publicTrade 獲取。
///
/// R1（根因修復）：Bybit 在 `confirm==true` 時推送整根真實 OHLCV+turnover。
/// 舊版只抽 `close`+`volume` 降級成 close-only tick，使持久化路徑的 tick-synth
/// aggregator 從稀疏 tick 合成退化 K 線（open≈close、range≈0、一-bar offset）。
/// 現改為填齊 open/high/low/close/volume/turnover + interval + start/end，標
/// `KlineConfirm`，讓持久化端直接落盤權威整根。
///
/// fail-closed：任一 OHLC 欄位缺失或不可解析即回 None，絕不落半截 bar。
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

    // R1 fail-closed：open/high/low/close 任一缺失即丟棄整根（不送退化 bar）。
    // Bybit WS kline item 欄位為字串編碼數值。
    let parse_field = |key: &str| -> Option<f64> {
        item.get(key)
            .and_then(|v| v.as_str())
            .and_then(|s| s.parse::<f64>().ok())
            .filter(|v| v.is_finite())
    };
    let open = parse_field("open")?;
    let high = parse_field("high")?;
    let low = parse_field("low")?;
    let close = parse_field("close")?;
    // volume / turnover 缺失視為 0（量類欄位 fail-soft，價格欄位才 fail-closed）。
    let volume = parse_field("volume").unwrap_or(0.0);
    let turnover = parse_field("turnover").unwrap_or(0.0);

    // Bybit `start` = 週期開盤時間（ms epoch）；缺失退回 now_ms（與舊行為一致）。
    let start_ms = item
        .get("start")
        .and_then(|v| {
            v.as_u64()
                .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
        })
        .unwrap_or_else(now_ms);
    // Bybit `end` = 週期收盤時間（ms epoch）；缺失退 None，持久化端依 interval 推算。
    let end_ms = item.get("end").and_then(|v| {
        v.as_u64()
            .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
    });

    // 從 topic 第二段抽 interval，e.g. "kline.1.BTCUSDT" → "1"、"kline.240.X" → "240"。
    let interval = extract_kline_interval_from_topic(topic);

    // close 走既有 last_price 欄位；其餘權威欄位走 R1 新增的 kline_* 欄位。
    let mut event = PriceEvent::new(symbol, close, start_ms);
    event.volume_24h = volume;
    event.event_kind = Some(PriceEventKind::KlineConfirm);
    event.kline_open = Some(open);
    event.kline_high = Some(high);
    event.kline_low = Some(low);
    event.kline_turnover = Some(turnover);
    event.kline_interval = interval;
    event.kline_start_ms = Some(start_ms);
    event.kline_close_ms = end_ms;
    Some(event)
}

/// Parse orderbook snapshot — extract best bid/ask into a PriceEvent.
/// 解析訂單簿快照 — 提取最優買賣價到 PriceEvent。
///
/// Bybit orderbook: {"topic":"orderbook.50.BTCUSDT","type":"snapshot","data":{"s":"BTCUSDT","b":[["price","qty"],...],"a":[...],"u":123,"seq":456}}
///
/// `msg_type` = 父消息的 `type` 欄位（"snapshot" / "delta"）。recorder-v2 必須靠它
/// 確定性區分 snapshot（reset+load 全簿）與 delta（upsert / qty==0 刪除），否則
/// L1BookTracker 無法正確 reset（這是 campaign-8 bad-tick 的根因，故 type 是
/// load-bearing 而非可有可無）。v1 路徑（bids5/asks5/best-bid/ask）不讀此參數。
///
/// `record_l1` = recorder-v2 producer-side gate（呼叫端 dispatch.rs 從進程啟動時
/// 讀一次的 `OPENCLAW_RECORD_L1_EVENTS` 快照取值，預設 OFF）。為什麼要 gate：
///   full-depth 解析（parse_all_levels 全 50 檔 + update_id/seq 抽取 + 5 個 ob_*
///   欄 populate）每條 orderbook.50 訊息都跑在 WS 讀熱路徑。flag-OFF 時消費端
///   （on_tick_helpers.rs:776 `if self.record_l1_events`）根本不消費這些欄位，做
///   了純屬白做工——這正是 E2 抓的「二進制非 inert」。flag-OFF 時 SKIP 全簿解析、
///   5 個 ob_* 欄保持 `PriceEvent::new` 的 None 預設；v1 路徑保持位元級不變。
pub(super) fn parse_orderbook_snapshot(
    data: &[serde_json::Value],
    topic: &str,
    msg_type: Option<&str>,
    record_l1: bool,
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

    // recorder-v2 producer gate：flag-OFF 時整段 full-depth 解析 SKIP，5 個 ob_* 欄
    // 保持下方 PriceEvent::new 的 None 預設（二進制 inert）；flag-ON 才抽全簿 + u/seq。
    // 與 parse_levels 的差異：不 .take(5)、保留 qty==0（刪除標記，tracker 端處理），
    // 但仍 fail-soft 丟棄不可解析 / 非有限的單檔（不污染本地簿）。
    let (all_bid_levels, all_ask_levels, update_id, seq) = if record_l1 {
        // 抽取**全部**變更檔（不截前 5），供 L1BookTracker 重建本地簿。
        let parse_all_levels = |arr: &[serde_json::Value]| -> Vec<(f64, f64)> {
            arr.iter()
                .filter_map(|lvl| {
                    let lvl = lvl.as_array()?;
                    let price = lvl.first()?.as_str()?.parse::<f64>().ok()?;
                    let qty = lvl.get(1)?.as_str()?.parse::<f64>().ok()?;
                    if !price.is_finite() || !qty.is_finite() {
                        return None;
                    }
                    Some((price, qty))
                })
                .collect()
        };
        // Bybit `u`（updateId，u==1=服務重啟須 reset）與 `seq`（cross-sequence）。
        // 字串或數值編碼皆容；缺欄回 None（tracker fail-soft 丟整筆，不寫 colliding 0）。
        let update_id = obj.get("u").and_then(|v| {
            v.as_u64()
                .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
        });
        let seq = obj.get("seq").and_then(|v| {
            v.as_u64()
                .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
        });
        (
            Some(parse_all_levels(bids)),
            Some(parse_all_levels(asks)),
            update_id,
            seq,
        )
    } else {
        (None, None, None, None)
    };

    let mut event = PriceEvent::new(symbol, mid_price, ts);
    event.bid_price = best_bid;
    event.ask_price = best_ask;
    event.event_kind = Some(PriceEventKind::Orderbook);
    // P-02: Populate structured fields directly — avoids serde round-trip in consumers.
    // P-02：直接填充結構化欄位 — 消費端免 serde 反序列化。
    event.bids5 = Some(bid_levels.clone());
    event.asks5 = Some(ask_levels.clone());
    // recorder-v2：additive 全變更檔 + type/u/seq。flag-OFF 時上方分支給全 None，
    // event.ob_* 維持 None 預設；非 orderbook 路徑亦恆 None。
    event.ob_msg_type = if record_l1 {
        msg_type.map(str::to_string)
    } else {
        None
    };
    event.ob_changed_bids = all_bid_levels;
    event.ob_changed_asks = all_ask_levels;
    event.ob_update_id = update_id;
    event.ob_seq = seq;
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
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|p| p.is_finite());

    // FND-4 P3：從 tickers 流提取 markPrice；缺欄/不可解析/非正/非有限值
    // 均保持 None，讓 forward recorder 寫 SQL NULL 而不是 0 佔位。
    let mark_price = item
        .get("markPrice")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|p| p.is_finite() && *p > 0.0);

    // W1 sub-task 3 (E1-γ, 2026-05-11)：從 tickers 流提取下次 funding 時間戳。
    // Bybit V5 tickers `nextFundingTime` 是字串編碼的 ms epoch；缺欄/不可解 → None。
    // 為 panel.funding_rates_panel.next_funding_ms 寫入提供來源（V085 schema）。
    let next_funding_ms = item
        .get("nextFundingTime")
        .and_then(|v| {
            v.as_str()
                .and_then(|s| s.parse::<i64>().ok())
                .or_else(|| v.as_i64())
        })
        .filter(|&t| t > 0);

    // OC-5: Extract index price from tickers for FundingArb basis calculation.
    // OC-5：從 tickers 提取指數價格，用於 FundingArb 基差計算。
    let index_price = item
        .get("indexPrice")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|p| p.is_finite() && *p > 0.0);

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
    event.mark_price = mark_price;
    event.next_funding_ms = next_funding_ms;
    event.index_price = index_price;
    event.open_interest = open_interest;
    event.event_kind = Some(PriceEventKind::Ticker);
    event.metadata.insert("type".into(), "ticker".into());
    Some(event)
}

/// Parse liquidation event — forced liquidation on the market.
/// 解析清算事件 — 市場上的強制清算。
///
/// Supports dormant legacy `liquidation.{symbol}` and the C1-proved
/// `allLiquidation.{symbol}` shape. The parser is strict: `allLiquidation`
/// requires item `s`; side must be `Buy`/`Sell`; qty/price must be positive
/// finite numbers; timestamp must be a sane positive ms epoch.
/// 支援 dormant legacy `liquidation.{symbol}` 與 C1 已證明的
/// `allLiquidation.{symbol}` payload；symbol / side / qty / price / timestamp
/// 皆 fail-closed。
pub(super) fn parse_liquidation_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
    let item_symbol = item
        .get("s")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(str::to_string);
    let symbol = if topic.starts_with("allLiquidation.") {
        item_symbol?
    } else {
        item_symbol.or_else(|| extract_symbol_from_topic(topic))?
    };
    let price = item
        .get("p")
        .or_else(|| item.get("price"))
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|v| v.is_finite() && *v > 0.0)?;
    let qty = item
        .get("v")
        .or_else(|| item.get("size"))
        .or_else(|| item.get("qty"))
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .filter(|v| v.is_finite() && *v > 0.0)?;
    let side = item
        .get("S")
        .or_else(|| item.get("side"))
        .and_then(|v| v.as_str())
        .filter(|s| matches!(*s, "Buy" | "Sell"))?;
    let ts = item
        .get("T")
        .or_else(|| item.get("updatedTime"))
        .and_then(|v| {
            v.as_u64()
                .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
        })
        .and_then(sane_liquidation_ts_ms)?;

    let mut event = PriceEvent::new(symbol, price, ts);
    event.event_kind = Some(PriceEventKind::Liquidation);
    event.metadata.insert("type".into(), "liquidation".into());
    event.metadata.insert("side".into(), side.into());
    event.metadata.insert("qty".into(), qty.to_string());
    let (position, direction) = match side {
        "Buy" => ("long_liquidation", "1"),
        "Sell" => ("short_liquidation", "-1"),
        _ => unreachable!("side filter only allows Buy/Sell"),
    };
    event
        .metadata
        .insert("liquidation_position".into(), position.into());
    event
        .metadata
        .insert("mean_reversion_direction".into(), direction.into());
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

/// Extract the kline interval segment from a topic like "kline.1.BTCUSDT" → "1".
/// 從 K 線主題字串提取 interval 段，如 "kline.1.BTCUSDT" → "1"、"kline.240.X" → "240"。
///
/// 格式為 "kline.{interval}.{symbol}" 三段；非此形狀（段數不符）回 None，
/// 持久化端據此 fail-closed（無 interval 無法決定 timeframe）。
pub(super) fn extract_kline_interval_from_topic(topic: &str) -> Option<String> {
    let mut parts = topic.split('.');
    let prefix = parts.next()?;
    if prefix != "kline" {
        return None;
    }
    let interval = parts.next()?;
    // 必須剛好三段（prefix.interval.symbol），且 symbol 段存在非空。
    let symbol = parts.next()?;
    if interval.is_empty() || symbol.is_empty() || parts.next().is_some() {
        return None;
    }
    Some(interval.to_string())
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
