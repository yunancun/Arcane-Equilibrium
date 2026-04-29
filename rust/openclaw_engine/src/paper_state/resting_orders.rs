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

/// EDGE-P2-3 Phase 1B-4.3: pure predicate — does the order's submit-time
/// funding rate exceed `|threshold|` in the direction that is adverse to the
/// maker side? Positive funding is paid by longs to shorts, so:
///   * Long maker, `funding > +threshold` → adverse (fill tilts against you)
///   * Short maker, `funding < -threshold` → adverse (fill tilts against you)
/// Threshold `0.0` (or non-finite input) disables the guard → always `false`.
/// The boundary `|funding| == threshold` is NOT adverse (strict `>`), so an
/// operator setting `threshold = 0.0003` can explicitly gate at 3 bps and
/// expect the 3 bps case itself to fill.
/// EDGE-P2-3 Phase 1B-4.3：純謂詞——提交時的 funding rate 是否以「逆向 maker
/// 側」方向超過 `|threshold|`。正 funding 由多方支付給空方，所以：
///   * 多 maker，`funding > +threshold` → 逆向（成交向你不利傾斜）
///   * 空 maker，`funding < -threshold` → 逆向
/// threshold `0.0`（或非有限輸入）關閉 guard → 恆回 false。邊界
/// `|funding| == threshold` 不算逆向（嚴格 `>`），operator 設 `threshold = 0.0003`
/// 可明確於 3 bps gate，並期待 3 bps 本身能成交。
#[inline]
pub fn funding_drag_adverse(funding_rate: f64, is_long: bool, threshold: f64) -> bool {
    if !funding_rate.is_finite() || !threshold.is_finite() || threshold <= 0.0 {
        return false;
    }
    if is_long {
        funding_rate > threshold
    } else {
        funding_rate < -threshold
    }
}

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

/// EDGE-P2-3 Phase 1B-4.2/4.3: pure classifier. No mutation, no I/O, no `&mut`.
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
/// 5. EDGE-P2-3 Phase 1B-4.3 Bias-guard #3 funding drag: if the chosen action
///    is `FillPartial` (touch-equal coin flip) AND `funding_drag_adverse(
///    order.funding_rate_at_submit, order.is_long, funding_drag_threshold)`
///    holds, downgrade to `Keep`. Real-market maker fills on touch in the
///    face of adverse funding are heavily adverse-selected — the sweep
///    should not paper-simulate a 50/50 coin flip in that regime. True cross
///    (`FillFull`) is NOT downgraded (the limit was actually crossed — not
///    a statistical artefact) and `Timeout` retains precedence (step 1).
///
/// EDGE-P2-3 Phase 1B-4.2/4.3：純函式分類器。不變動狀態、不讀寫 I/O、不需 &mut。
/// 規則（依序判定）：
/// 1. `now_ms >= deadline_ms` → `Timeout`（與 1B-3.2 交易所側對齊）。
/// 2. bias 保護「同 tick 不掛中」：`submit_ts_ms >= now_ms` → `Keep`（掛單
///    必須至少等到下一 tick 才可成交）。
/// 3. Buy：tick < limit → FillFull；== → FillPartial；> → Keep。
/// 4. Sell 鏡像：tick > limit → FillFull；== → FillPartial；< → Keep。
/// 5. 1B-4.3 funding drag guard：若結果為 `FillPartial` 且提交時 funding
///    對 maker 側嚴重逆向（超過 `funding_drag_threshold`），降級為 `Keep`。
///    真實穿越 FillFull 不受影響；Timeout 保留步驟 1 優先序。
pub fn classify_resting_order(
    order: &RestingLimitOrder,
    tick_price: f64,
    now_ms: u64,
    funding_drag_threshold: f64,
) -> RestingSweepAction {
    let base = classify_resting_order_raw(order, tick_price, now_ms);
    // 1B-4.3 bias guard #3: only FillPartial is shaped by funding drag.
    // True cross + Keep + Timeout pass through verbatim.
    // 1B-4.3 bias #3：僅 FillPartial 受 funding drag 影響；其他分支原樣返回。
    if matches!(base, RestingSweepAction::FillPartial)
        && funding_drag_adverse(
            order.funding_rate_at_submit,
            order.is_long,
            funding_drag_threshold,
        )
    {
        return RestingSweepAction::Keep;
    }
    base
}

