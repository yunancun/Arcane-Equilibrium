//! AI Budget tracker — fail-closed monthly USD budget enforcement (Phase 4 4-15).
//! AI 預算追蹤器 — fail-closed 月度美元預算強制執行（Phase 4 4-15）。
//!
//! MODULE_NOTE (EN): Tracks per-scope LLM spend, enforces three-stage degradation
//!   (SoftWarn $80 / HardLimit $95 / Killswitch $100), fail-closed: if usage write
//!   to PG fails, the call is rejected. Config and usage rows live in V010 tables
//!   `learning.ai_budget_config` and `learning.ai_usage_log`. Operator/IPC can hot-
//!   reload config via `update_ai_budget_config`. Pricing is hardcoded placeholder
//!   here; sub-task 4-17 (provider pricing) will replace it with a real DB table.
//!
//! MODULE_NOTE (中): 追蹤每 scope 的 LLM 開銷，強制三段降級（SoftWarn $80 /
//!   HardLimit $95 / Killswitch $100），fail-closed：用量寫 PG 失敗時拒絕該次調用。
//!   配置與用量列儲存於 V010 的 `learning.ai_budget_config` 與 `learning.ai_usage_log`。
//!   Operator/IPC 可透過 `update_ai_budget_config` 熱重載配置。定價為硬編碼占位，
//!   4-17（provider pricing）會改用真實 DB 表。
//!
//! Fail-closed contract / fail-closed 合約:
//!   - record_usage() returns Err on DB write failure → caller MUST refuse the LLM call.
//!   - degrade_level() reads cached counters; if cache stale beyond TTL the caller
//!     should call refresh_usage() first.
//!   - record_usage() 寫 DB 失敗時返回 Err → caller 必須拒絕該次 LLM 調用。
//!   - degrade_level() 讀快取計數；若快取超過 TTL，caller 應先呼叫 refresh_usage()。

pub mod config_io;
pub mod pricing;
pub mod tracker;
pub mod usage_io;

pub use tracker::{BudgetConfig, BudgetTracker, DegradeLevel};
