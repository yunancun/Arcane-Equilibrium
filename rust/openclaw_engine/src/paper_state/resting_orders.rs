//! Paper resting-limit-order queue — EDGE-P2-3 Phase 1B-4.1 plumbing.
//! 紙盤掛單隊列 — EDGE-P2-3 Phase 1B-4.1 純接線。
//!
//! MODULE_NOTE (EN): Paper-only infrastructure for PostOnly limit orders that
//!   must wait for a future tick to touch/cross the limit price. Before 1B-4,
//!   the Paper dispatch path short-circuited every intent to an immediate
//!   market fill (`router.rs::execute_market_fill_with_rate`), which hid the
//!   cost of passive execution and polluted edge estimates with optimistic
//!   fills. 1B-4.1 lands only the plumbing (queue + helpers + struct); 1B-4.2
//!   will wire the enqueue + tick-level touch/cross evaluation + bias guards.
//!
//!   Zero behaviour change at this commit: the queue stays empty because no
//!   call site enqueues yet. The timeout-cancel sweep in 1B-3.2
//!   (event_consumer/mod.rs) is exchange-side; Paper had no analogue, so this
//!   module also prepares the parallel path.
//!
//! MODULE_NOTE (中): 紙盤 PostOnly 掛單專用隊列。1B-4 前，紙盤 dispatch 會把每
//!   一個 intent 直接以市價成交（router.rs::execute_market_fill_with_rate），
//!   系統性高估 edge 並污染 edge_estimates。1B-4.1 只接線（struct + 隊列 +
//!   helper），1B-4.2 再接上 enqueue + tick 碰觸/穿越評估 + bias 保護。
//!
//!   本提交零行為變更：隊列在生產保持空（尚無 call site enqueue）。1B-3.2 的
//!   timeout-cancel sweep 是交易所側專用，Paper 原本無對應機制，此模組為其
//!   平行路徑做準備。

use super::PaperState;
use crate::order_manager::TimeInForce;
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, VecDeque};

