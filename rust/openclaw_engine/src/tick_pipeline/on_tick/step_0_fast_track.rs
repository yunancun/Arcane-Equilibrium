//! Step 0: fast-track evaluation — flash-crash / margin-crisis / held-drop.
//! Step 0：快速通道評估 — 閃崩 / 保證金危機 / 持倉跌幅。
//!
//! Also hosts the per-tick prelude (hot-reload checks, dynamic risk sizer,
//! stats bookkeeping, boot-ts stamping, price/turnover caching, synthetic-
//! owner re-triage, ADL alerts, market event fan-out). These ran above Step 0
//! in the original monolithic `on_tick.rs`; they stay contiguous with Step 0
//! because the fast-track gate consumes the freshly-cached prices/balances
//! and the subsequent steps assume `boot_ts_ms` is set + `total_ticks` is
//! already incremented.
//!
//! 亦收納每 tick 前段（熱重載 / 動態風險 sizer / stats 記錄 / boot-ts 打標 /
//! 價格與成交量快取 / synthetic-owner 再分類 / ADL 警報 / 市場事件 fan-out）。
//! 原檔中這段位於 Step 0 之上，拆分後與 Step 0 合併保留相鄰順序（fast-track
//! 依賴剛快取的價格 / 餘額，後續步驟亦假設 `boot_ts_ms` 與 `total_ticks` 已
//! 就緒）。

use std::ops::ControlFlow;
use std::time::Instant;

use openclaw_types::PriceEventKind;
use tracing::info;

use super::super::on_tick_helpers::{
    ft_reduce_cooldown_expired, push_capped, sigma_scaled_reduce_cooldown_ms,
    FT_REDUCE_COOLDOWN_MS,
};
use super::super::*;

