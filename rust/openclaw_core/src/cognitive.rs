//! CognitiveModulator — L0 Decision Threshold Modulation
//! CognitiveModulator — L0 決策門檻調製
//!
//! MODULE_NOTE (中文):
//!   CognitiveModulator 根據歷史績效、遺憾數據、蒙特卡洛建議動態調整策略決策參數：
//!   - confidence_floor：信號信心下限（越高 = 越保守）
//!   - qty_ceiling：倉位大小上限倍率（1.0 = 滿倉，0.3 = 最小倉）
//!   - stoploss_multiplier：止損距離倍率
//!   - scan_interval_secs：掃描間隔（秒）
//!
//!   所有輸出使用 EMA(α=0.3) 平滑以防止振盪。
//!   \[Q1\] max 單因子（不求和），\[Q6\] EMA 平滑，\[R1-5\] 連虧時忽略負向壓力。
//!
//! MODULE_NOTE (English):
//!   CognitiveModulator dynamically adjusts Strategist decision parameters based on
//!   historical performance, regret data, and Monte Carlo suggestions:
//!   - confidence_floor: signal confidence minimum (higher = more conservative)
//!   - qty_ceiling: position size ceiling multiplier (1.0 = full, 0.3 = minimum)
//!   - stoploss_multiplier: stop-loss distance multiplier
//!   - scan_interval_secs: scan interval (seconds)
//!
//!   All outputs EMA-smoothed (α=0.3) to prevent oscillation.
//!   \[Q1\] max single-factor (not sum), \[Q6\] EMA smoothing, \[R1-5\] ignore downward on streak.

// ── Base parameters / 基礎參數 ──
const BASE_CONFIDENCE_FLOOR: f64 = 0.60;
const BASE_QTY_CEILING: f64 = 1.0;
const BASE_STOPLOSS_MULT: f64 = 1.0;
const BASE_SCAN_INTERVAL: f64 = 1800.0;

// ── Clamp ranges / 限幅範圍 ──
const MIN_CONF_FLOOR: f64 = 0.45;
const MAX_CONF_FLOOR: f64 = 0.85;
const MIN_QTY_CEIL: f64 = 0.3;
const MAX_QTY_CEIL: f64 = 1.0;
const MIN_SL_MULT: f64 = 0.8;
const MAX_SL_MULT: f64 = 2.0;
const MIN_SCAN: f64 = 300.0;
const MAX_SCAN: f64 = 3600.0;

// ── EMA smoothing / EMA 平滑 ──
const EMA_ALPHA: f64 = 0.3;

/// Clamp value to [lo, hi]. / 將值限幅到 [lo, hi]。
#[inline]
fn clamp(v: f64, lo: f64, hi: f64) -> f64 {
    v.max(lo).min(hi)
}

// ────────────────────────────────────────────────────────────────
// Input / Output structs / 輸入輸出結構
// ────────────────────────────────────────────────────────────────

/// Regret data from OpportunityTracker.
/// 來自 OpportunityTracker 的遺憾數據。
#[derive(Debug, Clone, Default)]
pub struct RegretInput {
    /// "undertrading" / "overtrading" / "balanced"
    pub direction: String,
    /// Average missed profit percentage / 平均錯過利潤百分比
    pub avg_regret: f64,
    /// Average dodged loss percentage / 平均避開損失百分比
    pub avg_dodged: f64,
}

/// Dream engine suggestion data.
/// 夢境引擎建議數據。
#[derive(Debug, Clone, Default)]
pub struct DreamInput {
    /// Suggested stoploss multiplier value / 建議的止損倍率值
    pub stoploss_suggestion: f64,
    /// Dream confidence (0-1) / 夢境信心度 (0-1)
    pub confidence: f64,
}

/// Snapshot of all cognitive output parameters.
/// 所有認知輸出參數的快照。
#[derive(Debug, Clone)]
pub struct CognitiveOutput {
    pub confidence_floor: f64,
    pub qty_ceiling: f64,
    pub stoploss_multiplier: f64,
    pub scan_interval_secs: u64,
    pub update_count: u64,
}

// ────────────────────────────────────────────────────────────────
// CognitiveModulator / 認知調製器
// ────────────────────────────────────────────────────────────────

