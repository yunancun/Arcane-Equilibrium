//! Unix domain socket JSON-RPC 2.0 server for Rust↔Python IPC (R01-1).
//! Unix 域套接字 JSON-RPC 2.0 服務器，用於 Rust↔Python IPC。
//!
//! MODULE_NOTE (EN): Listens on a Unix socket, handles JSON-RPC 2.0 requests
//!   with newline-delimited messages. Each connection spawns a tokio task.
//!   Supports: ping, get_state, reload_config,
//!   paper session (pause/resume/close_all/reset), snapshot reads (paper_state/prices/stats),
//!   strategy params (update_strategy_params/get_strategy_params/get_param_ranges).
//! MODULE_NOTE (中): 監聯 Unix 套接字，處理 JSON-RPC 2.0 請求（換行分隔消息）。
//!   每個連接生成一個 tokio 任務。支援：ping、get_state、reload_config、
//!   紙盤控制（pause/resume/close_all/reset）、
//!   快照讀取（paper_state/prices/stats）、策略參數（update/get/ranges）。
//!
//! ## Module layout (G5-FUP-IPC-MOD-SPLIT, 2026-04-26)
//! ## 模組佈局（G5-FUP-IPC-MOD-SPLIT, 2026-04-26）
//!
//! `mod.rs` was 1251 lines (4% over §九 1200 hard cap). Split into siblings
//! following the `tick_pipeline/` pattern. `mod.rs` now keeps only module
//! declarations + re-exports so call sites and tests don't need to change.
//! All hot-path semantics (patch_risk_config deep-merge / EDGE-P1b 8 exit_*
//! fields incl. exit_stale_peak_ms / update_risk_config) preserved
//! byte-identical — pure structural extraction, zero production logic diff.
//!
//! `mod.rs` 原 1251 行（4% 超 §九 1200 硬上限）。仿 `tick_pipeline/` 模式拆
//! 成 sibling。`mod.rs` 現只保留模組宣告 + re-export，呼叫端與 test 無須修改。
//! 所有 hot-path 語意（patch_risk_config 深合併 / EDGE-P1b 8 個 exit_* 欄位
//! 含 exit_stale_peak_ms / update_risk_config）byte-identical 保留 —
//! 純結構抽取、零 production 邏輯 diff。
//!
//! ```text
//! ipc_server/
//! ├── mod.rs              # facade: module decl + pub re-export       (~95 lines)
//! ├── slots.rs            # late-injected Arc<RwLock<Option<...>>>    (~75 lines)
//! ├── engine_routing.rs   # PerEngineRiskStores / EngineCommandChannels / extract_engine_tx
//! ├── protocol.rs         # JsonRpc{Request,Response,Error} + IpcError + ERR_* consts
//! ├── server.rs           # IpcServer struct + setters + run() accept loop
//! ├── connection.rs       # HMAC handshake (verify_ipc_token) + handle_connection
//! ├── dispatch.rs         # dispatch_request + small utility handlers
//! ├── handlers/           # domain handlers (risk / strategy / budget / teacher / governance / ...)
//! ├── handlers_config.rs  # generic get_/patch_config helpers (deep-merge)
//! ├── param_extractor.rs  # JSON-RPC params extraction & validation helpers (E5-P1-5)
//! └── tests/              # integration tests against dispatch_request (10 sibling files)
//! ```

mod connection;
mod dispatch;
mod engine_routing;
mod handlers;
mod handlers_config;
// E5-P1-5: JSON-RPC params extraction & validation helpers (orphan §九).
//         Exposed as a sibling module so existing handlers.rs can adopt
//         incrementally without requiring a coordinated migration PR.
// E5-P1-5：JSON-RPC 參數提取與驗證輔助（§九 孤兒抽取）。
//         以兄弟模組暴露，讓現有 handlers.rs 可遞進採用，無需一次性大遷移。
pub(crate) mod param_extractor;
mod protocol;
mod server;
mod slots;
#[cfg(test)]
mod tests;

