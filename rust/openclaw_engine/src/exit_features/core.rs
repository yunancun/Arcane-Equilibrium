//! Core types: `ExitFeatures` 快照 + `PhysicalDecision` Track P 決策枚舉。
//! Core types: `ExitFeatures` snapshot + `PhysicalDecision` Track P decision.
//!
//! 與 consumer/builder 分檔（EXIT-FEATURES-SPLIT-1，2026-04-21）以控制單檔
//! 行數 ≤ §七 1200 硬上限；外部呼叫仍走 `crate::exit_features::…` re-export。
//! Split out from consumers/builder (EXIT-FEATURES-SPLIT-1, 2026-04-21) to
//! keep each file below §七 1200-line hard cap; external callers still use
//! `crate::exit_features::…` re-exports declared in the parent `mod.rs`.

/// 物理層退場決策特徵快照 / Physical-layer exit decision feature snapshot.
///
/// 任何 Option 欄位為 None 代表「歷史/樣本不足」，下游 gate 須保守（Hold）。
/// None means insufficient history/samples; downstream gates must be conservative.
///
/// T1-FIX: `serde::Serialize` + `serde::Deserialize` 供未來 EXIT-FEATURES-TABLE 持久化 /
/// consumer。`Deserialize` 包含以支持單元測試的 round-trip，Phase 1b+ 的離線
/// replay/fixture 管線亦會用到。
/// T1-FIX: `Serialize` + `Deserialize` for future EXIT-FEATURES-TABLE persistence
/// consumer. `Deserialize` included to support unit-test round-trips and the
/// Phase 1b+ offline replay/fixture pipeline.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
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
///
/// T1-FIX: `serde::Serialize` + `serde::Deserialize` 同 ExitFeatures，供持久化
/// 與 round-trip 測試。
/// T1-FIX: `Serialize` + `Deserialize` as ExitFeatures, for persistence and
/// round-trip tests.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
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

    // T1-FIX: Serialize boundary tests / Serialize 邊界測試
    // 驗證 None / 0.0 / stale_peak 邊界條件可安全序列化，未來 EXIT-FEATURES-TABLE
    // 持久化消費者不會在邊界值爆掉。
    // Ensure None / 0.0 / stale_peak boundary values serialise safely; future
    // EXIT-FEATURES-TABLE persistence consumers will not blow up on edges.

    #[test]
    fn test_exit_features_est_net_bps_none_serializes() {
        // est_net_bps=None（cell 缺失）必須序列化為 JSON null，
        // 下游 writer/reader 不可依賴欄位必定為數字。
        // est_net_bps=None (missing cell) must serialise to JSON null; downstream
        // writers/readers must not assume the field is always numeric.
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
        let j = serde_json::to_string(&f).expect("serialize");
        assert!(
            j.contains("\"est_net_bps\":null"),
            "expected est_net_bps:null in {}",
            j
        );
    }

    #[test]
    fn test_exit_features_atr_pct_zero_boundary() {
        // atr_pct=Some(0.0) 為合法構造（波動性為 0 的極端邊界），
        // 僅驗證 ctor + serialize 無 panic；gate 語意歸屬 risk_checks。
        // atr_pct=Some(0.0) is a valid boundary (degenerate volatility); we only
        // check that ctor + serialize do not panic. Gate semantics live in
        // risk_checks.
        let f = ExitFeatures {
            est_net_bps: Some(10.0),
            peak_pnl_pct: 1.0,
            current_pnl_pct: 0.5,
            atr_pct: Some(0.0),
            giveback_atr_norm: Some(0.0),
            time_since_peak_ms: Some(0),
            price_roc_short: Some(0.0),
            entry_age_secs: Some(0.0),
        };
        let j = serde_json::to_string(&f).expect("serialize");
        // atr_pct serialises as 0.0 (serde-json renders floats with decimal).
        // atr_pct 序列化為 0.0（serde-json 浮點帶小數點）。
        assert!(
            j.contains("\"atr_pct\":0.0"),
            "expected atr_pct:0.0 in {}",
            j
        );
    }

    #[test]
    fn test_exit_features_time_since_peak_stale_boundary() {
        // stale_peak_ms 預設 60_000ms（risk_config.phys_lock）——邊界等值值的
        // round-trip 必須完全還原。
        // Default stale_peak_ms is 60_000 (risk_config.phys_lock); boundary-equal
        // value must round-trip losslessly.
        let original = ExitFeatures {
            est_net_bps: Some(-25.0),
            peak_pnl_pct: 0.3,
            current_pnl_pct: 0.1,
            atr_pct: Some(0.5),
            giveback_atr_norm: Some(1.2),
            time_since_peak_ms: Some(60_000),
            price_roc_short: Some(-0.001),
            entry_age_secs: Some(120.0),
        };
        let j = serde_json::to_string(&original).expect("serialize");
        let decoded: ExitFeatures = serde_json::from_str(&j).expect("deserialize");
        assert_eq!(original, decoded, "round-trip must be lossless");
    }

    /// `PhysicalDecision::Hold` round-trips through serde without loss.
    /// PhysicalDecision::Hold 可經 serde 往返還原。
    #[test]
    fn test_physical_decision_hold_serde_round_trip() {
        let d = PhysicalDecision::Hold;
        let j = serde_json::to_string(&d).expect("ser");
        let back: PhysicalDecision = serde_json::from_str(&j).expect("de");
        assert_eq!(d, back);
    }
}
