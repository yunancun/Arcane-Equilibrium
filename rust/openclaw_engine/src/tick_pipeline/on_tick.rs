//! on_tick pipeline processing — the core tick-by-tick orchestration loop.
//! on_tick 管線處理 — 核心逐 tick 編排循環。

use super::*;
use super::on_tick_helpers::{push_capped, make_context_id, make_signal_id, make_fill_id, make_order_id, persist_verdict, persist_intent, push_display_intent, build_intent, ft_reduce_cooldown_expired, sigma_scaled_reduce_cooldown_ms, FT_REDUCE_COOLDOWN_MS};

impl TickPipeline {
    /// Process a single price event through the full pipeline.
    /// Returns a CanaryRecord when canary_mode is enabled (R07-2).
    /// 通過完整管線處理單個價格事件。
    /// 灰度模式啟用時返回 CanaryRecord。
    pub fn on_tick(&mut self, event: &PriceEvent) -> Option<CanaryRecord> {
        // Start timing the tick processing / 開始計時 tick 處理
        let tick_start = Instant::now();
        // P-01: local alias avoids 8× heap alloc per tick on hot path.
        // P-01：本地別名避免熱路徑上每 tick 8 次堆分配。
        let sym = &event.symbol;

        // ARCH-RC1 1C-2-B: hot-reload check — if RiskConfig store version has
        // bumped (IPC patch applied), refresh the intent_processor snapshot.
        // ARCH-RC1 1C-2-B：熱重載檢查 — RiskConfig store 版本有變即同步。
        self.sync_risk_config_if_changed();

        self.stats.total_ticks += 1;
        self.stats.last_tick_ms = event.ts_ms;
        // PNL-3: Stamp boot timestamp on first tick (used for cooldown gate below).
        // PNL-3：首個 tick 記錄啟動時間戳（用於下方冷卻期門控）。
        if self.boot_ts_ms.is_none() {
            self.boot_ts_ms = Some(event.ts_ms);
        }
        self.latest_prices
            .insert(sym.clone(), event.last_price);
        self.paper_state
            .set_latest_price(sym, event.last_price);

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
                    mark_price: 0.0,  // not available in PriceEvent yet
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
            let rank = event
                .adl_rank
                .or_else(|| {
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
                let total_notional: f64 = self.paper_state.positions().iter().map(|p| {
                    let px = self.latest_prices.get(&p.symbol).copied().unwrap_or(p.entry_price);
                    p.qty * px
                }).sum();
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

            // MICRO-PROFIT-FIX-1: drop candidates already below the notional floor.
            // Skipped when ratio is 0.0 (disabled) or entry_notional is 0.0 (legacy
            // snapshot not yet migrated — fail-open so operator positions still halve).
            // MICRO-PROFIT-FIX-1：剔除已低於底線的倉位；比率 0 或舊快照未遷移時 fail-open。
            if ft_min_notional_ratio > 0.0 {
                position_candidates.retain(|(sym, _, qty, entry_notional)| {
                    if *entry_notional <= 0.0 {
                        return true;
                    }
                    let last_price = self
                        .latest_prices
                        .get(sym)
                        .copied()
                        .unwrap_or(0.0);
                    if last_price <= 0.0 {
                        return true;
                    }
                    let current_notional = qty * last_price;
                    let floor_notional = ft_min_notional_ratio * entry_notional;
                    let keep = current_notional >= floor_notional;
                    if !keep {
                        tracing::info!(
                            symbol = %sym,
                            current_notional,
                            floor_notional,
                            entry_notional = *entry_notional,
                            ratio = ft_min_notional_ratio,
                            "MICRO-PROFIT-FIX-1: skip ReduceToHalf — notional below floor \
                             / 已低於名義值底線，跳過半倉"
                        );
                    }
                    keep
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
                                let pnl = self.paper_state.reduce_position(sym, half_qty, close_price);
                                self.emit_close_fill(sym, *is_long, half_qty, close_price, event.ts_ms, pnl, "risk_close:fast_track_reduce_half", &ectx);
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
                return self.maybe_canary_record(event, None, vec![], vec![], tick_duration_us);
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
                if let Some((il, q, px, pnl)) =
                    self.close_position_at_symbol_market(&sym, event.ts_ms)
                {
                    self.emit_close_fill(&sym, il, q, px, event.ts_ms, pnl, "risk_close:fast_track", &ectx);
                }
                self.stats.total_stops += 1;
            }
            // Measure elapsed time for fast-track exit / 計算快速通道退出的耗時
            let tick_duration_us = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, None, vec![], vec![], tick_duration_us);
        }

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
                if let Some((il, q, px, pnl)) =
                    self.close_position_at_symbol_market(sym, event.ts_ms)
                {
                    let tag = format!("stop_trigger:{}", trigger.reason);
                    self.emit_close_fill(sym, il, q, px, event.ts_ms, pnl, &tag, &ectx);
                }
                self.stats.total_stops += 1;
            }
            let dur = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, None, vec![], vec![], dur);
        }
        if !h0_result.reason.is_empty() {
            debug!(symbol = %sym, reason = %h0_result.reason,
                "H0 shadow would-block / H0 影子模式本應阻斷");
        }

