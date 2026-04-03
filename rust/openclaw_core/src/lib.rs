//! OpenClaw Core — risk control, gate logic, state machines, calculations
//! OpenClaw 核心 — 風控、門控邏輯、狀態機、計算
//!
//! Phase R-02: perception + cognition + risk modules.
//! 階段 R-02：感知 + 認知 + 風控模組。

pub use openclaw_types;

pub mod attention;
pub mod cognitive;
pub mod cost_gate;
pub mod dream;
pub mod h0_gate;
pub mod indicators;
pub mod klines;
pub mod opportunity;
pub mod risk;
pub mod signals;
