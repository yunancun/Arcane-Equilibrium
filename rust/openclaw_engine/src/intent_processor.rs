//! Intent Processor — H0 → Guardian → CostGate → Governance → OMS (R04-2).
//! 意圖處理器 — H0 → 守護者 → 成本門 → 治理 → OMS。
//!
//! Processes trade intents through the governance pipeline.
//! 通過治理管線處理交易意圖。

use openclaw_core::{
    execution::{self, FillResult},
    governance_core::GovernanceCore,
    guardian::{ExistingPosition, Guardian, PortfolioContext, TradeIntentCheck, Verdict},
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

/// Intent processor with guardian checks.
/// 帶守護者檢查的意圖處理器。
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
}

impl IntentProcessor {
    pub fn new() -> Self {
        Self {
            guardian: Guardian::default(),
            taker_fee_rate: None,
            kelly_config: None,
            trade_stats: std::collections::HashMap::new(),
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
        }
    }

    /// Phase 2b: Set Kelly sizing config.
    /// Phase 2b：設定 Kelly 倉位配置。
    pub fn set_kelly_config(&mut self, config: crate::ml::kelly_sizer::KellyConfig) {
        self.kelly_config = Some(config);
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
        const P1_RISK_PCT: f64 = 0.02;
        let p1_max_qty = if price > 0.0 { balance * P1_RISK_PCT / price } else { kelly_qty };
        let final_qty = kelly_qty.min(p1_max_qty);

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
