//! Step 0.5: H0 gate pre-check (shadow mode: observe only).
//! Step 0.5：H0 門控前置檢查（影子模式：僅觀察）。
//!
//! H0 is the <1ms local sanity layer (freshness / health / eligibility / risk
//! envelope). Hard-block → stops only early exit; shadow would-block → debug
//! log + return `h0_allowed=true`. The returned flag is threaded into Step
//! 4+5's `TickContext` so the per-strategy dispatch sees the real H0 verdict.
//!
//! H0 為 <1ms 本地合規層（新鮮度 / 健康度 / 可交易性 / 風控封套）。硬阻斷 →
//! 僅止損並早退；影子本應阻斷 → debug log 且回傳 `h0_allowed=true`。旗標透
//! 過 Step 4+5 的 `TickContext` 傳遞，逐策略分派時看得到真實 H0 裁決。

use std::ops::ControlFlow;
use std::time::Instant;

use tracing::{debug, warn};

use super::super::*;

impl TickPipeline {
    /// Execute the Step 0.5 H0 gate pre-check.
    ///
    /// Returns:
    /// - `ControlFlow::Break(record)` — H0 hard-blocked; stops were processed
    ///   and the caller returns `record` immediately.
    /// - `ControlFlow::Continue(h0_allowed)` — continue into Step 1+2 with
    ///   the real gate verdict threaded forward for Step 4+5.
    ///
    /// 執行 Step 0.5 H0 門控前置檢查。回傳：
    /// - `Break(record)`：H0 硬阻斷，止損已處理，編排器直接返回。
    /// - `Continue(h0_allowed)`：繼續下一 step，真實裁決向後傳遞。
    pub(super) fn on_tick_step_0_5_h0_gate(
        &mut self,
        event: &PriceEvent,
        tick_start: Instant,
    ) -> ControlFlow<Option<CanaryRecord>, bool> {
        let sym = &event.symbol;

        // Step 0.5: H0 Gate pre-check (shadow mode: observe only) / H0 門控前置檢查
        self.h0_gate.update_price_ts(sym, event.ts_ms);
        let h0_result = self.h0_gate.check(sym, "linear", event.ts_ms);
        let h0_allowed = h0_result.allowed;
        if !h0_result.allowed {
            // Hard block: stops only / 硬阻斷：僅處理止損
            warn!(symbol = %sym, reason = %h0_result.reason,
                "H0 BLOCKED — stops only / H0 阻斷 — 僅止損");
            // PNL-FIX-1: triggers may fire on positions whose symbol ≠ event.symbol;
            // close each at its own symbol's latest price (see fast_track block).
            // PNL-FIX-1：被觸發的倉位 symbol 可能 ≠ event.symbol，必須各自用自己的最新價平倉。
            for (sym, trigger) in &self.paper_state.check_stops(event.last_price, event.ts_ms) {
                let ectx = self
                    .paper_state
                    .get_entry_context_id(sym)
                    .unwrap_or("")
                    .to_string();
                // EXIT-FEATURES-TABLE-1: snapshot BEFORE close (full close path).
                // EXIT-FEATURES-TABLE-1：先取快照再平倉（full close 後倉位已移除）。
                let snap = self.paper_state.position_exit_snapshot(sym);
                if let Some((il, q, px, pnl)) =
                    self.close_position_at_symbol_market(sym, event.ts_ms)
                {
                    let tag = format!("stop_trigger:{}", trigger.reason);
                    self.emit_close_fill(
                        sym,
                        il,
                        q,
                        px,
                        event.ts_ms,
                        pnl,
                        &tag,
                        &ectx,
                        snap.as_ref(),
                    );
                }
                self.stats.total_stops += 1;
            }
            let dur = tick_start.elapsed().as_micros() as u64;
            return ControlFlow::Break(self.maybe_canary_record(
                event,
                None,
                vec![],
                vec![],
                dur,
            ));
        }
        if !h0_result.reason.is_empty() {
            debug!(symbol = %sym, reason = %h0_result.reason,
                "H0 shadow would-block / H0 影子模式本應阻斷");
        }

        ControlFlow::Continue(h0_allowed)
    }
}
