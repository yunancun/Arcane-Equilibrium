//! High-level event processor for Bybit private WebSocket events.
//! Bybit 私有 WebSocket 事件的高級事件處理器。
//!
//! MODULE_NOTE (EN): Consumes PrivateWsEvent from the mpsc channel produced by
//!   BybitPrivateWs, dispatches to registered callbacks (on_fill, on_order_update,
//!   on_position_update, on_balance_update), and tracks aggregate statistics.
//!   Designed for engine integration — callbacks can update paper state, trigger
//!   reconciliation, or forward to the Python layer via IPC.
//! MODULE_NOTE (中): 從 BybitPrivateWs 生成的 mpsc 通道消費 PrivateWsEvent，
//!   分派到已註冊的回調（on_fill、on_order_update、on_position_update、
//!   on_balance_update），並追蹤彙總統計。
//!   為引擎整合設計 — 回調可更新 Paper 狀態、觸發對賬或通過 IPC 轉發到 Python 層。

use crate::bybit_private_ws::{
    ExecutionUpdate, OrderUpdate, PositionUpdate, PrivateWsEvent, WalletUpdate,
};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use tokio::sync::mpsc;
use tracing::{debug, info, warn};

// ---------------------------------------------------------------------------
// ListenerStats / 監聽器統計
// ---------------------------------------------------------------------------

/// Aggregate statistics for the execution listener.
/// 執行監聽器的彙總統計。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ListenerStats {
    /// Total fill events received / 收到的成交事件總數
    pub total_fills: u64,
    /// Total order update events / 訂單更新事件總數
    pub total_order_updates: u64,
    /// Total position update events / 持倉更新事件總數
    pub total_position_updates: u64,
    /// Total balance update events / 餘額更新事件總數
    pub total_balance_updates: u64,
    /// Timestamp (ms) of last event processed / 最後處理事件的時間戳（毫秒）
    pub last_event_ts: u64,
    /// Total auth success events / 認證成功事件總數
    pub total_auth_successes: u64,
    /// Total disconnects / 斷線總數
    pub total_disconnects: u64,
}

/// Internal atomic counters for thread-safe stats tracking.
/// 用於線程安全統計追蹤的內部原子計數器。
///
/// EN: Fields stay `pub(crate)` so auxiliary tasks like the private-WS
///     status-JSON writer (see `bybit_private_ws_status_writer.rs`) can poll
///     them without consuming the listener. The listener itself stays the
///     sole writer; `snapshot()` returns an owned, serialisable `ListenerStats`.
/// 中文：欄位保持 `pub(crate)`，讓私有 WS status JSON writer 等輔助任務可不
///     消耗 listener 即可輪詢；listener 本身仍是唯一寫入方，`snapshot()`
///     回傳可序列化的 `ListenerStats` 擁有式副本。
#[derive(Debug, Default)]
pub struct AtomicStats {
    pub(crate) total_fills: AtomicU64,
    pub(crate) total_order_updates: AtomicU64,
    pub(crate) total_position_updates: AtomicU64,
    pub(crate) total_balance_updates: AtomicU64,
    pub(crate) last_event_ts: AtomicU64,
    pub(crate) total_auth_successes: AtomicU64,
    pub(crate) total_disconnects: AtomicU64,
}

impl AtomicStats {
    /// Snapshot current counters into a ListenerStats.
    /// 將當前計數器快照為 ListenerStats。
    pub fn snapshot(&self) -> ListenerStats {
        ListenerStats {
            total_fills: self.total_fills.load(Ordering::Relaxed),
            total_order_updates: self.total_order_updates.load(Ordering::Relaxed),
            total_position_updates: self.total_position_updates.load(Ordering::Relaxed),
            total_balance_updates: self.total_balance_updates.load(Ordering::Relaxed),
            last_event_ts: self.last_event_ts.load(Ordering::Relaxed),
            total_auth_successes: self.total_auth_successes.load(Ordering::Relaxed),
            total_disconnects: self.total_disconnects.load(Ordering::Relaxed),
        }
    }