        // Step 1: Kline aggregation — collect closed bars for DB write.
        // 步驟 1：K 線聚合 — 收集已關閉的 K 線用於 DB 寫入。
        let closed_bars = self.kline_manager.on_tick(
            sym,
            event.last_price,
            event.ts_ms,
            event.volume_24h,
            0.0,
        );

        // Phase 1: Emit KlineClose for each closed bar to market writer (F-2 audit fix).
        // Phase 1：為每根已關閉 K 線發送 KlineClose 到市場寫入器（F-2 審計修復）。
        if let Some(ref tx) = self.market_data_tx {
            for (timeframe, bar) in &closed_bars {
                if tx
                    .try_send(crate::database::MarketDataMsg::KlineClose {
                        symbol: sym.clone(),
                        timeframe: timeframe.clone(),
                        bar: bar.clone(),
                    })
                    .is_err()
                {
                    self.market_tx_dropped += 1;
                }
            }
        }

        // DB-RUN-5: Feed black-swan detector on 1m bar close.
        // Compute log-return vs previous close, push into rolling window, run
        // 4-signal vote. Severity >= Observe → warn log. DB write deferred.
        // DB-RUN-5：1 分鐘 K 線收盤時餵入黑天鵝檢測器，4 信號投票，severity 達標時 warn。
        for (timeframe, bar) in &closed_bars {
            if timeframe != "1m" {
                continue;
            }
            let prev = self.last_close_price.insert(sym.clone(), bar.close);
            let ret = match prev {
                Some(prev_close) if prev_close > 0.0 => (bar.close - prev_close) / prev_close,
                _ => 0.0,
            };
            self.black_swan.record_bar(sym, ret, bar.volume);
            let result = self.black_swan.check(sym, ret, bar.volume, event.ts_ms);
            use crate::database::black_swan_detector::BlackSwanSeverity;
            if !matches!(result.severity, BlackSwanSeverity::None) {
                warn!(
                    symbol = %sym,
                    severity = ?result.severity,
                    votes = result.votes_for,
                    return_pct = format!("{:.4}%", ret * 100.0),
                    "BLACK SWAN signal / 黑天鵝信號"
                );
            }
        }

        // Step 2: Compute indicators (need enough 1m bars)
        // 步驟 2：計算指標（需要足夠的 1 分鐘 K 線）
        let indicators = self.compute_indicators(sym);

        // Store latest indicators for IPC snapshot / 存儲最新指標供 IPC 快照使用
        if let Some(ref ind) = indicators {
            self.latest_indicators
                .insert(sym.clone(), ind.clone());
        }

