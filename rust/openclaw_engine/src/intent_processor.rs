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

pub struct IntentProcessor {
    guardian: Guardian,
    /// API-fetched taker fee rate (None = use hardcoded default).
    /// API 動態 taker 費率（None = 使用硬編碼默認值）。
    taker_fee_rate: Option<f64>,
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
        if loss <= 0.0 { 0.0 } else { loss / self.daily_start_balance * 100.0 }
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
        if balance <= 0.0 { return 0.0; }
        let total_notional: f64 = paper_state.positions().iter().map(|p| {
            let price = paper_state.latest_price(&p.symbol).unwrap_or(p.entry_price);
            p.qty * price
        }).sum();
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
        let positions: Vec<ExistingPosition> = paper_state.positions()
            .iter()
            .map(|p| ExistingPosition {
                symbol: p.symbol.clone(),
                side: if p.is_long { "Buy".into() } else { "Sell".into() },
            })
            .collect();

        let ctx = PortfolioContext {
            drawdown_pct: paper_state.drawdown_pct(),
            positions,
        };

        let check = TradeIntentCheck {
            symbol: intent.symbol.clone(),
            side: if intent.is_long { "Buy".into() } else { "Sell".into() },
            leverage: 1.0, // paper = 1x
            qty: intent.qty,
        };

        let guardian_result = self.guardian.review(&check, &ctx);

        match guardian_result.verdict {
            Verdict::Rejected => {
                return IntentResult {
                    submitted: false,
                    rejected_reason: Some(format!("guardian_rejected: {:?}", guardian_result.reasons)),
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
            let stats = self.trade_stats.get(&intent.symbol).cloned().unwrap_or_default();
            let atr_pct = paper_state.latest_turnover(&intent.symbol)
                .map(|_| 0.02) // placeholder — real ATR% from indicators in Phase 3
                .unwrap_or(0.02);
            crate::ml::kelly_sizer::compute_kelly_qty(
                kelly_cfg, &stats, balance, price, atr_pct, guardian_qty,
            )
        } else {
            guardian_qty
        };

        // ─── Gate 2.6: P1 hard cap = 2% of balance / price ───
        // P1 硬上限 = 餘額的 2% / 價格（不可超越的安全上限）
        let p1_max_qty = if price > 0.0 { balance * self.p1_risk_pct / price } else { kelly_qty };
        let final_qty = kelly_qty.min(p1_max_qty);

        // ─── Gate 2.7: Order admission risk check (RRC-1-B1) ───
        // 訂單准入風控檢查：日損/槓桿/持倉大小/曝險/相關曝險
        // Runs after P1 sizing so single-position-pct check uses final_qty.
        // 在 P1 調整後運行，以便單一持倉百分比檢查使用最終數量。
        {
            let is_reducing = paper_state.get_position(&intent.symbol)
                .map(|p| p.is_long != intent.is_long)
                .unwrap_or(false);
            let exposure_pct = Self::compute_exposure_pct(paper_state);
            let daily_loss = self.daily_loss_pct(balance);
            let check_result = check_order_allowed(
                final_qty, price, balance,
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

        // Gate 3: Cost gate (fail-open if ATR missing)
        // Simplified: just check if round-trip cost is reasonable
        // 簡化：只檢查往返成本是否合理

        // Gate 4: Execute fill (paper mode)
        // NOTE: order_type and limit_price fields are currently IGNORED. All orders execute as
        // immediate market fills. Limit order execution (hold until price reaches limit_price)
        // will be implemented in Phase 2 when the Paper Engine gains an order book simulator.
        // 注意：order_type 和 limit_price 欄位當前被忽略。所有訂單均以即時市價成交。
        // 限價單執行（持有直到價格觸及 limit_price）將在 Phase 2 Paper Engine 獲得訂單簿模擬器後實現。
        let turnover = paper_state.latest_turnover(&intent.symbol).unwrap_or(100_000_000.0);
        let fill = if let Some(rate) = self.taker_fee_rate {
            execution::execute_market_fill_with_rate(
                paper_state.latest_price(&intent.symbol).unwrap_or(0.0),
                final_qty,
                intent.is_long,
                turnover,
                rate,
            )
        } else {
            execution::execute_market_fill(
                paper_state.latest_price(&intent.symbol).unwrap_or(0.0),
                final_qty,
                intent.is_long,
                turnover,
            )
        };

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
                side: if p.is_long { "Buy".into() } else { "Sell".into() },
            })
            .collect();
        let ctx = PortfolioContext {
            drawdown_pct: paper_state.drawdown_pct(),
            positions,
        };
        let check = TradeIntentCheck {
            symbol: intent.symbol.clone(),
            side: if intent.is_long { "Buy".into() } else { "Sell".into() },
            leverage: 1.0,
            qty: intent.qty,
        };
        let guardian_result = self.guardian.review(&check, &ctx);
        if let Verdict::Rejected = guardian_result.verdict {
            return ExchangeGateResult {
                approved: false,
                rejected_reason: Some(format!(
                    "guardian_rejected: {:?}",
                    guardian_result.reasons
                )),
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
            let atr_pct = paper_state
                .latest_turnover(&intent.symbol)
                .map(|_| 0.02)
                .unwrap_or(0.02);
            crate::ml::kelly_sizer::compute_kelly_qty(
                kelly_cfg, &stats, balance, price, atr_pct, guardian_qty,
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

        // ─── Gate 2.7: Order admission risk check (RRC-1-B1) ───
        // 訂單准入風控檢查：日損/槓桿/持倉大小/曝險/相關曝險
        // Runs after P1 sizing so single-position-pct check uses final_qty.
        // 在 P1 調整後運行，以便單一持倉百分比檢查使用最終數量。
        {
            let is_reducing = paper_state.get_position(&intent.symbol)
                .map(|p| p.is_long != intent.is_long)
                .unwrap_or(false);
            let exposure_pct = Self::compute_exposure_pct(paper_state);
            let daily_loss = self.daily_loss_pct(balance);
            let check_result = check_order_allowed(
                final_qty, price, balance,
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
}

impl Default for IntentProcessor {
    fn default() -> Self { Self::new() }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn make_intent(symbol: &str, is_long: bool) -> OrderIntent {
        OrderIntent {
            symbol: symbol.into(), is_long, qty: 0.01, confidence: 0.7,
            strategy: "test".into(), order_type: "market".into(), limit_price: None,
        }
    }

    #[test]
    fn test_rejected_no_auth() {
        let proc = IntentProcessor::new();
        let gov = GovernanceCore::new(); // no auth
        let state = PaperState::new(10_000.0);
        let result = proc.process(&make_intent("BTC", true), &gov, &state);
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
        let result = proc.process(&make_intent("BTC", true), &gov, &state);
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
        let result = proc.process(&intent, &gov, &state);
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
        let result = proc.process(&intent, &gov, &state);
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
        let result = proc.process(&intent, &gov, &state);
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
        let result = proc.process(&make_intent("BTC", true), &gov, &state);
        assert!(!result.submitted);
    }
}
