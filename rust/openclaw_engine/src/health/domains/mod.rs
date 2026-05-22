//! M3 Sprint 2 Wave 1/2 — 6 domain emitter 拆檔範式。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_design_spec.md
//!   §3 D1 + spec §4.3 Wave 拆分 + dispatch packet §1.7 scaffold contract，本
//!   module 為 6 domain（engine_runtime / pipeline_throughput / database_pool /
//!   api_latency / strategy_quality / risk_envelope）拆檔範式：
//!     - Wave 1 Track B 接 `pipeline_throughput`
//!     - Wave 1 Track C 接 `database_pool`（本 commit）
//!     - Wave 2 Track D 接 `api_latency`
//!     - Wave 2 Track E 接 `strategy_quality`
//!     - Wave 2 Track F 接 `risk_envelope`
//!   engine_runtime 仍留在 `metric_emitter/mod.rs` (Track A scaffold owner)；
//!   後續 emitter 全走 `domains/<domain>.rs` 範式，避免 metric_emitter/mod.rs
//!   觸 2000 LOC hard cap。
//!
//! 主要 sub-module:
//!   - `pipeline_throughput`：Track B IMPL（WS tick rate / heartbeat lag /
//!     subscription drift / strategy signal rate / IPC roundtrip p99 — 30s
//!     sample；source closure 注入由 main.rs Wave 2 後接線）。
//!   - `database_pool`：Track C IMPL（sqlx Pool stats + writer queue probe +
//!     disk usage via sysinfo Disks）。
//!
//! 依賴:
//!   - 全部沿用 Track A scaffold（`DomainEmitter` / `MetricSample` /
//!     `RollingWindowAggregator` / `HealthObservationWriter` /
//!     `HealthStateMachine::observe_classified`）。
//!   - 各 domain 各自管自己的 sysinfo / sqlx / Bybit / strategy event 接點。
//!
//! 硬邊界:
//!   - emitter 只觀測，不修復外部 state（sqlx Pool 邏輯 / ws_client / risk_config
//!     既有 SSOT 不動）。
//!   - 不引 `cfg(feature = "spike")`；production binary 0 mock time 滲透。
//!   - 跨平台原生支援 Mac+Linux（per `feedback_cross_platform`）；不寫死
//!     `cfg(target_os = "linux")` 分支。

pub mod database_pool;
pub mod pipeline_throughput;
