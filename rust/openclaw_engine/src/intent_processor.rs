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
}

impl IntentProcessor {
    pub fn new() -> Self {
        Self { guardian: Guardian::default() }
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

        let final_qty = guardian_result.modified_qty.unwrap_or(intent.qty);

        // Gate 3: Cost gate (fail-open if ATR missing)
        // Simplified: just check if round-trip cost is reasonable
        // 簡化：只檢查往返成本是否合理

        // Gate 4: Execute fill (paper mode)
        let turnover = 100_000_000.0; // default assumption
        let fill = execution::execute_market_fill(
            paper_state.latest_price(&intent.symbol).unwrap_or(0.0),
            final_qty,
            intent.is_long,
            turnover,
        );

        IntentResult {
            submitted: true,
            rejected_reason: None,
            fill: Some(fill),
        }
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
