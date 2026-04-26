//! WebSocket run loop — connect / heartbeat / reconnect / topic change.
//! WebSocket 主迴圈 — 連線 / 心跳 / 重連 / 訂閱動態變更。
//!
//! MODULE_NOTE (EN): `WsClient::run` is the long-lived async entry point.
//!   Owns the outer reconnect loop with exponential backoff (`BackoffConfig`
//!   3-60s) and the inner `tokio::select!` event loop (cancel / heartbeat /
//!   ScannerRunner topic-change channel / Bybit message stream). The
//!   `BACKOFF_POLICY` constant and 15s connect timeout (WS-TIMEOUT) are
//!   preserved byte-identical from the pre-split implementation. G9-02
//!   force-reconnect path closes the write half and falls into the outer
//!   reconnect path, replaying the cached `subscriptions` HashSet.
//! MODULE_NOTE (中): `WsClient::run` 是長壽命 async 入口；持有外層重連迴圈
//!   （指數退避 3-60s）與內層 `tokio::select!` 事件迴圈（取消 / 心跳 /
//!   ScannerRunner 訂閱變更 / Bybit 訊息流）。`BACKOFF_POLICY` 與 15s 連線
//!   超時（WS-TIMEOUT）字節級保留拆分前實作。G9-02 強制重連路徑關閉
//!   write half 後落入外層重連，並用 cached `subscriptions` HashSet 重訂閱。

use crate::common::ws_backoff::BackoffConfig;
use futures_util::{SinkExt, StreamExt};
use std::time::Duration;
use tokio_tungstenite::tungstenite::Message;
use tracing::{debug, error, info, warn};

use super::connection::{log_state, WsState};
use super::dispatch::ProcessOutcome;
use super::{WsClient, WsTopicChange};

/// Shared reconnect backoff policy (public-WS profile).
/// 公共 WS 共用的重連退避策略。
///
/// EN: Holds max-ms + multiplier + jitter pct. `base_ms` is intentionally NOT
///     frozen here — it is read from `cfg.reconnect_delay_ms` on every loop
///     iteration (FA-1 risk #1) and passed to `next_delay_with_base()`.
/// 中文: 封裝 max-ms + multiplier + jitter pct。`base_ms` 刻意不凍結於此 —
///     它在每次迴圈從 `cfg.reconnect_delay_ms` 讀取（FA-1 風險 #1）
///     並傳入 `next_delay_with_base()`。
pub(super) const BACKOFF_POLICY: BackoffConfig = BackoffConfig::ws_public_default(0);

/// Max topics per subscribe call (Bybit limit = 10)
/// 每次 subscribe 調用最大主題數（Bybit 限制 = 10）
pub(super) const SUBSCRIBE_BATCH_SIZE: usize = 10;

impl WsClient {
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
                                        match self.process_message(&text).await {
                                            ProcessOutcome::Continue => {}
                                            ProcessOutcome::Exit => {
                                                // Event channel closed — engine shutting down (RE-2 fix)
                                                // 事件通道已關閉 — 引擎正在關閉
                                                log_state(WsState::Disconnected, 0);
                                                return;
                                            }
                                            ProcessOutcome::ForceReconnect => {
                                                // G9-02: break inner loop → outer reconnect path
                                                // re-runs subscribe with cached `subscriptions`.
                                                // G9-02：break 內層迴圈 → 外層 reconnect 路徑
                                                // 會用 cached subscriptions 重訂閱。
                                                info!(
                                                    "G9-02 force reconnect requested — breaking inner loop / \
                                                     G9-02 強制重連請求 — 中斷內層迴圈"
                                                );
                                                let _ = write.send(Message::Close(None)).await;
                                                break;
                                            }
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
}
