//! Bybit WebSocket client with auto-reconnect (R01-3).
//! Bybit WebSocket 客戶端，支持自動重連。
//!
//! MODULE_NOTE (EN): Connects to Bybit V5 public WebSocket, subscribes to kline
//!   and trade streams, parses messages into PriceEvent, pushes to mpsc channel.
//!   Exponential backoff reconnect with configurable base delay.
//! MODULE_NOTE (中): 連接 Bybit V5 公開 WebSocket，訂閱 K 線和交易流，
//!   將消息解析為 PriceEvent 並推送到 mpsc 通道。
//!   指數退避重連，可配置基礎延遲。

use crate::config::ConfigManager;
use futures_util::{SinkExt, StreamExt};
use openclaw_types::PriceEvent;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;
use tokio_tungstenite::tungstenite::Message;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

// ---------------------------------------------------------------------------
// Connection state / 連接狀態
// ---------------------------------------------------------------------------

/// WebSocket connection state.
/// WebSocket 連接狀態。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WsState {
    /// Attempting initial or re-connection / 嘗試連接中
    Connecting,
    /// Connected and receiving data / 已連接並接收數據
    Connected,
    /// Lost connection, will retry / 連接斷開，將重試
    Reconnecting,
    /// Shut down / 已關閉
    Disconnected,
}

impl std::fmt::Display for WsState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Connecting => write!(f, "Connecting"),
            Self::Connected => write!(f, "Connected"),
            Self::Reconnecting => write!(f, "Reconnecting"),
            Self::Disconnected => write!(f, "Disconnected"),
        }
    }
}

// ---------------------------------------------------------------------------
// WsClient / WebSocket 客戶端
// ---------------------------------------------------------------------------

/// Bybit WebSocket client with auto-reconnect.
/// Bybit WebSocket 客戶端，支持自動重連。
pub struct WsClient {
    config: Arc<ConfigManager>,
    event_tx: mpsc::Sender<PriceEvent>,
    cancel: CancellationToken,
    /// Default subscriptions / 預設訂閱
    subscriptions: Vec<String>,
}

/// Maximum reconnect delay (ms) / 最大重連延遲
const MAX_RECONNECT_DELAY_MS: u64 = 60_000;
/// Backoff multiplier / 退避倍數
const BACKOFF_FACTOR: u64 = 2;
/// Max topics per subscribe call (Bybit limit = 10)
/// 每次 subscribe 調用最大主題數（Bybit 限制 = 10）
const SUBSCRIBE_BATCH_SIZE: usize = 10;

impl WsClient {
    /// Create a new WS client.
    /// 創建新的 WebSocket 客戶端。
    pub fn new(
        config: Arc<ConfigManager>,
        event_tx: mpsc::Sender<PriceEvent>,
        cancel: CancellationToken,
    ) -> Self {
        Self {
            config,
            event_tx,
            cancel,
            subscriptions: Vec::new(),
        }
    }

    /// Add a subscription topic.
    /// 添加訂閱主題。
    pub fn subscribe(&mut self, topic: impl Into<String>) {
        self.subscriptions.push(topic.into());
    }

