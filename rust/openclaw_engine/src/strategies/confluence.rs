//! Confluence scoring + time-based signal persistence — shared across strategies (A0-b).
//! 匯流評分 + 基於時間的信號持續性 — 跨策略共享模組（A0-b）。
//!
//! MODULE_NOTE (EN): Provides weighted confluence scoring (4 conditions, 65-point scale),
//!   smooth position sizing interpolation, time-based persistence filtering, and cold-start
//!   indicator readiness checks. Used by ma_crossover, bb_reversion, bb_breakout strategies.
//!   Grid strategy uses trend cooldown (A3) instead of confluence scoring.
//! MODULE_NOTE (中): 提供加權匯流評分（4 條件，65 分量表）、平滑倉位大小插值、
//!   基於時間的持續性過濾、及冷啟動指標就緒檢查。供 ma_crossover、bb_reversion、
//!   bb_breakout 策略使用。Grid 策略使用趨勢冷卻（A3）而非匯流評分。

use std::collections::HashMap;

use serde::{Deserialize, Serialize};

// ── ConfluenceConfig ────────────────────────────────────────────────────────

/// Configuration for confluence scoring — per-strategy weight allocation + thresholds.
/// 匯流評分配置 — 每策略權重分配 + 閾值。
///
/// Weight sum MUST equal 65 (validated at construction). Thresholds define the
/// score-to-qty-pct mapping bands (smooth interpolation, no cliffs).
/// 權重總和必須等於 65（構建時驗證）。閾值定義分數→倉位百分比映射帶（平滑插值，無斷崖）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConfluenceConfig {
    /// ADX component weight. ADX 分量權重。
    pub weight_adx: f64,
    /// Regime/Hurst component weight. 市場體制/Hurst 分量權重。
    pub weight_regime: f64,
    /// Volume ratio component weight. 成交量比率分量權重。
    pub weight_volume: f64,
    /// Momentum (RSI) component weight. 動量（RSI）分量權重。
    pub weight_momentum: f64,
    /// ADX floor: below this value, ADX score = 0 (insufficient data).
    /// ADX 地板：低於此值，ADX 分數 = 0（數據不足）。
    pub adx_floor: f64,
    /// Invert ADX for mean-reversion strategies (high ADX = low score).
    /// 均值回歸策略反轉 ADX（高 ADX = 低分數）。
    pub invert_adx: bool,
    /// Score below which qty = 0% (hard floor).
    /// 低於此分數時 qty = 0%（硬地板）。
    pub threshold_no_trade: f64,
    /// Score below which qty ramps from 10% to 50%.
    /// 低於此分數時 qty 從 10% 升至 50%。
    pub threshold_light: f64,
    /// Score at/above which qty = 100%.
    /// 達到或超過此分數時 qty = 100%。
    pub threshold_full: f64,
    /// Whether confluence acts as position gate (true) or qty modifier only (false).
    /// 匯流是否作為倉位門控（true）或僅作為 qty 調整器（false）。
    ///
    /// BB Breakout uses `false`: triple gate is primary filter, confluence only adjusts qty.
    /// BB Breakout 使用 `false`：三重門控是主過濾器，匯流僅調整 qty。
    pub confluence_as_gate: bool,
}

impl Default for ConfluenceConfig {
    /// Default: trend-following weights (MA crossover profile).
    /// 默認：趨勢跟蹤權重（MA crossover 配置）。
    /// EDGE-P1-3: thresholds raised 35/45/55 → 45/52/58 to filter more noise.
    fn default() -> Self {
        Self {
            weight_adx: 25.0,
            weight_regime: 20.0,
            weight_volume: 12.0,
            weight_momentum: 8.0,
            adx_floor: 8.0,
            invert_adx: false,
            threshold_no_trade: 45.0,
            threshold_light: 52.0,
            threshold_full: 58.0,
            confluence_as_gate: true,
        }
    }
}

