//! Dynamic Risk Sizer — per-engine Sharpe-aware per-trade risk adjustment.
//! 動態風險調整器 — 按引擎依 Sharpe 調整單筆風險。
//!
//! MODULE_NOTE (EN): Small in-memory sizer owned by each `TickPipeline`.
//!   Consumes realized PnL from every close and periodically re-computes a
//!   simplified Sharpe (mean / std of last N closed trades, no annualization).
//!   Steps `per_trade_risk_pct` up when Sharpe >= high_threshold, down when
//!   Sharpe <= low_threshold, clamped to `[min_pct, max_pct]`. Output is a
//!   single scalar consumed by `IntentProcessor::set_p1_risk_pct`.
//!   Disabled-by-default; enabling makes the sizer publish updates at most
//!   once per `update_interval_ms`. No DB dependency (memory-only MVP).
//! MODULE_NOTE (中): 由各 `TickPipeline` 私有的輕量 in-memory 調整器。
//!   每次平倉後吞入已實現 PnL，定期重算簡化 Sharpe（最近 N 筆均值/標準差，
//!   不做年化）。Sharpe >= high_threshold 加步、<= low_threshold 減步，
//!   夾限 `[min_pct, max_pct]`。輸出單一標量由 `IntentProcessor::set_p1_risk_pct` 消費。
//!   預設 disabled；啟用後至多每 `update_interval_ms` 發布一次更新。無 DB 依賴（MVP in-memory）。

use std::collections::VecDeque;

/// Tunable parameters for the sizer. Mirrors `[risk.dynamic_sizing]` in the TOML.
/// Defaults are conservative: ±0.5% step, 1%..5% clamp, Sharpe band [0.0, 1.0],
/// 5-minute update interval, 50-trade minimum before the first up/down.
/// 可調參數，對應 TOML `[risk.dynamic_sizing]`。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(default)]
pub struct DynamicRiskSizerConfig {
    pub enabled: bool,
    pub min_trades: usize,
    pub step_pct: f64,
    pub min_pct: f64,
    pub max_pct: f64,
    pub sharpe_high: f64,
    pub sharpe_low: f64,
    pub update_interval_ms: u64,
    pub window_size: usize,
}

impl Default for DynamicRiskSizerConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            min_trades: 50,
            step_pct: 0.005,
            min_pct: 0.01,
            max_pct: 0.05,
            sharpe_high: 1.0,
            sharpe_low: 0.0,
            update_interval_ms: 300_000,
            window_size: 200,
        }
    }
}

impl DynamicRiskSizerConfig {
    /// Validate invariants. Called from `RiskConfig::validate()` via `dynamic_sizing.validate()`.
    /// 校驗不變量；由 `RiskConfig::validate()` 呼叫。
    pub fn validate(&self) -> Result<(), String> {
        if !(self.min_pct.is_finite() && self.max_pct.is_finite()) {
            return Err("dynamic_sizing: min_pct/max_pct must be finite".into());
        }
        // Align with IntentProcessor::set_p1_risk_pct clamp [0.001, 0.20].
        // Values above 0.20 would be silently reduced at publish time and
        // leave GUI / sizer state inconsistent with real order sizing.
        // DYNAMIC-RISK-1 BUG-2: tighten ceiling from 1.0 to 0.20.
        // 與 IntentProcessor::set_p1_risk_pct 的 [0.001, 0.20] 夾限對齊。
        // 超過 0.20 的值會在 publish 時被靜默截斷，造成 GUI/sizer 與真實下單不一致。
        if self.min_pct <= 0.0 || self.min_pct > 0.20 {
            return Err(format!(
                "dynamic_sizing.min_pct {} out of (0, 0.20] (IntentProcessor hard-clamps at 20%)",
                self.min_pct
            ));
        }
        if self.max_pct <= 0.0 || self.max_pct > 0.20 {
            return Err(format!(
                "dynamic_sizing.max_pct {} out of (0, 0.20] (IntentProcessor hard-clamps at 20%)",
                self.max_pct
            ));
        }
        if self.min_pct >= self.max_pct {
            return Err(format!(
                "dynamic_sizing.min_pct {} must be < max_pct {}",
                self.min_pct, self.max_pct
            ));
        }
        if self.step_pct <= 0.0 || self.step_pct > (self.max_pct - self.min_pct) {
            return Err(format!(
                "dynamic_sizing.step_pct {} must be in (0, max_pct - min_pct]",
                self.step_pct
            ));
        }
        if self.sharpe_low > self.sharpe_high {
            return Err(format!(
                "dynamic_sizing.sharpe_low {} must be <= sharpe_high {}",
                self.sharpe_low, self.sharpe_high
            ));
        }
        if self.min_trades < 2 {
            return Err("dynamic_sizing.min_trades must be >= 2".into());
        }
        if self.window_size < self.min_trades {
            return Err(format!(
                "dynamic_sizing.window_size {} must be >= min_trades {}",
                self.window_size, self.min_trades
            ));
        }
        Ok(())
    }
}

