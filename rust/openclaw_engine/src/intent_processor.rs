//! Intent Processor — H0 → Guardian → CostGate → Governance → OMS (R04-2).
//! 意圖處理器 — H0 → 守護者 → 成本門 → 治理 → OMS。
//!
//! Processes trade intents through the governance pipeline.
//! 通過治理管線處理交易意圖。

use openclaw_core::{
    execution::{self, FillResult},
    governance_core::GovernanceCore,
    guardian::{ExistingPosition, Guardian, PortfolioContext, TradeIntentCheck, Verdict},
    risk::{check_order_allowed, RiskManagerConfig},
};
use serde::{Deserialize, Serialize};

use crate::paper_state::PaperState;

/// A trade intent from a strategy.
/// 來自策略的交易意圖。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OrderIntent {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub confidence: f64,
    pub strategy: String,
    pub order_type: String, // "market" or "limit"
    pub limit_price: Option<f64>,
}

/// Result of intent processing.
/// 意圖處理結果。
#[derive(Debug, Clone)]
pub struct IntentResult {
    pub submitted: bool,
    pub rejected_reason: Option<String>,
    pub fill: Option<FillResult>,
}

/// EXT-1: Result of gate-only processing for exchange mode.
/// EXT-1：交易所模式下僅門禁處理的結果。
#[derive(Debug, Clone)]
pub struct ExchangeGateResult {
    /// Whether the intent passed all gates / 意圖是否通過所有門禁
    pub approved: bool,
    /// Rejection reason if not approved / 未通過時的拒絕原因
    pub rejected_reason: Option<String>,
    /// Gate-approved quantity after Kelly sizing + P1 cap / 門禁批准的數量（Kelly + P1 上限後）
    pub approved_qty: f64,
}

/// Intent processor with guardian checks.
/// 帶守護者檢查的意圖處理器。
/// Default P1 risk cap (2% of balance per trade).
/// 默認 P1 風險上限（每筆交易餘額的 2%）。
const DEFAULT_P1_RISK_PCT: f64 = 0.02;

/// Bybit USDT perp default taker fee (0.055%) — fallback when API rate not available.
/// Bybit USDT 永續合約默認 taker 費率，API 未提供時的回退值。
const DEFAULT_TAKER_FEE_RATE: f64 = 0.00055;

pub struct IntentProcessor {
    guardian: Guardian,
    /// Legacy single-rate fallback (None = use hardcoded default).
    /// Preferred path: read per-symbol from `account_manager` (live API source).
    /// 舊版單費率回退（None = 用常量）。優先路徑：從 account_manager 讀取 per-symbol 真實費率。
    taker_fee_rate: Option<f64>,
    /// Live per-symbol fee rates from Bybit `/v5/account/fee-rate`.
    /// Bybit API 動態 per-symbol 費率（每小時刷新）。
    account_manager: Option<std::sync::Arc<crate::account_manager::AccountManager>>,
    /// Phase 2b: Kelly sizing config (None = disabled, passthrough).
    /// Phase 2b：Kelly 倉位配置（None = 禁用，直通）。
    kelly_config: Option<crate::ml::kelly_sizer::KellyConfig>,
    /// Phase 2b: Per-symbol trade stats for Kelly calculation.
    /// Phase 2b：每交易對的交易統計，用於 Kelly 計算。
    trade_stats: std::collections::HashMap<String, crate::ml::kelly_sizer::TradeStats>,
    /// P1 risk cap percentage (configurable, default 2%).
    /// P1 風險上限百分比（可配置，默認 2%）。
    p1_risk_pct: f64,
    /// RRC-1-B4: Risk manager config for check_order_allowed Gate 0.
    /// RRC-1-B4：風控管理器配置，用於 Gate 0 訂單准入檢查。
    risk_config: RiskManagerConfig,
    /// RRC-1-B2: Daily start balance for daily loss tracking (reset at UTC midnight).
    /// RRC-1-B2：每日起始餘額，用於日損追蹤（UTC 午夜重置）。
    daily_start_balance: f64,
    /// RRC-1-B2: UTC day number of last reset (days since epoch).
    /// RRC-1-B2：上次重置的 UTC 天數（自 epoch 起的天數）。
    daily_reset_day: u64,
}

