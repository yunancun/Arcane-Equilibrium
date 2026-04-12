//! Intent processing pipelines — paper and exchange gate paths.
//! 意圖處理管線 — paper 模式完整執行路徑和交易所模式門禁路徑。

use super::*;

impl IntentProcessor {
    /// Process a single intent through the full governance pipeline.
    /// 通過完整治理管線處理單個意圖。
    pub fn process(
        &self,
        intent: &OrderIntent,
        governance: &GovernanceCore,
        paper_state: &PaperState,
        atr: f64,
        _profile: GovernanceProfile,
    ) -> IntentResult {
        // Gate 1: Governance authorization check (fail-closed)
        if !governance.is_authorized() {
            return IntentResult {
                submitted: false,
                rejected_reason: Some("governance_not_authorized".into()),
                fill: None,
                verdict_info: None,
            };
        }

        // Gate 1.5: Reject same-direction duplicate (prevent fee drain)
        // 拒絕同方向重複開倉（防止手續費消耗）
        if let Some(existing) = paper_state.get_position(&intent.symbol) {
            if existing.is_long == intent.is_long {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!(
                        "duplicate_position: {} already {} {}",
                        intent.symbol,
                        if existing.is_long { "LONG" } else { "SHORT" },
                        existing.qty,
                    )),
                    fill: None,
                    verdict_info: None,
                };
            }
        }

        // Gate 2: Guardian 4-check
        let positions: Vec<ExistingPosition> = paper_state
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

        let ctx = PortfolioContext {
            drawdown_pct: paper_state.drawdown_pct(),
            positions,
        };

        let check = TradeIntentCheck {
            symbol: intent.symbol.clone(),
            side: if intent.is_long {
                "Buy".into()
            } else {
                "Sell".into()
            },
            leverage: self.account_leverage,
            qty: intent.qty,
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
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!(
                        "guardian_rejected: {:?}",
                        guardian_result.reasons
                    )),
                    fill: None,
                    verdict_info: vi.take(),
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
        let guardian_qty = guardian_result.modified_qty.unwrap_or(intent.qty);

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
        let final_qty = kelly_qty.min(p1_max_qty);

        // ─── PNL-1: Reject qty=0 ghost positions ───
        // 拒絕 qty=0 幽靈倉（小餘額被取整為 0 時必須阻止開倉）
        if !(final_qty > 0.0) {
            return IntentResult {
                submitted: false,
                rejected_reason: Some(format!(
                    "qty_zero: final_qty={:.8} (kelly={:.8}, p1_cap={:.8}, balance=${:.2}, price=${:.2})",
                    final_qty, kelly_qty, p1_max_qty, balance, price,
                )),
                fill: None,
                verdict_info: vi.take(),
            };
        }

        // ─── Gate 2.7: Order admission risk check (RRC-1-B1) ───
        // 訂單准入風控檢查：日損/槓桿/持倉大小/曝險/相關曝險
        // Runs after P1 sizing so single-position-pct check uses final_qty.
        // 在 P1 調整後運行，以便單一持倉百分比檢查使用最終數量。
        {
            let is_reducing = paper_state
                .get_position(&intent.symbol)
                .map(|p| p.is_long != intent.is_long)
                .unwrap_or(false);
            let exposure_pct = Self::compute_exposure_pct(paper_state);
            let daily_loss = self.daily_loss_pct(balance);
            let check_result = check_order_allowed(
                final_qty,
                price,
                balance,
                exposure_pct,
                Self::compute_correlated_exposure_pct(paper_state), // FIX-05: real correlated exposure
                self.account_leverage, // FIX-28: paper=1x, exchange=actual
                daily_loss,
                is_reducing,
                &self.risk_config,
            );
            if !check_result.allowed {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!("risk_gate: {}", check_result.reason)),
                    fill: None,
                    verdict_info: vi.take(),
                };
            }

            // BLOCKER-3 D15: Cross-engine global notional cap check.
            // 跨引擎全局名目上限檢查。
            if !is_reducing {
                let order_notional = final_qty * price;
                if let Some(reason) = self.check_global_notional_cap(order_notional) {
                    return IntentResult {
                        submitted: false,
                        rejected_reason: Some(reason),
                        fill: None,
                        verdict_info: vi.take(),
                    };
                }
            }
        }

        // ─── Gate 3: Cost gate — PH5-WIRE-1 mode-aware (paper/demo = exploration) ───
        // 成本門控：PH5-WIRE-1 模式感知（paper/demo = 探索模式）
        {
            let min_confidence = self.risk_config.cost_gate.min_confidence;
            if intent.confidence < min_confidence {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!(
                        "cost_gate: confidence {:.2} < min {:.2}",
                        intent.confidence, min_confidence,
                    )),
                    fill: None,
                    verdict_info: vi.take(),
                };
            }
            // SEC-11: ATR=0 → fail-closed (cold-start by PNL-3 boot cooldown; runtime ATR=0 = indicator failure).
            // SEC-11：ATR=0 失敗關閉（冷啟動由 PNL-3 保護；運行時 ATR=0 = 指標故障）。
            if !(atr > 0.0) {
                tracing::warn!(symbol = %intent.symbol,
                    "cost_gate fail-closed: ATR unavailable (SEC-11) / 成本門禁因 ATR 不可用拒絕");
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some("cost_gate: ATR unavailable (fail-closed, SEC-11)".into()),
                    fill: None,
                    verdict_info: vi.take(),
                };
            }
            let volume_24h = paper_state.latest_turnover(&intent.symbol).unwrap_or(0.0);
            if let Some(r) = self.cost_gate_paper(&intent.strategy, &intent.symbol,
                                                   atr, intent.confidence, final_qty, price, volume_24h) {
                return IntentResult { verdict_info: vi.take(), ..r };
            }
        }

        // Gate 4: Execute fill (paper mode)
        // NOTE: order_type and limit_price fields are currently IGNORED. All orders execute as
        // immediate market fills. Limit order execution (hold until price reaches limit_price)
        // will be implemented in Phase 2 when the Paper Engine gains an order book simulator.
        // 注意：order_type 和 limit_price 欄位當前被忽略。所有訂單均以即時市價成交。
        // 限價單執行（持有直到價格觸及 limit_price）將在 Phase 2 Paper Engine 獲得訂單簿模擬器後實現。
        let turnover = paper_state
            .latest_turnover(&intent.symbol)
            .unwrap_or(100_000_000.0);
        // Use live per-symbol fee rate (AccountManager → legacy → constant fallback).
        let fill = execution::execute_market_fill_with_rate(
            paper_state.latest_price(&intent.symbol).unwrap_or(0.0),
            final_qty,
            intent.is_long,
            turnover,
            self.fee_rate(&intent.symbol),
        );

        IntentResult {
            submitted: true,
            rejected_reason: None,
            fill: Some(fill),
            verdict_info: vi.take(),
        }
    }

    /// EXT-1: Process intent through governance gates only (no simulated execution).
    /// Returns ExchangeGateResult with approved_qty for exchange-mode order dispatch.
    /// EXT-1：僅通過治理門禁處理意圖（不模擬執行）。
    pub fn process_gates_only(
        &self,
        intent: &OrderIntent,
        governance: &GovernanceCore,
        paper_state: &PaperState,
        atr: f64,
        profile: GovernanceProfile,
    ) -> ExchangeGateResult {
        // Gate 1: Governance authorization
        if !governance.is_authorized() {
            return ExchangeGateResult {
                approved: false,
                rejected_reason: Some("governance_not_authorized".into()),
                approved_qty: 0.0,
                verdict_info: None,
            };
        }
        // Gate 1.5: Reject same-direction duplicate
        if let Some(existing) = paper_state.get_position(&intent.symbol) {
            if existing.is_long == intent.is_long {
                return ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some(format!(
                        "duplicate_position: {} already {} {}",
                        intent.symbol,
                        if existing.is_long { "LONG" } else { "SHORT" },
                        existing.qty,
                    )),
                    approved_qty: 0.0,
                    verdict_info: None,
                };
            }
        }
        // Gate 2: Guardian 4-check
        let positions: Vec<ExistingPosition> = paper_state
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
        let ctx = PortfolioContext {
            drawdown_pct: paper_state.drawdown_pct(),
            positions,
        };
        let check = TradeIntentCheck {
            symbol: intent.symbol.clone(),
            side: if intent.is_long {
                "Buy".into()
            } else {
                "Sell".into()
            },
            leverage: self.account_leverage,
            qty: intent.qty,
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
            return ExchangeGateResult {
                approved: false,
                rejected_reason: Some(format!("guardian_rejected: {:?}", guardian_result.reasons)),
                approved_qty: 0.0,
                verdict_info: vi.take(),
            };
        }
        // Gate 2.5: Kelly position sizing
        let price = paper_state.latest_price(&intent.symbol).unwrap_or(0.0);
        let balance = paper_state.balance();
        let guardian_qty = guardian_result.modified_qty.unwrap_or(intent.qty);
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
        let final_qty = kelly_qty.min(p1_max_qty);

        // ─── PNL-1: Reject qty=0 ghost positions ───
        // 拒絕 qty=0 幽靈倉（小餘額被取整為 0 時必須阻止開倉）
        if !(final_qty > 0.0) {
            return ExchangeGateResult {
                approved: false,
                rejected_reason: Some(format!(
                    "qty_zero: final_qty={:.8} (kelly={:.8}, p1_cap={:.8}, balance=${:.2}, price=${:.2})",
                    final_qty, kelly_qty, p1_max_qty, balance, price,
                )),
                approved_qty: 0.0,
                verdict_info: vi.take(),
            };
        }

        // ─── Gate 2.7: Order admission risk check (RRC-1-B1) ───
        // 訂單准入風控檢查：日損/槓桿/持倉大小/曝險/相關曝險
        // Runs after P1 sizing so single-position-pct check uses final_qty.
        // 在 P1 調整後運行，以便單一持倉百分比檢查使用最終數量。
        {
            let is_reducing = paper_state
                .get_position(&intent.symbol)
                .map(|p| p.is_long != intent.is_long)
                .unwrap_or(false);
            let exposure_pct = Self::compute_exposure_pct(paper_state);
            let daily_loss = self.daily_loss_pct(balance);
            let check_result = check_order_allowed(
                final_qty,
                price,
                balance,
                exposure_pct,
                Self::compute_correlated_exposure_pct(paper_state), // FIX-05: real correlated exposure
                self.account_leverage, // FIX-28: paper=1x, exchange=actual
                daily_loss,
                is_reducing,
                &self.risk_config,
            );
            if !check_result.allowed {
                return ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some(format!("risk_gate: {}", check_result.reason)),
                    approved_qty: 0.0,
                    verdict_info: vi.take(),
                };
            }

            // BLOCKER-3 D15: Cross-engine global notional cap check.
            // 跨引擎全局名目上限檢查。
            if !is_reducing {
                let order_notional = final_qty * price;
                if let Some(reason) = self.check_global_notional_cap(order_notional) {
                    return ExchangeGateResult {
                        approved: false,
                        rejected_reason: Some(reason),
                        approved_qty: 0.0,
                        verdict_info: vi.take(),
                    };
                }
            }
        }

        // ─── Gate 3: Cost gate — profile-aware (3E-2a) ───
        // 成本門控：按 GovernanceProfile 分層（3E-2a）
        {
            let min_confidence = self.risk_config.cost_gate.min_confidence;
            if intent.confidence < min_confidence {
                return ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some(format!(
                        "cost_gate: confidence {:.2} < min {:.2}",
                        intent.confidence, min_confidence,
                    )),
                    approved_qty: 0.0,
                    verdict_info: vi.take(),
                };
            }
            // SEC-11: ATR=0 → fail-closed.
            if !(atr > 0.0) {
                tracing::warn!(symbol = %intent.symbol,
                    "cost_gate fail-closed: ATR unavailable (SEC-11) / 成本門禁因 ATR 不可用拒絕");
                return ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some("cost_gate: ATR unavailable (fail-closed, SEC-11)".into()),
                    approved_qty: 0.0,
                    verdict_info: vi.take(),
                };
            }
            let fee_rate = self.fee_rate(&intent.symbol);
            let volume_24h = paper_state.latest_turnover(&intent.symbol).unwrap_or(0.0);
            // Profile-based cost gate selection (D3):
            // Validation (Demo) → moderate: allows cold-start, blocks negative edge
            // Production (Live) → strict: fail-closed without positive estimate
            // 按 profile 選擇 cost gate：Validation 中等，Production 嚴格
            let gate_result = match profile {
                GovernanceProfile::Validation => self.cost_gate_moderate(&intent.strategy, &intent.symbol, fee_rate, volume_24h),
                GovernanceProfile::Production => self.cost_gate_live(&intent.strategy, &intent.symbol, fee_rate, volume_24h),
                GovernanceProfile::Exploration => None, // Paper doesn't call process_gates_only, but handle gracefully
            };
            if let Some(r) = gate_result {
                return ExchangeGateResult { verdict_info: vi.take(), ..r };
            }
        }

        ExchangeGateResult {
            approved: true,
            rejected_reason: None,
            approved_qty: final_qty,
            verdict_info: vi.take(),
        }
    }
}
