//! Paper Trading State — position tracking + PnL (R04-7).
//! 紙盤交易狀態 — 持倉追蹤 + 損益。
//!
//! MODULE_NOTE (EN): Manages simulated positions, fills, balance, and PnL for
//!   paper/demo/live modes. apply_fill() updates positions; mark_to_market()
//!   computes unrealized PnL each tick. Thread-safe: sole-owner in TickPipeline.
//!
//!   E5-P1-1 (2026-04-18) split the original 2380-line `paper_state.rs` into
//!   this module tree with zero behaviour change:
//!     * `containers`        — `PaperPosition` data struct
//!     * `accessor`          — pure getters, SEC-18 clamped setters, mirror
//!                             handle ops, entry_context_id, charge_fee,
//!                             migrate_legacy_entry_notional
//!     * `owner_attribution` — `SYNTHETIC_OWNER_LABELS`, `RetriageOutcome`,
//!                             `adopt_orphan`, `retriage_synthetic_owner`
//!                             (P1-8 FUP tick-level retriage)
//!     * `fill_engine`       — `apply_fill`, `close_position`, `reduce_position`,
//!                             `close_position_at_market`, `close_all_positions`,
//!                             `import_positions`, `upsert_position_from_exchange`,
//!                             `apply_restored_counters`, `restore_from_db`,
//!                             `update_best_prices`, `check_stops`
//!     * `snapshots`         — `PositionSnapshot`, `PaperStateSnapshot`,
//!                             `export_state`
//!     * `dust_gate`         — `TriageOutcome`, `triage_bybit_sync`
//!                             (P0-6 + DUST-EVICTION-GAP-1 / P1-8 orphan)
//!   All external callers keep using `crate::paper_state::{PaperState,
//!   PaperPosition, PaperStateSnapshot, PositionSnapshot, RetriageOutcome,
//!   TriageOutcome, SYNTHETIC_OWNER_LABELS}` — the re-exports below preserve
//!   every public symbol the pre-split module exposed. Bit-exact arithmetic
//!   preserved: no operation order was reordered and no intermediate
//!   accumulator type changed.
//!
//! MODULE_NOTE (中): 管理紙盤/Demo/Live 模式的模擬持倉、成交、餘額和損益。
//!   apply_fill() 更新持倉；mark_to_market() 每 tick 計算未實現損益。
//!   線程安全：TickPipeline 獨佔所有權。
//!
//!   2026-04-18 E5-P1-1 將原本 2380 行的 paper_state.rs 拆成此模組樹，零行為變更：
//!     * containers        — PaperPosition 資料結構
//!     * accessor          — 純 getter、SEC-18 夾值 setter、mirror handle 操作、
//!                           entry_context_id、charge_fee、migrate_legacy_entry_notional
//!     * owner_attribution — SYNTHETIC_OWNER_LABELS、RetriageOutcome、adopt_orphan、
//!                           retriage_synthetic_owner（P1-8 FUP tick-level 重分流）
//!     * fill_engine       — apply_fill、close_position、reduce_position、
//!                           close_position_at_market、close_all_positions、
//!                           import_positions、upsert_position_from_exchange、
//!                           apply_restored_counters、restore_from_db、
//!                           update_best_prices、check_stops
//!     * snapshots         — PositionSnapshot、PaperStateSnapshot、export_state
//!     * dust_gate         — TriageOutcome、triage_bybit_sync（P0-6 +
//!                           DUST-EVICTION-GAP-1 / P1-8 orphan）
//!   所有外部呼叫者沿用 `crate::paper_state::{PaperState, PaperPosition,
//!   PaperStateSnapshot, PositionSnapshot, RetriageOutcome, TriageOutcome,
//!   SYNTHETIC_OWNER_LABELS}`；下方 re-export 保留拆分前每一個 pub 符號。
//!   bit-exact 算術保留：無任何運算順序重排、無中繼累加器型別變動。

pub mod accessor;
pub mod checkpoint;
pub mod containers;
pub mod dust_gate;
pub mod fill_engine;
pub mod maker_stats;
pub mod owner_attribution;
pub mod resting_orders;
pub mod snapshots;

