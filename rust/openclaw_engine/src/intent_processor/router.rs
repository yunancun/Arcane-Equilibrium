//! Intent processing pipelines — paper and exchange gate paths.
//! 意圖處理管線 — paper 模式完整執行路徑和交易所模式門禁路徑。

use super::*;

// AMD-2026-05-02-01 Track E E-2: RAII guard for the Decision Lease acquired by
// Gate 1.4. On drop without `consume()` it releases with LeaseOutcome::Cancelled
// so any downstream gate rejection (Gate 1.5/1.6/2/2.5-2.7/3) does not leak the
// lease. Success paths call `consume()` to take the inner Active LeaseId out;
// fill consumer (step_4_5_dispatch.rs / future E-3 IPC release path) is the one
// that calls release_lease(Consumed) after exchange ack.
//
// Bypass / None states: drop is a no-op (release_lease handles Bypass; None
// means flag-OFF and no facade call ever happened).
//
// AMD-2026-05-02-01 Track E E-2：Gate 1.4 取得的 Decision Lease 之 RAII guard。
// Drop 時若未 `consume()` 即以 LeaseOutcome::Cancelled 釋放，避免下游 gate（1.5
// /1.6/2/2.5-2.7/3）拒絕路徑 leak lease；成功路徑呼 `consume()` 把 Active
// LeaseId 取出後由 fill consumer (step_4_5_dispatch.rs / 未來 E-3 IPC release
// path) 在交易所 ack 後呼 release_lease(Consumed)。Bypass / None 兩態 Drop 為
// no-op（release_lease 對 Bypass 即 Ok；None 表 flag OFF 從未呼 facade）。
struct RouterLeaseGuard<'a> {
    governance: &'a GovernanceCore,
    lease: Option<LeaseId>,
}

impl<'a> RouterLeaseGuard<'a> {
    /// New guard; `lease=None` means flag-OFF (no facade call); `Some(Bypass)` =
    /// non-Production short-circuit; `Some(Active(_))` = real production lease.
    /// 新建 guard。`lease=None` 對應 flag OFF；`Some(Bypass)` = 非 Production 短路；
    /// `Some(Active(_))` = 真實 Production lease。
    fn new(governance: &'a GovernanceCore, lease: Option<LeaseId>) -> Self {
        Self { governance, lease }
    }

    /// Take inner lease for use in the success-path IntentResult / ExchangeGateResult.
    /// Disables Drop release (caller / fill consumer is now responsible for release).
    /// 將內部 lease 取出供成功路徑使用，停用 Drop release（呼叫端 / fill consumer
    /// 自此負責 release）。
    fn consume(mut self) -> Option<LeaseId> {
        self.lease.take()
    }

    /// Lease id String for IntentResult.lease_id population on success path.
    /// 提取成功路徑的 lease_id 字串供 IntentResult 填入。
    fn id_str(&self) -> Option<String> {
        self.lease.as_ref().map(|l| l.as_str().to_string())
    }
}

impl<'a> Drop for RouterLeaseGuard<'a> {
    fn drop(&mut self) {
        if let Some(lease) = self.lease.take() {
            // Best-effort release on rejection-path drop. If SM transition fails
            // (race / state already moved), log warn and rely on ExpiryGuardian
            // to clean up — never panic in Drop.
            // 拒絕路徑 Drop 時 best-effort 釋放；SM transition 失敗（race / state 已
            // 異動）僅 warn，依 ExpiryGuardian 過期清理；Drop 內絕不 panic。
            if let Err(e) = self
                .governance
                .release_lease(&lease, LeaseOutcome::Cancelled)
            {
                tracing::warn!(
                    error = %e,
                    "Gate 1.4 lease release on drop failed (rejection path); ExpiryGuardian will sweep"
                );
            }
        }
    }
}

/// Acquire helper for Gate 1.4: wraps `governance.acquire_lease()` and maps
/// `GovernanceError` variants to user-visible reject reasons. Returns the raw
/// `LeaseId` (Active or Bypass) when successful so caller wraps in
/// `RouterLeaseGuard`.
///
/// Gate 1.4 acquire 輔助：包 `governance.acquire_lease()` 並把 `GovernanceError`
/// 各分支映射為對使用者可見的拒絕原因；成功時回 raw `LeaseId`，由呼叫端包成
/// `RouterLeaseGuard`。
fn acquire_lease_for_gate_1_4(
    intent: &OrderIntent,
    governance: &GovernanceCore,
    profile: GovernanceProfile,
    source_stage: &str,
    now_ms: u64,
) -> Result<LeaseId, String> {
    // E-1 facade contract: 100..=300_000 ms TTL window. 30s per spec §3 sample.
    // E-1 facade contract：100..=300_000 ms TTL；spec §3 範例 30s。
    const ROUTER_LEASE_TTL_MS: u32 = 30_000;
    // Synthetic intent_id matches make_intent_id() shape. Empty engine_mode tag
    // is intentional — router does not own engine_mode; downstream persisters
    // produce the canonical id with em prefix. Lease side only needs uniqueness
    // for SM book-keeping.
    // 合成 intent_id 與 make_intent_id() 形狀對齊；router 不掌握 engine_mode 因此
    // 留空，下游 persister 產生 canonical id；lease 端只需 SM book-keeping 唯一。
    let intent_id = format!("intent-{}-{}-{}", source_stage, intent.symbol, now_ms);
    governance
        .acquire_lease(
            &intent_id,
            "TRADE_ENTRY",
            ROUTER_LEASE_TTL_MS,
            profile,
            source_stage,
        )
        .map_err(|e| match e {
            GovernanceError::AuthNotEffective => {
                "lease_facade: authorization not effective (Production fail-closed)".to_string()
            }
            GovernanceError::LeaseScopeNotPermitted(scope) => {
                format!("lease_facade: scope not permitted: {scope}")
            }
            GovernanceError::InvalidTtl(ttl) => {
                format!("lease_facade: invalid TTL {ttl} ms")
            }
            GovernanceError::LeaseNotFound(id) => {
                format!("lease_facade: lease not found: {id}")
            }
            GovernanceError::LeaseSmFailure(sm_err) => {
                format!("lease_facade: SM failure: {sm_err}")
            }
        })
}

