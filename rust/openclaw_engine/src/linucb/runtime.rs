//! LinUCB runtime integration — per-decision arm selection on the live path.
//! LinUCB 運行時整合 — 在 live 路徑做 per-decision arm 選擇。
//!
//! MODULE_NOTE (EN):
//!   Owns the in-memory ArmState[15] for the active arm_space_version,
//!   cold-started at boot. Each call to `select_for_intent` returns the
//!   selected arm_id + UCB without actually changing the trading decision
//!   (read-only feature collection — Phase 4 baseline). Reward feedback
//!   loop is Phase 5. Uses std::sync::RwLock (sync) instead of tokio so it
//!   can be read from both sync and async call sites (the tick pipeline
//!   producer is a sync closure inside try_send).
//!
//! MODULE_NOTE (中):
//!   持有 active arm_space_version 的 in-memory ArmState[15]，
//!   啟動時 cold-start。每次呼叫 `select_for_intent` 返回 selected arm_id
//!   + UCB，但不改變交易決策（唯讀特徵收集 — Phase 4 baseline）。
//!   Reward feedback 留 Phase 5。使用 std::sync::RwLock（同步）而非 tokio，
//!   讓 sync / async 呼叫點都可以讀（tick_pipeline producer 是 try_send
//!   內的同步閉包）。
//!
//! Math reference / 數學參考: docs/references/math_implementation_notes.md Entry 01 §1.3

use crate::linucb::arms_v1_15::{v1_15_arm_ids, ARM_SPACE_VERSION_V1_15};
use crate::linucb::inference::{compute_ucb, select_arm, ArmState, LinUcbConfig};
use crate::linucb::schema_hash::compute_feature_schema_hash;
use std::sync::{Arc, RwLock};

/// v1 context feature names (order is load-bearing — schema hash depends on it).
/// v1 context 特徵名（順序會影響 schema hash，不能隨意調整）。
pub const FEATURE_NAMES_V1: &[&str] = &[
    "atr_pct",
    "rsi_14",
    "bb_bandwidth",
    "hurst_h",
    "adx",
    "vol_ratio",
    "time_of_day_sin",
    "time_of_day_cos",
];

/// Context feature dimension (must equal FEATURE_NAMES_V1.len()).
/// Context 特徵維度（必須等於 FEATURE_NAMES_V1.len()）。
pub const CONTEXT_DIM_V1: usize = 8;

/// Result of a single arm selection — metadata only, never drives the trade.
/// 單次 arm 選擇結果 — 僅 metadata，不驅動交易。
#[derive(Debug, Clone)]
pub struct ArmSelection {
    pub arm_id: String,
    pub ucb: f64,
    pub regime: String,
    pub strategy: String,
}

/// Live LinUCB runtime — shared Arc handle plugged into tick_pipeline / intent_processor.
/// Live LinUCB 運行時 — 共享 Arc，插入 tick_pipeline / intent_processor。
pub struct LinUcbRuntime {
    arms: RwLock<Vec<ArmState>>,
    config: LinUcbConfig,
    arm_space_version: String,
    feature_schema_hash: String,
}

impl LinUcbRuntime {
    /// EN: Cold-start constructor (15 arms, all identity prior) at 8-dim context.
    /// 中文: 冷啟動構造（15 個 arms，全 identity prior），context 維度 = 8。
    pub fn cold_start_v1_15() -> Arc<Self> {
        let config = LinUcbConfig {
            context_dim: CONTEXT_DIM_V1,
            alpha: 1.0,
            lambda: 1.0,
        };
        let mut arms = Vec::with_capacity(15);
        for arm_id in v1_15_arm_ids() {
            arms.push(ArmState::cold_start(arm_id, config.context_dim, config.lambda));
        }
        let feature_schema_hash = compute_feature_schema_hash(FEATURE_NAMES_V1);
        Arc::new(Self {
            arms: RwLock::new(arms),
            config,
            arm_space_version: ARM_SPACE_VERSION_V1_15.to_string(),
            feature_schema_hash,
        })
    }

