//! Bybit V5 Private WebSocket client with HMAC authentication and auto-reconnect.
//! Bybit V5 私有 WebSocket 客戶端，支持 HMAC 認證和自動重連。
//!
//! MODULE_NOTE (EN): Connects to Bybit V5 private WebSocket, authenticates via
//!   HMAC-SHA256 (GET/realtime + expires), subscribes to order/execution/position/wallet
//!   topics, parses messages into PrivateWsEvent, pushes to mpsc channel.
//!   Exponential backoff reconnect, following the same pattern as ws_client.rs.
//! MODULE_NOTE (中): 連接 Bybit V5 私有 WebSocket，通過 HMAC-SHA256 認證
//!   (GET/realtime + expires)，訂閱訂單/成交/持倉/錢包主題，
//!   將消息解析為 PrivateWsEvent 並推送到 mpsc 通道。
//!   指數退避重連，遵循 ws_client.rs 相同模式。

use crate::bybit_rest_client::BybitEnvironment;
use futures_util::{SinkExt, StreamExt};
use hmac::{Hmac, Mac};
use sha2::Sha256;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tokio::sync::mpsc;
use tokio_tungstenite::tungstenite::Message;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

// ---------------------------------------------------------------------------
// Constants / 常量
// ---------------------------------------------------------------------------

/// Maximum reconnect delay (ms) / 最大重連延遲
const MAX_RECONNECT_DELAY_MS: u64 = 60_000;
/// Base reconnect delay (ms) / 基礎重連延遲
const BASE_RECONNECT_DELAY_MS: u64 = 3_000;
/// Backoff multiplier / 退避倍數
const BACKOFF_FACTOR: u64 = 2;
/// Ping interval (ms) — Bybit requires every 20s / Ping 間隔（Bybit 要求 20 秒）
const PING_INTERVAL_MS: u64 = 20_000;
/// Auth expires offset (ms) / 認證過期偏移
const AUTH_EXPIRES_OFFSET_MS: u64 = 10_000;

// Private topic list now lives on `BybitEnvironment::private_ws_topics()`
// because it varies by environment: mainnet supports `execution.fast` (~50ms)
// while demo/testnet only support the regular `execution` topic. Bybit silently
// accepts unknown topics on subscribe, so a wrong topic = total_fills stuck at 0
// with no error. See 2026-04-11 B-2 root-cause investigation.
// 私有 topic 列表已遷移到 `BybitEnvironment::private_ws_topics()`，因為它隨環境
// 而異：mainnet 支援 `execution.fast`（~50ms），demo/testnet 只支援普通的 `execution`。
// Bybit 對未知 topic 在 subscribe 時靜默接受，因此 topic 錯了會導致 total_fills
// 卡在 0 且無任何錯誤。詳見 2026-04-11 B-2 根因調查。

// ---------------------------------------------------------------------------
// Event types / 事件類型
// ---------------------------------------------------------------------------

/// Events emitted by the private WebSocket connection.
/// 私有 WebSocket 連接發出的事件。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub enum PrivateWsEvent {
    /// Order status update / 訂單狀態更新
    Order(OrderUpdate),
    /// Fill/execution notification / 成交通知
    Execution(ExecutionUpdate),
    /// Position change / 持倉變化
    Position(PositionUpdate),
    /// Wallet/balance update / 錢包餘額更新
    Wallet(WalletUpdate),
    /// DCP triggered — Bybit auto-cancelled orders due to connection loss.
    /// DCP 觸發 — Bybit 因連接斷開自動取消了訂單。
    DcpTriggered,
    /// Authentication succeeded / 認證成功
    AuthSuccess,
    /// Authentication failed / 認證失敗
    AuthFailed(String),
    /// Connection lost / 連接斷開
    Disconnected,
}

/// Order status update from Bybit private WS.
/// Bybit 私有 WS 的訂單狀態更新。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OrderUpdate {
    /// Bybit order ID / Bybit 訂單 ID
    #[serde(default)]
    pub order_id: String,
    /// Client-side order link ID / 客戶端訂單連結 ID
    #[serde(default)]
    pub order_link_id: String,
    /// Trading symbol / 交易對
    #[serde(default)]
    pub symbol: String,
    /// "Buy" or "Sell" / 買入或賣出
    #[serde(default)]
    pub side: String,
    /// Order type: "Market", "Limit", etc. / 訂單類型
    #[serde(default)]
    pub order_type: String,
    /// Order price / 訂單價格
    #[serde(default)]
    pub price: String,
    /// Order quantity / 訂單數量
    #[serde(default)]
    pub qty: String,
    /// Cumulative executed quantity / 累計成交數量
    #[serde(default)]
    pub cum_exec_qty: String,
    /// Order status: "New", "PartiallyFilled", "Filled", "Cancelled", "Rejected"
    /// 訂單狀態
    #[serde(default)]
    pub order_status: String,
    /// Creation timestamp / 創建時間戳
    #[serde(default)]
    pub created_time: String,
    /// Last update timestamp / 最後更新時間戳
    #[serde(default)]
    pub updated_time: String,
}