fn apply_governor_order_constraints(
    governance: &GovernanceCore,
    is_reducing: bool,
    requested_qty: f64,
    existing_qty: Option<f64>,
) -> Result<f64, String> {
    let level = governance.risk.snapshot_level();
    let constraints = governance.risk.constraints();

    // Survival-first: reducing/unwind orders stay allowed. New entries must
    // honor tier constraints consistently across strategy + external paths.
    // 生存優先：減倉/平倉保持可用；新開倉必須一致遵守 tier 約束。
    if !is_reducing
        && (!constraints.new_entries_allowed
            || constraints.reduce_only
            || constraints.requires_operator)
    {
        return Err(format!(
            "risk_governor_{} blocks new entries (reduce_only={}, requires_operator={})",
            level, constraints.reduce_only, constraints.requires_operator
        ));
    }

    if is_reducing {
        return Ok(existing_qty.map_or(requested_qty, |qty| requested_qty.min(qty)));
    }

    let scaled_qty = requested_qty * constraints.position_size_multiplier.max(0.0);
    Ok(scaled_qty)
}

fn per_strategy_symbol_rejection(
    config: &RiskConfig,
    intent: &OrderIntent,
    is_reducing: bool,
) -> Option<String> {
    if is_reducing {
        return None;
    }
    crate::config::per_strategy_new_entry_rejection(config, &intent.strategy, &intent.symbol)
}

impl IntentProcessor {
    /// Process a single intent through the full governance pipeline (no edge-predictor features).
    /// Legacy entry-point retained for callers that do not yet compute FeatureVectorV1.
    /// Delegates to `process_with_features(None, ...)`.
    /// 通過完整治理管線處理單個意圖（舊 entry-point，無 ML features）。
    pub fn process(
        &self,
        intent: &OrderIntent,
        governance: &GovernanceCore,
        paper_state: &PaperState,
        atr: f64,
        profile: GovernanceProfile,
    ) -> IntentResult {
        self.process_with_features(intent, governance, paper_state, atr, profile, None, None, 0)
    }