/// L0 deterministic decision threshold modulator.
/// L0 確定性決策門檻調製器。
///
/// Thread-safe: no shared mutable state beyond internal parameters.
/// 線程安全：除內部參數外無共享可變狀態。
pub struct CognitiveModulator {
    /// EMA-smoothed confidence floor / EMA 平滑信心下限
    confidence_floor: f64,
    /// EMA-smoothed qty ceiling / EMA 平滑倉位上限
    qty_ceiling: f64,
    /// EMA-smoothed stoploss multiplier / EMA 平滑止損倍率
    stoploss_multiplier: f64,
    /// EMA-smoothed scan interval (seconds) / EMA 平滑掃描間隔（秒）
    scan_interval_secs: f64,
    /// EMA alpha coefficient / EMA 平滑係數
    alpha: f64,
    /// Total update invocations / 更新調用總次數
    update_count: u64,
}

impl Default for CognitiveModulator {
    fn default() -> Self {
        Self::new()
    }
}

impl CognitiveModulator {
    /// Create a new modulator with default parameters.
    /// 建立帶預設參數的新調製器。
    pub fn new() -> Self {
        Self {
            confidence_floor: BASE_CONFIDENCE_FLOOR,
            qty_ceiling: BASE_QTY_CEILING,
            stoploss_multiplier: BASE_STOPLOSS_MULT,
            scan_interval_secs: BASE_SCAN_INTERVAL,
            alpha: EMA_ALPHA,
            update_count: 0,
        }
    }

    /// Update all cognitive parameters based on current trading state.
    /// 根據當前交易狀態更新所有認知參數。
    ///
    /// Returns a snapshot of all current parameters.
    /// 返回所有當前參數的快照。
    pub fn update(
        &mut self,
        consecutive_losses: u32,
        weekly_net_pnl: f64,
        regret_data: &RegretInput,
        dream_data: &DreamInput,
    ) -> CognitiveOutput {
        self.update_count += 1;

        // ── Confidence floor / 信心下限 ──
        let target_conf =
            Self::compute_confidence_floor(consecutive_losses, weekly_net_pnl, regret_data);
        self.confidence_floor =
            self.alpha * target_conf + (1.0 - self.alpha) * self.confidence_floor;

        // ── Qty ceiling / 倉位上限 ──
        let target_qty = Self::compute_qty_ceiling(consecutive_losses, weekly_net_pnl);
        self.qty_ceiling = self.alpha * target_qty + (1.0 - self.alpha) * self.qty_ceiling;

        // ── Stoploss multiplier / 止損倍率 ──
        let target_sl = Self::compute_stoploss_mult(dream_data);
        self.stoploss_multiplier =
            self.alpha * target_sl + (1.0 - self.alpha) * self.stoploss_multiplier;

        // ── Scan interval / 掃描間隔 ──
        let target_scan = Self::compute_scan_interval(weekly_net_pnl, regret_data);
        self.scan_interval_secs =
            self.alpha * target_scan + (1.0 - self.alpha) * self.scan_interval_secs;

        self.snapshot()
    }

    // ── Getters / 存取器 ──

    /// Current confidence floor (rounded to 4 decimal places).
    /// 當前信心下限（四捨五入到小數第 4 位）。
    pub fn confidence_floor(&self) -> f64 {
        (self.confidence_floor * 10_000.0).round() / 10_000.0
    }

    /// Current qty ceiling (rounded to 4 decimal places).
    /// 當前倉位上限（四捨五入到小數第 4 位）。
    pub fn qty_ceiling(&self) -> f64 {
        (self.qty_ceiling * 10_000.0).round() / 10_000.0
    }

    /// Current stoploss multiplier (rounded to 4 decimal places).
    /// 當前止損倍率（四捨五入到小數第 4 位）。
    pub fn stoploss_multiplier(&self) -> f64 {
        (self.stoploss_multiplier * 10_000.0).round() / 10_000.0
    }

    /// Current scan interval in whole seconds.
    /// 當前掃描間隔（整數秒）。
    pub fn scan_interval_secs(&self) -> u64 {
        self.scan_interval_secs as u64
    }