/// Execution/fill update from Bybit private WS.
/// Bybit 私有 WS 的成交更新。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ExecutionUpdate {
    /// Execution ID / 成交 ID
    #[serde(default)]
    pub exec_id: String,
    /// Parent order ID / 所屬訂單 ID
    #[serde(default)]
    pub order_id: String,
    /// Trading symbol / 交易對
    #[serde(default)]
    pub symbol: String,
    /// "Buy" or "Sell" / 買入或賣出
    #[serde(default)]
    pub side: String,
    /// Execution price / 成交價格
    #[serde(default)]
    pub exec_price: String,
    /// Execution quantity / 成交數量
    #[serde(default)]
    pub exec_qty: String,
    /// Execution fee / 成交手續費
    #[serde(default)]
    pub exec_fee: String,
    /// Execution type: "Trade", "Funding" / 成交類型
    #[serde(default)]
    pub exec_type: String,
    /// Execution timestamp / 成交時間戳
    #[serde(default)]
    pub exec_time: String,
}

/// Position update from Bybit private WS.
/// Bybit 私有 WS 的持倉更新。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PositionUpdate {
    /// Trading symbol / 交易對
    #[serde(default)]
    pub symbol: String,
    /// Position side: "Buy" (long), "Sell" (short), "None"
    /// 持倉方向
    #[serde(default)]
    pub side: String,
    /// Position size / 持倉量
    #[serde(default)]
    pub size: String,
    /// Average entry price / 平均入場價
    #[serde(default, alias = "avgPrice")]
    pub avg_price: String,
    /// Unrealised PnL / 未實現盈虧
    #[serde(default, alias = "unrealisedPnl")]
    pub unrealised_pnl: String,
    /// Current mark price / 當前標記價格
    #[serde(default)]
    pub mark_price: String,
    /// Liquidation price / 強平價格
    #[serde(default)]
    pub liq_price: String,
}

/// Wallet/balance update from Bybit private WS.
/// Bybit 私有 WS 的錢包餘額更新。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct WalletUpdate {
    /// Account type: "UNIFIED", "CONTRACT", etc. / 帳戶類型
    #[serde(default)]
    pub account_type: String,
    /// Per-coin balances / 各幣種餘額
    #[serde(default)]
    pub coin: Vec<CoinUpdate>,
}

/// Per-coin balance details within a wallet update.
/// 錢包更新中的單幣種餘額詳情。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CoinUpdate {
    /// Coin name / 幣種名稱
    #[serde(default)]
    pub coin: String,
    /// Total equity / 總權益
    #[serde(default)]
    pub equity: String,
    /// Wallet balance / 錢包餘額
    #[serde(default)]
    pub wallet_balance: String,
    /// Available to withdraw / 可提現金額
    #[serde(default)]
    pub available_to_withdraw: String,
}

// ---------------------------------------------------------------------------
// BybitPrivateWs / Bybit 私有 WebSocket 客戶端
// ---------------------------------------------------------------------------

/// Bybit V5 private WebSocket client with HMAC auth and auto-reconnect.
/// Bybit V5 私有 WebSocket 客戶端，支持 HMAC 認證和自動重連。
///
/// Usage: create with `new()`, then spawn `run()` on a tokio task.
/// The client pushes parsed events to the provided mpsc channel.
/// 用法：用 `new()` 創建，然後在 tokio 任務上啟動 `run()`。
/// 客戶端將解析的事件推送到提供的 mpsc 通道。
pub struct BybitPrivateWs {
    api_key: String,
    api_secret: String,
    environment: BybitEnvironment,
    cancel: CancellationToken,
    /// Channel to send parsed events / 發送解析事件的通道
    event_tx: mpsc::Sender<PrivateWsEvent>,
}

