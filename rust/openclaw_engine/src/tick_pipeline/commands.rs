//! Pipeline command handlers — external order submission, risk status,
//! fill handling, close operations, snapshots, system mode.
//! 管線命令處理 — 外部訂單提交、風控狀態、成交處理、
//! 平倉操作、快照、系統模式。

use super::on_tick_helpers::{
    make_context_id, make_fill_id, make_intent_id, make_verdict_id, push_capped, risk_score_level,
};
use super::*;

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
            time_in_force: None,
            maker_timeout_ms: None,
        };

        let result = self.intent_processor.process(
            &intent,
            &self.governance,
            &self.paper_state,
            atr_value,
            GovernanceProfile::Exploration,
        );

        // Persist Guardian verdict (all verdicts including rejections) / 持久化 Guardian 裁定（含拒絕）
        if let (Some(ref tx), Some(ref vi)) = (&self.trading_tx, &result.verdict_info) {
            let now_ms_v = openclaw_core::now_ms();
            let em_v = self.effective_engine_mode();
            let checks_failed = vi.reasons.clone();
            let checks_passed = if checks_failed.is_empty() {
                vec!["guardian_checks".to_string()]
            } else {
                Vec::new()
            };
            let _ = crate::database::try_send_trading_msg(
                tx,
                crate::database::TradingMsg::RiskVerdict {
                    verdict_id: make_verdict_id(em_v, symbol, now_ms_v),
                    ts_ms: now_ms_v,
                    intent_id: make_intent_id(em_v, symbol, now_ms_v),
                    context_id: make_context_id(em_v, symbol, now_ms_v),
                    symbol: symbol.to_string(),
                    verdict: vi.verdict.clone(),
                    risk_score: vi.risk_score,
                    risk_level: risk_score_level(vi.risk_score).map(str::to_string),
                    checks_passed,
                    checks_failed,
                    reasons: vi.reasons.clone(),
                    modified_qty: vi.modified_qty,
                    engine_mode: em_v.to_string(),
                },
                "risk_verdict",
            );
        }

        if !result.submitted {
            return Err(result
                .rejected_reason
                .unwrap_or_else(|| "rejected_unknown".into()));
        }
        let mut fill = result
            .fill
            .ok_or_else(|| "submitted_but_no_fill".to_string())?;

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
        // EXIT-FEATURES-TABLE-1 (E2 P1 fix): also capture PositionExitSnapshot so
        // we can emit an ExitFeatureRow if this external fill turns out to be
        // a close (realized_pnl != 0). apply_fill mutates/removes the position
        // on close, so we must snapshot pre-fill. None when no position existed.
        // EXIT-FEATURES-TABLE-1 E2 P1：apply_fill 前捕獲 snapshot；外部 fill
        // 若為平倉（realized_pnl != 0）才發送 ExitFeatureRow。
        let pre_fill_snapshot = self.paper_state.position_exit_snapshot(symbol);
        let realized_pnl = self.paper_state.apply_fill(
            symbol,
            is_long,
            fill.fill_qty,
            fill.fill_price,
            fill.fee,
            now_ms,
            strategy,
        );

        // DYNAMIC-RISK-1: non-zero realized_pnl ⇒ close fill — feed the sizer.
        // DYNAMIC-RISK-1：realized_pnl != 0 代表平倉，餵入動態風險調整器。
        if realized_pnl != 0.0 {
            self.dynamic_risk_sizer.record_closed_trade(realized_pnl);
        }

        // EDGE-P3-1 R2: entry_context_id stamping for fresh opens — must reuse the
        // SAME context_id value that will be written to the Fill row below (same
        // em, symbol, now_ms → deterministic make_context_id).
        // EDGE-P3-1 R2：僅新開倉打 entry_context_id；加倉不覆蓋。context_id 與下方 Fill 寫入相同。
        if was_open && realized_pnl == 0.0 {
            let em_pre = self.effective_engine_mode();
            let ctx_pre = make_context_id(em_pre, symbol, now_ms);
            self.paper_state.set_entry_context_id(symbol, &ctx_pre);
        }

        // PA-DRY-1: helper centralised in tick_pipeline::mod (was 4-line dup here + below).
        // PA-DRY-1：legacy close-prefix 判斷集中到 tick_pipeline::mod helper（原處兩份重複）。
        let is_close_fill_for_db = realized_pnl != 0.0 || super::is_legacy_close_tag(strategy);

        // EDGE-P3-1 R2: entry_context_id for the Fill row emission below.
        // Close fills carry the pre-close entry's id; open/accumulate fills
        // leave it empty (JOIN is from decision_features → close fill's
        // entry_context_id only). Some IPC/manual close rows settle at zero
        // realized PnL, so DB close detection must also honor the close tag.
        // EDGE-P3-1 R2：平倉 Fill 帶 entry_context_id；開倉/加倉留空。部分
        // IPC / manual close 會以 0 PnL 結算，因此 DB 判斷也看 close tag。
        let fill_entry_ctx = if is_close_fill_for_db {
            existing_entry_ctx
        } else {
            String::new()
        };

        self.stats.total_intents += 1;
        self.stats.total_fills += 1;

        push_capped(
            &mut self.recent_intents,
            TimestampedIntent {
                timestamp_ms: now_ms,
                intent: intent.clone(),
                result: "submitted".into(),
            },
            50,
        );
        push_capped(
            &mut self.recent_fills,
            TimestampedFill {
                timestamp_ms: now_ms,
                symbol: symbol.to_string(),
                is_long,
                qty: fill.fill_qty,
                price: fill.fill_price,
                fee: fill.fee,
                realized_pnl,
                strategy: strategy.to_string(),
            },
            50,
        );

        let order_id = format!("ext-{symbol}-{now_ms}");

        // Persistence parity: emit Intent + Fill to PG writer when wired.
        // 持久化對等：trading_tx 已接時，發 Intent + Fill 到 PG writer。
        if let Some(ref tx) = self.trading_tx {
            let em = self.effective_engine_mode();
            let context_id = make_context_id(em, symbol, now_ms);
            let (fill_strategy_name, fill_exit_reason) = if is_close_fill_for_db {
                crate::tick_pipeline::on_tick::build_close_tags_from_legacy(
                    strategy,
                    pre_fill_snapshot
                        .as_ref()
                        .map(|snap| snap.owner_strategy.as_str()),
                )
            } else {
                (strategy.to_string(), None)
            };
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
                "limit_price": intent.limit_price,
                "time_in_force": intent.time_in_force.map(|tif| tif.as_str()),
                "post_only": matches!(intent.time_in_force, Some(crate::order_manager::TimeInForce::PostOnly)),
                "maker_timeout_ms": intent.maker_timeout_ms,
                "source": "command",
            });
            crate::database::try_send_trading_msg(
                tx,
                crate::database::TradingMsg::Intent {
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
                },
                "external_intent",
            );
            let _ = crate::database::try_send_trading_msg(
                tx,
                crate::database::TradingMsg::Fill {
                    fill_id: make_fill_id(em, symbol, now_ms),
                    ts_ms: now_ms,
                    order_id: order_id.clone(),
                    symbol: symbol.to_string(),
                    side: if is_long { "Buy".into() } else { "Sell".into() },
                    qty: fill.fill_qty,
                    price: fill.fill_price,
                    fee: fill.fee,
                    fee_rate: self.intent_processor.fee_rate(symbol),
                    reference_price: None,
                    reference_ts_ms: None,
                    reference_source: None,
                    slippage_bps: None,
                    liquidity_role: None,
                    fill_latency_ms: None,
                    realized_pnl,
                    strategy_name: fill_strategy_name,
                    context_id,
                    entry_context_id: fill_entry_ctx.clone(),
                    engine_mode: em.to_string(),
                    // INFRA-PREBUILD-1 Part A: external / IPC close path bypasses
                    // Combine Layer — exit_source stays NULL (no Track P eval here).
                    // INFRA-PREBUILD-1 A 部：外部 / IPC close 不走 Combine Layer，
                    // exit_source 保持 NULL。
                    exit_source: None,
                    // V033 W1-T2: external close fills use the same legacy-tag
                    // normalizer as the canonical close helper.
                    // V033 W1-T2：外部 close fill 與 canonical close helper
                    // 共用 legacy-tag 正規化。
                    exit_reason: fill_exit_reason,
                },
                "external_fill",
            );
        }

        // EXIT-FEATURES-TABLE-1 (E2 P1 fix): if this external fill was a close
        // (realized_pnl != 0), emit a Track P feature row too. Uses the pre-fill
        // snapshot captured above; fails soft when no snapshot (shouldn't happen
        // on a real close) or tx unwired.
        // EXIT-FEATURES-TABLE-1 E2 P1：外部平倉 fill 同步寫 exit_features，
        // 與內部 emit_close_fill 路徑保持 Track P 標籤覆蓋對等。
        if realized_pnl != 0.0 {
            self.try_emit_exit_feature_row(
                symbol,
                fill.fill_qty,
                fill.fill_price,
                now_ms,
                realized_pnl,
                fill.fee,
                self.intent_processor.fee_rate(symbol),
                // Preserve caller's strategy label for taxonomy — unlike
                // internal close paths this is driven by exchange reports, so
                // there is no canonical prefix. parse_exit_tag will fall
                // through to (strategy, "") pair which downstream treats as
                // ExternalFill category.
                // 外部 fill 無固定 prefix，策略名原樣傳；parse_exit_tag 退回
                // (strategy, "") 由下游歸類為 ExternalFill。
                strategy,
                pre_fill_snapshot.as_ref(),
                &fill_entry_ctx,
            );
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
            "lease_router": {
                "enabled": self.governance.router_gate_enabled(),
                "audit_writer_configured": self.governance.lease_transition_writer_configured(),
                "source": "GovernanceCore.router_gate_enabled",
                "scope": "production_intent_router",
            },
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
    ///
    /// FILL-CONTEXT-LINKAGE-1 (2026-04-19): `signal_context_id` carries the
    /// signal-time id (built with `event.ts_ms`) all the way from on_tick.rs
    /// through OrderDispatchRequest → PendingOrder. Using it here keeps
    /// `trading.fills.entry_context_id` in lockstep with
    /// `learning.decision_features.context_id` so the P1-7 C backfill JOIN
    /// actually matches. Empty string → fall back to exec-time recompute
    /// (preserves legacy behaviour for callers that don't have the id, e.g.
    /// orphan close or shadow channel).
    /// FILL-CONTEXT-LINKAGE-1 (2026-04-19)：`signal_context_id` 從 on_tick.rs
    /// 透過 OrderDispatchRequest → PendingOrder 端到端傳入，取代原本用 WS
    /// exec_ts 重算（100-500ms 漂移導致 JOIN 0 overlap）。空字串時 fallback
    /// 至原有 exec-time 重算以保留 orphan/shadow 舊行為。
    pub fn apply_confirmed_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        fill_price: f64,
        fee: f64,
        ts_ms: u64,
        strategy: &str,
        signal_context_id: &str,
        order_link_id: &str,
        fee_rate_override: Option<f64>,
        reference_price: Option<f64>,
        reference_ts_ms: Option<u64>,
        reference_source: Option<&str>,
        slippage_bps: Option<f64>,
        liquidity_role: Option<&str>,
        fill_latency_ms: Option<u64>,
        exchange_exec_id: Option<&str>,
    ) {
        // EDGE-P3-1 R2 + V083-FIX-1（2026-05-11）：apply_fill 前先捕獲 was_open
        // 與 existing entry_context_id；close fill 走 helper 拿 well-formed id
        // （真 id 或 synthetic `orphan_recovery_ctx:{symbol}:{ts_ms}`），避免
        // V083 NOT NULL CHECK reject + batch buffer 卡死（W-D MAG-083 P1-RCA-1）。
        // entry case（line ~587 `if is_close_fill_for_db` 分流）不關心本 ctx —
        // 仍寫 `String::new()`，對齊 V083 設計（entry fill 的 entry_context_id 為 NULL）。
        let was_open = self.paper_state.get_position(symbol).is_none();
        let existing_entry_ctx = self.resolve_close_entry_context_id(symbol, ts_ms);
        // EXIT-FEATURES-TABLE-1 Phase 1b GAP-1 (2026-04-19): capture pre-close
        // snapshot on the exchange-confirmed fill path. Before this, only
        // emit_close_fill / process_external_fill / ipc_close_symbol paper
        // branch emitted exit_feature rows — apply_confirmed_fill (the primary
        // Demo/Live close path via WS) was unwired, silently losing ~95% of
        // exit labels once Paper got disabled (PAPER-DISABLE-1).
        // EXIT-FEATURES-TABLE-1 Phase 1b GAP-1 修復（2026-04-19）：在交易所
        // 確認成交路徑捕獲 pre-close 快照。此前僅 emit_close_fill /
        // process_external_fill / ipc_close_symbol paper 分支發送；
        // apply_confirmed_fill（Demo/Live 主路徑）未接線，PAPER-DISABLE-1
        // 後 ~95% exit 標籤靜默遺失。
        let pre_close_snapshot = self.paper_state.position_exit_snapshot(symbol);
        let realized_pnl = self
            .paper_state
            .apply_fill(symbol, is_long, qty, fill_price, fee, ts_ms, strategy);
        // FILL-CONTEXT-LINKAGE-1: use the signal-time id carried through
        // OrderDispatchRequest → PendingOrder rather than recomputing with
        // WS exec_ts (drifts 100-500ms from event.ts_ms → 0 JOIN overlap).
        // Fallback to exec-time id only when caller didn't thread the id
        // (e.g. shadow-channel close on an orphan position).
        // FILL-CONTEXT-LINKAGE-1：使用訊號時刻 context_id，不再用 WS exec_ts。
        // 僅在呼叫方未傳時退回 exec-time 重算以保留舊行為。
        if was_open && realized_pnl == 0.0 {
            let ctx_pre = if !signal_context_id.is_empty() {
                signal_context_id.to_string()
            } else {
                let em_pre = self.effective_engine_mode();
                make_context_id(em_pre, symbol, ts_ms)
            };
            self.paper_state.set_entry_context_id(symbol, &ctx_pre);
        }
        self.stats.total_fills += 1;
        // Update Kelly stats on exchange fill (previously missing — QC P2-2 fix).
        // Non-zero realized_pnl indicates a position close (open fills return 0.0).
        // 交易所成交時更新 Kelly 統計（先前遺漏 — QC P2-2 修復）。
        // 非零 realized_pnl 表示平倉成交（開倉成交返回 0.0）。
        if realized_pnl.abs() > f64::EPSILON {
            self.intent_processor.record_trade(symbol, realized_pnl);
            // DYNAMIC-RISK-1: realized close on exchange-confirmed fill.
            // DYNAMIC-RISK-1：交易所確認的平倉成交，餵入動態風險調整器。
            self.dynamic_risk_sizer.record_closed_trade(realized_pnl);
        }
        // Clear pending_close flag if this was a close fill / 如果是平倉成交，清除待處理平倉標記
        self.pending_close_symbols.remove(symbol);

        push_capped(
            &mut self.recent_fills,
            TimestampedFill {
                timestamp_ms: ts_ms,
                symbol: symbol.to_string(),
                is_long,
                qty,
                price: fill_price,
                fee,
                realized_pnl,
                strategy: strategy.to_string(),
            },
            50,
        );

        if let Some(ref tx) = self.trading_tx {
            let em = self.effective_engine_mode();
            let fr = fee_rate_override
                .filter(|v| v.is_finite() && *v >= 0.0)
                .unwrap_or_else(|| self.intent_processor.fee_rate(symbol));
            // PA-DRY-1: see helper in tick_pipeline::mod (single source of truth).
            // PA-DRY-1：see tick_pipeline::mod helper（單一真相來源）。
            let is_close_fill_for_db = realized_pnl != 0.0 || super::is_legacy_close_tag(strategy);
            // EDGE-P3-1 R2: close fills carry the pre-close entry's id; opens stay empty.
            // Zero-PnL IPC/manual closes still count as close rows for DB attribution.
            // EDGE-P3-1 R2：平倉 fill 帶 entry_context_id；開倉/加倉留空。0 PnL
            // IPC / manual close 仍按 close row 寫歸因。
            let fill_entry_ctx = if is_close_fill_for_db {
                existing_entry_ctx.clone()
            } else {
                String::new()
            };
            // FILL-CONTEXT-LINKAGE-1: prefer signal-time id on OPEN fills so
            // the Fill row's own context_id (not entry_context_id) also
            // matches `learning.decision_features.context_id`. Closes compute
            // a new exec-time id (fill is a new row, not an entry proxy).
            // FILL-CONTEXT-LINKAGE-1：開倉 fill 用訊號時刻 id（JOIN decision_features）；
            // 平倉 fill 為新列，用 exec 時間戳另行生成，保留舊行為。
            let fill_ctx_id = if realized_pnl == 0.0 && !signal_context_id.is_empty() {
                signal_context_id.to_string()
            } else {
                make_context_id(em, symbol, ts_ms)
            };
            let fill_id = exchange_exec_id
                .filter(|id| !id.trim().is_empty())
                .map(|id| format!("bybit-{id}"))
                .unwrap_or_else(|| make_fill_id(em, symbol, ts_ms));
            let (fill_strategy_name, fill_exit_reason) = if is_close_fill_for_db {
                crate::tick_pipeline::on_tick::build_close_tags_from_legacy(
                    strategy,
                    pre_close_snapshot
                        .as_ref()
                        .map(|snap| snap.owner_strategy.as_str()),
                )
            } else {
                (strategy.to_string(), None)
            };
            let _ = crate::database::try_send_trading_msg(
                tx,
                crate::database::TradingMsg::Fill {
                    fill_id,
                    ts_ms,
                    order_id: order_link_id.to_string(),
                    symbol: symbol.to_string(),
                    side: if is_long { "Buy".into() } else { "Sell".into() },
                    qty,
                    price: fill_price,
                    fee,
                    fee_rate: fr,
                    reference_price,
                    reference_ts_ms,
                    reference_source: reference_source.map(str::to_string),
                    slippage_bps,
                    liquidity_role: liquidity_role.map(str::to_string),
                    fill_latency_ms,
                    realized_pnl,
                    strategy_name: fill_strategy_name,
                    context_id: fill_ctx_id,
                    entry_context_id: fill_entry_ctx,
                    engine_mode: em.to_string(),
                    // INFRA-PREBUILD-1 Part A: exchange-confirmed fill path — exit_source NULL.
                    // INFRA-PREBUILD-1 A 部：交易所確認 fill 不經 Combine Layer。
                    exit_source: None,
                    // V033 W1-T2: confirmed close fills carry normalized
                    // strategy_name plus free-text exit_reason.
                    // V033 W1-T2：交易所確認 close fill 寫 normalized
                    // strategy_name 與 free-text exit_reason。
                    exit_reason: fill_exit_reason,
                },
                "confirmed_fill",
            );
        }

        // EXIT-FEATURES-TABLE-1 Phase 1b GAP-1 (2026-04-19): emit exit feature
        // row on close. `try_emit_exit_feature_row` fail-softs if
        // `exit_feature_tx` is unwired OR if `pre_close_snapshot` is None
        // (which shouldn't happen on a real close since the position must
        // have existed prior to apply_fill for realized_pnl to be nonzero).
        // Pattern mirrors process_external_fill (commands.rs:285). For
        // entry_context_id we reuse `existing_entry_ctx` captured above —
        // the pre-close position's entry id — matching other close paths.
        // EXIT-FEATURES-TABLE-1 Phase 1b GAP-1：平倉時發送退場特徵行；
        // fail-soft（tx/snap 缺一即 no-op，對交易無影響）。entry_context_id
        // 沿用前述 existing_entry_ctx，與其他 close 路徑對齊。
        if realized_pnl != 0.0 {
            let fr = fee_rate_override
                .filter(|v| v.is_finite() && *v >= 0.0)
                .unwrap_or_else(|| self.intent_processor.fee_rate(symbol));
            self.try_emit_exit_feature_row(
                symbol,
                qty,
                fill_price,
                ts_ms,
                realized_pnl,
                fee,
                fr,
                strategy,
                pre_close_snapshot.as_ref(),
                &existing_entry_ctx,
            );
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
    ///
    /// F2 CROSS-SYMBOL-PRICE-CONTAMINATION-1 (2026-04-26): the dispatched
    /// `OrderDispatchRequest.price` MUST resolve from `symbol`'s own latest
    /// price ladder (paper_state.latest_price → entry_price → event.last_price
    /// last-resort), NOT from `event.last_price` directly. The risk / fast_track
    /// / strategy-close / halt-session callers iterate `paper_state.positions()`
    /// and may close any position regardless of which symbol fired the current
    /// tick (e.g. STRKUSDT dust-spiral fast_track ReduceToHalf evaluated under
    /// an ETHUSDT/BTCUSDT/KATUSDT outer tick → previously stamped the outer
    /// tick's price onto STRK's reduce-only OrderDispatchRequest, which
    /// (a) corrupted `min_notional` ref_price evaluation, (b) wrote 41 phantom
    /// downstream fill log rows under the wrong symbol's accounting bucket, and
    /// (c) skewed `event_consumer::loop_handlers` "new fill" attribution. The
    /// paper-side `emit_close_fill` rows were already protected by P1-16 + the
    /// caller-side `close_position_at_symbol_market` resolution; this is the
    /// final missing link covering the exchange dispatch. Fallback chain mirrors
    /// `ipc_close_all` (line ~688) and `ipc_close_symbol` (line ~798) so all
    /// three close paths agree on the same price-resolution policy.
    ///
    /// RRC-1-C2 / R-03：執行平倉 — 派發到影子/交易所通道，並標記 pending 防止重複派發。
    /// `trigger_tag` 穿透至 trading.fills.strategy_name — caller 必須傳真實因果 tag。
    /// F2 跨交易對價格污染修復（2026-04-26）：派發出去的
    /// `OrderDispatchRequest.price` 必須由 `symbol` 自己的價格梯（paper_state.
    /// latest_price → entry_price → event.last_price 末路 fallback）求得，**不**
    /// 直接借用 `event.last_price`。風控/fast_track/策略平倉/halt 等 caller
    /// 都會掃 `paper_state.positions()` 對非 event.symbol 倉位下手（例：STRKUSDT
    /// dust spiral 在 ETH/BTC/KAT 外層 tick 下被 fast_track ReduceToHalf 半倉
    /// → 修前把外層 tick 的價蓋進 STRK 平倉派發，造成 (a) min_notional gate
    /// 用錯 ref_price (b) event_consumer 寫進錯 symbol 41 條 phantom fill 列
    /// (c) 「new fill」歸因錯亂）。Paper 側 emit_close_fill 已由 P1-16 + caller
    /// `close_position_at_symbol_market` 保護；本 fix 補齊 exchange 派發這條
    /// 最後缺口。Fallback chain 對齊 ipc_close_all（line ~688）+ ipc_close_symbol
    /// （line ~798），三條 close 路徑使用一致的 price-resolution 策略。
    pub(super) fn execute_position_close(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        event: &PriceEvent,
        is_primary: bool,
        trigger_tag: &str,
    ) -> bool {
        if let Some(ref tx) = self.order_dispatch_tx {
            self.exchange_seq = self.exchange_seq.wrapping_add(1);
            let prefix = if is_primary { "oc_risk" } else { "sh_risk" };
            // V083-FIX-1（2026-05-11）：close 路徑帶 entry_context_id 滿足
            // V083 NOT NULL CHECK；paper_state 缺則 helper 回 synthetic
            // `orphan_recovery_ctx:{symbol}:{event.ts_ms}`，避免 batch INSERT
            // 整 chunk 卡死（W-D MAG-083 P1-RCA-1）。本函數無 local ts_ms，
            // 用 `event.ts_ms`（PriceEvent 的 tick 時間戳）作為 synthetic key。
            let entry_ctx = self.resolve_close_entry_context_id(symbol, event.ts_ms);
            // F2 CROSS-SYMBOL-PRICE-CONTAMINATION-1 (2026-04-26): resolve the
            // dispatched `price` from `symbol`'s own ladder, not from the outer
            // tick. NaN-aware: `latest_price` may carry NaN when an
            // orphan-adopted position has never received a tick; treat NaN as
            // missing (matches per_symbol_price_pnl::test_halt_session_uses_
            // per_symbol_price_not_triggering_tick semantics).
            // F2 跨交易對價格污染修復（2026-04-26）：派發價格依 `symbol` 自有
            // 梯度求得，不沿用外層 tick。NaN-aware：latest_price 為 NaN 時視為
            // 缺值（對齊 P1-16 halt_session 測試的 fallback 語義）。
            let dispatch_price = self
                .paper_state
                .latest_price(symbol)
                .filter(|p| p.is_finite() && *p > 0.0)
                .or_else(|| {
                    self.paper_state
                        .get_position(symbol)
                        .map(|p| p.entry_price)
                        .filter(|p| p.is_finite() && *p > 0.0)
                })
                .unwrap_or(event.last_price);
            let is_partial_reduce =
                crate::tick_pipeline::on_tick::is_partial_reduce_tag(trigger_tag);
            let full_close = !is_partial_reduce
                && self
                    .paper_state
                    .get_position(symbol)
                    .map(|p| qty >= p.qty - 1e-12)
                    .unwrap_or(false);
            let dispatch_qty = if full_close {
                self.close_dispatch_qty_for_full_close(qty, is_primary)
            } else {
                qty
            };
            let request = OrderDispatchRequest {
                symbol: symbol.to_string(),
                is_long: !is_long,
                qty: dispatch_qty,
                price: dispatch_price,
                strategy: trigger_tag.to_string(),
                paper_fill_ts: event.ts_ms,
                is_close: true,
                order_link_id: format!("{}_{}_{}", prefix, event.ts_ms, self.exchange_seq),
                decision_lease_id: None,
                is_primary,
                stop_loss: None,
                take_profit: None,
                context_id: entry_ctx,
                order_type: "market".to_string(),
                limit_price: None,
                time_in_force: None,
                // Close path stays Market (EDGE-P2-3 Phase 1a entry-only scope).
                // 平倉維持 Market（EDGE-P2-3 Phase 1a 僅入場走 maker 路徑）。
                maker_timeout_ms: None,
                reference_price: Some(dispatch_price).filter(|p| p.is_finite() && *p > 0.0),
                reference_ts_ms: if dispatch_price.is_finite() && dispatch_price > 0.0 {
                    Some(event.ts_ms)
                } else {
                    None
                },
                reference_source: if dispatch_price.is_finite() && dispatch_price > 0.0 {
                    Some("dispatch_last_fallback".to_string())
                } else {
                    None
                },
                // W-C Caveat 2 修復（2026-05-11）：close 路徑不寫 entry lineage
                // （emit_entry_lineage 僅 open intent 使用），下游
                // emit_fill_completion_lineage 自然 short-circuit。
                spine_order_plan_id: None,
                spine_decision_id: None,
                spine_verdict_id: None,
                spine_stub_report_id: None,
            };
            match tx.send(request) {
                Ok(()) => {
                    if is_primary {
                        self.pending_close_symbols.insert(symbol.to_string());
                    }
                    true
                }
                Err(e) => {
                    tracing::error!(
                        symbol,
                        trigger_tag,
                        error = %e,
                        "close dispatch enqueue failed — local flatten blocked \
                         / 平倉派發入隊失敗 — 阻止本地平倉"
                    );
                    false
                }
            }
        } else {
            if is_primary {
                tracing::warn!(
                    symbol,
                    trigger_tag,
                    "close dispatch requested but order_dispatch_tx is unbound \
                     / 平倉派發請求缺少 order_dispatch_tx"
                );
            }
            false
        }
    }

    /// Dispatch a primary reduce-only close before local flattening in
    /// exchange mode. Returns `None` when the enqueue fails or a close is
    /// already pending, so callers must not mark the local position flat.
    pub(super) fn close_position_after_exchange_dispatch(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        event: &PriceEvent,
        trigger_tag: &str,
    ) -> Option<(bool, f64, f64, f64)> {
        if self.pipeline_kind.is_exchange() {
            if self.pending_close_symbols.contains(symbol) {
                return None;
            }
            if !self.execute_position_close(symbol, is_long, qty, event, true, trigger_tag) {
                return None;
            }
        }
        self.close_position_at_symbol_market(symbol, event.ts_ms)
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
        self.pending_close_symbols
            .retain(|s| open_symbols.contains(s));
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
            // F2 CROSS-SYMBOL-PRICE-CONTAMINATION-1 audit (2026-04-26):
            // `price` resolved from each position's own `latest_price` →
            // entry_price ladder; never borrows the IPC trigger's tick.
            // OK — same fallback policy as `execute_position_close` and
            // `ipc_close_symbol` after F2 fix.
            // F2 跨交易對價格污染審計（2026-04-26）：每筆倉位的派發價依其
            // 自身 latest_price → entry_price 求得，不借用觸發者的 tick。
            // 與 execute_position_close / ipc_close_symbol 一致的策略。
            let positions: Vec<(String, bool, f64, f64)> = self
                .paper_state
                .positions()
                .into_iter()
                .filter(|p| p.qty > 0.0)
                .map(|p| {
                    let price = self
                        .paper_state
                        .latest_price(&p.symbol)
                        .filter(|p| p.is_finite() && *p > 0.0)
                        .unwrap_or(p.entry_price);
                    (p.symbol.clone(), p.is_long, p.qty, price)
                })
                .collect();
            let mut count = 0usize;
            for (symbol, is_long, qty, price) in positions {
                if let Some(ref tx) = self.order_dispatch_tx {
                    self.exchange_seq = self.exchange_seq.wrapping_add(1);
                    let order_link_id = format!("oc_ipc_close_{}_{}", ts_ms, self.exchange_seq);
                    // V083-FIX-1（2026-05-11）：close 路徑帶 entry_context_id；
                    // paper_state 缺則 helper 回 synthetic（W-D MAG-083 P1-RCA-1）。
                    let entry_ctx = self.resolve_close_entry_context_id(&symbol, ts_ms);
                    let dispatch_qty = self.close_dispatch_qty_for_full_close(qty, true);
                    let request = OrderDispatchRequest {
                        symbol: symbol.clone(),
                        is_long: !is_long, // opposite side to close / 相反方向平倉
                        qty: dispatch_qty,
                        price,
                        strategy: "ipc_close_all".into(),
                        paper_fill_ts: ts_ms,
                        is_close: true,
                        order_link_id,
                        decision_lease_id: None,
                        is_primary: true, // exchange mode: primary order / 交易所模式主訂單
                        stop_loss: None,
                        take_profit: None,
                        context_id: entry_ctx,
                        order_type: "market".to_string(),
                        limit_price: None,
                        time_in_force: None,
                        // ipc_close_all goes Market (no maker sweep needed).
                        // ipc_close_all 走 Market，不需 maker sweep。
                        maker_timeout_ms: None,
                        reference_price: Some(price).filter(|p| p.is_finite() && *p > 0.0),
                        reference_ts_ms: if price.is_finite() && price > 0.0 {
                            Some(ts_ms)
                        } else {
                            None
                        },
                        reference_source: if price.is_finite() && price > 0.0 {
                            Some("dispatch_last_fallback".to_string())
                        } else {
                            None
                        },
                        // W-C Caveat 2 修復（2026-05-11）：close 路徑不寫 entry lineage。
                        spine_order_plan_id: None,
                        spine_decision_id: None,
                        spine_verdict_id: None,
                        spine_stub_report_id: None,
                    };
                    match tx.send(request) {
                        Ok(()) => {
                            self.pending_close_symbols.insert(symbol);
                            count += 1;
                        }
                        Err(e) => {
                            tracing::error!(
                                symbol,
                                error = %e,
                                "ipc_close_all dispatch enqueue failed — pending_close not set \
                                 / ipc_close_all 派發入隊失敗 — 不設定 pending_close"
                            );
                        }
                    }
                }
            }
            count
        } else {
            // Paper mode: clear paper_state directly (no exchange orders).
            // Forward every realized PnL to the sizer (DYNAMIC-RISK-1 BUG-1 fix).
            // 紙盤模式：直接清除 paper_state，並把每筆實現 PnL 餵給 sizer。
            let results = self.paper_state.close_all_positions();
            for (_, pnl) in &results {
                if *pnl != 0.0 {
                    self.dynamic_risk_sizer.record_closed_trade(*pnl);
                }
            }
            results.len()
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
    /// V083-FIX-1（2026-05-11）：close 路徑 entry_context_id 解析 helper，orphan
    /// 安全。paper_state 有則用真 id；否則回 synthetic
    /// `orphan_recovery_ctx:{symbol}:{ts_ms}` 滿足 V083 NOT NULL CHECK 並讓 cron
    /// 後補映射回真 entry context_id。
    ///
    /// 背景：paper_state 的 entry_context_id map 是 in-memory，engine restart 後
    /// 全部清空；orphan-adopted positions 也起始為空字串。原 `unwrap_or("")` →
    /// V083 CHECK reject → batch INSERT 整 chunk 失敗 → buffer 卡死無限重試。
    /// 詳見 W-D MAG-083 P1-RCA-1（commands.rs:1108 / 945 / 1183 / 512 / 749 五處
    /// close-path call site 全走本 helper）。
    ///
    /// 為什麼用 `&self` 而非 `&mut self`：close path 通常已 `&mut self` 借了
    /// paper_state，再對 paper_state 取 `&mut` 會 borrow conflict；本 helper 純讀
    /// 即可滿足契約（只查 in-memory map，不寫回；synthetic id 由呼叫端攜帶下游）。
    ///
    /// Synthetic id pattern 必須嚴格 `orphan_recovery_ctx:{symbol}:{ts_ms}` —
    /// P2 cron backfill (`edge_label_backfill.py`) 識別此 prefix → 用 (symbol,
    /// ts_ms) 反查 entry fill → UPDATE 真 entry's context_id。E2 必跑 grep 確認
    /// `get_entry_context_id.*unwrap_or` 在本檔 close path 0 hit。
    #[inline]
    pub(super) fn resolve_close_entry_context_id(&self, symbol: &str, ts_ms: u64) -> String {
        match self.paper_state.get_entry_context_id(symbol) {
            Some(id) if !id.is_empty() => id.to_string(),
            _ => format!("orphan_recovery_ctx:{}:{}", symbol, ts_ms),
        }
    }

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
            // F2 CROSS-SYMBOL-PRICE-CONTAMINATION-1 audit (2026-04-26):
            // `price` resolved from `symbol`'s own `latest_price` →
            // entry_price ladder; orphan-hint branch falls back to
            // latest_price-or-zero. NaN-aware filter aligns this path
            // with `execute_position_close` and `ipc_close_all` so the
            // three close paths share one price-resolution policy.
            // F2 跨交易對價格污染審計（2026-04-26）：派發價依 `symbol` 自身
            // latest_price → entry_price 階梯求得；orphan-hint 分支退到
            // latest_price 或 0。NaN-aware filter 對齊三條 close 路徑。
            let pos_info = self.paper_state.get_position(symbol).and_then(|p| {
                if p.qty > 0.0 {
                    let price = self
                        .paper_state
                        .latest_price(symbol)
                        .filter(|p| p.is_finite() && *p > 0.0)
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
                        let price = self
                            .paper_state
                            .latest_price(symbol)
                            .filter(|p| p.is_finite() && *p > 0.0)
                            .unwrap_or(0.0);
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
                // V083-FIX-1（2026-05-11）：close 路徑帶 entry_context_id 滿足
                // V083 NOT NULL CHECK；paper_state 有倉用真 id，否則 helper 回
                // synthetic `orphan_recovery_ctx:{symbol}:{ts_ms}`，避免 batch
                // INSERT 整 chunk 卡死（W-D MAG-083 P1-RCA-1）。
                let entry_ctx = self.resolve_close_entry_context_id(symbol, ts_ms);
                let dispatch_qty = self.close_dispatch_qty_for_full_close(qty, true);
                let request = OrderDispatchRequest {
                    symbol: symbol.to_string(),
                    is_long: !is_long, // opposite side to close / 相反方向平倉
                    qty: dispatch_qty,
                    price,
                    strategy: "risk_close:ipc_close_symbol".into(),
                    paper_fill_ts: ts_ms,
                    is_close: true,
                    order_link_id,
                    decision_lease_id: None,
                    is_primary: true,
                    stop_loss: None,
                    take_profit: None,
                    context_id: entry_ctx,
                    order_type: "market".to_string(),
                    limit_price: None,
                    time_in_force: None,
                    // Per-symbol IPC close goes Market.
                    // 單幣種 IPC 平倉走 Market。
                    maker_timeout_ms: None,
                    reference_price: Some(price).filter(|p| p.is_finite() && *p > 0.0),
                    reference_ts_ms: if price.is_finite() && price > 0.0 {
                        Some(ts_ms)
                    } else {
                        None
                    },
                    reference_source: if price.is_finite() && price > 0.0 {
                        Some("dispatch_last_fallback".to_string())
                    } else {
                        None
                    },
                    // W-C Caveat 2 修復（2026-05-11）：close 路徑不寫 entry lineage。
                    spine_order_plan_id: None,
                    spine_decision_id: None,
                    spine_verdict_id: None,
                    spine_stub_report_id: None,
                };
                match tx.send(request) {
                    Ok(()) => {
                        self.pending_close_symbols.insert(symbol.to_string());
                        true
                    }
                    Err(e) => {
                        tracing::error!(
                            symbol,
                            error = %e,
                            "ipc_close_symbol dispatch enqueue failed — pending_close not set \
                             / ipc_close_symbol 派發入隊失敗 — 不設定 pending_close"
                        );
                        false
                    }
                }
            } else {
                false
            }
        } else {
            // Paper mode: immediate close via paper_state.
            // 紙盤模式：通過 paper_state 立即平倉。
            // EXIT-FEATURES-TABLE-1 (E2 P1 fix): capture snapshot + entry_context_id
            // + resolved close price + qty BEFORE paper_state mutates. The close is
            // at market — mirror close_position_at_market's price-resolution so the
            // emitted exit feature row carries the same price that was actually
            // used for PnL. No fill-emit here: paper ipc_close historically doesn't
            // write TradingMsg::Fill (scope-tight fix — only add exit features).
            // EXIT-FEATURES-TABLE-1 E2 P1：關倉前捕獲快照/entry_context_id/價格/qty，
            // 僅補 exit feature 發送，不動 Fill 寫入路徑（維持本 patch 範圍）。
            let snap = self.paper_state.position_exit_snapshot(symbol);
            // V083-FIX-1（2026-05-11）：paper close 路徑也統一走 helper；雖然
            // paper 不直接寫 trading.fills（fail-safe by-design），但 exit
            // feature row 的 context_id 同樣需要 well-formed，避免下游 ML
            // training JOIN miss（與 exchange path 對齊一致）。
            let entry_ctx = self.resolve_close_entry_context_id(symbol, ts_ms);
            let (close_qty, close_price) = self
                .paper_state
                .get_position(symbol)
                .map(|p| {
                    let px = self
                        .paper_state
                        .latest_price(symbol)
                        .unwrap_or(p.entry_price);
                    (p.qty, px)
                })
                .unwrap_or((0.0, 0.0));
            match self.paper_state.close_position_at_market(symbol) {
                Some(pnl) => {
                    self.dynamic_risk_sizer.record_closed_trade(pnl);
                    if close_qty > 0.0 {
                        let fr = self.intent_processor.fee_rate(symbol);
                        let close_fee = close_qty * close_price * fr;
                        self.try_emit_exit_feature_row(
                            symbol,
                            close_qty,
                            close_price,
                            ts_ms,
                            pnl,
                            close_fee,
                            fr,
                            "risk_close:ipc_close_symbol",
                            snap.as_ref(),
                            &entry_ctx,
                        );
                    }
                    true
                }
                None => false,
            }
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
        Ok(format!("{{\"old\":\"{old_mode}\",\"new\":\"{new_mode}\"}}"))
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