    /// Run the WebSocket client loop with auto-reconnect.
    /// 運行 WebSocket 客戶端循環，支持自動重連。
    pub async fn run(&self) {
        let mut attempt: u32 = 0;

        loop {
            if self.cancel.is_cancelled() {
                info!("WS client cancelled before connect / WS 客戶端在連接前被取消");
                break;
            }

            let cfg = self.config.get();
            let url = &cfg.ws_url;
            let base_delay = cfg.reconnect_delay_ms;
            let heartbeat_ms = cfg.heartbeat_interval_ms;

            log_state(WsState::Connecting, attempt);

            match tokio_tungstenite::connect_async(url).await {
                Ok((ws_stream, _response)) => {
                    attempt = 0;
                    log_state(WsState::Connected, 0);

                    let (mut write, mut read) = ws_stream.split();

                    // Send subscriptions in batches of 10 (Bybit limit per call)
                    // 分批發送訂閱（Bybit 每次調用限制 10 個主題）
                    let mut sub_ok = true;
                    for chunk in self.subscriptions.chunks(SUBSCRIBE_BATCH_SIZE) {
                        let sub_msg = serde_json::json!({
                            "op": "subscribe",
                            "args": chunk,
                        });
                        if let Err(e) = write.send(Message::Text(sub_msg.to_string().into())).await {
                            error!(error = %e, "failed to send subscribe / 發送訂閱失敗");
                            sub_ok = false;
                            break;
                        }
                    }
                    if !sub_ok {
                        log_state(WsState::Reconnecting, attempt);
                        continue;
                    }
                    info!(
                        topics = self.subscriptions.len(),
                        batches = (self.subscriptions.len() + SUBSCRIBE_BATCH_SIZE - 1) / SUBSCRIBE_BATCH_SIZE,
                        "subscribed / 已訂閱"
                    );

                    // Heartbeat + message loop / 心跳 + 消息循環
                    let heartbeat_interval = Duration::from_millis(heartbeat_ms);
                    let mut heartbeat_timer = tokio::time::interval(heartbeat_interval);
                    // Skip the first immediate tick / 跳過第一次立即觸發
                    heartbeat_timer.tick().await;

                    loop {
                        tokio::select! {
                            _ = self.cancel.cancelled() => {
                                info!("WS client shutdown requested / WS 客戶端請求關閉");
                                let _ = write.send(Message::Close(None)).await;
                                log_state(WsState::Disconnected, 0);
                                return;
                            }
                            _ = heartbeat_timer.tick() => {
                                // Send ping / 發送心跳
                                let ping = serde_json::json!({"op": "ping"});
                                if let Err(e) = write.send(Message::Text(ping.to_string().into())).await {
                                    warn!(error = %e, "heartbeat ping failed / 心跳 ping 失敗");
                                    break;
                                }
                                debug!("heartbeat ping sent / 心跳 ping 已發送");
                            }
                            msg = read.next() => {
                                match msg {
                                    Some(Ok(Message::Text(text))) => {
                                        if !self.process_message(&text).await {
                                            // Event channel closed — engine shutting down (RE-2 fix)
                                            // 事件通道已關閉 — 引擎正在關閉
                                            log_state(WsState::Disconnected, 0);
                                            return;
                                        }
                                    }
                                    Some(Ok(Message::Ping(data))) => {
                                        let _ = write.send(Message::Pong(data)).await;
                                    }
                                    Some(Ok(Message::Close(_))) => {
                                        info!("server sent close frame / 服務器發送關閉幀");
                                        break;
                                    }
                                    Some(Err(e)) => {
                                        warn!(error = %e, "WS read error / WS 讀取錯誤");
                                        break;
                                    }
                                    None => {
                                        info!("WS stream ended / WS 流結束");
                                        break;
                                    }
                                    _ => {
                                        // Binary/Pong/Frame — ignore / 忽略
                                    }
                                }
                            }
                        }
                    }

                    // Connection lost — will reconnect / 連接斷開 — 將重連
                    log_state(WsState::Reconnecting, attempt);
                }
                Err(e) => {
                    warn!(error = %e, url = url, "WS connect failed / WS 連接失敗");
                    log_state(WsState::Reconnecting, attempt);
                }
            }

            // Exponential backoff / 指數退避
            attempt = attempt.saturating_add(1);
            let delay_ms = std::cmp::min(
                base_delay.saturating_mul(BACKOFF_FACTOR.saturating_pow(attempt)),
                MAX_RECONNECT_DELAY_MS,
            );
            info!(delay_ms = delay_ms, attempt = attempt, "reconnecting after delay / 延遲後重連");

            tokio::select! {
                _ = self.cancel.cancelled() => {
                    log_state(WsState::Disconnected, 0);
                    return;
                }
                _ = tokio::time::sleep(Duration::from_millis(delay_ms)) => {}
            }
        }

        log_state(WsState::Disconnected, 0);
    }

