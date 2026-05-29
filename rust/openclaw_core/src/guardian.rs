//! Guardian — 4 deterministic risk checks for trade intent vetting.
//! 守護者 — 4 項確定性風控檢查用於交易意圖審核。
//!
//! Checks: direction conflict, leverage cap, drawdown limit, position count.
//! 檢查：方向衝突、槓桿上限、回撤限制、持倉數量。

use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// Scoring calibration — INVARIANT safety constants / 評分校準 — 不變量安全常數
// ═══════════════════════════════════════════════════════════════════════════════
//
// P2-09（QC-SRMA-004）：以下為 Guardian 確定性風控的「評分校準」常數。
// 為什麼是 const 而非 RiskConfig 可調欄位：
//   - 這些權重決定否決（veto）的嚴重程度，是 fail-closed 安全底線的計分邏輯，
//     不是 operator 可調旋鈕。若開放 runtime 覆蓋，將允許在 hot-reload 路徑上
//     削弱否決校準，違反 CLAUDE.md Root Principle 4（策略不得繞過 Guardian）
//     與 6（不確定預設保守）。GuardianConfig 的「閾值」欄位（max_leverage 等）
//     已可由 RiskConfig 派生熱重載；本區僅鎖定「校準權重 / 邊界比例」。
//   - 之所以提取為具名 const（而非散落在 review() 內的字面量），是為了讓 QC /
//     E2 能從源碼直接驗證風控校準，並由下方 lock test 鎖定值 + 計分行為。
// 任一常數調整都必須同步更新 `tests::test_scoring_constants_locked` 並走 QC 風控覆核。

/// 方向衝突（同 symbol 反向持倉）的風險分權重。
const SCORE_DIRECTION_CONFLICT: f64 = 0.4;
/// 同向持倉數達上限的風險分權重。
/// 設計不變量：此值「故意」等於 VERDICT_REJECT_THRESHOLD（皆為 0.3），
/// 使「持倉數達上限」單獨觸發即構成硬性否決（零裕度）。任一側調整都會
/// 靜默把它降級成 Approved，因此修改 SCORE_POSITION_COUNT 或
/// VERDICT_REJECT_THRESHOLD 必須走 QC 風控覆核，並由
/// `tests::test_position_count_zero_margin_locked` 鎖定此邊界。
const SCORE_POSITION_COUNT: f64 = 0.3;
/// 槓桿超過 2x 上限（直接否決級）的風險分權重。
const SCORE_LEVERAGE_EXCESSIVE: f64 = 0.4;
/// 槓桿超過上限但未達 2x（縮倉修正級）的風險分權重。
const SCORE_LEVERAGE_OVER_CAP: f64 = 0.15;
/// 回撤超過上限的風險分權重。
const SCORE_DRAWDOWN_BREACH: f64 = 0.35;

/// 槓桿比例「直接否決」邊界：intent.leverage / max_leverage > 此值 → reject。
const LEVERAGE_RATIO_REJECT: f64 = 2.0;
/// 槓桿比例「縮倉修正」邊界：> 此值且未達 reject 邊界 → modify。
const LEVERAGE_RATIO_MODIFY: f64 = 1.0;

