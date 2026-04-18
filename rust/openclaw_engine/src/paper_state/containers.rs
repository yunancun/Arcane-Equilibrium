//! Paper Trading containers — per-symbol position data struct.
//! 紙盤交易容器 — 單倉位資料結構。
//!
//! MODULE_NOTE (EN): Holds only data-container types (`PaperPosition`) so that
//!   engine code referencing a plain position record does not need to depend on
//!   the full `PaperState` surface. Separated from `mod.rs` during the
//!   E5-P1-1 split of `paper_state.rs` (2026-04-18) to keep each submodule
//!   focused on a single concern.
//! MODULE_NOTE (中): 只放資料容器型別（PaperPosition），讓引用單倉位資料的程式碼
//!   不需依賴整個 PaperState 面。2026-04-18 E5-P1-1 拆分 paper_state.rs 時自 mod.rs
//!   分離出來，讓每個子模組專注單一職責。

use serde::{Deserialize, Serialize};

/// A paper trading position.
/// 紙盤交易持倉。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaperPosition {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub entry_price: f64,
    pub best_price: f64,
    pub entry_fee: f64,
    pub entry_ts_ms: u64,
    pub unrealized_pnl: f64,
    /// EDGE-P3-1 R2: context_id of the entry that opened this position.
    /// Threaded to trading.fills.entry_context_id on close for ML training JOIN.
    /// Empty string when unknown (e.g., pre-V017 restored snapshots, orphan adopt).
    /// EDGE-P3-1 R2：開此倉的 entry 對應 context_id。平倉時透傳到
    /// trading.fills.entry_context_id，供 ML 訓練 JOIN。未知時為空串（如 pre-V017
    /// 還原的快照、orphan adopt）。
    #[serde(default)]
    pub entry_context_id: String,
    /// ORPHAN-ADOPT-1 Phase 2A: strategy name that originated this position.
    /// Strategy-driven fills write `intent.strategy` (e.g. "ma_crossover").
    /// Exchange-origin inserts (import_positions, WS upsert) write "bybit_sync".
    /// Adopted orphans write `ORPHAN_ADOPTED_STRATEGY` ("orphan_adopted").
    /// Same-direction accumulates preserve the first writer (first-write-wins)
    /// — rationale: original strategy owns the round-trip. Empty string only
    /// on pre-Phase-2A deserialized snapshots.
    /// ORPHAN-ADOPT-1 Phase 2A：倉位歸屬策略。策略驅動填單寫 intent.strategy；
    /// 交易所來源填單寫 "bybit_sync"；adopt 的孤兒寫 ORPHAN_ADOPTED_STRATEGY。
    /// 同向加倉保留首次寫入者（第一個持倉策略負責整個 round-trip）。
    /// 空字串僅於 Phase 2A 之前的舊快照反序列化時出現。
    #[serde(default)]
    pub owner_strategy: String,
    /// MICRO-PROFIT-FIX-1 (2026-04-17): cumulative entry notional — set on
    /// first open (`qty * entry_price`) and **accumulated** on same-direction
    /// fills (`entry_notional += fill_qty * fill_price`). NOT decremented on
    /// reductions, so it represents the peak accumulated entry notional and
    /// gives `fast_track` a stable baseline for the
    /// `ft_min_notional_ratio_of_entry` filter. Legacy snapshots lacking this
    /// field deserialise to `0.0` via `#[serde(default)]`; `PaperState::new`
    /// migrates them in-place to `qty * entry_price` on startup.
    /// MICRO-PROFIT-FIX-1：累積入場名目。首開 = qty × entry_price；同向加倉累加；
    /// 減倉不改。舊快照缺該欄位時反序列為 0.0，由 PaperState::new 啟動時補齊。
    #[serde(default)]
    pub entry_notional: f64,
    /// EXIT-FEATURES-TABLE-1 (2026-04-19): max favorable unrealized pnl %
    /// since entry. Tick-by-tick the engine calls
    /// `PaperPosition::refresh_max_favorable` with the current mark price; this
    /// field monotonically retains the highest realised-like % seen. Used by
    /// Track P exit rules and by `learning.exit_features.peak_pnl_pct` label.
    /// Legacy snapshots without this field deserialise to 0.0; the first tick
    /// after restore backfills with the correct value. Unit: percent of
    /// `entry_notional` (i.e. already scaled — 1.5 means +1.5%).
    /// EXIT-FEATURES-TABLE-1：自開倉以來 max favorable unrealized pnl 百分比。
    /// 每 tick 由 `PaperPosition::refresh_max_favorable` 用當下 mark price 更新；
    /// 此欄位單調保留觀測到的最大 %。舊快照缺該欄位時反序列為 0.0，還原後首次
    /// tick 自然補上正確值。單位：entry_notional 的百分比（1.5 = +1.5%）。
    #[serde(default)]
    pub max_favorable_pnl_pct: f32,
    /// EXIT-FEATURES-TABLE-1 (2026-04-19): wall-clock ms when
    /// `max_favorable_pnl_pct` was last set to a new high (strictly >). On open
    /// this is initialised to `entry_ts_ms` (peak = entry baseline = 0). Used
    /// to derive `time_since_peak_ms` feature at exit. Legacy snapshots without
    /// this field deserialise to 0, and the first favorable tick after restore
    /// will stamp the correct value.
    /// EXIT-FEATURES-TABLE-1：`max_favorable_pnl_pct` 上次刷新（嚴格 >）的 wall-clock
    /// 毫秒。開倉時初始化為 `entry_ts_ms`（peak = 基準 0）。退場時 derive
    /// `time_since_peak_ms` 特徵。舊快照缺該欄位時反序列為 0，還原後首次 favorable
    /// tick 會補上正確值。
    #[serde(default)]
    pub peak_reached_ts_ms: i64,
}

