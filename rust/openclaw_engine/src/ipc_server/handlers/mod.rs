//! IPC method handler facade — the monolithic `handlers.rs` was split by
//! domain as part of E5-P1-3 to keep each file under the §九 800-line warning
//! threshold. This module:
//!   - declares the domain submodules (`misc`, `budget`, `teacher`,
//!     `strategy`, `risk`, `dynamic_risk`, `governance`)
//!   - re-exports every handler + the `StrategyParamOp` enum under the same
//!     `handlers::*` namespace the dispatcher in `ipc_server/mod.rs` was
//!     already using (`use handlers::*;`), so no call-site edits are required
//!
//! MODULE_NOTE (EN): Each handler's visibility, signature, and behaviour is
//!   bit-for-bit identical to the pre-split `handlers.rs`. Only the hosting
//!   file changed. Config IPC helpers stay in the sibling `handlers_config`
//!   module as before.
//! MODULE_NOTE (中)：E5-P1-3 將 `handlers.rs` 按領域拆分；每個 handler 的
//!   可見性、簽名、行為與拆分前完全一致，僅承載檔案改變。Config IPC 輔助
//!   維持在兄弟模組 `handlers_config` 不變。

mod budget;
mod dynamic_risk;
mod governance;
mod misc;
mod risk;
mod strategy;
mod teacher;

// Re-export every handler + enum under `handlers::*` so the dispatcher in
// `ipc_server/mod.rs` (which does `use handlers::*;`) keeps resolving the
// same names to the same functions. Visibility is preserved as
// `pub(in crate::ipc_server)` on the submodule items, so `pub use` here lifts
// them to the facade without widening the public surface.
// 重新導出所有 handler 與 enum 於 `handlers::*` 命名空間；dispatcher
// 的 `use handlers::*;` 不需修改即可解析同名 fn。子模組以
// `pub(in crate::ipc_server)` 限定可見性，避免拓寬對外暴露面。
pub(in crate::ipc_server) use budget::{
    handle_get_ai_budget_status, handle_record_ai_usage, handle_update_ai_budget_config,
};
pub(in crate::ipc_server) use dynamic_risk::{
    handle_get_dynamic_risk_status, handle_set_dynamic_risk_enabled,
};
pub(in crate::ipc_server) use governance::{
    handle_force_governor_looser, handle_force_governor_tighter,
    handle_set_system_mode_broadcast,
};
pub(in crate::ipc_server) use misc::{
    handle_get_active_symbols, handle_get_phase4_status, handle_get_scanner_status,
    handle_get_state, handle_get_strategist_cycle_metrics,
};
pub(in crate::ipc_server) use risk::{
    handle_clear_consecutive_losses, handle_reset_drawdown_baseline, handle_risk_runtime_status,
    handle_update_risk_config,
};
pub(in crate::ipc_server) use strategy::{
    handle_set_strategy_active, handle_strategy_param_cmd, handle_submit_paper_order,
    StrategyParamOp,
};
pub(in crate::ipc_server) use teacher::{
    handle_get_teacher_loop_status, handle_set_teacher_loop_enabled,
};
