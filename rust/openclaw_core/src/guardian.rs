//! Guardian — 4 deterministic risk checks for trade intent vetting.
//! 守護者 — 4 項確定性風控檢查用於交易意圖審核。
//!
//! Checks: direction conflict, leverage cap, drawdown limit, position count.
//! 檢查：方向衝突、槓桿上限、回撤限制、持倉數量。

use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// Config / 配置
// ═══════════════════════════════════════════════════════════════════════════════

/// Guardian P0 trade-intent veto config.
///
/// ARCH-RC1 1C-4 E-Merge-4: every field below is now sourced from
/// `RiskConfig.limits` / `RiskConfig.anti_cluster` via
/// `tick_pipeline::apply_risk_snapshot`. GuardianConfig has no independent
/// state — it is a pure derived view that gets fully overwritten on every
/// hot-reload tick (no read-modify-write). The dead `max_correlation` field
/// (never read by `Guardian::review`) was deleted as part of this merge.
///
/// ARCH-RC1 1C-4 E-Merge-4：以下每個欄位都從 RiskConfig 派生，
/// apply_risk_snapshot 每個 hot-reload tick 完整覆蓋（無 RMW）。
/// 死欄位 `max_correlation`（review 從未讀取）已隨此 merge 刪除。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GuardianConfig {
    pub max_leverage: f64,
    pub max_drawdown_pct: f64,
    pub max_same_direction_positions: usize,
    pub modification_size_factor: f64,
    pub modification_leverage_cap: f64,
}

impl Default for GuardianConfig {
    /// Defaults match `RiskConfig::default()` so a Guardian constructed without
    /// a hot-reload wire-up still behaves sensibly (used by unit tests only;
    /// production paths always run apply_risk_snapshot before the first tick).
    /// 預設值對齊 RiskConfig::default()，未接 hot-reload 的 Guardian 也合理運作
    /// （僅單測使用；生產路徑首個 tick 前必跑 apply_risk_snapshot）。
    fn default() -> Self {
        Self {
            max_leverage: 20.0,
            max_drawdown_pct: 15.0,
            max_same_direction_positions: 3,
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
    pub side: String, // "Buy" | "Sell"
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
        let has_conflict = ctx
            .positions
            .iter()
            .any(|p| p.symbol == intent.symbol && p.side != intent.side);
        if has_conflict {
            reasons.push("direction_conflict: opposite position exists".to_string());
            risk_score += 0.4;
        }

        // Check 2: Same-direction position count
        let same_dir_count = ctx
            .positions
            .iter()
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

        let risk_score = (risk_score as f64).min(1.0);

        // Verdict logic
        let verdict = if reasons.iter().any(|r| {
            r.starts_with("direction_conflict")
                || r.starts_with("leverage_excessive")
                || r.starts_with("drawdown_breach")
                || r.starts_with("position_count")
        }) && risk_score >= 0.3
        {
            Verdict::Rejected
        } else if modified_qty.is_some() || modified_leverage.is_some() {
            Verdict::Modified
        } else {
            Verdict::Approved
        };

        GuardianResult {
            verdict,
            risk_score,
            reasons,
            modified_qty,
            modified_leverage,
        }
    }

    /// Get current config reference (for read-modify-write updates).
    /// 獲取當前配置引用。
    pub fn config(&self) -> &GuardianConfig {
        &self.config
    }

    /// Update guardian config at runtime (from IPC/Agent).
    /// 運行時更新守護者配置。
    pub fn update_config(&mut self, config: GuardianConfig) {
        self.config = config;
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

    fn buy_intent(symbol: &str, leverage: f64) -> TradeIntentCheck {
        TradeIntentCheck {
            symbol: symbol.into(),
            side: "Buy".into(),
            leverage,
            qty: 1.0,
        }
    }

    fn ctx_with_positions(positions: Vec<(&str, &str)>, drawdown: f64) -> PortfolioContext {
        PortfolioContext {
            drawdown_pct: drawdown,
            positions: positions
                .into_iter()
                .map(|(s, side)| ExistingPosition {
                    symbol: s.into(),
                    side: side.into(),
                })
                .collect(),
        }
    }

    #[test]
    fn test_approved_no_positions() {
        let g = Guardian::default();
        let r = g.review(&buy_intent("BTC", 1.0), &ctx_with_positions(vec![], 0.0));
        assert_eq!(r.verdict, Verdict::Approved);
    }

    #[test]
    fn test_direction_conflict_rejected() {
        let g = Guardian::default();
        let r = g.review(
            &buy_intent("BTC", 1.0),
            &ctx_with_positions(vec![("BTC", "Sell")], 0.0),
        );
        assert_eq!(r.verdict, Verdict::Rejected);
        assert!(r.reasons[0].contains("direction_conflict"));
    }

    #[test]
    fn test_position_count_rejected() {
        let g = Guardian::default(); // max 3
        let r = g.review(
            &buy_intent("BTC", 1.0),
            &ctx_with_positions(vec![("ETH", "Buy"), ("SOL", "Buy"), ("XRP", "Buy")], 0.0),
        );
        assert_eq!(r.verdict, Verdict::Rejected);
        assert!(r.reasons.iter().any(|r| r.contains("position_count")));
    }

    #[test]
    fn test_leverage_over_cap_modified() {
        // Use an explicit cap of 5x so the test is self-contained and not
        // coupled to GuardianConfig::default()'s value (which now mirrors
        // RiskConfig::default().limits.leverage_max post E-Merge-4).
        // 顯式設 5x 讓測試自洽，不耦合 Default 值（E-Merge-4 後對齊 RiskConfig）。
        let g = Guardian::new(GuardianConfig {
            max_leverage: 5.0,
            ..GuardianConfig::default()
        });
        let r = g.review(
            &buy_intent("BTC", 7.0), // 7x > 5x but < 10x
            &ctx_with_positions(vec![], 0.0),
        );
        assert_eq!(r.verdict, Verdict::Modified);
        assert!(r.modified_leverage.is_some());
    }

    #[test]
    fn test_drawdown_rejected() {
        let g = Guardian::default(); // max 15%
        let r = g.review(
            &buy_intent("BTC", 1.0),
            &ctx_with_positions(vec![], 20.0), // 20% drawdown
        );
        assert_eq!(r.verdict, Verdict::Rejected);
        assert!(r.reasons.iter().any(|r| r.contains("drawdown_breach")));
    }

    #[test]
    fn test_config_update() {
        let mut g = Guardian::default();
        assert_eq!(g.config().max_drawdown_pct, 15.0);
        let mut new_cfg = g.config().clone();
        new_cfg.max_drawdown_pct = 25.0;
        g.update_config(new_cfg);
        assert_eq!(g.config().max_drawdown_pct, 25.0);
        // 25% drawdown now passes
        let r = g.review(&buy_intent("BTC", 1.0), &ctx_with_positions(vec![], 20.0));
        assert_eq!(r.verdict, Verdict::Approved);
    }
}
