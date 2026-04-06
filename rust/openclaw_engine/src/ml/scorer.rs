//! 3-tier Scorer — ONNX → rule-based → fixed confidence degradation.
//! 三級評分器 — ONNX → 規則 → 固定 confidence 降級。
//!
//! MODULE_NOTE (EN): Wraps OnnxModelManager with fallback tiers per 0b-14 spec:
//!   Tier 1: ONNX model available → model.predict(features) → calibrated_prob
//!   Tier 2: No ONNX → use signal confidence directly (rule-based)
//!   Tier 3: Rule fails → fixed confidence = 0.5
//!   Never blocks. Never panics. Always returns a ScorerResult.
//! MODULE_NOTE (中): 包裝 OnnxModelManager，按 0b-14 規格提供降級層級。

use super::model_manager::OnnxModelManager;
use super::ScorerResult;
use std::sync::Arc;
use tracing::debug;

/// 3-tier Scorer with graceful degradation.
/// 帶優雅降級的三級評分器。
pub struct Scorer {
    model_manager: Option<Arc<OnnxModelManager>>,
    enabled: bool,
}

impl Scorer {
    /// Create with an optional model manager.
    /// 使用可選的模型管理器創建。
    pub fn new(model_manager: Option<Arc<OnnxModelManager>>, enabled: bool) -> Self {
        Self {
            model_manager,
            enabled,
        }
    }

    /// Create a disabled scorer (always returns rule-based).
    /// 創建禁用的評分器（總是返回規則評分）。
    pub fn disabled() -> Self {
        Self {
            model_manager: None,
            enabled: false,
        }
    }

    /// Score a signal using the 3-tier degradation chain.
    /// 使用三級降級鏈評分信號。
    ///
    /// - `features`: 34-dim feature vector from FeatureSnapshot
    /// - `signal_confidence`: raw confidence from signal engine (0.0-1.0)
    /// - `signal_edge_bps`: expected edge in basis points
    pub fn score(
        &self,
        features: &[f32],
        signal_confidence: f64,
        signal_edge_bps: f64,
    ) -> ScorerResult {
        if !self.enabled {
            return self.rule_based(signal_confidence, signal_edge_bps);
        }

        // Tier 1: ONNX model
        if let Some(ref mgr) = self.model_manager {
            if let Some(pred) = mgr.predict(features) {
                debug!(prob = pred.calibrated_prob, tier = 1, "ONNX score");
                return ScorerResult {
                    calibrated_prob: pred.calibrated_prob.clamp(0.0, 1.0),
                    expected_value: pred.raw_output,
                    tier: 1,
                    model_version: Some(format!("v{}", mgr.version())),
                };
            }
        }

        // Tier 2: Rule-based (use signal confidence)
        self.rule_based(signal_confidence, signal_edge_bps)
    }

    /// Tier 2: Rule-based scoring using signal confidence.
    /// 第 2 層：使用信號 confidence 的規則評分。
    fn rule_based(&self, signal_confidence: f64, signal_edge_bps: f64) -> ScorerResult {
        if signal_confidence > 0.0 && signal_confidence <= 1.0 {
            let ev = signal_edge_bps / 10_000.0; // convert bps to fraction
            return ScorerResult {
                calibrated_prob: signal_confidence,
                expected_value: ev,
                tier: 2,
                model_version: None,
            };
        }

        // Tier 3: Fixed fallback
        ScorerResult::default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_disabled_returns_rule_based() {
        let scorer = Scorer::disabled();
        let result = scorer.score(&[0.0; 34], 0.75, 50.0);
        assert_eq!(result.tier, 2);
        assert!((result.calibrated_prob - 0.75).abs() < 1e-10);
    }

    #[test]
    fn test_no_model_falls_to_rule() {
        let scorer = Scorer::new(None, true);
        let result = scorer.score(&[0.0; 34], 0.8, 30.0);
        assert_eq!(result.tier, 2);
        assert!((result.calibrated_prob - 0.8).abs() < 1e-10);
    }

    #[test]
    fn test_invalid_confidence_falls_to_fixed() {
        let scorer = Scorer::new(None, true);
        let result = scorer.score(&[0.0; 34], 0.0, 0.0);
        assert_eq!(result.tier, 3);
        assert!((result.calibrated_prob - 0.5).abs() < 1e-10);
    }

    #[test]
    fn test_with_model_manager_no_file() {
        let mgr = Arc::new(OnnxModelManager::new("", 34));
        let scorer = Scorer::new(Some(mgr), true);
        // No model loaded → falls to tier 2
        let result = scorer.score(&[0.0; 34], 0.6, 20.0);
        assert_eq!(result.tier, 2);
    }
}