    /// EDGE-P3-1 A4: Extended `process()` carrying optional ML features + DCS
    /// context_id + wall-clock ms. When `features=None` OR `cfg.use_edge_predictor=false`
    /// OR no predictor store is wired, behaves identically to the legacy path.
    /// EDGE-P3-1 A4：帶可選 ML features 與 DCS context_id 的 process()。
    /// features=None / use_edge_predictor=false / 無 store 時行為等同舊路徑。
    pub fn process_with_features(
        &self,
        intent: &OrderIntent,
        governance: &GovernanceCore,
        paper_state: &PaperState,
        atr: f64,
        profile: GovernanceProfile,
        features: Option<&FeatureVectorV1>,
        context_id: Option<&str>,
        now_ms: u64,
    ) -> IntentResult {
        // Gate 1: Governance authorization check (fail-closed)
        if !governance.is_authorized() {
            return IntentResult::rejected(RejectionCode::GovernanceNotAuthorized.format());
        }

        // ─── Gate 1.4: Decision Lease (SM-02 R-04 retrofit) ───
        // AMD-2026-05-02-01 Track E E-2 router gate. Feature-flag灰度 default OFF
        // (env `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0`). When ON we consult the
        // Rust facade `acquire_lease()`:
        //   • Production profile + auth effective → real Active lease (live path).
        //   • Exploration / Validation profile → LeaseId::Bypass (PA push back #1
        //     spec §3 point 1 trailing clause — paper / demo never touches SM).
        //   • Production but auth not effective → AuthNotEffective fail-closed.
        // Flag OFF: Gate 1.4 short-circuits (lease_id stays None); facade is still
        // callable from other consumers (Python IPC bridge E-3, etc.).
        // SLA：parking_lot::Mutex acquire ≤10 ns un-contended; whole gate ≤1 µs.
        // RouterLeaseGuard RAII：rejection 路徑下 Drop release Cancelled，避免 leak；
        // 成功路徑 .consume() 取出 lease 後由 fill consumer 釋放（Consumed）。
        // 灰度旗標 OFF（預設）→ 短路；ON → 真執行；spec §3 點 1 後段 short-circuit Bypass。
        // 失敗（AuthNotEffective / InvalidTtl / SmFailure / ScopeNotPermitted）一律 fail-closed 拒絕。
        let lease_guard = if governance.router_gate_enabled() {
            match acquire_lease_for_gate_1_4(intent, governance, profile, "router", now_ms) {
                Ok(lease) => RouterLeaseGuard::new(governance, Some(lease)),
                Err(reason) => return IntentResult::rejected(reason),
            }
        } else {
            RouterLeaseGuard::new(governance, None)
        };
        let lease_id_for_result: Option<String> = lease_guard.id_str();

        // Gate 1.5: Reject same-direction duplicate (prevent fee drain)
        // 拒絕同方向重複開倉（防止手續費消耗）
        if let Some(existing) = paper_state.get_position(&intent.symbol) {
            if existing.is_long == intent.is_long {
                return IntentResult::rejected(
                    RejectionCode::DuplicatePosition {
                        symbol: intent.symbol.clone(),
                        existing_is_long: existing.is_long,
                        existing_qty: existing.qty,
                    }
                    .format(),
                );
            }
        }

        // Gate 1.6: Negative-balance guard — reject brand-new opens when balance
        // has been wiped. Opposite-direction close/reduce (existing position
        // present) still flows to apply_fill so positions can be unwound.
        // Primary target is paper's synthetic-fill bust scenario (balance can
        // go negative without exchange margin enforcement); demo/live rarely
        // reach this because the exchange margin check rejects upstream.
        // Gate 1.6：負餘額守門 — 資金歸零後拒絕開新倉；已有反向倉位仍允許平倉/減倉。
        // 主要處理 paper 合成成交無真實保證金檢查導致的穿倉刷單；demo/live 幾乎不觸發
        // （交易所保證金檢查會在更早階段拒絕）。
        if paper_state.balance() <= 0.0 && paper_state.get_position(&intent.symbol).is_none() {
            return IntentResult::rejected(
                RejectionCode::InsufficientBalance {
                    balance: paper_state.balance(),
                }
                .format(),
            );
        }

        let reducing_existing_qty = paper_state
            .get_position(&intent.symbol)
            .filter(|p| p.is_long != intent.is_long)
            .map(|p| p.qty);
        let is_reducing = reducing_existing_qty.is_some();
        if let Some(reason) = per_strategy_symbol_rejection(&self.risk_config, intent, is_reducing)
        {
            return IntentResult::rejected(RejectionCode::RiskGate { reason }.format());
        }
        let pre_guardian_qty = if let Some(existing_qty) = reducing_existing_qty {
            intent.qty.min(existing_qty)
        } else {
            intent.qty
        };

        // Gate 2: Guardian 4-check
        let mut positions: Vec<ExistingPosition> = paper_state
            .positions()
            .iter()
            .map(|p| ExistingPosition {
                symbol: p.symbol.clone(),
                side: if p.is_long {
                    "Buy".into()
                } else {
                    "Sell".into()
                },
            })
            .collect();
        let guardian_leverage = if is_reducing {
            // Guardian's deterministic vetoes are designed for adding risk. A
            // capped opposite-side order can only unwind exposure, so keep the
            // survival path open even during drawdown/leverage stress.
            positions.clear();
            0.0
        } else {
            Self::compute_leverage(paper_state)
        };

        let ctx = PortfolioContext {
            drawdown_pct: if is_reducing {
                0.0
            } else {
                paper_state.drawdown_pct()
            },
            positions,
        };

        let check = TradeIntentCheck {
            symbol: intent.symbol.clone(),
            side: if intent.is_long {
                "Buy".into()
            } else {
                "Sell".into()
            },
            leverage: guardian_leverage, // RG-2: real leverage from positions for risk-adding orders
            qty: pre_guardian_qty,
        };

        let guardian_result = self.guardian.review(&check, &ctx);

        // Capture Guardian verdict for DB persistence (trading.risk_verdicts).
        // 捕獲 Guardian 裁定供 DB 持久化（trading.risk_verdicts）。
        let mut vi: Option<VerdictInfo> = Some(VerdictInfo {
            verdict: match guardian_result.verdict {
                Verdict::Approved => "Approved".to_string(),
                Verdict::Modified => "Modified".to_string(),
                Verdict::Rejected => "Rejected".to_string(),
            },
            risk_score: guardian_result.risk_score,
            reasons: guardian_result.reasons.clone(),
            modified_qty: guardian_result.modified_qty,
        });

        match guardian_result.verdict {
            Verdict::Rejected => {
                // AMD-2026-05-02-01 Track E E-2: rejection — RouterLeaseGuard
                // Drop releases Cancelled. lease_id deliberately left None on
                // rejection (caller writes verdict only; lease lineage is for
                // accepted intents that proceed to fill).
                // 拒絕路徑：RouterLeaseGuard Drop 釋放 Cancelled；rejection 不帶
                // lease_id（此欄位語意是「accepted intent → fill 之 lineage」）。
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(
                        RejectionCode::from_guardian_review(&guardian_result).format(),
                    ),
                    fill: None,
                    verdict_info: vi.take(),
                    approved_qty: 0.0,
                    resting_order: None,
                    maker_degraded_fallback: None,
                    lease_id: None,
                };
            }
            Verdict::Modified => {
                // Use modified qty if available
                // 如果有修改後的數量，使用修改後的
            }
            Verdict::Approved => {}
        }

        // ─── Gate 2.5: Kelly position sizing (Phase 2b) ───
        // Kelly 倉位計算（Phase 2b）
        let price = paper_state.latest_price(&intent.symbol).unwrap_or(0.0);
        let balance = paper_state.balance();
        let guardian_qty = guardian_result.modified_qty.unwrap_or(pre_guardian_qty);