/// EXIT-FEATURES-TABLE-1 (2026-04-18): immutable snapshot of the exit-relevant
/// fields of a `PaperPosition`. Captured by the caller **before** invoking any
/// `close_position*` / `reduce_position` helper that mutates or removes the
/// position, then threaded into `emit_close_fill` so the exit-features writer
/// has a stable view regardless of whether the position has since been removed.
///
/// Intentionally a plain value type (no lifetimes) so the snapshot can outlive
/// the borrow on `PaperState` while the close mutation runs.
///
/// EXIT-FEATURES-TABLE-1：PaperPosition 退場相關欄位的不可變快照。呼叫端在
/// 執行 close_position* / reduce_position（會改動或移除倉位）**之前**捕獲，
/// 再傳給 emit_close_fill，讓退場特徵寫入器擁有穩定視圖，與倉位是否已被
/// 移除脫鉤。刻意設計為純值型別（無生命週期）以便快照在 close 變更期間
/// 仍能跨 PaperState 借用存活。
#[derive(Debug, Clone)]
pub struct PositionExitSnapshot {
    pub symbol: String,
    pub is_long: bool,
    pub qty_at_snapshot: f64,
    pub entry_price: f64,
    pub entry_ts_ms: u64,
    pub entry_fee: f64,
    pub max_favorable_pnl_pct: f32,
    pub peak_reached_ts_ms: i64,
    pub owner_strategy: String,
    pub entry_context_id: String,
    pub entry_notional: f64,
}

impl PositionExitSnapshot {
    /// Derive from a `PaperPosition` reference. Infallible — all fields are
    /// plain copies / clones of the position state at call time.
    /// 從 PaperPosition 引用衍生；所有欄位皆為當下快照的純拷貝，絕不失敗。
    pub fn from_position(p: &PaperPosition) -> Self {
        Self {
            symbol: p.symbol.clone(),
            is_long: p.is_long,
            qty_at_snapshot: p.qty,
            entry_price: p.entry_price,
            entry_ts_ms: p.entry_ts_ms,
            entry_fee: p.entry_fee,
            max_favorable_pnl_pct: p.max_favorable_pnl_pct,
            peak_reached_ts_ms: p.peak_reached_ts_ms,
            owner_strategy: p.owner_strategy.clone(),
            entry_context_id: p.entry_context_id.clone(),
            entry_notional: p.entry_notional,
        }
    }
}