pub use containers::{PaperPosition, PositionExitSnapshot};
pub use dust_gate::TriageOutcome;
pub use maker_stats::{
    compute_net_edge_bps, MakerKpiConfig, MakerKpiStatus, MakerStats, MakerStatsCounters,
};
pub use owner_attribution::{RetriageOutcome, SYNTHETIC_OWNER_LABELS};
pub use resting_orders::{RestingFillEvent, RestingLimitOrder, RestingSweepAction};
pub use snapshots::{PaperStateSnapshot, PositionSnapshot};

use openclaw_core::stop_manager::StopConfig;
use std::collections::{HashMap, VecDeque};
use std::sync::Arc;

/// Paper trading state manager.
/// 紙盤交易狀態管理器。
pub struct PaperState {
    pub(super) _initial_balance: f64,
    pub(super) balance: f64,
    pub(super) peak_balance: f64,
    /// P1-5 A2: wall-clock ms when the current equity curve began. Preserved
    /// across restarts via `trading.paper_state_checkpoint`; only reset by
    /// operator IPC `reset_drawdown_baseline`. Initialised to now_ms() in
    /// `new()`, overwritten by `restore_checkpoint()` on cross-restart restore.
    /// P1-5 A2：當前 equity curve 起始時刻（ms）。透過
    /// `trading.paper_state_checkpoint` 跨重啟保留；僅 operator 手動
    /// reset_drawdown_baseline 會更新。
    pub(super) session_start_ts_ms: u64,
    pub(super) positions: HashMap<String, PaperPosition>,
    pub(super) latest_prices: HashMap<String, f64>,
    /// Per-symbol 24h turnover for dynamic slippage calculation.
    /// 每交易對 24h 成交額，用於動態滑點計算。
    pub(super) latest_turnovers: HashMap<String, f64>,
    pub(super) total_realized_pnl: f64,
    pub(super) total_fees: f64,
    pub(super) trade_count: u32,
    pub(super) stop_config: StopConfig,
    pub(super) forced_drawdown: f64,
    /// Bybit Demo account real balance (Mode B: bybit_sync). None = custom mode.
    /// Bybit Demo 帳戶真實餘額（模式 B：bybit_sync）。None = 自設金額模式。
    pub(super) bybit_sync_balance: Option<f64>,
    /// API-reported unrealized PnL per symbol (from WS position updates).
    /// API 報告的每交易對未實現損益（來自 WS 持倉更新）。
    pub(super) api_unrealized_pnl: HashMap<String, f64>,
    /// ORPHAN-ADOPT-1 FUP: side-car mirror of `positions` exposing only
    /// `(symbol → is_long)` so external observers (position_reconciler's
    /// orphan handler) can cross-check whether the engine already owns a
    /// candidate Orphan BEFORE dispatching a close. Updated on every insert /
    /// remove / clear alongside `positions`. Production wires
    /// `set_positions_mirror()` right after construction so the reconciler
    /// shares the same handle.
    /// ORPHAN-ADOPT-1 FUP：`positions` 的側車鏡像，僅暴露 `(symbol → is_long)`。
    /// 對帳器孤兒處理器讀此鏡像，派發平倉前先確認引擎是否已持倉，
    /// 避免把引擎剛開的新倉誤判為 Orphan。每次 insert / remove / clear
    /// 都同步更新。生產路徑在 TickPipeline 構造後用 `set_positions_mirror()`
    /// 換成與對帳器共享的 handle。
    pub(super) positions_mirror: Arc<parking_lot::RwLock<HashMap<String, bool>>>,
    /// EDGE-P2-3 Phase 1B-4.1: per-symbol FIFO queue of resting PostOnly
    /// limit orders awaiting a future tick touch/cross (Paper-only). Empty
    /// at this commit — 1B-4.2 will wire the enqueue path from the Paper
    /// dispatch router and the tick-level touch/cross sweep. Exchange mode
    /// never reads this map; real resting orders sit on Bybit's book and
    /// surface via WS order/fill events.
    /// EDGE-P2-3 Phase 1B-4.1：紙盤專用 per-symbol FIFO 掛中 PostOnly 限價單隊列。
    /// 本提交保持空。1B-4.2 會接線 enqueue 與 tick 碰觸/穿越 sweep。交易所模式
    /// 不讀此 map；真實掛單在 Bybit 委託簿上，靠 WS 成交事件回流。
    pub(super) resting_limit_orders: HashMap<String, VecDeque<RestingLimitOrder>>,
    /// EDGE-P2-3 Phase 1B-5: aggregate + per-symbol maker-order counters
    /// (submit / fill-full / fill-partial / timeout / degraded-fallback) plus
    /// running `sum_net_edge_bps`. Fed by `enqueue_resting_limit_order` and
    /// `sweep_resting_limit_orders_for_symbol`; read by router before enqueue
    /// so chronically timed-out symbols fall back to market execution.
    /// Paper-only — exchange path has its own WS-driven observability.
    /// EDGE-P2-3 Phase 1B-5：紙盤 maker 掛單統計（aggregate + per-symbol）+
    /// running `sum_net_edge_bps`。enqueue 與 sweep 餵入；router enqueue 前讀
    /// 此，KPI Degraded 時 fallback 市價。僅紙盤使用。
    pub(super) maker_stats: MakerStats,
    /// EDGE-P2-3 Phase 1B-4.3: latest WS-ticker funding rate per symbol.
    /// Populated by `on_tick` whenever `PriceEvent.funding_rate` is `Some(_)`;
    /// read by the router at maker-enqueue time to stamp
    /// `RestingLimitOrder.funding_rate_at_submit`. A symbol that has never
    /// seen a funding rate tick returns `None` → the router stamps 0.0 and the
    /// sweep's funding-drag guard treats it as "unknown / no bias".
    /// EDGE-P2-3 Phase 1B-4.3：每交易對最新的 WS tickers 資金費率。`on_tick` 於
    /// `PriceEvent.funding_rate` 非 None 時填入；router enqueue 時讀出，
    /// 壓入 `RestingLimitOrder.funding_rate_at_submit`。未見過的 symbol 回
    /// None → 壓 0.0、sweep funding drag guard 視為「未知 / 無偏差」。
    pub(super) funding_rates: HashMap<String, f64>,
}