    /// Process a single text message from Bybit WS.
    /// Returns false if event channel is closed (caller should exit).
    /// 處理來自 Bybit WS 的單條文本消息。
    /// 返回 false 表示事件通道已關閉（調用方應退出）。
    async fn process_message(&self, text: &str) -> bool {
        // Try to extract price data from various Bybit message formats.
        // 嘗試從各種 Bybit 消息格式中提取價格數據。
        let parsed: serde_json::Value = match serde_json::from_str(text) {
            Ok(v) => v,
            Err(e) => {
                debug!(error = %e, "non-JSON WS message / 非 JSON WS 消息");
                return true;
            }
        };

        // Skip pong / subscription confirmations / 跳過 pong 和訂閱確認
        if parsed.get("op").is_some() || parsed.get("success").is_some() {
            debug!("control message: {}", text);
            return true;
        }

        // Bybit public data formats:
        //   Array: {"topic":"publicTrade.BTCUSDT","data":[{...}]}
        //   Object: {"topic":"tickers.BTCUSDT","data":{...}}
        //   Orderbook: {"topic":"orderbook.50.BTCUSDT","data":{"s":"...","b":[...],"a":[...]}}
        let topic = parsed.get("topic").and_then(|t| t.as_str()).unwrap_or("");
        let raw_data = match parsed.get("data") {
            Some(d) => d,
            None => return true,
        };

        // Normalize to array: if data is a single object, wrap it / 統一為數組
        let data_vec: Vec<serde_json::Value>;
        let data: &[serde_json::Value] = if let Some(arr) = raw_data.as_array() {
            arr
        } else if raw_data.is_object() {
            data_vec = vec![raw_data.clone()];
            &data_vec
        } else {
            return true;
        };

        // Route by topic prefix / 按主題前綴路由
        let events: Vec<PriceEvent> = if topic.starts_with("publicTrade.") {
            data.iter().filter_map(|item| parse_trade_item(item, topic)).collect()
        } else if topic.starts_with("kline.") {
            data.iter().filter_map(|item| parse_kline_item(item, topic)).collect()
        } else if topic.starts_with("orderbook.") {
            parse_orderbook_snapshot(data, topic).into_iter().collect()
        } else if topic.starts_with("tickers.") {
            data.iter().filter_map(|item| parse_ticker_item(item, topic)).collect()
        } else if topic.starts_with("liquidation.") {
            data.iter().filter_map(|item| parse_liquidation_item(item, topic)).collect()
        } else if topic.starts_with("price-limit.") {
            data.iter().filter_map(|item| parse_price_limit_item(item)).collect()
        } else if topic.starts_with("adl-notice.") {
            data.iter().filter_map(|item| parse_adl_notice_item(item)).collect()
        } else {
            debug!(topic = topic, "unhandled topic / 未處理的主題");
            return true;
        };

        for event in events {
            if self.event_tx.send(event).await.is_err() {
                warn!("event channel closed / 事件通道已關閉");
                return false;
            }
        }
        true
    }
}

// ---------------------------------------------------------------------------
// Message parsers / 消息解析器
// ---------------------------------------------------------------------------

/// Parse a Bybit public trade item into PriceEvent.
/// 將 Bybit 公開交易項目解析為 PriceEvent。
fn parse_trade_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
    let symbol = extract_symbol_from_topic(topic)?;
    let price = item.get("p").and_then(|v| v.as_str())?.parse::<f64>().ok()?;
    let ts = item
        .get("T")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);
    let volume = item
        .get("v")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);

    let mut event = PriceEvent::new(symbol, price, ts);
    event.volume_24h = volume;
    Some(event)
}

