//! on_tick pipeline processing — the core tick-by-tick orchestration loop.
//! on_tick 管線處理 — 核心逐 tick 編排循環。
//!
//! ## 模組佈局（ON-TICK-SPLIT-1, 2026-04-21）
//!
//! 本目錄 (`tick_pipeline/on_tick/`) 於 2026-04-21 由單一 2071 行
//! `on_tick.rs` 拆出，以遵守 §七 1200 行硬上限。外部呼叫不變：
//! `TickPipeline::on_tick(event)` 維持同一簽名、同一語意、同一位元輸出；
//! `pub(crate)` helpers 透過本 `mod.rs` 的 `pub use` re-export 保持向後相容
//! （callers 仍可走 `crate::tick_pipeline::on_tick::strip_phys_lock_prefix`
//! 等路徑訪問）。
//!
//! This directory was split from a single 2071-line `on_tick.rs` on
//! 2026-04-21 to honour §七's 1200-line hard cap. External callers are
//! unchanged: `TickPipeline::on_tick(event)` keeps the same signature,
//! semantics, and byte-for-byte output; `pub(crate)` helpers are re-exported
//! via `pub use` in this `mod.rs` so callers still reach them as
//! `crate::tick_pipeline::on_tick::strip_phys_lock_prefix`, etc.
//!
//! ```text
//! tick_pipeline/on_tick/
//! ├── mod.rs                  # 編排器（本檔）: `impl TickPipeline::on_tick` 串接各 step
//! │                           # orchestrator: glues the step methods together
//! ├── step_0_fast_track.rs    # Step 0：熔斷/半倉/全平 + 熱重載
//! │                           # Step 0: fast-track halt / halve / close-all + hot-reload
//! ├── step_0_5_h0_gate.rs     # Step 0.5：H0 門控影子/硬阻斷
//! │                           # Step 0.5: H0 gate shadow / hard block
//! ├── step_1_2_klines_indicators.rs
//! │                           # Step 1+2：K 線聚合 + 指標計算 + FeatureSnapshot
//! │                           # Step 1+2: kline aggregation + indicators + FeatureSnapshot
//! ├── step_3_signals.rs       # Step 3：pause gate + boot cooldown + 信號評估/持久化
//! │                           # Step 3: pause gate + boot cooldown + signal evaluation
//! ├── step_4_5_dispatch.rs    # Step 4+5：策略分派 + 意圖處理 + maker sweep + 策略平倉
//! │                           # Step 4+5: strategy dispatch + intent + maker sweep + closes
//! ├── step_6_risk_checks.rs   # Step 6：9 項持倉風控 + halt/cooldown 派發
//! │                           # Step 6: 9-check position risk + halt / cooldown dispatch
//! └── helpers.rs              # T4 combine-layer audit wrappers + 端到端測試
//!                             # T4 combine-layer audit wrappers + end-to-end test
//! ```
//!
//! ## 借用邊界（borrow-check surface）
//!
//! 每個 step 是 `impl TickPipeline` 上的 `&mut self` 方法。Rust 的 disjoint-
//! fields NLL 只在單一函式內生效，因此 Step 4+5 的 `strategies_mut()` 迭代
//! 借用必須整塊留在 `step_4_5_dispatch.rs` 的單一方法內（不得再拆）；Step 6
//! 的 `exit_features_fn` closure 同樣必須在 `step_6_risk_checks.rs` 的單一
//! 方法內建構 + 消費，不得跨 step 傳遞。跨 step 的本地狀態（fast-track
//! pause flag、indicators、signals、intents、canary 累積…）以 **owned
//! return values** 串接，避免跨 step `&mut self` 借用衝突。
//!
//! Each step is a `&mut self` method on `impl TickPipeline`. Rust's disjoint-
//! fields NLL only applies within a single function, so the Step 4+5
//! `strategies_mut()` iterator borrow must stay entirely within the single
//! method in `step_4_5_dispatch.rs` (cannot be split further); similarly the
//! Step 6 `exit_features_fn` closure must be constructed **and** consumed
//! within the single method in `step_6_risk_checks.rs`, not passed across
//! steps. State crossing step boundaries (fast-track pause flag, indicators,
//! signals, intents, canary accumulator…) is threaded as **owned return
//! values** to sidestep cross-step `&mut self` borrow conflicts.

use super::*;
use std::ops::ControlFlow;
use std::time::Instant;

mod helpers;
mod step_0_5_h0_gate;
mod step_0_fast_track;
mod step_1_2_klines_indicators;
mod step_3_signals;
mod step_4_5_dispatch;
mod step_6_risk_checks;