        let kelly_qty = if let Some(ref kelly_cfg) = self.kelly_config {
            let stats = self
                .trade_stats
                .get(&intent.symbol)
                .cloned()
                .unwrap_or_default();
            // GAP-4: real ATR% from on_tick atr param (raw price units → fraction).
            // GAP-4：從 on_tick 傳入的真實 atr 計算 ATR% (價格單位轉小數)。
            let atr_pct = if price > 0.0 && atr > 0.0 {
                atr / price
            } else {
                0.0
            };
            crate::ml::kelly_sizer::compute_kelly_qty(
                kelly_cfg,
                &stats,
                balance,
                price,
                atr_pct,
                guardian_qty,
            )
        } else {
            guardian_qty
        };

        // ─── Gate 2.6: P1 hard cap = 2% of balance / price ───
        // P1 硬上限 = 餘額的 2% / 價格（不可超越的安全上限）
        let p1_max_qty = if price > 0.0 {
            balance * self.p1_risk_pct / price
        } else {
            kelly_qty
        };
        let governor_input_qty = if is_reducing {
            guardian_qty
        } else {
            kelly_qty.min(p1_max_qty)
        };

        let final_qty = match apply_governor_order_constraints(
            governance,
            is_reducing,
            governor_input_qty,
            reducing_existing_qty,
        ) {
            Ok(qty) => qty,
            Err(reason) => {
                return IntentResult::rejected(RejectionCode::RiskGate { reason }.format());
            }
        };

        // ─── PNL-1: Reject qty=0 ghost positions ───
        // 拒絕 qty=0 幽靈倉（小餘額被取整為 0 時必須阻止開倉）
        if !(final_qty > 0.0) {
            return IntentResult::rejected(
                RejectionCode::QtyZero {
                    final_qty,
                    kelly_qty,
                    p1_max_qty,
                    balance,
                    price,
                }
                .format(),
            );
        }

        // ─── Gate 2.7: Order admission risk check (RRC-1-B1) ───
        // 訂單准入風控檢查：日損/槓桿/持倉大小/曝險/相關曝險
        // Runs after P1 sizing so single-position-pct check uses final_qty.
        // 在 P1 調整後運行，以便單一持倉百分比檢查使用最終數量。
        {
            let exposure_pct = Self::compute_exposure_pct(paper_state);
            let daily_loss = self.daily_loss_pct(balance);
            let check_result = check_order_allowed(
                final_qty,
                price,
                balance,
                exposure_pct,
                Self::compute_correlated_exposure_pct(paper_state), // FIX-05: real correlated exposure
                Self::compute_leverage(paper_state), // RG-2: real leverage from positions
                daily_loss,
                is_reducing,
                &self.risk_config,
            );
            if !check_result.allowed {
                return IntentResult::rejected(
                    RejectionCode::RiskGate {
                        reason: check_result.reason,
                    }
                    .format(),
                );
            }

            // BLOCKER-3 D15: Cross-engine global notional cap check.
            // 跨引擎全局名目上限檢查。
            if !is_reducing {
                let order_notional = final_qty * price;
                if let Some(reason) = self.check_global_notional_cap(order_notional) {
                    return IntentResult::rejected(reason);
                }
            }
        }

        // ─── Gate 3: Cost gate — PH5-WIRE-1 mode-aware (paper/demo = exploration) ───
        // 成本門控：PH5-WIRE-1 模式感知（paper/demo = 探索模式）
        {
            let min_confidence = self.risk_config.cost_gate.min_confidence;
            if intent.confidence < min_confidence {
                return IntentResult::rejected(
                    RejectionCode::CostGateConfidence {
                        confidence: intent.confidence,
                        min_confidence,
                    }
                    .format(),
                );
            }
            // SEC-11: ATR=0 → fail-closed (cold-start by PNL-3 boot cooldown; runtime ATR=0 = indicator failure).
            // SEC-11：ATR=0 失敗關閉（冷啟動由 PNL-3 保護；runtime ATR=0 = 指標故障）。
            if !(atr > 0.0) {
                tracing::warn!(symbol = %intent.symbol,
                    "cost_gate fail-closed: ATR unavailable (SEC-11) / 成本門禁因 ATR 不可用拒絕");
                return IntentResult::rejected(RejectionCode::CostGateAtrUnavailable.format());
            }
            let volume_24h = paper_state.latest_turnover(&intent.symbol).unwrap_or(0.0);
            let fee_rate = self.fee_rate_for_intent(&intent.symbol, intent);
            let slippage_rate = self.slippage_rate_for_intent(intent, volume_24h);

            // ─── Gate 3a · EDGE-P3-1 A4: ML edge-predictor gate (spec §7.3) ───
            // Runs ahead of JS shrinkage. No-op when features=None / predictor disabled.
            // EDGE-P3-1 A4：ML 預測器 gate。features=None 或 predictor 禁用時為 no-op。
            let cost_bps = 2.0 * (fee_rate + slippage_rate) * 10_000.0;
            let ctx_id = context_id.unwrap_or("");
            match self.evaluate_predictor_gate(
                intent,
                paper_state,
                features,
                ctx_id,
                now_ms,
                cost_bps,
            ) {
                PredictorAction::Reject(reason) => {
                    return IntentResult::rejected(reason);
                }
                PredictorAction::SkipLegacyGate => {
                    // Predictor accepted; skip JS shrinkage fall-through.
                    // Predictor 接受；跳過 JS shrinkage 回退檢查。
                }
                PredictorAction::UseLegacyGate => {
                    if let Some(r) = self.cost_gate_paper(
                        &intent.strategy,
                        &intent.symbol,
                        atr,
                        intent.confidence,
                        final_qty,
                        price,
                        fee_rate,
                        slippage_rate,
                    ) {
                        // r already carries synthetic VerdictInfo (P0-6 permanent fix).
                        let _ = vi.take();
                        return r;
                    }
                }
            }
        }

