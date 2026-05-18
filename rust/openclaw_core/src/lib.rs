//! OpenClaw Core — risk control, gate logic, state machines, calculations
//! OpenClaw 核心 — 風控、門控邏輯、狀態機、計算
//!
//! Phase R-02: perception + cognition + risk modules.
//! Phase R-03: state machines + governance cascade.
//! 階段 R-02：感知 + 認知 + 風控模組。
//! 階段 R-03：狀態機 + 治理級聯。

pub use openclaw_types;

// W-AUDIT-8a Phase A：Alpha Surface 一等公民接口契約。
pub mod alpha_surface;
// P2-DEAD-RUST-CLEANUP-1 (2026-05-18, ADR-0015)：
// attention/attribution/cognitive/dream/message_bus/order_match/opportunity
// 七個 legacy 模塊原為平行 cognition/trading 大腦設計，現確認無任何 production
// caller（grep "openclaw_core::(attention|...)" 為空，scanner::opportunity 是另一
// 個獨立模塊），依 ADR-0015 結構性退役。如需重啟某能力，請於新模塊重做。
pub mod backtest;
pub mod cost_gate;
pub mod execution;
pub mod governance_core;
// AMD-2026-05-02-01 Track H E-4 retrofit (E2 round 1 verdict HIGH-1 fix):
// Audit emit primitives extracted to keep governance_core.rs under 1500 LOC
// hard cap and decouple E1/E4 retrofit collisions on the same file.
// AMD-2026-05-02-01 Track H E-4 retrofit（E2 round 1 verdict HIGH-1 fix）：
// 將 audit emit 基礎元件抽出，使 governance_core.rs 保持在 1500 LOC hard cap
// 之下，並解耦 E1/E4 retrofit 對同檔的撞車。
pub mod governance_emit;
pub mod guardian;
pub mod h0_gate;
pub mod indicators;
pub mod klines;
// W-AUDIT-9 T6 (AMD-2026-05-09-03 §4.5): 強型別 LeaseScope enum + 為 graduated
// canary stage promotion 提供專用 LeaseScope::CanaryStagePromotion variant 與
// CanaryStageTransition row payload。
pub mod lease_scope;
pub mod portfolio;
pub mod risk;
pub mod signals;
pub mod sm;
pub mod stop_manager;

// S-04: Re-export now_ms() as crate-level utility — avoids 5+ private copies across openclaw_engine.
// S-04：將 now_ms() 重導出為 crate 級工具 — 避免 openclaw_engine 中 5+ 個私有副本。
pub use sm::now_ms;
// P-05：將 is_stale() 重導出為 crate 級工具 — 替代 4+ 處內聯過期檢查。
pub use sm::is_stale;
