//! Strategy modules — 5 trading strategies + shared helpers (R04-5, G-SR-1).
//! 策略模組 — 5 個交易策略 + 共享輔助模組。
//!
//! MODULE_NOTE (EN): Defines Strategy trait + StrategyAction enum; public parameter
//!   schema + StrategyFactory live in sibling files (`params.rs`, `registry.rs`).
//!   Sub-modules: ma_crossover, bb_breakout, bb_reversion, grid_trading, funding_arb,
//!   confluence (shared scoring/persistence), grid_helpers (extracted grid math).
//!   Post-split (cluster C4c) this `mod.rs` is ~150 lines, well under §九 1200-line cap.
//!   Re-exports below preserve every external import path (`crate::strategies::X`).
//! MODULE_NOTE (中): 定義 Strategy trait + StrategyAction 枚舉；參數 schema 與
//!   StrategyFactory 移至 sibling 檔案（`params.rs`、`registry.rs`）。
//!   子模組：ma_crossover、bb_breakout、bb_reversion、grid_trading、funding_arb、
//!   confluence（共享評分/持續性）、grid_helpers（提取的網格數學）。
//!   cluster C4c 切分後 `mod.rs` 僅 ~150 行，遠低於 §九 1200 行硬上限。
//!   下方 re-export 保持所有外部匯入路徑（`crate::strategies::X`）零改動。

pub mod bb_breakout;
pub mod bb_reversion;
pub mod common;
pub mod confluence;
pub mod funding_arb;
pub mod grid_helpers;
pub mod grid_trading;
pub mod ma_crossover;
pub mod maker_rejection;

// ── C4c split: parameter schema + factory moved to siblings ──
// ── C4c 拆分：參數 schema + 工廠搬到 sibling ──
pub mod params;
pub mod registry;
pub mod strategy_params;

// Re-export public API surface so external call-sites keep using
// `crate::strategies::X` unchanged.
// 重新導出公用 API 表面，外部呼叫處 `crate::strategies::X` 完全不變。
pub use params::{
    load_strategy_params, load_strategy_params_from, BbBreakoutParams, BbReversionParams,
    FundingArbParams, GridTradingParams, MaCrossoverParams, ParamRange, StrategyParams,
    StrategyParamsConfig,
};
pub use registry::StrategyFactory;

use crate::intent_processor::OrderIntent;
use crate::strategies::maker_rejection::MakerRejectionCategory;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};
use openclaw_core::execution::FillResult;

/// First-class strategy action: Open (new position, full governance) or Close (exit, lightweight path).
/// 策略一等公民動作：Open（新倉，完整治理管線）或 Close（平倉，輕量路徑）。
///
/// Close bypasses governance gates (Guardian, cost_gate, Kelly sizing, P1 cap) since closing
/// reduces risk rather than increasing it. Pipeline looks up actual is_long/qty from paper_state.
/// Close 繞過治理門禁（Guardian、cost_gate、Kelly sizing、P1 cap），因為平倉是降低風險而非增加風險。
/// 管線從 paper_state 查找實際的 is_long/qty。
#[derive(Debug, Clone)]
pub enum StrategyAction {
    /// New position — goes through full governance pipeline.
    /// 新倉 — 經過完整治理管線。
    Open(OrderIntent),
    /// Close existing position — lightweight path, bypasses governance gates.
    /// 平倉 — 輕量路徑，繞過治理門禁。
    Close {
        symbol: String,
        confidence: f64,
        reason: String,
    },
}

/// Strategy trait — implement for each trading strategy.
/// 策略 trait — 為每個交易策略實現。
/// Send required for tokio::spawn compatibility.
pub trait Strategy: Send {
    /// Strategy name for logging and attribution.
    /// 策略名稱用於日誌和歸因。
    fn name(&self) -> &str;

    /// Is this strategy currently active?
    /// 此策略當前是否活躍？
    fn is_active(&self) -> bool;

    /// RRC-1-E2: Set strategy active/paused state via IPC.
    /// RRC-1-E2：通過 IPC 設置策略活躍/暫停狀態。
    fn set_active(&mut self, active: bool);

