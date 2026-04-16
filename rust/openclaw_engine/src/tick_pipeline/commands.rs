//! Pipeline command handlers — external order submission, risk status,
//! fill handling, close operations, snapshots, system mode.
//! 管線命令處理 — 外部訂單提交、風控狀態、成交處理、
//! 平倉操作、快照、系統模式。

use super::*;
use super::on_tick_helpers::{push_capped, make_context_id, make_intent_id, make_verdict_id, make_fill_id};

impl TickPipeline {

    /// ARCH-RC1 1C-3-B: Build Rust-native risk runtime status snapshot.
    ///
    /// Intentionally exposes the real state machine rather than synthesising
    /// the deprecated Python `RiskManager.get_status()` shape. Callers (new
    /// GUI Risk tab, `RiskViewClient`) must bind to these fields directly.
    ///
    /// Fields:
    /// - `governor_tier`: current RiskGovernorSm level (Normal/Cautious/Reduced/
    ///   Defensive/CircuitBreaker/ManualReview)
    /// - `consecutive_losses_by_symbol`: per-symbol loss streak map
    /// - `boot_cooldown_remaining_ms`: remaining ms of post-boot signal
    ///   suppression window (0 if boot_ts_ms unset or window expired)
    /// - `paper_paused`: IPC pause flag
    /// - `session_halted`: news/guardian hard-halt flag
    ///
    /// ARCH-RC1 1C-3-B：組裝 Rust 原生風控運行時狀態快照（新 GUI 直接綁定這些欄位）。
    /// Test-only helper: seed `latest_indicators` so cost-gate ATR lookups
    /// in `submit_external_order` succeed without driving a full on_tick.
    /// 測試專用：種入 latest_indicators 以便 submit_external_order 走通成本門。
    #[cfg(test)]
    pub fn set_latest_indicators_for_test(&mut self, symbol: &str, snap: IndicatorSnapshot) {
        self.latest_indicators.insert(symbol.to_string(), snap);
    }