    /// Return a snapshot of all parameters.
    /// 返回所有參數的快照。
    pub fn snapshot(&self) -> CognitiveOutput {
        CognitiveOutput {
            confidence_floor: self.confidence_floor(),
            qty_ceiling: self.qty_ceiling(),
            stoploss_multiplier: self.stoploss_multiplier(),
            scan_interval_secs: self.scan_interval_secs(),
            update_count: self.update_count,
        }
    }

    // ── Internal computations / 內部計算 ──

    /// Compute raw confidence floor target.
    /// 計算原始信心下限目標值。
    ///
    /// \[Q1\] max single-factor, \[R1-5\] ignore negative adjustments during loss streak.
    fn compute_confidence_floor(
        consec_losses: u32,
        weekly_pnl: f64,
        rd: &RegretInput,
    ) -> f64 {
        let mut pos: Vec<f64> = Vec::new();
        let mut neg: Vec<f64> = Vec::new();

        // Regret direction adjustment / 遺憾方向調整
        if rd.direction == "overtrading" {
            pos.push(0.05);
        } else if rd.direction == "undertrading" {
            neg.push(-0.03);
        }

        // Consecutive loss streak escalation / 連續虧損升級
        if consec_losses >= 3 {
            let factor = (consec_losses - 2).min(5) as f64;
            pos.push(0.02 * factor);
        }

        // Negative weekly PnL / 週負 PnL
        if weekly_pnl < 0.0 {
            pos.push(0.02);
        }

        let pos_net = if pos.is_empty() {
            0.0
        } else {
            pos.iter().cloned().fold(f64::NEG_INFINITY, f64::max)
        };

        // [R1-5]: ignore downward pressure during loss streak / 連虧時忽略向下壓力
        let neg_net = if consec_losses >= 3 || neg.is_empty() {
            0.0
        } else {
            neg.iter().cloned().fold(f64::INFINITY, f64::min)
        };

        clamp(
            BASE_CONFIDENCE_FLOOR + pos_net + neg_net,
            MIN_CONF_FLOOR,
            MAX_CONF_FLOOR,
        )
    }

    /// Compute raw qty ceiling target.
    /// 計算原始倉位上限目標值。
    ///
    /// \[Q1\] Single worst-case factor (not sum).
    fn compute_qty_ceiling(consec_losses: u32, weekly_pnl: f64) -> f64 {
        let mut adj: Vec<f64> = Vec::new();

        if consec_losses >= 3 {
            let factor = (consec_losses - 2).min(5) as f64;
            adj.push(-0.05 * factor);
        }
        if weekly_pnl < 0.0 {
            adj.push(-0.1);
        }

        let net = if adj.is_empty() {
            0.0
        } else {
            adj.iter().cloned().fold(f64::INFINITY, f64::min)
        };

        clamp(BASE_QTY_CEILING + net, MIN_QTY_CEIL, MAX_QTY_CEIL)
    }

    /// Compute raw stoploss multiplier target from dream data.
    /// 根據夢境數據計算原始止損倍率目標值。
    fn compute_stoploss_mult(dd: &DreamInput) -> f64 {
        if dd.confidence > 0.6 {
            let blend = (1.0 - dd.confidence * 0.3) * BASE_STOPLOSS_MULT
                + dd.confidence * 0.3 * dd.stoploss_suggestion;
            clamp(blend, MIN_SL_MULT, MAX_SL_MULT)
        } else {
            BASE_STOPLOSS_MULT
        }
    }

    /// Compute raw scan interval target.
    /// 計算原始掃描間隔目標值。
    ///
    /// \[R1-1\] Speed-up on negative PnL + undertrading, slow-down on overtrading.
    fn compute_scan_interval(weekly_pnl: f64, rd: &RegretInput) -> f64 {
        let mut interval = BASE_SCAN_INTERVAL;

        // Negative PnL → faster scanning / 負 PnL → 加速掃描
        if weekly_pnl < 0.0 {
            interval = interval.min(BASE_SCAN_INTERVAL * 0.5);
        }

        // Undertrading → faster scanning / 交易不足 → 加速掃描
        if rd.direction == "undertrading" {
            interval = interval.min(BASE_SCAN_INTERVAL * 0.7);
        }

        // [R1-1] Overtrading → slow down / 過度交易 → 減速
        if rd.direction == "overtrading" {
            interval = interval.max(BASE_SCAN_INTERVAL * 1.5);
        }

        clamp(interval, MIN_SCAN, MAX_SCAN)
    }
}

