//! Step 6: position risk checks (9-check RRC-1-C2) + halt / cooldown dispatch.
//! Step 6：9 項持倉風控檢查（RRC-1-C2）+ halt / cooldown 派發。
//!
//! Per-position math (pnl_pct / peak_pnl_pct / holding_hours / cost_ratio +
//! `check_position_on_tick`) is delegated to
//! `position_risk_evaluator::evaluate_positions`. Decision-vs-mechanism
//! split: that module computes WHAT to do (pure), the dispatch loop below
//! executes the side-effects (close / halt / cooldown). Behaviour preserved
//! because the original code already snapshotted positions into a Vec before
//! dispatching, so reading-then-acting in two phases is identical to the
//! inline form.
//!
//! 逐倉計算抽出至 `position_risk_evaluator::evaluate_positions`；派發迴圈
//! 仍負責所有副作用。行為與原始碼一致（原碼本就先快照後派發，兩階段等價於
//! 內聯）。
//!
//! ## T4 builder closure borrow shape
//!
//! The `exit_features_fn` closure captures three immutable sub-borrows of
//! `self` (`paper_state`, `price_tracker`, `intent_processor.edge_estimates`)
//! which coexist with the already-live `&risk_config`. The closure is
//! consumed by `evaluate_positions` and its borrows end before the side-
//! effectful `risk_closed_symbols` dispatch loop below. This pattern MUST
//! stay inside a single method — splitting `risk_config` and the closure
//! capture across functions would force clones or RefCell, both disallowed
//! under ON-TICK-SPLIT-1's zero-change mandate.
//!
//! Closure 捕獲 self 的三個 immutable sub-borrow，與既有 `&risk_config` 共
//! 存；於 `evaluate_positions` 返回後借用結束，派發迴圈才執行 side-effect。
//! 此借用型態必須整塊留在單一方法內（跨方法拆分需要 clone / RefCell，與
//! ON-TICK-SPLIT-1 零變更契約牴觸）。

use tracing::{info, warn};

use super::super::*;
use crate::risk_checks::RiskAction;