    /// ARCH-RC1 1C-3-F: External (non-strategy) paper-side order submission.
    /// Drives the same IntentProcessor pipeline strategies use, so all gates
    /// (Guardian / Kelly / P1 cap / risk gate / cost gate) apply uniformly.
    /// Returns a JSON envelope on success: `{order_id, fill_qty, fill_price, fee}`.
    /// Reject reasons (paused / halted / unknown symbol / no price / no atr /
    /// gate rejection) bubble up as Err(String).
    /// ARCH-RC1 1C-3-F：外部紙盤訂單入口（非策略），與策略走同一條 IntentProcessor 管線。
    pub fn submit_external_order(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        order_type: &str,
        limit_price: Option<f64>,
        confidence: f64,
        strategy: &str,
    ) -> Result<String, String> {
        if self.paper_paused {
            return Err("paper_paused".into());
        }
        if self.session_halted {
            return Err("session_halted".into());
        }
        if !(qty > 0.0) {
            return Err(format!("invalid qty: {qty}"));
        }
        let price = self.paper_state.latest_price(symbol).unwrap_or(0.0);
        if !(price > 0.0) {
            return Err(format!("no latest price for {symbol}"));
        }
        // ATR drives the cost gate; absent ATR is fail-closed (matches on_tick path).
        // ATR 由 latest_indicators 取得；缺失即 fail-closed（與 on_tick 行為一致）。
        let atr_value = self
            .latest_indicators
            .get(symbol)
            .and_then(|i| i.atr_14.as_ref())
            .map(|a| a.atr)
            .unwrap_or(0.0);

        let intent = crate::intent_processor::OrderIntent {
            symbol: symbol.to_string(),
            is_long,
            qty,
            confidence,
            strategy: strategy.to_string(),
            order_type: order_type.to_string(),
            limit_price,
            // Command-dispatched intents (manual / IPC-triggered) have no
            // strategy-side confluence or persistence state to pass through.
            // 指令派發的 intent 無策略端 confluence/persistence。
            confluence_score: None,
            persistence_elapsed_ms: None,
        };

        let result = self
            .intent_processor
            .process(&intent, &self.governance, &self.paper_state, atr_value, GovernanceProfile::Exploration);

        // Persist Guardian verdict (all verdicts including rejections) / 持久化 Guardian 裁定（含拒絕）
        if let (Some(ref tx), Some(ref vi)) = (&self.trading_tx, &result.verdict_info) {
            let now_ms_v = openclaw_core::now_ms();
            let em_v = self.effective_engine_mode();
            let _ = tx.try_send(crate::database::TradingMsg::RiskVerdict {
                verdict_id: make_verdict_id(em_v, symbol, now_ms_v),
                ts_ms: now_ms_v,
                intent_id: make_intent_id(em_v, symbol, now_ms_v),
                context_id: make_context_id(em_v, symbol, now_ms_v),
                symbol: symbol.to_string(),
                verdict: vi.verdict.clone(),
                risk_score: vi.risk_score,
                reasons: vi.reasons.clone(),
                modified_qty: vi.modified_qty,
                engine_mode: em_v.to_string(),
            });
        }

        if !result.submitted {
            return Err(result
                .rejected_reason
                .unwrap_or_else(|| "rejected_unknown".into()));
        }
        let mut fill = result.fill.ok_or_else(|| "submitted_but_no_fill".to_string())?;

        // Instrument-aware rounding (mirrors on_tick paper path).
        // 合約精度取整（與 on_tick 紙盤分支一致）。
        if let Some(ref icache) = self.instrument_cache {
            if let Some(spec) = icache.get(symbol) {
                fill.fill_qty = spec.round_qty(fill.fill_qty);
                fill.fill_price = spec.round_price(fill.fill_price);
                if fill.fill_qty <= 0.0 && spec.min_qty > 0.0 {
                    let notional = spec.min_qty * fill.fill_price;
                    if notional <= self.paper_state.balance() * 0.10 {
                        fill.fill_qty = spec.min_qty;
                    }
                }
            }
        }
        if !(fill.fill_qty > 0.0) {
            return Err("fill_qty rounded to 0".into());
        }

        let now_ms = openclaw_core::now_ms();
        // EDGE-P3-1 R2: Capture open/close state + entry_context_id BEFORE apply_fill
        // (apply_fill may consume the position on a close, erasing the id we need).
        // was_open=true + realized==0 → fresh open; was_open=false + realized!=0 → close
        // of opposite direction; was_open=false + realized==0 → accumulate same direction.
        // EDGE-P3-1 R2：關倉前先捕獲 entry_context_id（apply_fill 平倉會清除 position）。
        let was_open = self.paper_state.get_position(symbol).is_none();
        let existing_entry_ctx = self
            .paper_state
            .get_entry_context_id(symbol)
            .unwrap_or("")
            .to_string();
        let realized_pnl = self.paper_state.apply_fill(
            symbol,
            is_long,
            fill.fill_qty,
            fill.fill_price,
            fill.fee,
            now_ms,
            strategy,
        );

        // EDGE-P3-1 R2: entry_context_id stamping for fresh opens — must reuse the
        // SAME context_id value that will be written to the Fill row below (same
        // em, symbol, now_ms → deterministic make_context_id).
        // EDGE-P3-1 R2：僅新開倉打 entry_context_id；加倉不覆蓋。context_id 與下方 Fill 寫入相同。
        if was_open && realized_pnl == 0.0 {
            let em_pre = self.effective_engine_mode();
            let ctx_pre = make_context_id(em_pre, symbol, now_ms);
            self.paper_state.set_entry_context_id(symbol, &ctx_pre);
        }

        // EDGE-P3-1 R2: entry_context_id for the Fill row emission below.
        // Close fill (realized_pnl != 0) carries the pre-close entry's id;
        // open/accumulate fills leave it empty (JOIN is from decision_features →
        // close fill's entry_context_id only).
        // EDGE-P3-1 R2：平倉 Fill 才帶 entry_context_id；開倉/加倉留空。
        let fill_entry_ctx = if realized_pnl != 0.0 {
            existing_entry_ctx
        } else {
            String::new()
        };

        self.stats.total_intents += 1;
        self.stats.total_fills += 1;

        push_capped(&mut self.recent_intents, TimestampedIntent {
            timestamp_ms: now_ms,
            intent: intent.clone(),
            result: "submitted".into(),
        }, 50);
        push_capped(&mut self.recent_fills, TimestampedFill {
            timestamp_ms: now_ms,
            symbol: symbol.to_string(),
            is_long,
            qty: fill.fill_qty,
            price: fill.fill_price,
            fee: fill.fee,
            realized_pnl,
            strategy: strategy.to_string(),
        }, 50);

        let order_id = format!("ext-{symbol}-{now_ms}");

        // Persistence parity: emit Intent + Fill to PG writer when wired.
        // 持久化對等：trading_tx 已接時，發 Intent + Fill 到 PG writer。
        if let Some(ref tx) = self.trading_tx {
            let em = self.effective_engine_mode();
            let context_id = make_context_id(em, symbol, now_ms);
            // FUP-8: populate details (see on_tick_helpers::persist_intent).
            // Sentinel guard mirrors on_tick_helpers — IPC command path shouldn't
            // normally carry 1e9 but stay consistent for downstream analysts.
            // 哨兵旗標與 on_tick_helpers 對齊：IPC 路徑一般不會有 1e9，但為分析一致性保留。
            let is_sentinel = qty >= 1e9;
            let details = serde_json::json!({
                "strategy": strategy,
                "confidence": intent.confidence,
                "submitted_qty": if is_sentinel { serde_json::Value::Null } else { serde_json::json!(qty) },
                "is_sentinel": is_sentinel,
                "is_long": is_long,
                "source": "command",
            });
            let _ = tx.try_send(crate::database::TradingMsg::Intent {
                intent_id: make_intent_id(em, symbol, now_ms),
                ts_ms: now_ms,
                signal_id: String::new(),
                context_id: context_id.clone(),
                symbol: symbol.to_string(),
                side: if is_long { "Buy".into() } else { "Sell".into() },
                qty,
                price,
                order_type: order_type.to_string(),
                strategy_name: strategy.to_string(),
                engine_mode: em.to_string(),
                details: Some(details),
            });
            let _ = tx.try_send(crate::database::TradingMsg::Fill {
                fill_id: make_fill_id(em, symbol, now_ms),
                ts_ms: now_ms,
                order_id: order_id.clone(),
                symbol: symbol.to_string(),
                side: if is_long { "Buy".into() } else { "Sell".into() },
                qty: fill.fill_qty,
                price: fill.fill_price,
                fee: fill.fee,
                fee_rate: self.intent_processor.fee_rate(symbol),
                realized_pnl,
                strategy_name: strategy.to_string(),
                context_id,
                entry_context_id: fill_entry_ctx,
                engine_mode: em.to_string(),
            });
        }

        Ok(serde_json::json!({
            "order_id": order_id,
            "fill_qty": fill.fill_qty,
            "fill_price": fill.fill_price,
            "fee": fill.fee,
            "realized_pnl": realized_pnl,
        })
        .to_string())
    }

