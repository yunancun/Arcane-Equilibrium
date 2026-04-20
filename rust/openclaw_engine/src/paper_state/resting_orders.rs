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

/// EDGE-P2-3 Phase 1B-4.2: pure classifier output for one resting order at
/// a given tick. Kept separate from `RestingFillEvent` so sweep tests can
/// assert classification independently of `apply_fill` side-effects.
/// EDGE-P2-3 Phase 1B-4.2：單掛單於某 tick 的純分類結果。與 `RestingFillEvent`
/// 分離，便於 sweep 測試在不觸發 apply_fill 副作用下驗證分類。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RestingSweepAction {
    /// Order stays in queue — not yet touched/crossed and not past deadline.
    /// 掛單保留 — 尚未被碰觸/穿越、且未超過截止時間。
    Keep,
    /// Price crossed the limit — fill the full queued qty (bias guard #1
    /// queue-position discount: 100% because true cross implies no queue
    /// competition at our price level on Bybit's book).
    /// 價格穿越限價 — 整筆成交（bias #1：真實穿越代表我方價位已清隊列）。
    FillFull,
    /// Price exactly touched the limit — 50% fill decided deterministically
    /// by order_link_id parity (bias guard #1). Paper is all-or-nothing:
    /// heads → FillFull; tails → Keep. The `filled_qty` schema field on
    /// future partial-fill extensions (bias guard #2) will carry the
    /// fraction, but 1B-4 simulates boolean fill only.
    /// 價格恰等於限價 — 50% 成交決定由 order_link_id 奇偶性（bias #1）。
    /// 紙盤全有/全無：heads → FillFull；tails → Keep。未來 partial-fill
    /// (bias #2) 由 schema filled_qty 承載，1B-4 僅模擬布林成交。
    FillPartial,
    /// Deadline reached — cancel + remove without fill (1B-3.2 sweep parity).
    /// Takes precedence over fill classification (conservative: expired
    /// order never fills, matches exchange-side 1B-3.2 cancel semantics).
    /// 截止時間到達 — 取消 + 移除、不成交（與 1B-3.2 sweep 對齊）。
    /// 優先於成交分類（保守：過期單不成交，對齊交易所側 cancel 語義）。
    Timeout,
}

/// EDGE-P2-3 Phase 1B-4.2: deterministic 50/50 coin flip keyed by
/// `order_link_id`. Used by `FillPartial` classification so backtests are
/// reproducible without pulling in a PRNG. Byte-sum parity is deterministic,
/// branch-free, and does not depend on `std::hash::DefaultHasher` stability
/// across toolchain versions.
/// EDGE-P2-3 Phase 1B-4.2：以 `order_link_id` 為鍵的確定性 50/50 投幣。
/// 讓 backtest 可重現且免引入 PRNG。採位元和奇偶性：確定性、無分支、不依賴
/// `std::hash::DefaultHasher` 跨工具鏈版本穩定性。
#[inline]
pub(crate) fn resting_partial_fill_heads(order_link_id: &str) -> bool {
    let sum: u32 = order_link_id.as_bytes().iter().map(|b| *b as u32).sum();
    sum & 1 == 0
}