// Backward-compatible re-exports: callers continue to reach these via
// `crate::tick_pipeline::on_tick::…` exactly as they did before the split.
// Keep each symbol on its own `pub use` line for diff-friendly audits.
// 向後相容 re-export：外部繼續以 `crate::tick_pipeline::on_tick::…` 訪問，
// 與拆分前一致；每個符號單獨一行以利 diff 審計。
pub(crate) use helpers::build_risk_close_tag;
pub(crate) use helpers::compute_edge_estimates_file_age_secs;
pub(crate) use helpers::emit_shadow_exit_observation;
pub(crate) use helpers::log_phys_lock_through_combine_layer;
pub(crate) use helpers::strip_phys_lock_prefix;

impl TickPipeline {
    /// Process a single price event through the full pipeline.
    /// Returns a CanaryRecord when canary_mode is enabled (R07-2).
    /// 通過完整價格事件管線處理單個價格事件。
    /// 灰度模式啟用時返回 CanaryRecord。
    ///
    /// ON-TICK-SPLIT-1 (2026-04-21): the former 1900-line body lives under
    /// `on_tick/step_*.rs`; this orchestrator threads owned state between
    /// steps and honours each step's `ControlFlow::Break` as an early return.
    /// 各 step 以 owned return 串接；`ControlFlow::Break` 即早退。
    pub fn on_tick(&mut self, event: &PriceEvent) -> Option<CanaryRecord> {
        // Start timing the tick processing / 開始計時 tick 處理
        let tick_start = Instant::now();

        // ── Step 0: fast track (flash-crash / margin-crisis / held-drop). ──
        // ── Step 0：快速通道（閃崩 / 保證金危機 / 持倉跌幅）。──
        let ft_pause_new_entries = match self.on_tick_step_0_fast_track(event, tick_start) {
            ControlFlow::Break(record) => return record,
            ControlFlow::Continue(pause) => pause,
        };

        // ── Step 0.5: H0 gate pre-check (shadow mode: observe only). ──
        // ── Step 0.5：H0 門控前置檢查（影子模式：僅觀察）。──
        let h0_allowed = match self.on_tick_step_0_5_h0_gate(event, tick_start) {
            ControlFlow::Break(record) => return record,
            ControlFlow::Continue(flag) => flag,
        };

        // ── Step 1+2: kline aggregation + indicators + FeatureSnapshot. ──
        // ── Step 1+2：K 線聚合 + 指標計算 + FeatureSnapshot。──
        let indicators = self.on_tick_step_1_2_klines_indicators(event);

        // ── Step 3: pause gate + boot cooldown + signal evaluation. ──
        // ── Step 3：暫停門控 + 啟動冷卻 + 信號評估與持久化。──
        let signals =
            match self.on_tick_step_3_signals(event, tick_start, indicators.as_ref()) {
                ControlFlow::Break(record) => return record,
                ControlFlow::Continue(sig) => sig,
            };

        // ── Step 4+5: per-strategy dispatch + intent processing + maker sweep + closes. ──
        // ── Step 4+5：逐策略分派 + 意圖處理 + maker sweep + 策略平倉。──
        let intents = match self.on_tick_step_4_5_dispatch(
            event,
            tick_start,
            indicators.as_ref(),
            &signals,
            h0_allowed,
            ft_pause_new_entries,
        ) {
            ControlFlow::Break(record) => return record,
            ControlFlow::Continue(intents) => intents,
        };

        // ── Step 6: position risk checks (9-check) + halt/cooldown dispatch. ──
        // ── Step 6：9 項持倉風控 + halt/cooldown 派發。──
        self.on_tick_step_6_risk_checks(event);

        // ── Tail: periodic stats/snapshots + final CanaryRecord emission. ──
        // ── 尾段：定期統計/快照 + 最終 CanaryRecord 發送。──
        if self.stats.total_ticks % 1000 == 0 {
            tracing::info!(
                ticks = self.stats.total_ticks,
                fills = self.stats.total_fills,
                "tick stats"
            );

            // GAP-7: FIX-29 extracted to on_tick_helpers.rs.
            self.emit_periodic_snapshots(event);
        }

        // Measure elapsed time for the full tick / 計算完整 tick 處理耗時
        let tick_duration_us = tick_start.elapsed().as_micros() as u64;
        self.maybe_canary_record(event, indicators, signals, intents, tick_duration_us)
    }
    // FIX-29: maybe_canary_record + compute_indicators moved to on_tick_helpers.rs
}