    /// W-AUDIT-8a Phase A：聲明本策略消費的 alpha source tag 清單。
    /// 由 `Orchestrator` 用於 dispatch tracking metric `alpha_source_*_total`。
    /// 無 default impl：5 既存策略 explicit declare 強制 migration。
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag];

    /// Process a tick and return strategy actions (Open or Close).
    /// 處理 tick 並返回策略動作（Open 或 Close）。
    /// W-AUDIT-8a Phase A：簽名升級 + `surface: &AlphaSurface<'_>`。Tier 1 仍由
    /// `ctx.indicators` 提供（向後相容）；策略未來消費 Tier 2-4 改走
    /// `surface.<field>`，`None` → fail-closed 跳過自身 alpha source。
    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction>;

    /// Called when an intent from this strategy was rejected by the governance pipeline.
    /// 當此策略的意圖被治理管線拒絕時調用。
    /// Default: no-op. Strategies that track internal position should override.
    /// 默認：無操作。跟蹤內部倉位的策略應覆蓋此方法。
    fn on_rejection(&mut self, _intent: &OrderIntent, _reason: &str) {
        // Default no-op / 默認無操作
    }

    /// Called when an order from this strategy was filled.
    /// 當此策略的訂單成交時調用。
    fn on_fill(&mut self, _intent: &OrderIntent, _fill: &FillResult) {
        // Default no-op / 默認無操作
    }

    /// Called when a position was closed externally (risk-close/stop) rather than by this strategy.
    /// Strategies that track internal position state should override to stay in sync.
    /// 當倉位被外部（風控止損）而非本策略關閉時調用。跟蹤內部倉位狀態的策略應覆蓋以保持同步。
    fn on_external_close(&mut self, _symbol: &str) {
        // Default no-op / 默認無操作
    }

    /// Called after the pipeline confirms a strategy-emitted Close was executed successfully.
    /// Strategies that defer state changes until close is confirmed should override.
    /// 管線確認策略發出的 Close 已成功執行後調用。延遲狀態變更直到確認平倉的策略應覆蓋。
    fn on_close_confirmed(&mut self, _symbol: &str) {
        // Default no-op / 默認無操作
    }

    /// Called when a strategy-emitted Close was skipped (no position found in paper_state).
    /// Strategies that eagerly mutated state should override to roll back.
    /// 策略發出的 Close 被跳過（paper_state 中未找到倉位）時調用。提前變更狀態的策略應覆蓋以回滾。
    fn on_close_skipped(&mut self, _symbol: &str) {
        // Default no-op / 默認無操作
    }

    /// EDGE-P2-3 Phase 1B-3 (FIX-G7-09C-PHASE2-WIRE-1B3): exchange-side
    /// rejection reached this strategy. Distinct from `on_rejection`
    /// (which is the *governance* pipeline saying "no") — this is Bybit
    /// itself rejecting an order after structural acceptance, classified by
    /// `MakerRejectionCategory`. Strategies should arm a per-symbol cooldown
    /// so the same maker order does not get re-emitted in the next tick
    /// while the book / account-level cause is still live.
    /// Default no-op for strategies that do not yet implement maker-aware
    /// retry control; PostOnly maker entries (G7-09c Phase 1) make this
    /// callback meaningful for `grid_trading` first.
    /// `category` is the classified Bybit reject reason (`PostOnlyCross`,
    /// `TooManyPending`, `FokCancel`, `SelfCancel`, `Other(raw)`); strategy
    /// may inspect to decide cooldown duration / suppression strategy.
    /// EDGE-P2-3 Phase 1B-3：交易所端拒絕傳到本策略。與 `on_rejection`（治理
    /// 管線拒絕）不同，這是 Bybit 在結構接受後拒絕下單，已分類為
    /// `MakerRejectionCategory`。策略應設定該 symbol 的冷卻時間，避免下一
    /// tick 重發同一 maker 單。預設 no-op；PostOnly 入場（G7-09c Phase 1）
    /// 讓本 callback 對 `grid_trading` 首先有意義。
    fn on_post_only_rejected(
        &mut self,
        _symbol: &str,
        _ts_ms: i64,
        _category: &MakerRejectionCategory,
    ) {
        // Default no-op / 預設無操作
    }

    // ── Phase 3a: Runtime parameter tuning API (AGT-1) ──
    // Phase 3a：運行時參數調參 API

    /// Update strategy parameters from JSON. Returns Err if invalid.
    /// 從 JSON 更新策略參數。無效時返回 Err。
    fn update_params_json(&mut self, _json: &str) -> Result<(), String> {
        Err("update_params not implemented for this strategy".into())
    }

    /// Get current parameters as JSON string.
    /// 獲取當前參數的 JSON 字符串。
    fn get_params_json(&self) -> String {
        "{}".into()
    }

    /// Get tunable parameter ranges as JSON string.
    /// 獲取可調參數範圍的 JSON 字符串。
    fn param_ranges_json(&self) -> String {
        "[]".into()
    }

    // ── CONF-D: per-strategy confidence scaling exposed via update_strategy_params ──
    // CONF-D：通過 update_strategy_params 暴露的逐策略 confidence 縮放因子

    /// CONF-D: Read the current confidence scale (default 1.0).
    /// Strategies multiply every emitted intent.confidence by this value
    /// before pushing to the intent stream. Range [0.0, 2.0]; >1.0 amplifies,
    /// <1.0 dampens, 0.0 effectively mutes the strategy without disabling it.
    /// CONF-D：讀取當前 confidence 縮放因子（默認 1.0）。
    /// 策略在發出 intent 前將其 confidence 乘以此值。範圍 [0, 2]。
    fn conf_scale(&self) -> f64 {
        1.0
    }

    /// CONF-D: Set confidence scale. Out-of-range values are clamped to [0.0, 2.0].
    /// Default no-op for strategies that opt out (their conf_scale stays 1.0).
    /// CONF-D：設定 confidence 縮放因子，越界自動 clamp 到 [0, 2]。
    fn set_conf_scale(&mut self, _scale: f64) {
        // Default no-op / 預設無操作
    }
}

// ── Tests moved verbatim to sibling `tests.rs` to keep mod.rs lean ──
// ── 測試逐字搬到 sibling `tests.rs`，維持 mod.rs 精簡 ──
#[cfg(test)]
mod tests;