impl PaperPosition {
    /// EXIT-FEATURES-TABLE-1 (2026-04-19): update peak tracking given the
    /// current mark price. Returns true iff a new high was recorded (caller
    /// may log / metric). Safe to call every tick; O(1); no allocation.
    ///
    /// Semantics:
    /// - `pnl_pct = (mark - entry) / entry * 100 * side`, where side = +1 long / -1 short.
    /// - If `pnl_pct > self.max_favorable_pnl_pct`: update field + stamp `peak_reached_ts_ms`.
    /// - Guards: non-finite `mark_price` / `entry_price <= 0` → no-op.
    ///
    /// EXIT-FEATURES-TABLE-1：以當下 mark price 更新峰值追蹤；返回是否刷新新高。
    /// 保證每 tick 可安全呼叫（O(1)、零分配）。
    /// 語義：pnl_pct = (mark − entry) / entry × 100 × side；新高才更新 + 蓋時戳。
    /// 守衛：mark_price / entry_price 非法時 no-op。
    pub fn refresh_max_favorable(&mut self, mark_price: f64, ts_ms: i64) -> bool {
        if !mark_price.is_finite() || self.entry_price <= 0.0 {
            return false;
        }
        let side = if self.is_long { 1.0 } else { -1.0 };
        let pnl_pct = ((mark_price - self.entry_price) / self.entry_price) * 100.0 * side;
        // f64 → f32 at the boundary; pnl% fits comfortably in f32 dynamic range.
        let pnl_pct_f32 = pnl_pct as f32;
        if pnl_pct_f32 > self.max_favorable_pnl_pct {
            self.max_favorable_pnl_pct = pnl_pct_f32;
            self.peak_reached_ts_ms = ts_ms;
            true
        } else {
            false
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_position(is_long: bool, entry_price: f64, entry_ts_ms: u64) -> PaperPosition {
        PaperPosition {
            symbol: "BTCUSDT".into(),
            is_long,
            qty: 0.1,
            entry_price,
            best_price: entry_price,
            entry_fee: 0.0,
            entry_ts_ms,
            unrealized_pnl: 0.0,
            entry_context_id: String::new(),
            owner_strategy: "ma_crossover".into(),
            entry_notional: 0.1 * entry_price,
            max_favorable_pnl_pct: 0.0,
            peak_reached_ts_ms: entry_ts_ms as i64,
        }
    }

    /// EXIT-FEATURES-TABLE-1: tick→peak→giveback lifecycle preserves peak.
    /// EXIT-FEATURES-TABLE-1：tick→peak→giveback 生命週期保留峰值。
    #[test]
    fn test_refresh_max_favorable_tick_peak_giveback_long() {
        let mut p = make_position(true, 100.0, 1000);
        // tick 1: price 101 → +1% favorable
        assert!(p.refresh_max_favorable(101.0, 2000));
        assert!((p.max_favorable_pnl_pct - 1.0).abs() < 1e-5);
        assert_eq!(p.peak_reached_ts_ms, 2000);
        // tick 2: price 102 → +2% new high
        assert!(p.refresh_max_favorable(102.0, 3000));
        assert!((p.max_favorable_pnl_pct - 2.0).abs() < 1e-5);
        assert_eq!(p.peak_reached_ts_ms, 3000);
        // tick 3: price 101.5 giveback → peak unchanged, ts unchanged
        assert!(!p.refresh_max_favorable(101.5, 4000));
        assert!((p.max_favorable_pnl_pct - 2.0).abs() < 1e-5);
        assert_eq!(p.peak_reached_ts_ms, 3000);
    }

    /// Short side: favorable = price drops.
    /// 空頭：有利 = 價格下跌。
    #[test]
    fn test_refresh_max_favorable_short_side_inverted() {
        let mut p = make_position(false, 100.0, 1000);
        // price 99 → short is +1%
        assert!(p.refresh_max_favorable(99.0, 2000));
        assert!((p.max_favorable_pnl_pct - 1.0).abs() < 1e-5);
        // price 101 (adverse for short) → no new high
        assert!(!p.refresh_max_favorable(101.0, 3000));
        assert_eq!(p.peak_reached_ts_ms, 2000);
    }

    /// First favorable tick must update from 0 baseline.
    /// 首次有利 tick 必須自 0 基準更新。
    #[test]
    fn test_refresh_max_favorable_first_tick_updates_from_zero() {
        let mut p = make_position(true, 100.0, 1000);
        assert_eq!(p.max_favorable_pnl_pct, 0.0);
        assert_eq!(p.peak_reached_ts_ms, 1000); // init = entry_ts_ms
        // adverse first: 99 → long -1%, no update, peak stays at entry
        assert!(!p.refresh_max_favorable(99.0, 2000));
        assert_eq!(p.max_favorable_pnl_pct, 0.0);
        assert_eq!(p.peak_reached_ts_ms, 1000);
        // favorable: +0.5% updates
        assert!(p.refresh_max_favorable(100.5, 3000));
        assert_eq!(p.peak_reached_ts_ms, 3000);
    }

    /// NaN / Inf mark price must be a no-op (never poison peak).
    /// 非法 mark price 必須 no-op（永不污染 peak）。
    #[test]
    fn test_refresh_max_favorable_rejects_non_finite() {
        let mut p = make_position(true, 100.0, 1000);
        assert!(!p.refresh_max_favorable(f64::NAN, 2000));
        assert!(!p.refresh_max_favorable(f64::INFINITY, 3000));
        assert!(!p.refresh_max_favorable(f64::NEG_INFINITY, 4000));
        assert_eq!(p.max_favorable_pnl_pct, 0.0);
        assert_eq!(p.peak_reached_ts_ms, 1000);
    }

    /// Legacy snapshot (serde default 0.0 / 0) stays consistent; first tick
    /// after restore backfills peak_reached_ts_ms correctly.
    /// 舊快照 (serde default) 首次 tick 後自然補齊。
    #[test]
    fn test_legacy_snapshot_defaults_backfill_on_first_tick() {
        let mut p = make_position(true, 100.0, 1000);
        // Simulate legacy: peak_reached_ts_ms = 0 (restored from pre-V0xx snapshot)
        p.peak_reached_ts_ms = 0;
        // First favorable tick overwrites the stale 0.
        assert!(p.refresh_max_favorable(100.5, 5000));
        assert_eq!(p.peak_reached_ts_ms, 5000);
    }

    /// entry_price <= 0 (corrupt state) must be a no-op, not a divide-by-zero.
    /// entry_price <= 0 (state 損毀) 必須 no-op，不能除 0。
    #[test]
    fn test_refresh_max_favorable_guards_entry_price_zero() {
        let mut p = make_position(true, 0.0, 1000);
        assert!(!p.refresh_max_favorable(100.0, 2000));
        assert_eq!(p.max_favorable_pnl_pct, 0.0);
    }
}