/// 否決判定的風險分門檻：硬性 reason 命中且 risk_score >= 此值 → reject。
/// 設計不變量：此值「故意」等於 SCORE_POSITION_COUNT（皆為 0.3），確保
/// position_count 維持「可獨立否決」能力。調整任一側須走 QC 風控覆核
/// （見 SCORE_POSITION_COUNT 註解與零裕度 lock test）。
const VERDICT_REJECT_THRESHOLD: f64 = 0.3;
/// risk_score 上限（clamp），避免多項命中後超過 1.0 失去可解釋性。
const RISK_SCORE_CAP: f64 = 1.0;

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
            risk_score += SCORE_DIRECTION_CONFLICT;
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
            risk_score += SCORE_POSITION_COUNT;
        }

        // Check 3: Leverage cap
        let leverage_ratio = intent.leverage / self.config.max_leverage;
        if leverage_ratio > LEVERAGE_RATIO_REJECT {
            // 2x over cap → reject
            reasons.push(format!(
                "leverage_excessive: {}x > 2x max ({}x)",
                intent.leverage, self.config.max_leverage
            ));
            risk_score += SCORE_LEVERAGE_EXCESSIVE;
        } else if leverage_ratio > LEVERAGE_RATIO_MODIFY {
            // Over cap but not 2x → modify
            modified_leverage = Some(self.config.modification_leverage_cap);
            modified_qty = Some(intent.qty * self.config.modification_size_factor);
            reasons.push(format!(
                "leverage_over_cap: {}x > {}x, modified to {}x",
                intent.leverage, self.config.max_leverage, self.config.modification_leverage_cap
            ));
            risk_score += SCORE_LEVERAGE_OVER_CAP;
        }

        // Check 4: Drawdown limit
        if ctx.drawdown_pct > self.config.max_drawdown_pct {
            reasons.push(format!(
                "drawdown_breach: {:.1}% > {:.1}%",
                ctx.drawdown_pct, self.config.max_drawdown_pct
            ));
            risk_score += SCORE_DRAWDOWN_BREACH;
        }

        let risk_score = (risk_score as f64).min(RISK_SCORE_CAP);

        // Verdict logic
        let verdict = if reasons.iter().any(|r| {
            r.starts_with("direction_conflict")
                || r.starts_with("leverage_excessive")
                || r.starts_with("drawdown_breach")
                || r.starts_with("position_count")
        }) && risk_score >= VERDICT_REJECT_THRESHOLD
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

    /// P2-09 lock test：鎖定評分校準常數的「值」。
    /// 為什麼：這些是 fail-closed 安全底線的計分權重，不得在重構/誤改中漂移。
    /// 任一斷言失敗代表有人改了校準常數，必須走 QC 風控覆核而非直接放行。
    #[test]
    fn test_scoring_constants_locked() {
        assert_eq!(SCORE_DIRECTION_CONFLICT, 0.4);
        assert_eq!(SCORE_POSITION_COUNT, 0.3);
        assert_eq!(SCORE_LEVERAGE_EXCESSIVE, 0.4);
        assert_eq!(SCORE_LEVERAGE_OVER_CAP, 0.15);
        assert_eq!(SCORE_DRAWDOWN_BREACH, 0.35);
        assert_eq!(LEVERAGE_RATIO_REJECT, 2.0);
        assert_eq!(LEVERAGE_RATIO_MODIFY, 1.0);
        assert_eq!(VERDICT_REJECT_THRESHOLD, 0.3);
        assert_eq!(RISK_SCORE_CAP, 1.0);
    }

    /// P2-09 lock test：鎖定「計分行為」而非僅常數值。
    /// 為什麼：常數值正確不代表計分路徑正確；本測試針對單一觸發路徑驗 risk_score。
    #[test]
    fn test_scoring_behavior_locked() {
        let g = Guardian::default(); // max_leverage=20, max_drawdown=15%, max_pos=3

        // 純方向衝突 → risk_score == SCORE_DIRECTION_CONFLICT
        let r = g.review(
            &buy_intent("BTC", 1.0),
            &ctx_with_positions(vec![("BTC", "Sell")], 0.0),
        );
        assert_eq!(r.risk_score, SCORE_DIRECTION_CONFLICT);

        // 純回撤超限 → risk_score == SCORE_DRAWDOWN_BREACH
        let r = g.review(&buy_intent("BTC", 1.0), &ctx_with_positions(vec![], 20.0));
        assert_eq!(r.risk_score, SCORE_DRAWDOWN_BREACH);

        // 槓桿縮倉修正級（>1x 未達 2x）→ risk_score == SCORE_LEVERAGE_OVER_CAP
        let r = g.review(&buy_intent("BTC", 30.0), &ctx_with_positions(vec![], 0.0));
        assert_eq!(r.risk_score, SCORE_LEVERAGE_OVER_CAP);
        assert_eq!(r.verdict, Verdict::Modified);

        // 槓桿直接否決級（>2x）→ risk_score == SCORE_LEVERAGE_EXCESSIVE
        let r = g.review(&buy_intent("BTC", 50.0), &ctx_with_positions(vec![], 0.0));
        assert_eq!(r.risk_score, SCORE_LEVERAGE_EXCESSIVE);
        assert_eq!(r.verdict, Verdict::Rejected);

        // 多項命中後 clamp 不超過 RISK_SCORE_CAP
        let r = g.review(
            &buy_intent("BTC", 50.0),
            &ctx_with_positions(vec![("BTC", "Sell"), ("ETH", "Buy")], 20.0),
        );
        assert!(r.risk_score <= RISK_SCORE_CAP);
    }

    /// P2-09 lock test：鎖定 position_count 的「零裕度否決」邊界。
    /// 為什麼：SCORE_POSITION_COUNT (0.3) 故意等於 VERDICT_REJECT_THRESHOLD (0.3)，
    /// 純持倉數觸發即恰好命中否決門檻（零裕度）。任一側被調整都會把此情境
    /// 靜默降級為 Approved，本測試把這個最脆弱的校準格鎖死，調整須走 QC 覆核。
    #[test]
    fn test_position_count_zero_margin_locked() {
        let g = Guardian::default(); // max_same_direction_positions = 3
        // 純持倉數觸發：3 個同向(Buy)持倉，皆異於 intent symbol → 無方向衝突；
        // 槓桿 1.0 不觸發，drawdown 0.0 不觸發 → 唯一 reason 為 position_count。
        let r = g.review(
            &buy_intent("BTC", 1.0),
            &ctx_with_positions(vec![("ETH", "Buy"), ("SOL", "Buy"), ("XRP", "Buy")], 0.0),
        );
        // 唯一風險來源即 position_count，risk_score 必恰等於 0.3（零裕度）。
        assert_eq!(r.risk_score, SCORE_POSITION_COUNT);
        assert_eq!(r.risk_score, VERDICT_REJECT_THRESHOLD);
        // 零裕度下仍須硬性否決；若降級為 Approved 代表校準漂移。
        assert_eq!(r.verdict, Verdict::Rejected);
        assert!(r.reasons.iter().all(|reason| reason.starts_with("position_count")));
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
