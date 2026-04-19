//! Track P 物理層退場特徵 / Track P physical-layer exit features
//!
//! 共享型別：供 T3 (physical_micro_profit_lock) 與 T4 (combine_layer) 使用。
//! Shared types used by T3 and T4 (DUAL-TRACK-EXIT-1 Track P skeleton).

/// 物理層退場決策特徵快照 / Physical-layer exit decision feature snapshot.
///
/// 任何 Option 欄位為 None 代表「歷史/樣本不足」，下游 gate 須保守（Hold）。
/// None means insufficient history/samples; downstream gates must be conservative.
#[derive(Debug, Clone, PartialEq)]
pub struct ExitFeatures {
    /// Shrunk JS edge（bps）; None = cell 缺失 / missing cell
    pub est_net_bps: Option<f32>,
    /// 此 position 自 entry 後曾達的最大 favorable PnL %（side-signed）
    /// Position's peak side-signed favorable PnL % since entry
    pub peak_pnl_pct: f32,
    /// 當前 tick 的 side-signed PnL % / Current side-signed PnL %
    pub current_pnl_pct: f64,
    /// ATR %（price_tracker.compute_atr_pct） / ATR percentage
    pub atr_pct: Option<f64>,
    /// 從 peak 回吐幅度以 ATR 正規化 / Giveback from peak normalised by ATR
    pub giveback_atr_norm: Option<f32>,
    /// 自 peak 以來的毫秒 / Milliseconds since peak
    pub time_since_peak_ms: Option<i64>,
    /// 短期 (≈300ms) 價格變化率 / Short-horizon price rate-of-change
    pub price_roc_short: Option<f32>,
    /// Position 存活秒數 / Entry age in seconds
    pub entry_age_secs: Option<f32>,
}

/// Track P 物理層決策 / Track P physical-layer decision.
#[derive(Debug, Clone, PartialEq)]
pub enum PhysicalDecision {
    /// 維持持有 / Continue holding
    Hold,
    /// 鎖定退場，附原因字串（寫入 fills.details 供歸因）
    /// Lock-and-exit, reason string persisted to fills.details for audit trail
    Lock(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_exit_features_construction_round_trip() {
        let f = ExitFeatures {
            est_net_bps: Some(12.5),
            peak_pnl_pct: 1.75,
            current_pnl_pct: 1.20,
            atr_pct: Some(0.45),
            giveback_atr_norm: Some(0.8),
            time_since_peak_ms: Some(1500),
            price_roc_short: Some(-0.002),
            entry_age_secs: Some(45.0),
        };
        // Debug 可格式化（不 panic）
        let dbg = format!("{:?}", f);
        assert!(dbg.contains("ExitFeatures"));
        // Clone + PartialEq
        let g = f.clone();
        assert_eq!(f, g);
    }

    #[test]
    fn test_exit_features_none_fields_allowed() {
        let f = ExitFeatures {
            est_net_bps: None,
            peak_pnl_pct: 0.0,
            current_pnl_pct: 0.0,
            atr_pct: None,
            giveback_atr_norm: None,
            time_since_peak_ms: None,
            price_roc_short: None,
            entry_age_secs: None,
        };
        // 構造成功且可 clone/eq
        let g = f.clone();
        assert_eq!(f, g);
        assert!(f.est_net_bps.is_none());
        assert!(f.atr_pct.is_none());
        assert!(f.giveback_atr_norm.is_none());
        assert!(f.time_since_peak_ms.is_none());
        assert!(f.price_roc_short.is_none());
        assert!(f.entry_age_secs.is_none());
    }

    #[test]
    fn test_physical_decision_variants_equality() {
        let hold = PhysicalDecision::Hold;
        let lock_a = PhysicalDecision::Lock("a".to_string());
        let lock_b = PhysicalDecision::Lock("b".to_string());
        let lock_x_1 = PhysicalDecision::Lock("x".to_string());
        let lock_x_2 = PhysicalDecision::Lock("x".to_string());

        assert_ne!(hold, lock_a);
        assert_ne!(lock_a, lock_b);
        assert_eq!(lock_x_1, lock_x_2);
    }
}