impl BybitPrivateWs {
    /// Create a new private WS client.
    /// 創建新的私有 WebSocket 客戶端。
    pub fn new(
        api_key: String,
        api_secret: String,
        env: BybitEnvironment,
        cancel: CancellationToken,
        event_tx: mpsc::Sender<PrivateWsEvent>,
    ) -> Self {
        Self {
            api_key,
            api_secret,
            environment: env,
            cancel,
            event_tx,
        }
    }

    /// Main loop: connect, authenticate, subscribe, read messages, reconnect on failure.
    /// 主循環：連接、認證、訂閱、讀取消息、失敗時重連。
    pub async fn run(&self) {
        let mut attempt: u32 = 0;

        loop {
            if self.cancel.is_cancelled() {
                info!("Private WS cancelled before connect / 私有 WS 在連接前被取消");
                break;
            }

            let url = self.environment.private_ws_url();
            info!(
                url = url,
                attempt = attempt,
                "Private WS connecting / 私有 WS 連接中"
            );

            match tokio_tungstenite::connect_async(url).await {
                Ok((ws_stream, _response)) => {
                    attempt = 0;
                    info!("Private WS connected / 私有 WS 已連接");

                    let (mut write, mut read) = ws_stream.split();

                    // Step 1: Send auth message / 步驟 1：發送認證消息
                    let auth_msg = self.generate_auth_message();
                    if let Err(e) = write.send(Message::Text(auth_msg.into())).await {
                        error!(error = %e, "Failed to send auth / 發送認證失敗");
                        let _ = self.event_tx.send(PrivateWsEvent::Disconnected).await;
                        continue;
                    }
                    debug!("Auth message sent / 認證消息已發送");

                    // Step 2: Wait for auth response before subscribing
                    // 步驟 2：等待認證回應後再訂閱
                    let mut authed = false;
                    let auth_timeout = tokio::time::sleep(Duration::from_secs(10));
                    tokio::pin!(auth_timeout);

                    loop {
                        tokio::select! {
                            _ = self.cancel.cancelled() => {
                                let _ = write.send(Message::Close(None)).await;
                                let _ = self.event_tx.send(PrivateWsEvent::Disconnected).await;
                                return;
                            }
                            _ = &mut auth_timeout => {
                                warn!("Auth timeout / 認證超時");
                                let _ = self.event_tx.send(PrivateWsEvent::AuthFailed("timeout".into())).await;
                                break;
                            }
                            msg = read.next() => {
                                match msg {
                                    Some(Ok(Message::Text(text))) => {
                                        if let Some(event) = self.parse_message(&text) {
                                            match &event {
                                                PrivateWsEvent::AuthSuccess => {
                                                    info!("Private WS auth success / 私有 WS 認證成功");
                                                    let _ = self.event_tx.send(event).await;
                                                    authed = true;
                                                    break;
                                                }
                                                PrivateWsEvent::AuthFailed(reason) => {
                                                    error!(reason = %reason, "Private WS auth failed / 私有 WS 認證失敗");
                                                    let _ = self.event_tx.send(event).await;
                                                    break;
                                                }
                                                _ => {
                                                    // Unexpected event during auth phase — ignore
                                                    // 認證階段的意外事件 — 忽略
                                                }
                                            }
                                        }
                                    }
                                    Some(Err(e)) => {
                                        warn!(error = %e, "WS read error during auth / 認證階段 WS 讀取錯誤");
                                        break;
                                    }
                                    None => {
                                        warn!("WS stream ended during auth / 認證階段 WS 流結束");
                                        break;
                                    }
                                    _ => {}
                                }
                            }
                        }
                    }

                    if !authed {
                        let _ = self.event_tx.send(PrivateWsEvent::Disconnected).await;
                        // Fall through to reconnect logic / 進入重連邏輯
                    } else {
                        // Step 3: Subscribe to private topics / 步驟 3：訂閱私有主題
                        // Topic list is environment-specific (mainnet vs demo). See
                        // BybitEnvironment::private_ws_topics() for the rationale.
                        let topics = self.environment.private_ws_topics();
                        let sub_msg = serde_json::json!({
                            "op": "subscribe",
                            "args": topics,
                        });
                        if let Err(e) = write.send(Message::Text(sub_msg.to_string().into())).await
                        {
                            error!(error = %e, "Failed to send subscribe / 發送訂閱失敗");
                            let _ = self.event_tx.send(PrivateWsEvent::Disconnected).await;
                            continue;
                        }
                        info!(
                            env = ?self.environment,
                            topics = ?topics,
                            "Subscribed to private topics / 已訂閱私有主題"
                        );

                        // Step 4: Message loop with periodic ping
                        // 步驟 4：帶定期 ping 的消息循環
                        let mut ping_timer =
                            tokio::time::interval(Duration::from_millis(PING_INTERVAL_MS));
                        ping_timer.tick().await; // Skip first immediate tick / 跳過第一次立即觸發

                        loop {
                            tokio::select! {
                                _ = self.cancel.cancelled() => {
                                    info!("Private WS shutdown requested / 私有 WS 請求關閉");
                                    let _ = write.send(Message::Close(None)).await;
                                    let _ = self.event_tx.send(PrivateWsEvent::Disconnected).await;
                                    return;
                                }
                                _ = ping_timer.tick() => {
                                    let ping = serde_json::json!({"op": "ping"});
                                    if let Err(e) = write.send(Message::Text(ping.to_string().into())).await {
                                        warn!(error = %e, "Ping failed / Ping 失敗");
                                        break;
                                    }
                                    debug!("Private WS ping sent / 私有 WS ping 已發送");
                                }
                                msg = read.next() => {
                                    match msg {
                                        Some(Ok(Message::Text(text))) => {
                                            if let Some(event) = self.parse_message(&text) {
                                                if self.event_tx.send(event).await.is_err() {
                                                    warn!("Event channel closed / 事件通道已關閉");
                                                    return;
                                                }
                                            }
                                        }
                                        Some(Ok(Message::Ping(data))) => {
                                            let _ = write.send(Message::Pong(data)).await;
                                        }
                                        Some(Ok(Message::Close(_))) => {
                                            info!("Server sent close / 服務器發送關閉幀");
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
                                        _ => {}
                                    }
                                }
                            }
                        }
                    }

                    // Connection lost — emit Disconnected, will reconnect
                    // 連接斷開 — 發出 Disconnected 事件，準備重連
                    let _ = self.event_tx.send(PrivateWsEvent::Disconnected).await;
                }
                Err(e) => {
                    warn!(error = %e, "Private WS connect failed / 私有 WS 連接失敗");
                }
            }

            // Exponential backoff / 指數退避
            attempt = attempt.saturating_add(1);
            let delay_ms = std::cmp::min(
                BASE_RECONNECT_DELAY_MS.saturating_mul(BACKOFF_FACTOR.saturating_pow(attempt)),
                MAX_RECONNECT_DELAY_MS,
            );
            info!(
                delay_ms = delay_ms,
                attempt = attempt,
                "Private WS reconnecting / 私有 WS 重連中"
            );

            tokio::select! {
                _ = self.cancel.cancelled() => {
                    info!("Private WS cancelled during backoff / 私有 WS 在退避期間被取消");
                    return;
                }
                _ = tokio::time::sleep(Duration::from_millis(delay_ms)) => {}
            }
        }
    }

    /// Generate HMAC-SHA256 auth message for Bybit private WS.
    /// 為 Bybit 私有 WS 生成 HMAC-SHA256 認證消息。
    ///
    /// Format: {"op":"auth","args":["api_key","expires_str","signature"]}
    /// signature = hex(hmac_sha256(api_secret, "GET/realtime" + expires))
    pub fn generate_auth_message(&self) -> String {
        self.generate_auth_message_with_time(current_time_ms())
    }

    /// Generate auth message with explicit timestamp (for testing).
    /// 使用指定時間戳生成認證消息（用於測試）。
    fn generate_auth_message_with_time(&self, now_ms: u64) -> String {
        let expires = now_ms + AUTH_EXPIRES_OFFSET_MS;
        let sign_payload = format!("GET/realtime{}", expires);

        let signature = hmac_sha256_hex(&self.api_secret, &sign_payload);

        serde_json::json!({
            "op": "auth",
            "args": [self.api_key, expires.to_string(), signature]
        })
        .to_string()
    }

    /// Parse an incoming JSON message into a PrivateWsEvent.
    /// 將收到的 JSON 消息解析為 PrivateWsEvent。
    ///
    /// Returns None for control messages (pong, subscription confirmations).
    /// 對控制消息（pong、訂閱確認）返回 None。
    fn parse_message(&self, text: &str) -> Option<PrivateWsEvent> {
        parse_private_message(text)
    }
}

// ---------------------------------------------------------------------------
// Standalone message parser (testable without WS connection)
// 獨立消息解析器（無需 WS 連接即可測試）
// ---------------------------------------------------------------------------

/// Parse a Bybit private WS message into a PrivateWsEvent.
/// 將 Bybit 私有 WS 消息解析為 PrivateWsEvent。
fn parse_private_message(text: &str) -> Option<PrivateWsEvent> {
    let parsed: serde_json::Value = serde_json::from_str(text).ok()?;

    // Auth response: {"op":"auth","success":true,"ret_msg":""}
    // 認證回應
    if let Some(op) = parsed.get("op").and_then(|v| v.as_str()) {
        if op == "auth" {
            let success = parsed
                .get("success")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            if success {
                return Some(PrivateWsEvent::AuthSuccess);
            } else {
                let msg = parsed
                    .get("ret_msg")
                    .and_then(|v| v.as_str())
                    .unwrap_or("unknown error")
                    .to_string();
                return Some(PrivateWsEvent::AuthFailed(msg));
            }
        }
        // Pong: skip silently / Pong: 靜默跳過
        if op == "pong" {
            return None;
        }
        // Subscribe confirmation: log success/failure so a wrong topic name
        // doesn't go undetected (B-2 lesson — silently dropping these once cost
        // us a full session of zero-fill mystery).
        // 訂閱確認：記錄成功或失敗，避免錯誤的 topic 名稱被靜默忽略。
        if op == "subscribe" {
            let success = parsed
                .get("success")
                .and_then(|v| v.as_bool())
                .unwrap_or(false);
            let ret_msg = parsed.get("ret_msg").and_then(|v| v.as_str()).unwrap_or("");
            let conn_id = parsed.get("conn_id").and_then(|v| v.as_str()).unwrap_or("");
            if success {
                info!(
                    success = success,
                    ret_msg = ret_msg,
                    conn_id = conn_id,
                    "Subscribe confirmation / 訂閱確認"
                );
            } else {
                error!(
                    success = success,
                    ret_msg = ret_msg,
                    conn_id = conn_id,
                    "Subscribe REJECTED / 訂閱被拒絕"
                );
            }
            return None;
        }
    }

    // Data messages: {"topic":"order","data":[{...}]}
    // 數據消息
    let topic = parsed.get("topic").and_then(|v| v.as_str())?;
    let data = parsed.get("data").and_then(|v| v.as_array())?;

    match topic {
        "order" => {
            // Parse first item (Bybit sends array, usually 1 element)
            // 解析第一個項目（Bybit 發送陣列，通常 1 個元素）
            for item in data {
                if let Ok(update) = serde_json::from_value::<OrderUpdate>(item.clone()) {
                    return Some(PrivateWsEvent::Order(update));
                }
            }
            None
        }
        "execution" => {
            for item in data {
                if let Ok(update) = serde_json::from_value::<ExecutionUpdate>(item.clone()) {
                    return Some(PrivateWsEvent::Execution(update));
                }
            }
            None
        }
        "position" => {
            for item in data {
                if let Ok(update) = serde_json::from_value::<PositionUpdate>(item.clone()) {
                    return Some(PrivateWsEvent::Position(update));
                }
            }
            None
        }
        "wallet" => {
            // Wallet has nested structure: data[0].coin = [...]
            // 錢包有嵌套結構
            for item in data {
                if let Ok(update) = serde_json::from_value::<WalletUpdate>(item.clone()) {
                    return Some(PrivateWsEvent::Wallet(update));
                }
            }
            None
        }
        "execution.fast" => {
            // Same payload as `execution` but lower latency (~50ms vs ~300ms).
            // V5 fast-execution carries fewer fields (no execFee/execValue/feeRate);
            // ExecutionUpdate uses serde defaults so missing fields parse as "".
            // 與 execution 相同 payload 但延遲更低（~50ms vs ~300ms）。
            // V5 execution.fast 欄位較少（無 execFee/execValue/feeRate），
            // ExecutionUpdate 用 serde default，缺失欄位解析為空字串。
            for item in data {
                if let Ok(update) = serde_json::from_value::<ExecutionUpdate>(item.clone()) {
                    return Some(PrivateWsEvent::Execution(update));
                }
            }
            None
        }
        "dcp" => {
            // DCP triggered: Bybit auto-cancelled orders due to prior disconnect.
            // NOT a connection loss — the current WS is alive; orders were cancelled.
            // DCP 觸發：Bybit 因之前的斷連自動取消了訂單。不是連接斷開。
            info!("DCP triggered — orders may have been cancelled / DCP 觸發 — 訂單可能已被取消");
            Some(PrivateWsEvent::DcpTriggered)
        }
        _ => {
            debug!(topic = topic, "Unhandled private topic / 未處理的私有主題");
            None
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers / 輔助函數
// ---------------------------------------------------------------------------

/// Compute HMAC-SHA256 and return hex string.
/// 計算 HMAC-SHA256 並返回十六進制字串。
fn hmac_sha256_hex(secret: &str, payload: &str) -> String {
    let mut mac =
        Hmac::<Sha256>::new_from_slice(secret.as_bytes()).expect("HMAC can take key of any size");
    mac.update(payload.as_bytes());
    hex::encode(mac.finalize().into_bytes())
}

/// Get current time in milliseconds since UNIX epoch.
/// 取得自 UNIX 紀元以來的毫秒級當前時間。
fn current_time_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Test auth message has correct JSON structure.
    /// 測試認證消息具有正確的 JSON 結構。
    #[test]
    fn test_auth_message_structure() {
        let cancel = CancellationToken::new();
        let (tx, _rx) = mpsc::channel(16);
        let ws = BybitPrivateWs::new(
            "TEST_API_KEY".into(),
            "TEST_API_SECRET".into(),
            BybitEnvironment::Demo,
            cancel,
            tx,
        );

        let msg = ws.generate_auth_message_with_time(1700000000000);
        let parsed: serde_json::Value = serde_json::from_str(&msg).unwrap();

        assert_eq!(parsed["op"], "auth");
        let args = parsed["args"].as_array().unwrap();
        assert_eq!(args.len(), 3);
        assert_eq!(args[0], "TEST_API_KEY");
        // expires = 1700000000000 + 10000 = 1700000010000
        assert_eq!(args[1], "1700000010000");
        // Signature is 64 hex chars / 簽名是 64 個十六進制字符
        assert_eq!(args[2].as_str().unwrap().len(), 64);
    }

    /// Test auth signature is deterministic with known inputs.
    /// 測試認證簽名在已知輸入下是確定性的。
    #[test]
    fn test_auth_signature_deterministic() {
        let cancel = CancellationToken::new();
        let (tx, _rx) = mpsc::channel(16);
        let ws = BybitPrivateWs::new(
            "MYKEY".into(),
            "MYSECRET".into(),
            BybitEnvironment::Demo,
            cancel,
            tx,
        );

        let msg1 = ws.generate_auth_message_with_time(1700000000000);
        let msg2 = ws.generate_auth_message_with_time(1700000000000);
        assert_eq!(msg1, msg2);

        // Verify the HMAC manually / 手動驗證 HMAC
        let expires = 1700000010000_u64;
        let expected_sig = hmac_sha256_hex("MYSECRET", &format!("GET/realtime{}", expires));
        let parsed: serde_json::Value = serde_json::from_str(&msg1).unwrap();
        assert_eq!(parsed["args"][2].as_str().unwrap(), expected_sig);
    }

    /// Test parsing auth success response.
    /// 測試解析認證成功回應。
    #[test]
    fn test_parse_auth_success() {
        let msg = r#"{"op":"auth","success":true,"ret_msg":""}"#;
        let event = parse_private_message(msg).unwrap();
        assert!(matches!(event, PrivateWsEvent::AuthSuccess));
    }

    /// Test parsing auth failure response.
    /// 測試解析認證失敗回應。
    #[test]
    fn test_parse_auth_failed() {
        let msg = r#"{"op":"auth","success":false,"ret_msg":"Invalid api_key"}"#;
        let event = parse_private_message(msg).unwrap();
        match event {
            PrivateWsEvent::AuthFailed(reason) => assert_eq!(reason, "Invalid api_key"),
            _ => panic!("Expected AuthFailed"),
        }
    }

    /// Test parsing order update message.
    /// 測試解析訂單更新消息。
    #[test]
    fn test_parse_order_update() {
        let msg = r#"{
            "topic": "order",
            "data": [{
                "orderId": "1234567890",
                "orderLinkId": "my-order-001",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "orderType": "Limit",
                "price": "65000.00",
                "qty": "0.001",
                "cumExecQty": "0",
                "orderStatus": "New",
                "createdTime": "1700000000000",
                "updatedTime": "1700000000000"
            }]
        }"#;
        let event = parse_private_message(msg).unwrap();
        match event {
            PrivateWsEvent::Order(order) => {
                assert_eq!(order.order_id, "1234567890");
                assert_eq!(order.symbol, "BTCUSDT");
                assert_eq!(order.side, "Buy");
                assert_eq!(order.order_status, "New");
                assert_eq!(order.price, "65000.00");
            }
            _ => panic!("Expected Order event"),
        }
    }

    /// Test parsing execution update message.
    /// 測試解析成交更新消息。
    #[test]
    fn test_parse_execution_update() {
        let msg = r#"{
            "topic": "execution",
            "data": [{
                "execId": "exec-001",
                "orderId": "1234567890",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "execPrice": "3500.50",
                "execQty": "0.5",
                "execFee": "0.875125",
                "execType": "Trade",
                "execTime": "1700000001000"
            }]
        }"#;
        let event = parse_private_message(msg).unwrap();
        match event {
            PrivateWsEvent::Execution(exec) => {
                assert_eq!(exec.exec_id, "exec-001");
                assert_eq!(exec.symbol, "ETHUSDT");
                assert_eq!(exec.exec_price, "3500.50");
                assert_eq!(exec.exec_fee, "0.875125");
                assert_eq!(exec.exec_type, "Trade");
            }
            _ => panic!("Expected Execution event"),
        }
    }

    /// B-2 regression: parsing must accept the V5 `execution.fast` topic name.
    /// Bybit silently accepts unknown topics, so a typo here makes total_fills
    /// permanently 0 — only a parser-level test catches it.
    /// B-2 回歸：解析必須接受 V5 `execution.fast` topic 名稱。Bybit 對未知 topic
    /// 不報錯，typo 會使 total_fills 永遠為 0，只有解析層測試能擋住。
    #[test]
    fn test_parse_fast_execution_update() {
        let msg = r#"{
            "topic": "execution.fast",
            "data": [{
                "execId": "fast-exec-001",
                "orderId": "1234567890",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "execPrice": "65000.00",
                "execQty": "0.001",
                "execFee": "0.0325",
                "execType": "Trade",
                "execTime": "1700000002000"
            }]
        }"#;
        let event = parse_private_message(msg).unwrap();
        match event {
            PrivateWsEvent::Execution(exec) => {
                assert_eq!(exec.exec_id, "fast-exec-001");
                assert_eq!(exec.symbol, "BTCUSDT");
                assert_eq!(exec.side, "Buy");
                assert_eq!(exec.exec_price, "65000.00");
            }
            _ => panic!("Expected Execution event from execution.fast topic"),
        }
    }