/// Parse a Bybit kline item into PriceEvent (uses close price).
/// 將 Bybit K 線項目解析為 PriceEvent（使用收盤價）。
///
/// Only returns Some for **confirmed** candles (confirm == true).
/// Unconfirmed candles are dropped — real-time prices come via publicTrade.
/// 只返回**已確認**的 K 線（confirm == true）。
/// 未確認的 K 線被丟棄 — 實時價格通過 publicTrade 獲取。
fn parse_kline_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
    // Drop unconfirmed candles to avoid false signals on incomplete data
    // 丟棄未確認 K 線，避免不完整數據產生虛假信號
    let confirmed = item.get("confirm").and_then(|v| v.as_bool()).unwrap_or(false);
    if !confirmed {
        return None;
    }

    let symbol = extract_symbol_from_topic(topic)?;
    let close = item
        .get("close")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())?;
    let ts = item.get("start").and_then(|v| v.as_u64()).unwrap_or(0);
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
fn parse_orderbook_snapshot(data: &[serde_json::Value], topic: &str) -> Option<PriceEvent> {
    let symbol = extract_symbol_from_topic(topic)?;
    // Orderbook data is a single object, not an array of items.
    // The "data" array in process_message may contain the object directly,
    // or the snapshot object may be the first element.
    // 訂單簿數據是單個對象。
    let obj = data.first()?;

    let bids = obj.get("b").and_then(|v| v.as_array())?;
    let asks = obj.get("a").and_then(|v| v.as_array())?;

    let best_bid = bids.first()
        .and_then(|b| b.as_array())
        .and_then(|arr| arr.first())
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);

    let best_ask = asks.first()
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

    let ts = obj.get("ts").and_then(|v| v.as_u64()).unwrap_or(0);

    let mut event = PriceEvent::new(symbol, mid_price, ts);
    event.bid_price = best_bid;
    event.ask_price = best_ask;
    event.metadata.insert("type".into(), "orderbook".into());
    Some(event)
}

/// Parse ticker snapshot — last price, 24h volume, best bid/ask.
/// 解析行情快照 — 最新價、24h 成交量、最優買賣價。
///
/// Bybit ticker: {"topic":"tickers.BTCUSDT","data":{"symbol":"BTCUSDT","lastPrice":"65000","volume24h":"12345",...}}
fn parse_ticker_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
    let symbol = extract_symbol_from_topic(topic)?;
    let last_price = item.get("lastPrice")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())?;
    let volume = item.get("volume24h")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);
    let bid = item.get("bid1Price")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);
    let ask = item.get("ask1Price")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);
    let ts = item.get("ts")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<u64>().ok())
        .or_else(|| item.get("ts").and_then(|v| v.as_u64()))
        .unwrap_or_else(|| {
            // Fallback: use current time if Bybit ticker omits ts (common on Demo)
            // 後備：如果 Bybit ticker 省略 ts（Demo 常見），使用當前時間
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0)
        });

    let turnover = item.get("turnover24h")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0);

    let mut event = PriceEvent::new(symbol, last_price, ts);
    event.volume_24h = volume;
    event.turnover_24h = turnover;
    event.bid_price = bid;
    event.ask_price = ask;
    event.metadata.insert("type".into(), "ticker".into());
    Some(event)
}

/// Parse liquidation event — forced liquidation on the market.
/// 解析清算事件 — 市場上的強制清算。
///
/// Bybit liquidation: {"topic":"liquidation.BTCUSDT","data":{"symbol":"BTCUSDT","side":"Buy","price":"65000","qty":"0.5","updatedTime":...}}
fn parse_liquidation_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
    let symbol = extract_symbol_from_topic(topic)?;
    let price = item.get("price")
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())?;
    let qty = item.get("size")
        .and_then(|v| v.as_str())
        .unwrap_or("0");
    let side = item.get("side")
        .and_then(|v| v.as_str())
        .unwrap_or("Unknown");
    let ts = item.get("updatedTime")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);

    let mut event = PriceEvent::new(symbol, price, ts);
    event.metadata.insert("type".into(), "liquidation".into());
    event.metadata.insert("side".into(), side.into());
    event.metadata.insert("qty".into(), qty.into());
    Some(event)
}

