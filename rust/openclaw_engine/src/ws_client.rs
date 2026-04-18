//! Bybit WebSocket client with auto-reconnect (R01-3).
//! Bybit WebSocket 客戶端，支持自動重連。
//!
//! MODULE_NOTE (EN): Connects to Bybit V5 public WebSocket, subscribes to kline
//!   and trade streams, parses messages into PriceEvent, pushes to mpsc channel.
//!   Exponential backoff reconnect with configurable base delay.
//! MODULE_NOTE (中): 連接 Bybit V5 公開 WebSocket，訂閱 K 線和交易流，
//!   將消息解析為 PriceEvent 並推送到 mpsc 通道。
//!   指數退避重連，可配置基礎延遲。

use crate::common::ws_backoff::BackoffConfig;
use crate::config::ConfigManager;
use futures_util::{SinkExt, StreamExt};
use openclaw_types::{PriceEvent, PriceEventKind};
use std::collections::HashSet;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc;
use tokio_tungstenite::tungstenite::Message;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

// ---------------------------------------------------------------------------
// Runtime topic change channel / 運行時主題變更通道
// ---------------------------------------------------------------------------

/// Runtime WebSocket subscription change command.
/// Used by ScannerRunner to add/remove symbol topics without restarting.
/// 運行時 WebSocket 訂閱變更命令。
/// 由 ScannerRunner 使用，無需重啟即可添加/移除交易對主題。
#[derive(Debug)]
pub enum WsTopicChange {
    /// Subscribe to additional topics. Also recorded for reconnect replay.
    /// 訂閱額外主題。同時記錄以供重連時重播。
    Subscribe(Vec<String>),
    /// Unsubscribe from topics. Also removed from reconnect replay list.
    /// 取消訂閱主題。同時從重連重播列表中移除。
    Unsubscribe(Vec<String>),
}

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
    /// P-06: HashSet for O(1) dedup; Vec reconstituted for batch send.
    /// P-06：HashSet 去重 O(1)；批次發送時轉 Vec。
    subscriptions: HashSet<String>,
    /// Optional channel for runtime topic additions/removals (from ScannerRunner) / 運行時主題增減的可選通道
    topic_change_rx: Option<mpsc::UnboundedReceiver<WsTopicChange>>,
}

