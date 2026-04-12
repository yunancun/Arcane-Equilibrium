//! OpenClaw Core — risk control, gate logic, state machines, calculations
//! OpenClaw 核心 — 風控、門控邏輯、狀態機、計算
//!
//! Phase R-02: perception + cognition + risk modules.
//! Phase R-03: state machines + governance cascade.
//! 階段 R-02：感知 + 認知 + 風控模組。
//! 階段 R-03：狀態機 + 治理級聯。

pub use openclaw_types;

pub mod attention;
pub mod attribution;
pub mod backtest;
pub mod cognitive;
pub mod cost_gate;
pub mod dream;
pub mod execution;
pub mod governance_core;
pub mod guardian;
pub mod h0_gate;
pub mod indicators;
pub mod klines;
pub mod message_bus;
pub mod opportunity;
pub mod order_match;
pub mod portfolio;
pub mod risk;
pub mod signals;
pub mod sm;
pub mod stop_manager;

// S-04: Re-export now_ms() as crate-level utility — avoids 5+ private copies across openclaw_engine.
// S-04：將 now_ms() 重導出為 crate 級工具 — 避免 openclaw_engine 中 5+ 個私有副本。
pub use sm::now_ms;
