//! v1_15 arm space: 5 strategies x 3 regimes = 15 cold-start arms.
//! v1_15 arm 空間：5 策略 x 3 regime = 15 個 cold-start arms。
//!
//! MODULE_NOTE (EN): Phase 4 sub-task 4-04 baseline arm space. Naming convention
//!   is "{regime}__{strategy}" (double underscore separator) so regex split is
//!   unambiguous even if a strategy id later contains a single underscore.
//!   Sub-task 4-06 will introduce v2_25 (× symbol-bucket) and v3_375 (× symbol).
//! MODULE_NOTE (中): Phase 4 子任務 4-04 基準 arm 空間。命名約定為
//!   "{regime}__{strategy}"（雙底線分隔），即使策略 id 含單底線也能清楚拆分。
//!   子任務 4-06 將引入 v2_25（× symbol-bucket）與 v3_375（× symbol）。

/// Strategy identifiers in v1_15 / v1_15 中的策略 id
pub const STRATEGIES_V1_15: [&str; 5] = [
    "ma_crossover",
    "bb_breakout",
    "bb_reversion",
    "grid_trading",
    "funding_arb",
];

/// Regime identifiers in v1_15 / v1_15 中的 regime id
pub const REGIMES_V1_15: [&str; 3] = ["trending", "mean_reverting", "random_walk"];

/// Arm space version label, matches `learning.linucb_state.arm_space_version`.
/// arm 空間版本標籤，對應 `learning.linucb_state.arm_space_version`。
pub const ARM_SPACE_VERSION_V1_15: &str = "v1_15";

/// Return all 15 cold-start arm IDs for v1_15.
/// 返回 v1_15 的所有 15 個 cold-start arm ID。
pub fn v1_15_arm_ids() -> Vec<String> {
    let mut ids = Vec::with_capacity(15);
    for regime in REGIMES_V1_15.iter() {
        for strategy in STRATEGIES_V1_15.iter() {
            ids.push(format!("{}__{}", regime, strategy));
        }
    }
    ids
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_v1_15_arm_ids_returns_15() {
        let ids = v1_15_arm_ids();
        assert_eq!(ids.len(), 15);
        // Spot-check naming / 命名抽查
        assert!(ids.contains(&"trending__ma_crossover".to_string()));
        assert!(ids.contains(&"random_walk__funding_arb".to_string()));
        // All unique / 全部唯一
        let mut sorted = ids.clone();
        sorted.sort();
        sorted.dedup();
        assert_eq!(sorted.len(), 15);
    }
}