/// EDGE-P2-3 Phase 1B-4.2: pure classifier. No mutation, no I/O, no `&mut`.
/// Returns the action the sweep should execute for this order at this tick.
///
/// Rules (checked in order):
/// 1. `now_ms >= deadline_ms` → `Timeout` (exchange-side 1B-3.2 parity).
/// 2. Bias-guard "same-tick resting": if `submit_ts_ms >= now_ms` the order
///    was just enqueued this tick — return `Keep` so resting semantics hold
///    (order must wait for a strictly future tick before being eligible).
/// 3. Buy: `tick_price < limit_price` → `FillFull`; `== limit_price` →
///    `FillPartial`; `>  limit_price` → `Keep`.
/// 4. Sell mirror: `tick_price > limit_price` → `FillFull`; `==` → `FillPartial`;
///    `<` → `Keep`.
///
/// EDGE-P2-3 Phase 1B-4.2：純函式分類器。不變動狀態、不讀寫 I/O、不需 &mut。
/// 規則（依序判定）：
/// 1. `now_ms >= deadline_ms` → `Timeout`（與 1B-3.2 交易所側對齊）。
/// 2. bias 保護「同 tick 不掛中」：`submit_ts_ms >= now_ms` → `Keep`（掛單
///    必須至少等到下一 tick 才可成交）。
/// 3. Buy：tick < limit → FillFull；== → FillPartial；> → Keep。
/// 4. Sell 鏡像：tick > limit → FillFull；== → FillPartial；< → Keep。
pub fn classify_resting_order(
    order: &RestingLimitOrder,
    tick_price: f64,
    now_ms: u64,
) -> RestingSweepAction {
    if now_ms >= order.deadline_ms {
        return RestingSweepAction::Timeout;
    }
    if order.submit_ts_ms >= now_ms {
        return RestingSweepAction::Keep;
    }
    if tick_price <= 0.0 || order.limit_price <= 0.0 {
        return RestingSweepAction::Keep;
    }
    if order.is_long {
        if tick_price < order.limit_price {
            RestingSweepAction::FillFull
        } else if tick_price == order.limit_price {
            RestingSweepAction::FillPartial
        } else {
            RestingSweepAction::Keep
        }
    } else if tick_price > order.limit_price {
        RestingSweepAction::FillFull
    } else if tick_price == order.limit_price {
        RestingSweepAction::FillPartial
    } else {
        RestingSweepAction::Keep
    }
}