    /// EN: Build context feature vector from indicator-snapshot fields. Missing
    ///     values fall back to neutral (0.5 on [0,1] normalised axes, 1.0 for
    ///     vol_ratio, 50/100 for rsi, 25/100 for adx). Time-of-day uses a
    ///     24-hour sin/cos cyclic encoding.
    /// 中文: 從指標 snapshot 欄位建構 context 向量。缺值回退到中性
    ///     （[0,1] 正規化軸用 0.5，vol_ratio=1.0，rsi=50，adx=25）。
    ///     time-of-day 使用 24 小時 sin/cos 循環編碼。
    pub fn build_context_features(
        atr_pct: Option<f64>,
        rsi_14: Option<f64>,
        bb_bandwidth: Option<f64>,
        hurst_h: Option<f64>,
        adx: Option<f64>,
        vol_ratio: Option<f64>,
        timestamp_ms: i64,
    ) -> Vec<f64> {
        // Time-of-day cyclic features (24-hour period).
        // 一日內循環特徵（24 小時週期）。
        let secs_in_day = ((timestamp_ms.rem_euclid(86_400_000)) / 1000) as f64;
        let frac = secs_in_day / 86_400.0;
        let two_pi = std::f64::consts::TAU;
        vec![
            atr_pct.unwrap_or(0.5).clamp(0.0, 1.0),
            (rsi_14.unwrap_or(50.0) / 100.0).clamp(0.0, 1.0),
            bb_bandwidth.unwrap_or(0.5).clamp(0.0, 5.0),
            hurst_h.unwrap_or(0.5).clamp(0.0, 1.0),
            adx.unwrap_or(25.0).clamp(0.0, 100.0) / 100.0,
            vol_ratio.unwrap_or(1.0).clamp(0.0, 5.0),
            (two_pi * frac).sin(),
            (two_pi * frac).cos(),
        ]
    }

    /// EN: Read-only arm selection for the given regime + strategy. Returns
    ///     None if the corresponding arm doesn't exist, the context dim is
    ///     wrong, or the internal lock is poisoned (fail-soft).
    /// 中文: 對指定 regime + strategy 的唯讀 arm 選擇。對應 arm 不存在、
    ///     context 維度錯誤、或內部鎖毒化時返回 None（fail-soft）。
    pub fn select_for_intent(
        &self,
        regime: &str,
        strategy: &str,
        context: &[f64],
    ) -> Option<ArmSelection> {
        if context.len() != self.config.context_dim {
            return None;
        }
        // Naming convention from arms_v1_15: "{regime}__{strategy}".
        // arms_v1_15 命名：「{regime}__{strategy}」。
        let arm_id = format!("{}__{}", regime, strategy);
        let arms = self.arms.read().ok()?;
        let arm = arms.iter().find(|a| a.arm_id == arm_id)?;
        let ucb = compute_ucb(arm, context, self.config.alpha, self.config.context_dim);
        Some(ArmSelection {
            arm_id,
            ucb,
            regime: regime.to_string(),
            strategy: strategy.to_string(),
        })
    }

    /// EN: Pick the highest-UCB arm across all 15 (used for "what would
    ///     LinUCB choose" baseline tracking). Returns None on lock poison,
    ///     dim mismatch, or unparsable arm_id.
    /// 中文: 從 15 個中選 UCB 最高（供「LinUCB 會選什麼」基準追蹤）。
    ///     鎖毒化、維度錯誤或 arm_id 無法解析時返回 None。
    pub fn select_best(&self, context: &[f64]) -> Option<ArmSelection> {
        if context.len() != self.config.context_dim {
            return None;
        }
        let arms = self.arms.read().ok()?;
        let best = select_arm(&arms, context, &self.config)?;
        let parts: Vec<&str> = best.arm_id.splitn(2, "__").collect();
        if parts.len() != 2 {
            return None;
        }
        let ucb = compute_ucb(best, context, self.config.alpha, self.config.context_dim);
        Some(ArmSelection {
            arm_id: best.arm_id.clone(),
            ucb,
            regime: parts[0].to_string(),
            strategy: parts[1].to_string(),
        })
    }

    pub fn arm_space_version(&self) -> &str {
        &self.arm_space_version
    }

    pub fn feature_schema_hash(&self) -> &str {
        &self.feature_schema_hash
    }

    pub fn context_dim(&self) -> usize {
        self.config.context_dim
    }