/// Direction of the most recent update, for telemetry.
/// 最近一次更新的方向（遙測用）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum SizerUpdateDirection {
    Unchanged,
    Up,
    Down,
    Clamped,
}

/// Snapshot of sizer state for IPC `GetDynamicRiskStatus`.
/// IPC 狀態快照。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SizerStatus {
    pub enabled: bool,
    pub base_pct: f64,
    pub current_pct: f64,
    pub min_pct: f64,
    pub max_pct: f64,
    pub step_pct: f64,
    pub sharpe_high: f64,
    pub sharpe_low: f64,
    pub trades_in_window: usize,
    pub min_trades: usize,
    pub last_sharpe: Option<f64>,
    pub last_update_ms: Option<u64>,
    pub last_direction: SizerUpdateDirection,
    pub update_interval_ms: u64,
}

/// Per-engine Sharpe-aware sizer. Not `Send`/`Sync` sensitive — lives inside
/// the single-owner `TickPipeline`.
/// 單 pipeline 專屬的 Sharpe 調整器。
#[derive(Debug, Clone)]
pub struct DynamicRiskSizer {
    config: DynamicRiskSizerConfig,
    base_pct: f64,
    current_pct: f64,
    pnl_ring: VecDeque<f64>,
    last_update_ms: Option<u64>,
    last_sharpe: Option<f64>,
    last_direction: SizerUpdateDirection,
}

impl DynamicRiskSizer {
    /// Build a sizer anchored on `base_pct` (typically the configured
    /// `per_trade_risk_pct`). `current_pct` starts equal to `base_pct`.
    /// 以 `base_pct` 為錨（通常等於 `per_trade_risk_pct`），current = base。
    pub fn new(base_pct: f64, config: DynamicRiskSizerConfig) -> Self {
        let clamped = base_pct.clamp(config.min_pct, config.max_pct);
        Self {
            config,
            base_pct: clamped,
            current_pct: clamped,
            pnl_ring: VecDeque::new(),
            last_update_ms: None,
            last_sharpe: None,
            last_direction: SizerUpdateDirection::Unchanged,
        }
    }

    /// Re-anchor the base when the upstream TOML `per_trade_risk_pct` changes.
    /// Resets `current_pct` to the new base so the next `maybe_update` cycle
    /// starts clean — avoids stacking old drift onto a new operator intent.
    /// 當上游 `per_trade_risk_pct` 改動時重錨，current 回到 base。
    pub fn rebase(&mut self, base_pct: f64) {
        let clamped = base_pct.clamp(self.config.min_pct, self.config.max_pct);
        self.base_pct = clamped;
        self.current_pct = clamped;
        self.last_direction = SizerUpdateDirection::Unchanged;
    }