/// EDGE-P2-3 Phase 1B-4.2: one sweep output row per drained order.
/// `Filled` carries everything on_tick needs to emit a trading `Fill` row,
/// call `strategy.on_fill`, and stamp `entry_context_id` on fresh opens.
/// `Timedout` is informational — caller logs + increments a counter.
/// EDGE-P2-3 Phase 1B-4.2：每筆 drain 的 sweep 輸出列。
/// `Filled` 承載 on_tick 發 Fill、呼叫 on_fill、開倉時打 entry_context_id 所需。
/// `Timedout` 僅供記錄與計數。
#[derive(Debug, Clone)]
pub enum RestingFillEvent {
    /// Order filled — either true cross (100%) or touch-with-heads (50%).
    /// 訂單成交 — 真實穿越（100%）或碰觸且 heads（50%）。
    Filled {
        order: RestingLimitOrder,
        fill_qty: f64,
        fill_price: f64,
        fee: f64,
        realized_pnl: f64,
        /// Mid at the fill tick for bias guard #4 adverse-selection tracking.
        /// Compare against `order.mid_price_at_submit` downstream.
        /// 成交時 mid，供 bias #4 adverse-selection 追蹤。
        mid_price_at_fill: f64,
        /// Was this a true cross (`FillFull`) or coin-flip touch (`FillPartial`)?
        /// Kept in the event so DB emit can tag the fill row for KPI analysis.
        /// 本次是真實穿越還是 50% 投幣碰觸？保留於事件供 DB 標記用於 KPI。
        true_cross: bool,
    },
    /// Deadline expired without fill — drained from queue (no apply_fill).
    /// 截止時間到、未成交 — 從隊列移除（不呼叫 apply_fill）。
    Timedout { order: RestingLimitOrder },
}

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
    /// 1B-5: bumps `maker_stats.submitted` on both aggregate and per-symbol.
    /// EDGE-P2-3 Phase 1B-4.1：將新掛單 FIFO append 到 per-symbol 隊列。
    /// 1B-5：同步累加 `maker_stats.submitted`（aggregate + per-symbol）。
    pub fn enqueue_resting_limit_order(&mut self, order: RestingLimitOrder) {
        self.maker_stats.record_submit(&order.symbol);
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

    /// EDGE-P2-3 Phase 1B-5: read-only view of maker-order counters (aggregate
    /// + per-symbol) for operator observability and ML feature extraction.
    /// EDGE-P2-3 Phase 1B-5：maker 掛單統計的唯讀視圖（aggregate + per-symbol）。
    pub fn maker_stats(&self) -> &super::MakerStats {
        &self.maker_stats
    }

    /// EDGE-P2-3 Phase 1B-5: resolve effective KPI status for `symbol` under
    /// `cfg`. Router consults this before enqueue — Degraded triggers market
    /// fallback. Cold (samples < min) is treated as pass at the call site.
    /// EDGE-P2-3 Phase 1B-5：依 `cfg` 回傳某 symbol 的有效 KPI 狀態。Router
    /// enqueue 前查此，Degraded → 改走市價；Cold = 允許 enqueue。
    pub fn maker_kpi_status(
        &self,
        symbol: &str,
        cfg: &super::MakerKpiConfig,
    ) -> super::MakerKpiStatus {
        self.maker_stats.status_for(symbol, cfg)
    }

    /// EDGE-P2-3 Phase 1B-5: counter bump used by router when the gate
    /// rejected an enqueue — paper-only. Separate from sweep-side counters
    /// so a reader can distinguish "market fallback triggered by gate" from
    /// genuine exchange-driven timeouts.
    /// EDGE-P2-3 Phase 1B-5：router 因 gate 拒絕 enqueue 時累加。與 sweep 端
    /// 計數分離，便於區分「gate 觸發市價 fallback」與「真實超時」。
    pub fn record_maker_degraded_fallback(&mut self, symbol: &str) {
        self.maker_stats.record_degraded_fallback(symbol);
    }

    /// Test-only helper: seed `maker_stats` with a specific number of filled
    /// and timed-out orders for `symbol`. Bypasses enqueue / sweep so KPI
    /// gate / router tests can land exactly on Cold / Healthy / Degraded.
    /// Fills are recorded with submit_mid = fill_mid = 100 and fee = 0 so
    /// `sum_net_edge_bps` stays at 0 unless the test inspects it explicitly.
    /// 測試用：直接塞 filled / timedout 計數到 maker_stats 指定 symbol 的 scope，
    /// 讓 KPI gate / router 測試能精準對準三態。submit=fill=100、fee=0，使
    /// `sum_net_edge_bps` 保持 0，除非測試自行另行累加。
    #[cfg(test)]
    pub fn test_seed_maker_stats_terminal(
        &mut self,
        symbol: &str,
        filled: u64,
        timedout: u64,
    ) {
        for _ in 0..filled {
            self.maker_stats
                .record_fill(symbol, true, 100.0, 100.0, 1.0, 100.0, 0.0, true);
        }
        for _ in 0..timedout {
            self.maker_stats.record_timeout(symbol);
        }
    }

    /// Drop all resting orders — used by PipelineCommand::Reset and
    /// CloseAll paths so a session reset does not leak stale maker orders
    /// into the next session. 1B-4.2 will also call this when the engine
    /// transitions out of Paper mode.
    ///
    /// EDGE-P2-3 Phase 1B-5 FUP-1: also reset `maker_stats` so
    /// `degraded_fallbacks` / `sum_net_edge_bps` / terminal counters do not
    /// survive into the next session. Without this, future Reset wiring would
    /// inherit a stale Degraded verdict across sessions, silently blocking
    /// PostOnly enqueues even though the resting queue itself is empty.
    /// EDGE-P2-3 Phase 1B-5 FUP-1：同時重置 `maker_stats`，避免 session 切換
    /// 時讓 Degraded 結論/統計跨 session 污染 — 否則新 session 儘管 queue 空，
    /// 仍會因陳舊 Degraded verdict 靜默 PostOnly 入隊。
    pub fn clear_resting_limit_orders(&mut self) {
        self.resting_limit_orders.clear();
        self.maker_stats = super::maker_stats::MakerStats::default();
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

    /// EDGE-P2-3 Phase 1B-4.2: walk the resting queue for `symbol` against the
    /// current tick, classify each order via `classify_resting_order`, execute
    /// the resulting side-effect (apply_fill on fill / remove on timeout), and
    /// return one `RestingFillEvent` per drained order. `Keep` orders stay
    /// in the queue untouched.
    ///
    /// Caller (`on_tick`) is responsible for:
    ///   * emitting a `TradingMsg::Fill` row for each `Filled` event
    ///   * calling `strategy.on_fill` if the strategy is still resident
    ///   * stamping `entry_context_id` on fresh opens (mirror of the
    ///     optimistic-fill path at line ~1124 in on_tick)
    ///
    /// `maker_fee_rate` is passed in by caller (source: AccountManager →
    /// legacy → constant) to keep `PaperState` free of fee-resolution logic.
    /// Fee per fill = `qty * fill_price * maker_fee_rate` matching the
    /// exchange-side maker rebate semantics (Bybit charges maker fee on the
    /// notional once the limit is hit).
    ///
    /// EDGE-P2-3 Phase 1B-4.2：巡覽 `symbol` 的掛單隊列，對每筆使用
    /// `classify_resting_order` 分類並執行對應副作用（成交→apply_fill；
    /// 過期→移除），每筆 drain 輸出一個 `RestingFillEvent`。`Keep` 留在隊列。
    /// caller（on_tick）負責：發 Fill 列、呼叫 strategy.on_fill、開倉時打
    /// entry_context_id。`maker_fee_rate` 由 caller 傳入，PaperState 不做費率解析。
    pub fn sweep_resting_limit_orders_for_symbol(
        &mut self,
        symbol: &str,
        tick_price: f64,
        now_ms: u64,
        maker_fee_rate: f64,
    ) -> Vec<RestingFillEvent> {
        // Fast path: no queue for this symbol → nothing to do.
        // 快速路徑：本 symbol 無掛單 → 直接返回。
        if self.resting_limit_orders.get(symbol).map_or(true, |q| q.is_empty()) {
            return Vec::new();
        }

        // Pass 1: classify without mutating state. We need to buffer decisions
        // because `apply_fill` takes `&mut self` and we can't hold `q` mutable
        // while calling self methods. Cloning per-order is cheap (< 10 fields).
        // Pass 1：先分類再執行。因 apply_fill 需 &mut self，不能邊持有 q
        // 邊呼叫；per-order clone 廉價（欄位 < 10）。
        enum Decision {
            Keep,
            Fill { order: RestingLimitOrder, true_cross: bool },
            Timeout { order: RestingLimitOrder },
        }
        let decisions: Vec<Decision> = {
            let q = self
                .resting_limit_orders
                .get(symbol)
                .expect("queue existence checked by fast-path");
            q.iter()
                .map(|o| match classify_resting_order(o, tick_price, now_ms) {
                    RestingSweepAction::Keep => Decision::Keep,
                    RestingSweepAction::Timeout => Decision::Timeout { order: o.clone() },
                    RestingSweepAction::FillFull => Decision::Fill {
                        order: o.clone(),
                        true_cross: true,
                    },
                    RestingSweepAction::FillPartial => {
                        if resting_partial_fill_heads(&o.order_link_id) {
                            Decision::Fill {
                                order: o.clone(),
                                true_cross: false,
                            }
                        } else {
                            Decision::Keep
                        }
                    }
                })
                .collect()
        };

        // Pass 2: apply decisions and collect events. Retain Keep orders in
        // the queue; drop the rest. We rebuild the queue once to keep FIFO
        // order and avoid O(n²) `retain_mut` copies.
        // Pass 2：執行決策並蒐集事件；保留 Keep、丟棄其餘，重建隊列一次
        // 以保 FIFO 且避免 O(n²) 複製。
        let mut events: Vec<RestingFillEvent> = Vec::new();
        let mut new_queue: VecDeque<RestingLimitOrder> = VecDeque::new();
        let old_queue = self
            .resting_limit_orders
            .remove(symbol)
            .expect("queue existence checked by fast-path");
        for (order, decision) in old_queue.into_iter().zip(decisions.into_iter()) {
            match decision {
                Decision::Keep => new_queue.push_back(order),
                Decision::Timeout { order: drained } => {
                    // 1B-5: bump maker_stats before emitting event so readers
                    // see a consistent snapshot once the event is observed.
                    // 1B-5：先更 maker_stats 再發事件，確保觀察者看見一致快照。
                    self.maker_stats.record_timeout(&drained.symbol);
                    events.push(RestingFillEvent::Timedout { order: drained });
                }
                Decision::Fill {
                    order: drained,
                    true_cross,
                } => {
                    // Fill price = limit price (maker execution honours the
                    // resting price, not the tick). True cross pays maker fee
                    // on `qty * limit_price` notional.
                    // 成交價 = 限價（maker 執行以掛單價成交，而非 tick 價）。
                    let fill_price = drained.limit_price;
                    let fill_qty = drained.qty;
                    let fee = fill_qty * fill_price * maker_fee_rate;
                    let realized_pnl = self.apply_fill(
                        &drained.symbol,
                        drained.is_long,
                        fill_qty,
                        fill_price,
                        fee,
                        now_ms,
                        &drained.strategy,
                    );
                    // 1B-5: accumulate submit→fill edge before emitting event.
                    // mid_price_at_fill = tick_price (same signal as the event).
                    // 1B-5：emit 前累計 submit→fill net edge。
                    self.maker_stats.record_fill(
                        &drained.symbol,
                        drained.is_long,
                        drained.mid_price_at_submit,
                        tick_price,
                        fill_qty,
                        fill_price,
                        fee,
                        true_cross,
                    );
                    events.push(RestingFillEvent::Filled {
                        order: drained,
                        fill_qty,
                        fill_price,
                        fee,
                        realized_pnl,
                        mid_price_at_fill: tick_price,
                        true_cross,
                    });
                }
            }
        }
        if !new_queue.is_empty() {
            self.resting_limit_orders
                .insert(symbol.to_string(), new_queue);
        }
        events
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

    /// FUP-1: `clear_resting_limit_orders` must also reset maker_stats so a
    /// Degraded verdict or counter residue does not leak across sessions.
    /// FUP-1：clear 必須一併重置 maker_stats，避免 Degraded 結論跨 session 污染。
    #[test]
    fn test_clear_also_resets_maker_stats() {
        let mut s = PaperState::new(10_000.0);
        s.enqueue_resting_limit_order(make_order("oc_1", "BTCUSDT", 1_000, 46_000));
        // Seed terminal stats so Degraded could sticky if not cleared.
        s.test_seed_maker_stats_terminal("BTCUSDT", 0, 25);
        s.record_maker_degraded_fallback("BTCUSDT");
        let before = s.maker_stats();
        assert!(before.aggregate.timedout > 0);
        assert!(before.aggregate.degraded_fallbacks > 0);

        s.clear_resting_limit_orders();

        let after = s.maker_stats();
        assert_eq!(after.aggregate.submitted, 0);
        assert_eq!(after.aggregate.filled_full, 0);
        assert_eq!(after.aggregate.filled_partial, 0);
        assert_eq!(after.aggregate.timedout, 0);
        assert_eq!(after.aggregate.degraded_fallbacks, 0);
        assert_eq!(after.aggregate.sum_net_edge_bps, 0.0);
        assert!(after.per_symbol.is_empty());
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

    // ── 1B-4.2: classifier + sweep tests ──
    // 1B-4.2：分類器 + sweep 測試

    fn order_at(
        link_id: &str,
        symbol: &str,
        is_long: bool,
        limit_price: f64,
        submit_ts: u64,
        deadline_ms: u64,
    ) -> RestingLimitOrder {
        RestingLimitOrder {
            symbol: symbol.to_string(),
            is_long,
            qty: 0.1,
            limit_price,
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
    fn test_classify_timeout_takes_precedence_over_fill() {
        // Deadline expired AND price would cross → still Timeout (conservative).
        // 截止到期且價格會穿越 → 仍 Timeout（保守，對齊 1B-3.2）。
        let o = order_at("oc_t", "BTCUSDT", true, 50_000.0, 1_000, 2_000);
        let a = classify_resting_order(&o, 49_500.0, 2_500);
        assert_eq!(a, RestingSweepAction::Timeout);
    }

    #[test]
    fn test_classify_same_tick_enqueue_stays_kept() {
        // submit_ts_ms == now_ms → Keep (bias guard: resting must wait ≥1 tick).
        // 同 tick 不成交（bias 保護）。
        let o = order_at("oc_same", "BTCUSDT", true, 50_000.0, 1_000, 60_000);
        let a = classify_resting_order(&o, 49_000.0, 1_000);
        assert_eq!(a, RestingSweepAction::Keep);
    }

    #[test]
    fn test_classify_buy_tick_below_limit_fills_full() {
        let o = order_at("oc_b_cross", "BTCUSDT", true, 50_000.0, 1_000, 60_000);
        let a = classify_resting_order(&o, 49_999.0, 1_500);
        assert_eq!(a, RestingSweepAction::FillFull);
    }

    #[test]
    fn test_classify_buy_tick_equal_limit_fill_partial() {
        let o = order_at("oc_b_touch", "BTCUSDT", true, 50_000.0, 1_000, 60_000);
        let a = classify_resting_order(&o, 50_000.0, 1_500);
        assert_eq!(a, RestingSweepAction::FillPartial);
    }

    #[test]
    fn test_classify_buy_tick_above_limit_keeps() {
        let o = order_at("oc_b_keep", "BTCUSDT", true, 50_000.0, 1_000, 60_000);
        let a = classify_resting_order(&o, 50_001.0, 1_500);
        assert_eq!(a, RestingSweepAction::Keep);
    }

    #[test]
    fn test_classify_sell_tick_above_limit_fills_full() {
        let o = order_at("oc_s_cross", "BTCUSDT", false, 50_000.0, 1_000, 60_000);
        let a = classify_resting_order(&o, 50_001.0, 1_500);
        assert_eq!(a, RestingSweepAction::FillFull);
    }

    #[test]
    fn test_classify_sell_tick_equal_limit_fill_partial() {
        let o = order_at("oc_s_touch", "BTCUSDT", false, 50_000.0, 1_000, 60_000);
        let a = classify_resting_order(&o, 50_000.0, 1_500);
        assert_eq!(a, RestingSweepAction::FillPartial);
    }

    #[test]
    fn test_classify_sell_tick_below_limit_keeps() {
        let o = order_at("oc_s_keep", "BTCUSDT", false, 50_000.0, 1_000, 60_000);
        let a = classify_resting_order(&o, 49_999.0, 1_500);
        assert_eq!(a, RestingSweepAction::Keep);
    }

    #[test]
    fn test_classify_nonpositive_prices_stay_kept() {
        // tick_price <= 0 → Keep (defensive; sweep caller may pass 0 at boot)
        // 負/零 tick_price 保守 → Keep（防禦性）。
        let o = order_at("oc_bad", "BTCUSDT", true, 50_000.0, 1_000, 60_000);
        assert_eq!(
            classify_resting_order(&o, 0.0, 1_500),
            RestingSweepAction::Keep
        );
        assert_eq!(
            classify_resting_order(&o, -1.0, 1_500),
            RestingSweepAction::Keep
        );
    }

    #[test]
    fn test_partial_fill_heads_deterministic() {
        // Same id → same outcome every call (reproducibility).
        // 相同 id → 每次調用一致（可重現性）。
        let id = "pop_paper_BTCUSDT_42";
        let a = resting_partial_fill_heads(id);
        let b = resting_partial_fill_heads(id);
        assert_eq!(a, b);
    }

    #[test]
    fn test_sweep_empty_queue_returns_empty_events() {
        let mut s = PaperState::new(10_000.0);
        let events = s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 50_000.0, 2_000, 0.0002);
        assert!(events.is_empty());
    }

    #[test]
    fn test_sweep_timeout_drains_without_fill() {
        let mut s = PaperState::new(10_000.0);
        s.set_latest_price("BTCUSDT", 50_000.0);
        s.enqueue_resting_limit_order(order_at(
            "oc_to", "BTCUSDT", true, 49_000.0, 1_000, 2_000,
        ));
        let events =
            s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 48_000.0, 5_000, 0.0002);
        assert_eq!(events.len(), 1);
        match &events[0] {
            RestingFillEvent::Timedout { order } => {
                assert_eq!(order.order_link_id, "oc_to");
            }
            _ => panic!("expected Timedout"),
        }
        // No position opened — timeout does not apply_fill.
        assert!(s.get_position("BTCUSDT").is_none());
        assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 0);
    }

    #[test]
    fn test_sweep_buy_cross_opens_position_at_limit_price() {
        let mut s = PaperState::new(10_000.0);
        s.set_latest_price("BTCUSDT", 50_000.0);
        s.enqueue_resting_limit_order(order_at(
            "oc_b", "BTCUSDT", true, 49_000.0, 1_000, 60_000,
        ));
        // Tick drops below limit — buy limit fills at the limit price, not tick.
        // Tick 跌破限價 — buy 限價以限價成交，非 tick 價。
        let events =
            s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 48_900.0, 2_000, 0.0002);
        assert_eq!(events.len(), 1);
        match &events[0] {
            RestingFillEvent::Filled {
                order,
                fill_price,
                fill_qty,
                mid_price_at_fill,
                true_cross,
                fee,
                ..
            } => {
                assert_eq!(order.order_link_id, "oc_b");
                assert_eq!(*fill_price, 49_000.0, "maker fills at limit, not tick");
                assert_eq!(*fill_qty, 0.1);
                assert_eq!(*mid_price_at_fill, 48_900.0);
                assert!(*true_cross, "cross should be true_cross=true");
                // fee = 0.1 * 49_000 * 0.0002 = 0.98
                assert!((fee - 0.98).abs() < 1e-9);
            }
            _ => panic!("expected Filled"),
        }
        let pos = s.get_position("BTCUSDT").expect("position opened");
        assert!(pos.is_long);
        assert_eq!(pos.qty, 0.1);
        assert_eq!(pos.entry_price, 49_000.0);
        // Queue drained.
        assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 0);
    }

    #[test]
    fn test_sweep_sell_cross_opens_short_at_limit_price() {
        let mut s = PaperState::new(10_000.0);
        s.set_latest_price("ETHUSDT", 3_000.0);
        s.enqueue_resting_limit_order(order_at(
            "oc_s", "ETHUSDT", false, 3_100.0, 1_000, 60_000,
        ));
        // Tick rises above limit — sell limit fills at limit price.
        // Tick 升至限價之上 — sell 限價以限價成交。
        let events =
            s.sweep_resting_limit_orders_for_symbol("ETHUSDT", 3_105.0, 2_000, 0.0002);
        assert_eq!(events.len(), 1);
        match &events[0] {
            RestingFillEvent::Filled { fill_price, true_cross, .. } => {
                assert_eq!(*fill_price, 3_100.0);
                assert!(*true_cross);
            }
            _ => panic!("expected Filled"),
        }
        let pos = s.get_position("ETHUSDT").expect("short opened");
        assert!(!pos.is_long);
        assert_eq!(pos.entry_price, 3_100.0);
    }

    #[test]
    fn test_sweep_above_limit_buy_keeps_order() {
        let mut s = PaperState::new(10_000.0);
        s.enqueue_resting_limit_order(order_at(
            "oc_keep", "BTCUSDT", true, 49_000.0, 1_000, 60_000,
        ));
        let events =
            s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 50_000.0, 2_000, 0.0002);
        assert!(events.is_empty());
        assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 1);
        assert!(s.get_position("BTCUSDT").is_none());
    }

    #[test]
    fn test_sweep_same_tick_enqueue_does_not_fill() {
        let mut s = PaperState::new(10_000.0);
        // submit_ts = now_ms — classifier returns Keep even though price crosses.
        // submit_ts 與 now_ms 相等 — 分類器回 Keep 即使價格穿越。
        s.enqueue_resting_limit_order(order_at(
            "oc_st", "BTCUSDT", true, 49_000.0, 2_000, 60_000,
        ));
        let events =
            s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 48_500.0, 2_000, 0.0002);
        assert!(events.is_empty());
        assert_eq!(s.resting_limit_order_count_for("BTCUSDT"), 1);
    }

    #[test]
    fn test_sweep_preserves_fifo_for_kept_orders() {
        let mut s = PaperState::new(10_000.0);
        // Three orders — middle one will fill, other two keep.
        // 三筆掛單 — 中間成交、另兩筆保留。
        s.enqueue_resting_limit_order(order_at(
            "oc_1", "BTCUSDT", true, 48_000.0, 1_000, 60_000,
        ));
        s.enqueue_resting_limit_order(order_at(
            "oc_2", "BTCUSDT", true, 49_500.0, 1_000, 60_000,
        ));
        s.enqueue_resting_limit_order(order_at(
            "oc_3", "BTCUSDT", true, 47_000.0, 1_000, 60_000,
        ));
        // Tick = 49_000 — only oc_2 (limit 49_500) fills; oc_1/oc_3 keep.
        let events =
            s.sweep_resting_limit_orders_for_symbol("BTCUSDT", 49_000.0, 2_000, 0.0002);
        assert_eq!(events.len(), 1);
        match &events[0] {
            RestingFillEvent::Filled { order, .. } => {
                assert_eq!(order.order_link_id, "oc_2");
            }
            _ => panic!("expected Filled"),
        }
        let remaining = s.resting_limit_orders_for("BTCUSDT");
        assert_eq!(remaining.len(), 2);
        assert_eq!(remaining[0].order_link_id, "oc_1", "FIFO head preserved");
        assert_eq!(remaining[1].order_link_id, "oc_3", "FIFO tail preserved");
    }

    #[test]
    fn test_sweep_partial_fill_deterministic_by_link_id() {
        // Two touch orders with different ids — one heads, one tails. Exactly
        // one should fill; the other stays in queue. Guarantees deterministic
        // replay even though classifier returned FillPartial for both.
        // 兩筆碰觸掛單不同 id — 一 heads 一 tails，確定性一致。
        let mut s = PaperState::new(10_000.0);
        // "oc_even" (4 bytes summing to 111+99+95+101+118+101+110 = ...) — compute
        // which id goes heads by calling the helper and picking ids accordingly.
        let id_a = "oc_heads_a";
        let id_b = "oc_heads_b";
        let a_heads = resting_partial_fill_heads(id_a);
        let b_heads = resting_partial_fill_heads(id_b);
        s.enqueue_resting_limit_order(order_at(
            id_a, "SOLUSDT", true, 100.0, 1_000, 60_000,
        ));
        s.enqueue_resting_limit_order(order_at(
            id_b, "SOLUSDT", true, 100.0, 1_000, 60_000,
        ));
        let events =
            s.sweep_resting_limit_orders_for_symbol("SOLUSDT", 100.0, 2_000, 0.0002);
        // count expected fills by precomputed coin flips.
        let expected_fills = (a_heads as usize) + (b_heads as usize);
        let actual_fills = events
            .iter()
            .filter(|e| matches!(e, RestingFillEvent::Filled { .. }))
            .count();
        assert_eq!(actual_fills, expected_fills);
        // For every Filled event, `true_cross` must be false because tick == limit.
        for e in &events {
            if let RestingFillEvent::Filled { true_cross, .. } = e {
                assert!(!*true_cross, "touch fills are not true cross");
            }
        }
        // Queue + positions accounting must match.
        let remaining = s.resting_limit_order_count_for("SOLUSDT");
        assert_eq!(remaining, 2 - expected_fills);
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
