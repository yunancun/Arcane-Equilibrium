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
            subscriptions: vec!["kline.1.BTCUSDT".into(), "publicTrade.BTCUSDT".into()],
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

                    // Send subscription message / 發送訂閱消息
                    let sub_msg = serde_json::json!({
                        "op": "subscribe",
                        "args": self.subscriptions,
                    });
                    if let Err(e) = write.send(Message::Text(sub_msg.to_string().into())).await {
                        error!(error = %e, "failed to send subscribe / 發送訂閱失敗");
                        log_state(WsState::Reconnecting, attempt);
                        continue;
                    }
                    info!(topics = ?self.subscriptions, "subscribed / 已訂閱");

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
                                        self.process_message(&text).await;
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
    /// 處理來自 Bybit WS 的單條文本消息。
    async fn process_message(&self, text: &str) {
        // Try to extract price data from various Bybit message formats.
        // 嘗試從各種 Bybit 消息格式中提取價格數據。
        let parsed: serde_json::Value = match serde_json::from_str(text) {
            Ok(v) => v,
            Err(e) => {
                debug!(error = %e, "non-JSON WS message / 非 JSON WS 消息");
                return;
            }
        };

        // Skip pong / subscription confirmations / 跳過 pong 和訂閱確認
        if parsed.get("op").is_some() || parsed.get("success").is_some() {
            debug!("control message: {}", text);
            return;
        }

        // Bybit public trade: {"topic":"publicTrade.BTCUSDT","data":[{...}]}
        // Bybit kline: {"topic":"kline.1.BTCUSDT","data":[{...}]}
        let topic = parsed.get("topic").and_then(|t| t.as_str()).unwrap_or("");
        let data = match parsed.get("data").and_then(|d| d.as_array()) {
            Some(arr) => arr,
            None => return,
        };

        if topic.starts_with("publicTrade.") {
            for item in data {
                if let Some(event) = parse_trade_item(item, topic) {
                    if self.event_tx.send(event).await.is_err() {
                        warn!("event channel closed / 事件通道已關閉");
                        return;
                    }
                }
            }
        } else if topic.starts_with("kline.") {
            for item in data {
                if let Some(event) = parse_kline_item(item, topic) {
                    if self.event_tx.send(event).await.is_err() {
                        warn!("event channel closed / 事件通道已關閉");
                        return;
                    }
                }
            }
        } else {
            debug!(topic = topic, "unhandled topic / 未處理的主題");
        }
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
fn parse_kline_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
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
    fn test_parse_kline_item() {
        let item = serde_json::json!({
            "start": 1700000000000_u64,
            "end": 1700000060000_u64,
            "open": "64500.0",
            "close": "65000.0",
            "high": "65100.0",
            "low": "64400.0",
            "volume": "100.5",
        });
        let event = parse_kline_item(&item, "kline.1.BTCUSDT").unwrap();
        assert_eq!(event.symbol, "BTCUSDT");
        assert!((event.last_price - 65000.0).abs() < f64::EPSILON);
        assert!((event.volume_24h - 100.5).abs() < f64::EPSILON);
    }

    #[test]
    fn test_parse_kline_item_missing_close() {
        let item = serde_json::json!({"start": 1700000000000_u64});
        assert!(parse_kline_item(&item, "kline.1.BTCUSDT").is_none());
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
