//! Funding Rate Arbitrage Strategy V2 — delta-neutral paired execution.
//! 資金費率套利策略 V2 — delta 中性配對執行。
//!
//! Entry: |funding_rate| > threshold + edge > 0 after cost amortization.
//! Exit: rate flipped | rate < exit_threshold | basis > 0.5% | max hold 72h.

use super::Strategy;
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;

const TOTAL_COST_BPS: f64 = 34.0; // perp(11) + spot(20) + slippage(3)
const DEFAULT_EXPECTED_PERIODS: f64 = 3.0; // 8h funding periods
const FUNDING_THRESHOLD: f64 = 0.0005; // 5 bps
const MAX_BASIS_PCT: f64 = 0.5;
const MAX_HOLD_MS: u64 = 72 * 3_600_000;

pub struct FundingArb {
    active: bool,
    position: Option<FundingPosition>,
    last_trade_ms: u64,
    cooldown_ms: u64,
    default_qty: f64,
}

#[derive(Debug, Clone)]
struct FundingPosition {
    is_positive_funding: bool, // true = short perp + long spot
    entry_ms: u64,
    entry_funding_rate: f64,
}

impl FundingArb {
    pub fn new() -> Self {
        Self {
            active: true, position: None, last_trade_ms: 0,
            cooldown_ms: 3_600_000, default_qty: 0.01, // 1h cooldown
        }
    }

    fn compute_edge(funding_rate: f64) -> f64 {
        let amortized_fee = TOTAL_COST_BPS / 10_000.0 / DEFAULT_EXPECTED_PERIODS;
        funding_rate.abs() - amortized_fee
    }

    fn should_exit(&self, funding_rate: f64, basis_pct: f64, now_ms: u64) -> bool {
        let pos = match &self.position { Some(p) => p, None => return false };

        // Rate flipped sign
        if pos.is_positive_funding && funding_rate < 0.0 { return true; }
        if !pos.is_positive_funding && funding_rate > 0.0 { return true; }

        // Rate too small
        let exit_threshold = TOTAL_COST_BPS / 10_000.0 / 2.0; // half of total cost
        if funding_rate.abs() < exit_threshold { return true; }

        // Basis risk
        if basis_pct > MAX_BASIS_PCT { return true; }

        // Max hold time
        if now_ms - pos.entry_ms > MAX_HOLD_MS { return true; }

        false
    }
}

impl Strategy for FundingArb {
    fn name(&self) -> &str { "funding_arb" }
    fn is_active(&self) -> bool { self.active }

    fn on_tick(&mut self, _ctx: &TickContext) -> Vec<OrderIntent> {
        // Funding arb uses external funding rate data, not indicators
        // For now, check if any signal contains funding info
        // In production, funding rate comes via WS or REST polling
        // 資金費率套利使用外部資金費率數據，非指標
        // 目前暫時不產生信號，等 R-06 Python IPC 提供資金費率

        // Placeholder: funding_arb needs external data not available in tick context
        // Will be wired in R-06 when Python IPC provides funding rate

        vec![]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_edge_positive() {
        let edge = FundingArb::compute_edge(0.005); // 50 bps — well above amortized cost
        assert!(edge > 0.0);
    }

    #[test]
    fn test_edge_negative_small_rate() {
        let edge = FundingArb::compute_edge(0.0001); // 1 bps, below amortized cost
        assert!(edge < 0.0);
    }

    #[test]
    fn test_should_exit_rate_flip() {
        let mut s = FundingArb::new();
        s.position = Some(FundingPosition {
            is_positive_funding: true, entry_ms: 0, entry_funding_rate: 0.001,
        });
        assert!(s.should_exit(-0.001, 0.1, 1000));
    }

    #[test]
    fn test_should_exit_max_hold() {
        let mut s = FundingArb::new();
        s.position = Some(FundingPosition {
            is_positive_funding: true, entry_ms: 0, entry_funding_rate: 0.001,
        });
        assert!(s.should_exit(0.001, 0.1, MAX_HOLD_MS + 1));
    }

    #[test]
    fn test_should_exit_basis_risk() {
        let mut s = FundingArb::new();
        s.position = Some(FundingPosition {
            is_positive_funding: true, entry_ms: 0, entry_funding_rate: 0.001,
        });
        assert!(s.should_exit(0.001, 0.6, 1000)); // basis > 0.5%
    }

    #[test]
    fn test_no_exit_normal() {
        let mut s = FundingArb::new();
        s.position = Some(FundingPosition {
            is_positive_funding: true, entry_ms: 0, entry_funding_rate: 0.005,
        });
        // Rate 0.005 (50 bps) > exit_threshold 0.0017 → no exit
        assert!(!s.should_exit(0.005, 0.1, 1000));
    }

    #[test]
    fn test_on_tick_placeholder() {
        let mut s = FundingArb::new();
        let ctx = TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: 0,
            indicators: None, signals: vec![], h0_allowed: true,
        };
        assert!(s.on_tick(&ctx).is_empty());
    }
}