        // Phase 1: Emit FeatureSnapshot to DB writer channel (non-blocking try_send).
        // Phase 1：發送 FeatureSnapshot 到 DB 寫入器通道（非阻塞 try_send）。
        if let (Some(ref tx), Some(ref ind)) = (&self.feature_tx, &indicators) {
            let snap = crate::feature_collector::FeatureSnapshot::new(
                sym.clone(),
                event.ts_ms,
                event.last_price,
                event.volume_24h,
                ind.clone(),
                self.feature_version.clone(),
            );
            if tx.try_send(snap).is_err() {
                self.feature_tx_dropped += 1;
            }
        }

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
                if let Some((il, q, px, pnl)) =
                    self.close_position_at_symbol_market(sym, event.ts_ms)
                {
                    let tag = format!("stop_trigger:{}", trigger.reason);
                    self.emit_close_fill(sym, il, q, px, event.ts_ms, pnl, &tag, &ectx);
                    self.stats.total_stops += 1;
                    self.execute_position_close(sym, il, q, event, false, &tag);
                } else {
                    self.stats.total_stops += 1;
                }
            }
            let tick_duration_us = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, indicators, vec![], vec![], tick_duration_us);
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
        } else if let Some(ref ind) = indicators {
            let input = snapshot_to_input(ind);
            self.signal_engine
                .evaluate(sym, "1m", &input, event.ts_ms)
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
                    let _ = tx.try_send(crate::database::TradingMsg::Signal {
                        signal_id: make_signal_id(&sig.source, sig.ts_ms),
                        ts_ms: sig.ts_ms,
                        symbol: sig.symbol.clone(),
                        strategy_name: sig.source.clone(),
                        timeframe: sig.timeframe.clone(),
                        signal_type: format!("{:?}", sig.direction),
                        strength: sig.confidence,
                        context_id: make_context_id(em, &sig.symbol, sig.ts_ms),
                    });
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
                    indicators.as_ref(),
                    self.paper_state.get_position(sym),
                    self.paper_state.balance(),
                    self.paper_state.drawdown_pct(),
                    self.linucb.as_ref(),
                    self.news_snapshot.as_ref(),
                    self.effective_engine_mode(),
                );
            }
        }

        // Step 4+5: Per-strategy dispatch + intent processing with rejection/fill callbacks (RC-04/RC-05).
        // 步驟 4+5：逐策略分派 + 意圖處理，含拒絕/成交回調。
        // P-08: Borrow instead of clone — lifetime scoped to this on_tick call.
        // P-08：借用取代克隆 — 生命週期限定在此 on_tick 調用中。
        // EDGE-P1-2: Cache funding rate from Ticker events; pass latest to strategies.
        // EDGE-P1-2：緩存 Ticker 事件的資金費率；傳遞最新值給策略。
        if let Some(fr) = event.funding_rate {
            self.funding_rates.insert(sym.to_string(), fr);
        }
        // OC-5: Cache index price from Ticker events for FundingArb basis calculation.
        // OC-5：緩存 Ticker 事件的指數價格，用於 FundingArb 基差計算。
        if let Some(ip) = event.index_price {
            self.index_prices.insert(sym.to_string(), ip);
        }
        let funding_rate = self.funding_rates.get(sym).copied();
        let index_price = self.index_prices.get(sym).copied();

        let ctx = TickContext {
            symbol: sym,
            price: event.last_price,
            timestamp_ms: event.ts_ms,
            indicators: indicators.as_ref(),
            signals: &signals,
            h0_allowed, // RRC-1-A1: real H0 gate result from Step 0.5
            funding_rate,
            index_price,
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
                SystemMode::DemoReserved
                    if self.pipeline_kind == PipelineKind::Live =>
                {
                    true
                }
                _ => false,
            };
            if block {
                let tick_duration_us = tick_start.elapsed().as_micros() as u64;
                return self.maybe_canary_record(
                    event,
                    indicators,
                    signals,
                    vec![],
                    tick_duration_us,
                );
            }
        }

        // Extract ATR for cost gate (Gate 3) / 提取 ATR 用於成本門控
        let atr_value = indicators
            .as_ref()
            .and_then(|i| i.atr_14.as_ref())
            .map(|a| a.atr)
            .unwrap_or(0.0);

        let mut intents: Vec<crate::intent_processor::OrderIntent> = Vec::new();
        let mut pending_strategy_closes: Vec<(String, String)> = Vec::new();
        for strategy in self.orchestrator.strategies_mut() {
            if !strategy.is_active() {
                continue;
            }
            let strategy_actions = strategy.on_tick(&ctx);
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
                // SCANNER-GATE: block new opens on symbols not in scanner active universe.
                // Prevents death-loop where strategy opens → reconciler closes → repeat.
                // 掃描器門控：非活躍交易對不開新倉，防止開→平→開死循環。
                if let Some(ref reg) = self.symbol_registry {
                    if !reg.is_active(&intent.symbol) {
                        tracing::debug!(
                            strategy = %strategy.name(),
                            symbol = %intent.symbol,
                            "SCANNER-GATE: new entry blocked — symbol not in scanner universe"
                        );
                        continue;
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
                    let features = crate::edge_predictor::feature_builder::build_feature_vector(
                        intent,
                        event,
                        indicators.as_ref(),
                        atr_value,
                        &self.paper_state,
                    );
                    let context_id = make_context_id(em, &intent.symbol, event.ts_ms);
                    let gate = self.intent_processor.process_gates_only_with_features(
                        intent,
                        &self.governance,
                        &self.paper_state,
                        atr_value,
                        self.pipeline_kind.governance_profile(),
                        Some(&features),
                        Some(&context_id),
                        event.ts_ms,
                    );

                    // S-01: persist verdict via extracted helper
                    if let Some(ref vi) = gate.verdict_info {
                        persist_verdict(&self.trading_tx, em, &intent.symbol, event.ts_ms, vi, em);
                    }

                    // P0-6 DIAG: surface post-Guardian rejection reason (normally silent).
                    // Remove after root-cause confirmed.
                    if !gate.approved {
                        if let Some(ref reason) = gate.rejected_reason {
                            static DIAG_COUNTER: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
                            let c = DIAG_COUNTER.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
                            if c < 50 || c % 10000 == 0 {
                                tracing::warn!(
                                    em, symbol = %intent.symbol, strategy = %intent.strategy,
                                    "P0-6 DIAG exchange gate rejected: {reason}"
                                );
                            }
                        }
                    }

                    if gate.approved {

                        self.exchange_seq = self.exchange_seq.wrapping_add(1);
                        let order_link_id = format!("oc_{}_{}", event.ts_ms, self.exchange_seq);

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
                        push_display_intent(&mut self.recent_intents, event.ts_ms, intent, Some(final_qty), format!("pending_exchange:{}", order_link_id));

                        // Dispatch to exchange / 派發到交易所
                        // I-08 雙軌止損：compute broker-side SL from stop config
                        let sl_pct = self.paper_state.stop_config_pct();
                        let broker_sl = if sl_pct > 0.0 {
                            Some(if intent.is_long {
                                event.last_price * (1.0 - sl_pct / 100.0)
                            } else {
                                event.last_price * (1.0 + sl_pct / 100.0)
                            })
                        } else {
                            None
                        };
                        if let Some(ref tx) = self.order_dispatch_tx {
                            let _ = tx.send(OrderDispatchRequest {
                                symbol: intent.symbol.clone(),
                                is_long: intent.is_long,
                                qty: final_qty,
                                price: event.last_price,
                                strategy: intent.strategy.clone(),
                                paper_fill_ts: event.ts_ms,
                                is_close: false,
                                order_link_id,
                                is_primary: true,
                                stop_loss: broker_sl,
                                take_profit: None,
                            });
                            // FUP-RACE: proactively mark mirror so reconciler
                            // won't orphan-close this position before the WS
                            // Fill arrives.
                            self.paper_state
                                .proactive_mirror_insert(&intent.symbol, intent.is_long);
                        }
                    } else if let Some(ref reason) = gate.rejected_reason {
                        strategy.on_rejection(intent, reason);
                        let mq = gate.verdict_info.as_ref().and_then(|vi| vi.modified_qty);
                        push_display_intent(&mut self.recent_intents, event.ts_ms, intent, mq, format!("rejected:{}", reason));
                    }
                } else {
                    // ═══ PAPER_ONLY MODE: simulate fill locally + optional shadow order ═══
                    // ═══ 紙盤模式：本地模擬成交 + 可選影子訂單 ═══
                    // EDGE-P3-1 A5: mirror the exchange branch — build features + context_id.
                    // EDGE-P3-1 A5：與交易所分支對齊，組裝 features + context_id。
                    let features = crate::edge_predictor::feature_builder::build_feature_vector(
                        intent,
                        event,
                        indicators.as_ref(),
                        atr_value,
                        &self.paper_state,
                    );
                    let context_id = make_context_id(em, &intent.symbol, event.ts_ms);
                    let result = self.intent_processor.process_with_features(
                        intent,
                        &self.governance,
                        &self.paper_state,
                        atr_value,
                        self.pipeline_kind.governance_profile(),
                        Some(&features),
                        Some(&context_id),
                        event.ts_ms,
                    );

                    // S-01: persist verdict via extracted helper
                    if let Some(ref vi) = result.verdict_info {
                        persist_verdict(&self.trading_tx, em, &intent.symbol, event.ts_ms, vi, em);
                    }

                    if result.submitted {
                        self.stats.total_intents += 1;
                        let mq = result.verdict_info.as_ref().and_then(|vi| vi.modified_qty);
                        push_display_intent(&mut self.recent_intents, event.ts_ms, intent, mq, "submitted".into());
                        // S-01: persist intent via extracted helper
                        // FUP-8 Phase 2: pass result.approved_qty (post-Kelly/P1 sizing) so
                        // paper's trading.intents.details.submitted_qty records the real sized
                        // qty instead of the 1e9 sentinel that intent.qty carries. Mirrors the
                        // exchange path at line ~643 which already passes gate.approved_qty.
                        // FUP-8 Phase 2：傳 result.approved_qty（Kelly/P1 sizing 後）
                        // 讓 paper 的 submitted_qty 記錄真實 sized qty，而非 intent.qty 攜帶的 1e9 sentinel。
                        persist_intent(&self.trading_tx, em, event.ts_ms, intent, result.approved_qty, event.last_price, em);

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
                            let was_open = self
                                .paper_state
                                .get_position(&intent.symbol)
                                .is_none();
                            let realized_pnl = self.paper_state.apply_fill(
                                &intent.symbol,
                                intent.is_long,
                                fill.fill_qty,
                                fill.fill_price,
                                fill.fee,
                                event.ts_ms,
                                &intent.strategy,
                            );
                            // EDGE-P3-1 R2: stamp entry_context_id for fresh opens only.
                            // Uses the same make_context_id signature used below for the
                            // Fill row (same em, symbol, ts_ms → same context_id).
                            // EDGE-P3-1 R2：僅開新倉時打 entry_context_id；加倉不覆蓋。
                            if was_open && realized_pnl == 0.0 {
                                let ctx = make_context_id(em, &intent.symbol, event.ts_ms);
                                self.paper_state.set_entry_context_id(&intent.symbol, &ctx);
                            }
                            self.stats.total_fills += 1;
                            push_capped(&mut self.recent_fills, TimestampedFill {
                                timestamp_ms: event.ts_ms,
                                symbol: intent.symbol.clone(),
                                is_long: intent.is_long,
                                qty: fill.fill_qty,
                                price: fill.fill_price,
                                fee: fill.fee,
                                realized_pnl,
                                strategy: intent.strategy.clone(),
                            }, 50);

                            if let Some(ref tx) = self.trading_tx {
                                // EDGE-P3-1 R2: this on_tick.rs path is the STRATEGY OPEN path
                                // (reached via signal → intent → apply_fill). It produces open or
                                // accumulate fills; close fills are emitted via emit_close_fill
                                // on the risk/strategy/fast_track paths. Leave entry_context_id
                                // empty here — the training JOIN reads it from close-fill rows.
                                // EDGE-P3-1 R2：此處走策略開倉路徑，不產生平倉 fill；留空即可。
                                let _ = tx.try_send(crate::database::TradingMsg::Fill {
                                    fill_id: make_fill_id(em, &intent.symbol, event.ts_ms),
                                    ts_ms: event.ts_ms,
                                    order_id: make_order_id(em, &intent.symbol, event.ts_ms),
                                    symbol: intent.symbol.clone(),
                                    side: if intent.is_long {
                                        "Buy".into()
                                    } else {
                                        "Sell".into()
                                    },
                                    qty: fill.fill_qty,
                                    price: fill.fill_price,
                                    fee: fill.fee,
                                    fee_rate: self.intent_processor.fee_rate(&intent.symbol),
                                    realized_pnl,
                                    strategy_name: intent.strategy.clone(),
                                    context_id: make_context_id(em, &intent.symbol, event.ts_ms),
                                    entry_context_id: String::new(),
                                    engine_mode: em.to_string(),
                                });
                            }

                            if let Some(ref tx) = self.stop_request_tx {
                                if let Some(pos) = self.paper_state.get_position(&intent.symbol) {
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
                                    is_primary: false,
                                    stop_loss: None,
                                    take_profit: None,
                                });
                            }
                        }
                    } else if let Some(ref reason) = result.rejected_reason {
                        strategy.on_rejection(intent, reason);
                        let mq = result.verdict_info.as_ref().and_then(|vi| vi.modified_qty);
                        push_display_intent(&mut self.recent_intents, event.ts_ms, intent, mq, format!("rejected:{}", reason));
                    }
                }
                intents.push(intent.clone());
                } // end StrategyAction::Open

                // StrategyAction::Close — collected for deferred execution after strategy loop
                // (borrow checker: strategies_mut() borrows self, can't call self methods inline)
                // StrategyAction::Close — 收集後在策略循環結束後延遲執行
                StrategyAction::Close { symbol, confidence: _, reason } => {
                    pending_strategy_closes.push((symbol.clone(), reason.clone()));
                }
                } // end match
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
                    push_display_intent(&mut self.recent_intents, event.ts_ms, &close_intent, None, format!("close_skipped:pending_{reason}"));
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
                    push_display_intent(&mut self.recent_intents, event.ts_ms, &close_intent, None, format!("close_dispatched:{reason}"));
                    close_confirmed_symbols.push(symbol.clone());
                } else {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: no position found / 策略平倉跳過：未找到倉位");
                    push_display_intent(&mut self.recent_intents, event.ts_ms, &close_intent, None, format!("close_skipped:no_position_{reason}"));
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
                    // PNL-FIX-1: close at this symbol's own latest price — strategies may
                    // close cross-symbol positions (after multi-symbol position tracking),
                    // so event.last_price (current tick) is wrong when symbol ≠ event.symbol.
                    // PNL-FIX-1：策略可能跨交易對平倉，必須以該交易對自己的最新價平倉。
                    if let Some((_il, _q, close_px, pnl)) =
                        self.close_position_at_symbol_market(symbol, event.ts_ms)
                    {
                        let tag = format!("strategy_close:{reason}");
                        self.emit_close_fill(symbol, is_long, qty, close_px, event.ts_ms, pnl, &tag, &ectx);
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
                    push_display_intent(&mut self.recent_intents, event.ts_ms, &close_intent, None, format!("close_filled:{reason}"));
                    close_confirmed_symbols.push(symbol.clone());
                } else {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: no position found / 策略平倉跳過：未找到倉位");
                    push_display_intent(&mut self.recent_intents, event.ts_ms, &close_intent, None, format!("close_skipped:no_position_{reason}"));
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
        self.paper_state.update_best_prices();
        let session_drawdown = self.paper_state.drawdown_pct();
        let daily_loss = self
            .intent_processor
            .daily_loss_pct_pub(self.paper_state.balance());
        // FIX-32: borrow instead of deep-cloning RiskConfig per tick.
        let risk_config = self.intent_processor.risk_config();
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
                crate::position_risk_evaluator::PositionRow {
                    symbol: p.symbol.clone(),
                    is_long: p.is_long,
                    qty: p.qty,
                    entry_price: p.entry_price,
                    entry_ts_ms: p.entry_ts_ms,
                    peak_price: p.best_price,
                    current_price,
                    atr_pct: self.price_tracker.compute_atr_pct(&p.symbol),
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
        let decisions = crate::position_risk_evaluator::evaluate_positions(
            &position_rows,
            daily_loss,
            session_drawdown,
            event.ts_ms,
            cost_edge_max_ratio,
            min_profit_to_close_pct,
            &risk_config,
        );

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
                    risk_closed_symbols.push(symbol.clone());
                    if is_exchange_mode {
                        if self.pending_close_symbols.contains(symbol) {
                            continue;
                        }
                        warn!(symbol = %symbol, reason = %reason, "risk close → exchange / 風控平倉 → 交易所");
                        let tag = format!("risk_close:{reason}");
                        self.execute_position_close(symbol, *is_long, *qty, event, true, &tag);
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
                        if let Some((_il, _q, close_px, pnl)) =
                            self.close_position_at_symbol_market(symbol, event.ts_ms)
                        {
                            let tag = format!("risk_close:{reason}");
                            self.emit_close_fill(symbol, *is_long, *qty, close_px, event.ts_ms, pnl, &tag, &ectx);
                            // P1-2 fix: update Kelly stats for risk-close (pre-existing omission).
                            // P1-2 修復：風控平倉也更新 Kelly 統計（既有遺漏）。
                            self.intent_processor.record_trade(symbol, pnl);
                        }
                        self.stats.total_stops += 1;
                        let tag = format!("risk_close:{reason}");
                        self.execute_position_close(symbol, *is_long, *qty, event, false, &tag);
                    }
                }
                RiskAction::HaltSession(reason) => {
                    // RRC-1-C4: Circuit breaker — halt + close all / 熔斷 — 暫停+全部平倉
                    warn!(reason = %reason, "SESSION HALTED / 會話暫停");
                    self.session_halted = true;
                    self.paper_paused = true;
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
                        let px = self
                            .latest_prices
                            .get(sym)
                            .copied()
                            .unwrap_or(event.last_price);
                        let ectx = self
                            .paper_state
                            .get_entry_context_id(sym)
                            .unwrap_or("")
                            .to_string();
                        if let Some(pnl) =
                            self.paper_state.close_position(sym, px, event.ts_ms)
                        {
                            self.emit_close_fill(sym, *il, *q, px, event.ts_ms, pnl, "risk_close:halt_session", &ectx);
                        }
                        self.stats.total_stops += 1;
                        self.execute_position_close(
                            sym,
                            *il,
                            *q,
                            event,
                            is_exchange_mode,
                            "risk_close:halt_session",
                        );
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

        if self.stats.total_ticks % 1000 == 0 {
            info!(
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
