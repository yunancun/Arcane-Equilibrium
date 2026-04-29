//! Step 3: pause-gate + boot-cooldown + signal evaluation / persistence.
//! Step 3：暫停門控 + 啟動冷卻 + 信號評估與持久化。
//!
//! Pause gate: `paper_paused` true → run protective stops then early-return
//! the canary record so signals and strategy dispatch are skipped.
//! Boot cooldown: first N ms after boot suppresses strategy signals (stops /
//! indicators / snapshots continue via earlier steps). Otherwise run
//! `SignalEngine::evaluate`, persist throttled, emit decision_context.
//!
//! 暫停門控：`paper_paused` true → 跑保護性止損後直接早退，跳過信號評估與策略
//! 分派。啟動冷卻：啟動後 N ms 內抑制策略信號（止損/指標/快照由先前 step 處理）。
//! 其餘情況執行 `SignalEngine::evaluate`、節流持久化、發送 decision_context。

use std::ops::ControlFlow;
use std::time::Instant;

use openclaw_core::signals::Signal;
use tracing::debug;

use super::super::on_tick_helpers::{make_context_id, make_signal_id, push_capped};
use super::super::*;

impl TickPipeline {
    /// Execute the Step 3 pause-gate / boot-cooldown / signal pipeline.
    ///
    /// Returns:
    /// - `ControlFlow::Break(record)` — `paper_paused` was set; protective
    ///   stops ran and the caller returns `record` immediately.
    /// - `ControlFlow::Continue(signals)` — continue into Step 4+5 with the
    ///   (possibly empty) evaluated signal vector.
    ///
    /// 執行 Step 3 暫停門控 / 啟動冷卻 / 信號管線。回傳：
    /// - `Break(record)`：`paper_paused` 已設，止損已處理，編排器直接返回。
    /// - `Continue(signals)`：繼續下一 step，信號向量（可能為空）向後傳遞。
    pub(super) fn on_tick_step_3_signals(
        &mut self,
        event: &PriceEvent,
        tick_start: Instant,
        indicators: Option<&IndicatorSnapshot>,
    ) -> ControlFlow<Option<CanaryRecord>, Vec<Signal>> {
        let sym = &event.symbol;

        // ── Pause gate: skip signal evaluation + strategy dispatch when paused ──
        // 暫停門控：暫停時跳過信號評估+策略分派（價格/指標/止損繼續）
        if self.paper_paused {
            // Protective stops while paused / 暫停時的保護性止損
            // PNL-FIX-1: per-symbol close price (see fast_track block).
            for (sym, trigger) in &self.paper_state.check_stops(event.last_price, event.ts_ms) {
                debug!(symbol = %sym, reason = %trigger.reason, "stop (paused)");
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
                    self.stats.total_stops += 1;
                    self.execute_position_close(sym, il, q, event, false, &tag);
                } else {
                    self.stats.total_stops += 1;
                }
            }
            let tick_duration_us = tick_start.elapsed().as_micros() as u64;
            return ControlFlow::Break(self.maybe_canary_record(
                event,
                indicators.cloned(),
                vec![],
                vec![],
                tick_duration_us,
            ));
        }

        // PNL-3: Boot cooldown — suppress strategy signals for first N ms after boot.
        // Stops/indicators/feature snapshots continue to run; only intent generation is gated.
        // PNL-3：啟動冷卻期 — 啟動後 N 毫秒內抑制策略信號（止損/指標/快照繼續）。
        let in_boot_cooldown = match self.boot_ts_ms {
            Some(boot) => event.ts_ms.saturating_sub(boot) < self.boot_cooldown_ms,
            None => false,
        };

        // Step 3: Signal evaluation
        let signals = if in_boot_cooldown {
            debug!(
                symbol = %sym,
                elapsed_ms = event.ts_ms.saturating_sub(self.boot_ts_ms.unwrap_or(event.ts_ms)),
                cooldown_ms = self.boot_cooldown_ms,
                "PNL-3 boot cooldown — signals suppressed / 啟動冷卻期 — 信號已抑制"
            );
            vec![]
        } else if let Some(ind) = indicators {
            let input = snapshot_to_input(ind);
            self.signal_engine.evaluate(sym, "1m", &input, event.ts_ms)
        } else {
            vec![]
        };

