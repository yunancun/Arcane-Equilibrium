//! Bybit WebSocket client with auto-reconnect (R01-3).
//! Bybit WebSocket 客戶端，支持自動重連。
//!
//! MODULE_NOTE (EN): Connects to Bybit V5 public WebSocket, subscribes to kline
//!   and trade streams, parses messages into PriceEvent, pushes to mpsc channel.
//!   Exponential backoff reconnect with configurable base delay.
//!
//!   Sibling layout (G9-02-FUP-WS-CLIENT-SPLIT, mirror of G5-FUP-IPC-MOD-SPLIT):
//!   - `mod.rs`        — public API: `WsClient` struct + ctor / small impls + `WsTopicChange`
//!   - `connection.rs` — `WsState` enum + `log_state` helper
//!   - `parsers.rs`    — Bybit message parsers + `extract_symbol_from_topic` + `now_ms` re-export
//!   - `dispatch.rs`   — `WsClient::process_message` + `ProcessOutcome`
//!   - `run_loop.rs`   — `WsClient::run` + `BACKOFF_POLICY` / `SUBSCRIBE_BATCH_SIZE` constants
//!   - `tests.rs`      — unit tests (parsers + backoff + state display)
//!
//! MODULE_NOTE (中): 連接 Bybit V5 公開 WebSocket，訂閱 K 線和交易流，
//!   將消息解析為 PriceEvent 並推送到 mpsc 通道。
//!   指數退避重連，可配置基礎延遲。
//!
//!   Sibling 結構（G9-02-FUP-WS-CLIENT-SPLIT，鏡射 G5-FUP-IPC-MOD-SPLIT）：
//!   - `mod.rs`        — 公開 API：`WsClient` struct、ctor、小 impl、`WsTopicChange`
//!   - `connection.rs` — `WsState` enum + `log_state`
//!   - `parsers.rs`    — Bybit 訊息 parsers + topic 解析 + `now_ms` 重匯出
//!   - `dispatch.rs`   — `process_message` 主分派 + `ProcessOutcome`
//!   - `run_loop.rs`   — `run` 主迴圈 + `BACKOFF_POLICY`、`SUBSCRIBE_BATCH_SIZE` 常量
//!   - `tests.rs`      — 單元測試（parsers + 退避 + state 顯示）

use crate::config::ConfigManager;
use crate::ws_unknown_handler_guard::UnknownHandlerGuard;
use openclaw_types::PriceEvent;
use std::collections::HashSet;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

mod connection;
mod dispatch;
mod parsers;
mod run_loop;

#[cfg(test)]
mod tests;

// Public re-exports — keep crate-level callers (`main_ws.rs`,
// `main.rs`, `scanner/runner.rs`) using the same import paths as before.
// 公開再匯出 — 讓 crate 內呼叫端（main_ws.rs / main.rs / scanner/runner.rs）的
// import 路徑與拆分前完全一致。
pub use connection::WsState;

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
// WsClient / WebSocket 客戶端
// ---------------------------------------------------------------------------

/// Bybit WebSocket client with auto-reconnect.
/// Bybit WebSocket 客戶端，支持自動重連。
pub struct WsClient {
    pub(super) config: Arc<ConfigManager>,
    pub(super) event_tx: mpsc::Sender<PriceEvent>,
    pub(super) cancel: CancellationToken,
    /// P-06: HashSet for O(1) dedup; Vec reconstituted for batch send.
    /// P-06：HashSet 去重 O(1)；批次發送時轉 Vec。
    pub(super) subscriptions: HashSet<String>,
    /// Optional channel for runtime topic additions/removals (from ScannerRunner) / 運行時主題增減的可選通道
    pub(super) topic_change_rx: Option<mpsc::UnboundedReceiver<WsTopicChange>>,
    /// G9-02: unknown-topic guard with force-reconnect trigger (DEFAULT-OFF
    /// via `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED=1`). `Arc` so the
    /// reference can be cloned for diagnostics / metrics readout while the
    /// run loop owns one for `record_unknown()` calls.
    /// G9-02：未知 topic 守衛 + 強制重連觸發（DEFAULT-OFF，透過環境變數
    /// `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED=1` arm）。`Arc` 包裝
    /// 以便 metrics 讀取 / 診斷可 clone reference，而 run loop 持有一份呼叫
    /// `record_unknown()`。
    pub(super) unknown_guard: Arc<UnknownHandlerGuard>,
}

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
            // G9-02: env-gate snapshot taken at construction time; flip the
            // env var requires `--rebuild` or restart for effect (acceptable
            // since this is a behavioural toggle, not a hot-reload knob).
            // G9-02：env-gate 在建構時取快照；改 env 需 `--rebuild` 或重啟才生效
            //（行為性 toggle，非熱重載參數，可接受）。
            unknown_guard: UnknownHandlerGuard::new_arc(),
        }
    }

    /// G9-02: clone the unknown-handler guard `Arc` for external metrics
    /// readout (e.g. healthcheck / status JSON writer). Consumers should
    /// only call `snapshot_metrics()` and `is_armed()` — never mutate.
    /// G9-02：複製未知 handler 守衛 `Arc`，供外部讀取 metrics（healthcheck /
    /// status JSON writer）。Consumer 只應呼叫 `snapshot_metrics()` 與
    /// `is_armed()`，不應 mutate。
    pub fn unknown_guard_handle(&self) -> Arc<UnknownHandlerGuard> {
        Arc::clone(&self.unknown_guard)
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
}
