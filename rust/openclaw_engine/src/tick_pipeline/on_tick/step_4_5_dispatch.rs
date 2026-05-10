//! Step 4+5: per-strategy dispatch + intent processing + maker sweep +
//! deferred strategy closes.
//! Step 4+5：逐策略分派 + 意圖處理 + maker sweep + 延遲策略平倉。
//!
//! Largest step by far (~870 lines). **Cannot be split further** across
//! files because the `self.orchestrator.strategies_mut()` iterator borrow
//! must coexist with disjoint-field access to `self.intent_processor /
//! paper_state / recent_intents / exchange_seq / …` inside the loop body,
//! and Rust's disjoint-field NLL is only resolved within a single function.
//! Splitting the body across methods would require either clones, RefCell,
//! or reshaping `TickPipeline`'s field layout — all of which would alter
//! semantics or perf, which ON-TICK-SPLIT-1's zero-change mandate forbids.
//!
//! Step 4+5 為最大單步（~870 行）。**不可再拆** — 因為
//! `self.orchestrator.strategies_mut()` 迭代借用必須與迴圈內對
//! `self.intent_processor / paper_state / recent_intents / exchange_seq /
//! …` 的 disjoint-field 訪問共存，而 Rust 的 disjoint-field NLL 僅在單一
//! 函式內有效。跨方法拆分需要 clone / RefCell / 重塑 `TickPipeline` 欄位
//! 佈局，任一方案都會改動語意或效能，與 ON-TICK-SPLIT-1 零變更契約牴觸。

use std::ops::ControlFlow;
use std::time::Instant;

use openclaw_core::alpha_surface::AlphaSurface;
use openclaw_core::governance_core::LeaseOutcome;
use openclaw_core::signals::Signal;
use tracing::{info, warn};

use super::super::on_tick_helpers::{
    build_intent, make_context_id, make_fill_id, make_intent_id, make_order_id,
    make_strategy_signal_id, make_verdict_id, persist_intent, persist_strategy_signal,
    persist_verdict, push_capped, push_display_intent, scanner_legacy_new_open_block_reason,
    IntentScannerContext, ScannerGateAudit,
};
use super::super::pipeline_helpers::release_decision_lease_for_governance;
use super::super::*;

fn execution_reference(
    is_buy: bool,
    best_bid: Option<f64>,
    best_ask: Option<f64>,
    fallback_price: f64,
) -> (Option<f64>, Option<String>) {
    let bbo = if is_buy { best_ask } else { best_bid };
    if let Some(price) = bbo.filter(|v| v.is_finite() && *v > 0.0) {
        (Some(price), Some("bbo_same_side".to_string()))
    } else if fallback_price.is_finite() && fallback_price > 0.0 {
        (
            Some(fallback_price),
            Some("dispatch_last_fallback".to_string()),
        )
    } else {
        (None, None)
    }
}

#[allow(clippy::too_many_arguments)]
fn record_pre_risk_rejection(
    trading_tx: &Option<tokio::sync::mpsc::Sender<crate::database::TradingMsg>>,
    recent_intents: &mut std::collections::VecDeque<crate::pipeline_types::TimestampedIntent>,
    em: &str,
    ts_ms: u64,
    signal_id: &str,
    context_id: &str,
    intent: &crate::intent_processor::OrderIntent,
    price: f64,
    scanner_ctx: Option<&IntentScannerContext>,
    scanner_gate: Option<&ScannerGateAudit>,
    reason: &str,
) {
    push_display_intent(
        recent_intents,
        ts_ms,
        intent,
        Some(0.0),
        format!("rejected:{reason}"),
    );
    persist_intent(
        trading_tx,
        em,
        ts_ms,
        signal_id,
        context_id,
        intent,
        0.0,
        price,
        em,
        scanner_ctx,
        scanner_gate,
    );
    let verdict_info = crate::intent_processor::VerdictInfo::rejected(reason.to_string());
    persist_verdict(trading_tx, em, &intent.symbol, ts_ms, &verdict_info, em);
}

