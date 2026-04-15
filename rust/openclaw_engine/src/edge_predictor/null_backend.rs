//! Null backend — always returns `Err(NoModel)` to trigger fallback.
//! Null 後端 — 永遠返回 `Err(NoModel)` 以觸發 fallback。
//!
//! MODULE_NOTE (EN): Default backend compiled when the `edge_predictor_ort`
//!   feature is not enabled.
//!   Every `predict()` call returns `Err(PredictError::NoModel)`, which the
//!   gate logic (§7.3) catches and falls back to the existing shrinkage gate.
//!   Safe to ship to prod — behaves identically to "predictor disabled".
//! MODULE_NOTE (中): 預設後端（無 feature flag 啟用時）。所有 `predict()` 呼叫
//!   回傳 `Err(NoModel)`，gate 邏輯（§7.3）捕獲後 fallback 至現有 shrinkage。
//!   可安全部署 prod — 行為等同「預測器未啟用」。
//!
//! Used by tests and by the default cargo build. Stage 2 (ML-MIT) may still
//! use NullPredictor as a placeholder until the first ONNX artifact ships.
//! 測試與預設 cargo build 使用。Stage 2 可作為首個 ONNX artifact 交付前的占位。

use super::{now_unix_seconds, EdgePredictor, FeatureVectorV1, PredictError, Prediction};

/// Always-`Err(NoModel)` predictor. Self-describes as `"null-backend-v0"`.
/// 永 `Err(NoModel)` 預測器。
pub struct NullPredictor {
    /// Wallclock seconds when this NullPredictor was constructed.
    /// Used by age_seconds() so the gate can detect stale placeholder loads.
    /// 建構時的 wall-clock 秒數，供 age_seconds() 檢測陳舊占位。
    created_at_unix: u64,
}

impl NullPredictor {
    pub fn new() -> Self {
        Self {
            created_at_unix: now_unix_seconds(),
        }
    }
}

impl Default for NullPredictor {
    fn default() -> Self {
        Self::new()
    }
}

impl EdgePredictor for NullPredictor {
    fn predict(&self, _features: &FeatureVectorV1) -> Result<Prediction, PredictError> {
        Err(PredictError::NoModel)
    }

    fn age_seconds(&self) -> u64 {
        now_unix_seconds().saturating_sub(self.created_at_unix)
    }

    fn schema_hash(&self) -> &str {
        "null-backend"
    }

    fn definition_hash(&self) -> &str {
        "null-backend"
    }

    fn model_id(&self) -> &str {
        "null-backend-v0"
    }
}

// ============================================================
// Tests
// ============================================================
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_predict_always_returns_no_model() {
        let p = NullPredictor::new();
        let f = FeatureVectorV1::zeroed();
        match p.predict(&f) {
            Err(PredictError::NoModel) => {}
            other => panic!("expected NoModel, got {:?}", other),
        }
    }

    #[test]
    fn test_age_seconds_is_monotone_non_negative() {
        let p = NullPredictor::new();
        let a0 = p.age_seconds();
        let a1 = p.age_seconds();
        assert!(a1 >= a0);
    }

    #[test]
    fn test_model_id_and_hash_strings_stable() {
        let p = NullPredictor::new();
        assert_eq!(p.model_id(), "null-backend-v0");
        assert_eq!(p.schema_hash(), "null-backend");
        assert_eq!(p.definition_hash(), "null-backend");
    }
}
