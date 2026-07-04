// G5-09: tick_pipeline::tests sibling module aggregator.
// Original tests.rs (3524 lines, 194% over §九 1200 hard cap) split into 11
// cohesive sibling files; this mod.rs only owns shared test helpers + mod
// declarations. Pattern follows G5-07 (event_consumer/tests.rs split, commit
// 913b536) — 0 production file touched, every test fn byte-identical to the
// pre-split source.
// G5-09：tick_pipeline::tests 子模組聚合器。原 tests.rs（3524 行，超 §九 1200
// 硬上限 194%）按主題拆成 11 個 sibling；本 mod.rs 僅持共用 helpers + mod
// 宣告。樣式承襲 G5-07（event_consumer/tests.rs 拆分，commit 913b536）—
// production code 零改動，每個 test fn 字節級保留拆前內容。

use super::*;

/// Shared event factory used across every sibling. Kept in `mod.rs` so each
/// sibling can `use super::make_event;` without duplicating the helper.
/// 共用事件 factory。每個 sibling 透過 `use super::make_event;` 引用。
pub(super) fn make_event(symbol: &str, price: f64, ts: u64) -> PriceEvent {
    PriceEvent::new(symbol.to_string(), price, ts)
}

/// Shared signal factory for `should_persist_signal` / throttle tests. Pinned
/// defaults: `confidence=0.5`, `edge_bps=10.0`, `source=ma_crossover`,
/// `timeframe=1m`, `reasoning=test`.
/// 共用 signal factory（throttle / persistence 測試用）。
pub(super) fn make_signal(
    symbol: &str,
    dir: openclaw_core::signals::SignalDirection,
    ts_ms: u64,
) -> openclaw_core::signals::Signal {
    openclaw_core::signals::Signal {
        symbol: symbol.into(),
        direction: dir,
        confidence: 0.5,
        edge_bps: 10.0,
        source: "ma_crossover".into(),
        timeframe: "1m".into(),
        reasoning: "test".into(),
        ts_ms,
    }
}

mod dual_rail_dispatch;
mod emit_close_fill;
mod engine_event_snapshot;
mod exit_features;
mod fanout_canary;
mod fast_track_reduce;
// P1-4a G3-DRIFT-LANE-FIX（2026-07-04 冷審計 R2）：非 paper 路徑 FeatureSnapshot
// 發送回歸測試（features.online_latest 斷供事故）。
mod feature_snapshot_emit;
// LG1-T1（Wave 2.2，2026-05-11）：H0 Blocking Production Caller E2E integration test。
// 對應 PA tech plan `2026-05-11--lg_2_3_4_design_plan.md` §1.4。
mod h0_blocking;
mod h0_ctor_default;
// P2-LG1-DEMO-SLO-CARVEOUT（2026-05-21）：H0 latency metrics 接線 E2E integration test。
// 對應 spec `docs/execution_plan/2026-05-21--p2_lg1_demo_slo_carveout_spec.md` §10。
mod h0_latency_metrics;
// QUOTE-VOL-FIX（2026-06-15）：step_1_2 K 線聚合 per-event-kind 量/額 gating 回歸測試。
mod klines_turnover_gating;
// R1（2026-06-16）：WS-confirmed-candle 直寫持久化 + tick-synth 不再落盤回歸測試。
mod kline_confirm_persistence;
// P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19)：halt TTL 狀態機測試。
// P0-ENGINE-HALTSESSION-STUCK-FIX（2026-05-19）：halt TTL 測試。
mod halt_ttl;
mod maker_kpi_hot_reload;
mod per_symbol_price_pnl;
// P1-11（2026-07-04）：bar-close gated 1m 指標重算快取回歸測試（PERF-1 5m 半邊補全）。
mod perf1_indicators_1m_cache;
// PERF-1（2026-06-14）：bar-close gated 5m 指標重算快取回歸測試。
mod perf1_indicators_5m_cache;
mod pipeline_kind_governance;
mod resolve_close_entry_context_id;
mod risk_governance_hot_reload;
mod signal_throttle;