    /// B-2 regression: per-environment private topic selection.
    ///
    /// Bybit Demo (and Testnet/LiveDemo, which use the demo endpoint) does NOT
    /// support `execution.fast` — only mainnet does. Demo subscribe to
    /// `execution.fast` returns success:true but never pushes data, leaving
    /// total_fills permanently 0. Mainnet must use `execution.fast` for ~50ms
    /// latency. This test enforces the correct topic per environment so the
    /// regression cannot reappear at the subscribe-args layer.
    /// B-2 回歸：每個環境的私有 topic 選擇。Demo（含 Testnet/LiveDemo）不支援
    /// `execution.fast`，只能用 `execution`；mainnet 才用 `execution.fast`。
    #[test]
    fn test_private_topics_per_environment() {
        use crate::bybit_rest_client::BybitEnvironment;

        // Demo / Testnet / LiveDemo: must use `execution`, NOT `execution.fast`.
        for env in [
            BybitEnvironment::Demo,
            BybitEnvironment::Testnet,
            BybitEnvironment::LiveDemo,
        ] {
            let topics = env.private_ws_topics();
            assert!(
                topics.contains(&"execution"),
                "{:?} must subscribe to `execution` (the only fill topic supported on demo)",
                env
            );
            assert!(
                !topics.contains(&"execution.fast"),
                "{:?} must NOT subscribe to `execution.fast` (mainnet-only; \
                 demo silently drops it leaving total_fills=0)",
                env
            );
            // Sanity: also expect the other essential topics.
            assert!(topics.contains(&"order"), "{:?} missing `order` topic", env);
            assert!(
                topics.contains(&"position"),
                "{:?} missing `position` topic",
                env
            );
            assert!(
                topics.contains(&"wallet"),
                "{:?} missing `wallet` topic",
                env
            );
            // dcp is mainnet-only; demo rejects with "topic does not exist".
            assert!(
                !topics.contains(&"dcp"),
                "{:?} must NOT subscribe to `dcp` (mainnet-only; demo rejects \
                 with \"topic does not exist\" — visible noise per reconnect)",
                env
            );
        }

        // Mainnet: must use `execution.fast` for low-latency fills, and dcp for
        // server-side cancel-on-disconnect.
        let mainnet_topics = BybitEnvironment::Mainnet.private_ws_topics();
        assert!(
            mainnet_topics.contains(&"dcp"),
            "Mainnet must subscribe to `dcp` for server-side cancel-on-disconnect"
        );
        assert!(
            mainnet_topics.contains(&"execution.fast"),
            "Mainnet must subscribe to `execution.fast` (~50ms vs `execution` ~300ms)"
        );
        assert!(
            !mainnet_topics.contains(&"execution"),
            "Mainnet should not subscribe to both `execution` and `execution.fast` \
             (would yield duplicate fill events)"
        );
        assert!(
            !mainnet_topics.contains(&"fast-execution"),
            "Mainnet must NOT use the typo `fast-execution` — Bybit silently drops it"
        );
    }