    /// EN: Number of arms currently held (for observability / tests).
    /// 中文: 當前持有的 arm 數量（供觀察性 / 測試使用）。
    pub fn arm_count(&self) -> usize {
        self.arms.read().map(|a| a.len()).unwrap_or(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cold_start_15_arms_initialized() {
        let rt = LinUcbRuntime::cold_start_v1_15();
        assert_eq!(rt.arm_count(), 15);
        assert_eq!(rt.arm_space_version(), "v1_15");
        assert_eq!(rt.context_dim(), CONTEXT_DIM_V1);
    }

    #[test]
    fn test_select_for_intent_known_arm_returns_some() {
        let rt = LinUcbRuntime::cold_start_v1_15();
        let ctx = vec![0.5; CONTEXT_DIM_V1];
        let sel = rt
            .select_for_intent("trending", "ma_crossover", &ctx)
            .expect("known arm");
        assert_eq!(sel.arm_id, "trending__ma_crossover");
        assert_eq!(sel.regime, "trending");
        assert_eq!(sel.strategy, "ma_crossover");
        assert!(sel.ucb.is_finite());
    }

    #[test]
    fn test_select_for_intent_unknown_arm_returns_none() {
        let rt = LinUcbRuntime::cold_start_v1_15();
        let ctx = vec![0.5; CONTEXT_DIM_V1];
        assert!(rt.select_for_intent("nonexistent", "strategy", &ctx).is_none());
        // Wrong dim → None / 維度錯誤
        assert!(rt
            .select_for_intent("trending", "ma_crossover", &[0.1, 0.2])
            .is_none());
    }

    #[test]
    fn test_select_best_picks_highest_ucb() {
        let rt = LinUcbRuntime::cold_start_v1_15();
        let ctx = vec![0.5; CONTEXT_DIM_V1];
        let best = rt.select_best(&ctx).expect("some best");
        // On pure cold start all UCBs are equal, so any valid arm_id is fine;
        // assert structural validity.
        // 冷啟動時所有 UCB 相等，任何合法 arm_id 皆可；驗證結構合法。
        assert!(best.arm_id.contains("__"));
        assert!(best.ucb >= 0.0);
        assert!(!best.regime.is_empty());
        assert!(!best.strategy.is_empty());
    }

    #[test]
    fn test_build_context_features_8_dim() {
        let v = LinUcbRuntime::build_context_features(
            Some(0.02),
            Some(55.0),
            Some(0.3),
            Some(0.6),
            Some(30.0),
            Some(1.2),
            0,
        );
        assert_eq!(v.len(), CONTEXT_DIM_V1);
        for x in &v {
            assert!(x.is_finite());
        }
    }

    #[test]
    fn test_build_context_features_handles_none_with_fallback() {
        let v = LinUcbRuntime::build_context_features(None, None, None, None, None, None, 0);
        assert_eq!(v.len(), CONTEXT_DIM_V1);
        // Neutral fallbacks / 中性回退
        assert!((v[0] - 0.5).abs() < 1e-9); // atr_pct
        assert!((v[1] - 0.5).abs() < 1e-9); // rsi 50/100
        assert!((v[2] - 0.5).abs() < 1e-9); // bb
        assert!((v[3] - 0.5).abs() < 1e-9); // hurst
        assert!((v[4] - 0.25).abs() < 1e-9); // adx 25/100
        assert!((v[5] - 1.0).abs() < 1e-9); // vol_ratio
        // time-of-day at ts=0 → sin(0)=0, cos(0)=1
        assert!(v[6].abs() < 1e-9);
        assert!((v[7] - 1.0).abs() < 1e-9);
    }

    #[test]
    fn test_feature_schema_hash_matches_expected() {
        let rt = LinUcbRuntime::cold_start_v1_15();
        let direct = compute_feature_schema_hash(FEATURE_NAMES_V1);
        assert_eq!(rt.feature_schema_hash(), direct);
        assert!(rt.feature_schema_hash().starts_with("sha256:"));
    }

    #[test]
    fn test_arm_id_naming_regime_strategy() {
        let rt = LinUcbRuntime::cold_start_v1_15();
        let ctx = vec![0.5; CONTEXT_DIM_V1];
        // All 5 strategies under all 3 regimes must be resolvable.
        // 3 regime × 5 strategy 全部可解析。
        for regime in ["trending", "mean_reverting", "random_walk"] {
            for strat in [
                "ma_crossover",
                "bb_breakout",
                "bb_reversion",
                "grid_trading",
                "funding_arb",
            ] {
                let sel = rt
                    .select_for_intent(regime, strat, &ctx)
                    .expect("arm exists");
                assert_eq!(sel.arm_id, format!("{}__{}", regime, strat));
            }
        }
    }

    #[test]
    fn test_time_of_day_cyclic_wraps() {
        // At noon UTC (ts = 12h) sin/cos should reflect half-period.
        // 中午 UTC（12h）sin/cos 應在半週期。
        let noon_ms: i64 = 12 * 3_600 * 1000;
        let v = LinUcbRuntime::build_context_features(None, None, None, None, None, None, noon_ms);
        // sin(pi) ≈ 0, cos(pi) ≈ -1
        assert!(v[6].abs() < 1e-9);
        assert!((v[7] + 1.0).abs() < 1e-9);
    }
}