impl PaperState {
    pub fn new(initial_balance: f64) -> Self {
        Self {
            _initial_balance: initial_balance,
            balance: initial_balance,
            peak_balance: initial_balance,
            session_start_ts_ms: openclaw_core::now_ms(),
            positions: HashMap::new(),
            latest_prices: HashMap::new(),
            latest_turnovers: HashMap::new(),
            total_realized_pnl: 0.0,
            total_fees: 0.0,
            trade_count: 0,
            stop_config: StopConfig::default(),
            forced_drawdown: 0.0,
            bybit_sync_balance: None,
            api_unrealized_pnl: HashMap::new(),
            positions_mirror: Arc::new(parking_lot::RwLock::new(HashMap::new())),
            resting_limit_orders: HashMap::new(),
            maker_stats: MakerStats::default(),
            funding_rates: HashMap::new(),
        }
    }

    /// Private helper: insert a position AND mirror `(symbol → is_long)`.
    /// 私有 helper：同時寫入 positions 與 positions_mirror。
    pub(super) fn positions_insert(&mut self, symbol: String, pos: PaperPosition) {
        self.positions_mirror
            .write()
            .insert(symbol.clone(), pos.is_long);
        self.positions.insert(symbol, pos);
    }

    /// Private helper: remove from both positions and mirror.
    /// 私有 helper：同步從 positions 與 mirror 移除。
    pub(super) fn positions_remove(&mut self, symbol: &str) -> Option<PaperPosition> {
        self.positions_mirror.write().remove(symbol);
        self.positions.remove(symbol)
    }

    /// Private helper: clear both positions and mirror.
    /// 私有 helper：清空 positions 與 mirror。
    pub(super) fn positions_clear(&mut self) {
        self.positions_mirror.write().clear();
        self.positions.clear();
    }
}

#[cfg(test)]
mod tests;
