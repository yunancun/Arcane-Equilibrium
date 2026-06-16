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
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;

mod connection;
mod dispatch;
mod parsers;
mod run_loop;
pub mod stats;

#[cfg(test)]
mod tests;

use std::sync::OnceLock;

/// recorder-v2 producer-side gate：WS 讀熱路徑是否需要做 full-depth L1 解析。
///
/// 為什麼是 process-global one-shot（OnceLock）而非 per-message `env::var`：
///   `parse_orderbook_snapshot` 跑在 WS 讀迴圈熱路徑（run_loop.rs:212，每條
///   orderbook.50 訊息一次）。逐訊息查 `std::env::var` 本身就是熱路徑性能 bug
///   （每次配置查找 + 字串配置），故只在進程啟動時讀一次並快取。對齊消費端
///   `OPENCLAW_RECORD_L1_EVENTS`（pipeline_ctor.rs:120 在建構時讀同一 env）的
///   gate 語意——兩端必須同源同預設，否則 producer 解析了 consumer 不消費的全簿。
///
/// 不變量：flag-OFF（預設）時 producer 完全 inert——不做 full-50-level 解析、不抽
///   update_id/seq、5 個 ob_* 欄保持 `PriceEvent::new` 的 None 預設；只走 v1 路徑
///   （bids5/asks5 top-5 + best-bid/ask + mid + metadata），與舊行為位元級相同。
fn l1_recording_enabled() -> bool {
    static FLAG: OnceLock<bool> = OnceLock::new();
    *FLAG.get_or_init(|| {
        std::env::var("OPENCLAW_RECORD_L1_EVENTS")
            .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
            .unwrap_or(false)
    })
}

// 公開再匯出 — 讓 crate 內呼叫端（main_ws.rs / main.rs / scanner/runner.rs）的
// import 路徑與拆分前完全一致。
pub use connection::WsState;
// Sprint 5+ Track B real probe SSOT；`main_health_emitters.rs` 取 Arc 透傳給
// `RealPipelineThroughputSource`。
pub use stats::WsStats;

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
    /// Sprint 5+ Track B real probe — WS tick rate / heartbeat lag 統計。
    /// 為什麼 Option：既有 caller（test / scanner / paper-only）不接 health
    /// pipeline 時走 None；emitter 端 fallback 走 PlaceholderPipelineThroughput
    /// Source，per spec §2.5 `RealPipelineThroughputSource` 接 Arc<WsStats>。
    /// `Arc` clone 跨 task 共享同 instance — dispatch.rs hot path 透過
    /// `inc_tick` 寫 + emitter 透過 accessor 讀。
    pub(super) ws_stats: Option<Arc<stats::WsStats>>,
    /// Sprint 5+ Track B real probe round 2 — actual subscription count 跨
    /// supervisor restart 的全局 Arc 計數器。
    ///
    /// 為什麼 `Arc<AtomicU32>` 跨 process 全局：
    ///   - WsClient instance 每次 supervisor restart 重建；`subscriptions` HashSet
    ///     生命週期跟 instance；caller 端讀 `subscriptions.len()` 需借用 instance，
    ///     不可從 supervisor 外部安全讀取（會跨 thread mutable borrow）。
    ///   - 改採 caller 端預構 `Arc<AtomicU32>`，supervisor 每次重建 WsClient 都
    ///     attach 同一 Arc；WsClient 在 subscribe / unsubscribe / 重連初始化時
    ///     fetch_add / fetch_sub / store。emitter 端 closure 走 `load(Relaxed)`
    ///     讀同一 counter，0 鎖 0 task race。
    ///   - 為什麼 Option：既有 8+ caller `WsClient::new` 不接 health pipeline 走
    ///     None；attach 後 supervisor restart 都同 instance（per `feedback_no
    ///     _dead_params` 反假陽性 fail-soft）。
    pub(super) subscriptions_counter: Option<Arc<AtomicU32>>,
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
            // Sprint 5+ Track B：default None；caller 走 `attach_ws_stats` 接通。
            // 既有 main_ws / scanner runner / paper test 不接 health pipeline，
            // 0 行為退化。
            ws_stats: None,
            // Sprint 5+ Track B round 2：default None；caller 走
            // `attach_subscriptions_counter` 注入 Arc<AtomicU32>。既有 caller 不接
            // 走 None 路徑，subscribe / unsubscribe 不寫 counter（fail-soft）。
            subscriptions_counter: None,
        }
    }

    /// Sprint 5+ Track B real probe — 注入 `WsStats` Arc。
    ///
    /// 為什麼 setter 而非 ctor 參數：
    ///   - 既有 `WsClient::new` signature 已被 8+ caller 引用；加參數會破測試
    ///     fixture 與 main_ws 編排。per `feedback_working_principles` 範圍最小化
    ///     走 setter pattern（對齊 既有 `with_topic_change_channel` setter 範式）。
    ///   - main_ws 在 ctor 後 + run() 前呼此 setter 注入；其它 caller 不呼即走
    ///     None fallback。
    pub fn attach_ws_stats(&mut self, ws_stats: Arc<stats::WsStats>) {
        self.ws_stats = Some(ws_stats);
    }

    /// Sprint 5+ Track B round 2 — 注入跨 supervisor restart 共享的
    /// `Arc<AtomicU32>` subscription counter。
    ///
    /// 為什麼 supervisor 預構 Arc 跨 restart 共享：
    ///   - 每次 supervisor restart 重建 WsClient + 新 `subscriptions` HashSet，
    ///     若計數器隨 instance 走會在 restart 時歸零，emitter 端 actual 讀到 0
    ///     觸發誤陽性 drift；改採 caller 預構 Arc，restart 後本 setter 同步
    ///     `subscriptions.len()` 至 counter 確保連續性。
    ///   - `Ordering::Relaxed` 因 counter 非 lock-acquire 語意（per spec §7.2）。
    pub fn attach_subscriptions_counter(&mut self, counter: Arc<AtomicU32>) {
        // 同步重連後 subscriptions 內容到 counter（restart 後初始 / 重新訂閱前
        // 走 0；訂閱完成後 update 至實際數）。caller 在 attach 後立刻 subscribe
        // 的常見路徑：先 attach（counter=0）→ subscribe（counter += 1）。
        counter.store(self.subscriptions.len() as u32, Ordering::Relaxed);
        self.subscriptions_counter = Some(counter);
    }

    /// Sprint 5+ Track B real probe — 暴露 subscription set count 給 emitter 端。
    ///
    /// 為什麼 actual = subscriptions.len()：
    ///   - WS-RC1 subscriptions HashSet 由 `subscribe()` 與 `with_topic_change_channel`
    ///     維護；確認 ack 後 hot path 端不另外增刪（per WS Track B 既有設計）。
    ///   - emitter 端 `current_ws_subscription_drift_count` 走 expected - actual
    ///     abs_diff；expected 由 caller 端從 SymbolRegistry / config snapshot 決定。
    pub fn subscriptions_count(&self) -> u32 {
        self.subscriptions.len() as u32
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
        let inserted = self.subscriptions.insert(topic.into());
        // Sprint 5+ Track B round 2：HashSet.insert() 已自動去重；只在實際新增時
        // 推 counter 避重複 fetch_add（per WS-RC1 既有去重設計）。
        if inserted {
            if let Some(ref c) = self.subscriptions_counter {
                c.fetch_add(1, Ordering::Relaxed);
            }
        }
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
