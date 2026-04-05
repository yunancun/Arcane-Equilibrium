//! ML inference module — ONNX model management + Scorer + Kelly sizing.
//! ML 推理模組 — ONNX 模型管理 + 評分器 + Kelly 倉位管理。
//!
//! MODULE_NOTE (EN): Phase 2b-infra. Provides:
//!   - OnnxModelManager: ArcSwap-based hot-swappable ONNX model (ort crate, added later)
//!   - Scorer: 3-tier degradation (ONNX → rule-based → fixed confidence 0.5)
//!   - KellySizer: fractional Kelly position sizing with sample-size adjustment
//!   All designed for graceful absence — engine runs without ONNX model.
//! MODULE_NOTE (中): Phase 2b-infra。提供：
//!   - OnnxModelManager：基於 ArcSwap 的可熱交換 ONNX 模型
//!   - Scorer：三級降級��ONNX → 規則 → 固定 confidence 0.5）
//!   - KellySizer：帶樣本量調整的分數 Kelly 倉位管理
//!   所有設計支持優雅缺失 — 無 ONNX 模型時引擎正常運行。

pub mod kelly_sizer;
pub mod model_manager;
pub mod scorer;

/// Result of scoring a trading signal / 交易信號評分結果
#[derive(Debug, Clone)]
pub struct ScorerResult {
    /// Calibrated probability of profit (0.0-1.0) / 校準的獲利概率
    pub calibrated_prob: f64,
    /// Expected value in ATR units / 以 ATR 為單位的期望值
    pub expected_value: f64,
    /// Source tier (1=ONNX, 2=rule, 3=fixed) / 來源層級
    pub tier: u8,
    /// Model version if ONNX was used / ONNX 模���版本（如有使用）
    pub model_version: Option<String>,
}

impl Default for ScorerResult {
    fn default() -> Self {
        Self {
            calibrated_prob: 0.5,
            expected_value: 0.0,
            tier: 3, // fixed fallback
            model_version: None,
        }
    }
}
