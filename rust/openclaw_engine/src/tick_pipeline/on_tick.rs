//! on_tick pipeline processing — the core tick-by-tick orchestration loop.
//! on_tick 管線處理 — 核心逐 tick 編排循環。

use super::*;

impl TickPipeline {
    /// Process a single price event through the full pipeline.
    /// Returns a CanaryRecord when canary_mode is enabled (R07-2).
    /// 通過完整管線處理單個價格事件。
    /// 灰度模式啟用時返回 CanaryRecord。
    pub fn on_tick(&mut self, event: &PriceEvent) -> Option<CanaryRecord> {
        // Start timing the tick processing / 開始計時 tick 處理
        let tick_start = Instant::now();

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
            .insert(event.symbol.clone(), event.last_price);
        self.paper_state
            .set_latest_price(&event.symbol, event.last_price);
        // RRC-1-B2: Reset daily start balance at UTC midnight for daily loss tracking.
        // RRC-1-B2：UTC 午夜重置每日起始餘額，用於日損追蹤。
        self.intent_processor
            .maybe_reset_daily_balance(self.paper_state.balance(), event.ts_ms);
        // RRC-1-C1: Feed price to tracker for ATR computation + spike detection.
        // RRC-1-C1：餵入價格到追蹤器，用於 ATR 計算 + 尖峰偵測。
        self.price_tracker
            .record(&event.symbol, event.last_price, event.ts_ms);
        // Update per-symbol turnover for dynamic slippage (from ticker events)
        // 更新每交易對成交額用於動態滑點（來自 ticker 事件）
        if event.turnover_24h > 0.0 {
            self.paper_state
                .set_latest_turnover(&event.symbol, event.turnover_24h);

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
                    symbol: event.symbol.clone(),
                    last_price: event.last_price,
                    mark_price: 0.0,  // not available in PriceEvent yet
                    index_price: 0.0, // not available in PriceEvent yet
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
        if event.metadata.get("type").map(|t| t.as_str()) == Some("adl_notice") {
            if let Some(rank_str) = event.metadata.get("adl_rank") {
                if let Ok(rank) = rank_str.parse::<u32>() {
                    self.adl_alerts
                        .push_back((event.ts_ms, event.symbol.clone(), rank));
                    if self.adl_alerts.len() > 50 {
                        self.adl_alerts.pop_front();
                    }
                    if rank >= 3 {
                        info!(
                            symbol = %event.symbol, rank = rank,
                            "⚠ ADL rank HIGH — consider reducing position / ADL 排名高，考慮減倉"
                        );
                    }
                }
            }
        }

        // Session 11: feed trade & orderbook events into 1-minute aggregators.
        // Flushes happen at minute boundaries → MarketDataMsg::TradeAgg1m / ObSnapshot.
        // Session 11：將 trade/orderbook 事件餵入 1 分鐘聚合器，跨分鐘時 flush。
        if let Some(event_type) = event.metadata.get("type").map(|s| s.as_str()) {
            match event_type {
                "trade" => {
                    let side = event
                        .metadata
                        .get("side")
                        .and_then(|s| crate::database::aggregators::TradeSide::parse(s));
                    let qty = event
                        .metadata
                        .get("qty")
                        .and_then(|s| s.parse::<f64>().ok())
                        .unwrap_or(0.0);
                    if let Some(side) = side {
                        if let Some(msg) = self.trade_aggregator.record(
                            &event.symbol,
                            side,
                            qty,
                            event.last_price,
                            event.ts_ms,
                        ) {
                            if let Some(ref tx) = self.market_data_tx {
                                let _ = tx.try_send(msg);
                            }
                        }
                    }
                }
                "orderbook" => {
                    let bids: Vec<(f64, f64)> = event
                        .metadata
                        .get("bids5")
                        .and_then(|s| serde_json::from_str(s).ok())
                        .unwrap_or_default();
                    let asks: Vec<(f64, f64)> = event
                        .metadata
                        .get("asks5")
                        .and_then(|s| serde_json::from_str(s).ok())
                        .unwrap_or_default();
                    if !bids.is_empty() && !asks.is_empty() {
                        if let Some(msg) = self.ob_aggregator.record(
                            &event.symbol,
                            &bids,
                            &asks,
                            event.ts_ms,
                        ) {
                            if let Some(ref tx) = self.market_data_tx {
                                let _ = tx.try_send(msg);
                            }
                        }
                    }
                }
                _ => {}
            }
        }

        // Step 0: Fast track check — emergency actions before normal processing
        // PNL-4 (2026-04-12): price_drop_pct and margin_utilization_pct are
        // hardcoded 0.0 — flash-crash and margin-crisis branches inside
        // fast_track::evaluate_fast_track() are dead until something computes
        // them on each tick. The ONLY reachable CloseAll trigger today is
        // `risk_level >= CircuitBreaker`. Tracked as a separate follow-up.
        // PNL-4：price_drop / margin_util 仍硬編 0，閃崩/保證金危機分支死碼，
        // 唯一可觸發的 CloseAll 是 risk_level ≥ CircuitBreaker。
        let ft_action = crate::fast_track::evaluate_fast_track(
            self.governance.risk.level,
            0.0, // PNL-4 dead input — see note above
            0.0, // PNL-4 dead input — see note above
        );
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
                trigger_symbol = %event.symbol,
                trigger_price = event.last_price,
                "FAST_TRACK CloseAll fired — closing all positions / 快速通道全平觸發"
            );
            // PNL-FIX-1: must close each position at ITS OWN symbol's latest price,
            // not event.last_price (which is the triggering tick's price for ONE
            // symbol — applying it to all symbols inflated PnL by 1000-10000x in
            // the 2026-04-12 anomaly).
            // PNL-FIX-1：每個倉位必須以該交易對自己的最新價平倉，禁止使用 event.last_price。
            for sym in symbols {
                if let Some((il, q, px, pnl)) =
                    self.close_position_at_symbol_market(&sym, event.ts_ms)
                {
                    self.emit_close_fill(&sym, il, q, px, event.ts_ms, pnl, "fast_track");
                }
                self.stats.total_stops += 1;
            }
            // Measure elapsed time for fast-track exit / 計算快速通道退出的耗時
            let tick_duration_us = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, None, vec![], vec![], tick_duration_us);
        }

        // Step 0.5: H0 Gate pre-check (shadow mode: observe only) / H0 門控前置檢查
        self.h0_gate.update_price_ts(&event.symbol, event.ts_ms);
        let h0_result = self.h0_gate.check(&event.symbol, "linear", event.ts_ms);
        let h0_allowed = h0_result.allowed;
        if !h0_result.allowed {
            // Hard block: stops only / 硬阻斷：僅處理止損
            warn!(symbol = %event.symbol, reason = %h0_result.reason,
                "H0 BLOCKED — stops only / H0 阻斷 — 僅止損");
            // PNL-FIX-1: triggers may fire on positions whose symbol ≠ event.symbol;
            // close each at its own symbol's latest price (see fast_track block).
            // PNL-FIX-1：被觸發的倉位 symbol 可能 ≠ event.symbol，必須各自用自己的最新價平倉。
            for (sym, trigger) in &self.paper_state.check_stops(event.last_price, event.ts_ms) {
                if let Some((il, q, px, pnl)) =
                    self.close_position_at_symbol_market(sym, event.ts_ms)
                {
                    self.emit_close_fill(sym, il, q, px, event.ts_ms, pnl, &trigger.reason);
                }
                self.stats.total_stops += 1;
            }
            let dur = tick_start.elapsed().as_micros() as u64;
            return self.maybe_canary_record(event, None, vec![], vec![], dur);
        }
        if !h0_result.reason.is_empty() {
            debug!(symbol = %event.symbol, reason = %h0_result.reason,
                "H0 shadow would-block / H0 影子模式本應阻斷");
        }

        // Step 1: Kline aggregation — collect closed bars for DB write.
        // 步驟 1：K 線聚合 — 收集已關閉的 K 線用於 DB 寫入。
        let closed_bars = self.kline_manager.on_tick(
            &event.symbol,
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
                        symbol: event.symbol.clone(),
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
            let prev = self.last_close_price.insert(event.symbol.clone(), bar.close);
            let ret = match prev {
                Some(prev_close) if prev_close > 0.0 => (bar.close - prev_close) / prev_close,
                _ => 0.0,
            };
            self.black_swan.record_bar(&event.symbol, ret, bar.volume);
            let result = self.black_swan.check(&event.symbol, ret, bar.volume, event.ts_ms);
            use crate::database::black_swan_detector::BlackSwanSeverity;
            if !matches!(result.severity, BlackSwanSeverity::None) {
                warn!(
                    symbol = %event.symbol,
                    severity = ?result.severity,
                    votes = result.votes_for,
                    return_pct = format!("{:.4}%", ret * 100.0),
                    "BLACK SWAN signal / 黑天鵝信號"
                );
            }
        }

        // Step 2: Compute indicators (need enough 1m bars)
        // 步驟 2：計算指標（需要足夠的 1 分鐘 K 線）
        let indicators = self.compute_indicators(&event.symbol);

        // Store latest indicators for IPC snapshot / 存儲最新指標供 IPC 快照使用
        if let Some(ref ind) = indicators {
            self.latest_indicators
                .insert(event.symbol.clone(), ind.clone());
        }

        // Phase 1: Emit FeatureSnapshot to DB writer channel (non-blocking try_send).
        // Phase 1：發送 FeatureSnapshot 到 DB 寫入器通道（非阻塞 try_send）。
        if let (Some(ref tx), Some(ref ind)) = (&self.feature_tx, &indicators) {
            let snap = crate::feature_collector::FeatureSnapshot::new(
                event.symbol.clone(),
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
                if let Some((il, q, px, pnl)) =
                    self.close_position_at_symbol_market(sym, event.ts_ms)
                {
                    self.emit_close_fill(sym, il, q, px, event.ts_ms, pnl, &trigger.reason);
                    self.stats.total_stops += 1;
                    self.dispatch_close_order(sym, il, q, event, false);
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
                symbol = %event.symbol,
                elapsed_ms = event.ts_ms.saturating_sub(self.boot_ts_ms.unwrap_or(event.ts_ms)),
                cooldown_ms = self.boot_cooldown_ms,
                "PNL-3 boot cooldown — signals suppressed / 啟動冷卻期 — 信號已抑制"
            );
            vec![]
        } else if let Some(ref ind) = indicators {
            let input = snapshot_to_input(ind);
            self.signal_engine
                .evaluate(&event.symbol, "1m", &input, event.ts_ms)
        } else {
            vec![]
        };

        // Store recent signals for IPC snapshot (ring buffer, max 100)
        // 存儲最近信號供 IPC 快照使用（環形緩衝，最大 100）
        // Engine mode tag for DB record IDs — prevents cross-pipeline collisions.
        // 引擎模式標記用於 DB 記錄 ID — 防止跨管線 ID 碰撞。
        let em = self.pipeline_kind.db_mode();
        let mut signals_persisted_this_tick = 0u32;
        for sig in &signals {
            self.recent_signals.push_back(sig.clone());
            if self.recent_signals.len() > 100 {
                self.recent_signals.pop_front();
            }

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
                        signal_id: format!("sig-{}-{}", sig.source, sig.ts_ms),
                        ts_ms: sig.ts_ms,
                        symbol: sig.symbol.clone(),
                        strategy_name: sig.source.clone(),
                        timeframe: sig.timeframe.clone(),
                        signal_type: format!("{:?}", sig.direction),
                        strength: sig.confidence,
                        context_id: format!("ctx-{}-{}-{}", em, sig.symbol, sig.ts_ms),
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
                    self.paper_state.get_position(&event.symbol),
                    self.paper_state.balance(),
                    self.paper_state.drawdown_pct(),
                    self.linucb.as_ref(),
                    self.news_snapshot.as_ref(),
                    self.pipeline_kind.db_mode(),
                );
            }
        }

        // Step 4+5: Per-strategy dispatch + intent processing with rejection/fill callbacks (RC-04/RC-05).
        // 步驟 4+5：逐策略分派 + 意圖處理，含拒絕/成交回調。
        let ctx = TickContext {
            symbol: event.symbol.clone(),
            price: event.last_price,
            timestamp_ms: event.ts_ms,
            indicators: indicators.clone(),
            signals: signals.clone(),
            h0_allowed, // RRC-1-A1: real H0 gate result from Step 0.5
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
                if is_exchange_mode {
                    // ═══ EXCHANGE MODE: gates only, send order to exchange ═══
                    // ═══ 交易所模式：僅過門禁，發送訂單到交易所 ═══
                    let gate = self.intent_processor.process_gates_only(
                        intent,
                        &self.governance,
                        &self.paper_state,
                        atr_value,
                        self.pipeline_kind.governance_profile(),
                    );

                    // Persist Guardian verdict (all verdicts including rejections) / 持久化 Guardian 裁定（含拒絕）
                    if let (Some(ref tx), Some(ref vi)) = (&self.trading_tx, &gate.verdict_info) {
                        let _ = tx.try_send(crate::database::TradingMsg::RiskVerdict {
                            verdict_id: format!("vrd-{}-{}-{}", em, intent.symbol, event.ts_ms),
                            ts_ms: event.ts_ms,
                            intent_id: format!("intent-{}-{}-{}", em, intent.symbol, event.ts_ms),
                            context_id: format!("ctx-{}-{}-{}", em, intent.symbol, event.ts_ms),
                            symbol: intent.symbol.clone(),
                            verdict: vi.verdict.clone(),
                            risk_score: vi.risk_score,
                            reasons: vi.reasons.clone(),
                            modified_qty: vi.modified_qty,
                            engine_mode: self.pipeline_kind.db_mode().to_string(),
                        });
                    }

                    if gate.approved {
                        self.stats.total_intents += 1;

                        // Phase 3b fix: Emit Intent to trading_tx for PG persistence.
                        // Phase 3b 修復：發送 Intent 到 trading_tx 以持久化到 PG。
                        if let Some(ref tx) = self.trading_tx {
                            let _ = tx.try_send(crate::database::TradingMsg::Intent {
                                intent_id: format!("intent-{}-{}-{}", em, intent.symbol, event.ts_ms),
                                ts_ms: event.ts_ms,
                                signal_id: String::new(),
                                context_id: format!("ctx-{}-{}-{}", em, intent.symbol, event.ts_ms),
                                symbol: intent.symbol.clone(),
                                side: if intent.is_long {
                                    "Buy".into()
                                } else {
                                    "Sell".into()
                                },
                                qty: gate.approved_qty,
                                price: event.last_price,
                                order_type: intent.order_type.clone(),
                                strategy_name: intent.strategy.clone(),
                                engine_mode: self.pipeline_kind.db_mode().to_string(),
                            });
                        }

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

                        // M-2 (2026-04-11) audit fix: display the post-cap qty instead of
                        // the strategy's raw pre-cap qty (e.g. grid_trading's 1e9 sentinel).
                        // M-2 審計修復：顯示治理後 qty 而非策略原始 pre-cap qty
                        // （例如 grid_trading 的 1e9 哨兵值）。
                        let mut display_intent = intent.clone();
                        display_intent.qty = final_qty;
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: display_intent,
                            result: format!("pending_exchange:{}", order_link_id),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }

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
                        if let Some(ref tx) = self.shadow_order_tx {
                            let _ = tx.send(ShadowOrderRequest {
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
                        }
                    } else if let Some(ref reason) = gate.rejected_reason {
                        strategy.on_rejection(intent, reason);
                        // M-2: surface the post-Guardian capped qty if available so the
                        // GUI doesn't show e.g. grid_trading's 1e9 raw sentinel.
                        // M-2：可用時顯示 Guardian 治理後 qty，避免 GUI 顯示
                        // grid_trading 的 1e9 原始哨兵。
                        let mut display_intent = intent.clone();
                        if let Some(vi) = gate.verdict_info.as_ref() {
                            if let Some(mq) = vi.modified_qty {
                                display_intent.qty = mq;
                            }
                        }
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: display_intent,
                            result: format!("rejected:{}", reason),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }
                    }
                } else {
                    // ═══ PAPER_ONLY MODE: simulate fill locally + optional shadow order ═══
                    // ═══ 紙盤模式：本地模擬成交 + 可選影子訂單 ═══
                    let result = self.intent_processor.process(
                        intent,
                        &self.governance,
                        &self.paper_state,
                        atr_value,
                        self.pipeline_kind.governance_profile(),
                    );

                    // Persist Guardian verdict (all verdicts including rejections) / 持久化 Guardian 裁定（含拒絕）
                    if let (Some(ref tx), Some(ref vi)) = (&self.trading_tx, &result.verdict_info) {
                        let _ = tx.try_send(crate::database::TradingMsg::RiskVerdict {
                            verdict_id: format!("vrd-{}-{}-{}", em, intent.symbol, event.ts_ms),
                            ts_ms: event.ts_ms,
                            intent_id: format!("intent-{}-{}-{}", em, intent.symbol, event.ts_ms),
                            context_id: format!("ctx-{}-{}-{}", em, intent.symbol, event.ts_ms),
                            symbol: intent.symbol.clone(),
                            verdict: vi.verdict.clone(),
                            risk_score: vi.risk_score,
                            reasons: vi.reasons.clone(),
                            modified_qty: vi.modified_qty,
                            engine_mode: self.pipeline_kind.db_mode().to_string(),
                        });
                    }

                    if result.submitted {
                        self.stats.total_intents += 1;
                        // M-2: surface post-Guardian capped qty so the GUI doesn't
                        // show raw strategy sentinels (e.g. grid_trading 1e9).
                        let mut display_intent = intent.clone();
                        if let Some(ref vi) = result.verdict_info {
                            if let Some(mq) = vi.modified_qty {
                                display_intent.qty = mq;
                            }
                        }
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: display_intent,
                            result: "submitted".into(),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }

                        // Phase 3b fix: Emit Intent to trading_tx for PG persistence.
                        // Phase 3b 修復：發送 Intent 到 trading_tx 以持久化到 PG。
                        if let Some(ref tx) = self.trading_tx {
                            let _ = tx.try_send(crate::database::TradingMsg::Intent {
                                intent_id: format!("intent-{}-{}-{}", em, intent.symbol, event.ts_ms),
                                ts_ms: event.ts_ms,
                                signal_id: String::new(),
                                context_id: format!("ctx-{}-{}-{}", em, intent.symbol, event.ts_ms),
                                symbol: intent.symbol.clone(),
                                side: if intent.is_long {
                                    "Buy".into()
                                } else {
                                    "Sell".into()
                                },
                                qty: intent.qty,
                                price: event.last_price,
                                order_type: intent.order_type.clone(),
                                strategy_name: intent.strategy.clone(),
                                engine_mode: self.pipeline_kind.db_mode().to_string(),
                            });
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
                                continue;
                            }
                            strategy.on_fill(intent, &fill);
                            let realized_pnl = self.paper_state.apply_fill(
                                &intent.symbol,
                                intent.is_long,
                                fill.fill_qty,
                                fill.fill_price,
                                fill.fee,
                                event.ts_ms,
                            );
                            self.stats.total_fills += 1;
                            self.recent_fills.push_back(TimestampedFill {
                                timestamp_ms: event.ts_ms,
                                symbol: intent.symbol.clone(),
                                is_long: intent.is_long,
                                qty: fill.fill_qty,
                                price: fill.fill_price,
                                fee: fill.fee,
                                strategy: intent.strategy.clone(),
                            });
                            if self.recent_fills.len() > 50 {
                                self.recent_fills.pop_front();
                            }

                            if let Some(ref tx) = self.trading_tx {
                                let _ = tx.try_send(crate::database::TradingMsg::Fill {
                                    fill_id: format!("fill-{}-{}-{}", em, intent.symbol, event.ts_ms),
                                    ts_ms: event.ts_ms,
                                    order_id: format!("order-{}-{}-{}", em, intent.symbol, event.ts_ms),
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
                                    context_id: format!("ctx-{}-{}-{}", em, intent.symbol, event.ts_ms),
                                    engine_mode: self.pipeline_kind.db_mode().to_string(),
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
                            if let Some(ref tx) = self.shadow_order_tx {
                                self.exchange_seq = self.exchange_seq.wrapping_add(1);
                                let _ = tx.send(ShadowOrderRequest {
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
                        // M-2: surface post-Guardian capped qty if available.
                        let mut display_intent = intent.clone();
                        if let Some(ref vi) = result.verdict_info {
                            if let Some(mq) = vi.modified_qty {
                                display_intent.qty = mq;
                            }
                        }
                        self.recent_intents.push_back(TimestampedIntent {
                            timestamp_ms: event.ts_ms,
                            intent: display_intent,
                            result: format!("rejected:{}", reason),
                        });
                        if self.recent_intents.len() > 50 {
                            self.recent_intents.pop_front();
                        }
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
            // P2 修復：合成 intent 供監控/審計（recent_intents 環形緩衝）。
            let close_intent = crate::intent_processor::OrderIntent {
                symbol: symbol.clone(),
                is_long: false, // direction filled in below if position found
                qty: 0.0,
                confidence: 0.0,
                strategy: format!("strategy_close:{reason}"),
                order_type: "market".into(),
                limit_price: None,
            };
            if is_exchange_mode {
                if self.pending_close_symbols.contains(symbol) {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: pending close exists / 策略平倉跳過：已有待處理平倉");
                    self.recent_intents.push_back(TimestampedIntent {
                        timestamp_ms: event.ts_ms,
                        intent: close_intent,
                        result: format!("close_skipped:pending_{reason}"),
                    });
                    if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    close_skipped_symbols.push(symbol.clone());
                    continue;
                }
                if let Some(pos) = self.paper_state.get_position(symbol) {
                    let is_long = pos.is_long;
                    let qty = pos.qty;
                    info!(symbol = %symbol, is_long = %is_long, qty = %qty, reason = %reason,
                          "strategy close → exchange / 策略平倉 → 交易所");
                    self.dispatch_close_order(symbol, is_long, qty, event, true);
                    self.recent_intents.push_back(TimestampedIntent {
                        timestamp_ms: event.ts_ms,
                        intent: close_intent,
                        result: format!("close_dispatched:{reason}"),
                    });
                    if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    close_confirmed_symbols.push(symbol.clone());
                } else {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: no position found / 策略平倉跳過：未找到倉位");
                    self.recent_intents.push_back(TimestampedIntent {
                        timestamp_ms: event.ts_ms,
                        intent: close_intent,
                        result: format!("close_skipped:no_position_{reason}"),
                    });
                    if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    close_skipped_symbols.push(symbol.clone());
                }
            } else {
                if let Some(pos) = self.paper_state.get_position(symbol) {
                    let is_long = pos.is_long;
                    let qty = pos.qty;
                    info!(symbol = %symbol, is_long = %is_long, qty = %qty, reason = %reason,
                          "strategy close (paper) / 策略平倉（紙盤）");
                    // PNL-FIX-1: close at this symbol's own latest price — strategies may
                    // close cross-symbol positions (after multi-symbol position tracking),
                    // so event.last_price (current tick) is wrong when symbol ≠ event.symbol.
                    // PNL-FIX-1：策略可能跨交易對平倉，必須以該交易對自己的最新價平倉。
                    if let Some((_il, _q, close_px, pnl)) =
                        self.close_position_at_symbol_market(symbol, event.ts_ms)
                    {
                        self.emit_close_fill(symbol, is_long, qty, close_px, event.ts_ms, pnl, reason);
                        // Update Kelly stats for future sizing / 更新 Kelly 統計供未來 sizing 使用
                        self.intent_processor.record_trade(symbol, pnl);
                        // Push to recent_fills ring buffer / 推入最近成交環形緩衝
                        let fr = self.intent_processor.fee_rate(symbol);
                        self.recent_fills.push_back(TimestampedFill {
                            timestamp_ms: event.ts_ms,
                            symbol: symbol.clone(),
                            is_long,
                            qty,
                            price: close_px,
                            fee: qty * close_px * fr,
                            strategy: format!("strategy_close:{reason}"),
                        });
                        if self.recent_fills.len() > 50 {
                            self.recent_fills.pop_front();
                        }
                        // Track consecutive losses for risk evaluator
                        // 追蹤連續虧損供風控評估器使用
                        if pnl < 0.0 {
                            *self.consecutive_losses.entry(symbol.clone()).or_insert(0) += 1;
                        } else {
                            self.consecutive_losses.remove(symbol);
                        }
                    }
                    // Shadow order: mirror close to Demo API / 影子訂單：鏡像平倉到 Demo API
                    self.dispatch_close_order(symbol, is_long, qty, event, false);
                    self.recent_intents.push_back(TimestampedIntent {
                        timestamp_ms: event.ts_ms,
                        intent: close_intent,
                        result: format!("close_filled:{reason}"),
                    });
                    if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
                    close_confirmed_symbols.push(symbol.clone());
                } else {
                    warn!(symbol = %symbol, reason = %reason, "strategy close skipped: no position found / 策略平倉跳過：未找到倉位");
                    self.recent_intents.push_back(TimestampedIntent {
                        timestamp_ms: event.ts_ms,
                        intent: close_intent,
                        result: format!("close_skipped:no_position_{reason}"),
                    });
                    if self.recent_intents.len() > 50 { self.recent_intents.pop_front(); }
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
        let risk_config = self.intent_processor.risk_config().clone();
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
        // 0.8 in tests where store is not wired).
        // ARCH-RC1 1C-2-B：從 BudgetConfig store 即時讀取；未接線時回退 0.8。
        let cost_edge_max_ratio = self.current_cost_edge_max_ratio();
        let decisions = crate::position_risk_evaluator::evaluate_positions(
            &position_rows,
            daily_loss,
            session_drawdown,
            event.ts_ms,
            cost_edge_max_ratio,
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
                        self.dispatch_close_order(symbol, *is_long, *qty, event, true);
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
                        if let Some((_il, _q, close_px, pnl)) =
                            self.close_position_at_symbol_market(symbol, event.ts_ms)
                        {
                            self.emit_close_fill(symbol, *is_long, *qty, close_px, event.ts_ms, pnl, &reason);
                            // P1-2 fix: update Kelly stats for risk-close (pre-existing omission).
                            // P1-2 修復：風控平倉也更新 Kelly 統計（既有遺漏）。
                            self.intent_processor.record_trade(symbol, pnl);
                        }
                        self.stats.total_stops += 1;
                        self.dispatch_close_order(symbol, *is_long, *qty, event, false);
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
                        if let Some(pnl) =
                            self.paper_state.close_position(sym, px, event.ts_ms)
                        {
                            self.emit_close_fill(sym, *il, *q, px, event.ts_ms, pnl, "halt_session");
                        }
                        self.stats.total_stops += 1;
                        self.dispatch_close_order(sym, *il, *q, event, is_exchange_mode);
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

            // GAP-7 / idle-writer-fix #4: emit PositionSnapshot for every open
            // paper position every 1000 ticks so trading.position_snapshots
            // stays populated for ML training.
            // GAP-7：每 1000 ticks 發射持倉快照以填充 position_snapshots 表。
            if let Some(ref tx) = self.trading_tx {
                for pos in self.paper_state.positions() {
                    let mark_price = *self
                        .latest_prices
                        .get(&pos.symbol)
                        .unwrap_or(&pos.entry_price);
                    let unrealized_pnl = if pos.is_long {
                        (mark_price - pos.entry_price) * pos.qty
                    } else {
                        (pos.entry_price - mark_price) * pos.qty
                    };
                    let msg = crate::database::TradingMsg::PositionSnapshot {
                        ts_ms: event.ts_ms,
                        symbol: pos.symbol.clone(),
                        side: if pos.is_long {
                            "long".to_string()
                        } else {
                            "short".to_string()
                        },
                        qty: pos.qty,
                        entry_price: pos.entry_price,
                        mark_price,
                        unrealized_pnl,
                        engine_mode: self.pipeline_kind.db_mode().to_string(),
                    };
                    let _ = tx.try_send(msg);
                }
            }
        }

        // Measure elapsed time for the full tick / 計算完整 tick 處理耗時
        let tick_duration_us = tick_start.elapsed().as_micros() as u64;
        self.maybe_canary_record(event, indicators, signals, intents, tick_duration_us)
    }

    fn maybe_canary_record(
        &self,
        event: &PriceEvent,
        indicators: Option<IndicatorSnapshot>,
        signals: Vec<Signal>,
        intents: Vec<crate::intent_processor::OrderIntent>,
        tick_duration_us: u64,
    ) -> Option<CanaryRecord> {
        if !self.canary_mode {
            return None;
        }
        Some(CanaryRecord {
            schema_version: "1.0.0".into(),
            source: "rust_engine".into(),
            tick_number: self.stats.total_ticks,
            timestamp_ms: event.ts_ms,
            symbol: event.symbol.clone(),
            price: event.last_price,
            indicators,
            signals,
            order_intents: intents,
            paper_state: self.paper_state.export_state(),
            stats: self.stats.clone(),
            tick_duration_us,
        })
    }

    fn compute_indicators(&self, symbol: &str) -> Option<IndicatorSnapshot> {
        let ohlcv = self.kline_manager.get_ohlcv(symbol, "1m", Some(100))?;
        if ohlcv.close.len() < 30 {
            return None;
        }
        Some(IndicatorEngine::compute_all(
            &ohlcv.high,
            &ohlcv.low,
            &ohlcv.close,
            &ohlcv.volume,
        ))
    }
}