impl IntentProcessor {
    pub fn new() -> Self {
        Self {
            guardian: Guardian::default(),
            taker_fee_rate: None,
            account_manager: None,
            kelly_config: None,
            trade_stats: std::collections::HashMap::new(),
            p1_risk_pct: DEFAULT_P1_RISK_PCT,
            risk_config: RiskManagerConfig::default(),
            daily_start_balance: 0.0,
            daily_reset_day: 0,
        }
    }

    /// Create with an API-fetched taker fee rate.
    /// 使用 API 動態費率創建。
    pub fn with_fee_rate(rate: f64) -> Self {
        Self {
            guardian: Guardian::default(),
            taker_fee_rate: Some(rate),
            account_manager: None,
            kelly_config: None,
            trade_stats: std::collections::HashMap::new(),
            p1_risk_pct: DEFAULT_P1_RISK_PCT,
            risk_config: RiskManagerConfig::default(),
            daily_start_balance: 0.0,
            daily_reset_day: 0,
        }
    }

    /// Set P1 risk cap percentage (e.g. 0.02 = 2%, 0.05 = 5%).
    /// 設定 P1 風險上限百分比。
    pub fn set_p1_risk_pct(&mut self, pct: f64) {
        self.p1_risk_pct = pct.clamp(0.001, 0.20); // Min 0.1%, max 20%
    }

    /// Get Guardian config for read-modify-write updates.
    /// 獲取守護者配置用於讀取-修改-寫回更新。
    pub fn guardian_config(&self) -> &openclaw_core::guardian::GuardianConfig {
        self.guardian.config()
    }

    /// Update Guardian config at runtime. / 運行時更新守護者配置。
    pub fn update_guardian_config(&mut self, config: openclaw_core::guardian::GuardianConfig) {
        self.guardian.update_config(config);
    }

    /// Phase 2b: Set Kelly sizing config.
    /// Phase 2b：設定 Kelly 倉位配置。
    pub fn set_kelly_config(&mut self, config: crate::ml::kelly_sizer::KellyConfig) {
        self.kelly_config = Some(config);
    }

    /// RRC-1-B4: Update risk manager config at runtime.
    /// RRC-1-B4：運行時更新風控管理器配置。
    pub fn update_risk_config(&mut self, config: RiskManagerConfig) {
        self.risk_config = config;
    }

    /// RRC-1-B4: Read-only access to risk manager config.
    /// RRC-1-B4：風控管理器配置的唯讀訪問。
    pub fn risk_config(&self) -> &RiskManagerConfig {
        &self.risk_config
    }

    /// PNL-7: Patch the dynamic-stop / RR tunables in-place. Each Some(v) is
    /// validated and applied; None leaves the field untouched. Returns the
    /// number of fields actually changed (for IPC ack).
    /// PNL-7：原地更新動態止損 / RR 三個可調參數，逐個驗證後生效。
    pub fn patch_dynamic_stop_params(
        &mut self,
        base_ratio: Option<f64>,
        cap_ratio: Option<f64>,
        trailing_min_rr_ratio: Option<f64>,
    ) -> u32 {
        let mut changed = 0;
        if let Some(v) = base_ratio {
            if v.is_finite() && (0.05..=1.0).contains(&v) {
                self.risk_config.dynamic_stop_base_ratio = v;
                changed += 1;
            }
        }
        if let Some(v) = cap_ratio {
            if v.is_finite() && (0.1..=1.0).contains(&v) {
                self.risk_config.dynamic_stop_cap_ratio = v;
                changed += 1;
            }
        }
        if let Some(v) = trailing_min_rr_ratio {
            if v.is_finite() && (0.0..=2.0).contains(&v) {
                self.risk_config.trailing_min_rr_ratio = v;
                changed += 1;
            }
        }
        changed
    }