    pub fn risk_runtime_status_json(&self, now_ms: u64) -> serde_json::Value {
        let boot_remaining_ms = match self.boot_ts_ms {
            Some(boot_ts) => {
                let elapsed = now_ms.saturating_sub(boot_ts);
                self.boot_cooldown_ms.saturating_sub(elapsed)
            }
            None => 0,
        };
        serde_json::json!({
            "governor_tier": self.governance.risk.snapshot_level().to_string(),
            "consecutive_losses_by_symbol": self.consecutive_losses,
            "boot_cooldown_remaining_ms": boot_remaining_ms,
            "boot_cooldown_total_ms": self.boot_cooldown_ms,
            "paper_paused": self.paper_paused,
            "session_halted": self.session_halted,
        })
    }

    /// ARCH-RC1 1C-3-B-2: minimum interval (ms) between two operator-driven
    /// governor de-escalations. Default 24h. Demo phase only — for live this
    /// should be persisted to PG so a restart doesn't reset the cooldown.
    /// ARCH-RC1 1C-3-B-2：兩次 operator 降級之間的最短間隔（24h）。
    pub const GOVERNOR_DE_ESCALATION_COOLDOWN_MS: u64 = 24 * 60 * 60 * 1000;

    /// Whitelist of valid reason codes for `force_governor_tier_looser`.
    /// `force_governor_tier_looser` 的合法 reason code 白名單。
    pub const VALID_DE_ESCALATION_REASONS: &'static [&'static str] =
        &["false_positive", "root_cause_fixed", "accept_risk"];

    /// Parse a tier name (case-insensitive) into a `RiskLevel`.
    /// Accepts both display form ("CIRCUIT_BREAKER") and friendly aliases.
    /// 將 tier 名稱（大小寫不敏感）解析為 `RiskLevel`。
    pub fn parse_risk_level(s: &str) -> Result<openclaw_core::sm::risk_gov::RiskLevel, String> {
        use openclaw_core::sm::risk_gov::RiskLevel;
        match s.to_ascii_uppercase().as_str() {
            "NORMAL" => Ok(RiskLevel::Normal),
            "CAUTIOUS" => Ok(RiskLevel::Cautious),
            "REDUCED" => Ok(RiskLevel::Reduced),
            "DEFENSIVE" => Ok(RiskLevel::Defensive),
            "CIRCUIT_BREAKER" | "CIRCUITBREAKER" => Ok(RiskLevel::CircuitBreaker),
            "MANUAL_REVIEW" | "MANUALREVIEW" => Ok(RiskLevel::ManualReview),
            other => Err(format!("unknown risk tier: {other}")),
        }
    }

    /// ARCH-RC1 1C-3-B-2: in-memory cooldown getter (testable).
    /// ARCH-RC1 1C-3-B-2：in-memory 冷卻時間 getter（可測）。
    pub fn last_governor_de_escalation_ms(&self) -> Option<u64> {
        self.last_governor_de_escalation_ms
    }

    /// ARCH-RC1 1C-3-B-2: helper for tests to seed cooldown state.
    /// ARCH-RC1 1C-3-B-2：測試輔助設定冷卻時間戳。
    pub fn set_last_governor_de_escalation_ms(&mut self, ts: Option<u64>) {
        self.last_governor_de_escalation_ms = ts;
    }

    /// PNL-3 / Session 12: Update boot cooldown at runtime via IPC.
    /// Clamped to [0, 1h]. Returns the value actually applied.
    /// PNL-3：運行時更新啟動冷卻期，鉗制到 [0, 1h]。
    pub fn set_boot_cooldown_ms(&mut self, ms: u64) -> u64 {
        let v = ms.min(3_600_000);
        self.boot_cooldown_ms = v;
        v
    }

    pub fn boot_cooldown_ms(&self) -> u64 {
        self.boot_cooldown_ms
    }

    /// DB-RUN-1: Set signals heartbeat interval at runtime. 0 disables throttling.
    /// DB-RUN-1：運行時設定 signals 心跳間隔，0=關閉節流。
    pub fn set_signals_heartbeat_ms(&mut self, ms: u64) -> u64 {
        self.signals_heartbeat_ms = ms.min(3_600_000);
        self.signals_heartbeat_ms
    }

    pub fn signals_heartbeat_ms(&self) -> u64 {
        self.signals_heartbeat_ms
    }

    pub fn signals_throttled(&self) -> u64 {
        self.signals_throttled
    }

    pub fn context_throttled(&self) -> u64 {
        self.context_throttled
    }



    /// EXT-1: Apply a confirmed fill from the exchange to paper_state.
    /// Called by event_consumer when exchange confirms a fill for a pending order.
    /// EXT-1：將交易所確認的成交應用到 paper_state。
    pub fn apply_confirmed_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        fill_price: f64,
        fee: f64,
        ts_ms: u64,
        strategy: &str,
        order_link_id: &str,
    ) {
        // EDGE-P3-1 R2: snapshot was_open + existing entry_context_id BEFORE apply_fill.
        // Exchange-confirmed fills can be open/close/accumulate; thread id on close fills.
        // EDGE-P3-1 R2：apply_fill 前先捕獲 was_open 與 existing entry_context_id。
        let was_open = self.paper_state.get_position(symbol).is_none();
        let existing_entry_ctx = self
            .paper_state
            .get_entry_context_id(symbol)
            .unwrap_or("")
            .to_string();
        let realized_pnl = self
            .paper_state
            .apply_fill(symbol, is_long, qty, fill_price, fee, ts_ms, strategy);
        // EDGE-P3-1 R2: stamp entry_context_id on fresh exchange-confirmed opens.
        // Uses the same deterministic make_context_id as the Fill row below.
        // EDGE-P3-1 R2：僅交易所確認的開新倉打 entry_context_id。
        if was_open && realized_pnl == 0.0 {
            let em_pre = self.effective_engine_mode();
            let ctx_pre = make_context_id(em_pre, symbol, ts_ms);
            self.paper_state.set_entry_context_id(symbol, &ctx_pre);
        }
        self.stats.total_fills += 1;
        // Update Kelly stats on exchange fill (previously missing — QC P2-2 fix).
        // Non-zero realized_pnl indicates a position close (open fills return 0.0).
        // 交易所成交時更新 Kelly 統計（先前遺漏 — QC P2-2 修復）。
        // 非零 realized_pnl 表示平倉成交（開倉成交返回 0.0）。
        if realized_pnl.abs() > f64::EPSILON {
            self.intent_processor.record_trade(symbol, realized_pnl);
        }
        // Clear pending_close flag if this was a close fill / 如果是平倉成交，清除待處理平倉標記
        self.pending_close_symbols.remove(symbol);

        push_capped(&mut self.recent_fills, TimestampedFill {
            timestamp_ms: ts_ms,
            symbol: symbol.to_string(),
            is_long,
            qty,
            price: fill_price,
            fee,
            realized_pnl,
            strategy: strategy.to_string(),
        }, 50);

        if let Some(ref tx) = self.trading_tx {
            let em = self.effective_engine_mode();
            let fr = self.intent_processor.fee_rate(symbol);
            // EDGE-P3-1 R2: close fills carry the pre-close entry's id; opens stay empty.
            // EDGE-P3-1 R2：平倉 fill 帶 entry_context_id；開倉/加倉留空。
            let fill_entry_ctx = if realized_pnl != 0.0 {
                existing_entry_ctx.clone()
            } else {
                String::new()
            };
            let _ = tx.try_send(crate::database::TradingMsg::Fill {
                fill_id: make_fill_id(em, symbol, ts_ms),
                ts_ms,
                order_id: order_link_id.to_string(),
                symbol: symbol.to_string(),
                side: if is_long { "Buy".into() } else { "Sell".into() },
                qty,
                price: fill_price,
                fee,
                fee_rate: fr,
                realized_pnl,
                strategy_name: strategy.to_string(),
                context_id: make_context_id(em, symbol, ts_ms),
                entry_context_id: fill_entry_ctx,
                engine_mode: em.to_string(),
            });
        }

        info!(
            symbol = %symbol, qty = %qty, price = %fill_price,
            order_link_id = %order_link_id,
            "confirmed fill applied / 已應用交易所確認成交"
        );
    }

    /// RRC-1-C2 / R-03: Execute a position close — dispatches to shadow/exchange channel
    /// and marks the symbol as pending-close to prevent duplicate dispatches.
    /// `trigger_tag` flows through OrderDispatchRequest.strategy → PendingOrder.strategy →
    /// apply_confirmed_fill → trading.fills.strategy_name, so callers must pass the causal
    /// tag (e.g. "strategy_close:funding_arb_exit", "risk_close:fast_track"). P0-4 R1:
    /// previously hardcoded "risk_check" which collapsed three distinct trigger sources.
    /// RRC-1-C2 / R-03：執行平倉 — 派發到影子/交易所通道，並標記 pending 防止重複派發。
    /// `trigger_tag` 穿透至 trading.fills.strategy_name — caller 必須傳真實因果 tag。
    pub(super) fn execute_position_close(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        event: &PriceEvent,
        is_primary: bool,
        trigger_tag: &str,
    ) {
        if let Some(ref tx) = self.order_dispatch_tx {
            self.exchange_seq = self.exchange_seq.wrapping_add(1);
            let prefix = if is_primary { "oc_risk" } else { "sh_risk" };
            let _ = tx.send(OrderDispatchRequest {
                symbol: symbol.to_string(),
                is_long: !is_long,
                qty,
                price: event.last_price,
                strategy: trigger_tag.to_string(),
                paper_fill_ts: event.ts_ms,
                is_close: true,
                order_link_id: format!("{}_{}_{}", prefix, event.ts_ms, self.exchange_seq),
                is_primary,
                stop_loss: None,
                take_profit: None,
            });
            if is_primary {
                self.pending_close_symbols.insert(symbol.to_string());
            }
        }
    }

    /// R-02: Reconcile pending_close_symbols against actual open positions.
    /// Removes entries for symbols that no longer have an open position (fill was processed
    /// but the flag was not cleared, or the exchange order was silently dropped).
    /// Should be called after fill processing and/or by periodic IPC health checks.
    ///
    /// R-02：將 pending_close_symbols 與實際持倉對照清理。
    /// 移除已無對應倉位的條目（成交已處理但標記未清除，或交易所訂單靜默丟失）。
    /// 應在成交處理後和/或 IPC 定期健康檢查時調用。
    pub(crate) fn reconcile_pending_exchange_orders(&mut self) {
        if self.pending_close_symbols.is_empty() {
            return;
        }
        let open_symbols: std::collections::HashSet<String> = self
            .paper_state
            .positions()
            .iter()
            .map(|p| p.symbol.clone())
            .collect();
        let before = self.pending_close_symbols.len();
        self.pending_close_symbols.retain(|s| open_symbols.contains(s));
        let removed = before - self.pending_close_symbols.len();
        if removed > 0 {
            tracing::debug!(removed, "reconcile_pending_exchange_orders: cleared stale pending-close flags / 清理過期 pending-close 標記");
        }
    }

    /// IPC-triggered close-all: exchange mode (Demo/Live) dispatches reduce_only market orders
    /// via the shadow channel; paper mode clears paper_state directly.
    /// Returns the number of positions acted on.
    ///
    /// IPC 觸發全部平倉：交易所模式（Demo/Live）通過 shadow 通道發 reduce_only 市價單；
    /// 紙盤模式直接清除 paper_state。返回操作的倉位數量。
    pub(crate) fn ipc_close_all(&mut self) -> usize {
        let ts_ms = openclaw_core::now_ms();
        let is_exchange = self.pipeline_kind.is_exchange();
        if is_exchange {
            // Collect position snapshot first to avoid borrow conflict on self.
            // 先快照倉位，避免 borrow 衝突。
            let positions: Vec<(String, bool, f64, f64)> = self
                .paper_state
                .positions()
                .into_iter()
                .filter(|p| p.qty > 0.0)
                .map(|p| {
                    let price = self
                        .paper_state
                        .latest_price(&p.symbol)
                        .unwrap_or(p.entry_price);
                    (p.symbol.clone(), p.is_long, p.qty, price)
                })
                .collect();
            let count = positions.len();
            for (symbol, is_long, qty, price) in positions {
                if let Some(ref tx) = self.order_dispatch_tx {
                    self.exchange_seq = self.exchange_seq.wrapping_add(1);
                    let order_link_id =
                        format!("oc_ipc_close_{}_{}", ts_ms, self.exchange_seq);
                    let _ = tx.send(OrderDispatchRequest {
                        symbol: symbol.clone(),
                        is_long: !is_long, // opposite side to close / 相反方向平倉
                        qty,
                        price,
                        strategy: "ipc_close_all".into(),
                        paper_fill_ts: ts_ms,
                        is_close: true,
                        order_link_id,
                        is_primary: true, // exchange mode: primary order / 交易所模式主訂單
                        stop_loss: None,
                        take_profit: None,
                    });
                    self.pending_close_symbols.insert(symbol);
                }
            }
            count
        } else {
            // Paper mode: clear paper_state directly (no exchange orders).
            // 紙盤模式：直接清除 paper_state（無交易所訂單）。
            self.paper_state.close_all_positions()
        }
    }

    /// IPC-triggered close-symbol: exchange mode dispatches a single reduce_only market order;
    /// paper mode calls close_position_at_market directly.
    /// Returns true if a position was found and acted on.
    ///
    /// IPC 觸發單倉平倉：交易所模式發單一 reduce_only 市價單；
    /// 紙盤模式直接調用 close_position_at_market。找到倉位則返回 true。
    /// IPC-triggered single-symbol close.
    /// hint_is_long / hint_qty: caller-supplied exchange position info for orphan positions
    /// (positions that exist on the exchange but are not tracked in paper_state).
    /// When paper_state has no position but valid hints are provided, a shadow reduce_only
    /// market order is dispatched directly — Rust handles the Bybit API call.
    ///
    /// IPC 觸發單倉平倉。
    /// hint_is_long / hint_qty：呼叫方提供的交易所側倉位資訊（孤兒倉位用）。
    /// paper_state 無倉但有有效 hints 時，直接發 shadow reduce_only 市價單，
    /// 由 Rust 引擎完成 Bybit API 調用，Python 層不介入交易執行。
    pub(crate) fn ipc_close_symbol(
        &mut self,
        symbol: &str,
        hint_is_long: Option<bool>,
        hint_qty: Option<f64>,
    ) -> bool {
        let ts_ms = openclaw_core::now_ms();
        // Use exchange path when:
        //   (a) pipeline_kind is Demo or Live, OR
        //   (b) system_mode is DemoReserved AND shadow channel is active
        //       (paper_only + demo_reserved is the current shadow-dispatch setup).
        // 交易所路徑條件：
        //   (a) pipeline_kind 為 Demo 或 Live，或
        //   (b) system_mode 為 DemoReserved 且 shadow channel 可用。
        let is_exchange = self.pipeline_kind.is_exchange()
            || (self.order_dispatch_tx.is_some()
                && matches!(self.system_mode, SystemMode::DemoReserved));
        if is_exchange {
            // Read position data before mutating self.exchange_seq.
            // 先讀倉位數據，再修改 self.exchange_seq。
            let pos_info = self.paper_state.get_position(symbol).and_then(|p| {
                if p.qty > 0.0 {
                    let price = self
                        .paper_state
                        .latest_price(symbol)
                        .unwrap_or(p.entry_price);
                    Some((p.is_long, p.qty, price))
                } else {
                    None
                }
            });
            // Fallback: use caller hints for orphan exchange positions not in paper_state.
            // paper_state 無倉時，使用呼叫方提供的 hints 平掉交易所側的孤兒倉位。
            let (is_long, qty, price) = match pos_info {
                Some(v) => v,
                None => match (hint_is_long, hint_qty) {
                    (Some(il), Some(q)) if q > 0.0 => {
                        let price = self.paper_state.latest_price(symbol).unwrap_or(0.0);
                        info!(
                            symbol,
                            is_long = il,
                            qty = q,
                            "ipc_close_symbol: orphan hint close — no paper pos, using caller hint / 孤兒倉位 hint 平倉"
                        );
                        (il, q, price)
                    }
                    _ => return false,
                },
            };
            if let Some(ref tx) = self.order_dispatch_tx {
                self.exchange_seq = self.exchange_seq.wrapping_add(1);
                let order_link_id = format!("oc_ipc_close_{}_{}", ts_ms, self.exchange_seq);
                let _ = tx.send(OrderDispatchRequest {
                    symbol: symbol.to_string(),
                    is_long: !is_long, // opposite side to close / 相反方向平倉
                    qty,
                    price,
                    strategy: "ipc_close_symbol".into(),
                    paper_fill_ts: ts_ms,
                    is_close: true,
                    order_link_id,
                    is_primary: true,
                    stop_loss: None,
                    take_profit: None,
                });
                self.pending_close_symbols.insert(symbol.to_string());
                true
            } else {
                false
            }
        } else {
            // Paper mode: immediate close via paper_state.
            // 紙盤模式：通過 paper_state 立即平倉。
            self.paper_state.close_position_at_market(symbol).is_some()
        }
    }

    /// Build a canary record if canary_mode is enabled (R07-2).
    /// 灰度模式啟用時構建灰度記錄。


    pub fn grant_paper_auth(&mut self) -> Result<(), String> {
        self.governance
            .grant_paper_authorization(None)
            .map(|_| ())
            .map_err(|e| e.to_string())
    }

    pub fn status(&self) -> PipelineStatus {
        PipelineStatus {
            stats: self.stats.clone(),
            governance: self.governance.status(),
            positions: self.paper_state.position_count(),
            balance: self.paper_state.balance(),
            symbols_tracked: self.latest_prices.len(),
        }
    }

    /// Create full IPC snapshot / 創建完整 IPC 快照（R06-A）
    pub fn snapshot(&self) -> PipelineSnapshot {
        let strategies: Vec<StrategyInfo> = self.orchestrator.strategy_infos();
        let mut klines: HashMap<String, Vec<openclaw_core::klines::KlineBar>> = HashMap::new();
        for sym in self.kline_manager.symbols() {
            if let Some(buf) = self.kline_manager.get_buffer(sym, "1m") {
                let bars = buf.latest_cloned(100);
                if !bars.is_empty() {
                    klines.insert(sym.clone(), bars);
                }
            }
        }

        PipelineSnapshot {
            schema_version: "2.0.0".into(),
            written_at_ms: openclaw_core::now_ms(),
            paper_state: self.paper_state.export_state(),
            latest_prices: self.latest_prices.clone(),
            stats: self.stats.clone(),
            source: "rust_engine".into(),
            paper_paused: self.paper_paused,
            pipeline_kind: self.pipeline_kind,
            system_mode: self.system_mode.to_string(),
            indicators: self.latest_indicators.clone(),
            signals: self.recent_signals.iter().cloned().collect(),
            strategies,
            recent_intents: self.recent_intents.iter().cloned().collect(),
            recent_fills: self.recent_fills.iter().cloned().collect(),
            klines,
            h0_gate_stats: Some(self.h0_gate.get_stats().clone()),
            stop_config: Some(self.paper_state.stop_config().clone()),
            guardian_config: Some(self.intent_processor.guardian_config().clone()),
            risk_manager_config: Some(self.intent_processor.risk_config().clone()),
            consecutive_losses: self.consecutive_losses.clone(),
            session_halted: self.session_halted,
            daily_loss_pct: self
                .intent_processor
                .daily_loss_pct_pub(self.paper_state.balance()),
            session_drawdown_pct: self.paper_state.drawdown_pct(),
            mode_snapshots: {
                // 3E-4: Each pipeline emits its own snapshot. Multi-mode iteration removed.
                // 3E-4：每管線發出自己的快照。多模式迭代已移除。
                let mut ms = HashMap::new();
                ms.insert(
                    self.pipeline_kind.db_mode().to_string(),
                    crate::mode_state::ModeStateSnapshot {
                        paper_state: self.paper_state.export_state(),
                        recent_intents: self.recent_intents.iter().cloned().collect(),
                        recent_fills: self.recent_fills.iter().cloned().collect(),
                        consecutive_losses: self.consecutive_losses.clone(),
                        session_halted: self.session_halted,
                        paper_paused: self.paper_paused,
                    },
                );
                ms
            },
        }
    }

    /// Set global system mode, syncing from Python GUI.
    /// Automatically closes exchange positions when entering ShadowOnly/ObserveOnly/DesignOnly.
    /// Pauses paper simulation when entering ObserveOnly/DesignOnly.
    /// 設置全局系統模式，從 Python GUI 同步。
    /// 進入 ShadowOnly/ObserveOnly/DesignOnly 時自動平倉交易所持倉。
    /// 進入 ObserveOnly/DesignOnly 時暫停 paper 模擬。
    pub fn set_system_mode(&mut self, mode: &str) -> Result<String, String> {
        let new_mode = SystemMode::from_str(mode)?;
        let old_mode = self.system_mode;
        let is_exchange_mode = self.pipeline_kind.is_exchange();
        let was_exchange_allowed = !matches!(
            old_mode,
            SystemMode::ShadowOnly | SystemMode::ObserveOnly | SystemMode::DesignOnly
        );
        let exchange_now_blocked = matches!(
            new_mode,
            SystemMode::ShadowOnly | SystemMode::ObserveOnly | SystemMode::DesignOnly
        );
        // Auto-close exchange positions when transitioning into a blocking mode
        // 過渡到封鎖模式時自動平倉交易所持倉
        if is_exchange_mode && was_exchange_allowed && exchange_now_blocked {
            let count = self.ipc_close_all();
            info!(
                old = %old_mode, new = %new_mode, closed = count,
                "system_mode gate: auto-closing exchange positions / 系統模式門控：自動平倉交易所持倉"
            );
        }
        // Pause/resume paper simulation based on new mode
        // 根據新模式暫停/恢復 paper 模擬
        match new_mode {
            SystemMode::ObserveOnly | SystemMode::DesignOnly => {
                self.paper_paused = true;
            }
            SystemMode::ShadowOnly => {
                self.paper_paused = false;
            }
            _ => {}
        }
        self.system_mode = new_mode;
        info!(old = %old_mode, new = %new_mode, "system_mode updated / 系統模式已更新");
        Ok(format!(
            "{{\"old\":\"{old_mode}\",\"new\":\"{new_mode}\"}}"
        ))
    }

    /// Read-only access to latest prices map (R06-A).
    /// 最新價格映射的唯讀訪問。
    pub fn latest_prices(&self) -> &HashMap<String, f64> {
        &self.latest_prices
    }

    /// Feed a single replay tick through the full pipeline (R07-replay).
    /// Delegates to on_tick() with canary_mode forced on to guarantee a
    /// CanaryRecord is returned for every tick.
    /// 將單個回放 tick 送入完整管線（R07-replay）。
    /// 強制啟用 canary_mode 以確保每個 tick 都返回 CanaryRecord。
    pub fn feed_replay_tick(&mut self, event: &PriceEvent) -> Option<CanaryRecord> {
        // Ensure canary_mode is on so on_tick() produces a record.
        // 確保 canary_mode 開啟，使 on_tick() 產生記錄。
        let was_canary = self.canary_mode;
        self.canary_mode = true;
        let record = self.on_tick(event);
        self.canary_mode = was_canary;
        record
    }
}
