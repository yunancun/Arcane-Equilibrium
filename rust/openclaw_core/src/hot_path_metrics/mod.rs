//! Hot-path metrics — HdrHistogram-based latency observability for hot paths.
//! 熱路徑指標 — 基於 HdrHistogram 的熱路徑延遲觀測。
//!
//! Module 概覽（per `docs/execution_plan/2026-05-21--p2_lg1_demo_slo_carveout_spec.md`）：
//!
//! - `h0_latency` — H0 gate `check()` 路徑 5 種 engine_mode（paper/demo/live/
//!   live_demo/live_testnet）的 p50/p99/p999/max percentile recorder。
//!
//! 設計約束：
//! - record 路徑 overhead ≤ 50ns（per spec AC-3，E5 baseline avg=4.86ns 10× headroom）
//! - per-tick reset 禁止（mem 爆風險）；reset 由 status_report 1h cadence 觸發
//! - 不引新 EngineMode enum；engine_mode 收 `&'static str` 對齊既有
//!   `effective_engine_mode` 5-string 系統（per spec §3.6）
//!
//! Module 入口僅做 re-export；型別/邏輯放子模組。

pub mod h0_latency;

pub use h0_latency::{H0LatencyRecorder, H0LatencySummary};

/// 5 種既有 engine_mode 標籤（per `openclaw_engine::mode_state::effective_engine_mode`）。
/// 用於 hot_path_metrics 子模組枚舉全部 mode 時的單一來源。
pub const ENGINE_MODES: &[&str] = &["paper", "demo", "live", "live_demo", "live_testnet"];
