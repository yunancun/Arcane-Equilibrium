//! Dynamic stop-loss calculations with ATR adaptation and anti-cluster offset.
//! 動態止損計算：ATR 自適應 + 反聚集偏移。

use super::config::regime_multipliers;

/// Compute a deterministic anti-cluster offset in [-0.15, +0.15].
/// 計算確定性反聚集偏移量，範圍 [-0.15, +0.15]。
///
/// Purpose: prevent multiple positions from hitting stops at the exact same level.
/// 目的：防止多個持倉在完全相同的價位觸發止損。
///
/// Uses a simple hash of symbol + timestamp for deterministic but distributed offsets.
/// 使用 symbol + 時間戳的簡單雜湊，產生確定性但分散的偏移。
pub fn anti_cluster_offset(symbol: &str, ts_ms: u64) -> f64 {
    let mut hash: u64 = 0;
    for b in symbol.bytes() {
        hash = hash.wrapping_mul(31).wrapping_add(b as u64);
    }
    hash = hash.wrapping_mul(ts_ms.wrapping_add(1));
    let norm = (hash % 10000) as f64 / 10000.0; // 0.0 – 1.0
    (norm - 0.5) * 0.30 // -0.15 to +0.15
}

/// Compute dynamic stop-loss percentage incorporating ATR, regime, and anti-cluster offset.
/// 計算動態止損百分比，整合 ATR、regime 乘數和反聚集偏移。
///
/// # Logic / 邏輯
/// 1. Apply regime multiplier to base stop / 對基礎止損應用 regime 乘數
/// 2. Cap at 80% of hard stop (leave headroom) / 上限為硬止損的 80%（留餘裕）
/// 3. If ATR available: use max(base, min(atr×1.5, cap)) / 若有 ATR：取 max(基礎, min(atr×1.5, 上限))
/// 4. Apply anti-cluster offset for distribution / 應用反聚集偏移以分散止損位
/// 5. Floor at 0.1% (never set a near-zero stop) / 下限 0.1%（不允許接近零的止損）
///
/// # Arguments / 參數
/// - `base_stop_pct`:  Base stop-loss percentage / 基礎止損百分比
/// - `atr_pct`:        ATR as % of price (None if unavailable) / ATR 佔價格百分比
/// - `symbol`:         Trading symbol for hash seed / 交易符號（雜湊種子）
/// - `entry_ts_ms`:    Entry timestamp ms for hash seed / 入場時間戳毫秒（雜湊種子）
/// - `regime`:         Market regime string / 市場 regime 字串
/// - `hard_stop_pct`:  Hard stop ceiling from config / 配置的硬止損上限
pub fn compute_dynamic_stop_pct(
    base_stop_pct: f64,
    atr_pct: Option<f64>,
    symbol: &str,
    entry_ts_ms: u64,
    regime: &str,
    hard_stop_pct: f64,
) -> f64 {
    let rm = regime_multipliers(regime);
    let base = base_stop_pct * rm.stop;
    let cap = hard_stop_pct * 0.8; // 80% of hard stop — leave headroom / 硬止損的 80%

    let effective = match atr_pct {
        Some(atr) => {
            let atr_stop = atr * 1.5;
            // Use ATR-derived stop, but never below base, never above cap
            // 使用 ATR 推導的止損，但不低於基礎值，不高於上限
            base.max(atr_stop.min(cap))
        }
        None => base,
    };

    // Anti-cluster: distribute stops around the effective level
    // 反聚集：在有效止損位附近分散
    let offset = anti_cluster_offset(symbol, entry_ts_ms);
    (effective * (1.0 + offset)).max(0.1)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_anti_cluster_offset_range() {
        // Offset must be in [-0.15, +0.15] / 偏移量必須在 [-0.15, +0.15]
        for ts in [0u64, 1, 1000, 1_700_000_000_000, u64::MAX] {
            let off = anti_cluster_offset("BTCUSDT", ts);
            assert!(
                (-0.15..=0.15).contains(&off),
                "offset {off} out of range for ts={ts}"
            );
        }
    }

    #[test]
    fn test_anti_cluster_deterministic() {
        let a = anti_cluster_offset("ETHUSDT", 12345);
        let b = anti_cluster_offset("ETHUSDT", 12345);
        assert_eq!(a, b, "same inputs must produce same offset");
    }

    #[test]
    fn test_anti_cluster_different_symbols() {
        let a = anti_cluster_offset("BTCUSDT", 12345);
        let b = anti_cluster_offset("ETHUSDT", 12345);
        // Not guaranteed different, but extremely unlikely to be equal
        // with different symbols
        assert_ne!(a, b, "different symbols should usually differ");
    }

    #[test]
    fn test_dynamic_stop_no_atr() {
        // No ATR → use base × regime / 無 ATR → 使用基礎 × regime
        let stop = compute_dynamic_stop_pct(2.0, None, "BTCUSDT", 1000, "trending", 5.0);
        // trending stop mult = 1.0, base = 2.0
        // With anti-cluster offset, result should be near 2.0
        assert!(stop > 1.5 && stop < 2.5, "stop={stop}, expected ~2.0");
    }

    #[test]
    fn test_dynamic_stop_with_atr() {
        // ATR = 3.0%, base = 1.5%, cap = 5.0 * 0.8 = 4.0
        // atr_stop = 3.0 * 1.5 = 4.5, capped to 4.0
        // effective = max(1.5, 4.0) = 4.0
        let stop = compute_dynamic_stop_pct(1.5, Some(3.0), "BTCUSDT", 1000, "trending", 5.0);
        // With anti-cluster offset, result should be near 4.0
        assert!(stop > 3.0 && stop < 5.0, "stop={stop}, expected ~4.0");
    }

    #[test]
    fn test_dynamic_stop_volatile_regime() {
        // volatile stop mult = 1.5, base = 2.0 → 3.0
        let stop = compute_dynamic_stop_pct(2.0, None, "BTCUSDT", 1000, "volatile", 5.0);
        assert!(stop > 2.0 && stop < 4.0, "stop={stop}, expected ~3.0");
    }

    #[test]
    fn test_dynamic_stop_floor() {
        // Very small base + squeeze regime (0.6×) should still be >= 0.1
        let stop = compute_dynamic_stop_pct(0.05, None, "BTCUSDT", 1000, "squeeze", 5.0);
        assert!(stop >= 0.1, "stop={stop} must be >= 0.1");
    }

    #[test]
    fn test_dynamic_stop_atr_below_base() {
        // ATR very low → atr_stop < base → use base
        // base=3.0, atr=0.5 → atr_stop=0.75, effective=max(3.0, 0.75)=3.0
        let stop = compute_dynamic_stop_pct(3.0, Some(0.5), "BTCUSDT", 1000, "trending", 5.0);
        assert!(stop > 2.0 && stop < 4.0, "stop={stop}, expected ~3.0");
    }
}