/// Shared reconnect backoff policy (public-WS profile).
/// 公共 WS 共用的重連退避策略。
///
/// EN: Holds max-ms + multiplier + jitter pct. `base_ms` is intentionally NOT
///     frozen here — it is read from `cfg.reconnect_delay_ms` on every loop
///     iteration (FA-1 risk #1) and passed to `next_delay_with_base()`.
/// 中文: 封裝 max-ms + multiplier + jitter pct。`base_ms` 刻意不凍結於此 —
///     它在每次迴圈從 `cfg.reconnect_delay_ms` 讀取（FA-1 風險 #1）
///     並傳入 `next_delay_with_base()`。
const BACKOFF_POLICY: BackoffConfig = BackoffConfig::ws_public_default(0);
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
            subscriptions: HashSet::new(),
            topic_change_rx: None,
        }
    }

    /// Add a startup subscription topic (called before run()).
    /// 添加啟動訂閱主題（在 run() 前調用）。
    pub fn subscribe(&mut self, topic: impl Into<String>) {
        self.subscriptions.insert(topic.into());
    }

    /// Attach a runtime topic-change channel. Returns the sender half for callers.
    /// Must be called before run(). ScannerRunner uses the returned sender.
    /// 附加運行時主題變更通道。返回調用方使用的發送半端。
    /// 必須在 run() 前調用。ScannerRunner 使用返回的發送端。
    pub fn with_topic_change_channel(&mut self) -> mpsc::UnboundedSender<WsTopicChange> {
        let (tx, rx) = mpsc::unbounded_channel();
        self.topic_change_rx = Some(rx);
        tx
    }

    /// Run the WebSocket client loop with auto-reconnect.
    /// Consumes self so that the run loop can mutate subscriptions for reconnect replay.
    /// 運行 WebSocket 客戶端循環，支持自動重連。
    /// 消耗 self 以便 run loop 可以修改訂閱列表用於重連重播。
    pub async fn run(mut self) {
        let mut attempt: u32 = 0;
        // Extract runtime topic-change receiver (if wired up by caller) / 提取運行時主題變更接收端
        let mut topic_change_rx = self.topic_change_rx.take();

        loop {
            if self.cancel.is_cancelled() {
                info!("WS client cancelled before connect / WS 客戶端在連接前被取消");
                break;
            }

            let cfg = self.config.get();
            let url = cfg.ws_url.clone();
            let base_delay = cfg.reconnect_delay_ms;
            let heartbeat_ms = cfg.heartbeat_interval_ms;

            log_state(WsState::Connecting, attempt);

            // WS-TIMEOUT: 15s connect timeout prevents indefinite hang on broken TCP/TLS
            // WS-TIMEOUT: 15s 連接超時，防止 TCP/TLS 握手掛死（如 03:31 事件）
            let connect_result = tokio::time::timeout(
                Duration::from_secs(15),
                tokio_tungstenite::connect_async(&url),
            )
            .await;

            let connect_result = match connect_result {
                Ok(r) => r,
                Err(_elapsed) => {
                    warn!(url = url, "WS connect timed out (15s) / WS 連接超時（15s）");
                    log_state(WsState::Reconnecting, attempt);
                    // FA-1 risk #2: connect-timeout path increments `attempt` AFTER
                    // sleeping (opposite order from main-exit path). Preserved here.
                    // FA-1 風險 #2：連接超時路徑於睡眠後才遞增 `attempt`
                    //（與主迴圈出口路徑順序相反）。此處保留原行為。
                    let delay = BACKOFF_POLICY.next_delay_with_base(base_delay, attempt);
                    tokio::time::sleep(delay).await;
                    attempt = attempt.saturating_add(1);
                    continue;
                }
            };

            match connect_result {
                Ok((ws_stream, _response)) => {
                    attempt = 0;
                    log_state(WsState::Connected, 0);

                    let (mut write, mut read) = ws_stream.split();

                    // Send subscriptions in batches of 10 (Bybit limit per call)
                    // 分批發送訂閱（Bybit 每次調用限制 10 個主題）
                    let sub_list: Vec<&String> = self.subscriptions.iter().collect();
                    let mut sub_ok = true;
                    for chunk in sub_list.chunks(SUBSCRIBE_BATCH_SIZE) {
                        let sub_msg = serde_json::json!({
                            "op": "subscribe",
                            "args": chunk,
                        });
                        if let Err(e) = write.send(Message::Text(sub_msg.to_string().into())).await
                        {
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
                        batches = (self.subscriptions.len() + SUBSCRIBE_BATCH_SIZE - 1)
                            / SUBSCRIBE_BATCH_SIZE,
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
                            // Runtime topic change from ScannerRunner / 來自 ScannerRunner 的運行時主題變更
                            change = async {
                                if let Some(ref mut rx) = topic_change_rx { rx.recv().await }
                                else { std::future::pending().await }
                            } => {
                                if let Some(change) = change {
                                    match change {
                                        WsTopicChange::Subscribe(topics) => {
                                            // 1. Record for reconnect replay / 記錄以供重連重播
                                            // P-06: HashSet.insert() handles dedup natively / HashSet.insert() 自動去重
                                            for t in &topics {
                                                self.subscriptions.insert(t.clone());
                                            }
                                            // 2. Send to Bybit in batches / 分批發送給 Bybit
                                            for chunk in topics.chunks(SUBSCRIBE_BATCH_SIZE) {
                                                let msg = serde_json::json!({"op":"subscribe","args":chunk});
                                                if let Err(e) = write.send(Message::Text(msg.to_string().into())).await {
                                                    warn!(error = %e, "[scanner] subscribe send failed");
                                                    break;
                                                }
                                                // 500ms inter-batch gap (Bybit rate limit)
                                                // 500ms 批次間隔（Bybit 速率限制）
                                                tokio::time::sleep(Duration::from_millis(500)).await;
                                            }
                                            info!(count = topics.len(), "[scanner] runtime subscribe sent");
                                        }
                                        WsTopicChange::Unsubscribe(topics) => {
                                            // 1. Remove from replay list / 從重播列表移除
                                            self.subscriptions.retain(|t| !topics.contains(t));
                                            // 2. Send unsubscribe to Bybit / 發送取消訂閱給 Bybit
                                            for chunk in topics.chunks(SUBSCRIBE_BATCH_SIZE) {
                                                let msg = serde_json::json!({"op":"unsubscribe","args":chunk});
                                                if let Err(e) = write.send(Message::Text(msg.to_string().into())).await {
                                                    warn!(error = %e, "[scanner] unsubscribe send failed");
                                                    break;
                                                }
                                            }
                                            info!(count = topics.len(), "[scanner] runtime unsubscribe sent");
                                        }
                                    }
                                }
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
            // FA-1 risk #2: main-exit path increments `attempt` BEFORE computing
            // the delay (opposite order from connect-timeout path). Preserved.
            // FA-1 風險 #2：主出口路徑於計算延遲前即遞增 `attempt`
            //（與連接超時路徑順序相反）。此處保留原行為。
            attempt = attempt.saturating_add(1);
            let delay = BACKOFF_POLICY.next_delay_with_base(base_delay, attempt);
            let delay_ms = delay.as_millis() as u64;
            info!(
                delay_ms = delay_ms,
                attempt = attempt,
                "reconnecting after delay / 延遲後重連"
            );

            tokio::select! {
                _ = self.cancel.cancelled() => {
                    log_state(WsState::Disconnected, 0);
                    return;
                }
                _ = tokio::time::sleep(delay) => {}
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
            data.iter()
                .filter_map(|item| parse_trade_item(item, topic))
                .collect()
        } else if topic.starts_with("kline.") {
            data.iter()
                .filter_map(|item| parse_kline_item(item, topic))
                .collect()
        } else if topic.starts_with("orderbook.") {
            parse_orderbook_snapshot(data, topic).into_iter().collect()
        } else if topic.starts_with("tickers.") {
            data.iter()
                .filter_map(|item| parse_ticker_item(item, topic))
                .collect()
        } else if topic.starts_with("liquidation.") {
            data.iter()
                .filter_map(|item| parse_liquidation_item(item, topic))
                .collect()
        } else if topic.starts_with("price-limit.") {
            data.iter()
                .filter_map(|item| parse_price_limit_item(item))
                .collect()
        } else if topic.starts_with("adl-notice.") {
            data.iter()
                .filter_map(|item| parse_adl_notice_item(item))
                .collect()
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

// S-04: use shared now_ms() from openclaw_core instead of local copy.
// S-04：使用 openclaw_core 的共用 now_ms() 取代本地副本。
use openclaw_core::now_ms;

/// Parse a Bybit public trade item into PriceEvent.
/// 將 Bybit 公開交易項目解析為 PriceEvent。
fn parse_trade_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
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
fn parse_kline_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
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
fn parse_orderbook_snapshot(data: &[serde_json::Value], topic: &str) -> Option<PriceEvent> {
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
fn parse_ticker_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
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

    let mut event = PriceEvent::new(symbol, last_price, ts);
    event.volume_24h = volume;
    event.turnover_24h = turnover;
    event.bid_price = bid;
    event.ask_price = ask;
    event.funding_rate = funding_rate;
    event.index_price = index_price;
    event.event_kind = Some(PriceEventKind::Ticker);
    event.metadata.insert("type".into(), "ticker".into());
    Some(event)
}

/// Parse liquidation event — forced liquidation on the market.
/// 解析清算事件 — 市場上的強制清算。
///
/// Bybit liquidation: {"topic":"liquidation.BTCUSDT","data":{"symbol":"BTCUSDT","side":"Buy","price":"65000","qty":"0.5","updatedTime":...}}
fn parse_liquidation_item(item: &serde_json::Value, topic: &str) -> Option<PriceEvent> {
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
fn parse_price_limit_item(item: &serde_json::Value) -> Option<PriceEvent> {
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
fn parse_adl_notice_item(item: &serde_json::Value) -> Option<PriceEvent> {
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
}