impl TickPipeline {
    /// Execute Step 6: position risk checks + halt / cooldown dispatch +
    /// external-close callbacks.
    ///
    /// No return value and no early exit — mutates `self` in place. Strategy
    /// external-close notifications are emitted at the end of the method so
    /// `strategies_mut()` is only borrowed once the `risk_closed_symbols`
    /// vector is stable.
    ///
    /// 執行 Step 6：持倉風控 + halt/cooldown 派發 + 策略外部平倉回調。無返回
    /// 值、無早退；`strategies_mut()` 借用延至 `risk_closed_symbols` 穩定後。
    pub(super) fn on_tick_step_6_risk_checks(&mut self, event: &PriceEvent) {
        // Step 6: Position risk checks — 9-check (RRC-1-C2, replaces basic check_stops).
        // 步驟 6：持倉風控 9 項檢查（RRC-1-C2，替代基本止損）。
        //
        // P2 refactor (2026-04-07): per-position math (pnl_pct / peak_pnl_pct /
        // holding_hours / cost_ratio + check_position_on_tick) extracted to
        // `position_risk_evaluator::evaluate_positions`. Decision-vs-mechanism
        // split: that module computes WHAT to do (pure), the dispatch loop
        // below executes the side-effects (close / halt / cooldown). Behavior
        // preserved because the original code already snapshotted positions
        // into a Vec before dispatching, so reading-then-acting in two phases
        // is identical to the inline form.
        // P2 重構（2026-04-07）：逐倉計算抽出至 position_risk_evaluator；
        // 派發迴圈仍負責所有副作用，行為與原始碼一致。
        // EXIT-FEATURES-TABLE-1: pass wall-clock ts so `peak_reached_ts_ms`
        // advances whenever max_favorable_pnl_pct records a new high. Legacy
        // `update_best_prices()` (ts=0) leaves peak timestamps stuck.
        // EXIT-FEATURES-TABLE-1：傳入 tick 時戳，讓 peak_reached_ts_ms 在新高
        // 時同步推進；舊 update_best_prices() 等同 ts=0，peak 戳不動。
        self.paper_state.update_best_prices_at(event.ts_ms as i64);
        let session_drawdown = self.paper_state.drawdown_pct();
        let daily_loss = self
            .intent_processor
            .daily_loss_pct_pub(self.paper_state.balance());
        // FIX-32: borrow instead of deep-cloning RiskConfig per tick.
        let risk_config = self.intent_processor.risk_config();
        // INFRA-PREBUILD-1 Part A: snapshot shadow_enabled to an owned bool
        // up-front so the `risk_config` immutable borrow doesn't have to
        // survive into the `decisions` for-loop's match arms (which need
        // mutable `self` for execute_position_close / emit_close_fill etc.).
        // NLL would still extend the borrow through the match arm otherwise.
        // INFRA-PREBUILD-1 A 部：先將 shadow_enabled 取為 owned bool，
        // 避免 risk_config 借用延到 for-loop match arm 內（arm 需 mutable self 做
        // execute_position_close 等），NLL 否則會延長借用造成衝突。
        let shadow_enabled: bool = risk_config.exit.shadow_enabled;
        let position_rows: Vec<crate::position_risk_evaluator::PositionRow> = self
            .paper_state
            .positions()
            .iter()
            .map(|p| {
                let current_price = self
                    .latest_prices
                    .get(&p.symbol)
                    .copied()
                    .unwrap_or(p.entry_price);
                // P0-13 Option F (2026-04-22): atr_pct now sourced from kline
                // 1m OHLCV + Wilder's 14-period ATR (via
                // `openclaw_core::indicators::volatility::atr`) instead of
                // `PriceHistoryTracker::compute_atr_pct` which returned per-tick
                // micro-volatility (~0.001-0.006% scale) and broke position-life
                // semantics for both `compute_dynamic_stop_pct` (never exceeded
                // base stop) and `physical_micro_profit_lock_v2` Gate 3/4a
                // (giveback inflated 100-1000x). Kline ATR gives ~0.05-0.5%
                // scale matching trader intuition and ExitConfig seed values.
                // Cold-start 15 min after restart returns None (< 15 bars) →
                // downstream Gates Hold conservatively (same as previous None).
                // P0-13 Option F（2026-04-22）：atr_pct 改用 kline 1m OHLCV +
                // Wilder's 14-period ATR，取代 per-tick micro-volatility 的
                // compute_atr_pct（~0.001-0.006% 尺度）；新來源 ~0.05-0.5%
                // 吻合交易員直覺與 ExitConfig seed。Cold-start 首 15 min 返
                // None（< 15 bars），下游 Gates 保守 Hold 與原行為一致。
                let atr_pct = self
                    .kline_manager
                    .get_ohlcv(&p.symbol, "1m", Some(20))
                    .and_then(|o| openclaw_core::indicators::atr(&o.high, &o.low, &o.close, 14))
                    .map(|r| r.atr_percent);
                crate::position_risk_evaluator::PositionRow {
                    symbol: p.symbol.clone(),
                    is_long: p.is_long,
                    qty: p.qty,
                    entry_price: p.entry_price,
                    entry_ts_ms: p.entry_ts_ms,
                    peak_price: p.best_price,
                    current_price,
                    atr_pct,
                    fee_rate: self.intent_processor.fee_rate(&p.symbol),
                    regime: self.derive_regime(self.latest_indicators.get(&p.symbol)),
                    consecutive_losses: self
                        .consecutive_losses
                        .get(&p.symbol)
                        .copied()
                        .unwrap_or(0),
                }
            })
            .collect();
        // ARCH-RC1 1C-2-B: live read from BudgetConfig store (falls back to
        // defaults in tests where store is not wired).
        // MICRO-PROFIT-FIX-1 (2026-04-17): add matching live read for
        // min_profit_to_close_pct so the narrow lock-in band is applied on every tick.
        // ARCH-RC1 1C-2-B：即時從 BudgetConfig store 讀取；未接線時回退 default。
        // MICRO-PROFIT-FIX-1：同步讀取 min_profit_to_close_pct，實現窄帶觸發。
        let cost_edge_max_ratio = self.current_cost_edge_max_ratio();
        let min_profit_to_close_pct = self.current_min_profit_to_close_pct();
        // DUAL-TRACK-EXIT-1 Track P **T4 wiring** (2026-04-21 · TRACK-P-T4-WIRING-1):
        // real ExitFeatures builder replaces the former `|_| None` placeholder.
        // Per live position we look up (a) the mid-life `PositionExitSnapshot`
        // from `paper_state`, (b) short-horizon ROC (300 ms) from
        // `price_tracker` — ATR% is already on the row, (c) the JS-shrunk edge
        // estimate for `(owner_strategy, symbol)` from the intent-processor
        // cache. Any miss → `Option::None` → Priority-6 4-Gate responds with a
        // conservative Hold (pre-T3 semantics preserved as the degenerate case).
        //
        // Borrow split: closure captures only immutable sub-borrows of `self`
        // (paper_state / price_tracker / edge_estimates), which coexist with
        // the already-live `&risk_config` (= `&self.intent_processor.risk_config()`).
        // The closure is consumed by `evaluate_positions` and its borrows end
        // before the side-effectful `risk_closed_symbols` dispatch loop.
        //
        // Before T4: Priority 6 PHYS-LOCK was inert in production (0 fires
        // over the full decision_outcomes history; see
        // `memory/project_track_p_runtime_dead.md`). With T4 in place the
        // 4-Gate lock runs every tick and can trigger
        // `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg`.
        //
        // DUAL-TRACK-EXIT-1 Track P **T4 接線**（2026-04-21 · TRACK-P-T4-WIRING-1）：
        // 以實際 ExitFeatures 建構器取代舊 `|_| None` 佔位。逐倉查
        // (a) `paper_state` 即時快照、(b) `price_tracker.compute_roc(300ms)`、
        // (c) intent_processor 邊際估計快取；任一缺失 → None → Priority 6
        // 4-Gate 保守 Hold。Closure 僅捕獲 self 的 immutable sub-borrow，
        // 與既有 `&risk_config` 共存；借用於 evaluate_positions 返回後結束。
        // T4 接線前 Priority 6 生產 0 次觸發（見 memory/project_track_p_runtime_dead.md）。
        let paper_state_ref = &self.paper_state;
        let price_tracker_ref = &self.price_tracker;
        let edge_estimates_ref = self.intent_processor.edge_estimates();
        let tick_ts_ms = event.ts_ms;
        let exit_features_fn =
            |row: &crate::position_risk_evaluator::PositionRow|
                -> Option<crate::exit_features::ExitFeatures> {
                // Mid-life snapshot (not pre-close). Skip (None → Hold) when
                // the position has vanished between row collection and here —
                // e.g. racing IPC close on the same tick batch.
                // 即時快照（非 pre-close）；position 在收集與此處之間被移除
                // （例：同 tick IPC 先行 close）→ None → 下游 Hold。
                let snap = paper_state_ref.position_exit_snapshot(&row.symbol)?;
                let price_roc_short = price_tracker_ref.compute_roc(&row.symbol, 300);
                let est_net_bps = edge_estimates_ref
                    .get_cell(&snap.owner_strategy, &row.symbol)
                    .map(|c| c.shrunk_bps as f32);
                Some(crate::exit_features::build_exit_features_for_tick(
                    &snap,
                    row.current_price,
                    row.atr_pct,
                    price_roc_short,
                    est_net_bps,
                    tick_ts_ms,
                ))
            };
        let decisions = crate::position_risk_evaluator::evaluate_positions(
            &position_rows,
            daily_loss,
            session_drawdown,
            event.ts_ms,
            cost_edge_max_ratio,
            min_profit_to_close_pct,
            exit_features_fn,
            &risk_config,
        );

        let is_exchange_mode = self.pipeline_kind.is_exchange();
        let mut risk_closed_symbols: Vec<String> = Vec::new();
        for decision in &decisions {
            let symbol = &decision.symbol;
            let is_long = &decision.is_long;
            let qty = &decision.qty;
            let pnl_pct = &decision.pnl_pct;
            let _entry_ts_ms = &decision.entry_ts_ms;
            match decision.action.clone() {
                RiskAction::Hold => {} // no action / 無動作
                RiskAction::ClosePosition(reason) => {
                    // DUAL-TRACK-EXIT-1 T4: route PHYS-LOCK closes through the Combine Layer
                    // so exit_source is recorded. Phase 1a passes ml_opt=None →
                    // combine_exit_decision always returns (Lock, Physical). This is a
                    // pure audit-side wrapper; the existing close path proceeds unchanged.
                    // Non-PHYS-LOCK reasons (HARD STOP / TAKE PROFIT / TRAILING / TIME STOP /
                    // COST EDGE pre-T3) are not part of the dual-track exit scope and
                    // bypass the combine layer (they are P0 hard-stops, not physical-lock
                    // optimisations).
                    // TODO(T5 audit): persist exit_source tag into fills.details once
                    // schema field plumbing lands.
                    // DUAL-TRACK-EXIT-1 T4：PHYS-LOCK 平倉經 Combine Layer 記錄 exit_source。
                    // Phase 1a 傳 ml_opt=None → 永遠 (Lock, Physical)；純審計層包裝，
                    // 現有平倉路徑不變。非 PHYS-LOCK（HARD STOP 等 P0 硬止損）不走 combine layer。
                    // T4-FIX（2026-04-19）：prefix 由 `PHYS-LOCK` 對齊為 T3 實際輸出的
                    // `risk_close:phys_lock_` (risk_checks.rs:242 `format!("risk_close:{}", reason)`)。
                    // 之前 prefix 不匹配導致 combine_layer 在生產 0 次被呼叫，459 LOC + 9 tests 死碼。
                    // 同時 debug_assert_eq! → assert_eq!，release build 也留下不變式 runtime 防線。
                    // TODO(T5 audit)：等 fills.details 欄位 plumbing 到位後持久化 exit_source。
                    // T4-FIX (2026-04-19): prefix aligned from `PHYS-LOCK` to the T3-actual
                    // `risk_close:phys_lock_` (risk_checks.rs:242). Previously mismatched →
                    // combine_layer called 0× in prod, 459 LOC + 9 tests dead.
                    // Also promote debug_assert_eq! → assert_eq! so the invariant holds in
                    // release builds.
                    //
                    // RUST-DOUBLE-PREFIX-1 (2026-04-23): defensive prefix normalisation.
                    // `risk_checks.rs:247` already emits PHYS-LOCK reasons with a
                    // `risk_close:` envelope (so `strip_phys_lock_prefix` at line 236
                    // below can recognise them as PHYS-LOCK). Other reasons
                    // (HARD STOP / TRAILING / TIME / TAKE PROFIT / DRAWDOWN / CONSECUTIVE
                    // LOSS / DAILY LOSS) come through bare. Previously we unconditionally
                    // wrapped each with `format!("risk_close:{reason}")` → PHYS-LOCK rows
                    // landed in `trading.fills.strategy_name` as
                    // `"risk_close:risk_close:phys_lock_gate4_giveback"` (double prefix),
                    // which broke `trading.fills.strategy_name LIKE 'risk_close:phys_lock_%'`
                    // style queries and the healthcheck [4] pattern. We fix it defensively
                    // at the single outbound emission site: if `reason` already starts
                    // with `risk_close:`, treat the whole thing as the tag; otherwise wrap.
                    // This is the Option (B) fix from TODO §RUST-DOUBLE-PREFIX-1 —
                    // chosen over (A) because `strip_phys_lock_prefix` and its helpers-test
                    // still depend on the PHYS-LOCK reason having an explicit
                    // `risk_close:phys_lock_` prefix (see `on_tick/helpers.rs:30-44`).
                    //
                    // RUST-DOUBLE-PREFIX-1（2026-04-23）：防禦性 prefix 正規化。
                    // `risk_checks.rs:247` 的 PHYS-LOCK 分支已經加過一次 `risk_close:`
                    // 前綴（讓下方 line 236 的 `strip_phys_lock_prefix` 能識別為
                    // PHYS-LOCK）。其他 reason（HARD STOP / TRAILING / TIME / TP /
                    // DRAWDOWN / CONSECUTIVE LOSS / DAILY LOSS）則沒加。原本這裡對所有
                    // reason 無條件 `format!("risk_close:{reason}")` → PHYS-LOCK 進入
                    // `trading.fills.strategy_name` 變成
                    // `"risk_close:risk_close:phys_lock_gate4_giveback"`（雙前綴），
                    // 打爆 `LIKE 'risk_close:phys_lock_%'` 查詢 + healthcheck [4]。
                    // 此處採 TODO §RUST-DOUBLE-PREFIX-1 選項 (B)：單一 emission 點防禦性
                    // 檢查 reason 是否已含 `risk_close:`，已含則直接用；未含則 wrap。
                    // 不選 (A) 的理由：strip_phys_lock_prefix + 既有 helpers test 仍依賴
                    // PHYS-LOCK reason 帶顯式 `risk_close:phys_lock_` 前綴
                    // （見 on_tick/helpers.rs:30-44）。
                    let close_tag: String = super::build_risk_close_tag(&reason);
                    if let Some(lock_tag) = super::strip_phys_lock_prefix(&reason) {
                        // EDGE-DIAG-1（2026-04-23）：每次 PHYS-LOCK fire 重查 paper_state
                        // owner_strategy + edge_estimates cell，把「Gate 1 是經 cell 還是
                        // 經 fallback 通過」的證據附在 INFO log。pre-close snapshot 仍存
                        // （close 排在 log 之後）。Closed mid-tick 的罕見競態 → owner=
                        // "<closed>"、est=None。
                        // EDGE-DIAG-1: re-query paper_state and edge_estimates at fire
                        // time so the INFO log records *why* Gate 1 was bypassed (cell
                        // hit vs fallback). Pre-close snapshot is still live; rare
                        // mid-tick close race → owner="<closed>", est=None.
                        let (owner_strategy, est_net_bps) = self
                            .paper_state
                            .position_exit_snapshot(symbol)
                            .map(|snap| {
                                let est = self
                                    .intent_processor
                                    .edge_estimates()
                                    .get_cell(&snap.owner_strategy, symbol)
                                    .map(|c| c.shrunk_bps as f32);
                                (snap.owner_strategy.clone(), est)
                            })
                            .unwrap_or_else(|| (String::from("<closed>"), None));
                        super::log_phys_lock_through_combine_layer(
                            symbol,
                            &reason,
                            lock_tag,
                            &owner_strategy,
                            est_net_bps,
                        );

                        // INFRA-PREBUILD-1 Part A (2026-04-23): Combine Layer
                        // shadow observation. Dormant by default — runs only
                        // when `ExitConfig.shadow_enabled=true` AND the writer
                        // channel is wired. Zero emits in Phase 1a.
                        // All borrows are copied/cloned into owned locals so
                        // the subsequent mutable `self` calls in this match
                        // arm (execute_position_close / close_position_at_
                        // symbol_market / emit_close_fill / record_trade) stay
                        // borrow-clean — matches the T4 wiring closure pattern.
                        // INFRA-PREBUILD-1 A 部：Combine Layer shadow 觀測。預設
                        // dormant — 僅當 ExitConfig.shadow_enabled=true 且 writer
                        // 通道已接線時 fire。所有借用先 copy/clone 為 owned local，
                        // 讓後續 match arm 內 mutable self 呼叫保持 borrow-clean。
                        if shadow_enabled {
                            let tx_opt = self.shadow_exit_tx().cloned();
                            if let Some(tx) = tx_opt {
                                // Snapshot + engine_mode captured as owned to
                                // drop the `&self.paper_state` immediate borrow
                                // before emit runs. `effective_engine_mode()`
                                // returns &'static str so no borrow lifetime.
                                // 快照與 engine_mode 先抓為 owned，emit 前 drop
                                // `&self.paper_state` 借用；engine_mode 為 &'static。
                                let engine_mode = self.effective_engine_mode();
                                let snap_opt = self.paper_state.position_exit_snapshot(symbol);
                                if let Some(snap) = snap_opt {
                                    let side_i16: i16 = if snap.is_long { 1 } else { -1 };
                                    // INFRA-PREBUILD-1 L1-1 (2026-04-23):
                                    // compute real cell age from
                                    // `settings/edge_estimates*.json` file mtime
                                    // so Phase 2's 7d stale gate can fire when
                                    // the Python writer stalls. Resolves
                                    // `OPENCLAW_BASE_DIR` at call time (cheap
                                    // env var read); missing var falls back to
                                    // CWD — same precedence as
                                    // `event_consumer::mod.rs` edge loader so
                                    // writer-side and reader-side agree.
                                    // INFRA-PREBUILD-1 L1-1（2026-04-23）：從
                                    // `settings/edge_estimates*.json` 檔案
                                    // mtime 計算真實 cell 齡期，讓 Phase 2
                                    // 7d stale gate 在 Python writer 停寫時
                                    // 能 fire。env 解析與 event_consumer 同
                                    // 優先序，讀寫兩端對齊。
                                    let base_dir = std::env::var("OPENCLAW_BASE_DIR")
                                        .map(std::path::PathBuf::from)
                                        .unwrap_or_else(|_| {
                                            std::env::current_dir()
                                                .unwrap_or_else(|_| std::path::PathBuf::from("."))
                                        });
                                    let cell_age_secs = super::compute_edge_estimates_file_age_secs(
                                        engine_mode,
                                        &base_dir,
                                    );
                                    super::emit_shadow_exit_observation(
                                        &snap.entry_context_id,
                                        event.ts_ms as i64,
                                        engine_mode,
                                        &snap.owner_strategy,
                                        symbol,
                                        side_i16,
                                        lock_tag,
                                        est_net_bps,
                                        cell_age_secs,
                                        &tx,
                                    );
                                }
                            }
                        }
                    }

                    risk_closed_symbols.push(symbol.clone());
                    if is_exchange_mode {
                        if self.pending_close_symbols.contains(symbol) {
                            continue;
                        }
                        warn!(symbol = %symbol, reason = %reason, "risk close → exchange / 風控平倉 → 交易所");
                        // RUST-DOUBLE-PREFIX-1: use pre-computed `close_tag` (single
                        // `risk_close:` prefix). See comment block above.
                        // RUST-DOUBLE-PREFIX-1：使用上方已計算好的 `close_tag`（單前綴）。
                        self.execute_position_close(
                            symbol, *is_long, *qty, event, true, &close_tag,
                        );
                    } else {
                        warn!(symbol = %symbol, reason = %reason, "risk close (paper) / 風控平倉（紙盤）");
                        if *pnl_pct < 0.0 {
                            *self.consecutive_losses.entry(symbol.clone()).or_insert(0) += 1;
                        } else {
                            self.consecutive_losses.remove(symbol);
                        }
                        // PNL-FIX-1: risk evaluator can act on cross-symbol positions —
                        // close at this symbol's own latest price, not event.last_price.
                        // PNL-FIX-1：風控評估器可作用於跨交易對倉位，必須以該交易對自己的最新價平倉。
                        let ectx = self
                            .paper_state
                            .get_entry_context_id(symbol)
                            .unwrap_or("")
                            .to_string();
                        // EXIT-FEATURES-TABLE-1: snapshot BEFORE close.
                        // EXIT-FEATURES-TABLE-1：先取快照再平倉。
                        let snap = self.paper_state.position_exit_snapshot(symbol);
                        if let Some((_il, _q, close_px, pnl)) =
                            self.close_position_at_symbol_market(symbol, event.ts_ms)
                        {
                            // RUST-DOUBLE-PREFIX-1: reuse `close_tag` to avoid the
                            // double-prefix drift PHYS-LOCK used to suffer.
                            // RUST-DOUBLE-PREFIX-1：重用 `close_tag`，避免 PHYS-LOCK 雙前綴漂移。
                            self.emit_close_fill(
                                symbol,
                                *is_long,
                                *qty,
                                close_px,
                                event.ts_ms,
                                pnl,
                                &close_tag,
                                &ectx,
                                snap.as_ref(),
                            );
                            // P1-2 fix: update Kelly stats for risk-close (pre-existing omission).
                            // P1-2 修復：風控平倉也更新 Kelly 統計（既有遺漏）。
                            self.intent_processor.record_trade(symbol, pnl);
                        }
                        self.stats.total_stops += 1;
                        // RUST-DOUBLE-PREFIX-1: single outbound tag, single prefix.
                        // RUST-DOUBLE-PREFIX-1：單一出口 tag，單前綴。
                        self.execute_position_close(
                            symbol, *is_long, *qty, event, false, &close_tag,
                        );
                    }
                }
                RiskAction::HaltSession(reason) => {
                    // RRC-1-C4: Circuit breaker — halt + close all / 熔斷 — 暫停+全部平倉
                    warn!(reason = %reason, "SESSION HALTED / 會話暫停");
                    self.session_halted = true;
                    self.paper_paused = true;
                    // G1-06 (Root Principle #5/#6): on Live drawdown halts, also
                    // delete authorization.json so the Live session cannot be
                    // silently un-paused without operator re-approval. The
                    // live_auth_watcher (5s poll) will tear down the Live slot
                    // on the next cycle. Demo / Paper kinds are no-op (Demo /
                    // Paper have no authorization.json). The pure decision
                    // function also gates daily-loss halts out (operator
                    // policy: daily-loss is an opt-in limit, not a re-auth
                    // event). Fail-soft: a failed remove_file does not block
                    // the close-all loop below.
                    // G1-06（根原則 #5/#6）：Live drawdown halt 同步刪除
                    // authorization.json，避免靜默 unpause；Demo/Paper 與
                    // daily-loss 不觸發。失敗也不阻塞下方關倉迴圈。
                    if let Some(decision) =
                        crate::drawdown_revoke::should_revoke(&reason, self.pipeline_kind)
                    {
                        let outcome = crate::drawdown_revoke::revoke_live_authorization(&decision);
                        info!(
                            outcome = outcome.kind_str(),
                            reason = %reason,
                            "drawdown auto-revoke evaluated / 提款自動撤銷已評估"
                        );
                    }
                    let all_pos: Vec<(String, bool, f64)> = self
                        .paper_state
                        .positions()
                        .iter()
                        .map(|p| (p.symbol.clone(), p.is_long, p.qty))
                        .collect();
                    for (sym, _, _) in &all_pos {
                        risk_closed_symbols.push(sym.clone());
                    }
                    for (sym, il, q) in &all_pos {
                        // Q1 fix: skip already-dispatched closes / 跳過已派發的平倉
                        if is_exchange_mode && self.pending_close_symbols.contains(sym) {
                            continue;
                        }
                        // P1-16 fix: use the per-symbol helper (paper_state.latest_price →
                        // entry_price fallback) instead of `event.last_price`, which carries
                        // the triggering tick's symbol price and would stamp that single
                        // price across every other symbol's halt close fill — the root cause
                        // behind `learning.decision_features` getting `-17M bps` realized
                        // edge rows when ETHUSDT triggered halt.
                        // P1-16 修復：改用 per-symbol helper（paper_state.latest_price →
                        // entry_price fallback）取代 `event.last_price`。後者攜帶觸發 tick
                        // 的那個交易對的價，會把這一個價蓋到 halt 時每個其他交易對的平倉
                        // fill，正是 ETHUSDT 觸發 halt 時 learning.decision_features 出現
                        // `-17M bps` realized edge 列的根因。
                        let ectx = self
                            .paper_state
                            .get_entry_context_id(sym)
                            .unwrap_or("")
                            .to_string();
                        // EXIT-FEATURES-TABLE-1: snapshot BEFORE close.
                        // EXIT-FEATURES-TABLE-1：先取快照再平倉。
                        let snap = self.paper_state.position_exit_snapshot(sym);
                        let close_result = if is_exchange_mode {
                            self.close_position_after_exchange_dispatch(
                                sym,
                                *il,
                                *q,
                                event,
                                "risk_close:halt_session",
                            )
                        } else {
                            self.close_position_at_symbol_market(sym, event.ts_ms)
                        };
                        if let Some((_il, _q, close_px, pnl)) = close_result {
                            self.emit_close_fill(
                                sym,
                                *il,
                                *q,
                                close_px,
                                event.ts_ms,
                                pnl,
                                "risk_close:halt_session",
                                &ectx,
                                snap.as_ref(),
                            );
                            if !is_exchange_mode {
                                self.execute_position_close(
                                    sym,
                                    *il,
                                    *q,
                                    event,
                                    false,
                                    "risk_close:halt_session",
                                );
                            }
                        }
                        self.stats.total_stops += 1;
                    }
                    break;
                }
                RiskAction::SetCooldown(ms) => {
                    // RRC-1-C4: Set cooldown on H0Gate to suppress new orders.
                    // RRC-1-C4：在 H0 門控設置冷卻期，抑制新訂單。
                    let until_ms = event.ts_ms + ms;
                    info!(cooldown_ms = ms, symbol = %symbol,
                        "cooldown set by risk check / 風控設置冷卻期");
                    self.h0_gate
                        .update_risk(openclaw_types::H0GateRiskSnapshot {
                            open_position_count: self.paper_state.positions().len() as u32,
                            total_exposure_pct: 0.0, // recalculated next status interval
                            cooldown_until_ts_ms: until_ms,
                            kill_switch_active: false,
                            snapshot_ts_ms: event.ts_ms,
                        });
                }
            }
        }

        // Notify strategies of externally-closed positions (risk-stop/halt)
        // so they can reset internal state (e.g., grid net_inventory, position flag).
        // 通知策略外部平倉的倉位（風控止損/熔斷），讓策略重設內部狀態。
        if !risk_closed_symbols.is_empty() {
            for strategy in self.orchestrator.strategies_mut() {
                for sym in &risk_closed_symbols {
                    strategy.on_external_close(sym);
                }
            }
        }
    }
}
