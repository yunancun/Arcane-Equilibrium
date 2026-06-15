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
// P3-04 (v80 cold audit, 2026-05-29)：reserved library API — 引擎 hot path 目前
// 無 production caller（engine 不跑回測；回測屬 research / 未來 promotion 評估能
// 力）。保留為 library 契約，由 inline `#[cfg(test)] mod tests` 與整合測試
// `tests/golden_extreme.rs`（BacktestEngine / compute_sharpe / compute_max_drawdown）
// 持續行使，確保「保留而非死碼」。如要接 hot path，於新模組顯式接線。
pub mod backtest;
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
// P2-LG1-DEMO-SLO-CARVEOUT (2026-05-21, spec):
// H0 hot-path latency observability — HdrHistogram-based p50/p99/p999/max
// percentile recorder per engine_mode（paper/demo/live/live_demo/live_testnet）。
// 落實 E5 F1 audit verdict 選項 B（accept variance + SLO carve-out）。
pub mod hot_path_metrics;
pub mod indicators;
pub mod klines;
// W-AUDIT-9 T6 (AMD-2026-05-09-03 §4.5): 強型別 LeaseScope enum + 為 graduated
// canary stage promotion 提供專用 LeaseScope::CanaryStagePromotion variant 與
// CanaryStageTransition row payload。
pub mod lease_scope;
// W1-C M4 Pattern Miner Stage 1 (per docs/execution_plan/2026-05-25--m4_pattern_miner_stage_1_algorithm_spec.md):
// 自監督統計 hypothesis discovery 模組 hot-path computation — leak-free rolling
// cross-correlation + event-window analysis + Bonferroni K=2500 correction。
// Rust 端只算 statistic（pure compute，無 PG I/O）；DRAFT writeback 走 Python
// 端 helper_scripts/m4/ 寫入 learning.hypotheses 表（V100 + V103 EXTEND 6 column）。
pub mod m4_miner;
// P3-04 (v80 cold audit, 2026-05-29)：reserved library API — 引擎 hot path 目前
// 無 production caller（注意 main.rs 的 `portfolio_cache` 是另一條 health emitter
// 路徑，與 `openclaw_core::portfolio::check_portfolio_risk` 無關）。保留為
// library 契約，由 inline `#[cfg(test)] mod tests` 與整合測試
// `tests/golden_extreme.rs`（PortfolioConfig / check_portfolio_risk）持續行使，
// 確保「保留而非死碼」。如要接 hot path，於新模組顯式接線。
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