impl ConfluenceConfig {
    /// Validate weight sum = 65. Returns Err if violated.
    /// 驗證權重總和 = 65。違反時返回 Err。
    pub fn validate(&self) -> Result<(), String> {
        let sum = self.weight_adx + self.weight_regime + self.weight_volume + self.weight_momentum;
        if (sum - 65.0).abs() > 0.01 {
            return Err(format!(
                "confluence weight sum must be 65, got {sum:.2} \
                 (adx={}, regime={}, volume={}, momentum={})",
                self.weight_adx, self.weight_regime, self.weight_volume, self.weight_momentum
            ));
        }
        Ok(())
    }

    /// Create a reversion-profile config (BB Reversion defaults).
    /// 建立均值回歸配置（BB Reversion 默認值）。
    pub fn reversion() -> Self {
        Self {
            weight_adx: 15.0,
            weight_regime: 30.0,
            weight_volume: 10.0,
            weight_momentum: 10.0,
            invert_adx: true,
            ..Self::default()
        }
    }

    /// Create a breakout-profile config (BB Breakout: qty modifier only).
    /// 建立突破配置（BB Breakout：僅 qty 調整器）。
    pub fn breakout() -> Self {
        Self {
            confluence_as_gate: false,
            ..Self::default()
        }
    }
}

// ── PersistenceTracker ──────────────────────────────────────────────────────

/// Time-based signal persistence tracker.
/// 基於時間的信號持續性追蹤器。
///
/// Tracks signal TRANSITIONS (state onset), not states. A signal must persist
/// for `min_persistence_ms` before being acted upon. Close signals are always exempt.
/// 追蹤信號轉換（狀態起始），非狀態。信號必須持續 `min_persistence_ms` 才會被執行。
/// 平倉信號始終免檢。
pub struct PersistenceTracker {
    /// Per-symbol: (direction, first_signal_ts_ms)
    /// 每幣種：（方向，首次信號時間戳 ms）
    state: HashMap<String, (bool, u64)>,
}

impl PersistenceTracker {
    pub fn new() -> Self {
        Self {
            state: HashMap::new(),
        }
    }

    /// Check if signal has persisted long enough.
    /// 檢查信號是否已持續足夠長時間。
    ///
    /// - New signal (None→Some or direction change) → record timestamp, return false
    /// - Same signal continues → check elapsed ≥ min_persistence_ms
    /// - Signal disappears → clear entry, return false
    /// - Close signals → always return true (exempt, reduces risk)
    /// - 新信號（None→Some 或方向改變）→ 記錄時間戳，返回 false
    /// - 同方向信號持續 → 檢查經過時間 ≥ min_persistence_ms
    /// - 信號消失 → 清除記錄，返回 false
    /// - 平倉信號 → 始終返回 true（免檢，降低風險）
    pub fn check(
        &mut self,
        symbol: &str,
        signal: Option<bool>, // None=no signal, Some(true)=long, Some(false)=short
        now_ms: u64,
        min_persistence_ms: u64,
        is_close: bool,
    ) -> bool {
        if is_close {
            return true; // Close always exempt / 平倉始終免檢
        }

        match signal {
            None => {
                self.state.remove(symbol);
                false
            }
            Some(is_long) => {
                let entry = self.state.get(symbol);
                match entry {
                    Some(&(prev_dir, first_ts)) if prev_dir == is_long => {
                        // Same direction — check elapsed time
                        // 同方向 — 檢查經過時間
                        now_ms.saturating_sub(first_ts) >= min_persistence_ms
                    }
                    _ => {
                        // New signal or direction change — start timer
                        // 新信號或方向改變 — 啟動計時器
                        self.state.insert(symbol.to_string(), (is_long, now_ms));
                        // min_persistence_ms=0 would pass immediately
                        min_persistence_ms == 0
                    }
                }
            }
        }
    }

    /// Clear tracking state for a symbol (e.g., after position close).
    /// 清除某幣種的追蹤狀態（例如平倉後）。
    pub fn clear(&mut self, symbol: &str) {
        self.state.remove(symbol);
    }
}

impl Default for PersistenceTracker {
    fn default() -> Self {
        Self::new()
    }
}

// ── Scoring Functions ───────────────────────────────────────────────────────