    /// Session 12: Patch cost-gate + regime tunables in-place with validation.
    /// Each Some(v) is range-checked; invalid values silently dropped.
    /// Session 12：原地更新成本門 + regime 三類參數，逐個範圍校驗。
    pub fn patch_cost_gate_params(
        &mut self,
        min_confidence: Option<f64>,
        k_base: Option<f64>,
        k_medium: Option<f64>,
        k_small: Option<f64>,
        adx_trending_threshold: Option<f64>,
    ) -> u32 {
        let mut changed = 0;
        if let Some(v) = min_confidence {
            if v.is_finite() && (0.0..=1.0).contains(&v) {
                self.risk_config.cost_gate_min_confidence = v;
                changed += 1;
            }
        }
        if let Some(v) = k_base {
            if v.is_finite() && (0.5..=10.0).contains(&v) {
                self.risk_config.cost_gate_k_base = v;
                changed += 1;
            }
        }
        if let Some(v) = k_medium {
            if v.is_finite() && (0.5..=20.0).contains(&v) {
                self.risk_config.cost_gate_k_medium = v;
                changed += 1;
            }
        }
        if let Some(v) = k_small {
            if v.is_finite() && (0.5..=50.0).contains(&v) {
                self.risk_config.cost_gate_k_small = v;
                changed += 1;
            }
        }
        if let Some(v) = adx_trending_threshold {
            if v.is_finite() && (0.0..=100.0).contains(&v) {
                self.risk_config.adx_trending_threshold = v;
                changed += 1;
            }
        }
        changed
    }

    /// RRC-1-B2: Update daily start balance (called on each tick, resets at UTC midnight).
    /// RRC-1-B2：更新每日起始餘額（每 tick 調用，UTC 午夜重置）。
    pub fn maybe_reset_daily_balance(&mut self, balance: f64, ts_ms: u64) {
        let day = ts_ms / 86_400_000; // UTC day number / UTC 天數
        if day != self.daily_reset_day {
            self.daily_start_balance = balance;
            self.daily_reset_day = day;
        }
    }

    /// RRC-1-B2: Compute current daily loss percentage (internal).
    /// RRC-1-B2：計算當前日損百分比（內部）。
    fn daily_loss_pct(&self, current_balance: f64) -> f64 {
        if self.daily_start_balance <= 0.0 {
            return 0.0;
        }
        let loss = self.daily_start_balance - current_balance;
        if loss <= 0.0 {
            0.0
        } else {
            loss / self.daily_start_balance * 100.0
        }
    }

    /// RRC-1-C2: Public accessor for daily loss percentage (used by tick_pipeline Step 6).
    /// RRC-1-C2：日損百分比公開訪問器（用於 tick_pipeline 步驟 6）。
    pub fn daily_loss_pct_pub(&self, current_balance: f64) -> f64 {
        self.daily_loss_pct(current_balance)
    }

    /// RRC-1-B3: Compute total exposure percentage from positions.
    /// RRC-1-B3：從持倉計算總曝險百分比。
    fn compute_exposure_pct(paper_state: &PaperState) -> f64 {
        let balance = paper_state.balance();
        if balance <= 0.0 {
            return 0.0;
        }
        let total_notional: f64 = paper_state
            .positions()
            .iter()
            .map(|p| {
                let price = paper_state.latest_price(&p.symbol).unwrap_or(p.entry_price);
                p.qty * price
            })
            .sum();
        (total_notional / balance * 100.0).min(999.0)
    }

    /// Phase 2b: Record a closed trade for Kelly stats.
    /// Phase 2b：記錄已平倉交易用於 Kelly 統計。
    pub fn record_trade(&mut self, symbol: &str, pnl: f64) {
        self.trade_stats
            .entry(symbol.to_string())
            .or_default()
            .record(pnl);
    }