/// EDGE-P2-3 Phase 1B-4.1: in-memory resting PostOnly limit order for Paper
/// simulation. The queue lives on `PaperState.resting_limit_orders` keyed by
/// symbol. 1B-4.2 will tick-walk each queue and classify `Keep` / `Fill` /
/// `Timeout` against the current tick price.
///
/// Design notes:
/// - `mid_price_at_submit` captures the mark at enqueue time so bias guard #4
///   (adverse-selection marker) can compare `mid@fill - mid@submit` without
///   needing to re-scan tick history. Stored even when unknown (0.0 fallback)
///   so the row shape is stable for future serialisation.
/// - `deadline_ms` is absolute wall-clock (ms) rather than a relative offset
///   to keep sweep logic trivial: `if now_ms >= deadline_ms { timeout }`.
/// - `order_link_id` mirrors the client-minted id used by the exchange-side
///   tracker so operator reports and ML training can correlate paper +
///   exchange rows. Required (never empty) in the 1B-4.2 enqueue path.
/// - `context_id` is the signal-time id (FILL-CONTEXT-LINKAGE-1) so the
///   eventual `trading.fills.entry_context_id` JOIN works for paper fills
///   the same way it works for exchange fills.
///
/// EDGE-P2-3 Phase 1B-4.1：紙盤用的掛中 PostOnly 限價單。隊列放在
/// `PaperState.resting_limit_orders`，以 symbol 為鍵。1B-4.2 會逐 tick 遍歷
/// 隊列並對照當下 tick 價分類 `Keep` / `Fill` / `Timeout`。
///
/// 設計要點：
/// - `mid_price_at_submit` 於 enqueue 時錄入當下 mark，供 bias 保護 #4
///   adverse-selection marker 以 `mid@fill - mid@submit` 比對，不需回掃 tick。
/// - `deadline_ms` 採絕對 wall-clock（ms）而非相對位移，令 sweep 邏輯直觀：
///   `if now_ms >= deadline_ms { timeout }`。
/// - `order_link_id` 鏡射交易所側 tracker 的 client-minted id，讓 operator
///   報告與 ML 訓練可跨紙盤 / 交易所關聯。1B-4.2 enqueue 後必填。
/// - `context_id` 為訊號時刻 id（FILL-CONTEXT-LINKAGE-1），保證紙盤 fill 與
///   交易所 fill 在 trading.fills.entry_context_id 的 JOIN 一致。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RestingLimitOrder {
    /// Trading symbol / 交易對
    pub symbol: String,
    /// Long direction (buy limit below mid, sell limit above mid).
    /// 多方向（買限單在 mid 之下，賣限單在 mid 之上）。
    pub is_long: bool,
    /// Requested quantity / 請求數量
    pub qty: f64,
    /// Limit price the order waits to be touched/crossed at.
    /// 訂單等待被碰觸 / 穿越的限價。
    pub limit_price: f64,
    /// Time-in-force. For 1B-4 this is always `PostOnly`; the field is kept
    /// explicit so future `Limit+IOC` or `Limit+GTC` extensions do not need a
    /// schema change.
    /// TIF。1B-4 恆為 PostOnly；保留欄位以免未來支援 Limit+IOC/GTC 時需改 schema。
    pub time_in_force: TimeInForce,
    /// Wall-clock ms when the order was submitted / 送出時間（ms）。
    pub submit_ts_ms: u64,
    /// Absolute deadline (ms): once `now_ms >= deadline_ms` the 1B-4.2 sweep
    /// cancels+removes the order. Derived at enqueue as `submit_ts_ms +
    /// maker_timeout_ms` using the per-intent timeout so policy stays data-
    /// driven rather than baked in.
    /// 絕對截止時間（ms）：`now_ms >= deadline_ms` 時 1B-4.2 sweep 取消 + 移除。
    /// enqueue 時由 `submit_ts_ms + maker_timeout_ms` 得出，策略走資料驅動。
    pub deadline_ms: u64,
    /// Mid price at submit for bias-guard #4 adverse-selection tracking.
    /// Zero when unknown (e.g. first tick before any mid is available).
    /// 送出時的 mid，供 bias 保護 #4 adverse-selection 追蹤。未知時為 0。
    pub mid_price_at_submit: f64,
    /// Client-minted order link id mirroring the exchange-side tracker.
    /// 客戶端 orderLinkId，與交易所側 tracker 對齊。
    pub order_link_id: String,
    /// FILL-CONTEXT-LINKAGE-1 signal-time id — threaded to
    /// `trading.fills.entry_context_id` on fill so ML training JOINs.
    /// FILL-CONTEXT-LINKAGE-1 訊號時刻 id；成交時寫入 trading.fills.entry_context_id。
    pub context_id: String,
    /// Originating strategy name ("grid_trading" in 1B-4; explicit field to
    /// keep owner_strategy attribution stable for any future maker strategy).
    /// 發起策略名稱（1B-4 為 "grid_trading"；欄位明列以便未來其他 maker 策略擴充）。
    pub strategy: String,
}

impl PaperState {
    /// Test / bootstrap helper: install a non-empty resting queue directly.
    /// Production code in 1B-4.2 will go through `enqueue_resting_limit_order`
    /// instead; this is kept `pub` only so restore paths and tests can seed
    /// the queue without re-enacting the enqueue flow.
    /// 測試 / bootstrap helper：直接安裝非空掛單隊列。1B-4.2 的生產路徑走
    /// `enqueue_resting_limit_order`；本函數僅供還原路徑與測試使用。
    pub fn seed_resting_limit_orders(
        &mut self,
        queues: HashMap<String, VecDeque<RestingLimitOrder>>,
    ) {
        self.resting_limit_orders = queues;
    }