    /// Push realized PnL from a close. Ring trims to `window_size`.
    /// 吞入平倉實現 PnL；環形緩衝裁切到 `window_size`。
    pub fn record_closed_trade(&mut self, pnl: f64) {
        if !pnl.is_finite() {
            return;
        }
        self.pnl_ring.push_back(pnl);
        while self.pnl_ring.len() > self.config.window_size {
            self.pnl_ring.pop_front();
        }
    }

    /// Set enable flag at runtime (IPC hook). Does not touch `current_pct` —
    /// callers applying the sizer's output should check `is_enabled()`.
    /// 運行時設置啟用旗標（IPC 入口）；不動 current_pct，呼叫端以 `is_enabled()` 判斷。
    pub fn set_enabled(&mut self, enabled: bool) {
        self.config.enabled = enabled;
    }

    pub fn is_enabled(&self) -> bool {
        self.config.enabled
    }

    pub fn current_pct(&self) -> f64 {
        self.current_pct
    }

    pub fn base_pct(&self) -> f64 {
        self.base_pct
    }

    /// Called every tick. Returns `Some(new_pct)` iff a publishable change
    /// happened; `None` otherwise (insufficient trades, throttled, disabled,
    /// or no actionable Sharpe band crossing).
    /// 每 tick 呼叫；有可發布變動時回 `Some(new_pct)`，否則 `None`。
    pub fn maybe_update(&mut self, now_ms: u64) -> Option<f64> {
        if !self.config.enabled {
            return None;
        }
        if let Some(last) = self.last_update_ms {
            if now_ms.saturating_sub(last) < self.config.update_interval_ms {
                return None;
            }
        }
        if self.pnl_ring.len() < self.config.min_trades {
            return None;
        }

        let sharpe = compute_sharpe(&self.pnl_ring)?;
        self.last_sharpe = Some(sharpe);
        self.last_update_ms = Some(now_ms);

        let previous = self.current_pct;
        let (next, direction) = if sharpe >= self.config.sharpe_high {
            let candidate = previous + self.config.step_pct;
            if candidate >= self.config.max_pct {
                (self.config.max_pct, SizerUpdateDirection::Clamped)
            } else {
                (candidate, SizerUpdateDirection::Up)
            }
        } else if sharpe <= self.config.sharpe_low {
            let candidate = previous - self.config.step_pct;
            if candidate <= self.config.min_pct {
                (self.config.min_pct, SizerUpdateDirection::Clamped)
            } else {
                (candidate, SizerUpdateDirection::Down)
            }
        } else {
            self.last_direction = SizerUpdateDirection::Unchanged;
            return None;
        };

        if (next - previous).abs() < f64::EPSILON {
            self.last_direction = SizerUpdateDirection::Unchanged;
            return None;
        }

        self.current_pct = next;
        self.last_direction = direction;
        Some(next)
    }

    pub fn status(&self) -> SizerStatus {
        SizerStatus {
            enabled: self.config.enabled,
            base_pct: self.base_pct,
            current_pct: self.current_pct,
            min_pct: self.config.min_pct,
            max_pct: self.config.max_pct,
            step_pct: self.config.step_pct,
            sharpe_high: self.config.sharpe_high,
            sharpe_low: self.config.sharpe_low,
            trades_in_window: self.pnl_ring.len(),
            min_trades: self.config.min_trades,
            last_sharpe: self.last_sharpe,
            last_update_ms: self.last_update_ms,
            last_direction: self.last_direction,
            update_interval_ms: self.config.update_interval_ms,
        }
    }
}

