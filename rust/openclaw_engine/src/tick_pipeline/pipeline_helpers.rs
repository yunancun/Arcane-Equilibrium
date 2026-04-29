//! TickPipeline impl — close + exit features + channel setters + misc.
//! TickPipeline impl — 平倉 + 退場特徵 + 通道 setter + 雜項。
//!
//! MODULE_NOTE (EN): Split out of `tick_pipeline/mod.rs` by TICK-PIPELINE-MOD-SPLIT-1
//!   (2026-04-22) to honour CLAUDE.md §七's 1200-line hard cap. Contains the
//!   `close_position_at_symbol_market` helper (PNL-FIX-1), the `emit_close_fill`
//!   DB fill emitter + exit-feature row builder (EXIT-FEATURES-TABLE-1), the
//!   `should_persist_signal` heartbeat gate and `derive_regime` label helper,
//!   the instrument_cache / stop / shadow / market / feature / trading /
//!   context channel setters, the pending-close flag mutators, and the
//!   per-tick `retriage_synthetic_owner_for_symbol` hook (DUST-EVICTION-GAP-1).
//!   `build_exit_feature_row` stays private (sole caller is same-file
//!   `try_emit_exit_feature_row`). The other previously-private helpers
//!   invoked from `on_tick/step_*` are bumped to `pub(super)`:
//!   `close_position_at_symbol_market`, `emit_close_fill`,
//!   `should_persist_signal`, `derive_regime`.
//! MODULE_NOTE (中)：TICK-PIPELINE-MOD-SPLIT-1（2026-04-22）由 `tick_pipeline/mod.rs`
//!   拆出以遵守 CLAUDE.md §七 1200 行硬上限。本檔包含 `close_position_at_symbol_market`
//!   PNL-FIX-1 輔助、`emit_close_fill` DB fill 發射 + exit-feature row 建構（
//!   EXIT-FEATURES-TABLE-1）、`should_persist_signal` 心跳閘 + `derive_regime`
//!   標籤、instrument_cache / stop / shadow / market / feature / trading /
//!   context 通道 setter、pending-close 標記修改、以及 per-tick
//!   `retriage_synthetic_owner_for_symbol` hook（DUST-EVICTION-GAP-1）。
//!   `build_exit_feature_row` 保持 private（唯一呼叫者為同檔
//!   `try_emit_exit_feature_row`）。`on_tick/step_*` 呼叫的 helper 升為
//!   `pub(super)`：`close_position_at_symbol_market` / `emit_close_fill` /
//!   `should_persist_signal` / `derive_regime`。

use std::sync::Arc;
use tracing::{info, warn};

use crate::instrument_info::InstrumentInfoCache;

use super::{
    on_tick_helpers, parse_exit_tag, OrderDispatchRequest, StopRequest, TickPipeline,
    TimestampedFill,
};

impl TickPipeline {
    /// PNL-FIX-1: Close a single position at its OWN symbol's latest market price.
    /// Returns (is_long, qty, close_price, pnl) on success — caller passes the
    /// returned price to emit_close_fill so the fill record matches the close.
    ///
    /// Why this exists: every multi-symbol close path used to call
    /// `paper_state.close_position(sym, event.last_price, ts)`, where
    /// `event.last_price` is the price of the SINGLE tick that fired the close.
    /// When sym ≠ event.symbol (e.g. fast_track CloseAll iterating all
    /// positions on one tick) the wrong-symbol price corrupted PnL by 1000-
    /// 10000x — see the 2026-04-12 paper anomaly: $497K fake PnL from 8 fills.
    ///
    /// Falls back to the position's entry_price (zero PnL) when no latest
    /// price is recorded for the symbol — strictly safer than borrowing the
    /// triggering tick's price.
    ///
    /// PNL-FIX-1：以「該交易對自己」的最新市場價平掉單一倉位。
    /// 返回 (is_long, qty, close_price, pnl)，呼叫端把 close_price 傳給
    /// emit_close_fill 讓 fill 記錄與真實平倉一致。
    /// 無最新價時退回到 entry_price（pnl=0），絕不借用觸發 tick 的價格。
    pub(super) fn close_position_at_symbol_market(
        &mut self,
        sym: &str,
        ts_ms: u64,
    ) -> Option<(bool, f64, f64, f64)> {
        let (is_long, qty, entry_price) = self
            .paper_state
            .get_position(sym)
            .map(|p| (p.is_long, p.qty, p.entry_price))?;
        let close_price = match self.paper_state.latest_price(sym) {
            Some(p) if p.is_finite() && p > 0.0 => p,
            _ => {
                tracing::warn!(
                    symbol = %sym,
                    fallback = entry_price,
                    "PNL-FIX-1: no latest_price for symbol — falling back to entry price (zero PnL close)"
                );
                entry_price
            }
        };
        let pnl = self.paper_state.close_position(sym, close_price, ts_ms)?;
        // DYNAMIC-RISK-1: feed realized PnL into the per-engine sizer.
        // Skip the zero-pnl fallback branch (close_price == entry_price when
        // no latest price is known) so synthetic break-even values don't
        // pollute the Sharpe window. DYNAMIC-RISK-1 BUG-10 fix.
        // DYNAMIC-RISK-1：把實現 PnL 餵入 sizer；跳過 entry-price fallback
        // 產生的假零值，避免污染 Sharpe 視窗。
        if pnl != 0.0 {
            self.dynamic_risk_sizer.record_closed_trade(pnl);
        }
        Some((is_long, qty, close_price, pnl))
    }