impl TickPipeline {
    /// Execute Step 4 (strategy dispatch) + Step 5 (intent processing with
    /// rejection / fill callbacks) + maker-sweep + deferred-close execution
    /// + strategy close callbacks.
    ///
    /// Returns:
    /// - `ControlFlow::Break(record)` — system mode blocked trading; the
    ///   caller returns `record` immediately.
    /// - `ControlFlow::Continue(intents)` — the intents emitted this tick,
    ///   handed to Step 6 and the final canary record.
    ///
    /// 執行 Step 4（策略分派）+ Step 5（意圖處理、rejection/fill 回調）+
    /// maker-sweep + 延遲平倉執行 + 策略平倉回調。回傳：
    /// - `Break(record)`：system mode 封鎖交易，編排器直接返回。
    /// - `Continue(intents)`：本 tick 發出的意圖，供 Step 6 與最終 canary 使用。
    pub(super) fn on_tick_step_4_5_dispatch(
        &mut self,
        event: &PriceEvent,
        tick_start: Instant,
        indicators: Option<&IndicatorSnapshot>,
        signals: &[Signal],
        h0_allowed: bool,
        ft_pause_new_entries: bool,
    ) -> ControlFlow<Option<CanaryRecord>, Vec<crate::intent_processor::OrderIntent>> {
        let sym = &event.symbol;
        let em = self.effective_engine_mode();

        // Step 4+5: Per-strategy dispatch + intent processing with rejection/fill callbacks (RC-04/RC-05).
        // 步驟 4+5：逐策略分派 + 意圖處理，含拒絕/成交回調。
        // P-08: Borrow instead of clone — lifetime scoped to this on_tick call.
        // P-08：借用取代克隆 — 生命週期限定在此 on_tick 調用中。
        // EDGE-P1-2: Cache funding rate from Ticker events; pass latest to strategies.
        // EDGE-P2-3 Phase 1B-4.3: also mirror the rate onto PaperState so the
        // maker router can stamp `RestingLimitOrder.funding_rate_at_submit` at
        // enqueue time (bias guard #3 input). TickPipeline's `funding_rates`
        // stays authoritative for the rest of the tick; the PaperState copy is
        // a read-only view for the router and the sweep has no further need.
        // EDGE-P1-2：緩存 Ticker 事件的資金費率；傳遞最新值給策略。
        // EDGE-P2-3 Phase 1B-4.3：同時同步到 PaperState，讓 maker router 於
        // enqueue 時打標 `RestingLimitOrder.funding_rate_at_submit`（bias #3
        // 輸入）。TickPipeline 的 `funding_rates` 仍為本 tick 權威；PaperState
        // 側僅供 router 讀取。
        if let Some(fr) = event.funding_rate {
            self.funding_rates.insert(sym.to_string(), fr);
            self.paper_state.set_latest_funding_rate(sym, fr);
        }
        // OC-5: Cache index price from Ticker events for FundingArb basis calculation.
        // OC-5：緩存 Ticker 事件的指數價格，用於 FundingArb 基差計算。
        if let Some(ip) = event.index_price {
            self.index_prices.insert(sym.to_string(), ip);
        }
        // EDGE-P2-2: Cache open interest from Ticker events. Raw value only; each
        // consuming strategy owns its own rolling window (see bb_breakout OI buffer).
        // EDGE-P2-2：緩存 Ticker 事件的 OI 原始值；滾動窗口由各策略自維護。
        if let Some(oi) = event.open_interest {
            self.open_interests.insert(sym.to_string(), oi);
        }
        let funding_rate = self.funding_rates.get(sym).copied();
        let index_price = self.index_prices.get(sym).copied();
        let open_interest = self.open_interests.get(sym).copied();

        // G7-09c Phase 1: surface BBO + tick_size to strategies so the maker
        // PostOnly path can compute a strictly passive limit_price (best_bid -
        // buffer×tick / best_ask + buffer×tick) instead of the legacy
        // `last_price ± offset_bps` which RCA `7f0e793` proved cross the
        // book 100% of the time on Bybit. `None` semantics: BBO None when WS
        // hasn't delivered orderbook (PriceEvent default = 0.0 → mapped to
        // None to match strategy fallback expectations); tick_size None when
        // instrument_cache miss.
        // G7-09c Phase 1：暴露 BBO 與 tick_size 給策略，讓 maker PostOnly 路徑
        // 算嚴格被動限價。`PriceEvent.bid_price/ask_price` 預設 0.0 視為 None，
        // 對齊策略 fallback 條件；tick_size 透過 instrument_cache 查得。
        let best_bid = if event.bid_price > 0.0 {
            Some(event.bid_price)
        } else {
            None
        };
        let best_ask = if event.ask_price > 0.0 {
            Some(event.ask_price)
        } else {
            None
        };
        let tick_size = self
            .instrument_cache
            .as_ref()
            .and_then(|c| c.get_tick_size(sym))
            .filter(|t| *t > 0.0);
        let indicators_5m = self.compute_indicators_for_timeframe(sym, "5m");

        // W-AUDIT-8a Phase A：build Tier 1 only AlphaSurface — Tier 2-4 collector
        // 留給 Phase B/C/D。surface 引用與 ctx 同生命週期，借用 `indicators` /
        // `indicators_5m`（與 `TickContext` 同源）。
        //
        // === Sprint N+1 W1 funding_curve / oi_delta_panel surface field assignment ===
        // W1 E1-α (B-1) 在 surface field 處加 `funding_curve: self.funding_slot.latest()`
        // W1 E1-β (B-2) 在 surface field 處加 `oi_delta_panel: self.oi_slot.latest()`
        //
        // === W2 btc_lead_lag surface field assignment ===
        // W2 E1-δ (C-IMPL-2) 在 surface 構造處加 paper-only engine_mode gate：
        //   let btc_lead_lag = match self.effective_engine_mode() {
        //       "paper" => self.btc_lead_lag_slot.latest(),
        //       _ => None,  // demo / live_demo / live → 永遠 None
        //   };
        //   AlphaSurface { ..tier1_only_base, btc_lead_lag, ... }
        //
        // 詳 srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md §5 Layer 1 + §7
        let alpha_surface = AlphaSurface::tier1_only(indicators, indicators_5m.as_ref());

        let ctx = TickContext {
            symbol: sym,
            price: event.last_price,
            timestamp_ms: event.ts_ms,
            indicators,
            indicators_5m: indicators_5m.as_ref(),
            signals,
            h0_allowed, // RRC-1-A1: real H0 gate result from Step 0.5
            funding_rate,
            index_price,
            open_interest,
            best_bid,
            best_ask,
            tick_size,
            alpha_surface_ref: &alpha_surface,
            // Sprint N+1 W7-1：base ctx position_state default None；真實值由 for-loop
            // 內 per-strategy iteration 從 self.paper_state.get_position(sym) 取
            // 並 Clone ctx 覆寫，避免與後續 paper_state mutable borrow 衝突。
            position_state: None,
        };

        // NOTE: Current rejection rollback assumes each strategy emits at most 1 intent per tick.
        // If a strategy ever emits >1, partial rejection + partial fill could leave inconsistent state.
        // All current strategies satisfy this constraint. Revisit if multi-intent strategies are added.
        // 注意：當前拒絕回滾假設每策略每 tick 最多發出 1 個意圖。所有當前策略滿足此約束。
        // Exchange mode = any mode that routes real orders to an exchange (Demo or Live)
        // 交易所模式 = 向交易所發送真實訂單的任何模式（Demo 或 Live）
        let is_exchange_mode = self.pipeline_kind.is_exchange();

        // System mode gate — blocks trading based on GUI-set global mode.
        // ObserveOnly/DesignOnly: no trading of any kind (scanner + market data continue).
        // ShadowOnly: only paper simulation; exchange intents suppressed.
        // DemoReserved: live engine blocked (Demo + Paper allowed).
        // LiveReserved: all engines allowed (default).
        // 系統模式門控 — 根據 GUI 設置的全局模式封鎖交易。
        {
            let block = match self.system_mode {
                SystemMode::ObserveOnly | SystemMode::DesignOnly => true,
                SystemMode::ShadowOnly if is_exchange_mode => true,
                SystemMode::DemoReserved if self.pipeline_kind == PipelineKind::Live => true,
                _ => false,
            };
            if block {
                let tick_duration_us = tick_start.elapsed().as_micros() as u64;
                return ControlFlow::Break(self.maybe_canary_record(
                    event,
                    indicators.cloned(),
                    signals.to_vec(),
                    vec![],
                    tick_duration_us,
                ));
            }
        }

        // Extract ATR for cost gate (Gate 3) / 提取 ATR 用於成本門控
        let atr_value = indicators
            .and_then(|i| i.atr_14.as_ref())
            .map(|a| a.atr)
            .unwrap_or(0.0);

        let mut intents: Vec<crate::intent_processor::OrderIntent> = Vec::new();
        let mut pending_strategy_closes: Vec<(String, String)> = Vec::new();
        // W-AUDIT-8a Phase A：disjoint-field split borrow — 同時拿到 strategies +
        // alpha dispatch / unavailable counter 的 mutable ref，hot path inline
        // 增量計數，避免 `&mut self.orchestrator` 與 `strategies_mut()` 二次借用。
        let (strategies_iter, dispatched_counter, unavailable_counter) =
            self.orchestrator.split_borrow_for_dispatch();
        for strategy in strategies_iter {
            if !strategy.is_active() {
                continue;
            }
            // W-AUDIT-8a Phase A：在 on_tick 前先 tally alpha source dispatch
            // metric，與 spec §2.5 Prometheus 計數對齊。Phase A：Tier 2-4
            // collector 未 wire 故吃 Tier 2-4 tag 的策略累積 unavailable，
            // Phase B/C/D 漸進降為 0。
            crate::orchestrator::Orchestrator::tally_alpha_sources(
                strategy.name(),
                strategy.declared_alpha_sources(),
                &alpha_surface,
                dispatched_counter,
                unavailable_counter,
            );
            // Sprint N+1 W7-1：per-strategy iteration 取 read-only position handle，
            // borrow scope 在本次 strategy.on_tick 結束即釋放，不與後續
            // paper_state.proactive_mirror_insert / apply_fill 等 mutable borrow 衝突。
            // PA #3 Option A — 解 cross-strategy position state 盲區。
            let position_state = self.paper_state.get_position(sym);
            let mut iter_ctx = ctx.clone();
            iter_ctx.position_state = position_state;
            let strategy_actions = strategy.on_tick(&iter_ctx, &alpha_surface);
            debug_assert!(
                strategy_actions.len() <= 1,
                "Strategy {} emitted {} actions in one tick — rollback assumes max 1",
                strategy.name(),
                strategy_actions.len()
            );
            for action in &strategy_actions {
                match action {
                    // ═══════════════════════════════════════════════════════════════
                    // StrategyAction::Open — full governance pipeline (unchanged)
                    // StrategyAction::Open — 完整治理管線（不變）
                    // ═══════════════════════════════════════════════════════════════
                    StrategyAction::Open(intent) => {
                        // FIX-03: fast_track ReduceToHalf/PauseNewEntries blocks new opens.
                        // FIX-03：快速通道暫停開倉時跳過所有新開倉意圖。
                        if ft_pause_new_entries {
                            tracing::debug!(
                                strategy = %strategy.name(),
                                symbol = %intent.symbol,
                                "FIX-03: new entry blocked by fast_track / 快速通道暫停開倉"
                            );
                            continue;
                        }
                        let scanner_authority_mode = self.scanner_authority_mode;
                        // SCANNER-EVIDENCE: scanner is an always-on market-context
                        // surface. Inactive-universe findings are recorded as legacy
                        // would-block evidence but never suppress the open path.
                        // scanner evidence：scanner 是常開市場 context。非 active
                        // universe 只記錄 legacy would-block evidence，不壓制 open path。
                        let mut active_universe_block_reason: Option<String> = None;
                        if let Some(ref reg) = self.symbol_registry {
                            if !reg.is_active(&intent.symbol) {
                                let reason = "scanner_active_universe:inactive".to_string();
                                tracing::debug!(
                                        strategy = %strategy.name(),
                                        symbol = %intent.symbol,
                                        authority_mode = %scanner_authority_mode.as_str(),
                                    "SCANNER-EVIDENCE: legacy inactive-universe block recorded without suppressing new entry"
                                );
                                active_universe_block_reason = Some(reason);
                            }
                        }
                        let mut scanner_ctx: Option<IntentScannerContext> =
                            self.symbol_registry.as_ref().and_then(|reg| {
                                let scan = reg.last_scan()?;
                                let candidate =
                                    scan.candidates.iter().find(|c| c.symbol == intent.symbol)?;
                                let strategy_judgment =
                                    candidate.strategy_judgments.get(intent.strategy.as_str());
                                Some(IntentScannerContext {
                                    authority_mode: scanner_authority_mode,
                                    legacy_would_block: false,
                                    legacy_block_reason: None,
                                    scan_id: scan.scan_id.clone(),
                                    best_strategy: candidate
                                        .best_strategy
                                        .as_estimate_key()
                                        .to_string(),
                                    intent_strategy: intent.strategy.clone(),
                                    market_regime: candidate.market_regime.clone(),
                                    trend_phase: candidate.trend_phase.clone(),
                                    trend_score: candidate.trend_score,
                                    range_score: candidate.range_score,
                                    shock_score: candidate.shock_score,
                                    close_alignment: candidate.close_alignment,
                                    range_position: candidate.range_position,
                                    crowding_score: candidate.crowding_score,
                                    reversal_risk_score: candidate.reversal_risk_score,
                                    directional_efficiency: candidate.de,
                                    dir_pct: candidate.dir_pct,
                                    signed_dir_pct: candidate.signed_dir_pct,
                                    range_pct: candidate.range_pct,
                                    fr_bps: candidate.fr_bps,
                                    f_ma: candidate.f_ma,
                                    f_grid: candidate.f_grid,
                                    f_bbrv: candidate.f_bbrv,
                                    f_bkout: candidate.f_bkout,
                                    f_funding_arb: candidate.f_funding_arb,
                                    edge_bps: strategy_judgment
                                        .map(|j| j.edge_bps)
                                        .unwrap_or(candidate.edge_bps),
                                    edge_n: strategy_judgment
                                        .map(|j| j.edge_n)
                                        .unwrap_or(candidate.edge_n),
                                    edge_status: strategy_judgment
                                        .map(|j| j.edge_status.clone())
                                        .unwrap_or_else(|| candidate.edge_status.clone()),
                                    route_mode: strategy_judgment
                                        .map(|j| j.route_mode.clone())
                                        .unwrap_or_else(|| candidate.route_mode.clone()),
                                    market_status: strategy_judgment
                                        .map(|j| j.market_status.clone())
                                        .unwrap_or_else(|| candidate.market_status.clone()),
                                    route_reason: strategy_judgment
                                        .map(|j| j.route_reason.clone())
                                        .unwrap_or_else(|| candidate.route_reason.clone()),
                                    opportunity: strategy_judgment
                                        .and_then(|j| j.opportunity.clone()),
                                    final_score: strategy_judgment
                                        .map(|j| j.final_score)
                                        .unwrap_or(candidate.final_score),
                                    raw_score: strategy_judgment
                                        .map(|j| j.fitness_score)
                                        .unwrap_or(candidate.raw_score),
                                })
                            });
                        let scanner_legacy_block_reason = scanner_legacy_new_open_block_reason(
                            &intent.strategy,
                            scanner_ctx.as_ref(),
                            active_universe_block_reason.as_deref(),
                            matches!(em, "demo" | "live_demo"),
                        );
                        if let Some(ref mut sctx) = scanner_ctx {
                            sctx.legacy_would_block = scanner_legacy_block_reason.is_some();
                            sctx.legacy_block_reason = scanner_legacy_block_reason.clone();
                        }
                        let scanner_gate_audit = ScannerGateAudit::new(
                            scanner_authority_mode,
                            scanner_legacy_block_reason.clone(),
                        );
                        let context_id = make_context_id(em, &intent.symbol, event.ts_ms);
                        let signal_id = make_strategy_signal_id(
                            em,
                            &intent.strategy,
                            &intent.symbol,
                            event.ts_ms,
                        );
                        persist_strategy_signal(
                            &self.trading_tx,
                            &signal_id,
                            &context_id,
                            event.ts_ms,
                            em,
                            intent,
                        );
                        if matches!(em, "demo" | "live_demo") {
                            if let Some(reason) = self
                                .intent_processor
                                .per_strategy_new_entry_rejection(intent)
                            {
                                strategy.on_rejection(intent, &reason);
                                record_pre_risk_rejection(
                                    &self.trading_tx,
                                    &mut self.recent_intents,
                                    em,
                                    event.ts_ms,
                                    &signal_id,
                                    &context_id,
                                    intent,
                                    event.last_price,
                                    scanner_ctx.as_ref(),
                                    Some(&scanner_gate_audit),
                                    &reason,
                                );

                                // W-AUDIT-4b-M3 (2026-05-09)：pre_risk reject
                                // path 寫 negative label。inline build features
                                // —— 此 path 在 exchange/paper gate 之前，尚未
                                // 構造過 features。Cost: 17 fields from already-
                                // available context, identical to下方 gate path
                                // build_feature_vector 呼叫。
                                // Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
                                //       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M3
                                let pre_risk_features =
                                    crate::edge_predictor::feature_builder::build_feature_vector(
                                        intent,
                                        event,
                                        indicators,
                                        atr_value,
                                        &self.paper_state,
                                    );
                                self.intent_processor.emit_decision_feature_intent_rejected(
                                    intent,
                                    &pre_risk_features,
                                    &context_id,
                                    event.ts_ms,
                                    &reason,
                                );

                                tracing::debug!(
                                    strategy = %intent.strategy,
                                    symbol = %intent.symbol,
                                    reason = %reason,
                                    "SCANNER-RISK-POLICY-GATE: demo/live_demo new entry blocked before risk verdict"
                                );
                                continue;
                            }
                            if let Some(reason) = scanner_legacy_block_reason.clone() {
                                tracing::debug!(
                                    strategy = %intent.strategy,
                                    symbol = %intent.symbol,
                                    reason = %reason,
                                    authority_mode = %scanner_authority_mode.as_str(),
                                    "SCANNER-EVIDENCE: legacy would-block recorded without suppressing new entry"
                                );
                            }
                        }
                        if is_exchange_mode {
                            // ═══ EXCHANGE MODE: gates only, send order to exchange ═══
                            // ═══ 交易所模式：僅過門禁，發送訂單到交易所 ═══
                            // EDGE-P3-1 A5: build FeatureVectorV1 and pass into gates-only path.
                            // Cost is cheap (17 fields from already-available context); gate is gated
                            // by `cfg.use_edge_predictor=false` in Stage 0 so features are unused until
                            // operator opts in.
                            // EDGE-P3-1 A5：組裝 feature 向量；Stage 0 由 config 默認關閉 gate。
                            let features =
                                crate::edge_predictor::feature_builder::build_feature_vector(
                                    intent,
                                    event,
                                    indicators,
                                    atr_value,
                                    &self.paper_state,
                                );
                            // P0-6 方案 A: endpoint-aware profile — LiveDemo must get
                            // Validation (moderate cost gate, cold-start allowed); only
                            // Live + Mainnet keeps Production (strict fail-closed).
                            // Inlined to avoid borrow conflict with orchestrator mutable
                            // iterator above (pipeline_kind/endpoint_env are Copy).
                            // P0-6 方案 A：endpoint 感知 profile — LiveDemo 走 Validation。
                            // 直接呼叫自由函式以避免與上方 orchestrator 可變迭代借用衝突。
                            let profile = crate::mode_state::effective_governance_profile(
                                self.pipeline_kind,
                                self.endpoint_env,
                            );
                            let gate = self.intent_processor.process_gates_only_with_features(
                                intent,
                                &self.governance,
                                &self.paper_state,
                                atr_value,
                                profile,
                                Some(&features),
                                Some(&context_id),
                                event.ts_ms,
                            );

                            // S-01: persist verdict via extracted helper
                            if let Some(ref vi) = gate.verdict_info {
                                persist_verdict(
                                    &self.trading_tx,
                                    em,
                                    &intent.symbol,
                                    event.ts_ms,
                                    vi,
                                    em,
                                );
                            }

                            if gate.approved {
                                self.exchange_seq = self.exchange_seq.wrapping_add(1);
                                let order_link_id =
                                    format!("oc_{}_{}", event.ts_ms, self.exchange_seq);

                                // Round to exchange precision / 取整至交易所精度
                                let final_qty = if let Some(ref icache) = self.instrument_cache {
                                    if let Some(spec) = icache.get(&intent.symbol) {
                                        spec.round_qty(gate.approved_qty)
                                    } else {
                                        gate.approved_qty
                                    }
                                } else {
                                    gate.approved_qty
                                };

                                // P0-2 fix: Skip if qty rounded to zero / 數量取整為零則跳過
                                if final_qty <= 0.0 {
                                    warn!(symbol = %intent.symbol, "exchange order skipped: qty=0 after rounding");
                                    continue;
                                }

                                // S-01+P-09: use helper to push display intent (M-2 post-cap qty)
                                push_display_intent(
                                    &mut self.recent_intents,
                                    event.ts_ms,
                                    intent,
                                    Some(final_qty),
                                    format!("pending_exchange:{}", order_link_id),
                                );

                                // P1-7 A INTENT-WRITE-GAP-1 fix (2026-04-18):
                                // Mirror Paper's persist_intent call (line ~986). Exchange branch
                                // previously persisted the verdict (line ~837) but never persisted
                                // the intent itself, causing trading.intents.live/live_demo = 0
                                // for 7d while 4.9M Approved verdicts accumulated. Root cause was
                                // architectural: process_gates_only_with_features() returns
                                // ExchangeGateResult (no `submitted` field), so the result.submitted
                                // guard at the paper branch was structurally unreachable here.
                                // Use final_qty (post-rounding) to match the actual qty being
                                // dispatched, paralleling Paper's use of result.approved_qty.
                                // P1-7 A INTENT-WRITE-GAP-1 修復（2026-04-18）：
                                // 對齊 Paper 分支的 persist_intent；exchange 分支原僅寫 verdict 不寫 intent，
                                // 導致 7d 內 trading.intents 對 live/live_demo 持續為 0。
                                self.stats.total_intents += 1;
                                persist_intent(
                                    &self.trading_tx,
                                    em,
                                    event.ts_ms,
                                    &signal_id,
                                    &context_id,
                                    intent,
                                    final_qty,
                                    event.last_price,
                                    em,
                                    scanner_ctx.as_ref(),
                                    Some(&scanner_gate_audit),
                                );

                                // W-AUDIT-4b-M1 split (V082)：intent-only emit
                                // 到 production learning.decision_features。
                                // 此路徑為 exchange (live/demo/live_demo) success
                                // path（gate.approved == true 後 persist_intent 之
                                // 後）。對應 trading.intents 真實 INSERT，與
                                // ML training JOIN key 1:1 對齊。
                                // Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
                                //       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
                                self.intent_processor.emit_decision_feature_intent_emitted(
                                    intent,
                                    &features,
                                    &context_id,
                                    event.ts_ms,
                                );

                                crate::agent_spine::runtime_shadow::emit_entry_lineage(
                                    self.agent_spine_tx.as_ref(),
                                    self.agent_spine_mode,
                                    crate::agent_spine::runtime_shadow::RuntimeShadowLineageInput {
                                        signal_id: &signal_id,
                                        context_id: &context_id,
                                        intent_id: &make_intent_id(em, &intent.symbol, event.ts_ms),
                                        verdict_id: &make_verdict_id(
                                            em,
                                            &intent.symbol,
                                            event.ts_ms,
                                        ),
                                        ts_ms: event.ts_ms,
                                        engine_mode: em,
                                        intent,
                                        approved_qty: final_qty,
                                        reference_price: event.last_price,
                                        verdict_info: gate.verdict_info.as_ref(),
                                        lease_id: gate.lease_id.as_deref(),
                                        order_link_id: Some(order_link_id.as_str()),
                                    },
                                );

                                // Dispatch to exchange / 派發到交易所
                                // I-08 雙軌止損：compute broker-side SL from stop config
                                let is_reducing_order = self
                                    .paper_state
                                    .get_position(&intent.symbol)
                                    .map(|p| p.is_long != intent.is_long)
                                    .unwrap_or(false);
                                let sl_pct = self.paper_state.stop_config_pct();
                                let broker_sl = if !is_reducing_order && sl_pct > 0.0 {
                                    Some(if intent.is_long {
                                        event.last_price * (1.0 - sl_pct / 100.0)
                                    } else {
                                        event.last_price * (1.0 + sl_pct / 100.0)
                                    })
                                } else {
                                    None
                                };
                                let decision_lease_id = gate.lease_id.clone();
                                if let Some(ref tx) = self.order_dispatch_tx {
                                    // F2 CROSS-SYMBOL-PRICE-CONTAMINATION-1
                                    // audit (2026-04-26): `event.last_price`
                                    // is safe here because `intent.symbol` ==
                                    // `ctx.symbol` == `event.symbol` for every
                                    // open path (verified across all 5 strategies
                                    // — bb_breakout / bb_reversion / ma_crossover
                                    // / grid_trading / funding_arb — each builds
                                    // intents with `symbol: ctx.symbol.to_string()`
                                    // inside their `on_tick(&ctx)` body). The
                                    // `debug_assert!(strategy_actions.len() <= 1)`
                                    // above plus the disjoint-borrow constraint
                                    // on `strategies_mut()` keep this invariant
                                    // single-threaded and trivially auditable.
                                    // If a future strategy ever emits an
                                    // `Open(intent)` whose `intent.symbol` differs
                                    // from `ctx.symbol`, the `debug_assert!` won't
                                    // catch it — the maintainer MUST switch this
                                    // dispatch to `paper_state.latest_price(&intent.
                                    // symbol)` with the same fallback chain as
                                    // `execute_position_close` (commands.rs:~617).
                                    // F2 跨交易對價格污染審計（2026-04-26）：此處
                                    // `event.last_price` 安全，因為 `intent.symbol`
                                    // == `ctx.symbol` == `event.symbol`（所有 5
                                    // 個策略 on_tick 內部 intent 的 symbol 都用
                                    // ctx.symbol 設置）。未來若新增策略在 Open
                                    // 動作生成跨 symbol 的 intent，必須改為
                                    // `paper_state.latest_price(&intent.symbol)`
                                    // 並對齊 execute_position_close 的 fallback。
                                    let (reference_price, reference_source) = execution_reference(
                                        intent.is_long,
                                        best_bid,
                                        best_ask,
                                        event.last_price,
                                    );
                                    let order_link_id_for_log = order_link_id.clone();
                                    let send_result = tx.send(OrderDispatchRequest {
                                        symbol: intent.symbol.clone(),
                                        is_long: intent.is_long,
                                        qty: final_qty,
                                        price: event.last_price,
                                        strategy: intent.strategy.clone(),
                                        paper_fill_ts: event.ts_ms,
                                        is_close: is_reducing_order,
                                        order_link_id,
                                        decision_lease_id: decision_lease_id.clone(),
                                        is_primary: true,
                                        stop_loss: broker_sl,
                                        take_profit: None,
                                        // FILL-CONTEXT-LINKAGE-1: carry signal-time id
                                        // so trading.fills.entry_context_id will match
                                        // learning.decision_features.context_id on the
                                        // eventual WS fill (see apply_confirmed_fill).
                                        // FILL-CONTEXT-LINKAGE-1：帶入訊號時刻 id，
                                        // 讓日後 WS 成交寫入的 entry_context_id
                                        // 與 decision_features 對齊可 JOIN。
                                        context_id: context_id.clone(),
                                        order_type: intent.order_type.clone(),
                                        limit_price: intent.limit_price,
                                        time_in_force: intent.time_in_force,
                                        // EDGE-P2-3 Phase 1B-3.2: forward maker timeout
                                        // for the PostOnly resting-order sweep.
                                        // EDGE-P2-3 Phase 1B-3.2：轉發 PostOnly sweep 逾時。
                                        maker_timeout_ms: intent.maker_timeout_ms,
                                        reference_price,
                                        reference_ts_ms: reference_price.map(|_| event.ts_ms),
                                        reference_source,
                                    });
                                    match send_result {
                                        Ok(()) => {
                                            // FUP-RACE: proactively mark true opens only.
                                            // Reducing strategy flips are reduce_only close orders
                                            // and must not insert an opposite-side mirror.
                                            if !is_reducing_order {
                                                self.paper_state.proactive_mirror_insert(
                                                    &intent.symbol,
                                                    intent.is_long,
                                                );
                                            }
                                        }
                                        Err(e) => {
                                            warn!(
                                                symbol = %intent.symbol,
                                                order_link_id = %order_link_id_for_log,
                                                error = %e,
                                                "order dispatch channel closed — releasing decision lease as failed \
                                                 / 訂單派發 channel 已關閉，決策租約標記失敗"
                                            );
                                            release_decision_lease_for_governance(
                                                &self.governance,
                                                decision_lease_id.as_deref(),
                                                LeaseOutcome::Failed,
                                                "exchange_dispatch_channel_closed",
                                            );
                                        }
                                    }
                                } else {
                                    warn!(
                                        symbol = %intent.symbol,
                                        "exchange gate approved but order dispatch channel is unavailable — releasing decision lease as failed \
                                         / exchange gate 已批准但訂單派發 channel 不可用，決策租約標記失敗"
                                    );
                                    release_decision_lease_for_governance(
                                        &self.governance,
                                        decision_lease_id.as_deref(),
                                        LeaseOutcome::Failed,
                                        "exchange_dispatch_channel_missing",
                                    );
                                }
                            } else if let Some(ref reason) = gate.rejected_reason {
                                strategy.on_rejection(intent, reason);
                                let mq = gate.verdict_info.as_ref().and_then(|vi| vi.modified_qty);
                                push_display_intent(
                                    &mut self.recent_intents,
                                    event.ts_ms,
                                    intent,
                                    mq,
                                    format!("rejected:{}", reason),
                                );

                                // W-AUDIT-4b-M3 (2026-05-09)：exchange gate reject
                                // path 寫 negative label。features 已於上方
                                // build_feature_vector 構造，context_id 已 make_*
                                // 編碼。Spec §2.5 B-M3。
                                self.intent_processor.emit_decision_feature_intent_rejected(
                                    intent,
                                    &features,
                                    &context_id,
                                    event.ts_ms,
                                    reason,
                                );
                            }
                        } else {
                            // ═══ PAPER_ONLY MODE: simulate fill locally + optional shadow order ═══
                            // ═══ 紙盤模式：本地模擬成交 + 可選影子訂單 ═══
                            // EDGE-P3-1 A5: mirror the exchange branch — build features + context_id.
                            // EDGE-P3-1 A5：與交易所分支對齊，組裝 features + context_id。
                            let features =
                                crate::edge_predictor::feature_builder::build_feature_vector(
                                    intent,
                                    event,
                                    indicators,
                                    atr_value,
                                    &self.paper_state,
                                );
                            // P0-6 方案 A: endpoint-aware profile (mirror of exchange
                            // branch). LiveDemo → Validation; Live + Mainnet → Production.
                            // Inlined free-fn call sidesteps orchestrator mutable borrow.
                            // P0-6 方案 A：endpoint 感知（與交易所分支對齊）。
                            // 直接走自由函式以避免借用衝突。
                            let profile = crate::mode_state::effective_governance_profile(
                                self.pipeline_kind,
                                self.endpoint_env,
                            );
                            let result = self.intent_processor.process_with_features(
                                intent,
                                &self.governance,
                                &self.paper_state,
                                atr_value,
                                profile,
                                Some(&features),
                                Some(&context_id),
                                event.ts_ms,
                            );

                            // S-01: persist verdict via extracted helper
                            if let Some(ref vi) = result.verdict_info {
                                persist_verdict(
                                    &self.trading_tx,
                                    em,
                                    &intent.symbol,
                                    event.ts_ms,
                                    vi,
                                    em,
                                );
                            }

                            if result.submitted {
                                self.stats.total_intents += 1;
                                let mq =
                                    result.verdict_info.as_ref().and_then(|vi| vi.modified_qty);
                                push_display_intent(
                                    &mut self.recent_intents,
                                    event.ts_ms,
                                    intent,
                                    mq,
                                    "submitted".into(),
                                );
                                // S-01: persist intent via extracted helper
                                // FUP-8 Phase 2: pass result.approved_qty (post-Kelly/P1 sizing) so
                                // paper's trading.intents.details.submitted_qty records the real sized
                                // qty instead of the 1e9 sentinel that intent.qty carries. Mirrors the
                                // exchange path at line ~643 which already passes gate.approved_qty.
                                // FUP-8 Phase 2：傳 result.approved_qty（Kelly/P1 sizing 後）
                                // 讓 paper 的 submitted_qty 記錄真實 sized qty，而非 intent.qty 攜帶的 1e9 sentinel。
                                persist_intent(
                                    &self.trading_tx,
                                    em,
                                    event.ts_ms,
                                    &signal_id,
                                    &context_id,
                                    intent,
                                    result.approved_qty,
                                    event.last_price,
                                    em,
                                    scanner_ctx.as_ref(),
                                    Some(&scanner_gate_audit),
                                );

                                // W-AUDIT-4b-M1 split (V082)：intent-only emit
                                // 到 production learning.decision_features。
                                // 此路徑為 paper success path（result.submitted）；
                                // 含 PostOnly resting 接受與 market fill 兩種，
                                // 都對應真實 intent emit 後再寫 features。
                                // Spec: docs/CCAgentWorkSpace/PA/workspace/reports/
                                //       2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M1
                                self.intent_processor.emit_decision_feature_intent_emitted(
                                    intent,
                                    &features,
                                    &context_id,
                                    event.ts_ms,
                                );

                                crate::agent_spine::runtime_shadow::emit_entry_lineage(
                                    self.agent_spine_tx.as_ref(),
                                    self.agent_spine_mode,
                                    crate::agent_spine::runtime_shadow::RuntimeShadowLineageInput {
                                        signal_id: &signal_id,
                                        context_id: &context_id,
                                        intent_id: &make_intent_id(em, &intent.symbol, event.ts_ms),
                                        verdict_id: &make_verdict_id(
                                            em,
                                            &intent.symbol,
                                            event.ts_ms,
                                        ),
                                        ts_ms: event.ts_ms,
                                        engine_mode: em,
                                        intent,
                                        approved_qty: result.approved_qty,
                                        reference_price: event.last_price,
                                        verdict_info: result.verdict_info.as_ref(),
                                        lease_id: result.lease_id.as_deref(),
                                        order_link_id: None,
                                    },
                                );

                                // EDGE-P2-3 Phase 1B-4.2: router classified
                                // PostOnly limit intent as "accepted pending".
                                // Enqueue into paper resting queue; later ticks
                                // (sweep_resting_limit_orders_for_symbol below)
                                // convert to fills when price touches/crosses
                                // the limit. fill=None here so the legacy
                                // apply_fill path is naturally skipped.
                                // EDGE-P2-3 Phase 1B-4.2：router 將 PostOnly 限價意圖
                                // 分類為「已接受、待成交」。enqueue 入紙盤掛單隊列；
                                // 後續 tick 由下方 sweep 轉為成交。此處 fill=None
                                // 自然跳過 apply_fill 路徑。
                                if let Some(draft) = result.resting_order.clone() {
                                    self.paper_state.enqueue_resting_limit_order(draft);
                                    release_decision_lease_for_governance(
                                        &self.governance,
                                        result.lease_id.as_deref(),
                                        LeaseOutcome::Consumed,
                                        "paper_resting_order_enqueued",
                                    );
                                    continue;
                                }

                                // EDGE-P2-3 Phase 1B-5: router flagged a
                                // MakerKpi Degraded fallback — count + warn.
                                // The `result.fill` branch below still runs
                                // (market fill executes normally).
                                // EDGE-P2-3 Phase 1B-5：router 標記 MakerKpi
                                // Degraded fallback — 計數 + warn。下方
                                // result.fill 分支照常執行（市價成交）。
                                if let Some(ref fb_sym) = result.maker_degraded_fallback {
                                    self.paper_state.record_maker_degraded_fallback(fb_sym);
                                    warn!(
                                        symbol = %fb_sym,
                                        strategy = %intent.strategy,
                                        "maker KPI degraded → market fallback / KPI Degraded 改走市價"
                                    );
                                }

                                if let Some(mut fill) = result.fill {
                                    if let Some(ref icache) = self.instrument_cache {
                                        if let Some(spec) = icache.get(&intent.symbol) {
                                            fill.fill_qty = spec.round_qty(fill.fill_qty);
                                            fill.fill_price = spec.round_price(fill.fill_price);
                                            // Paper min-qty fallback: if rounding reduced to 0, use min_qty
                                            // so high-priced assets (BTC/ETH) can still accumulate fill data.
                                            // Guard: min_qty notional must not exceed 10% of balance.
                                            // Paper 最小手數後備：取整為 0 時使用 min_qty，
                                            // 讓高價資產（BTC/ETH）仍能積累成交數據。
                                            // 防護：min_qty 名義值不得超過餘額的 10%。
                                            if fill.fill_qty <= 0.0 && spec.min_qty > 0.0 {
                                                let notional = spec.min_qty * fill.fill_price;
                                                let balance = self.paper_state.balance();
                                                if notional <= balance * 0.10 {
                                                    info!(symbol = %intent.symbol, min_qty = spec.min_qty,
                                                  "paper fill: qty rounded to 0, using min_qty fallback / 數量取整為 0，使用最小手數");
                                                    fill.fill_qty = spec.min_qty;
                                                }
                                            }
                                        }
                                    }
                                    // Guard: skip zero-qty fills (instrument rounding can reduce to 0)
                                    // 防護：跳過零數量成交（合約精度取整可能降為 0）
                                    if fill.fill_qty <= 0.0 {
                                        warn!(symbol = %intent.symbol, "paper fill skipped: qty=0 after rounding");
                                        release_decision_lease_for_governance(
                                            &self.governance,
                                            result.lease_id.as_deref(),
                                            LeaseOutcome::Failed,
                                            "paper_market_fill_qty_zero",
                                        );
                                        continue;
                                    }
                                    strategy.on_fill(intent, &fill);
                                    // EDGE-P3-1 R2: detect whether this fill will open a fresh position
                                    // so we can thread the entry_context_id onto it after apply_fill.
                                    // apply_fill returns non-zero realized_pnl only on CLOSE; opening
                                    // or accumulating returns 0.0. For the "open" case we need to
                                    // distinguish from accumulate — if position did not exist before,
                                    // it's an open. EDGE-P3-1 R2：區分開倉 / 加倉 / 平倉，只在開新倉時
                                    // 打上 entry_context_id（加倉保留原 entry；平倉已被清）。
                                    let was_open =
                                        self.paper_state.get_position(&intent.symbol).is_none();
                                    let realized_pnl = self.paper_state.apply_fill(
                                        &intent.symbol,
                                        intent.is_long,
                                        fill.fill_qty,
                                        fill.fill_price,
                                        fill.fee,
                                        event.ts_ms,
                                        &intent.strategy,
                                    );
                                    release_decision_lease_for_governance(
                                        &self.governance,
                                        result.lease_id.as_deref(),
                                        LeaseOutcome::Consumed,
                                        "paper_market_fill_applied",
                                    );
                                    // EDGE-P3-1 R2: stamp entry_context_id for fresh opens only.
                                    // Uses the same make_context_id signature used below for the
                                    // Fill row (same em, symbol, ts_ms → same context_id).
                                    // EDGE-P3-1 R2：僅開新倉時打 entry_context_id；加倉不覆蓋。
                                    if was_open && realized_pnl == 0.0 {
                                        self.paper_state
                                            .set_entry_context_id(&intent.symbol, &context_id);
                                    }
                                    // DYNAMIC-RISK-1: non-zero realized_pnl is a close — feed sizer.
                                    // DYNAMIC-RISK-1：realized_pnl 非零代表平倉，餵入動態風險調整器。
                                    if realized_pnl != 0.0 {
                                        self.dynamic_risk_sizer.record_closed_trade(realized_pnl);
                                    }
                                    self.stats.total_fills += 1;
                                    push_capped(
                                        &mut self.recent_fills,
                                        TimestampedFill {
                                            timestamp_ms: event.ts_ms,
                                            symbol: intent.symbol.clone(),
                                            is_long: intent.is_long,
                                            qty: fill.fill_qty,
                                            price: fill.fill_price,
                                            fee: fill.fee,
                                            realized_pnl,
                                            strategy: intent.strategy.clone(),
                                        },
                                        50,
                                    );

                                    if let Some(ref tx) = self.trading_tx {
                                        // EDGE-P3-1 R2: this on_tick.rs path is the STRATEGY OPEN path
                                        // (reached via signal → intent → apply_fill). It produces open or
                                        // accumulate fills; close fills are emitted via emit_close_fill
                                        // on the risk/strategy/fast_track paths. Leave entry_context_id
                                        // empty here — the training JOIN reads it from close-fill rows.
                                        // EDGE-P3-1 R2：此處走策略開倉路徑，不產生平倉 fill；留空即可。
                                        crate::database::try_send_trading_msg(
                                            tx,
                                            crate::database::TradingMsg::Fill {
                                                fill_id: make_fill_id(
                                                    em,
                                                    &intent.symbol,
                                                    event.ts_ms,
                                                ),
                                                ts_ms: event.ts_ms,
                                                order_id: make_order_id(
                                                    em,
                                                    &intent.symbol,
                                                    event.ts_ms,
                                                ),
                                                symbol: intent.symbol.clone(),
                                                side: if intent.is_long {
                                                    "Buy".into()
                                                } else {
                                                    "Sell".into()
                                                },
                                                qty: fill.fill_qty,
                                                price: fill.fill_price,
                                                fee: fill.fee,
                                                // FIX-FEE-POSTONLY-2 (EDGE-DIAG-2-FUP, 2026-04-28):
                                                // Strategy-open fill on the IPC-emit path was the last
                                                // remaining call site writing TIF-agnostic taker fee_rate
                                                // to trading.fills. Verified via SQL: 24h 367 demo+live_demo
                                                // entry fills had fee_rate=0.00055 (taker) for 100% of rows
                                                // even though ma_crossover implied fee bps from fee/notional
                                                // was 3.25 bps (~50% maker fills working). Switched to
                                                // fee_rate_for_intent (TIF-aware: PostOnly→maker, else
                                                // taker) so the DB column reflects the actual rate the
                                                // exchange charged. Companion to the 2026-04-23
                                                // event_consumer/loop_handlers.rs:487 fix; same pattern.
                                                // FIX-FEE-POSTONLY-2（EDGE-DIAG-2-FUP，2026-04-28）：
                                                // 策略開倉 fill 是最後一個寫 TIF-agnostic taker fee_rate
                                                // 進 trading.fills 的呼叫點。實證 24h 367 entry fills
                                                // fee_rate=0.00055 100%（taker）即便 ma_crossover 實際
                                                // implied 3.25 bps（約 50% maker）。改 fee_rate_for_intent
                                                // 對齊 loop_handlers.rs:487 的同模式修復。
                                                fee_rate: self
                                                    .intent_processor
                                                    .fee_rate_for_intent(&intent.symbol, intent),
                                                reference_price: None,
                                                reference_ts_ms: None,
                                                reference_source: None,
                                                slippage_bps: None,
                                                liquidity_role: Some("paper_sim".into()),
                                                fill_latency_ms: None,
                                                realized_pnl,
                                                strategy_name: intent.strategy.clone(),
                                                context_id: context_id.clone(),
                                                entry_context_id: String::new(),
                                                engine_mode: em.to_string(),
                                                // INFRA-PREBUILD-1 Part A: strategy open fill.
                                                // INFRA-PREBUILD-1 A 部：策略開倉 fill。
                                                exit_source: None,
                                                // V033 (2026-04-29): entry path → exit_reason None.
                                                // V033（2026-04-29）：entry path → exit_reason None。
                                                exit_reason: None,
                                            },
                                            "strategy_open_fill",
                                        );
                                    }

                                    if let Some(ref tx) = self.stop_request_tx {
                                        if let Some(pos) =
                                            self.paper_state.get_position(&intent.symbol)
                                        {
                                            let stop_pct = self.paper_state.stop_config_pct();
                                            let sl_price = if pos.is_long {
                                                pos.entry_price * (1.0 - stop_pct / 100.0)
                                            } else {
                                                pos.entry_price * (1.0 + stop_pct / 100.0)
                                            };
                                            let _ = tx.send(StopRequest {
                                                symbol: intent.symbol.clone(),
                                                stop_loss: sl_price,
                                                is_long: pos.is_long,
                                            });
                                        }
                                    }

                                    // Shadow order: mirror paper fill to Demo API
                                    if let Some(ref tx) = self.order_dispatch_tx {
                                        self.exchange_seq = self.exchange_seq.wrapping_add(1);
                                        // F2 CROSS-SYMBOL-PRICE-CONTAMINATION-1
                                        // audit (2026-04-26): `fill.fill_price`
                                        // here is the paper fill simulator's
                                        // own resolved price (paper_state.
                                        // apply_intent → resolve close price
                                        // from `latest_price(intent.symbol)`),
                                        // so by construction it belongs to
                                        // `intent.symbol`, not the outer tick.
                                        // Safe — no fallback chain needed.
                                        // F2 跨交易對價格污染審計（2026-04-26）：
                                        // `fill.fill_price` 是 paper 模擬器
                                        // 從 `latest_price(intent.symbol)`
                                        // 算出的成交價，本質就屬 intent.symbol，
                                        // 非外層 tick 的價，無需 fallback。
                                        let (reference_price, reference_source) =
                                            execution_reference(
                                                intent.is_long,
                                                best_bid,
                                                best_ask,
                                                event.last_price,
                                            );
                                        let _ = tx.send(OrderDispatchRequest {
                                            symbol: intent.symbol.clone(),
                                            is_long: intent.is_long,
                                            qty: fill.fill_qty,
                                            price: fill.fill_price,
                                            strategy: intent.strategy.clone(),
                                            paper_fill_ts: event.ts_ms,
                                            is_close: false,
                                            order_link_id: format!(
                                                "sh_{}_{}",
                                                event.ts_ms, self.exchange_seq
                                            ),
                                            decision_lease_id: None,
                                            is_primary: false,
                                            stop_loss: None,
                                            take_profit: None,
                                            // FILL-CONTEXT-LINKAGE-1: shadow orders are
                                            // fire-and-forget (no PendingOrder registered),
                                            // but pass the paper signal-time id for
                                            // consistency in case shadow path is ever
                                            // promoted to tracked.
                                            // FILL-CONTEXT-LINKAGE-1：shadow 為 fire-and-forget
                                            // 不註冊 PendingOrder；仍帶入 paper 訊號 id 以備未來追蹤。
                                            context_id: context_id.clone(),
                                            order_type: intent.order_type.clone(),
                                            limit_price: intent.limit_price,
                                            time_in_force: intent.time_in_force,
                                            // Shadow orders are fire-and-forget; sweep
                                            // never sees them (is_primary=false means no
                                            // PendingOrder registered). Forward for schema parity.
                                            // Shadow 為 fire-and-forget；is_primary=false 不註冊
                                            // PendingOrder，sweep 永不觸及。仍帶值保持結構一致。
                                            maker_timeout_ms: intent.maker_timeout_ms,
                                            reference_price,
                                            reference_ts_ms: reference_price.map(|_| event.ts_ms),
                                            reference_source,
                                        });
                                    }
                                }
                            } else if let Some(ref reason) = result.rejected_reason {
                                strategy.on_rejection(intent, reason);
                                let mq =
                                    result.verdict_info.as_ref().and_then(|vi| vi.modified_qty);
                                push_display_intent(
                                    &mut self.recent_intents,
                                    event.ts_ms,
                                    intent,
                                    mq,
                                    format!("rejected:{}", reason),
                                );

                                // W-AUDIT-4b-M3 (2026-05-09)：paper gate reject
                                // path 寫 negative label。features 已於上方
                                // build_feature_vector 構造，context_id 同源。
                                // Spec §2.5 B-M3。
                                self.intent_processor.emit_decision_feature_intent_rejected(
                                    intent,
                                    &features,
                                    &context_id,
                                    event.ts_ms,
                                    reason,
                                );
                            }
                        }
                        intents.push(intent.clone());
                    } // end StrategyAction::Open

                    // StrategyAction::Close — collected for deferred execution after strategy loop
                    // (borrow checker: strategies_mut() borrows self, can't call self methods inline)
                    // StrategyAction::Close — 收集後在策略循環結束後延遲執行
                    StrategyAction::Close {
                        symbol,
                        confidence: _,
                        reason,
                    } => {
                        pending_strategy_closes.push((symbol.clone(), reason.clone()));
                    }
                } // end match
            }
        }

        // ═══════════════════════════════════════════════════════════════════════
        // EDGE-P2-3 Phase 1B-4.2: Paper resting-order sweep — classify any
        // PostOnly limit orders in `paper_state.resting_limit_orders[event.symbol]`
        // against the current tick. True cross → 100% fill; touch → 50% fill
        // via deterministic link-id parity; deadline expired → cancel. Runs
        // only in Paper mode (exchange path has no resting queue — the exchange
        // holds the book). Sweep owns `apply_fill` internally so `on_tick` only
        // emits DB `Fill` rows + stamps entry_context_id for fresh opens.
        //
        // Strategy.on_fill is deliberately NOT called here — grid_trading reacts
        // to closes via `on_close_confirmed` at line ~1403 and inventory drift
        // is already handled at that layer. Follow-up: 1B-4.3+ may thread the
        // strategy handle through sweep if maker-specific strategies need
        // per-fill hooks (funding drag / rung replenishment).
        //
        // EDGE-P2-3 Phase 1B-4.2：紙盤掛單 sweep — 對 event.symbol 隊列的每筆
        // 掛單依當前 tick 分類。真實穿越 → 100% 成交;碰觸 → 以 link-id 奇偶性
        // 50% 成交；到期 → 取消。僅在紙盤模式執行（交易所由 Bybit 委託簿承擔）。
        // sweep 內部自行 apply_fill，on_tick 僅負責發 Fill 列與開倉打
        // entry_context_id。strategy.on_fill 刻意不在此處呼叫 — grid 透過
        // on_close_confirmed 反應已足夠；1B-4.3+ 再視需要接線。
        // ═══════════════════════════════════════════════════════════════════════
        if !is_exchange_mode {
            let maker_fee_rate = self.intent_processor.maker_fee_rate(&event.symbol);
            // EDGE-P2-3 Phase 1B-5: read the hot-reloadable funding-drag
            // threshold from the owned MakerKpiConfig snapshot (refreshed at
            // the top of this tick by `sync_maker_kpi_config_if_changed`). When
            // no ConfigStore is wired, `maker_kpi_config` stays at
            // `MakerKpiConfig::default()` so behaviour is bit-identical to the
            // pre-hot-reload commit.
            // EDGE-P2-3 Phase 1B-5：從 tick 頂部同步過的 owned `maker_kpi_config`
            // 讀 funding_drag_threshold；未接 store 時維持
            // `MakerKpiConfig::default()`，行為 bit-identical。
            let funding_drag_threshold = self.maker_kpi_config.funding_drag_threshold;
            let resting_events = self.paper_state.sweep_resting_limit_orders_for_symbol(
                &event.symbol,
                event.last_price,
                event.ts_ms,
                maker_fee_rate,
                funding_drag_threshold,
            );
            for ev in resting_events {
                match ev {
                    crate::paper_state::RestingFillEvent::Filled {
                        order,
                        fill_qty,
                        fill_price,
                        fee,
                        realized_pnl,
                        mid_price_at_fill: _,
                        true_cross: _,
                    } => {
                        self.stats.total_fills += 1;
                        // Open-path detection mirrors the line ~1108 pattern:
                        // fresh opens write `entry_context_id`; closes already
                        // cleared it via apply_fill's remove-position branch.
                        // 開倉路徑偵測與 line ~1108 一致：開新倉打
                        // entry_context_id；平倉已由 apply_fill 清除。
                        let opened_fresh = realized_pnl == 0.0
                            && self
                                .paper_state
                                .get_position(&order.symbol)
                                .map(|p| p.qty - fill_qty < 1e-12 && p.is_long == order.is_long)
                                .unwrap_or(false);
                        if opened_fresh && !order.context_id.is_empty() {
                            self.paper_state
                                .set_entry_context_id(&order.symbol, &order.context_id);
                        }
                        if realized_pnl != 0.0 {
                            self.dynamic_risk_sizer.record_closed_trade(realized_pnl);
                        }
                        push_capped(
                            &mut self.recent_fills,
                            TimestampedFill {
                                timestamp_ms: event.ts_ms,
                                symbol: order.symbol.clone(),
                                is_long: order.is_long,
                                qty: fill_qty,
                                price: fill_price,
                                fee,
                                realized_pnl,
                                strategy: order.strategy.clone(),
                            },
                            50,
                        );
                        if let Some(ref tx) = self.trading_tx {
                            crate::database::try_send_trading_msg(
                                tx,
                                crate::database::TradingMsg::Fill {
                                    fill_id: make_fill_id(em, &order.symbol, event.ts_ms),
                                    ts_ms: event.ts_ms,
                                    order_id: order.order_link_id.clone(),
                                    symbol: order.symbol.clone(),
                                    side: if order.is_long {
                                        "Buy".into()
                                    } else {
                                        "Sell".into()
                                    },
                                    qty: fill_qty,
                                    price: fill_price,
                                    fee,
                                    fee_rate: maker_fee_rate,
                                    reference_price: None,
                                    reference_ts_ms: None,
                                    reference_source: None,
                                    slippage_bps: None,
                                    liquidity_role: Some("paper_sim".into()),
                                    fill_latency_ms: None,
                                    realized_pnl,
                                    strategy_name: order.strategy.clone(),
                                    // Maker fill context = order's enqueue-time id;
                                    // entry_context_id left empty (open-path, matches
                                    // line ~1182 exchange-path convention).
                                    // Maker 成交 context = 掛單入隊 id；
                                    // entry_context_id 留空（開倉路徑）。
                                    context_id: if order.context_id.is_empty() {
                                        make_context_id(em, &order.symbol, event.ts_ms)
                                    } else {
                                        order.context_id.clone()
                                    },
                                    entry_context_id: String::new(),
                                    engine_mode: em.to_string(),
                                    // INFRA-PREBUILD-1 Part A: PostOnly maker fill (open).
                                    // INFRA-PREBUILD-1 A 部：PostOnly maker 成交（開倉）。
                                    exit_source: None,
                                    // V033 (2026-04-29): entry path (PostOnly maker open) → None.
                                    // V033（2026-04-29）：entry path（PostOnly maker 開倉）→ None。
                                    exit_reason: None,
                                },
                                "resting_maker_fill",
                            );
                        }
                    }
                    crate::paper_state::RestingFillEvent::Timedout { order } => {
                        // Timeout draining — no Fill row, just log for observability.
                        // Counter-worthy but 1B-5 owns the maker_net_edge metric.
                        // 到期 drain — 無 Fill 列，僅 log 供觀察；計數由 1B-5 接手。
                        warn!(
                            symbol = %order.symbol,
                            order_link_id = %order.order_link_id,
                            strategy = %order.strategy,
                            "paper maker timeout / 紙盤掛單到期 cancel"
                        );
                    }
                }
            }
        }

        // ═══════════════════════════════════════════════════════════════════════
        // Deferred strategy close execution — outside strategies_mut() borrow scope.
        // 延遲執行策略平倉 — 在 strategies_mut() 借用範圍之外。
        // Close reduces risk (not increases it), so Guardian/cost_gate/Kelly/P1 are skipped.
        // Retains: fee accounting, PG persistence, shadow order, Kelly stats, audit trail.
        // ═══════════════════════════════════════════════════════════════════════
        // Track confirmed/skipped closes for strategy callbacks after execution.
        // 追蹤已確認/跳過的平倉，供執行後的策略回調使用。
        let mut close_confirmed_symbols: Vec<String> = Vec::new();
        let mut close_skipped_symbols: Vec<String> = Vec::new();

        for (symbol, reason) in &pending_strategy_closes {
            // P2 fix: synthetic intent for monitoring/audit (recent_intents ring buffer).
            // S-03: use build_intent() helper — eliminates inline OrderIntent literal.
            // P2 修復：合成 intent 供監控/審計；S-03：使用 build_intent 消除內聯字面量。
            let close_intent = build_intent(
                symbol,
                false, // direction filled in below if position found
                0.0,
                0.0,
                format!("strategy_close:{reason}"),
            );
            if is_exchange_mode {
                if self.pending_close_symbols.contains(symbol) {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: pending close exists / 策略平倉跳過：已有待處理平倉");
                    push_display_intent(
                        &mut self.recent_intents,
                        event.ts_ms,
                        &close_intent,
                        None,
                        format!("close_skipped:pending_{reason}"),
                    );
                    close_skipped_symbols.push(symbol.clone());
                    continue;
                }
                if let Some(pos) = self.paper_state.get_position(symbol) {
                    let is_long = pos.is_long;
                    let qty = pos.qty;
                    info!(symbol = %symbol, is_long = %is_long, qty = %qty, reason = %reason,
                          "strategy close → exchange / 策略平倉 → 交易所");
                    let tag = format!("strategy_close:{reason}");
                    self.execute_position_close(symbol, is_long, qty, event, true, &tag);
                    push_display_intent(
                        &mut self.recent_intents,
                        event.ts_ms,
                        &close_intent,
                        None,
                        format!("close_dispatched:{reason}"),
                    );
                    close_confirmed_symbols.push(symbol.clone());
                } else {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: no position found / 策略平倉跳過：未找到倉位");
                    push_display_intent(
                        &mut self.recent_intents,
                        event.ts_ms,
                        &close_intent,
                        None,
                        format!("close_skipped:no_position_{reason}"),
                    );
                    close_skipped_symbols.push(symbol.clone());
                }
            } else {
                if let Some(pos) = self.paper_state.get_position(symbol) {
                    let is_long = pos.is_long;
                    let qty = pos.qty;
                    // EDGE-P3-1 R2: snapshot entry_context_id here (pos is &; read before close).
                    // EDGE-P3-1 R2：先行快照 entry_context_id（pos 為借用引用，關倉前讀取）。
                    let ectx = pos.entry_context_id.clone();
                    info!(symbol = %symbol, is_long = %is_long, qty = %qty, reason = %reason,
                          "strategy close (paper) / 策略平倉（紙盤）");
                    // EXIT-FEATURES-TABLE-1: snapshot BEFORE close so Track P
                    // features reflect pre-exit state.
                    // EXIT-FEATURES-TABLE-1：先取快照再平倉，Track P 反映出場前狀態。
                    let snap = self.paper_state.position_exit_snapshot(symbol);
                    // PNL-FIX-1: close at this symbol's own latest price — strategies may
                    // close cross-symbol positions (after multi-symbol position tracking),
                    // so event.last_price (current tick) is wrong when symbol ≠ event.symbol.
                    // PNL-FIX-1：策略可能跨交易對平倉，必須以該交易對自己的最新價平倉。
                    if let Some((_il, _q, close_px, pnl)) =
                        self.close_position_at_symbol_market(symbol, event.ts_ms)
                    {
                        let tag = format!("strategy_close:{reason}");
                        self.emit_close_fill(
                            symbol,
                            is_long,
                            qty,
                            close_px,
                            event.ts_ms,
                            pnl,
                            &tag,
                            &ectx,
                            snap.as_ref(),
                        );
                        // Update Kelly stats for future sizing / 更新 Kelly 統計供未來 sizing 使用
                        self.intent_processor.record_trade(symbol, pnl);
                        // Track consecutive losses for risk evaluator
                        // 追蹤連續虧損供風控評估器使用
                        if pnl < 0.0 {
                            *self.consecutive_losses.entry(symbol.clone()).or_insert(0) += 1;
                        } else {
                            self.consecutive_losses.remove(symbol);
                        }
                    }
                    // Shadow order: mirror close to Demo API / 影子訂單：鏡像平倉到 Demo API
                    let tag = format!("strategy_close:{reason}");
                    self.execute_position_close(symbol, is_long, qty, event, false, &tag);
                    push_display_intent(
                        &mut self.recent_intents,
                        event.ts_ms,
                        &close_intent,
                        None,
                        format!("close_filled:{reason}"),
                    );
                    close_confirmed_symbols.push(symbol.clone());
                } else {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: no position found / 策略平倉跳過：未找到倉位");
                    push_display_intent(
                        &mut self.recent_intents,
                        event.ts_ms,
                        &close_intent,
                        None,
                        format!("close_skipped:no_position_{reason}"),
                    );
                    close_skipped_symbols.push(symbol.clone());
                }
            }
        }

        // Notify strategies of close outcomes (P1 fix: prevents grid inventory drift on skipped close).
        // 通知策略平倉結果（P1 修復：防止 grid 庫存在跳過平倉時漂移）。
        for strategy in self.orchestrator.strategies_mut() {
            for sym in &close_confirmed_symbols {
                strategy.on_close_confirmed(sym);
            }
            for sym in &close_skipped_symbols {
                strategy.on_close_skipped(sym);
            }
        }

        ControlFlow::Continue(intents)
    }
}
