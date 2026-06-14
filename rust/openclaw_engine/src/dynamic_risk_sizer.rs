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
///
/// 量綱說明（DYNAMIC-RISK-SIG-1, 2026-06-14）：`compute_sharpe` 計算的是
/// 逐筆 (per-trade) Sharpe = mean/std of realized-PnL ring，**無年化、無 per-period
/// 正規化**。故 `sharpe_high` / `sharpe_low` 閾值的語義是「per-trade Sharpe」而非
/// 年化 Sharpe；不要拿年化直覺（>1 算好）解讀這些閾值。
/// 純遙測欄位 `last_sharpe_annualized`（不參與任何決策）僅供人類在 status 看年化視圖。
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
    /// DYNAMIC-RISK-SIG-1 (2026-06-14): 顯著性 gate 總開關。
    /// 為何 fail-closed default=true：無 gate 時 maybe_update 只檢查筆數 >= min_trades
    /// 就拿 point-estimate SR_trade 比閾值；n=50、SR≈0 時 SE(SR)≈0.14，measured SR=0.14
    /// 與 0 無法區分卻仍可觸發加倉路徑（樣本不足即放大倉位）。開啟後 UP 路徑改用下置信界
    /// LCB，樣本不足 → SE 大 → LCB 低 → 不加倉。設 false 僅回退舊（有缺陷）行為，不引入新風險。
    pub sig_gate_enabled: bool,
    /// UP 置信界 z 值（單尾）；default 1.645 = 單尾 95%。越大越保守（LCB 越低、UP 越難 fire）。
    pub sig_z: f64,
    /// UP 路徑額外硬 floor 筆數；與既有 `min_trades` 取 max（只嚴不鬆）。
    /// 樣本數 < max(min_trades, sig_min_trades) 時 UP 一律禁止（DOWN 仍允許）。
    pub sig_min_trades: usize,
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
            // 保守 default：gate 開、單尾 95%、UP floor=50（與 min_trades default 對齊）。
            sig_gate_enabled: true,
            sig_z: 1.645,
            sig_min_trades: 50,
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
        // DYNAMIC-RISK-SIG-1 (2026-06-14): 顯著性 gate 參數校驗。
        // sig_z 須 finite 且 >= 0（負 z 會把 LCB 抬到 point-estimate 之上 = 放鬆，禁止）。
        if !self.sig_z.is_finite() || self.sig_z < 0.0 {
            return Err(format!(
                "dynamic_sizing.sig_z {} must be finite and >= 0",
                self.sig_z
            ));
        }
        // sig_min_trades >= min_trades：UP floor 不可低於既有筆數門檻，否則等於放鬆。
        if self.sig_min_trades < self.min_trades {
            return Err(format!(
                "dynamic_sizing.sig_min_trades {} must be >= min_trades {} (UP floor cannot relax)",
                self.sig_min_trades, self.min_trades
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
    /// 純遙測：last_sharpe 的年化視圖（× sqrt(trades_in_window)），不參與任何決策。
    /// 僅供人類在 status 用年化直覺對照 per-trade 閾值的量綱落差。
    pub last_sharpe_annualized: Option<f64>,
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
        // DYNAMIC-RISK-SIG-1 (2026-06-14)：UP（加倉）路徑顯著性 gate。
        // 只有「即使保守地把 SR 拉到下置信界 LCB 仍 >= sharpe_high」才允許加倉，
        // 且筆數須過 UP 硬 floor max(min_trades, sig_min_trades)。樣本不足 → SE 大 →
        // LCB 低 → up_allowed=false → 退回 unchanged。DOWN 路徑刻意不加 gate：
        // 降倉永遠 survival-safe，noise 觸發降倉是好事（survival-first）。
        let up_allowed = if self.config.sig_gate_enabled {
            let up_floor = self.config.min_trades.max(self.config.sig_min_trades);
            if self.pnl_ring.len() < up_floor {
                false
            } else {
                // SE(SR) ≈ sqrt((1 + 0.5·SR²)/(n−1))（Lo 2002 IID 近似；crypto 厚尾下
                // 真 SE 偏大故用 (n−1) 較保守）。LCB = SR − z·SE。
                let n = self.pnl_ring.len() as f64;
                let se = ((1.0 + 0.5 * sharpe * sharpe) / (n - 1.0)).sqrt();
                let lcb = sharpe - self.config.sig_z * se;
                lcb >= self.config.sharpe_high
            }
        } else {
            // gate 關閉 → 回退舊行為（point-estimate 直接比閾值）。
            sharpe >= self.config.sharpe_high
        };
        let (next, direction) = if sharpe >= self.config.sharpe_high && up_allowed {
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
            // 純遙測年化視圖：per-trade SR × sqrt(window 筆數)。僅供人類量綱對照，
            // 不參與決策（決策一律用 per-trade last_sharpe 比 per-trade 閾值）。
            last_sharpe_annualized: self
                .last_sharpe
                .map(|sr| sr * (self.pnl_ring.len() as f64).sqrt()),
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
            // 既有機制測試（step/clamp/throttle）驗的是步進與夾限，非顯著性 gate。
            // 關閉 gate 以保留小樣本 UP 行為；gate 行為由下方 DYNAMIC-RISK-SIG-1 專測覆蓋。
            sig_gate_enabled: false,
            sig_z: 1.645,
            sig_min_trades: 4,
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

    // ----- DYNAMIC-RISK-SIG-1 (2026-06-14): UP-path significance gate -----

    /// 灌入 33 勝 / 17 負（±1）的 50 筆樣本：point-estimate SR≈0.334，
    /// LCB(z=1.645,n=50)≈0.093。用於驗證 gate 在「point 過閾、LCB 未過閾」時擋下 UP。
    fn fill_marginal_sample(s: &mut DynamicRiskSizer) {
        for _ in 0..33 {
            s.record_closed_trade(1.0);
        }
        for _ in 0..17 {
            s.record_closed_trade(-1.0);
        }
    }

    fn cfg_gated(sharpe_high: f64) -> DynamicRiskSizerConfig {
        DynamicRiskSizerConfig {
            enabled: true,
            min_trades: 50,
            step_pct: 0.005,
            min_pct: 0.01,
            max_pct: 0.05,
            sharpe_high,
            sharpe_low: -10.0, // 把 DOWN 推到不可達，隔離 UP 路徑
            update_interval_ms: 0,
            window_size: 200,
            sig_gate_enabled: true,
            sig_z: 1.645,
            sig_min_trades: 50,
        }
    }

    /// 核心 mutation-bite：同一邊際樣本，gate OFF 會加倉（舊行為），gate ON 不加倉。
    /// 證明 gate 真改變行為（樣本不足以顯著 → 不放大）。
    #[test]
    fn sig_gate_blocks_marginal_up_but_off_fires() {
        // gate OFF（舊行為）：point SR 0.334 >= 0.30 → UP fire。
        let mut cfg_off = cfg_gated(0.30);
        cfg_off.sig_gate_enabled = false;
        let mut s_off = DynamicRiskSizer::new(0.03, cfg_off);
        fill_marginal_sample(&mut s_off);
        let r_off = s_off
            .maybe_update(10_000)
            .expect("gate OFF must reproduce old behavior (UP fires on point-estimate)");
        assert!((r_off - 0.035).abs() < 1e-9, "UP step to 0.035, got {r_off}");
        assert_eq!(s_off.status().last_direction, SizerUpdateDirection::Up);

        // gate ON：LCB 0.093 < 0.30 → UP 被擋，退回 unchanged。
        let mut s_on = DynamicRiskSizer::new(0.03, cfg_gated(0.30));
        fill_marginal_sample(&mut s_on);
        assert_eq!(
            s_on.maybe_update(10_000),
            None,
            "gate ON must block UP when LCB < sharpe_high (insufficient significance)"
        );
        assert!((s_on.current_pct() - 0.03).abs() < f64::EPSILON);
        assert_eq!(
            s_on.status().last_direction,
            SizerUpdateDirection::Unchanged
        );
    }

    /// gate ON 但證據夠強（LCB >= sharpe_high）時仍允許加倉。
    /// 同樣本，sharpe_high 降到 0.05：point 0.334 與 LCB 0.093 皆 >= 0.05 → UP fire。
    #[test]
    fn sig_gate_allows_up_when_lcb_clears_threshold() {
        let mut s = DynamicRiskSizer::new(0.03, cfg_gated(0.05));
        fill_marginal_sample(&mut s);
        let next = s
            .maybe_update(10_000)
            .expect("gate ON must allow UP when LCB >= sharpe_high");
        assert!((next - 0.035).abs() < 1e-9, "UP step to 0.035, got {next}");
        assert_eq!(s.status().last_direction, SizerUpdateDirection::Up);
    }

    /// UP 硬 floor：樣本數 < max(min_trades, sig_min_trades) 時 UP 一律禁止。
    /// 用 min_trades=10、sig_min_trades=50 的配置，灌 20 筆（過 min_trades 但未過 floor）。
    #[test]
    fn sig_gate_up_floor_blocks_below_sig_min_trades() {
        let mut cfg = cfg_gated(0.05);
        cfg.min_trades = 10;
        cfg.sig_min_trades = 50;
        let mut s = DynamicRiskSizer::new(0.03, cfg);
        for _ in 0..14 {
            s.record_closed_trade(1.0);
        }
        for _ in 0..6 {
            s.record_closed_trade(-1.0);
        }
        // 20 筆 >= min_trades(10) 故進 maybe_update，但 < sig_min_trades(50) → UP floor 擋。
        assert_eq!(
            s.maybe_update(10_000),
            None,
            "UP must be blocked below max(min_trades, sig_min_trades)"
        );
    }

    /// DOWN 路徑刻意不受 gate 影響（survival-safe）：邊際負樣本仍可降倉。
    #[test]
    fn sig_gate_does_not_block_down() {
        let mut cfg = cfg_gated(10.0); // UP 不可達
        cfg.sharpe_low = -0.30; // DOWN 在 SR≈-0.334 時觸發
        let mut s = DynamicRiskSizer::new(0.03, cfg);
        for _ in 0..17 {
            s.record_closed_trade(1.0);
        }
        for _ in 0..33 {
            s.record_closed_trade(-1.0);
        }
        // SR≈-0.334 <= sharpe_low(-0.30) → DOWN fire，不被任何顯著性 gate 擋。
        let next = s
            .maybe_update(10_000)
            .expect("DOWN must remain ungated (降倉永遠 survival-safe)");
        assert!((next - 0.025).abs() < 1e-9, "DOWN step to 0.025, got {next}");
        assert_eq!(s.status().last_direction, SizerUpdateDirection::Down);
    }

    #[test]
    fn validate_rejects_negative_sig_z() {
        let mut cfg = cfg_tight();
        cfg.sig_z = -0.1;
        let err = cfg.validate().expect_err("negative sig_z must reject");
        assert!(err.contains("sig_z"), "unexpected error message: {err}");
    }

    #[test]
    fn validate_rejects_sig_min_trades_below_min_trades() {
        let mut cfg = cfg_tight(); // min_trades = 4
        cfg.sig_min_trades = 3;
        let err = cfg
            .validate()
            .expect_err("sig_min_trades < min_trades must reject");
        assert!(
            err.contains("sig_min_trades"),
            "unexpected error message: {err}"
        );
    }

    #[test]
    fn validate_accepts_default_sig_keys() {
        // Default config (gate on, z=1.645, sig_min_trades=50, min_trades=50) validates.
        DynamicRiskSizerConfig::default()
            .validate()
            .expect("default sig keys must validate");
    }

    /// 純遙測年化欄位不為 None 且方向正確（與 per-trade SR 同號、放大）。
    #[test]
    fn status_exposes_annualized_telemetry_without_affecting_decision() {
        let mut s = DynamicRiskSizer::new(0.03, cfg_gated(0.30));
        fill_marginal_sample(&mut s);
        // gate ON 擋 UP（決策層用 per-trade），但 last_sharpe 仍被記錄供遙測。
        let _ = s.maybe_update(10_000);
        let st = s.status();
        let sr = st.last_sharpe.expect("last_sharpe recorded");
        let ann = st
            .last_sharpe_annualized
            .expect("annualized telemetry present");
        // 年化 = per-trade SR × sqrt(n)，n=50 → 放大 ~7.07×，同號。
        assert!(ann > sr, "annualized view magnifies per-trade SR");
        assert!((ann - sr * (50f64).sqrt()).abs() < 1e-9);
    }
}