// ────────────────────────────────────────────────────────────────
// Tests / 測試
// ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper: create default inputs. / 輔助：建立預設輸入。
    fn defaults() -> (RegretInput, DreamInput) {
        (RegretInput::default(), DreamInput::default())
    }

    #[test]
    fn test_default_state() {
        // Default modulator should have base values.
        // 預設調製器應有基礎值。
        let m = CognitiveModulator::new();
        assert!((m.confidence_floor() - 0.6).abs() < 1e-10);
        assert!((m.qty_ceiling() - 1.0).abs() < 1e-10);
        assert!((m.stoploss_multiplier() - 1.0).abs() < 1e-10);
        assert_eq!(m.scan_interval_secs(), 1800);
        assert_eq!(m.update_count, 0);
    }

    #[test]
    fn test_update_with_no_pressure() {
        // Update with all-zero inputs should keep values at base (EMA of base → base).
        // 全零輸入的更新應保持基礎值。
        let mut m = CognitiveModulator::new();
        let (rd, dd) = defaults();
        let out = m.update(0, 0.0, &rd, &dd);
        assert!((out.confidence_floor - 0.6).abs() < 1e-10);
        assert!((out.qty_ceiling - 1.0).abs() < 1e-10);
        assert!((out.stoploss_multiplier - 1.0).abs() < 1e-10);
        assert_eq!(out.scan_interval_secs, 1800);
        assert_eq!(out.update_count, 1);
    }

    #[test]
    fn test_loss_streak_raises_confidence() {
        // 3 consecutive losses → confidence floor should increase.
        // 連續 3 次虧損 → 信心下限應上升。
        let mut m = CognitiveModulator::new();
        let (rd, dd) = defaults();
        let out = m.update(3, 0.0, &rd, &dd);
        assert!(out.confidence_floor > 0.6);
    }

    #[test]
    fn test_loss_streak_lowers_qty_ceiling() {
        // Loss streak → qty ceiling should decrease.
        // 連續虧損 → 倉位上限應下降。
        let mut m = CognitiveModulator::new();
        let (rd, dd) = defaults();
        let out = m.update(5, 0.0, &rd, &dd);
        assert!(out.qty_ceiling < 1.0);
    }

    #[test]
    fn test_negative_weekly_pnl() {
        // Negative weekly PnL → higher confidence floor, lower qty, faster scan.
        // 週負 PnL → 更高信心下限、更低倉位、更快掃描。
        let mut m = CognitiveModulator::new();
        let (rd, dd) = defaults();
        let out = m.update(0, -500.0, &rd, &dd);
        assert!(out.confidence_floor > 0.6);
        assert!(out.qty_ceiling < 1.0);
        assert!(out.scan_interval_secs < 1800);
    }

    #[test]
    fn test_r1_5_rule_ignore_downward_on_streak() {
        // [R1-5] With 3+ losses AND undertrading, the -0.03 undertrading
        // adjustment should be ignored. Confidence should go UP not down.
        // [R1-5] 連虧 3+ 且 undertrading 時，-0.03 調整應被忽略，信心應上升。
        let mut m = CognitiveModulator::new();
        let rd = RegretInput {
            direction: "undertrading".into(),
            ..Default::default()
        };
        let dd = DreamInput::default();
        let out = m.update(4, 0.0, &rd, &dd);
        // With 4 losses: pos factor = 0.02 * min(4-2,5) = 0.04
        // neg factor = 0 (R1-5 ignores), target = 0.64
        // EMA: 0.3*0.64 + 0.7*0.60 = 0.612
        assert!(out.confidence_floor > 0.6, "R1-5: confidence must rise on streak");
    }

    #[test]
    fn test_r1_5_undertrading_without_streak() {
        // Without loss streak, undertrading should lower confidence floor.
        // 無連虧時，undertrading 應降低信心下限。
        let mut m = CognitiveModulator::new();
        let rd = RegretInput {
            direction: "undertrading".into(),
            ..Default::default()
        };
        let dd = DreamInput::default();
        let out = m.update(0, 0.0, &rd, &dd);
        // target = 0.60 - 0.03 = 0.57, EMA: 0.3*0.57 + 0.7*0.60 = 0.591
        assert!(out.confidence_floor < 0.6, "undertrading should lower floor");
    }

    #[test]
    fn test_dream_blend_stoploss() {
        // High-confidence dream suggestion blends into stoploss multiplier.
        // 高信心夢境建議混合進止損倍率。
        let mut m = CognitiveModulator::new();
        let rd = RegretInput::default();
        let dd = DreamInput {
            stoploss_suggestion: 1.5,
            confidence: 0.8,
        };
        let out = m.update(0, 0.0, &rd, &dd);
        // blend = (1.0 - 0.8*0.3)*1.0 + 0.8*0.3*1.5 = 0.76 + 0.36 = 1.12
        // EMA: 0.3*1.12 + 0.7*1.0 = 1.036
        assert!(out.stoploss_multiplier > 1.0, "dream should raise stoploss");
        assert!((out.stoploss_multiplier - 1.036).abs() < 0.001);
    }

    #[test]
    fn test_dream_low_confidence_ignored() {
        // Dream with confidence <= 0.6 should not affect stoploss.
        // 信心度 <= 0.6 的夢境不應影響止損。
        let mut m = CognitiveModulator::new();
        let rd = RegretInput::default();
        let dd = DreamInput {
            stoploss_suggestion: 2.0,
            confidence: 0.5,
        };
        let out = m.update(0, 0.0, &rd, &dd);
        assert!((out.stoploss_multiplier - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_overtrading_slows_scan() {
        // Overtrading direction → scan interval increases.
        // 過度交易方向 → 掃描間隔增加。
        let mut m = CognitiveModulator::new();
        let rd = RegretInput {
            direction: "overtrading".into(),
            ..Default::default()
        };
        let dd = DreamInput::default();
        let out = m.update(0, 0.0, &rd, &dd);
        assert!(out.scan_interval_secs > 1800);
    }

    #[test]
    fn test_ema_convergence() {
        // After many updates with same input, values should converge to target.
        // 多次相同輸入更新後，值應收斂到目標。
        let mut m = CognitiveModulator::new();
        let rd = RegretInput::default();
        let dd = DreamInput::default();
        for _ in 0..50 {
            m.update(5, -100.0, &rd, &dd);
        }
        // Target confidence: 0.60 + max(0.02*min(3,5), 0.02) = 0.60 + 0.06 = 0.66
        assert!((m.confidence_floor() - 0.66).abs() < 0.01);
        // Target qty: 1.0 + min(-0.05*3, -0.1) = 1.0 - 0.15 = 0.85
        assert!((m.qty_ceiling() - 0.85).abs() < 0.01);
    }

    #[test]
    fn test_clamp_bounds_respected() {
        // Extreme loss streak should keep values within clamp bounds.
        // 極端連虧應將值保持在限幅範圍內。
        let mut m = CognitiveModulator::new();
        let rd = RegretInput::default();
        let dd = DreamInput::default();
        for _ in 0..100 {
            m.update(100, -10000.0, &rd, &dd);
        }
        assert!(m.confidence_floor() <= 0.85);
        assert!(m.confidence_floor() >= 0.45);
        assert!(m.qty_ceiling() >= 0.3);
        assert!(m.qty_ceiling() <= 1.0);
    }

    #[test]
    fn test_snapshot_matches_getters() {
        // Snapshot values should match individual getters.
        // 快照值應與個別存取器一致。
        let mut m = CognitiveModulator::new();
        let rd = RegretInput {
            direction: "overtrading".into(),
            ..Default::default()
        };
        let dd = DreamInput {
            stoploss_suggestion: 1.8,
            confidence: 0.9,
        };
        m.update(4, -200.0, &rd, &dd);
        let snap = m.snapshot();
        assert!((snap.confidence_floor - m.confidence_floor()).abs() < 1e-12);
        assert!((snap.qty_ceiling - m.qty_ceiling()).abs() < 1e-12);
        assert!((snap.stoploss_multiplier - m.stoploss_multiplier()).abs() < 1e-12);
        assert_eq!(snap.scan_interval_secs, m.scan_interval_secs());
        assert_eq!(snap.update_count, m.update_count);
    }
}