// ---------------------------------------------------------------------------
// Re-exports — keep `use crate::ipc_server::*` (and `use super::*` from tests)
// resolving exactly the names that existed pre-split, so call sites and
// tests don't need to change.
// 重新導出 — 維持拆分前 `use crate::ipc_server::*` 與 test 的
// `use super::*` 解析的所有名稱，呼叫端與測試零修改。
// ---------------------------------------------------------------------------

// Public API (consumed by main.rs / external crates).
// 公開 API（main.rs 與外部 crate 使用）。
pub use engine_routing::{EngineCommandChannels, PerEngineRiskStores};
pub use protocol::{IpcError, JsonRpcError, JsonRpcRequest, JsonRpcResponse};
pub use server::IpcServer;
pub use slots::{
    AuditPoolSlot, BudgetTrackerSlot, StrategistCountersSlot, TeacherLoopHandles, TeacherLoopSlot,
};

// Internal re-exports — each `handlers/*.rs` and `handlers_config.rs` file
// uses `use super::super::*` to pick up the items the dispatcher historically
// inlined in `mod.rs`. To avoid touching every domain handler call site, we
// re-export the same names back through the facade with `pub(crate)`
// visibility (so the public API surface stays exactly what `pub use` above
// declared).
// 內部 re-export — 每個 `handlers/*.rs` 與 `handlers_config.rs` 用
// `use super::super::*` 取得 dispatcher 過去 inlined 在 `mod.rs` 的型別。
// 為避免動到每個 domain handler 的 call site，這裡用 `pub(crate)` 把同名
// 項目從 facade re-export 回來（公開 API 表面仍以上面的 `pub use` 為準）。

// Error code constants used in handler short-circuits.
// handler 短路用的錯誤碼常量。
pub(crate) use protocol::{ERR_INTERNAL, ERR_INVALID_REQUEST};

// Re-export `extract_engine_tx` so handlers that route per engine can call
// it without a fully-qualified path.
// re-export `extract_engine_tx`，讓 per-engine 路由 handler 不必寫完整路徑。
#[allow(unused_imports)]
pub(crate) use engine_routing::extract_engine_tx;

// Standard library + crate types used by handlers via `super::super::*`
// and tests via `use super::*`. Re-exported here so call sites & tests
// keep resolving the same names without growing per-file `use` statements.
// handler 透過 `super::super::*`、test 透過 `use super::*` 使用的標準庫 +
// crate 型別。在 facade re-export 讓 call site 與測試解析同名項目，
// 不必逐檔長 use list。
pub(crate) use crate::claude_teacher::ConsumerLoopStatus;
pub(crate) use crate::config::{
    BudgetConfig, ConfigManager, ConfigStore, LearningConfig, PatchSource, RiskConfig,
};
pub(crate) use crate::tick_pipeline::{PipelineCommand, PipelineSnapshot};
pub(crate) use std::path::PathBuf;
pub(crate) use std::sync::atomic::{AtomicBool, Ordering};
pub(crate) use std::sync::Arc;
pub(crate) use tokio::net::UnixListener;
pub(crate) use tokio::sync::RwLock;

// Internal re-exports.
// `dispatch_request` is consumed by tests via `super::super::*` (and by the
// production code path via `super::dispatch::dispatch_request` directly in
// `connection.rs`). Re-exporting it crate-wide so tests resolve it through
// the facade.
//
// Domain handlers re-exported through `handlers/mod.rs` (which uses
// `pub(in crate::ipc_server) use ...` per-handler). The facade pulls them
// into `ipc_server::*` so tests under `tests/*.rs` reach them via
// `super::super::*`.
//
// 內部 re-export。
// `dispatch_request` 給 tests 透過 `super::super::*` 取用（生產路徑透過
// `connection.rs` 的 `super::dispatch::dispatch_request` 直呼）。
// crate 範圍 re-export 讓 tests 經 facade 解析。
//
// Domain handler 透過 `handlers/mod.rs`（內部 `pub(in crate::ipc_server)
// use ...`）暴露；facade 把它們拉進 `ipc_server::*`，tests 經
// `super::super::*` 取得。
pub(crate) use dispatch::dispatch_request;
pub(in crate::ipc_server) use handlers::*;
pub(crate) use protocol::ERR_METHOD_NOT_FOUND;