/// Compute confluence score. Returns None if indicators insufficient (cold-start fallback).
/// Returns Some(0.0) if primary signal is false (mandatory gate).
/// 計算匯流分數。指標不足時返回 None（冷啟動退化）。主信號未觸發時返回 Some(0.0)。
///
/// Score range: [0, 65] (4 conditions, signal is gate not component).
/// 分數範圍：[0, 65]（4 個條件，信號是門控非分量）。
///
/// R3-3: Returns Option<f64> instead of NaN sentinel. Rust's type system forces
/// callers to handle the None case explicitly, preventing NaN propagation bugs.
/// R3-3：返回 Option<f64> 替代 NaN 哨兵。Rust 類型系統強制 caller 顯式處理 None。
pub fn compute_score(
    config: &ConfluenceConfig,
    primary_signal: bool,
    adx: Option<f64>,
    hurst_regime: &str,
    volume_ratio: Option<f64>,
    rsi: Option<f64>,
    is_long: bool,
) -> Option<f64> {
    // ── Gate: primary signal MUST fire ──
    // 門控：主信號必須觸發
    if !primary_signal {
        return Some(0.0);
    }

    // ── Cold-start fallback: if key indicators missing, return None ──
    // 冷啟動退化：關鍵指標缺失時返回 None
    // R3-3: Option<f64> forces caller to handle fallback explicitly
    if adx.is_none() && rsi.is_none() {
        return None; // Caller: None → fallback mode (full qty, skip confluence)
    }

    // ── ADX component ──
    let adx_val = adx.unwrap_or(0.0);
    let adx_score = if adx_val < config.adx_floor {
        0.0 // Insufficient data / 數據不足
    } else if config.invert_adx {
        // Mean-reversion: high ADX = low score, ADX=50→0.0, ADX=8→0.84
        // 均值回歸：高 ADX = 低分，ADX=50→0.0，ADX=8→0.84
        (1.0 - (adx_val / 50.0)).clamp(0.0, 1.0)
    } else {
        // Trend-following: ADX/25, ADX=25→1.0
        // 趨勢跟蹤：ADX/25，ADX=25→1.0
        (adx_val / 25.0).clamp(0.0, 1.0)
    };

    // ── Regime component ──
    let regime_score = match (config.invert_adx, hurst_regime) {
        (false, "trending") => 1.0,
        (true, "mean_reverting") => 1.0,
        (false, "mean_reverting") | (true, "trending") => 0.3,
        _ => 0.6, // "uncertain" or missing / 不確定或缺失
    };

    // ── Volume component (handle None) ──
    let vol_score = match volume_ratio {
        Some(vr) => (vr / 1.2).clamp(0.0, 1.0),
        None => 0.5, // Neutral when unavailable / 不可用時中性
    };

    // ── Momentum component (R2 fix C-5: short=30-50, not 20-45) ──
    let rsi_val = rsi.unwrap_or(50.0);
    let momentum_score = match (is_long, rsi_val) {
        (true, r) if (55.0..=80.0).contains(&r) => 0.9,  // Long + rising momentum
        (false, r) if (30.0..=50.0).contains(&r) => 0.9, // Short + declining, not oversold
        (_, r) if (40.0..=60.0).contains(&r) => 0.6,     // Neutral zone
        _ => 0.3, // Over-extended or misaligned / 過度延伸或錯位
    };

    // ── Weighted sum (4 conditions, max 65) ──
    Some(
        adx_score * config.weight_adx
            + regime_score * config.weight_regime
            + vol_score * config.weight_volume
            + momentum_score * config.weight_momentum,
    )
}

/// Convert score to qty percentage. Smooth curve, no cliffs.
/// 分數→倉位百分比。平滑曲線，無斷崖。
///
/// R3-3: Accepts Option<f64>. None → 1.0 (fallback mode, confluence skipped).
/// R3-3：接受 Option<f64>。None → 1.0（退化模式，跳過 confluence）。
pub fn score_to_qty_pct(score: Option<f64>, config: &ConfluenceConfig) -> f64 {
    let score = match score {
        Some(s) => s,
        None => return 1.0, // Fallback mode: full qty (confluence skipped)
    };
    if score < config.threshold_no_trade {
        // Below floor: linear ramp 0→10% in bottom band (soft floor, no hard cliff)
        // 低於底線：底部帶線性升坡 0→10%（軟底線，無硬斷崖）
        let ramp_start = config.threshold_no_trade - 5.0; // e.g., 30
        if score <= ramp_start {
            0.0
        } else {
            0.10 * (score - ramp_start) / 5.0
        }
    } else if score < config.threshold_light {
        // threshold_no_trade → threshold_light: linear 10%→50%
        0.10 + 0.40 * (score - config.threshold_no_trade)
            / (config.threshold_light - config.threshold_no_trade)
    } else if score < config.threshold_full {
        // threshold_light → threshold_full: linear 50%→100%
        0.50 + 0.50 * (score - config.threshold_light)
            / (config.threshold_full - config.threshold_light)
    } else {
        1.0
    }
}