    /// EDGE-P2-3 Phase 1B-4.1: append a new resting order to the per-symbol
    /// queue. FIFO so queue-position semantics stay intuitive when 1B-4.2
    /// wires touch/cross logic. Returns nothing — enqueue never fails.
    /// EDGE-P2-3 Phase 1B-4.1：將新掛單 FIFO append 到 per-symbol 隊列。
    pub fn enqueue_resting_limit_order(&mut self, order: RestingLimitOrder) {
        self.resting_limit_orders
            .entry(order.symbol.clone())
            .or_default()
            .push_back(order);
    }

    /// Read-only view of resting orders for a symbol. Empty slice when the
    /// symbol has never had a resting order enqueued.
    /// 某 symbol 的掛單唯讀視圖。若從未 enqueue 則回空切片。
    pub fn resting_limit_orders_for(&self, symbol: &str) -> &[RestingLimitOrder] {
        static EMPTY: [RestingLimitOrder; 0] = [];
        match self.resting_limit_orders.get(symbol) {
            Some(q) => q.as_slices().0, // VecDeque.as_slices() head slice is enough for read-only callers
            None => &EMPTY[..],
        }
    }

    /// Total number of resting orders across all symbols. 0 when queue is empty.
    /// 所有 symbol 合計的掛單數量。
    pub fn resting_limit_order_count(&self) -> usize {
        self.resting_limit_orders.values().map(|q| q.len()).sum()
    }

    /// Number of resting orders for a specific symbol.
    /// 單一 symbol 的掛單數量。
    pub fn resting_limit_order_count_for(&self, symbol: &str) -> usize {
        self.resting_limit_orders.get(symbol).map_or(0, |q| q.len())
    }

    /// Drop all resting orders — used by PipelineCommand::Reset and
    /// CloseAll paths so a session reset does not leak stale maker orders
    /// into the next session. 1B-4.2 will also call this when the engine
    /// transitions out of Paper mode.
    /// 丟棄所有掛單 — Reset / CloseAll 路徑使用，避免 session 切換時洩漏。
    pub fn clear_resting_limit_orders(&mut self) {
        self.resting_limit_orders.clear();
    }

    /// Remove a specific resting order by `order_link_id`. Returns the
    /// removed order when found. Used by 1B-4.2 sweep for timeout + fill
    /// removal, and by operator cancel IPC in future batches.
    /// 以 orderLinkId 移除特定掛單；找到時回傳該單。1B-4.2 sweep 與 operator
    /// cancel IPC 使用。
    pub fn remove_resting_limit_order_by_link_id(
        &mut self,
        order_link_id: &str,
    ) -> Option<RestingLimitOrder> {
        for q in self.resting_limit_orders.values_mut() {
            if let Some(idx) = q.iter().position(|o| o.order_link_id == order_link_id) {
                return q.remove(idx);
            }
        }
        None
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::paper_state::PaperState;

    fn make_order(link_id: &str, symbol: &str, submit_ts: u64, deadline_ms: u64) -> RestingLimitOrder {
        RestingLimitOrder {
            symbol: symbol.to_string(),
            is_long: true,
            qty: 0.1,
            limit_price: 50_000.0,
            time_in_force: TimeInForce::PostOnly,
            submit_ts_ms: submit_ts,
            deadline_ms,
            mid_price_at_submit: 50_001.0,
            order_link_id: link_id.to_string(),
            context_id: "ctx_test".to_string(),
            strategy: "grid_trading".to_string(),
        }
    }

    #[test]
    fn test_resting_queue_empty_by_default() {
        // Fresh PaperState must have an empty queue — 1B-4.1 is zero-behavior.
        // 全新 PaperState 的隊列必須為空 — 1B-4.1 零行為。
        let s = PaperState::new(10_000.0);
        assert_eq!(s.resting_limit_order_count(), 0);
        assert!(s.resting_limit_orders_for("BTCUSDT").is_empty());
    }

    #[test]
    fn test_enqueue_preserves_fifo_per_symbol() {
        let mut s = PaperState::new(10_000.0);
        s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
        s.enqueue_resting_limit_order(make_order("oc_2", "BTCUSDT", 2_000, 47_000));
        s.enqueue_resting_limit_order(make_order("oc_3", "ETHUSDT", 3_000, 48_000));
        assert_eq!(s.resting_limit_order_count(), 3);
        assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 2);
        assert_eq!(s.resting_limit_order_count_for("ETHUSDT"), 1);
        let btc = s.resting_limit_orders_for("BTCUSDT");
        assert_eq!(btc[0].order_link_id, "oc_1");
        assert_eq!(btc[1].order_link_id, "oc_2");
    }