        // Gate 4: Execute fill (paper mode)
        // EDGE-P2-3 Phase 1B-4.2: PostOnly limit intents are now ENQUEUED as
        // resting orders instead of filling at market on enqueue tick. Caller
        // (`on_tick`) detects `resting_order=Some(_)` and runs the enqueue
        // side-effect; `PaperState::sweep_resting_limit_orders_for_symbol`
        // converts queued orders to fills on future ticks that touch/cross
        // the limit price (bias guard #1 queue-position discount applied).
        // Legacy behaviour: order_type / limit_price were IGNORED — every
        // intent produced an immediate market fill, overstating passive
        // execution edge. Market / non-PostOnly intents keep the legacy path.
        // EDGE-P2-3 Phase 1B-4.2：PostOnly 限價意圖改為 ENQUEUE 為掛單，而非
        // 即時市價成交。caller（on_tick）偵測 resting_order=Some(_) 執行
        // enqueue；`sweep_resting_limit_orders_for_symbol` 於後續 tick 碰觸
        // 限價時轉為成交（含 bias #1 queue-position discount）。市價/非
        // PostOnly 保留原市價成交路徑。
        // EDGE-P2-3 Phase 1B-5: MakerKpi gate — before building the resting
        // draft, consult per-symbol fill-rate / net-edge KPI. When Degraded,
        // silently drop to the market fill path and flag
        // `maker_degraded_fallback = Some(symbol)` so caller counts the
        // fallback. Cold (warmup) is treated as pass — enqueue proceeds so
        // the accumulator can ever leave warmup.
        // EDGE-P2-3 Phase 1B-5：MakerKpi gate — 建 draft 前先查 per-symbol
        // 成交率 / net-edge。Degraded → 靜默 fallback 市價並標記 symbol，
        // caller 計 counter。Cold（warmup）視為 pass，以便累計離開冷啟。
        let mut kpi_fallback_symbol: Option<String> = None;
        if matches!(
            intent.time_in_force,
            Some(crate::order_manager::TimeInForce::PostOnly)
        ) && intent.order_type.eq_ignore_ascii_case("limit")
            && intent.limit_price.is_some()
        {
            let limit_price = intent.limit_price.unwrap_or(0.0);
            if limit_price > 0.0 && now_ms > 0 {
                // EDGE-P2-3 Phase 1B-5: honour operator patches via the live
                // MakerKpiConfig snapshot that TickPipeline mirrors into
                // IntentProcessor on every store version bump. Default fallback
                // is bit-identical to the pre-hot-reload commit.
                // EDGE-P2-3 Phase 1B-5：讀 TickPipeline 於每次 store 升版
                // 鏡像到 IntentProcessor 的 live MakerKpiConfig 快照，尊重
                // operator patch；未接 store 時仍為 `MakerKpiConfig::default()`
                // bit-identical。
                let kpi_cfg = &self.maker_kpi_config;
                let kpi_status = paper_state.maker_kpi_status(&intent.symbol, kpi_cfg, now_ms);
                if kpi_status.is_degraded() {
                    // Mark fallback; fall through to market fill path below.
                    // 標記 fallback；直接走下方市價路徑。
                    kpi_fallback_symbol = Some(intent.symbol.clone());
                } else {
                    let submit_ts_ms = now_ms;
                    let timeout_ms = intent.maker_timeout_ms.unwrap_or(45_000);
                    let deadline_ms = submit_ts_ms.saturating_add(timeout_ms);
                    let mid_price_at_submit =
                        paper_state.latest_price(&intent.symbol).unwrap_or(0.0);
                    let ctx = context_id.unwrap_or("").to_string();
                    // EDGE-P2-3 Phase 1B-4.3: stamp the submit-time funding rate
                    // so the sweep's bias guard #3 can later judge "adverse
                    // funding at submit → defer touch-equal FillPartial". An
                    // unknown rate (0.0) is treated as neutral — the guard
                    // short-circuits to `false` on zero thresholds or zero
                    // rates, so a symbol that has never emitted a ticker
                    // update still behaves bit-identically to pre-1B-4.3.
                    // EDGE-P2-3 Phase 1B-4.3：壓入提交時 funding rate 供 sweep
                    // bias guard #3 判斷「提交時逆向 → 推遲碰觸 FillPartial」。
                    // 0.0 = 尚未見過 ticker，視為中性；guard 於零門檻或零 rate
                    // 時短路回 false，因此行為與 1B-4.3 前一致。
                    let funding_rate_at_submit = paper_state
                        .latest_funding_rate(&intent.symbol)
                        .unwrap_or(0.0);
                    let draft = crate::paper_state::RestingLimitOrder {
                        symbol: intent.symbol.clone(),
                        is_long: intent.is_long,
                        qty: final_qty,
                        limit_price,
                        time_in_force: crate::order_manager::TimeInForce::PostOnly,
                        submit_ts_ms,
                        deadline_ms,
                        mid_price_at_submit,
                        // Client-minted link id — stable per (engine, symbol, ts)
                        // so `on_tick` Fill-row emission and operator cancel IPC
                        // can correlate. `pop_{em}_{symbol}_{ts_ms}` prefix keeps
                        // paper (`pop_`) distinguishable from exchange (`oc_`).
                        // 客戶端 link id：以 (引擎, 交易對, ts) 穩定生成；pop_ 前綴
                        // 區隔紙盤（pop_）與交易所（oc_）。
                        order_link_id: format!(
                            "pop_{}_{}_{}",
                            self.effective_engine_mode(),
                            intent.symbol,
                            submit_ts_ms
                        ),
                        context_id: ctx,
                        strategy: intent.strategy.clone(),
                        funding_rate_at_submit,
                    };
                    // AMD-2026-05-02-01 Track E E-2: success path (resting
                    // PostOnly draft accepted). consume() moves Active lease out
                    // of the guard so Drop does NOT release; fill consumer
                    // takes over (release Consumed after fill ack).
                    // 成功路徑（PostOnly 掛單接受）：consume() 取出 lease，Drop
                    // 不再 release；交由 fill consumer 在成交 ack 後釋放 Consumed。
                    let _consumed_lease = lease_guard.consume();
                    return IntentResult {
                        submitted: true,
                        rejected_reason: None,
                        fill: None,
                        verdict_info: vi.take(),
                        approved_qty: final_qty,
                        resting_order: Some(draft),
                        maker_degraded_fallback: None,
                        lease_id: lease_id_for_result.clone(),
                    };
                }
            }
        }

