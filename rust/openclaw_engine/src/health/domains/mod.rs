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
//!   - `api_latency`：Track D IMPL（REST p50/p95/p99 + WS RTT p50/p99 +
//!     HTTP 4xx/5xx retCode 累積 + ws_dropout 累積；60s sample；source
//!     probe trait 注入；ret_code 用 HTTP 標準語意預留 multi-venue per
//!     ADR-0040）。
//!   - `api_latency_probe_impl`：PA-DRIFT-4 Wave A IMPL — `RealApiLatencySourceProbe`
//!     接 bybit_rest_client `RestLatencyHistogram` + `RetCodeCounter` 與
//!     bybit_private_ws `WsDropoutCounter` + `WsRttHistogram` 的 trait 適配層；
//!     main.rs Wave B 接 scheduler 時注入此 probe；本檔不修 client 既有邏輯。
//!   - `strategy_quality`：Track E IMPL（per-strategy SM 25 instance =
//!     5 strategy × 5 symbol + aggregate SM rule 0.40；fill_rate /
//!     slippage / lease grant / dormant minute / signal count；5min sample；
//!     trait probe 注入由 main.rs Wave 2 後接線）。
//!   - `strategy_quality_probe_impl`：Sprint 5+ §4.3.1 Phase A IMPL —
//!     `RealStrategyQualitySourceProbe` + `StrategyQualityMetricsCache` per-
//!     (strategy, symbol) HashMap 緩存 + 5 metric snapshot；main_health_emitters.rs
//!     Wave C 接 scheduler 時注入此 probe；update task 走 300s tick 1 big CTE
//!     join PG query 整 HashMap 覆寫；本檔不修 strategy_quality.rs 1580 LOC
//!     emitter + scheduler + classify 既有邏輯。
//!   - `risk_envelope`：Track F IMPL（portfolio cum_pnl_24h / max_dd /
//!     position_count / correlation_avg_pairwise / concentration_top1 — 300s
//!     sample；source probe 注入由 main.rs Wave 2 後接線；emitter 只觀測，不
//!     修 risk_verdict_ledger / position_snapshot / fill_writer SSOT）。
//!   - `risk_envelope_probe_impl`：Sprint 4+ first Live PA-DRIFT-5 Wave A IMPL —
//!     `RealRiskEnvelopeSourceProbe` + `PortfolioStateCache` 24h sliding window
//!     +5 SSOT calculator accessor；main.rs Wave B 接 scheduler 時注入此 probe；
//!     本檔不修 paper_state / mode_state / pipeline_types 既有寫入邏輯。
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

pub mod api_latency;
pub mod api_latency_probe_impl;
pub mod database_pool;
pub mod pipeline_throughput;
pub mod risk_envelope;
pub mod risk_envelope_probe_impl;
pub mod strategy_quality;
pub mod strategy_quality_probe_impl;