        // Store recent signals for IPC snapshot (ring buffer, max 100)
        // 存儲最近信號供 IPC 快照使用（環形緩衝，最大 100）
        // Engine mode tag for DB record IDs — prevents cross-pipeline collisions.
        // Endpoint-aware: Live + LiveDemo → "live_demo", not "live".
        // 引擎模式標記用於 DB 記錄 ID — 防止跨管線 ID 碰撞。endpoint 感知。
        let em = self.effective_engine_mode();
        let mut signals_persisted_this_tick = 0u32;
        for sig in &signals {
            push_capped(&mut self.recent_signals, sig.clone(), 100);

            // DB-RUN-1: Throttle signal persistence — only write on state change
            // or heartbeat interval. Reduces 352 rows/s to ~per-symbol-per-strat
            // change rate, expected 95%+ reduction.
            // DB-RUN-1：節流 signal 寫入 — 僅狀態變更或心跳到期時持久化。
            if !self.should_persist_signal(sig) {
                continue;
            }
            signals_persisted_this_tick += 1;

            // Phase 2a: Emit signal to trading_writer for PG persistence.
            // Signal Diamond (V015): signals are market observations — only Paper
            // writes them to avoid triple-write waste from identical signal_ids.
            // Signal Diamond（V015）：信號為市場觀察 — 僅 Paper 寫入以避免
            // 相同 signal_id 的三重寫入浪費。
            if !self.pipeline_kind.is_exchange() {
                if let Some(ref tx) = self.trading_tx {
                    crate::database::try_send_trading_msg(
                        tx,
                        crate::database::TradingMsg::Signal {
                            signal_id: make_signal_id(&sig.source, sig.ts_ms),
                            ts_ms: sig.ts_ms,
                            symbol: sig.symbol.clone(),
                            strategy_name: sig.source.clone(),
                            timeframe: sig.timeframe.clone(),
                            signal_type: format!("{:?}", sig.direction),
                            strength: sig.confidence,
                            context_id: make_context_id(em, &sig.symbol, sig.ts_ms),
                        },
                        "signal",
                    );
                }
            }
        }

        // DB-RUN-2: Decision context piggybacks on signal persistence — only emit
        // when at least one signal was actually persisted this tick. Reduces
        // 10.6M/day to ~36k/day (~99.6% drop) while preserving full fidelity at
        // every state-change / heartbeat boundary.
        // DB-RUN-2：decision_context 跟隨 signal 持久化 — 本 tick 至少 1 個 signal
        // 被寫入時才發送 context。降幅 ~99.6%，狀態變更與心跳邊界仍保留完整快照。
        if !signals.is_empty() && signals_persisted_this_tick == 0 {
            self.context_throttled += 1;
        }
        if signals_persisted_this_tick > 0 {
            if let Some(ref tx) = self.context_tx {
                // P2 refactor (2026-04-07): the LinUCB arm selection + news
                // snapshot read + DecisionContextMsg construction (~140 lines)
                // were extracted to `decision_context_producer.rs` to keep
                // tick_pipeline.rs under the §九 1200-line hard limit. The
                // logic is unchanged — see that module's MODULE_NOTE for the
                // full whitelist + fail-soft contract.
                // P2 重構（2026-04-07）：LinUCB arm 選擇 + 新聞快照讀取 +
                // DecisionContextMsg 構造（~140 行）已抽出至
                // `decision_context_producer.rs`，讓 tick_pipeline.rs 保持
                // 在 §九 1200 行硬上限以下。邏輯未變動 — 完整白名單與
                // fail-soft 合約見該模組 MODULE_NOTE。
                crate::decision_context_producer::emit_decision_context(
                    tx,
                    event,
                    &signals,
                    indicators,
                    self.paper_state.get_position(sym),
                    self.paper_state.balance(),
                    self.paper_state.drawdown_pct(),
                    self.linucb.as_ref(),
                    self.news_snapshot.as_ref(),
                    self.effective_engine_mode(),
                );
            }
        }

        ControlFlow::Continue(signals)
    }
}