    /// Test parsing position update message.
    /// 測試解析持倉更新消息。
    #[test]
    fn test_parse_position_update() {
        let msg = r#"{
            "topic": "position",
            "data": [{
                "symbol": "BTCUSDT",
                "side": "Buy",
                "size": "0.01",
                "avgPrice": "64500.00",
                "unrealisedPnl": "5.00",
                "markPrice": "65000.00",
                "liqPrice": "55000.00"
            }]
        }"#;
        let event = parse_private_message(msg).unwrap();
        match event {
            PrivateWsEvent::Position(pos) => {
                assert_eq!(pos.symbol, "BTCUSDT");
                assert_eq!(pos.side, "Buy");
                assert_eq!(pos.size, "0.01");
                assert_eq!(pos.unrealised_pnl, "5.00");
                assert_eq!(pos.liq_price, "55000.00");
            }
            _ => panic!("Expected Position event"),
        }
    }

    /// Test parsing wallet update message.
    /// 測試解析錢包更新消息。
    #[test]
    fn test_parse_wallet_update() {
        let msg = r#"{
            "topic": "wallet",
            "data": [{
                "accountType": "UNIFIED",
                "coin": [{
                    "coin": "USDT",
                    "equity": "10000.00",
                    "walletBalance": "9500.00",
                    "availableToWithdraw": "8000.00"
                }]
            }]
        }"#;
        let event = parse_private_message(msg).unwrap();
        match event {
            PrivateWsEvent::Wallet(wallet) => {
                assert_eq!(wallet.account_type, "UNIFIED");
                assert_eq!(wallet.coin.len(), 1);
                assert_eq!(wallet.coin[0].coin, "USDT");
                assert_eq!(wallet.coin[0].equity, "10000.00");
                assert_eq!(wallet.coin[0].wallet_balance, "9500.00");
            }
            _ => panic!("Expected Wallet event"),
        }
    }

    /// Test that pong messages are ignored (return None).
    /// 測試 pong 消息被忽略（返回 None）。
    #[test]
    fn test_parse_pong_ignored() {
        let msg = r#"{"op":"pong","args":["1700000000000"]}"#;
        assert!(parse_private_message(msg).is_none());
    }

    /// Test that subscribe confirmation is ignored.
    /// 測試訂閱確認被忽略。
    #[test]
    fn test_parse_subscribe_confirmation_ignored() {
        let msg = r#"{"op":"subscribe","success":true,"ret_msg":"","conn_id":"abc123"}"#;
        assert!(parse_private_message(msg).is_none());
    }

    /// Test that invalid JSON returns None.
    /// 測試無效 JSON 返回 None。
    #[test]
    fn test_parse_invalid_json() {
        assert!(parse_private_message("not json at all").is_none());
    }

    /// Test that unknown topic returns None.
    /// 測試未知主題返回 None。
    #[test]
    fn test_parse_unknown_topic() {
        let msg = r#"{"topic":"something_else","data":[{}]}"#;
        assert!(parse_private_message(msg).is_none());
    }

    /// Test HMAC helper produces 64-char hex.
    /// 測試 HMAC 輔助函數產生 64 字符十六進制。
    #[test]
    fn test_hmac_sha256_hex_length() {
        let sig = hmac_sha256_hex("secret", "payload");
        assert_eq!(sig.len(), 64);
    }
}
