//! Common strategy helpers — per-symbol state, cooldown, confidence builder.
//! 通用策略輔助 — 逐幣種狀態、冷卻、信心值建構器。
//!
//! MODULE_NOTE (EN): Extracted from funding_arb / bb_breakout / bb_reversion /
//!   ma_crossover to remove duplicated `HashMap<String, T>` patterns, cooldown
//!   math, and ADX+regime confidence formulas. Shared types here are
//!   intentionally small — each strategy keeps its domain-specific state
//!   tracking (RC-04 rollback, squeeze detection, ER-scaled exit, funding
//!   positions) in its own module.
//! MODULE_NOTE (中): 從 funding_arb / bb_breakout / bb_reversion /
//!   ma_crossover 提取，消除重複的 `HashMap<String, T>` 模式、冷卻計算與
//!   ADX+regime 信心值公式。此處的共享型別刻意維持輕量 —
//!   各策略的領域狀態（RC-04 回滾、壓縮偵測、ER 縮放出場、資金費率倉位）
//!   仍留在各自模組。

pub mod confidence_builder;
pub mod per_symbol_state;
pub mod trend_cooldown;

pub use confidence_builder::ConfidenceBuilder;
pub use per_symbol_state::PerSymbolState;
pub use trend_cooldown::TrendCooldown;