        let turnover = paper_state
            .latest_turnover(&intent.symbol)
            .unwrap_or(100_000_000.0);
        // Use live per-symbol fee rate (AccountManager → legacy → constant fallback).
        // EDGE-P2-3 Phase 1a: PostOnly intents pay maker fee; others pay taker.
        let fill = execution::execute_market_fill_with_rate(
            paper_state.latest_price(&intent.symbol).unwrap_or(0.0),
            final_qty,
            intent.is_long,
            turnover,
            self.fee_rate_for_intent(&intent.symbol, intent),
        );

        // AMD-2026-05-02-01 Track E E-2: success path (market fill emitted).
        // consume() moves Active lease out so Drop does NOT release; fill
        // consumer / paper_state apply_fill takes over (release Consumed).
        // 成功路徑（市價立即成交）：consume() 取出 lease，Drop 不再 release；
        // 由 fill consumer / paper_state apply_fill 釋放 Consumed。
        let _consumed_lease = lease_guard.consume();
        IntentResult {
            submitted: true,
            rejected_reason: None,
            fill: Some(fill),
            verdict_info: vi.take(),
            approved_qty: final_qty,
            resting_order: None,
            maker_degraded_fallback: kpi_fallback_symbol,
            lease_id: lease_id_for_result,
        }
    }

    /// EXT-1: Legacy gates-only entry. Delegates to `process_gates_only_with_features(None, ...)`.
    /// EXT-1：舊 gates-only entry-point，delegate 到 with-features 版本（無 ML features）。
    pub fn process_gates_only(
        &self,
        intent: &OrderIntent,
        governance: &GovernanceCore,
        paper_state: &PaperState,
        atr: f64,
        profile: GovernanceProfile,
    ) -> ExchangeGateResult {
        self.process_gates_only_with_features(
            intent,
            governance,
            paper_state,
            atr,
            profile,
            None,
            None,
            0,
        )
    }

    /// EDGE-P3-1 A4: Extended `process_gates_only` carrying optional ML features.
    /// EDGE-P3-1 A4：帶可選 ML features 的 process_gates_only。
    pub fn process_gates_only_with_features(
        &self,
        intent: &OrderIntent,
        governance: &GovernanceCore,
        paper_state: &PaperState,
        atr: f64,
        profile: GovernanceProfile,
        features: Option<&FeatureVectorV1>,
        context_id: Option<&str>,
        now_ms: u64,
    ) -> ExchangeGateResult {
        // Gate 1: Governance authorization
        if !governance.is_authorized() {
            return ExchangeGateResult::rejected(RejectionCode::GovernanceNotAuthorized.format());
        }

        // ─── Gate 1.4: Decision Lease (SM-02 R-04 retrofit) ───
        // AMD-2026-05-02-01 Track E E-2 router gate. Mirror of process_with_features
        // Gate 1.4 — see that function for rationale + flag semantics.
        // RouterLeaseGuard RAII：rejection 路徑下 Drop release Cancelled，避免 leak；
        // 成功路徑 .consume() 取出 lease 後由 fill consumer 釋放（Consumed）。
        let lease_guard = if governance.router_gate_enabled() {
            match acquire_lease_for_gate_1_4(
                intent,
                governance,
                profile,
                "router_gates_only",
                now_ms,
            ) {
                Ok(lease) => RouterLeaseGuard::new(governance, Some(lease)),
                Err(reason) => return ExchangeGateResult::rejected(reason),
            }
        } else {
            RouterLeaseGuard::new(governance, None)
        };
        let lease_id_for_result: Option<String> = lease_guard.id_str();

        // Gate 1.5: Reject same-direction duplicate
        if let Some(existing) = paper_state.get_position(&intent.symbol) {
            if existing.is_long == intent.is_long {
                return ExchangeGateResult::rejected(
                    RejectionCode::DuplicatePosition {
                        symbol: intent.symbol.clone(),
                        existing_is_long: existing.is_long,
                        existing_qty: existing.qty,
                    }
                    .format(),
                );
            }
        }
        let reducing_existing_qty = paper_state
            .get_position(&intent.symbol)
            .filter(|p| p.is_long != intent.is_long)
            .map(|p| p.qty);
        let is_reducing = reducing_existing_qty.is_some();
        if let Some(reason) = per_strategy_symbol_rejection(&self.risk_config, intent, is_reducing)
        {
            return ExchangeGateResult::rejected(RejectionCode::RiskGate { reason }.format());
        }
        let pre_guardian_qty = if let Some(existing_qty) = reducing_existing_qty {
            intent.qty.min(existing_qty)
        } else {
            intent.qty
        };

        // Gate 2: Guardian 4-check
        let mut positions: Vec<ExistingPosition> = paper_state
            .positions()
            .iter()
            .map(|p| ExistingPosition {
                symbol: p.symbol.clone(),
                side: if p.is_long {
                    "Buy".into()
                } else {
                    "Sell".into()
                },
            })
            .collect();
        let guardian_leverage = if is_reducing {
            positions.clear();
            0.0
        } else {
            Self::compute_leverage(paper_state)
        };
        let ctx = PortfolioContext {
            drawdown_pct: if is_reducing {
                0.0
            } else {
                paper_state.drawdown_pct()
            },
            positions,
        };
        let check = TradeIntentCheck {
            symbol: intent.symbol.clone(),
            side: if intent.is_long {
                "Buy".into()
            } else {
                "Sell".into()
            },
            leverage: guardian_leverage, // RG-2: real leverage from positions for risk-adding orders
            qty: pre_guardian_qty,
        };
        let guardian_result = self.guardian.review(&check, &ctx);

        // Capture Guardian verdict for DB persistence (trading.risk_verdicts).
        // 捕獲 Guardian 裁定供 DB 持久化（trading.risk_verdicts）。
        let mut vi: Option<VerdictInfo> = Some(VerdictInfo {
            verdict: match guardian_result.verdict {
                Verdict::Approved => "Approved".to_string(),
                Verdict::Modified => "Modified".to_string(),
                Verdict::Rejected => "Rejected".to_string(),
            },
            risk_score: guardian_result.risk_score,
            reasons: guardian_result.reasons.clone(),
            modified_qty: guardian_result.modified_qty,
        });

        if let Verdict::Rejected = guardian_result.verdict {
            // AMD-2026-05-02-01 Track E E-2: rejection — RouterLeaseGuard Drop
            // releases Cancelled. lease_id deliberately None on rejection.
            // 拒絕路徑：RouterLeaseGuard Drop 釋放 Cancelled；rejection 不帶 lease_id。
            return ExchangeGateResult {
                approved: false,
                rejected_reason: Some(
                    RejectionCode::from_guardian_review(&guardian_result).format(),
                ),
                approved_qty: 0.0,
                verdict_info: vi.take(),
                lease_id: None,
            };
        }
        // Gate 2.5: Kelly position sizing
        let price = paper_state.latest_price(&intent.symbol).unwrap_or(0.0);
        let balance = paper_state.balance();
        let guardian_qty = guardian_result.modified_qty.unwrap_or(pre_guardian_qty);
        let kelly_qty = if let Some(ref kelly_cfg) = self.kelly_config {
            let stats = self
                .trade_stats
                .get(&intent.symbol)
                .cloned()
                .unwrap_or_default();
            // GAP-4: real ATR% from on_tick atr param.
            let atr_pct = if price > 0.0 && atr > 0.0 {
                atr / price
            } else {
                0.0
            };
            crate::ml::kelly_sizer::compute_kelly_qty(
                kelly_cfg,
                &stats,
                balance,
                price,
                atr_pct,
                guardian_qty,
            )
        } else {
            guardian_qty
        };
        // Gate 2.6: P1 hard cap
        let p1_max_qty = if price > 0.0 {
            balance * self.p1_risk_pct / price
        } else {
            kelly_qty
        };
        let governor_input_qty = if is_reducing {
            guardian_qty
        } else {
            kelly_qty.min(p1_max_qty)
        };

        let final_qty = match apply_governor_order_constraints(
            governance,
            is_reducing,
            governor_input_qty,
            reducing_existing_qty,
        ) {
            Ok(qty) => qty,
            Err(reason) => {
                return ExchangeGateResult::rejected(RejectionCode::RiskGate { reason }.format());
            }
        };

        // ─── PNL-1: Reject qty=0 ghost positions ───
        // 拒絕 qty=0 幽靈倉（小餘額被取整為 0 時必須阻止開倉）
        if !(final_qty > 0.0) {
            return ExchangeGateResult::rejected(
                RejectionCode::QtyZero {
                    final_qty,
                    kelly_qty,
                    p1_max_qty,
                    balance,
                    price,
                }
                .format(),
            );
        }

        // ─── Gate 2.7: Order admission risk check (RRC-1-B1) ───
        // 訂單准入風控檢查：日損/槓桿/持倉大小/曝險/相關曝險
        // Runs after P1 sizing so single-position-pct check uses final_qty.
        // 在 P1 調整後運行，以便單一持倉百分比檢查使用最終數量。
        {
            let exposure_pct = Self::compute_exposure_pct(paper_state);
            let daily_loss = self.daily_loss_pct(balance);
            let check_result = check_order_allowed(
                final_qty,
                price,
                balance,
                exposure_pct,
                Self::compute_correlated_exposure_pct(paper_state), // FIX-05: real correlated exposure
                Self::compute_leverage(paper_state), // RG-2: real leverage from positions
                daily_loss,
                is_reducing,
                &self.risk_config,
            );
            if !check_result.allowed {
                return ExchangeGateResult::rejected(
                    RejectionCode::RiskGate {
                        reason: check_result.reason,
                    }
                    .format(),
                );
            }

            // BLOCKER-3 D15: Cross-engine global notional cap check.
            // 跨引擎全局名目上限檢查。
            if !is_reducing {
                let order_notional = final_qty * price;
                if let Some(reason) = self.check_global_notional_cap(order_notional) {
                    return ExchangeGateResult::rejected(reason);
                }
            }
        }

        // ─── Gate 3: Cost gate — profile-aware (3E-2a) ───
        // 成本門控：按 GovernanceProfile 分層（3E-2a）
        {
            let min_confidence = self.risk_config.cost_gate.min_confidence;
            if intent.confidence < min_confidence {
                return ExchangeGateResult::rejected(
                    RejectionCode::CostGateConfidence {
                        confidence: intent.confidence,
                        min_confidence,
                    }
                    .format(),
                );
            }
            // SEC-11: ATR=0 → fail-closed.
            if !(atr > 0.0) {
                tracing::warn!(symbol = %intent.symbol,
                    "cost_gate fail-closed: ATR unavailable (SEC-11) / 成本門禁因 ATR 不可用拒絕");
                return ExchangeGateResult::rejected(
                    RejectionCode::CostGateAtrUnavailable.format(),
                );
            }
            if let Some(reason) = self.fee_rate_staleness_rejection(now_ms) {
                tracing::warn!(
                    symbol = %intent.symbol,
                    reason = %reason,
                    "cost_gate fail-closed: fee rates stale / 成本門禁因費率過期拒絕"
                );
                return ExchangeGateResult::rejected(reason);
            }
            // EDGE-P2-3 Phase 1a: PostOnly intents pay maker fee in the cost gate.
            let fee_rate = self.fee_rate_for_intent(&intent.symbol, intent);
            let volume_24h = paper_state.latest_turnover(&intent.symbol).unwrap_or(0.0);
            let slippage_rate = self.slippage_rate_for_intent(intent, volume_24h);

            // ─── Gate 3a · EDGE-P3-1 A4: ML edge-predictor gate (spec §7.3) ───
            // No-op when features=None / predictor disabled. Shadow-mode always falls through.
            // EDGE-P3-1 A4：ML 預測器 gate；features=None / predictor 禁用 / shadow 模式 → 回退。
            let cost_bps = 2.0 * (fee_rate + slippage_rate) * 10_000.0;
            let ctx_id = context_id.unwrap_or("");
            match self.evaluate_predictor_gate(
                intent,
                paper_state,
                features,
                ctx_id,
                now_ms,
                cost_bps,
            ) {
                PredictorAction::Reject(reason) => {
                    return ExchangeGateResult::rejected(reason);
                }
                PredictorAction::SkipLegacyGate => {
                    // Predictor accepted; bypass JS shrinkage fall-through entirely.
                }
                PredictorAction::UseLegacyGate => {
                    // Profile-based cost gate selection (D3):
                    // Validation (Demo) → moderate: allows cold-start, blocks negative edge
                    // Production (Live) → strict: fail-closed without positive estimate
                    // 按 profile 選擇 cost gate：Validation 中等，Production 嚴格
                    let gate_result = match profile {
                        GovernanceProfile::Validation => self.cost_gate_moderate_with_slippage(
                            &intent.strategy,
                            &intent.symbol,
                            fee_rate,
                            slippage_rate,
                        ),
                        GovernanceProfile::Production => self.cost_gate_live_with_slippage(
                            &intent.strategy,
                            &intent.symbol,
                            fee_rate,
                            slippage_rate,
                        ),
                        GovernanceProfile::Exploration => None,
                    };
                    if let Some(r) = gate_result {
                        // r already carries synthetic VerdictInfo (P0-6 permanent fix).
                        // r is a rejection from cost_gate_*_with_slippage — its
                        // own lease_id stays None (default). RouterLeaseGuard
                        // Drop releases Cancelled.
                        // r 是 cost_gate 拒絕；自身 lease_id 預設 None；
                        // RouterLeaseGuard Drop 釋放 Cancelled。
                        let _ = vi.take();
                        return r;
                    }
                }
            }
        }

        // AMD-2026-05-02-01 Track E E-2: success path. consume() moves Active
        // lease out of the guard so Drop does NOT release; fill consumer
        // (downstream order-dispatch ack handler) takes over (release Consumed).
        // 成功路徑：consume() 取出 lease，Drop 不再 release；交由 fill consumer
        // 在交易所 ack 後釋放 Consumed。
        let _consumed_lease = lease_guard.consume();
        ExchangeGateResult {
            approved: true,
            rejected_reason: None,
            approved_qty: final_qty,
            verdict_info: vi.take(),
            lease_id: lease_id_for_result,
        }
    }
}