    /// DB-RUN-3 / PNL-FIX-2: Emit a TradingMsg::Fill row for a close so
    /// trading.fills records the realized PnL **and** the real taker fee.
    /// Counter on stats.total_fills.
    ///
    /// EDGE-P2-1: `close_tag` is written directly as `strategy_name` in the DB.
    /// Callers MUST pass a prefixed tag to distinguish close sources:
    ///   - `"risk_close:{reason}"` — risk evaluator / fast-track / halt-session
    ///   - `"stop_trigger:{reason}"` — StopManager hard/trailing/time stop
    ///   - `"strategy_close:{reason}"` — strategy-driven exit
    /// This enables downstream analytics to separate risk-forced from
    /// strategy-driven exits (previously ALL closes were `risk_close:*`).
    ///
    /// EDGE-P2-1：`close_tag` 直接寫入 DB `strategy_name`。呼叫方必須傳入
    /// 帶前綴標籤（risk_close / stop_trigger / strategy_close）以區分平倉來源。
    ///
    /// PNL-FIX-2 (2026-04-12): the previous version wrote `fee: 0.0` —
    /// now we compute close_fee = qty × price × fee_rate, charge it via
    /// paper_state.charge_fee(), AND write it to DB so downstream cost
    /// analytics see the truth.
    /// EDGE-P3-1 R2: `entry_context_id` is the context_id of the entry that opened
    /// the position being closed. Pass empty string when unknown (pre-V017 restored
    /// positions, orphan adopts, tests). Typical call sites capture it via
    /// `self.paper_state.get_entry_context_id(symbol)` **before** invoking the
    /// `close_position*` helper that removes the position, then pass it here.
    /// EDGE-P3-1 R2：entry_context_id 為開此倉 entry 的 context_id。未知時空串。
    /// 典型呼叫：先 `paper_state.get_entry_context_id(symbol)` 捕獲，再關倉，再傳入。
    pub(super) fn emit_close_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        price: f64,
        ts_ms: u64,
        realized_pnl: f64,
        close_tag: &str,
        entry_context_id: &str,
        exit_snapshot: Option<&crate::paper_state::PositionExitSnapshot>,
    ) {
        // PNL-FIX-2: compute close fee from per-symbol taker rate, charge it
        // to paper_state, and record it in the DB row. Charge always happens
        // (even when trading_tx is unwired) so paper_state.balance / total_fees
        // stay consistent with the close action regardless of persistence.
        let fr = self.intent_processor.fee_rate(symbol);
        let close_fee = qty * price * fr;
        self.paper_state.charge_fee(close_fee);
        let em = self.effective_engine_mode();
        // INFRA-PREBUILD-1 Part A (2026-04-23): derive exit_source from
        // close_tag. Only PHYS-LOCK fires pass through combine_layer in
        // Phase 1a (with ml_opt=None → always Physical). Other close reasons
        // (HARD STOP / TRAILING / TIME / TP / DRAWDOWN / CONSECUTIVE LOSS /
        // DAILY LOSS / strategy exits) bypass Combine Layer entirely per
        // DUAL-TRACK-EXIT-1 design — their exit_source stays NULL.
        // Phase 2 shadow observations land in learning.decision_shadow_exits
        // (separate table); trading.fills.exit_source records only the real
        // decision actually used for the close (Phase 1a always Physical for
        // PHYS-LOCK; Phase 3+ Hybrid/ML when Track L goes live).
        //
        // Uses `strip_phys_lock_prefix` (re-exported from on_tick::helpers)
        // instead of a bare `"risk_close:phys_lock_"` literal — the
        // RUST-DOUBLE-PREFIX-1 regression guard rejects new bare literals
        // outside its allowlist (helpers.rs / risk_checks.rs /
        // step_6_risk_checks.rs). Single point of truth for PHYS-LOCK
        // recognition stays at strip_phys_lock_prefix.
        //
        // INFRA-PREBUILD-1 A 部：從 close_tag 推 exit_source。Phase 1a 只有
        // PHYS-LOCK 走 Combine Layer（ml_opt=None → 恆 Physical）。其他 close
        // reason（HARD STOP / TRAILING / TIME / TP / DRAWDOWN / CONSECUTIVE
        // LOSS / DAILY LOSS / 策略退場）依 DUAL-TRACK-EXIT-1 設計 bypass
        // Combine Layer，exit_source 保持 NULL。Phase 2 shadow 觀測寫
        // learning.decision_shadow_exits；trading.fills.exit_source 只記
        // **實際採用**的決策來源（Phase 1a PHYS-LOCK 恆 Physical；Phase 3+
        // Track L live 後才會出現 Hybrid/ML）。
        // 使用 `strip_phys_lock_prefix`（on_tick::helpers re-export）而非裸
        // `"risk_close:phys_lock_"` 字面量，避免 RUST-DOUBLE-PREFIX-1 regression
        // guard 警報；PHYS-LOCK 識別的單一事實源維持在 strip_phys_lock_prefix。
        let exit_source: Option<String> =
            if crate::tick_pipeline::on_tick::strip_phys_lock_prefix(close_tag).is_some() {
                Some("Physical".to_string())
            } else {
                None
            };
        if let Some(ref tx) = self.trading_tx {
            // Fill side reflects the closing direction (opposite of position side).
            let close_side = if is_long { "Sell" } else { "Buy" };
            crate::database::try_send_trading_msg(
                tx,
                crate::database::TradingMsg::Fill {
                    fill_id: format!("close-{em}-{}-{}", symbol, ts_ms),
                    ts_ms,
                    order_id: format!("close_{em}_{}_{}", symbol, ts_ms),
                    symbol: symbol.to_string(),
                    side: close_side.into(),
                    qty,
                    price,
                    fee: close_fee,
                    fee_rate: fr,
                    reference_price: None,
                    reference_ts_ms: None,
                    reference_source: None,
                    slippage_bps: None,
                    liquidity_role: Some("paper_sim".into()),
                    fill_latency_ms: None,
                    realized_pnl,
                    strategy_name: close_tag.to_string(),
                    context_id: on_tick_helpers::make_context_id(em, symbol, ts_ms),
                    entry_context_id: entry_context_id.to_string(),
                    engine_mode: em.to_string(),
                    exit_source,
                },
                "close_fill",
            );
        }
        self.stats.total_fills += 1;
        // Mirror the close fill into the in-memory ring buffer so GUI snapshot
        // readers see it. Without this, `recent_fills` only contained open fills
        // and every risk_close / stop_trigger / strategy_close silently bypassed
        // the buffer — DB had the data but the snapshot view was blind.
        // `is_long` is the POSITION side; the closing order is the opposite.
        // 鏡像平倉 fill 到環形緩衝供 GUI 快照讀取；否則 recent_fills 只有開倉 fill，
        // 所有 risk_close / stop_trigger / strategy_close 都悄悄繞過緩衝。
        on_tick_helpers::push_capped(
            &mut self.recent_fills,
            TimestampedFill {
                timestamp_ms: ts_ms,
                symbol: symbol.to_string(),
                is_long: !is_long,
                qty,
                price,
                fee: close_fee,
                realized_pnl,
                strategy: close_tag.to_string(),
            },
            50,
        );

        // EXIT-FEATURES-WRITER-BUG-1-FIX (2026-04-26): partial reduce paths
        // (fast_track ReduceToHalf — the only one in the current taxonomy)
        // leave the position OPEN; emitting an EF row here pollutes
        // `learning.exit_features` with labels whose `realized_net_bps`
        // reflects only the reduced portion, not the round-trip outcome.
        // MIT audit `2026-04-26--exit_features_writer_bug_audit.md` §4
        // RCA-B: 37 noise rows in 24h healthcheck window (Δ between
        // exit_features_24h and close_fills_24h). The fill row in
        // `trading.fills` is still written (operator visibility, PnL
        // accounting); only the EF writer skips. Full closes
        // (PHYS-LOCK / hard stop / trailing / time / TP / strategy exits)
        // continue to emit normally.
        // EXIT-FEATURES-WRITER-BUG-1-FIX：partial reduce 路徑（目前僅 fast_track
        // ReduceToHalf）平倉後倉位仍 open，寫 EF 會污染 ML training set；
        // MIT audit §4 RCA-B 驗證。fill 仍寫 trading.fills，只跳過 EF emit。
        if !crate::tick_pipeline::on_tick::is_partial_reduce_tag(close_tag) {
            self.try_emit_exit_feature_row(
                symbol,
                qty,
                price,
                ts_ms,
                realized_pnl,
                close_fee,
                fr,
                close_tag,
                exit_snapshot,
                entry_context_id,
            );
        }
    }

    /// EXIT-FEATURES-TABLE-1: emit one row to `learning.exit_features` per
    /// close. Requires both a captured pre-close snapshot (caller's
    /// responsibility — position is already removed by the time we run) and
    /// a wired tx. With either missing we degrade to fail-soft no-op —
    /// trading is unaffected, only Track P label collection for this close
    /// is skipped. Split out so non-`emit_close_fill` close paths
    /// (`ipc_close_symbol` paper branch, `process_external_fill`) can emit
    /// exit features without going through full Fill-persistence logic that
    /// those paths already handle themselves.
    /// EXIT-FEATURES-TABLE-1：獨立 helper，支援非 emit_close_fill 路徑
    /// （ipc_close_symbol paper 分支、process_external_fill 外部 fill 回報）
    /// 的 exit feature 發送。缺 snap 或 tx → fail-soft no-op。
    pub(crate) fn try_emit_exit_feature_row(
        &self,
        symbol: &str,
        qty: f64,
        price: f64,
        ts_ms: u64,
        realized_pnl: f64,
        close_fee: f64,
        fee_rate: f64,
        close_tag: &str,
        exit_snapshot: Option<&crate::paper_state::PositionExitSnapshot>,
        entry_context_id: &str,
    ) {
        let em = self.effective_engine_mode();
        if let (Some(snap), Some(tx)) = (exit_snapshot, self.exit_feature_tx.as_ref()) {
            let row = self.build_exit_feature_row(
                symbol,
                qty,
                price,
                ts_ms,
                realized_pnl,
                close_fee,
                fee_rate,
                close_tag,
                snap,
                em,
                entry_context_id,
            );
            // try_send: never block the close path. Overflow is explicitly
            // logged so feature-loss is visible instead of silent.
            // try_send：永不阻塞 close 路徑；溢出時顯式告警，避免靜默丟失。
            if let Err(e) = tx.try_send(row) {
                warn!(
                    symbol = %symbol,
                    close_tag = %close_tag,
                    error = %e,
                    "exit feature writer channel send failed — row not queued \
                     / exit feature writer channel 發送失敗 — row 未入隊"
                );
            }
        }
    }

    /// EXIT-FEATURES-TABLE-1: assemble one `ExitFeatureRow` from the captured
    /// position snapshot + current tick context. Pure data-shaping — no IO,
    /// no mutation beyond what `emit_close_fill` already did before calling
    /// this. Split out of `emit_close_fill` so the 7-dim math has its own test
    /// surface and the signature stays readable.
    ///
    /// Derivation summary:
    ///   est_net_bps       = edge_estimates[(owner_strategy, symbol)].shrunk_bps  (None on miss)
    ///   peak_pnl_pct      = snapshot.max_favorable_pnl_pct                       (always Some; 0.0 pre-first-tick)
    ///   atr_pct           = price_tracker.compute_atr_pct(symbol)                (None until ≥ min samples)
    ///   giveback_atr_norm = (peak_pct - current_pct) / atr_pct                   (None when atr_pct None/≤0)
    ///   time_since_peak_ms= ts_ms (i64) − peak_reached_ts_ms                     (clamped ≥ 0)
    ///   price_roc_short   = price_tracker.compute_roc(symbol, 300 ms)            (None until ≥ 2 samples in window)
    ///   entry_age_secs    = (ts_ms − entry_ts_ms) / 1000                         (None if ts_ms < entry_ts_ms)
    ///
    /// realized_net_bps = (realized_pnl / entry_notional_for_portion) × 10000
    ///                  − round_trip_fee_bps (2 × fee_rate × 10000).
    /// entry_notional_for_portion uses the portion's entry notional
    /// (`qty * entry_price`) rather than the position's aggregate accumulated
    /// `entry_notional` so partial closes report bps of the portion actually
    /// exiting.
    ///
    /// EXIT-FEATURES-TABLE-1：純資料整形，無 IO、無副作用；從 emit_close_fill
    /// 拆出以便 7 維衍生獨立測試、並保持原簽名可讀。realized_net_bps 以本段
    /// 平倉部位對應的入場 notional 計算（非聚合 entry_notional），partial close
    /// 才不會誤放大。
    fn build_exit_feature_row(
        &self,
        symbol: &str,
        qty: f64,
        close_price: f64,
        ts_ms: u64,
        realized_pnl: f64,
        close_fee: f64,
        fee_rate: f64,
        close_tag: &str,
        snap: &crate::paper_state::PositionExitSnapshot,
        engine_mode: &str,
        caller_entry_context_id: &str,
    ) -> crate::database::ExitFeatureRow {
        let ts_ms_i64 = ts_ms as i64;
        // est_net_bps — shrunk JS edge for (entry strategy, symbol). Cell miss
        // keeps it None rather than folding in grand_mean_bps: the label
        // preserves "we had no cell" as a distinct signal downstream.
        let est_net_bps = self
            .intent_processor
            .edge_estimates()
            .get_cell(&snap.owner_strategy, symbol)
            .map(|c| c.shrunk_bps as f32);

        // peak_pnl_pct — already maintained tick-by-tick on PaperPosition.
        let peak_pnl_pct = Some(snap.max_favorable_pnl_pct);

        // P0-13 Option F (2026-04-22): atr_pct now from kline 1m OHLCV +
        // Wilder's 14-period ATR to match position-life scale (~0.05-0.5%),
        // replacing per-tick micro-volatility from `compute_atr_pct`. Keep
        // close-time row and tick-time ExitFeatures on the same atr scale so
        // replay / audit / phys_lock decisions stay consistent pre/post fix.
        // P0-13 Option F（2026-04-22）：atr_pct 改用 kline 1m OHLCV +
        // Wilder's 14-period ATR 對齊持倉期尺度（~0.05-0.5%），與 tick-time
        // ExitFeatures 同源，保持 replay / audit / phys_lock 一致性。
        let atr_pct = self
            .kline_manager
            .get_ohlcv(symbol, "1m", Some(20))
            .and_then(|o| openclaw_core::indicators::atr(&o.high, &o.low, &o.close, 14))
            .map(|r| r.atr_percent as f32);

        // current_pnl_pct at exit (side-signed, in %). Used to derive the
        // normalized giveback. If entry_price was zero we'd have returned early
        // from the close path, but guard anyway so division is defensive.
        let current_pnl_pct = if snap.entry_price > 0.0 && snap.entry_price.is_finite() {
            let side = if snap.is_long { 1.0f64 } else { -1.0f64 };
            ((close_price - snap.entry_price) / snap.entry_price) * 100.0 * side
        } else {
            0.0
        };

        // giveback_atr_norm = (peak_pct − current_pct) / atr_pct. The divisor
        // is in "percent" too (atr_pct is already a percentage), so the ratio
        // is unitless. None when ATR is unavailable OR peak lies below current
        // (position exiting into a fresh high — giveback is undefined).
        let giveback_atr_norm = match atr_pct {
            Some(atr) if atr > 0.0 => {
                let peak_f64 = snap.max_favorable_pnl_pct as f64;
                let gb = peak_f64 - current_pnl_pct;
                if gb < 0.0 {
                    // Closing at/above peak — ok, but giveback is 0 not negative.
                    Some(0.0f32)
                } else {
                    Some((gb / atr as f64) as f32)
                }
            }
            _ => None,
        };

        // time_since_peak_ms: monotone ≥ 0. Legacy snapshots with
        // `peak_reached_ts_ms == 0` surface a large value until the first
        // favorable-tick refresh runs; `max(0)` prevents negative output.
        let time_since_peak_ms = if snap.peak_reached_ts_ms > 0 {
            Some((ts_ms_i64 - snap.peak_reached_ts_ms).max(0))
        } else {
            None
        };

        // 300 ms ROC — short-window momentum feature for Track P policy. None
        // until the price buffer has two samples spanning the window.
        let price_roc_short = self.price_tracker.compute_roc(symbol, 300);

        // entry_age_secs: guard against clock skew / restored snapshots whose
        // entry_ts_ms lies in the future of `ts_ms`.
        let entry_age_secs = if ts_ms >= snap.entry_ts_ms {
            Some(((ts_ms - snap.entry_ts_ms) as f32) / 1000.0)
        } else {
            None
        };

        // exit_source / exit_trigger_rule derivation. close_tag format from
        // call sites is "<prefix>:<reason>" where prefix ∈ {risk_close,
        // stop_trigger, strategy_close}. Map to canonical categories mirroring
        // the DUAL-TRACK-EXIT-1 taxonomy ("Physical" / "TimeStop" / "HardStop"
        // etc.). Unknown prefixes fall through verbatim so labels never lie.
        let (exit_source, exit_trigger_rule) = parse_exit_tag(close_tag);

        // realized_net_bps: gross bps on the portion closed, minus round-trip
        // taker fees (entry + exit at same rate). `qty * entry_price` is the
        // portion's entry notional — matches how pairer reasons and avoids
        // proration gymnastics with the aggregate `entry_notional` for partial
        // closes.
        let entry_notional_portion = qty * snap.entry_price;
        let realized_net_bps = if entry_notional_portion > 0.0 && entry_notional_portion.is_finite()
        {
            let gross_bps = (realized_pnl / entry_notional_portion) * 10_000.0;
            // Entry fee was already charged at open; close fee was charged in
            // emit_close_fill. Both are taker-rate × notional. Express in bps
            // of the entry notional for internal consistency with the edge
            // conventions (cost_gate reasons in bps of entry notional).
            let close_fee_bps = (close_fee / entry_notional_portion) * 10_000.0;
            // Entry fee is aggregate on the position; prorate by qty share.
            let entry_fee_prorated =
                if snap.qty_at_snapshot > 0.0 && snap.qty_at_snapshot.is_finite() {
                    snap.entry_fee * (qty / snap.qty_at_snapshot)
                } else {
                    // Defensive fallback: synthesize from fee_rate.
                    entry_notional_portion * fee_rate
                };
            let entry_fee_bps = (entry_fee_prorated / entry_notional_portion) * 10_000.0;
            Some((gross_bps - close_fee_bps - entry_fee_bps) as f32)
        } else {
            None
        };

        crate::database::ExitFeatureRow {
            // Precedence: caller-supplied entry_context_id (authoritative, set
            // at intent-emit time) > snapshot-stored entry_context_id (captured
            // at position open, may be empty for restored/orphan-adopted
            // positions) > synthetic `ctx-<mode>-<sym>-<ts>` fallback (PK must
            // be non-null). The synthetic branch mirrors decision_features.
            // 優先序：caller 傳入 > 快照內 > 合成 fallback。
            context_id: if !caller_entry_context_id.is_empty() {
                caller_entry_context_id.to_string()
            } else if !snap.entry_context_id.is_empty() {
                snap.entry_context_id.clone()
            } else {
                on_tick_helpers::make_context_id(engine_mode, symbol, ts_ms)
            },
            ts_ms: ts_ms_i64,
            engine_mode: engine_mode.to_string(),
            strategy_name: snap.owner_strategy.clone(),
            symbol: symbol.to_string(),
            side: if snap.is_long { 1 } else { -1 },
            est_net_bps,
            peak_pnl_pct,
            atr_pct,
            giveback_atr_norm,
            time_since_peak_ms,
            price_roc_short,
            entry_age_secs,
            exit_source: Some(exit_source),
            exit_trigger_rule: Some(exit_trigger_rule),
            realized_net_bps,
            feature_schema_version:
                crate::database::exit_feature_schema::EXIT_FEATURE_SCHEMA_VERSION.to_string(),
            feature_schema_hash: crate::database::exit_feature_schema::exit_feature_schema_hash()
                .to_string(),
        }
    }

    /// DB-RUN-1: Decide whether to persist a freshly emitted signal.
    /// Persist if (a) direction differs from last persisted for the same
    /// (symbol, strategy) key, OR (b) heartbeat interval has elapsed.
    /// Returns true on persist (and updates the dedupe map).
    /// DB-RUN-1：判斷新生成的 signal 是否應持久化（狀態變更或心跳到期）。
    pub(super) fn should_persist_signal(&mut self, sig: &openclaw_core::signals::Signal) -> bool {
        if self.signals_heartbeat_ms == 0 {
            return true;
        }
        let key = (sig.symbol.clone(), sig.source.clone());
        let now = sig.ts_ms;
        let persist = match self.last_persisted_signal.get(&key) {
            None => true,
            Some(&(prev_dir, prev_ts)) => {
                prev_dir != sig.direction
                    || now.saturating_sub(prev_ts) >= self.signals_heartbeat_ms
            }
        };
        if persist {
            self.last_persisted_signal.insert(key, (sig.direction, now));
        } else {
            self.signals_throttled += 1;
        }
        persist
    }

    /// PNL-4: Derive live regime label from indicator snapshot.
    /// Priority: Hurst regime → ADX strength fallback → "ranging" default.
    /// ADX threshold reads from RiskManagerConfig (Session 12 cleanup).
    /// PNL-4：從指標快照推導實時 regime 標籤。
    pub(super) fn derive_regime(
        &self,
        snap: Option<&openclaw_core::indicators::IndicatorSnapshot>,
    ) -> String {
        if let Some(ind) = snap {
            if let Some(ref h) = ind.hurst {
                match h.regime.as_str() {
                    "trending" => return "trending".into(),
                    "mean_reverting" => return "ranging".into(),
                    _ => {}
                }
            }
            if let Some(ref a) = ind.adx {
                let threshold = self.intent_processor.risk_config().cost_gate.adx_trending;
                if a.adx >= threshold {
                    return "trending".into();
                }
            }
        }
        "ranging".into()
    }

    /// Set instrument info cache for exchange precision rounding (R-05).
    /// 設定合約信息緩存，用於交易所精度取整。
    pub fn set_instrument_cache(&mut self, cache: Arc<InstrumentInfoCache>) {
        self.instrument_cache = Some(cache);
    }

    /// Set channel for dispatching server-side stop requests (Item 1: dual-track stops).
    /// 設定伺服器端止損請求派發通道（項目 1：雙軌止損）。
    pub fn set_stop_channel(&mut self, tx: tokio::sync::mpsc::UnboundedSender<StopRequest>) {
        self.stop_request_tx = Some(tx);
    }

    /// Set channel for dispatching orders to exchange API.
    /// 設定訂單派發通道到交易所 API。
    pub fn set_shadow_channel(
        &mut self,
        tx: tokio::sync::mpsc::UnboundedSender<OrderDispatchRequest>,
    ) {
        self.order_dispatch_tx = Some(tx);
    }

    /// EXT-1: Set trading mode (paper_only or exchange).
    // 3E-4: set_trading_mode() REMOVED — pipeline identity is immutable.
    // 3E-4：set_trading_mode() 已移除 — 管線身份不可變。

    /// EXT-1: Clear pending close flag for a symbol (called when close order is rejected/cancelled).
    /// EXT-1：清除交易對的待處理平倉標記（平倉訂單被拒/取消時調用）。
    pub fn clear_pending_close(&mut self, symbol: &str) {
        self.pending_close_symbols.remove(symbol);
    }

    /// EXT-1: Clear all pending close flags (on reset or DCP).
    /// EXT-1：清除所有待處理平倉標記（重置或 DCP 時）。
    pub fn clear_all_pending_close(&mut self) {
        self.pending_close_symbols.clear();
    }

    /// Phase 1: Set channel for dispatching market data to async PG writer.
    /// Phase 1：設定市場數據派發到異步 PG 寫入器的通道。
    pub fn set_market_data_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::MarketDataMsg>,
    ) {
        self.market_data_tx = Some(tx);
    }

    /// Phase 1: Set channel for dispatching feature snapshots to async PG writer.
    /// Phase 1：設定特徵快照派發到異步 PG 寫入器的通道。
    pub fn set_feature_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::feature_collector::FeatureSnapshot>,
    ) {
        self.feature_tx = Some(tx);
    }

    /// Phase 2a: Set channel for dispatching trading lifecycle events to PG writer.
    /// Phase 2a：設定交易生命週期事件派發通道。
    pub fn set_trading_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::TradingMsg>,
    ) {
        self.trading_tx = Some(tx);
    }

    /// Phase 2a: Set channel for dispatching decision context snapshots.
    /// Phase 2a：設定決策上下文快照派發通道。
    pub fn set_context_channel(
        &mut self,
        tx: tokio::sync::mpsc::Sender<crate::database::DecisionContextMsg>,
    ) {
        self.context_tx = Some(tx);
    }

    // 3E-4: Multi-mode infrastructure REMOVED — each pipeline is independent.
    // set_trading_mode / sync_direct_to_mode_state / load_mode_state_to_direct /
    // add_mode / get_mode_state / get_mode_state_mut / active_modes /
    // set_mode_risk_store / mode_snapshot all removed.
    // 3E-4：多模式基礎設施已移除 — 每管線獨立運行。

    // 3E-4: Multi-mode infrastructure REMOVED — each pipeline is independent.
    // 3E-4：多模式基礎設施已移除 — 每管線獨立運行。

    /// DUST-EVICTION-GAP-1 / P1-8 FUP (2026-04-17): per-tick hook called from `on_tick`.
    /// Reads instrument_cache + symbol_registry snapshot for this symbol, delegates the
    /// actual decision to `paper_state.retriage_synthetic_owner`, then (for
    /// `NeedsEviction`) dispatches `ipc_close_symbol` with 2-minute dedup.
    /// DUST-EVICTION-GAP-1 / P1-8 FUP：on_tick 的 per-tick hook。讀 instrument_cache +
    /// symbol_registry 快照，委派給 paper_state，NeedsEviction 走 ipc_close_symbol 並 2min 去重。
    pub(crate) fn retriage_synthetic_owner_for_symbol(
        &mut self,
        symbol: &str,
        tick_price: f64,
        ts_ms: u64,
    ) {
        // Symbol-registry gate: treat None (registry not wired) as "universe unknown" —
        // we can't safely promote a position to a strategy that may not evaluate this
        // symbol, so in that case behave as "not in universe" (pushes into eviction path
        // only when notional is OK). Most production paths have the registry wired; tests
        // using `with_balance` and no registry naturally exercise this fallback.
        // symbol_registry 未接時視為「universe 未知」→ 不升級；僅在名義值足夠時考慮驅逐。
        let in_universe = match self.symbol_registry.as_ref() {
            Some(reg) => reg.is_active(symbol),
            None => false,
        };

        // Look up min_notional from instrument cache. None → caller treats as "no dust gate".
        // 從 instrument cache 取 min_notional。None → 無 dust 門檻。
        let min_notional = self
            .instrument_cache
            .as_ref()
            .and_then(|ic| ic.get(symbol).map(|spec| spec.min_notional))
            .filter(|v| *v > 0.0);

        // Target strategy for promotion — KNOWN_STRATEGY_NAMES[0] (same rule as startup
        // triage adoption). Keeps behaviour consistent between boot-time and tick-time.
        // 升級目標策略 — 與啟動 triage 同規則取 KNOWN_STRATEGY_NAMES[0]。
        let target_strategy = crate::position_reconciler::orphan_handler::KNOWN_STRATEGY_NAMES
            .first()
            .copied()
            .unwrap_or("");

        let outcome = self.paper_state.retriage_synthetic_owner(
            symbol,
            tick_price,
            in_universe,
            target_strategy,
            min_notional,
        );

        match outcome {
            crate::paper_state::RetriageOutcome::NoOp => {}
            crate::paper_state::RetriageOutcome::FrozenAsDust {
                est_notional,
                min_notional: minn,
                was_downgraded,
            } => {
                // Only log on first downgrade — subsequent ticks on the same frozen
                // symbol would spam otherwise.
                // 僅在首次降級時記錄，避免重複 tick 轟炸日誌。
                if was_downgraded {
                    warn!(
                        symbol,
                        est_notional,
                        min_notional = minn,
                        "DUST-EVICTION-GAP-1 retriage: position frozen as dust (notional \
                         below exchange minimum) / 重分流：持倉降級為 dust"
                    );
                }
            }
            crate::paper_state::RetriageOutcome::Promoted {
                from,
                to,
                est_notional,
            } => {
                info!(
                    symbol,
                    from = %from,
                    to = %to,
                    est_notional,
                    "DUST-EVICTION-GAP-1 retriage: synthetic owner promoted to real strategy \
                     / 重分流：synthetic 擁有者升級為實策略"
                );
                // Also clear any lingering dedup entry so a subsequent re-freeze + evict
                // flip isn't rate-limited by a stale timestamp.
                // 升級後清除 dedup 時間戳，避免後續 re-freeze+evict 被舊戳節流。
                self.retriage_last_evict_ms.remove(symbol);
            }
            crate::paper_state::RetriageOutcome::NeedsEviction {
                is_long,
                qty,
                est_notional,
            } => {
                // 2-minute dedup — matches ORPHAN_CLOSE_DEDUP_MS cadence in orphan_handler.
                // 2 分鐘去重，與 orphan_handler 的 ORPHAN_CLOSE_DEDUP_MS 一致。
                const RETRIAGE_EVICT_DEDUP_MS: u64 =
                    crate::position_reconciler::orphan_handler::ORPHAN_CLOSE_DEDUP_MS;
                let last = self
                    .retriage_last_evict_ms
                    .get(symbol)
                    .copied()
                    .unwrap_or(0);
                if ts_ms.saturating_sub(last) < RETRIAGE_EVICT_DEDUP_MS {
                    return;
                }
                warn!(
                    symbol,
                    is_long,
                    qty,
                    est_notional,
                    "DUST-EVICTION-GAP-1 retriage: synthetic-owner position not in universe, \
                     dispatching close / 重分流：synthetic 持倉不在 universe，派平倉"
                );
                self.retriage_last_evict_ms
                    .insert(symbol.to_string(), ts_ms);
                self.ipc_close_symbol(symbol, Some(is_long), Some(qty));
            }
        }
    }

    /// G7-03 Phase B: apply per-symbol hysteresis-stabilized regime label to
    /// a freshly-computed `IndicatorSnapshot`. Bypassed entirely when
    /// `risk_store=None` or `risk.hurst.enabled=false` so Phase A behaviour
    /// (instantaneous regime string from `compute_indicators`) is preserved
    /// bit-identical for the dormant default config.
    ///
    /// When enabled:
    ///   1. Pull the latest `n = window_size` 1m closes via `kline_manager`.
    ///   2. Compute raw Hurst via `regime::compute_hurst` (R/S analysis).
    ///   3. Lazy-init a per-symbol `HysteresisDetector` from the live config.
    ///   4. `push(h)` → stabilized `RegimeLabel`.
    ///   5. Overwrite `indicators.hurst.regime` with `label.as_legacy_str()`
    ///      so legacy strategy comparison sites (`h.regime == "trending"`)
    ///      pick up the *stabilized* label without needing per-strategy
    ///      detector ownership.
    ///
    /// Fail-safe behaviour (any of these → no-op, regime untouched):
    ///   * risk_store wiring absent (tests / standalone harness)
    ///   * `hurst.enabled = false` (default — Phase A bit-identical)
    ///   * 1m kline buffer too short for `compute_hurst` window
    ///   * `compute_hurst` returns None (degenerate / NaN / inf)
    ///   * `indicators.hurst` is None (core hurst failed → don't fabricate)
    ///
    /// Note: detectors live as long as the pipeline; they are not pruned on
    /// universe shrinkage. At ~25-100 active symbols × ~6 lag * 1 f64 each,
    /// the cache footprint is negligible (<5 KB).
    ///
    /// G7-03 Phase B：對剛算好的 `IndicatorSnapshot` 套用 per-symbol 滯回穩定標籤。
    /// 當 `risk_store=None` 或 `hurst.enabled=false` 時整段 bypass，與 Phase A
    /// bit-identical（dormant 預設）。啟用時用 `kline_manager.get_ohlcv("1m",N)`
    /// 取最新 1m closes → `compute_hurst` 算原始 H → 懶分配 per-symbol
    /// `HysteresisDetector` → `push(h)` 取穩定標籤 → 覆寫 `indicators.hurst.regime`，
    /// 讓 legacy 策略比較點（`h.regime == "trending"`）自動拿到穩定後標籤，
    /// 無須各策略自持 detector。
    pub(super) fn apply_hurst_regime_label_for(
        &mut self,
        symbol: &str,
        indicators: &mut openclaw_core::indicators::IndicatorSnapshot,
    ) {
        // ── Bypass gate: dormant when risk_store unwired or hurst disabled ──
        // 旁路門控：risk_store 未接線或 hurst.enabled=false 即 no-op。
        let risk_store = match &self.risk_store {
            Some(s) => s,
            None => return,
        };
        let snapshot = risk_store.load();
        let cfg = &snapshot.hurst;
        if !cfg.enabled {
            return;
        }

        // Need a freshly-computed `hurst` slot to overwrite. If `compute_indicators`
        // returned None for hurst (degenerate window / cold start), don't fabricate.
        // 必須先有 compute_indicators 寫入的 hurst 槽位才覆寫；core 為 None 時不偽造。
        let h_result = match indicators.hurst.as_mut() {
            Some(h) => h,
            None => return,
        };

        // Pull 1m closes from kline_manager. `compute_hurst` requires
        // `len >= min_window * 4`; if the symbol has fewer 1m bars yet we
        // bail and leave the instantaneous label intact (cold-start safe).
        // 取 1m closes；不足時 bail 保留瞬時標籤（冷啟動安全）。
        let closes = match self
            .kline_manager
            .get_ohlcv(symbol, "1m", Some(cfg.window_size))
        {
            Some(o) => o.close,
            None => return,
        };

        let max_window = cfg.window_size / 2;
        let h_value = match crate::regime::compute_hurst(&closes, cfg.min_window(), max_window) {
            Some(h) => h,
            None => return,
        };

        // Lazy-init detector from live config snapshot. If config thresholds /
        // lag changed between ticks, the existing detector keeps its history
        // and old thresholds — this matches the "config snapshot at first
        // observation" semantic; operator restarts engine to fully re-seed.
        // (Acceptable: hurst.enabled is the dormant-by-default flip flag, not
        // a hot threshold knob.)
        // 懶分配 detector；config 中途變動不重設既有 detector（restart 才完整重種）。
        let detector = self
            .hurst_detectors
            .entry(symbol.to_string())
            .or_insert_with(|| crate::regime::HysteresisDetector::from_config(cfg));

        let label = detector.push(h_value);

        // Overwrite legacy regime string with stabilized label. The numeric
        // `hurst` value is left untouched (it is the raw R/S estimate, not a
        // function of the hysteresis filter).
        // 覆寫 legacy regime 字串為穩定標籤；數值 `hurst` 保持為原始 R/S 估計。
        h_result.regime = label.as_legacy_str().to_string();
    }
}