    /// Update the last-event timestamp to now.
    /// 更新最後事件時間戳為當前時間。
    fn touch(&self) {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;
        self.last_event_ts.store(now, Ordering::Relaxed);
    }
}

// ---------------------------------------------------------------------------
// ExecutionListener / 執行監聽器
// ---------------------------------------------------------------------------

/// High-level event processor that consumes PrivateWsEvent and dispatches
/// to registered callbacks for engine integration.
/// 高級事件處理器，消費 PrivateWsEvent 並分派到已註冊的回調以整合引擎。
pub struct ExecutionListener {
    /// Receiver for private WS events / 私有 WS 事件接收器
    event_rx: mpsc::Receiver<PrivateWsEvent>,
    /// Callback for fill/execution events / 成交事件回調
    on_fill: Option<Box<dyn Fn(ExecutionUpdate) + Send>>,
    /// Callback for order status updates / 訂單狀態更新回調
    on_order_update: Option<Box<dyn Fn(OrderUpdate) + Send>>,
    /// Callback for position changes / 持倉變化回調
    on_position_update: Option<Box<dyn Fn(PositionUpdate) + Send>>,
    /// Callback for balance/wallet updates / 餘額/錢包更新回調
    on_balance_update: Option<Box<dyn Fn(WalletUpdate) + Send>>,
    /// EXT-1: Callback for DCP triggered / DCP 觸發回調
    on_dcp: Option<Box<dyn Fn() + Send>>,
    /// EXT-1: Callback for WS disconnect / WS 斷連回調
    on_disconnect: Option<Box<dyn Fn() + Send>>,
    /// Aggregate stats (Arc for shared access) / 彙總統計（Arc 共享存取）
    stats: Arc<AtomicStats>,
}

impl ExecutionListener {
    /// Create a new execution listener consuming from the given channel.
    /// 創建新的執行監聽器，從給定通道消費事件。
    pub fn new(event_rx: mpsc::Receiver<PrivateWsEvent>) -> Self {
        Self {
            event_rx,
            on_fill: None,
            on_order_update: None,
            on_position_update: None,
            on_balance_update: None,
            on_dcp: None,
            on_disconnect: None,
            stats: Arc::new(AtomicStats::default()),
        }
    }

    /// Register a callback for fill/execution events.
    /// 註冊成交事件的回調。
    pub fn set_on_fill(&mut self, f: impl Fn(ExecutionUpdate) + Send + 'static) {
        self.on_fill = Some(Box::new(f));
    }

    /// Register a callback for order status updates.
    /// 註冊訂單狀態更新的回調。
    pub fn set_on_order_update(&mut self, f: impl Fn(OrderUpdate) + Send + 'static) {
        self.on_order_update = Some(Box::new(f));
    }

    /// Register a callback for position changes.
    /// 註冊持倉變化的回調。
    pub fn set_on_position_update(&mut self, f: impl Fn(PositionUpdate) + Send + 'static) {
        self.on_position_update = Some(Box::new(f));
    }

    /// Register a callback for balance/wallet updates.
    /// 註冊餘額/錢包更新的回調。
    pub fn set_on_balance_update(&mut self, f: impl Fn(WalletUpdate) + Send + 'static) {
        self.on_balance_update = Some(Box::new(f));
    }

    /// EXT-1: Register callback for DCP triggered events.
    /// EXT-1：註冊 DCP 觸發事件的回調。
    pub fn set_on_dcp(&mut self, f: impl Fn() + Send + 'static) {
        self.on_dcp = Some(Box::new(f));
    }

    /// EXT-1: Register callback for WS disconnect events.
    /// EXT-1：註冊 WS 斷連事件的回調。
    pub fn set_on_disconnect(&mut self, f: impl Fn() + Send + 'static) {
        self.on_disconnect = Some(Box::new(f));
    }

    /// Get a snapshot of current aggregate statistics.
    /// 取得當前彙總統計的快照。
    pub fn stats(&self) -> ListenerStats {
        self.stats.snapshot()
    }