/// Simplified Sharpe: mean / stddev over the ring, no annualization.
/// Returns `None` when stddev is zero (constant PnL — undefined Sharpe) or ring
/// is too small to form a sample variance (len < 2).
/// 簡化 Sharpe：mean / stddev；stddev=0 或長度<2 回 None。
fn compute_sharpe(pnls: &VecDeque<f64>) -> Option<f64> {
    let n = pnls.len();
    if n < 2 {
        return None;
    }
    let sum: f64 = pnls.iter().sum();
    let mean = sum / n as f64;
    let var: f64 = pnls
        .iter()
        .map(|p| {
            let d = *p - mean;
            d * d
        })
        .sum::<f64>()
        / (n as f64 - 1.0);
    let std = var.sqrt();
    if std <= f64::EPSILON {
        return None;
    }
    Some(mean / std)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cfg_tight() -> DynamicRiskSizerConfig {
        DynamicRiskSizerConfig {
            enabled: true,
            min_trades: 4,
            step_pct: 0.005,
            min_pct: 0.01,
            max_pct: 0.05,
            sharpe_high: 0.5,
            sharpe_low: -0.5,
            update_interval_ms: 1_000,
            window_size: 50,
        }
    }

    #[test]
    fn disabled_sizer_never_updates() {
        let mut cfg = cfg_tight();
        cfg.enabled = false;
        let mut s = DynamicRiskSizer::new(0.03, cfg);
        for _ in 0..10 {
            s.record_closed_trade(1.0);
        }
        assert_eq!(s.maybe_update(10_000), None);
        assert!((s.current_pct() - 0.03).abs() < f64::EPSILON);
    }

    #[test]
    fn insufficient_trades_no_update() {
        let mut s = DynamicRiskSizer::new(0.03, cfg_tight());
        for _ in 0..3 {
            s.record_closed_trade(1.0);
        }
        assert_eq!(s.maybe_update(10_000), None);
    }

    #[test]
    fn high_sharpe_steps_up() {
        let mut s = DynamicRiskSizer::new(0.03, cfg_tight());
        for _ in 0..10 {
            s.record_closed_trade(1.0);
            s.record_closed_trade(1.1);
            s.record_closed_trade(0.9);
        }
        let next = s.maybe_update(10_000).expect("should publish update");
        assert!(next > 0.03 - f64::EPSILON);
        assert!((next - 0.035).abs() < 1e-9);
        assert_eq!(s.status().last_direction, SizerUpdateDirection::Up);
    }

    #[test]
    fn low_sharpe_steps_down() {
        let mut s = DynamicRiskSizer::new(0.03, cfg_tight());
        for _ in 0..10 {
            s.record_closed_trade(-1.0);
            s.record_closed_trade(-1.1);
            s.record_closed_trade(-0.9);
        }
        let next = s.maybe_update(10_000).expect("should publish update");
        assert!((next - 0.025).abs() < 1e-9);
        assert_eq!(s.status().last_direction, SizerUpdateDirection::Down);
    }

    #[test]
    fn update_interval_throttles() {
        let mut s = DynamicRiskSizer::new(0.03, cfg_tight());
        for _ in 0..10 {
            s.record_closed_trade(1.0);
            s.record_closed_trade(1.2);
        }
        assert!(s.maybe_update(10_000).is_some());
        // Too soon — throttled.
        assert!(s.maybe_update(10_500).is_none());
        // After interval — allowed again.
        for _ in 0..10 {
            s.record_closed_trade(1.0);
            s.record_closed_trade(1.2);
        }
        assert!(s.maybe_update(12_000).is_some());
    }

    #[test]
    fn clamps_at_max() {
        let mut cfg = cfg_tight();
        cfg.min_trades = 2;
        cfg.update_interval_ms = 0;
        let mut s = DynamicRiskSizer::new(0.048, cfg);
        for _ in 0..5 {
            s.record_closed_trade(1.0);
            s.record_closed_trade(1.1);
        }
        let next = s.maybe_update(10_000).expect("update");
        assert!((next - 0.05).abs() < 1e-9);
        assert_eq!(s.status().last_direction, SizerUpdateDirection::Clamped);
        s.record_closed_trade(1.0);
        s.record_closed_trade(1.1);
        // Already at max — no further change publishable even under high Sharpe.
        assert!(s.maybe_update(20_000).is_none());
    }

    #[test]
    fn clamps_at_min() {
        let mut cfg = cfg_tight();
        cfg.min_trades = 2;
        cfg.update_interval_ms = 0;
        let mut s = DynamicRiskSizer::new(0.012, cfg);
        for _ in 0..5 {
            s.record_closed_trade(-1.0);
            s.record_closed_trade(-1.2);
        }
        let next = s.maybe_update(10_000).expect("update");
        assert!((next - 0.01).abs() < 1e-9);
        assert_eq!(s.status().last_direction, SizerUpdateDirection::Clamped);
    }

    #[test]
    fn neutral_sharpe_band_no_update() {
        let mut s = DynamicRiskSizer::new(0.03, cfg_tight());
        // Alternating +1 / -1 → mean≈0, stddev≈1 → sharpe≈0 → inside band.
        for _ in 0..20 {
            s.record_closed_trade(1.0);
            s.record_closed_trade(-1.0);
        }
        assert_eq!(s.maybe_update(10_000), None);
    }

    #[test]
    fn window_trims_old_trades() {
        let mut cfg = cfg_tight();
        cfg.window_size = 5;
        let mut s = DynamicRiskSizer::new(0.03, cfg);
        for i in 0..20 {
            s.record_closed_trade(i as f64);
        }
        assert_eq!(s.status().trades_in_window, 5);
    }

    #[test]
    fn rebase_resets_current() {
        let mut s = DynamicRiskSizer::new(0.03, cfg_tight());
        for _ in 0..10 {
            s.record_closed_trade(1.0);
            s.record_closed_trade(1.2);
        }
        let _ = s.maybe_update(10_000);
        assert!((s.current_pct() - 0.035).abs() < 1e-9);
        s.rebase(0.02);
        assert!((s.current_pct() - 0.02).abs() < f64::EPSILON);
        assert!((s.base_pct() - 0.02).abs() < f64::EPSILON);
    }

    #[test]
    fn rebase_clamps_to_range() {
        let mut s = DynamicRiskSizer::new(0.03, cfg_tight());
        s.rebase(0.99);
        assert!((s.current_pct() - 0.05).abs() < f64::EPSILON);
        s.rebase(0.0);
        assert!((s.current_pct() - 0.01).abs() < f64::EPSILON);
    }

    #[test]
    fn record_rejects_non_finite() {
        let mut s = DynamicRiskSizer::new(0.03, cfg_tight());
        s.record_closed_trade(f64::NAN);
        s.record_closed_trade(f64::INFINITY);
        s.record_closed_trade(f64::NEG_INFINITY);
        assert_eq!(s.status().trades_in_window, 0);
    }

    /// BUG-2 regression: max_pct must be ≤ 0.20 to match
    /// `IntentProcessor::set_p1_risk_pct` hard clamp. Values beyond 0.20 would
    /// be silently reduced at publish time.
    /// BUG-2 回歸：max_pct 必須 ≤ 0.20，與 IntentProcessor 硬夾限對齊。
    #[test]
    fn validate_rejects_max_pct_above_20pct() {
        let mut cfg = cfg_tight();
        cfg.max_pct = 0.25;
        let err = cfg.validate().expect_err("max_pct 0.25 must be rejected");
        assert!(
            err.contains("out of (0, 0.20]"),
            "unexpected error message: {err}"
        );
    }

    #[test]
    fn validate_accepts_max_pct_at_20pct_ceiling() {
        let mut cfg = cfg_tight();
        cfg.max_pct = 0.20;
        cfg.min_pct = 0.01;
        cfg.step_pct = 0.005;
        cfg.validate().expect("max_pct 0.20 must be accepted");
    }

    #[test]
    fn validate_rejects_min_pct_above_20pct() {
        let mut cfg = cfg_tight();
        cfg.min_pct = 0.25;
        cfg.max_pct = 0.30;
        let err = cfg.validate().expect_err("min_pct 0.25 must be rejected");
        assert!(
            err.contains("out of (0, 0.20]"),
            "unexpected error message: {err}"
        );
    }
}
