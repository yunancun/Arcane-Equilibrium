//! WS message dispatch + topic-prefix routing.
//! WebSocket 訊息分派 + topic 前綴路由。
//!
//! MODULE_NOTE (EN): `process_message` is the per-message dispatcher. It
//!   parses one JSON line, skips control frames (op / success), normalises
//!   `data` into a slice, then routes by topic prefix to the parsers in
//!   `super::parsers`. Returns `ProcessOutcome` so the caller can distinguish
//!   normal continuation, channel-closed exit, and G9-02 force reconnect.
//!   Hot path: byte-identical with the original `WsClient::process_message`
//!   inline body.
//! MODULE_NOTE (中): `process_message` 是逐訊息分派器；解析單行 JSON、過濾控
//!   制幀（op / success）、把 `data` 統一為 slice，再依 topic 前綴路由到
//!   `super::parsers` 的對應 parser。回傳 `ProcessOutcome` 讓呼叫端可區分
//!   正常繼續、通道關閉退出、G9-02 強制重連三態。熱路徑：與原本
//!   `WsClient::process_message` 內嵌實作字節級相同。

use crate::ws_unknown_handler_guard::ShouldReconnect;
use openclaw_types::PriceEvent;
use tracing::{debug, warn};

use super::parsers::{
    now_ms, parse_adl_notice_item, parse_kline_item, parse_liquidation_item,
    parse_orderbook_snapshot, parse_price_limit_item, parse_ticker_item, parse_trade_item,
};
use super::WsClient;

/// Outcome of processing a single WS message.
/// 處理單條 WS 消息的結果。
///
/// EN: Replaces the original `bool` return so we can distinguish "exit run
///     loop" (channel closed) from "force reconnect" (G9-02 unknown handler
///     threshold) without overloading semantics.
/// 中文：取代原本的 `bool` 回傳，讓「退出 run loop」（通道關閉）與「強制
///     重連」（G9-02 未知 handler 達閾值）有不同語意，避免重載 bool。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(super) enum ProcessOutcome {
    /// Normal: keep reading next message / 正常：繼續讀取下一條訊息
    Continue,
    /// Event channel closed → caller should return from run() / 通道關閉 → 退出 run()
    Exit,
    /// G9-02 force reconnect: break inner loop, outer loop will reconnect+resubscribe
    /// G9-02 強制重連：break 內層迴圈，外層會重連並重訂閱
    ForceReconnect,
}

impl WsClient {
    /// Process a single text message from Bybit WS.
    /// 處理來自 Bybit WS 的單條文本消息。
    ///
    /// Returns:
    ///   - `ProcessOutcome::Continue`: handled normally, keep reading.
    ///   - `ProcessOutcome::Exit`: event channel closed, run loop should exit.
    ///   - `ProcessOutcome::ForceReconnect`: G9-02 unknown-handler guard hit
    ///     threshold and is armed → caller should break inner loop, falling
    ///     into the existing reconnect path which resubscribes the cached
    ///     `subscriptions` set.
    /// 回傳：
    ///   - `Continue`：正常處理，繼續讀取。
    ///   - `Exit`：事件通道已關閉，run loop 應退出。
    ///   - `ForceReconnect`：G9-02 未知 handler 守衛達閾值且已 arm → 呼叫端
    ///     break 內層迴圈，進入既有 reconnect 路徑，重訂閱 cached subscriptions。
    pub(super) async fn process_message(&self, text: &str) -> ProcessOutcome {
        // Try to extract price data from various Bybit message formats.
        // 嘗試從各種 Bybit 消息格式中提取價格數據。
        let parsed: serde_json::Value = match serde_json::from_str(text) {
            Ok(v) => v,
            Err(e) => {
                debug!(error = %e, "non-JSON WS message / 非 JSON WS 消息");
                return ProcessOutcome::Continue;
            }
        };

        // Skip pong / subscription confirmations / 跳過 pong 和訂閱確認
        if parsed.get("op").is_some() || parsed.get("success").is_some() {
            debug!("control message: {}", text);
            return ProcessOutcome::Continue;
        }

        // Bybit public data formats:
        //   Array: {"topic":"publicTrade.BTCUSDT","data":[{...}]}
        //   Object: {"topic":"tickers.BTCUSDT","data":{...}}
        //   Orderbook: {"topic":"orderbook.50.BTCUSDT","data":{"s":"...","b":[...],"a":[...]}}
        let topic = parsed.get("topic").and_then(|t| t.as_str()).unwrap_or("");
        let raw_data = match parsed.get("data") {
            Some(d) => d,
            None => return ProcessOutcome::Continue,
        };

        // Normalize to array: if data is a single object, wrap it / 統一為數組
        let data_vec: Vec<serde_json::Value>;
        let data: &[serde_json::Value] = if let Some(arr) = raw_data.as_array() {
            arr
        } else if raw_data.is_object() {
            data_vec = vec![raw_data.clone()];
            &data_vec
        } else {
            return ProcessOutcome::Continue;
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
        } else if topic.starts_with("allLiquidation.") || topic.starts_with("liquidation.") {
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
            // G9-02: track unknown topic; trigger force reconnect when armed
            // and threshold met. `now_ms()` is the openclaw_core shared helper
            // imported below at file-level (line ~437).
            // G9-02：追蹤未知 topic；arm 且達閾值時觸發強制重連。
            let decision = self.unknown_guard.record_unknown(topic, now_ms());
            match decision {
                ShouldReconnect::No => {
                    debug!(topic = topic, "unhandled topic / 未處理的主題");
                }
                ShouldReconnect::Yes => {
                    let (total, forced) = self.unknown_guard.snapshot_metrics();
                    warn!(
                        topic = topic,
                        unknown_total = total,
                        forced_reconnect_total = forced,
                        "G9-02 force reconnect on unknown handler threshold reached / \
                         G9-02 未知 handler 達閾值，強制重連"
                    );
                    return ProcessOutcome::ForceReconnect;
                }
            }
            return ProcessOutcome::Continue;
        };

        for event in events {
            if self.event_tx.send(event).await.is_err() {
                warn!("event channel closed / 事件通道已關閉");
                return ProcessOutcome::Exit;
            }
        }
        ProcessOutcome::Continue
    }
}