/// Parse price limit update — max buy / min sell boundaries.
/// 解析價格限制更新 — 最高買入/最低賣出邊界。
fn parse_price_limit_item(item: &serde_json::Value) -> Option<PriceEvent> {
    let symbol = item.get("symbol").and_then(|v| v.as_str())?.to_string();
    let max_price = item.get("maxPrice")
        .and_then(|v| v.as_str())
        .unwrap_or("0");
    let min_price = item.get("minPrice")
        .and_then(|v| v.as_str())
        .unwrap_or("0");
    let ts = item.get("ts")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);

    let mid = max_price.parse::<f64>().unwrap_or(0.0);
    let mut event = PriceEvent::new(symbol, mid, ts);
    event.metadata.insert("type".into(), "price_limit".into());
    event.metadata.insert("max_price".into(), max_price.into());
    event.metadata.insert("min_price".into(), min_price.into());
    Some(event)
}

/// Parse ADL (Auto-Deleveraging) notice — position at risk of forced reduction.
/// 解析 ADL 通知 — 持倉面臨強制減倉風險。
fn parse_adl_notice_item(item: &serde_json::Value) -> Option<PriceEvent> {
    let symbol = item.get("symbol").and_then(|v| v.as_str())?.to_string();
    let adl_rank = item.get("adlRankIndicator")
        .and_then(|v| v.as_i64().or_else(|| v.as_str().and_then(|s| s.parse().ok())))
        .unwrap_or(0);
    let side = item.get("side")
        .and_then(|v| v.as_str())
        .unwrap_or("Unknown");
    let ts = item.get("ts")
        .and_then(|v| v.as_u64())
        .unwrap_or(0);

    let mut event = PriceEvent::new(symbol, 0.0, ts);
    event.metadata.insert("type".into(), "adl_notice".into());
    event.metadata.insert("adl_rank".into(), adl_rank.to_string());
    event.metadata.insert("side".into(), side.into());
    Some(event)
}

/// Extract symbol from topic string like "publicTrade.BTCUSDT" → "BTCUSDT".
/// 從主題字串中提取交易對，如 "publicTrade.BTCUSDT" → "BTCUSDT"。
fn extract_symbol_from_topic(topic: &str) -> Option<String> {
    // Format: "prefix.SYMBOL" or "prefix.interval.SYMBOL"
    // Zero-allocation: rsplit returns last segment first / 零分配
    let sym = topic.rsplit('.').next()?;
    if sym.is_empty() {
        return None;
    }
    Some(sym.to_string())
}

/// Log state transition.
/// 記錄狀態轉換。
fn log_state(state: WsState, attempt: u32) {
    match state {
        WsState::Connected => info!(state = %state, "WebSocket connected / WebSocket 已連接"),
        WsState::Disconnected => info!(state = %state, "WebSocket disconnected / WebSocket 已斷開"),
        WsState::Connecting => {
            info!(state = %state, attempt = attempt, "WebSocket connecting / WebSocket 連接中")
        }
        WsState::Reconnecting => {
            warn!(state = %state, attempt = attempt, "WebSocket reconnecting / WebSocket 重連中")
        }
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

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
        let delay1 = std::cmp::min(base * BACKOFF_FACTOR.pow(1), MAX_RECONNECT_DELAY_MS);
        assert_eq!(delay1, 6000);
        // attempt 5: 3000 * 2^5 = 96000 → capped at 60000
        let delay5 = std::cmp::min(base * BACKOFF_FACTOR.pow(5), MAX_RECONNECT_DELAY_MS);
        assert_eq!(delay5, MAX_RECONNECT_DELAY_MS);
    }
}