impl TickPipeline {
    /// Execute the per-tick prelude + Step 0 fast-track evaluation.
    ///
    /// Returns:
    /// - `ControlFlow::Break(record)` — fast-track triggered an early exit
    ///   (`CloseAll` with empty positions short-circuit, or `CloseAll` full
    ///   path); the caller returns `record` immediately.
    /// - `ControlFlow::Continue(ft_pause_new_entries)` — continue into Step
    ///   0.5 with the fast-track pause flag threaded forward so Step 4+5 can
    ///   block new opens.
    ///
    /// 執行每 tick 前段 + Step 0 快速通道。回傳：
    /// - `Break(record)`：fast-track 觸發早退（`CloseAll`），由編排器直接返回。
    /// - `Continue(ft_pause_new_entries)`：繼續下一 step，旗標向後傳遞供 Step
    ///   4+5 阻擋新開倉。
    pub(super) fn on_tick_step_0_fast_track(
        &mut self,
        event: &PriceEvent,
        tick_start: Instant,
    ) -> ControlFlow<Option<CanaryRecord>, bool> {
        // P-01: local alias avoids 8× heap alloc per tick on hot path.
        // P-01：本地別名避免熱路徑上每 tick 8 次堆分配。
        let sym = &event.symbol;

        // ARCH-RC1 1C-2-B: hot-reload check — if RiskConfig store version has
        // bumped (IPC patch applied), refresh the intent_processor snapshot.
        // ARCH-RC1 1C-2-B：熱重載檢查 — RiskConfig store 版本有變即同步。
        self.sync_risk_config_if_changed();

        // EDGE-P2-3 Phase 1B-5: mirror MakerKpiConfig store into the owned
        // snapshot so the paper-only maker sweep and the router KPI gate both
        // see operator patches without waiting for the next boot. Free when
        // the store is unwired or the version is unchanged (one atomic load
        // + equality check).
        // EDGE-P2-3 Phase 1B-5：把 MakerKpiConfig 最新快照鏡像至 owned copy，
        // 讓紙盤 maker sweep 與 router KPI gate 下一 tick 即見 operator patch。
        // 未接 store 或未升版時只花一次 atomic load + equality 比較。
        self.sync_maker_kpi_config_if_changed();

        // DYNAMIC-RISK-1: throttled Sharpe-aware sizer tick. Internally rate-limited
        // by `update_interval_ms` and `min_trades`, so safe to call on every tick.
        // When it publishes a new pct, push into IntentProcessor. Disabled in TOML
        // → short-circuits inside `maybe_update` (returns None), effectively free.
        // DYNAMIC-RISK-1：節流化 Sharpe 調整器，內部限頻安全逐 tick 呼叫。
        // 停用時 `maybe_update` 直接 None，近乎零成本。
        if let Some(new_pct) = self.dynamic_risk_sizer.maybe_update(event.ts_ms) {
            self.intent_processor.set_p1_risk_pct(new_pct);
        }

        self.stats.total_ticks += 1;
        self.stats.last_tick_ms = event.ts_ms;
        // PNL-3: Stamp boot timestamp on first tick (used for cooldown gate below).
        // PNL-3：首個 tick 記錄啟動時間戳（用於下方冷卻期門控）。
        if self.boot_ts_ms.is_none() {
            self.boot_ts_ms = Some(event.ts_ms);
        }
        self.latest_prices.insert(sym.clone(), event.last_price);
        self.paper_state.set_latest_price(sym, event.last_price);

        // DUST-EVICTION-GAP-1 / P1-8 FUP (2026-04-17): opportunistic per-tick re-triage for
        // positions wearing a synthetic owner label (bybit_sync / orphan_adopted /
        // orphan_frozen). Lets Agent autonomously recover from startup-time conditions
        // that blocked ownership promotion (notional below min, symbol not in universe)
        // without requiring restart or operator action (§原則 #11 Agent 最大自主權).
        // Fast path: non-synthetic labels short-circuit in `retriage_synthetic_owner` with
        // a single hashmap lookup + label compare — zero per-tick cost in the common case.
        // DUST-EVICTION-GAP-1 / P1-8 FUP：synthetic owner（bybit_sync / orphan_adopted /
        // orphan_frozen）持倉每 tick 機會性重分流，讓 Agent 自主恢復啟動時阻擋升級的條件
        // （§原則 #11）。熱路徑短路：非 synthetic 為 O(1) 無成本。
        self.retriage_synthetic_owner_for_symbol(sym, event.last_price, event.ts_ms);

        // RRC-1-B2: Reset daily start balance at UTC midnight for daily loss tracking.
        // RRC-1-B2：UTC 午夜重置每日起始餘額，用於日損追蹤。
        self.intent_processor
            .maybe_reset_daily_balance(self.paper_state.balance(), event.ts_ms);
        // RRC-1-C1: Feed price to tracker for ATR computation + spike detection.
        // RRC-1-C1：餵入價格到追蹤器，用於 ATR 計算 + 尖峰偵測。
        self.price_tracker
            .record(sym, event.last_price, event.ts_ms);
        // Update per-symbol turnover for dynamic slippage (from ticker events)
        // 更新每交易對成交額用於動態滑點（來自 ticker 事件）
        if event.turnover_24h > 0.0 {
            self.paper_state
                .set_latest_turnover(sym, event.turnover_24h);

            // Phase 1 (F-2 fix): Emit TickerSnapshot to market writer for ticker events.
            // Phase 1（F-2 修復）：為 ticker 事件發送 TickerSnapshot 到市場寫入器。
            if let Some(ref tx) = self.market_data_tx {
                let spread = if event.ask_price > 0.0 && event.bid_price > 0.0 {
                    (event.ask_price - event.bid_price) / event.last_price * 10_000.0
                } else {
                    0.0
                };
                let _ = tx.try_send(crate::database::MarketDataMsg::TickerSnapshot {
                    ts_ms: event.ts_ms,
                    symbol: sym.clone(),
                    last_price: event.last_price,
                    mark_price: 0.0, // not available in PriceEvent yet
                    index_price: event.index_price.unwrap_or(0.0),
                    best_bid: event.bid_price,
                    best_ask: event.ask_price,
                    bid_size: 0.0, // not available in PriceEvent yet
                    ask_size: 0.0, // not available in PriceEvent yet
                    volume_24h: event.volume_24h,
                    turnover_24h: event.turnover_24h,
                    spread_bps: spread,
                    open_interest: 0.0, // not available in PriceEvent yet
                });
            }
        }

        // Item 9 (M3 fix): ADL alert monitoring
        // 項目 9（M3 修復）：ADL 警報監控
        if event.event_kind.as_ref() == Some(&PriceEventKind::AdlNotice) {
            // P-02: Read structured field first, fall back to legacy metadata.
            // P-02：優先讀結構化欄位，回退到舊版 metadata。
            let rank = event.adl_rank.or_else(|| {
                event
                    .metadata
                    .get("adl_rank")
                    .and_then(|s| s.parse::<u32>().ok())
            });
            if let Some(rank) = rank {
                push_capped(&mut self.adl_alerts, (event.ts_ms, sym.clone(), rank), 50);
                if rank >= 3 {
                    info!(
                        symbol = %sym, rank = rank,
                        "⚠ ADL rank HIGH — consider reducing position / ADL 排名高，考慮減倉"
                    );
                }
            }
        }

        // Session 11: feed trade & orderbook events into 1-minute aggregators.
        // FIX-29: extracted to on_tick_helpers.rs.
        self.process_market_events(event);

        // Step 0: Fast track check — emergency actions before normal processing
        // FIX-03+04: Real inputs for flash-crash and margin-crisis detection.
        // margin_utilization_pct: margin_used (= notional / leverage) / balance × 100.
        // FA-PHANTOM-1 fix (2026-04-14): margin now leverage-aware.
        // FA-PHANTOM-2 fix (2026-04-15): drop input scoped to held symbols with
        //   sigma signal, replacing the global cross-symbol scan that trivially
        //   hit the 5% threshold on any microcap in the observation pool and
        //   false-triggered CloseAll at Normal risk (blocked G-2 funding_arb
        //   validation — 0/20 fills in 7h on 2026-04-15 prior to fix).
        // FA-PHANTOM-2 修復：跌幅輸入改為「僅持倉幣種」+ sigma 信號，
        //   取代舊的全觀察池掃描（小幣常態 5% 抖動即誤觸 CloseAll）。
        let held_symbols: Vec<String> = self
            .paper_state
            .positions()
            .iter()
            .map(|p| p.symbol.clone())
            .collect();
        let (held_drop_pct, held_drop_sigma, held_drop_symbol) = self
            .price_tracker
            .worst_drop_for_held(&held_symbols)
            .map(|info| (info.drop_pct, info.sigma, info.symbol))
            .unwrap_or((0.0, 0.0, String::new()));
        let margin_utilization_pct = {
            let balance = self.paper_state.balance();
            if balance > 0.0 {
                let total_notional: f64 = self
                    .paper_state
                    .positions()
                    .iter()
                    .map(|p| {
                        let px = self
                            .latest_prices
                            .get(&p.symbol)
                            .copied()
                            .unwrap_or(p.entry_price);
                        p.qty * px
                    })
                    .sum();
                let leverage = self
                    .intent_processor
                    .risk_config()
                    .limits
                    .leverage_max
                    .max(1.0);
                let margin_used = total_notional / leverage;
                (margin_used / balance * 100.0).min(999.0)
            } else {
                0.0
            }
        };
        let ft_action = crate::fast_track::evaluate_fast_track(
            self.governance.risk.level,
            held_drop_pct,
            held_drop_sigma,
            margin_utilization_pct,
        );

        // EDGE-P0-1 + P0-5: Clear guard only when risk fully recovers to Normal.
        // The prior `< Defensive` condition wiped the guard every tick in
        // persistent Cautious — FA-PHANTOM-2's 5%+3σ held-drop path fires
        // ReduceToHalf at Cautious, so the clear+re-emit loop produced 9
        // fires in 1.3 s on 2026-04-16. Per-symbol burst is still bounded by
        // the 60 s cooldown inside `ft_reduce_cooldown_expired`; this clear
        // is the fast re-arm for a genuine new episode after full recovery.
        // EDGE-P0-1 + P0-5：僅當風控完全回到 Normal 才清空 guard，避免
        // Cautious 下每 tick 清一次。毫秒連發由 60 s 冷卻窗另行封住。
        if self.governance.risk.level == openclaw_core::sm::risk_gov::RiskLevel::Normal
            && !self.ft_reduced_symbols.is_empty()
        {
            tracing::info!(
                cleared = self.ft_reduced_symbols.len(),
                "EDGE-P0-1: risk returned to Normal — clearing ReduceToHalf cooldown map / 風控回歸 Normal 清空半倉冷卻表"
            );
            self.ft_reduced_symbols.clear();
        }

        // FIX-03: Track whether fast_track blocks new entries for this tick.
        // ReduceToHalf and PauseNewEntries both suppress new opens.
        // FIX-03：追蹤 fast_track 是否暫停本 tick 的新開倉。
        let ft_pause_new_entries = ft_action == crate::fast_track::FastTrackAction::PauseNewEntries
            || ft_action == crate::fast_track::FastTrackAction::ReduceToHalf;

        // FIX-03: Handle ReduceToHalf — close half qty of each position.
        // EDGE-P0-1: One-shot guard — each position only halved once per Defensive episode.
        // FIX-03：處理 ReduceToHalf — 每個倉位平半倉。
        // EDGE-P0-1：One-shot 保護 — 每個倉位在同一次 Defensive 階段只半倉一次。
        if ft_action == crate::fast_track::FastTrackAction::ReduceToHalf {
            // P0-5: cast once per tick for the filter + insert.
            // P0-5：每 tick 轉型一次供 filter 與 insert 共用。
            let now_ts_ms: i64 = event.ts_ms as i64;

            // B1: Classify the trigger. A 5%+3σ held-drop at Normal/Cautious
            // is a *symbol-specific* outlier event — scope the reduction to
            // just that symbol. Systemic triggers (Defensive+ without drop,
            // margin, ≥15% fall-through) still reduce every position.
            // B1：分類觸發源。5%+3σ+<Defensive 為單 symbol 異常事件，限定
            //     該 symbol 減半；系統性觸發維持全倉減半。
            let drop_scoped = crate::fast_track::is_drop_scoped_reduce(
                self.governance.risk.level,
                held_drop_pct,
                held_drop_sigma,
            );

            // B2: Compute the cooldown that will be stamped for this reduce
            // event. Drop-triggered reductions scale with sigma; systemic
            // reductions keep the base window.
            // B2：本次半倉事件寫入冷卻表的有效 ms。drop 觸發按 sigma 縮放，
            //     系統性觸發用基準窗口。
            let effective_cooldown_ms = if drop_scoped {
                sigma_scaled_reduce_cooldown_ms(held_drop_sigma)
            } else {
                FT_REDUCE_COOLDOWN_MS
            };

            // MICRO-PROFIT-FIX-1 (Scheme A, 2026-04-17): read current floor ratio from
            // RiskConfig (hot-reloadable). 0.0 disables the floor for back-compat tests.
            // Worklog §3.3: default 0.25 — skip halving positions whose current notional
            // is already ≤ 25% of the entry notional, killing the 4-6× halving spiral
            // observed in demo (989 fast_track_reduce_half dust fills / 48h).
            // MICRO-PROFIT-FIX-1（方案 A）：從 RiskConfig 熱讀 ft_min_notional_ratio_of_entry
            // （預設 0.25）；當前名義值已 ≤ 25% 入場名義值則跳過半倉，封住 4-6 次螺旋。
            let ft_min_notional_ratio = self
                .intent_processor
                .risk_config()
                .limits
                .ft_min_notional_ratio_of_entry;
            // EXIT-FEATURES-WRITER-BUG-1-FIX (2026-04-26): absolute USD dust floor —
            // closes the MICRO-PROFIT-FIX-1 fail-open hole when entry_notional is
            // missing (legacy/restored snapshot). MIT audit
            // `2026-04-26--exit_features_writer_bug_audit.md` §4 RCA-A: STRKUSDT
            // 0.05-unit residue with `entry_notional == 0.0` triggered 37 halvings
            // (60s apart) down to 7.3e-13, polluting `learning.exit_features`
            // with 37 noise labels (close_fills 1:1 invariant violated by Δ37).
            // Hot-reloadable; default 1 USD (well below any real position
            // notional, well above sub-cent dust residues).
            // EXIT-FEATURES-WRITER-BUG-1-FIX（2026-04-26）：絕對 USD dust 門檻，
            // 修補 MICRO-PROFIT-FIX-1 在 entry_notional 缺失時 fail-open 的漏洞
            // （MIT audit §4 RCA-A：STRKUSDT 37 次半倉 spiral，污染 EF 37 條 noise label）。
            let ft_dust_qty_floor_usd = self
                .intent_processor
                .risk_config()
                .limits
                .ft_dust_qty_floor_usd;

            // Materialize per-position data up front so the notional-floor filter below
            // can freely read self.latest_prices without a concurrent self.paper_state borrow.
            // 先物化每倉資料，後續 filter 可自由讀 latest_prices。
            let mut position_candidates: Vec<(String, bool, f64, f64)> = self
                .paper_state
                .positions()
                .iter()
                .filter(|p| {
                    // B1: drop-scoped reduce only halves the triggering symbol.
                    !drop_scoped || p.symbol == held_drop_symbol
                })
                .filter(|p| {
                    ft_reduce_cooldown_expired(&self.ft_reduced_symbols, &p.symbol, now_ts_ms)
                })
                .map(|p| (p.symbol.clone(), p.is_long, p.qty, p.entry_notional))
                .collect();

            // MICRO-PROFIT-FIX-1 + EXIT-FEATURES-WRITER-BUG-1-FIX: layered
            // dust filter. Each candidate must pass BOTH gates before being
            // halved — failing either gate skips the position (stays at full
            // qty until a real exit signal arrives or operator clears manually).
            //
            // Gate 1 — absolute USD floor (EXIT-FEATURES-WRITER-BUG-1-FIX):
            //   `qty * latest_price < ft_dust_qty_floor_usd` → skip. Active in
            //   ALL branches (including the `entry_notional == 0` legacy path
            //   that previously fail-opened). This is the primary defence
            //   against MIT-audited STRKUSDT 37-halve dust spiral.
            //
            // Gate 2 — ratio gate (MICRO-PROFIT-FIX-1):
            //   `qty * latest_price < ratio * entry_notional` → skip. Inactive
            //   when ratio == 0 (disabled) OR entry_notional <= 0 (no baseline
            //   from which to derive a relative floor — Gate 1 already handles
            //   the dust case). The ratio gate kills the 4-6× halving spiral
            //   observed in demo by capping at "two halvings then stop".
            //
            // SAFETY / 不變量：
            //   - `latest_price <= 0` (stale tick): both gates fall through,
            //     position is left intact. Fast-track will re-evaluate on the
            //     next tick once a fresh price arrives.
            //   - `entry_notional <= 0` (legacy/restored snapshot): Gate 2 is
            //     a no-op; Gate 1 alone decides. If qty * price > floor the
            //     halving proceeds (pre-FIX behaviour preserved for genuine
            //     legacy real positions); if not, dust is left frozen.
            //
            // MICRO-PROFIT-FIX-1 + EXIT-FEATURES-WRITER-BUG-1-FIX：分層 dust 過濾，
            // 每個候選必須同時通過 Gate 1（絕對 USD 門檻）+ Gate 2（比率門檻）。
            // 任一失敗即 skip（倉位保持原 qty 直到真正退場訊號或 operator 清理）。
            // Gate 1 對 entry_notional == 0 legacy 倉位仍生效（封住 STRKUSDT 37 次
            // dust spiral 漏洞）；Gate 2 在 entry_notional 缺失時 no-op，由 Gate 1 兜底。
            if ft_dust_qty_floor_usd > 0.0 || ft_min_notional_ratio > 0.0 {
                position_candidates.retain(|(sym, _, qty, entry_notional)| {
                    let last_price = self.latest_prices.get(sym).copied().unwrap_or(0.0);
                    if last_price <= 0.0 {
                        // Stale tick — leave position intact, re-evaluate next tick.
                        // 過期 tick — 保留倉位，下 tick 重評估。
                        return true;
                    }
                    let current_notional = qty * last_price;

                    // Gate 1: absolute USD dust floor (EXIT-FEATURES-WRITER-BUG-1-FIX).
                    // Fires regardless of entry_notional state (closes the legacy
                    // fail-open hole that drove the dust spiral).
                    // Gate 1：絕對 USD dust 門檻（不看 entry_notional 是否有效）。
                    if ft_dust_qty_floor_usd > 0.0 && current_notional < ft_dust_qty_floor_usd {
                        tracing::info!(
                            symbol = %sym,
                            current_notional,
                            dust_floor_usd = ft_dust_qty_floor_usd,
                            entry_notional = *entry_notional,
                            "EXIT-FEATURES-WRITER-BUG-1-FIX: skip ReduceToHalf — dust \
                             qty floor / 低於 dust 絕對門檻，跳過半倉"
                        );
                        return false;
                    }

                    // Gate 2: ratio gate (MICRO-PROFIT-FIX-1). Inactive on
                    // `entry_notional <= 0` (no baseline) — Gate 1 already
                    // handled the dust case; non-dust legacy real positions
                    // fall through to fail-open here.
                    // Gate 2：比率門檻；entry_notional <= 0 時 no-op（Gate 1 已處理 dust）。
                    if ft_min_notional_ratio > 0.0 && *entry_notional > 0.0 {
                        let floor_notional = ft_min_notional_ratio * entry_notional;
                        if current_notional < floor_notional {
                            tracing::info!(
                                symbol = %sym,
                                current_notional,
                                floor_notional,
                                entry_notional = *entry_notional,
                                ratio = ft_min_notional_ratio,
                                "MICRO-PROFIT-FIX-1: skip ReduceToHalf — notional \
                                 below ratio floor / 已低於比率底線，跳過半倉"
                            );
                            return false;
                        }
                    }
                    true
                });
            }

            let positions: Vec<(String, bool, f64)> = position_candidates
                .into_iter()
                .map(|(sym, is_long, qty, _)| (sym, is_long, qty))
                .collect();
            if !positions.is_empty() {
                tracing::warn!(
                    risk_level = ?self.governance.risk.level,
                    ts_ms = event.ts_ms,
                    positions = positions.len(),
                    held_drop_pct,
                    held_drop_sigma,
                    held_drop_symbol = %held_drop_symbol,
                    margin_utilization_pct,
                    drop_scoped,
                    effective_cooldown_ms,
                    "FAST_TRACK ReduceToHalf — halving positions (one-shot) / 快速通道半倉（一次性）"
                );
                for (sym, is_long, qty) in &positions {
                    let half_qty = qty / 2.0;
                    if half_qty > 0.0 {
                        if let Some(close_price) = self.paper_state.latest_price(sym) {
                            if close_price > 0.0 {
                                // EDGE-P3-1 R2: reduce_position keeps the position alive (partial close),
                                // so entry_context_id remains on the residual. Capture here for the fill row.
                                // EDGE-P3-1 R2：reduce_position 是部分平倉，剩餘倉位仍保留 entry_context_id。
                                let ectx = self
                                    .paper_state
                                    .get_entry_context_id(sym)
                                    .unwrap_or("")
                                    .to_string();
                                // EXIT-FEATURES-TABLE-1: snapshot BEFORE close/reduce
                                // so the Track P row reflects pre-exit state. by-value.
                                // EXIT-FEATURES-TABLE-1：先取快照再平倉，Track P 標籤
                                // 反映出場前狀態（by-value，partial close 亦安全）。
                                let snap = self.paper_state.position_exit_snapshot(sym);
                                let pnl =
                                    self.paper_state.reduce_position(sym, half_qty, close_price);
                                self.emit_close_fill(
                                    sym,
                                    *is_long,
                                    half_qty,
                                    close_price,
                                    event.ts_ms,
                                    pnl,
                                    "risk_close:fast_track_reduce_half",
                                    &ectx,
                                    snap.as_ref(),
                                );
                                // FIX-03b: dispatch exchange order for Demo/Live so
                                // Bybit-side position matches local paper_state.
                                // FIX-03b：Demo/Live 模式派發交易所訂單，避免本地狀態與交易所倉位脫節。
                                let is_primary = self.pipeline_kind.is_exchange();
                                self.execute_position_close(
                                    sym,
                                    *is_long,
                                    half_qty,
                                    event,
                                    is_primary,
                                    "risk_close:fast_track_reduce_half",
                                );
                            }
                        }
                    }
                    // EDGE-P0-1 + P0-5 + B2: Stamp (last-reduce ts, effective cooldown)
                    // so `ft_reduce_cooldown_expired` uses the sigma-scaled window
                    // captured at the moment of halving.
                    // EDGE-P0-1 + P0-5 + B2：寫入（半倉時間戳, 有效冷卻 ms），
                    // 冷卻依觸發 sigma 鎖定。
                    self.ft_reduced_symbols
                        .insert(sym.clone(), (now_ts_ms, effective_cooldown_ms));
                }
            }
            // Continue processing stops but skip new entries (ft_pause_new_entries = true)
        }

        if ft_action == crate::fast_track::FastTrackAction::PauseNewEntries {
            tracing::info!(
                risk_level = ?self.governance.risk.level,
                ts_ms = event.ts_ms,
                held_drop_pct,
                held_drop_sigma,
                margin_utilization_pct,
                "FAST_TRACK PauseNewEntries — stops only, no new positions / 快速通道暫停開倉"
            );
            // Continue processing — stops will run, but new entries blocked by ft_pause_new_entries
        }

        if ft_action == crate::fast_track::FastTrackAction::CloseAll {
            let symbols: Vec<String> = self
                .paper_state
                .positions()
                .iter()
                .map(|p| p.symbol.clone())
                .collect();
            // FIX-A: If CB is set but positions are already gone (IPC already closed them),
            // skip the WARN + empty loop every tick — it only generates noise and wastes CPU.
            // The CB risk level will persist until operator de-escalates via IPC.
            // FIX-A：若 CB 已設但倉位已清（IPC 已平倉），每 tick 跳過 WARN + 空迴圈，避免日誌垃圾。
            // CB 風控級別持續直到 Operator 通過 IPC 手動降級。
            if symbols.is_empty() {
                let tick_duration_us = tick_start.elapsed().as_micros() as u64;
                return ControlFlow::Break(self.maybe_canary_record(
                    event,
                    None,
                    vec![],
                    vec![],
                    tick_duration_us,
                ));
            }
            // PNL-4: every fast_track CloseAll now leaves a forensic breadcrumb
            // (risk level + ts + position count + triggering tick symbol). The
            // 2026-04-11 18:51 incident was untraceable because logs rotated;
            // the next time a CloseAll fires, this WARN line is what you grep.
            // PNL-4：每次 fast_track CloseAll 留下取證痕跡，避免 2026-04-11 重演。
            tracing::warn!(
                risk_level = ?self.governance.risk.level,
                ts_ms = event.ts_ms,
                positions = symbols.len(),
                trigger_symbol = %sym,
                trigger_price = event.last_price,
                held_drop_pct,
                held_drop_sigma,
                held_drop_symbol = %held_drop_symbol,
                margin_utilization_pct,
                "FAST_TRACK CloseAll fired — closing all positions / 快速通道全平觸發"
            );
            // PNL-FIX-1: must close each position at ITS OWN symbol's latest price,
            // not event.last_price (which is the triggering tick's price for ONE
            // symbol — applying it to all symbols inflated PnL by 1000-10000x in
            // the 2026-04-12 anomaly).
            // PNL-FIX-1：每個倉位必須以該交易對自己的最新價平倉，禁止使用 event.last_price。
            for sym in symbols {
                // EDGE-P3-1 R2: capture entry_context_id BEFORE close_position_at_symbol_market
                // removes the position. Empty string when unknown → NULL in DB.
                // EDGE-P3-1 R2：關倉前先捕獲 entry_context_id。
                let ectx = self
                    .paper_state
                    .get_entry_context_id(&sym)
                    .unwrap_or("")
                    .to_string();
                // EXIT-FEATURES-TABLE-1: snapshot BEFORE close_position_at_symbol_market
                // (full close → position removed after).
                // EXIT-FEATURES-TABLE-1：先取快照再平倉（full close 後倉位已移除）。
                let snap = self.paper_state.position_exit_snapshot(&sym);
                if let Some((il, q, px, pnl)) =
                    self.close_position_at_symbol_market(&sym, event.ts_ms)
                {
                    self.emit_close_fill(
                        &sym,
                        il,
                        q,
                        px,
                        event.ts_ms,
                        pnl,
                        "risk_close:fast_track",
                        &ectx,
                        snap.as_ref(),
                    );
                }
                self.stats.total_stops += 1;
            }
            // Measure elapsed time for fast-track exit / 計算快速通道退出的耗時
            let tick_duration_us = tick_start.elapsed().as_micros() as u64;
            return ControlFlow::Break(self.maybe_canary_record(
                event,
                None,
                vec![],
                vec![],
                tick_duration_us,
            ));
        }

        ControlFlow::Continue(ft_pause_new_entries)
    }
}