/// Check if enough indicators are available for confluence scoring.
/// 檢查是否有足夠的指標進行匯流評分。
///
/// Returns true if at least ADX or RSI is present (minimum for scoring).
/// Cold-start fallback: returns false → caller should skip confluence and use full qty.
/// 至少有 ADX 或 RSI 時返回 true（評分最低需求）。
/// 冷啟動退化：返回 false → 調用方應跳過匯流並使用完整 qty。
pub fn indicators_ready(adx: Option<f64>, rsi: Option<f64>) -> bool {
    adx.is_some() || rsi.is_some()
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn trend_config() -> ConfluenceConfig {
        ConfluenceConfig::default()
    }

    fn reversion_config() -> ConfluenceConfig {
        ConfluenceConfig::reversion()
    }

    // ── ConfluenceConfig tests ──

    #[test]
    fn test_default_weights_sum_65() {
        assert!(trend_config().validate().is_ok());
    }

    #[test]
    fn test_reversion_weights_sum_65() {
        assert!(reversion_config().validate().is_ok());
    }

    #[test]
    fn test_breakout_weights_sum_65() {
        assert!(ConfluenceConfig::breakout().validate().is_ok());
    }

    #[test]
    fn test_invalid_weights_rejected() {
        let mut cfg = trend_config();
        cfg.weight_adx = 30.0; // sum = 70, not 65
        assert!(cfg.validate().is_err());
    }

    // ── PersistenceTracker tests ──

    #[test]
    fn test_persistence_new_signal_blocks() {
        let mut tracker = PersistenceTracker::new();
        // First appearance — should block (timer just started)
        assert!(!tracker.check("BTCUSDT", Some(true), 1000, 120_000, false));
    }

    #[test]
    fn test_persistence_signal_passes_after_duration() {
        let mut tracker = PersistenceTracker::new();
        // t=0: start
        assert!(!tracker.check("BTCUSDT", Some(true), 0, 120_000, false));
        // t=60s: still waiting
        assert!(!tracker.check("BTCUSDT", Some(true), 60_000, 120_000, false));
        // t=120s: exactly at threshold — passes
        assert!(tracker.check("BTCUSDT", Some(true), 120_000, 120_000, false));
        // t=130s: still passes
        assert!(tracker.check("BTCUSDT", Some(true), 130_000, 120_000, false));
    }

    #[test]
    fn test_persistence_direction_change_resets() {
        let mut tracker = PersistenceTracker::new();
        assert!(!tracker.check("BTCUSDT", Some(true), 0, 120_000, false));
        // Direction flip at t=100s — resets timer
        assert!(!tracker.check("BTCUSDT", Some(false), 100_000, 120_000, false));
        // t=220s from flip: 120s elapsed since flip → passes
        assert!(tracker.check("BTCUSDT", Some(false), 220_000, 120_000, false));
    }

    #[test]
    fn test_persistence_signal_disappears_clears() {
        let mut tracker = PersistenceTracker::new();
        assert!(!tracker.check("BTCUSDT", Some(true), 0, 120_000, false));
        // Signal gone
        assert!(!tracker.check("BTCUSDT", None, 50_000, 120_000, false));
        // Re-appear — timer restarts
        assert!(!tracker.check("BTCUSDT", Some(true), 60_000, 120_000, false));
        // Need full 120s from re-appear
        assert!(tracker.check("BTCUSDT", Some(true), 180_000, 120_000, false));
    }

    #[test]
    fn test_persistence_close_always_exempt() {
        let mut tracker = PersistenceTracker::new();
        assert!(tracker.check("BTCUSDT", Some(true), 0, 120_000, true));
    }

    #[test]
    fn test_persistence_zero_ms_passes_immediately() {
        let mut tracker = PersistenceTracker::new();
        assert!(tracker.check("BTCUSDT", Some(true), 0, 0, false));
    }

    #[test]
    fn test_persistence_multi_symbol_independent() {
        let mut tracker = PersistenceTracker::new();
        assert!(!tracker.check("BTCUSDT", Some(true), 0, 120_000, false));
        assert!(!tracker.check("ETHUSDT", Some(false), 50_000, 120_000, false));
        // BTC passes at 120s, ETH doesn't yet
        assert!(tracker.check("BTCUSDT", Some(true), 120_000, 120_000, false));
        assert!(!tracker.check("ETHUSDT", Some(false), 120_000, 120_000, false));
        // ETH passes at 170s (50k+120k)
        assert!(tracker.check("ETHUSDT", Some(false), 170_000, 120_000, false));
    }

    // ── compute_score tests ──

    #[test]
    fn test_score_no_primary_signal() {
        let cfg = trend_config();
        let score = compute_score(&cfg, false, Some(30.0), "trending", Some(1.5), Some(65.0), true);
        assert_eq!(score, Some(0.0));
    }

    #[test]
    fn test_score_cold_start_returns_none() {
        let cfg = trend_config();
        let score = compute_score(&cfg, true, None, "uncertain", Some(1.0), None, true);
        assert!(score.is_none());
    }

    #[test]
    fn test_score_perfect_trend() {
        let cfg = trend_config();
        // ADX=25 (→1.0), trending (→1.0), volume=1.2 (→1.0), RSI=65 long (→0.9)
        let score = compute_score(&cfg, true, Some(25.0), "trending", Some(1.2), Some(65.0), true);
        // Expected: 1.0*25 + 1.0*20 + 1.0*12 + 0.9*8 = 64.2
        let s = score.unwrap();
        assert!((s - 64.2).abs() < 0.01, "got {s}");
    }

    #[test]
    fn test_score_low_adx_floors_to_zero() {
        let cfg = trend_config();
        // ADX=5 (< floor 8) → adx_score=0
        let score = compute_score(&cfg, true, Some(5.0), "trending", Some(1.0), Some(50.0), true);
        let s = score.unwrap();
        // 0*25 + 1.0*20 + (1.0/1.2)*12 + 0.6*8 = 0 + 20 + 10 + 4.8 = 34.8
        assert!((s - 34.8).abs() < 0.1, "got {s}");
    }

    #[test]
    fn test_score_reversion_profile() {
        let cfg = reversion_config();
        // ADX=15 (inverted: 1-(15/50)=0.7), mean_reverting (→1.0), vol=1.0 (→0.83), RSI=40 short (→0.9)
        let score =
            compute_score(&cfg, true, Some(15.0), "mean_reverting", Some(1.0), Some(40.0), false);
        let s = score.unwrap();
        // 0.7*15 + 1.0*30 + 0.833*10 + 0.9*10 = 10.5 + 30 + 8.33 + 9.0 = 57.83
        assert!(s > 55.0 && s < 60.0, "got {s}");
    }

    #[test]
    fn test_score_adx_only_no_rsi() {
        let cfg = trend_config();
        // RSI=None → default 50 → neutral zone → 0.6
        let score = compute_score(&cfg, true, Some(20.0), "uncertain", None, None, true);
        // adx=20/25=0.8, regime=0.6, volume=None→0.5, momentum=0.6
        // 0.8*25 + 0.6*20 + 0.5*12 + 0.6*8 = 20+12+6+4.8 = 42.8
        // rsi is None so both adx and rsi would be... wait, adx=Some(20), rsi=None
        // Cold start check: adx.is_none() && rsi.is_none() → false (adx is Some), so we proceed
        let s = score.unwrap();
        assert!(s > 40.0 && s < 45.0, "got {s}");
    }

    // ── score_to_qty_pct tests ──

    #[test]
    fn test_qty_none_returns_full() {
        let cfg = trend_config();
        assert!((score_to_qty_pct(None, &cfg) - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_qty_below_floor() {
        let cfg = trend_config();
        assert!((score_to_qty_pct(Some(25.0), &cfg)).abs() < 1e-10);
    }

    #[test]
    fn test_qty_ramp_zone() {
        let cfg = trend_config(); // EDGE-P1-3: threshold_no_trade=45, ramp zone=40-45
        // score=42.5 → in ramp zone (40-45): 0.10 * (42.5-40)/5 = 0.10*0.5 = 0.05
        assert!((score_to_qty_pct(Some(42.5), &cfg) - 0.05).abs() < 0.01);
    }

    #[test]
    fn test_qty_light_zone() {
        let cfg = trend_config(); // EDGE-P1-3: 45→52: 10%→50%
        // score=48.5 → 0.10 + 0.40*(48.5-45)/(52-45) = 0.10 + 0.40*0.5 = 0.30
        assert!((score_to_qty_pct(Some(48.5), &cfg) - 0.30).abs() < 0.01);
    }

    #[test]
    fn test_qty_standard_zone() {
        let cfg = trend_config(); // EDGE-P1-3: 52→58: 50%→100%
        // score=55 → 0.50 + 0.50*(55-52)/(58-52) = 0.50 + 0.25 = 0.75
        assert!((score_to_qty_pct(Some(55.0), &cfg) - 0.75).abs() < 0.01);
    }

    #[test]
    fn test_qty_full_zone() {
        let cfg = trend_config();
        assert!((score_to_qty_pct(Some(60.0), &cfg) - 1.0).abs() < 1e-10);
    }

    // ── indicators_ready tests ──

    #[test]
    fn test_indicators_ready_both_present() {
        assert!(indicators_ready(Some(20.0), Some(50.0)));
    }

    #[test]
    fn test_indicators_ready_adx_only() {
        assert!(indicators_ready(Some(20.0), None));
    }

    #[test]
    fn test_indicators_ready_rsi_only() {
        assert!(indicators_ready(None, Some(50.0)));
    }

    #[test]
    fn test_indicators_ready_neither() {
        assert!(!indicators_ready(None, None));
    }

    // ── G-SR-1 S4: Edge-case tests ──

    #[test]
    fn test_score_inverted_adx_high_yields_low() {
        // Reversion: high ADX (50) → adx_score = 1-(50/50) = 0.0
        let cfg = reversion_config();
        let score = compute_score(&cfg, true, Some(50.0), "mean_reverting", Some(1.2), Some(40.0), false);
        let s = score.unwrap();
        // 0.0*15 + 1.0*30 + 1.0*10 + 0.9*10 = 0+30+10+9 = 49
        assert!(s > 45.0 && s < 52.0, "got {s}");
    }

    #[test]
    fn test_score_inverted_adx_low_yields_high() {
        // Reversion: low ADX (10) → adx_score = 1-(10/50) = 0.8
        let cfg = reversion_config();
        let score = compute_score(&cfg, true, Some(10.0), "mean_reverting", Some(1.2), Some(40.0), false);
        let s = score.unwrap();
        // 0.8*15 + 1.0*30 + 1.0*10 + 0.9*10 = 12+30+10+9 = 61
        assert!(s > 58.0 && s < 64.0, "got {s}");
    }

    #[test]
    fn test_score_short_momentum_rsi_30_50() {
        // C-5 fix: short RSI 30-50 → 0.9 (not 20-45)
        let cfg = trend_config();
        let score = compute_score(&cfg, true, Some(25.0), "trending", Some(1.2), Some(35.0), false);
        let s = score.unwrap();
        // adx=1.0*25 + regime=1.0*20 + vol=1.0*12 + momentum(short, RSI=35 in [30,50])=0.9*8 = 64.2
        assert!((s - 64.2).abs() < 0.1, "got {s}");
    }

    #[test]
    fn test_score_short_momentum_rsi_25_not_in_range() {
        // RSI=25 for short: not in [30,50], not in [40,60] → falls to 0.3
        let cfg = trend_config();
        let score = compute_score(&cfg, true, Some(25.0), "trending", Some(1.2), Some(25.0), false);
        let s = score.unwrap();
        // 1.0*25 + 1.0*20 + 1.0*12 + 0.3*8 = 59.4
        assert!((s - 59.4).abs() < 0.1, "got {s}");
    }

    #[test]
    fn test_score_volume_ratio_none_neutral() {
        let cfg = trend_config();
        // volume=None → 0.5
        let score = compute_score(&cfg, true, Some(25.0), "trending", None, Some(65.0), true);
        let s = score.unwrap();
        // 1.0*25 + 1.0*20 + 0.5*12 + 0.9*8 = 25+20+6+7.2 = 58.2
        assert!((s - 58.2).abs() < 0.1, "got {s}");
    }

    #[test]
    fn test_score_volume_ratio_high_clamps() {
        let cfg = trend_config();
        // volume=5.0 → (5.0/1.2)=4.16 → clamp to 1.0
        let score = compute_score(&cfg, true, Some(25.0), "trending", Some(5.0), Some(65.0), true);
        let s = score.unwrap();
        // Same as perfect: 1.0*25 + 1.0*20 + 1.0*12 + 0.9*8 = 64.2
        assert!((s - 64.2).abs() < 0.1, "got {s}");
    }

    #[test]
    fn test_qty_pct_at_exact_thresholds() {
        let cfg = trend_config(); // EDGE-P1-3: no_trade=45, light=52, full=58
        // Exactly at no_trade: should be 10%
        assert!((score_to_qty_pct(Some(45.0), &cfg) - 0.10).abs() < 0.01);
        // Exactly at light: should be 50%
        assert!((score_to_qty_pct(Some(52.0), &cfg) - 0.50).abs() < 0.01);
        // Exactly at full: should be 100%
        assert!((score_to_qty_pct(Some(58.0), &cfg) - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_qty_pct_soft_ramp_bottom() {
        let cfg = trend_config(); // EDGE-P1-3: ramp_start = 45-5 = 40
        // Score=39 → below ramp_start → 0%
        assert!((score_to_qty_pct(Some(39.0), &cfg)).abs() < 1e-10);
        // Score=40.01 → just above ramp_start → tiny %
        let pct = score_to_qty_pct(Some(40.01), &cfg);
        assert!(pct > 0.0 && pct < 0.01, "got {pct}");
    }

    #[test]
    fn test_score_regime_uncertain() {
        // "uncertain" regime → 0.6 regardless of invert_adx
        let cfg = trend_config();
        let s1 = compute_score(&cfg, true, Some(25.0), "uncertain", Some(1.2), Some(65.0), true).unwrap();
        let cfg2 = reversion_config();
        let s2 = compute_score(&cfg2, true, Some(10.0), "uncertain", Some(1.2), Some(40.0), false).unwrap();
        // Both should use regime_score=0.6
        // Trend: 1.0*25 + 0.6*20 + 1.0*12 + 0.9*8 = 25+12+12+7.2 = 56.2
        assert!((s1 - 56.2).abs() < 0.1, "trend uncertain: got {s1}");
        // Reversion: 0.8*15 + 0.6*30 + 1.0*10 + 0.9*10 = 12+18+10+9 = 49
        assert!(s2 > 46.0 && s2 < 52.0, "reversion uncertain: got {s2}");
    }

    #[test]
    fn test_persistence_clear_resets_tracking() {
        let mut tracker = PersistenceTracker::new();
        // Start tracking
        assert!(!tracker.check("BTCUSDT", Some(true), 0, 120_000, false));
        // Clear
        tracker.clear("BTCUSDT");
        // Re-check: timer should have reset
        assert!(!tracker.check("BTCUSDT", Some(true), 60_000, 120_000, false));
        // New timer: need 60_000+120_000 = 180_000
        assert!(tracker.check("BTCUSDT", Some(true), 180_000, 120_000, false));
    }

    #[test]
    fn test_validate_threshold_ordering_in_config() {
        // ConfluenceConfig.validate() only checks weight sum, not thresholds.
        // Threshold ordering is validated at strategy level (S3).
        let mut cfg = trend_config();
        cfg.threshold_no_trade = 50.0;
        cfg.threshold_light = 40.0; // wrong order
        // ConfluenceConfig.validate() should still pass (only checks weights)
        assert!(cfg.validate().is_ok());
        // But score_to_qty_pct with bad thresholds produces weird results
        // (this is why strategy-level validation catches it first)
    }
}