    /// Process a single intent through the full governance pipeline.
    /// 通過完整治理管線處理單個意圖。
    pub fn process(
        &self,
        intent: &OrderIntent,
        governance: &GovernanceCore,
        paper_state: &PaperState,
        atr: f64,
    ) -> IntentResult {
        // Gate 1: Governance authorization check (fail-closed)
        if !governance.is_authorized() {
            return IntentResult {
                submitted: false,
                rejected_reason: Some("governance_not_authorized".into()),
                fill: None,
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
            leverage: 1.0, // paper = 1x
            qty: intent.qty,
        };

        let guardian_result = self.guardian.review(&check, &ctx);

        match guardian_result.verdict {
            Verdict::Rejected => {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!(
                        "guardian_rejected: {:?}",
                        guardian_result.reasons
                    )),
                    fill: None,
                };
            }
            Verdict::Modified => {
                // Use modified qty if available
                // 如果有修改後的數量，使用修改後的
            }
            Verdict::Approved => {}
        }

        // ─── Gate 2.5: Kelly position sizing (Phase 2b) ─���─
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
                0.0, // correlated_exposure_pct — Phase C wiring
                1.0, // leverage — paper = 1x
                daily_loss,
                is_reducing,
                &self.risk_config,
            );
            if !check_result.allowed {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!("risk_gate: {}", check_result.reason)),
                    fill: None,
                };
            }
        }

        // ─── Gate 3: Cost gate — reject if EV < k × round_trip_fee ───
        // 成本門控：預期收益 < k × 往返手續費時拒絕
        // Session 12: thresholds read from RiskManagerConfig (was hardcoded 0.15 / 1.5).
        {
            let min_confidence = self.risk_config.cost_gate_min_confidence;
            if intent.confidence < min_confidence {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!(
                        "cost_gate: confidence {:.2} < min {:.2}",
                        intent.confidence, min_confidence,
                    )),
                    fill: None,
                };
            }

            if atr > 0.0 {
                let fee_rate = self.fee_rate(&intent.symbol);
                let expected_profit = atr * intent.confidence * final_qty;
                let notional = final_qty * price;
                let rt_fee = notional * 2.0 * fee_rate;
                let k = self.cost_gate_k(notional).max(self.risk_config.cost_gate_k_base);

                if expected_profit < k * rt_fee {
                    return IntentResult {
                        submitted: false,
                        rejected_reason: Some(format!(
                            "cost_gate: EV ${:.4} < {:.1}× fee ${:.4} (atr={:.6}, conf={:.2}, notional=${:.2})",
                            expected_profit, k, rt_fee, atr, intent.confidence, notional,
                        )),
                        fill: None,
                    };
                }
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
    ) -> ExchangeGateResult {
        // Gate 1: Governance authorization
        if !governance.is_authorized() {
            return ExchangeGateResult {
                approved: false,
                rejected_reason: Some("governance_not_authorized".into()),
                approved_qty: 0.0,
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
            leverage: 1.0,
            qty: intent.qty,
        };
        let guardian_result = self.guardian.review(&check, &ctx);
        if let Verdict::Rejected = guardian_result.verdict {
            return ExchangeGateResult {
                approved: false,
                rejected_reason: Some(format!("guardian_rejected: {:?}", guardian_result.reasons)),
                approved_qty: 0.0,
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
                0.0, // correlated_exposure_pct — Phase C wiring
                1.0, // leverage — paper = 1x
                daily_loss,
                is_reducing,
                &self.risk_config,
            );
            if !check_result.allowed {
                return ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some(format!("risk_gate: {}", check_result.reason)),
                    approved_qty: 0.0,
                };
            }
        }

        // ─── Gate 3: Cost gate (config-driven, Session 12) ───
        {
            let min_confidence = self.risk_config.cost_gate_min_confidence;
            if intent.confidence < min_confidence {
                return ExchangeGateResult {
                    approved: false,
                    rejected_reason: Some(format!(
                        "cost_gate: confidence {:.2} < min {:.2}",
                        intent.confidence, min_confidence,
                    )),
                    approved_qty: 0.0,
                };
            }

            if atr > 0.0 {
                let fee_rate = self.fee_rate(&intent.symbol);
                let expected_profit = atr * intent.confidence * final_qty;
                let notional = final_qty * price;
                let rt_fee = notional * 2.0 * fee_rate;
                let k = self.cost_gate_k(notional).max(self.risk_config.cost_gate_k_base);

                if expected_profit < k * rt_fee {
                    return ExchangeGateResult {
                        approved: false,
                        rejected_reason: Some(format!(
                            "cost_gate: EV ${:.4} < {:.1}× fee ${:.4} (atr={:.6}, conf={:.2}, notional=${:.2})",
                            expected_profit, k, rt_fee, atr, intent.confidence, notional,
                        )),
                        approved_qty: 0.0,
                    };
                }
            }
        }

        ExchangeGateResult {
            approved: true,
            rejected_reason: None,
            approved_qty: final_qty,
        }
    }

    /// Set dynamic fee rate post-creation (for hot-reload).
    /// 創建後設定動態費率（用於熱重載）。
    pub fn set_fee_rate(&mut self, rate: f64) {
        self.taker_fee_rate = Some(rate);
    }

    /// Set live AccountManager for per-symbol API-fetched fee rates.
    /// 設置 AccountManager 用於 per-symbol 真實費率。
    pub fn set_account_manager(
        &mut self,
        am: std::sync::Arc<crate::account_manager::AccountManager>,
    ) {
        self.account_manager = Some(am);
    }

    /// Effective taker fee rate for a symbol. Resolution order:
    ///   1. Live `AccountManager.taker_fee(symbol)` (Bybit API, refreshed hourly)
    ///   2. Legacy single-rate fallback (`taker_fee_rate`)
    ///   3. `DEFAULT_TAKER_FEE_RATE` constant (cold-boot before API responds)
    /// 有效 taker 費率（per-symbol）。優先序：API → legacy → 常量。
    pub fn fee_rate(&self, symbol: &str) -> f64 {
        if let Some(ref am) = self.account_manager {
            return am.taker_fee(symbol);
        }
        self.taker_fee_rate.unwrap_or(DEFAULT_TAKER_FEE_RATE)
    }

    /// PNL-5: Cost-gate k multiplier scaled by notional size, reading
    /// k_small / k_medium / k_base from RiskManagerConfig (Session 12 cleanup).
    /// PNL-5：成本門 k 倍率隨 notional 規模調整，三檔 k 從 config 讀取。
    fn cost_gate_k(&self, notional: f64) -> f64 {
        if notional < 50.0 {
            self.risk_config.cost_gate_k_small
        } else if notional < 200.0 {
            self.risk_config.cost_gate_k_medium
        } else {
            self.risk_config.cost_gate_k_base
        }
    }
}

