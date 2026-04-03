//! Guardian — 4 deterministic risk checks for trade intent vetting.
//! 守護者 — 4 項確定性風控檢查用於交易意圖審核。
//!
//! Checks: direction conflict, leverage cap, drawdown limit, position count.
//! 檢查：方向衝突、槓桿上限、回撤限制、持倉數量。

use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// Config / 配置
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardianConfig {
    pub max_leverage: f64,
    pub max_drawdown_pct: f64,
    pub max_same_direction_positions: usize,
    pub max_correlation: f64,
    pub modification_size_factor: f64,
    pub modification_leverage_cap: f64,
}

impl Default for GuardianConfig {
    fn default() -> Self {
        Self {
            max_leverage: 5.0,
            max_drawdown_pct: 15.0,
            max_same_direction_positions: 3,
            max_correlation: 0.85,
            modification_size_factor: 0.5,
            modification_leverage_cap: 2.0,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Intent & Verdict / 意圖 & 裁決
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone)]
pub struct TradeIntentCheck {
    pub symbol: String,
    pub side: String,   // "Buy" | "Sell"
    pub leverage: f64,
    pub qty: f64,
}

/// Existing position summary for conflict checks.
/// 現有持倉摘要用於衝突檢查。
#[derive(Debug, Clone)]
pub struct ExistingPosition {
    pub symbol: String,
    pub side: String,
}

/// Portfolio context for guardian checks.
/// 組合上下文用於守護者檢查。
#[derive(Debug, Clone)]
pub struct PortfolioContext {
    pub drawdown_pct: f64,
    pub positions: Vec<ExistingPosition>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Verdict {
    Approved,
    Modified,
    Rejected,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardianResult {
    pub verdict: Verdict,
    pub risk_score: f64,
    pub reasons: Vec<String>,
    pub modified_qty: Option<f64>,
    pub modified_leverage: Option<f64>,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Guardian / 守護者
// ═══════════════════════════════════════════════════════════════════════════════

pub struct Guardian {
    config: GuardianConfig,
}

impl Guardian {
    pub fn new(config: GuardianConfig) -> Self {
        Self { config }
    }

    /// Review a trade intent against 4 deterministic checks.
    /// 對交易意圖執行 4 項確定性檢查。
    pub fn review(&self, intent: &TradeIntentCheck, ctx: &PortfolioContext) -> GuardianResult {
        let mut reasons = Vec::new();
        let mut risk_score = 0.0;
        let mut modified_qty = None;
        let mut modified_leverage = None;

        // Check 1: Direction conflict — same symbol opposite side
        let has_conflict = ctx.positions.iter().any(|p| {
            p.symbol == intent.symbol && p.side != intent.side
        });
        if has_conflict {
            reasons.push("direction_conflict: opposite position exists".to_string());
            risk_score += 0.4;
        }

        // Check 2: Same-direction position count
        let same_dir_count = ctx.positions.iter()
            .filter(|p| p.side == intent.side)
            .count();
        if same_dir_count >= self.config.max_same_direction_positions {
            reasons.push(format!(
                "position_count: {same_dir_count} >= max {}",
                self.config.max_same_direction_positions
            ));
            risk_score += 0.3;
        }

        // Check 3: Leverage cap
        let leverage_ratio = intent.leverage / self.config.max_leverage;
        if leverage_ratio > 2.0 {
            // 2x over cap → reject
            reasons.push(format!(
                "leverage_excessive: {}x > 2x max ({}x)",
                intent.leverage, self.config.max_leverage
            ));
            risk_score += 0.4;
        } else if leverage_ratio > 1.0 {
            // Over cap but not 2x → modify
            modified_leverage = Some(self.config.modification_leverage_cap);
            modified_qty = Some(intent.qty * self.config.modification_size_factor);
            reasons.push(format!(
                "leverage_over_cap: {}x > {}x, modified to {}x",
                intent.leverage, self.config.max_leverage, self.config.modification_leverage_cap
            ));
            risk_score += 0.15;
        }

        // Check 4: Drawdown limit
        if ctx.drawdown_pct > self.config.max_drawdown_pct {
            reasons.push(format!(
                "drawdown_breach: {:.1}% > {:.1}%",
                ctx.drawdown_pct, self.config.max_drawdown_pct
            ));
            risk_score += 0.35;
        }

        let risk_score: f64 = risk_score;
        let risk_score = risk_score.min(1.0);

        // Verdict logic
        let verdict = if reasons.iter().any(|r| {
            r.starts_with("direction_conflict")
                || r.starts_with("leverage_excessive")
                || r.starts_with("drawdown_breach")
                || r.starts_with("position_count")
        }) && risk_score >= 0.3 {
            Verdict::Rejected
        } else if modified_qty.is_some() || modified_leverage.is_some() {
            Verdict::Modified
        } else {
            Verdict::Approved
        };

        GuardianResult { verdict, risk_score, reasons, modified_qty, modified_leverage }
    }
}

impl Default for Guardian {
    fn default() -> Self {
        Self::new(GuardianConfig::default())
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn empty_ctx() -> PortfolioContext {
        PortfolioContext { drawdown_pct: 0.0, positions: vec![] }
    }

    fn intent(symbol: &str, side: &str, leverage: f64) -> TradeIntentCheck {
        TradeIntentCheck { symbol: symbol.to_string(), side: side.to_string(), leverage, qty: 0.1 }
    }

    #[test]
    fn test_approved_no_issues() {
        let g = Guardian::default();
        let r = g.review(&intent("BTCUSDT", "Buy", 3.0), &empty_ctx());
        assert_eq!(r.verdict, Verdict::Approved);
        assert_eq!(r.risk_score, 0.0);
        assert!(r.reasons.is_empty());
    }

    #[test]
    fn test_direction_conflict_rejected() {
        let g = Guardian::default();
        let ctx = PortfolioContext {
            drawdown_pct: 0.0,
            positions: vec![ExistingPosition { symbol: "BTCUSDT".into(), side: "Sell".into() }],
        };
        let r = g.review(&intent("BTCUSDT", "Buy", 3.0), &ctx);
        assert_eq!(r.verdict, Verdict::Rejected);
        assert!(r.reasons[0].starts_with("direction_conflict"));
    }

    #[test]
    fn test_leverage_over_cap_modified() {
        let g = Guardian::default();
        let r = g.review(&intent("BTCUSDT", "Buy", 7.0), &empty_ctx());
        assert_eq!(r.verdict, Verdict::Modified);
        assert_eq!(r.modified_leverage, Some(2.0));
        assert_eq!(r.modified_qty, Some(0.05));
    }

    #[test]
    fn test_leverage_excessive_rejected() {
        let g = Guardian::default();
        let r = g.review(&intent("BTCUSDT", "Buy", 11.0), &empty_ctx());
        assert_eq!(r.verdict, Verdict::Rejected);
        assert!(r.reasons[0].starts_with("leverage_excessive"));
    }

    #[test]
    fn test_drawdown_breach() {
        let g = Guardian::default();
        let ctx = PortfolioContext { drawdown_pct: 16.0, positions: vec![] };
        let r = g.review(&intent("BTCUSDT", "Buy", 3.0), &ctx);
        assert_eq!(r.verdict, Verdict::Rejected);
    }

    #[test]
    fn test_position_count_limit() {
        let g = Guardian::default();
        let ctx = PortfolioContext {
            drawdown_pct: 0.0,
            positions: vec![
                ExistingPosition { symbol: "ETHUSDT".into(), side: "Buy".into() },
                ExistingPosition { symbol: "SOLUSDT".into(), side: "Buy".into() },
                ExistingPosition { symbol: "ADAUSDT".into(), side: "Buy".into() },
            ],
        };
        let r = g.review(&intent("BTCUSDT", "Buy", 3.0), &ctx);
        assert_eq!(r.verdict, Verdict::Rejected);
    }

    #[test]
    fn test_risk_score_capped_at_1() {
        let g = Guardian::default();
        let ctx = PortfolioContext {
            drawdown_pct: 20.0,
            positions: vec![
                ExistingPosition { symbol: "BTCUSDT".into(), side: "Sell".into() },
                ExistingPosition { symbol: "A".into(), side: "Buy".into() },
                ExistingPosition { symbol: "B".into(), side: "Buy".into() },
                ExistingPosition { symbol: "C".into(), side: "Buy".into() },
            ],
        };
        let r = g.review(&intent("BTCUSDT", "Buy", 11.0), &ctx);
        assert!(r.risk_score <= 1.0);
    }
}
