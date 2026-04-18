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
}