impl Default for IntentProcessor {
    fn default() -> Self {
        Self::new()
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn make_intent(symbol: &str, is_long: bool) -> OrderIntent {
        OrderIntent {
            symbol: symbol.into(),
            is_long,
            qty: 0.01,
            confidence: 0.7,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        }
    }

    #[test]
    fn test_rejected_no_auth() {
        let proc = IntentProcessor::new();
        let gov = GovernanceCore::new(); // no auth
        let state = PaperState::new(10_000.0);
        let result = proc.process(&make_intent("BTC", true), &gov, &state, 500.0);
        assert!(!result.submitted);
        assert!(result.rejected_reason.unwrap().contains("governance"));
    }

    #[test]
    fn test_approved_with_auth() {
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 50000.0);
        let result = proc.process(&make_intent("BTC", true), &gov, &state, 500.0);
        assert!(result.submitted);
        assert!(result.fill.is_some());
    }

    #[test]
    fn test_position_sizing_caps_qty() {
        // P1 cap: 2% of 10,000 / 50,000 = 0.004 BTC
        // Intent qty 0.01 should be reduced to 0.004.
        // P1 上限：10,000 * 2% / 50,000 = 0.004 BTC
        // 意圖 qty 0.01 應被縮小為 0.004。
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 50_000.0);
        let intent = make_intent("BTC", true); // qty=0.01
        let result = proc.process(&intent, &gov, &state, 500.0);
        assert!(result.submitted);
        let fill = result.fill.unwrap();
        // fill.fill_qty should be 0.004 (= 10000 * 0.02 / 50000), not 0.01
        assert!(
            (fill.fill_qty - 0.004).abs() < 1e-9,
            "Expected qty ~0.004 from P1 sizing, got {}",
            fill.fill_qty
        );
    }

    #[test]
    fn test_position_sizing_tiny_balance() {
        // With tiny balance, P1 calc gives very small qty — no artificial floor.
        // 餘額極小時，P1 計算給出極小 qty — 無人為下限。
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(100.0); // tiny balance
        state.set_latest_price("BTC", 50_000.0);
        let intent = make_intent("BTC", true); // qty=0.01
        let result = proc.process(&intent, &gov, &state, 500.0);
        assert!(result.submitted);
        let fill = result.fill.unwrap();
        // P1 calc: 100 * 0.02 / 50000 = 0.00004 — used directly, no MIN_QTY floor.
        assert!(
            (fill.fill_qty - 0.00004).abs() < 1e-9,
            "Expected P1-sized qty 0.00004, got {}",
            fill.fill_qty
        );
    }

    #[test]
    fn test_position_sizing_small_intent_unchanged() {
        // If intent.qty < P1 cap, intent.qty is used (sizing never increases).
        // 如果 intent.qty < P1 上限，使用 intent.qty（sizing 只會縮小）。
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(1_000_000.0); // large balance
        state.set_latest_price("ETH", 3_000.0);
        // P1 cap: 1,000,000 * 0.02 / 3000 = 6.67; intent qty=0.01 is smaller
        let intent = make_intent("ETH", true); // qty=0.01
        let result = proc.process(&intent, &gov, &state, 500.0);
        assert!(result.submitted);
        let fill = result.fill.unwrap();
        assert!(
            (fill.fill_qty - 0.01).abs() < 1e-9,
            "Expected intent qty 0.01 (under P1 cap), got {}",
            fill.fill_qty
        );
    }

    #[test]
    fn test_guardian_drawdown_rejection() {
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 50000.0);
        // Simulate high drawdown
        state.force_drawdown(20.0);
        let result = proc.process(&make_intent("BTC", true), &gov, &state, 500.0);
        assert!(!result.submitted);
    }

    #[test]
    fn test_cost_gate_rejects_low_confidence() {
        // Confidence below 0.15 → always rejected regardless of ATR
        // 信心低於 0.15 → 無論 ATR 如何都拒絕
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("ETH", 2000.0);
        let intent = OrderIntent {
            symbol: "ETH".into(),
            is_long: true,
            qty: 0.01,
            confidence: 0.10,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        let result = proc.process(&intent, &gov, &state, 10.0);
        assert!(!result.submitted);
        assert!(result
            .rejected_reason
            .unwrap()
            .contains("cost_gate: confidence"));
    }

    #[test]
    fn test_cost_gate_rejects_low_ev() {
        // Low ATR + moderate confidence → EV < fee threshold → rejected
        // 低 ATR + 中等信心 → EV < 手續費門檻 → 拒絕
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 67000.0);
        let intent = OrderIntent {
            symbol: "BTC".into(),
            is_long: true,
            qty: 0.001,
            confidence: 0.30,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        // ATR=20 (very compressed for BTC), notional=$67 → rt_fee=$0.074 → EV=20×0.3×0.001=$0.006
        let result = proc.process(&intent, &gov, &state, 20.0);
        assert!(!result.submitted);
        assert!(result.rejected_reason.unwrap().contains("cost_gate: EV"));
    }

    #[test]
    fn test_process_gates_only_cost_gate_rejects_low_ev() {
        // I-01: process_gates_only must enforce Gate 3 cost gate like process().
        // I-01：process_gates_only 必須像 process() 一樣執行 Gate 3 成本門控。
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("BTC", 67000.0);
        let intent = OrderIntent {
            symbol: "BTC".into(),
            is_long: true,
            qty: 0.001,
            confidence: 0.30,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        // ATR=20 compressed → EV << fee → reject
        let result = proc.process_gates_only(&intent, &gov, &state, 20.0);
        assert!(!result.approved);
        assert!(result.rejected_reason.unwrap().contains("cost_gate"));
    }

    #[test]
    fn test_cost_gate_accepts_good_ev() {
        // High ATR + high confidence → EV >> fee → accepted
        // 高 ATR + 高信心 → EV >> 手續費 → 接受
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(10_000.0);
        state.set_latest_price("SOL", 80.0);
        let intent = OrderIntent {
            symbol: "SOL".into(),
            is_long: true,
            qty: 0.2,
            confidence: 0.7,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        // ATR=1.5, EV=1.5×0.7×0.2=$0.21, notional=$16 → rt_fee=$0.018 → 0.21 >> 0.027 ✓
        let result = proc.process(&intent, &gov, &state, 1.5);
        assert!(result.submitted);
    }

    #[test]
    fn test_pnl5_cost_gate_k_tiers() {
        // PNL-5: k=3.0 below $50, k=2.0 below $200, k=1.5 otherwise (defaults).
        let proc = IntentProcessor::new();
        assert_eq!(proc.cost_gate_k(20.0), 3.0);
        assert_eq!(proc.cost_gate_k(49.99), 3.0);
        assert_eq!(proc.cost_gate_k(50.0), 2.0);
        assert_eq!(proc.cost_gate_k(199.99), 2.0);
        assert_eq!(proc.cost_gate_k(200.0), 1.5);
        assert_eq!(proc.cost_gate_k(10_000.0), 1.5);
    }

    #[test]
    fn test_pnl5_small_notional_tightens_cost_gate() {
        // PNL-5: A trade that passed the old k=1.5 gate now fails under k=3.0
        // because notional ~ $20 falls into the smallest tier.
        // PNL-5：在 $20 notional 級別，原本通過 k=1.5 的單現在 k=3.0 應被攔截。
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(1_000.0); // $1k balance
        state.set_latest_price("SOL", 80.0);
        // qty 0.005 → notional $0.40 → tier <$50 → k=3.0
        // EV = atr(0.5) * conf(0.4) * 0.005 = 0.001
        // fee = 0.4 * 2 * 0.00055 = 0.00044
        // 1.5 * fee = 0.00066 (would pass), 3.0 * fee = 0.00132 (fails)
        let intent = OrderIntent {
            symbol: "SOL".into(),
            is_long: true,
            qty: 0.005,
            confidence: 0.4,
            strategy: "test".into(),
            order_type: "market".into(),
            limit_price: None,
        };
        let result = proc.process(&intent, &gov, &state, 0.5);
        assert!(!result.submitted, "PNL-5: expected reject under tightened k");
        assert!(result.rejected_reason.unwrap().contains("3.0× fee"));
    }

    #[test]
    fn test_pnl1_rejects_qty_zero_process() {
        // PNL-1: When P1 sizing produces final_qty=0 (e.g. balance=0), reject.
        // PNL-1：P1 sizing 產生 final_qty=0 時拒絕（餘額=0 等情況）
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(0.0); // zero balance → p1_max_qty=0
        state.set_latest_price("BTC", 50_000.0);
        let intent = make_intent("BTC", true);
        let result = proc.process(&intent, &gov, &state, 500.0);
        assert!(!result.submitted);
        let reason = result.rejected_reason.unwrap();
        assert!(reason.starts_with("qty_zero:"), "got: {}", reason);
    }

    #[test]
    fn test_pnl1_rejects_qty_zero_gates_only() {
        // PNL-1 (exchange path): same guard in process_gates_only.
        // PNL-1（exchange 路徑）：process_gates_only 同一守衛
        let proc = IntentProcessor::new();
        let mut gov = GovernanceCore::new();
        gov.grant_paper_authorization(None).unwrap();
        let mut state = PaperState::new(0.0);
        state.set_latest_price("BTC", 50_000.0);
        let intent = make_intent("BTC", true);
        let result = proc.process_gates_only(&intent, &gov, &state, 500.0);
        assert!(!result.approved);
        assert_eq!(result.approved_qty, 0.0);
        assert!(result.rejected_reason.unwrap().starts_with("qty_zero:"));
    }
}