    /// Share the underlying `Arc<AtomicStats>` so auxiliary tasks (e.g. the
    /// private-WS status-JSON writer) can poll live counters without
    /// consuming the listener.
    ///
    /// 共享底層 `Arc<AtomicStats>`，讓輔助任務（如私有 WS status JSON
    /// writer）可不消耗 listener 即輪詢即時計數器。
    pub fn stats_arc(&self) -> Arc<AtomicStats> {
        Arc::clone(&self.stats)
    }

    /// Run the event dispatch loop. Consumes self.
    /// 運行事件分派循環。消耗 self。
    ///
    /// Blocks until the channel is closed (sender dropped or WS shut down).
    /// 阻塞直到通道關閉（發送端丟棄或 WS 關閉）。
    pub async fn run(&mut self) {
        info!("ExecutionListener started / 執行監聽器已啟動");

        while let Some(event) = self.event_rx.recv().await {
            self.stats.touch();

            match event {
                PrivateWsEvent::Execution(exec) => {
                    self.stats.total_fills.fetch_add(1, Ordering::Relaxed);
                    debug!(
                        exec_id = %exec.exec_id,
                        symbol = %exec.symbol,
                        side = %exec.side,
                        price = %exec.exec_price,
                        qty = %exec.exec_qty,
                        "Fill received / 收到成交"
                    );
                    if let Some(ref cb) = self.on_fill {
                        cb(exec);
                    }
                }
                PrivateWsEvent::Order(order) => {
                    self.stats
                        .total_order_updates
                        .fetch_add(1, Ordering::Relaxed);
                    debug!(
                        order_id = %order.order_id,
                        symbol = %order.symbol,
                        status = %order.order_status,
                        "Order update / 訂單更新"
                    );
                    if let Some(ref cb) = self.on_order_update {
                        cb(order);
                    }
                }
                PrivateWsEvent::Position(pos) => {
                    self.stats
                        .total_position_updates
                        .fetch_add(1, Ordering::Relaxed);
                    debug!(
                        symbol = %pos.symbol,
                        side = %pos.side,
                        size = %pos.size,
                        "Position update / 持倉更新"
                    );
                    if let Some(ref cb) = self.on_position_update {
                        cb(pos);
                    }
                }
                PrivateWsEvent::Wallet(wallet) => {
                    self.stats
                        .total_balance_updates
                        .fetch_add(1, Ordering::Relaxed);
                    debug!(
                        account_type = %wallet.account_type,
                        coins = wallet.coin.len(),
                        "Wallet update / 錢包更新"
                    );
                    if let Some(ref cb) = self.on_balance_update {
                        cb(wallet);
                    }
                }
                PrivateWsEvent::AuthSuccess => {
                    self.stats
                        .total_auth_successes
                        .fetch_add(1, Ordering::Relaxed);
                    info!("Auth success event received / 收到認證成功事件");
                }
                PrivateWsEvent::AuthFailed(reason) => {
                    warn!(reason = %reason, "Auth failed event received / 收到認證失敗事件");
                }
                PrivateWsEvent::DcpTriggered => {
                    warn!("DCP triggered — open orders may have been cancelled / DCP 觸發 — 掛單可能已被取消");
                    if let Some(ref cb) = self.on_dcp {
                        cb();
                    }
                }
                PrivateWsEvent::Disconnected => {
                    self.stats.total_disconnects.fetch_add(1, Ordering::Relaxed);
                    info!("Disconnect event received / 收到斷線事件");
                    if let Some(ref cb) = self.on_disconnect {
                        cb();
                    }
                }
            }
        }

        info!("ExecutionListener stopped (channel closed) / 執行監聽器已停止（通道關閉）");
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicU64 as StdAtomicU64;

    /// Test that fills are dispatched and counted.
    /// 測試成交事件被分派並計數。
    #[tokio::test]
    async fn test_fill_dispatch_and_count() {
        let (tx, rx) = mpsc::channel(16);
        let mut listener = ExecutionListener::new(rx);

        let fill_count = Arc::new(StdAtomicU64::new(0));
        let fill_count_clone = Arc::clone(&fill_count);
        listener.set_on_fill(move |_exec| {
            fill_count_clone.fetch_add(1, Ordering::Relaxed);
        });

        // Send 3 fill events / 發送 3 個成交事件
        for i in 0..3 {
            tx.send(PrivateWsEvent::Execution(ExecutionUpdate {
                exec_id: format!("exec-{}", i),
                order_id: "order-1".into(),
                symbol: "BTCUSDT".into(),
                side: "Buy".into(),
                exec_price: "65000.00".into(),
                exec_qty: "0.001".into(),
                exec_fee: "0.01".into(),
                exec_type: "Trade".into(),
                exec_time: "1700000000000".into(),
            }))
            .await
            .unwrap();
        }
        drop(tx); // Close channel to end listener loop / 關閉通道結束監聽循環

        listener.run().await;

        assert_eq!(fill_count.load(Ordering::Relaxed), 3);
        assert_eq!(listener.stats().total_fills, 3);
    }

    /// Test that order updates are dispatched and counted.
    /// 測試訂單更新被分派並計數。
    #[tokio::test]
    async fn test_order_update_dispatch() {
        let (tx, rx) = mpsc::channel(16);
        let mut listener = ExecutionListener::new(rx);

        let order_symbols = Arc::new(std::sync::Mutex::new(Vec::new()));
        let order_symbols_clone = Arc::clone(&order_symbols);
        listener.set_on_order_update(move |order| {
            order_symbols_clone.lock().unwrap().push(order.symbol);
        });

        tx.send(PrivateWsEvent::Order(OrderUpdate {
            order_id: "111".into(),
            order_link_id: "link-1".into(),
            symbol: "ETHUSDT".into(),
            side: "Sell".into(),
            order_type: "Limit".into(),
            price: "3500.00".into(),
            qty: "1.0".into(),
            cum_exec_qty: "0".into(),
            order_status: "New".into(),
            created_time: "1700000000000".into(),
            updated_time: "1700000000000".into(),
            reject_reason: String::new(),
        }))
        .await
        .unwrap();
        drop(tx);

        listener.run().await;

        let symbols = order_symbols.lock().unwrap();
        assert_eq!(symbols.len(), 1);
        assert_eq!(symbols[0], "ETHUSDT");
        assert_eq!(listener.stats().total_order_updates, 1);
    }

    /// Test that position updates are dispatched and counted.
    /// 測試持倉更新被分派並計數。
    #[tokio::test]
    async fn test_position_update_dispatch() {
        let (tx, rx) = mpsc::channel(16);
        let mut listener = ExecutionListener::new(rx);

        let pos_count = Arc::new(StdAtomicU64::new(0));
        let pos_count_clone = Arc::clone(&pos_count);
        listener.set_on_position_update(move |_pos| {
            pos_count_clone.fetch_add(1, Ordering::Relaxed);
        });

        tx.send(PrivateWsEvent::Position(PositionUpdate {
            symbol: "BTCUSDT".into(),
            side: "Buy".into(),
            size: "0.01".into(),
            avg_price: "64500.00".into(),
            unrealised_pnl: "5.00".into(),
            mark_price: "65000.00".into(),
            liq_price: "55000.00".into(),
        }))
        .await
        .unwrap();
        drop(tx);

        listener.run().await;

        assert_eq!(pos_count.load(Ordering::Relaxed), 1);
        assert_eq!(listener.stats().total_position_updates, 1);
    }

    /// Test that wallet updates are dispatched and counted.
    /// 測試錢包更新被分派並計數。
    #[tokio::test]
    async fn test_wallet_update_dispatch() {
        let (tx, rx) = mpsc::channel(16);
        let mut listener = ExecutionListener::new(rx);

        let balance_count = Arc::new(StdAtomicU64::new(0));
        let balance_count_clone = Arc::clone(&balance_count);
        listener.set_on_balance_update(move |_wallet| {
            balance_count_clone.fetch_add(1, Ordering::Relaxed);
        });

        tx.send(PrivateWsEvent::Wallet(WalletUpdate {
            account_type: "UNIFIED".into(),
            coin: vec![super::super::bybit_private_ws::CoinUpdate {
                coin: "USDT".into(),
                equity: "10000.00".into(),
                wallet_balance: "9500.00".into(),
                available_to_withdraw: "8000.00".into(),
            }],
        }))
        .await
        .unwrap();
        drop(tx);

        listener.run().await;

        assert_eq!(balance_count.load(Ordering::Relaxed), 1);
        assert_eq!(listener.stats().total_balance_updates, 1);
    }

    /// Test mixed events and aggregate stats.
    /// 測試混合事件和彙總統計。
    #[tokio::test]
    async fn test_mixed_events_stats() {
        let (tx, rx) = mpsc::channel(32);
        let mut listener = ExecutionListener::new(rx);

        // No callbacks — just counting / 沒有回調 — 只計數
        tx.send(PrivateWsEvent::AuthSuccess).await.unwrap();
        tx.send(PrivateWsEvent::Execution(ExecutionUpdate {
            exec_id: "e1".into(),
            order_id: "o1".into(),
            symbol: "BTCUSDT".into(),
            side: "Buy".into(),
            exec_price: "65000".into(),
            exec_qty: "0.01".into(),
            exec_fee: "0.1".into(),
            exec_type: "Trade".into(),
            exec_time: "1700000000000".into(),
        }))
        .await
        .unwrap();
        tx.send(PrivateWsEvent::Order(OrderUpdate {
            order_id: "o1".into(),
            order_link_id: String::new(),
            symbol: "BTCUSDT".into(),
            side: "Buy".into(),
            order_type: "Market".into(),
            price: "65000".into(),
            qty: "0.01".into(),
            cum_exec_qty: "0.01".into(),
            order_status: "Filled".into(),
            created_time: "1700000000000".into(),
            updated_time: "1700000001000".into(),
            reject_reason: String::new(),
        }))
        .await
        .unwrap();
        tx.send(PrivateWsEvent::Disconnected).await.unwrap();
        drop(tx);

        listener.run().await;

        let stats = listener.stats();
        assert_eq!(stats.total_fills, 1);
        assert_eq!(stats.total_order_updates, 1);
        assert_eq!(stats.total_auth_successes, 1);
        assert_eq!(stats.total_disconnects, 1);
        assert_eq!(stats.total_position_updates, 0);
        assert_eq!(stats.total_balance_updates, 0);
        assert!(stats.last_event_ts > 0);
    }

    /// Test listener with no callbacks still counts events.
    /// 測試沒有回調的監聽器仍然計數事件。
    #[tokio::test]
    async fn test_no_callbacks_still_counts() {
        let (tx, rx) = mpsc::channel(16);
        let mut listener = ExecutionListener::new(rx);

        tx.send(PrivateWsEvent::Execution(ExecutionUpdate {
            exec_id: "e1".into(),
            order_id: "o1".into(),
            symbol: "BTCUSDT".into(),
            side: "Buy".into(),
            exec_price: "65000".into(),
            exec_qty: "0.01".into(),
            exec_fee: "0.1".into(),
            exec_type: "Trade".into(),
            exec_time: "1700000000000".into(),
        }))
        .await
        .unwrap();
        drop(tx);

        listener.run().await;

        assert_eq!(listener.stats().total_fills, 1);
    }

    /// Test initial stats are all zero.
    /// 測試初始統計全部為零。
    #[test]
    fn test_initial_stats_zero() {
        let (_tx, rx) = mpsc::channel(1);
        let listener = ExecutionListener::new(rx);
        let stats = listener.stats();
        assert_eq!(stats.total_fills, 0);
        assert_eq!(stats.total_order_updates, 0);
        assert_eq!(stats.total_position_updates, 0);
        assert_eq!(stats.total_balance_updates, 0);
        assert_eq!(stats.last_event_ts, 0);
        assert_eq!(stats.total_auth_successes, 0);
        assert_eq!(stats.total_disconnects, 0);
    }
}