/// EDGE-P2-3 Phase 1B-4.3: classifier stages 1-4 only (no funding-drag guard).
/// Kept `pub(crate)` so the sweep can inspect the pre-guard verdict, detect a
/// `FillPartial → Keep` downgrade, and attribute it to the funding-drag
/// counter. External callers should continue using `classify_resting_order`
/// (which layers rule 5 on top) — only sweep-side accounting needs the raw form.
/// EDGE-P2-3 Phase 1B-4.3：分類器規則 1-4（不含 funding drag guard）。`pub(crate)`
/// 讓 sweep 可讀取未套 guard 的原始結論以判斷 FillPartial→Keep 降級並歸屬
/// funding_drag 計數器。外部呼叫者沿用 `classify_resting_order`，只有 sweep
/// 側統計邏輯需要此 raw 版本。
pub(crate) fn classify_resting_order_raw(
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
    /// EDGE-P2-3 Phase 1B-4.3: decimal funding rate captured at enqueue time,
    /// stamped by the router via `paper_state.latest_funding_rate(symbol)`.
    /// Feeds bias guard #3: if |rate| exceeds the operator's
    /// `funding_drag_threshold` in the direction that is adverse to this
    /// maker's side, the sweep downgrades touch-equal `FillPartial` fills to
    /// `Keep`. `0.0` means "unknown / no ticker seen yet" — treated as neutral
    /// (guard stays off for this order). Stored at submit time so later funding
    /// regime changes do not retroactively reshape the decision.
    /// 1B-4.3：enqueue 時錄入的 decimal funding rate，router 透過
    /// `paper_state.latest_funding_rate(symbol)` 打標。餵 bias 保護 #3：|rate|
    /// 超過 operator 設定的 `funding_drag_threshold` 且方向逆向 maker 時，sweep
    /// 將碰觸 FillPartial 降級為 Keep。`0.0` = 未知 / 尚未見 ticker，本單停用
    /// guard。於提交時鎖定，不受後續 funding regime 變動回溯影響。
    ///
    /// EDGE-P2-3 Phase 1B-5 FUP-4: `#[serde(default)]` falls back to `0.0` when
    /// an older persisted queue (written before 1B-4.3 landed) is loaded —
    /// equivalent to "unknown rate, guard stays off", which is the correct
    /// backcompat semantic. Without this, deserialising pre-1B-4.3 data
    /// would fail with "missing field".
    /// 1B-5 FUP-4：`#[serde(default)]` 讓 1B-4.3 之前持久化的隊列反序列化時
    /// 此欄位回退 `0.0`（= rate 未知、guard 關閉），語意與缺欄位前一致。
    #[serde(default)]
    pub funding_rate_at_submit: f64,
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
        now_ms: u64,
    ) -> super::MakerKpiStatus {
        self.maker_stats.status_for(symbol, cfg, now_ms)
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
        now_ms: u64,
    ) {
        // 1B-5 FUP-2: seed with the caller's `now_ms` so the staleness window
        // does not silently decay the Degraded verdict in router integration
        // tests that advance time (NOW_MS ≈ 1.7 trillion) beyond the default
        // 30-minute window. Callers that want stale seed data pass an old
        // `now_ms` explicitly.
        // 1B-5 FUP-2：以 caller 的 `now_ms` seed，避免 staleness 默默把整合
        // 測試裡的 Degraded 衰減成 Cold；想測陳舊場景的 caller 自行傳舊 ts。
        for _ in 0..filled {
            self.maker_stats
                .record_fill(symbol, true, 100.0, 100.0, 1.0, 100.0, 0.0, true, now_ms);
        }
        for _ in 0..timedout {
            self.maker_stats.record_timeout(symbol, now_ms);
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
        funding_drag_threshold: f64,
    ) -> Vec<RestingFillEvent> {
        // Fast path: no queue for this symbol → nothing to do.
        // 快速路徑：本 symbol 無掛單 → 直接返回。
        if self
            .resting_limit_orders
            .get(symbol)
            .map_or(true, |q| q.is_empty())
        {
            return Vec::new();
        }

        // Pass 1: classify without mutating state. We need to buffer decisions
        // because `apply_fill` takes `&mut self` and we can't hold `q` mutable
        // while calling self methods. Cloning per-order is cheap (< 10 fields).
        // 1B-4.3: we run the *raw* classifier (rules 1-4) here so that when
        // funding drag downgrades FillPartial to Keep we can attribute the
        // skip to `maker_stats.funding_drag_skips` instead of silently
        // conflating with ordinary "tick didn't cross" Keeps.
        // Pass 1：先分類再執行。因 apply_fill 需 &mut self，不能邊持有 q
        // 邊呼叫；per-order clone 廉價（欄位 < 10）。
        // 1B-4.3：本處使用 *raw* 分類器（規則 1-4），以便在 funding drag guard
        // 把 FillPartial 降級為 Keep 時能精準計入 `maker_stats.funding_drag_skips`，
        // 不與「tick 未穿越」類的 Keep 混為一談。
        enum Decision {
            Keep,
            /// 1B-4.3: FillPartial touch that got vetoed by funding drag guard.
            /// Same end-state as Keep (order stays in queue) but counted
            /// separately so operators can see when the guard fires.
            /// 1B-4.3：本輪 funding drag 否決的 FillPartial 碰觸。最終狀態同
            /// Keep（訂單留在隊列）但另行計數供觀察 guard 觸發頻率。
            FundingDragSkip,
            Fill {
                order: RestingLimitOrder,
                true_cross: bool,
            },
            Timeout {
                order: RestingLimitOrder,
            },
        }
        let decisions: Vec<Decision> = {
            let q = self
                .resting_limit_orders
                .get(symbol)
                .expect("queue existence checked by fast-path");
            q.iter()
                .map(
                    |o| match classify_resting_order_raw(o, tick_price, now_ms) {
                        RestingSweepAction::Keep => Decision::Keep,
                        RestingSweepAction::Timeout => Decision::Timeout { order: o.clone() },
                        RestingSweepAction::FillFull => Decision::Fill {
                            order: o.clone(),
                            true_cross: true,
                        },
                        RestingSweepAction::FillPartial => {
                            // 1B-4.3 bias guard #3: adverse funding → defer (Skip).
                            // 1B-4.3：逆向 funding → 延後成交（Skip）。
                            if funding_drag_adverse(
                                o.funding_rate_at_submit,
                                o.is_long,
                                funding_drag_threshold,
                            ) {
                                Decision::FundingDragSkip
                            } else if resting_partial_fill_heads(&o.order_link_id) {
                                Decision::Fill {
                                    order: o.clone(),
                                    true_cross: false,
                                }
                            } else {
                                Decision::Keep
                            }
                        }
                    },
                )
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
                Decision::FundingDragSkip => {
                    // 1B-4.3: bump observability counter then keep order in
                    // queue. A later tick where funding has moderated or the
                    // price truly crosses can still fill it; the deadline
                    // branch still evicts it if the full maker_timeout_ms
                    // elapses without a favourable fill window.
                    // 1B-4.3：累加觀察計數器後原序留在隊列；後續 funding 緩和
                    // 或價格真實穿越時仍可成交；超時到期仍照常被 Timeout 清出。
                    self.maker_stats.record_funding_drag_skip(&order.symbol);
                    new_queue.push_back(order);
                }
                Decision::Timeout { order: drained } => {
                    // 1B-5: bump maker_stats before emitting event so readers
                    // see a consistent snapshot once the event is observed.
                    // 1B-5：先更 maker_stats 再發事件，確保觀察者看見一致快照。
                    self.maker_stats.record_timeout(&drained.symbol, now_ms);
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
                        now_ms,
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
#[path = "resting_orders_tests.rs"]
mod tests;