    #[test]
    fn test_enqueue_unseen_symbol_returns_empty_slice() {
        let s = PaperState::new(10_000.0);
        // symbol never enqueued → empty slice, not panic.
        assert!(s.resting_limit_orders_for("DOGEUSDT").is_empty());
        assert_eq!(s.resting_limit_order_count_for("DOGEUSDT"), 0);
    }

    #[test]
    fn test_remove_by_link_id_returns_removed_and_decrements_count() {
        let mut s = PaperState::new(10_000.0);
        s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
        s.enqueue_resting_limit_order(make_order("oc_2", "BTCUSDT", 2_000, 47_000));
        let removed = s.remove_resting_limit_order_by_link_id("oc_1");
        assert!(removed.is_some());
        assert_eq!(removed.unwrap().order_link_id, "oc_1");
        assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 1);
        // Surviving order kept its FIFO position.
        assert_eq!(s.resting_limit_orders_for("BTCUSDT")[0].order_link_id, "oc_2");
    }

    #[test]
    fn test_remove_by_link_id_missing_returns_none() {
        let mut s = PaperState::new(10_000.0);
        s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
        assert!(s.remove_resting_limit_order_by_link_id("oc_missing").is_none());
        assert_eq!(s.resting_limit_order_count(), 1);
    }

    #[test]
    fn test_clear_drops_all_queues() {
        let mut s = PaperState::new(10_000.0);
        s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
        s.enqueue_resting_limit_order(make_order("oc_2", "ETHUSDT", 2_000, 47_000));
        assert_eq!(s.resting_limit_order_count(), 2);
        s.clear_resting_limit_orders();
        assert_eq!(s.resting_limit_order_count(), 0);
    }

    #[test]
    fn test_seed_resting_orders_replaces_queue() {
        let mut s = PaperState::new(10_000.0);
        s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
        // Seed a different payload; seed must fully replace prior state.
        let mut replacement: HashMap<String, VecDeque<RestingLimitOrder>> = HashMap::new();
        let mut q = VecDeque::new();
        q.push_back(make_order("oc_9", "SOLUSDT", 9_000, 54_000));
        replacement.insert("SOLUSDT".to_string(), q);
        s.seed_resting_limit_orders(replacement);
        assert_eq!(s.resting_limit_order_count(), 1);
        assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 0);
        assert_eq!(s.resting_limit_orders_for("SOLUSDT")[0].order_link_id, "oc_9");
    }

    #[test]
    fn test_resting_order_fields_serde_roundtrip() {
        // Serialisation stability: future snapshot wiring (1B-4.2 or beyond)
        // needs this shape to round-trip cleanly.
        // 序列化穩定性：未來快照接線需此形狀乾淨 round-trip。
        let o = make_order("oc_rt", "BTCUSDT", 1_000, 46_000);
        let json = serde_json::to_string(&o).expect("serialise");
        let back: RestingLimitOrder = serde_json::from_str(&json).expect("deserialise");
        assert_eq!(back.order_link_id, o.order_link_id);
        assert_eq!(back.symbol, o.symbol);
        assert_eq!(back.qty, o.qty);
        assert_eq!(back.limit_price, o.limit_price);
        assert_eq!(back.deadline_ms, o.deadline_ms);
        assert_eq!(back.mid_price_at_submit, o.mid_price_at_submit);
        assert_eq!(back.context_id, o.context_id);
        assert_eq!(back.strategy, o.strategy);
        assert_eq!(back.time_in_force, TimeInForce::PostOnly);
    }
}
