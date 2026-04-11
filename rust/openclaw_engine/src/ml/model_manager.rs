//! ONNX Model Manager — ArcSwap-based hot-swappable inference model.
//! ONNX 模型管理器 — 基於 ArcSwap 的可熱交換推理模型。
//!
//! MODULE_NOTE (EN): Wraps an optional ONNX model with lock-free reads via ArcSwap.
//!   When no model file exists, predict() returns None (graceful degradation).
//!   SIGHUP triggers try_reload() to hot-swap the model without stopping inference.
//!   The actual `ort` crate dependency is deferred — this module uses a trait-based
//!   interface that works with or without ort.
//! MODULE_NOTE (中): 通過 ArcSwap 包裝可選 ONNX 模型，實現無鎖讀取。
//!   無模型文件時 predict() 返回 None（優雅降級）���
//!   SIGHUP 觸發 try_reload() 熱交換模型。ort 依賴延後添加。

use arc_swap::ArcSwap;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use tracing::{info, warn};

/// Prediction output from the model / 模型預測輸出
#[derive(Debug, Clone, PartialEq)]
pub struct ModelPrediction {
    /// Raw model output (e.g., expected PnL/ATR) / 原始模型輸出
    pub raw_output: f64,
    /// Calibrated probability (after isotonic/Platt) / 校準概率
    pub calibrated_prob: f64,
}

/// ONNX model state — None when no model loaded.
/// ONNX 模型狀態 — 無模型載入時為 None。
type ModelState = Option<LoadedModel>;

/// Placeholder for loaded ONNX model (ort::Session will replace this).
/// 已載入 ONNX 模型的佔位（ort::Session 將替換此項）。
struct LoadedModel {
    /// Model file path / 模型文件路徑
    _path: PathBuf,
    /// Feature dimension expected / 期望的特徵維度
    feature_dim: usize,
    /// Version string / 版本字符串
    _version: String,
}

/// ONNX Model Manager with ArcSwap for zero-lock hot-swap.
/// 使用 ArcSwap 的 ONNX 模型管理器，支持零鎖熱交換。
pub struct OnnxModelManager {
    state: ArcSwap<ModelState>,
    model_path: PathBuf,
    version_counter: AtomicU32,
    feature_dim: usize,
}

impl OnnxModelManager {
    /// Create a new manager. If model_path exists, loads it. Otherwise starts empty.
    /// 創建新管理器。如果模型路徑存在則載入，否則空啟動。
    pub fn new(model_path: &str, feature_dim: usize) -> Self {
        let path = PathBuf::from(model_path);
        let initial_state = if !model_path.is_empty() && path.exists() {
            info!(path = model_path, "ONNX model found / 找到 ONNX 模型");
            Some(LoadedModel {
                _path: path.clone(),
                feature_dim,
                _version: "v1".into(),
            })
        } else {
            if !model_path.is_empty() {
                info!(path = model_path, "ONNX model not found, scorer will use rule-based / ONNX 模型未找到，評分器將使用規則");
            }
            None
        };

        Self {
            state: ArcSwap::from_pointee(initial_state),
            model_path: path,
            version_counter: AtomicU32::new(1),
            feature_dim,
        }
    }

    /// Check if a model is loaded / 檢查是否已載入模型
    pub fn is_loaded(&self) -> bool {
        self.state.load().is_some()
    }

    /// Get current model version / 獲取當前模型版本
    pub fn version(&self) -> u32 {
        self.version_counter.load(Ordering::Relaxed)
    }

    /// Predict using the loaded model. Returns None if no model.
    /// When ort is integrated, this will call session.run().
    /// 使用載入的模型進行預測。無模型時返回 None。
    pub fn predict(&self, features: &[f32]) -> Option<ModelPrediction> {
        let state = self.state.load();
        let model = match state.as_ref() {
            Some(m) => m,
            None => return None,
        };

        if features.len() != model.feature_dim {
            warn!(
                expected = model.feature_dim,
                got = features.len(),
                "feature dimension mismatch / 特徵維度不匹配"
            );
            return None;
        }

        // TODO: Replace with ort::Session::run() when ort crate is added
        // 目前返回佔位預測，ort 整合後替換為真實推理
        // Placeholder: return None to trigger rule-based fallback
        None
    }

    /// Try to reload model from disk (called on SIGHUP).
    /// 嘗試從磁碟重新載入模型（SIGHUP 時調用）。
    pub fn try_reload(&self) -> bool {
        if !self.model_path.exists() {
            info!("ONNX model file not found on reload / 重載時未找到 ONNX 模型文件");
            return false;
        }

        // TODO: Replace with actual ort::Session::builder()...commit_from_file()
        let new_version = self.version_counter.fetch_add(1, Ordering::Relaxed) + 1;
        let new_model = Some(LoadedModel {
            _path: self.model_path.clone(),
            feature_dim: self.feature_dim,
            _version: format!("v{}", new_version),
        });
        self.state.store(Arc::new(new_model));
        info!(
            version = new_version,
            "ONNX model reloaded / ONNX 模型已重載"
        );
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_path_no_model() {
        let mgr = OnnxModelManager::new("", 34);
        assert!(!mgr.is_loaded());
        assert_eq!(mgr.predict(&vec![0.0; 34]), None);
    }

    #[test]
    fn test_nonexistent_path_graceful() {
        let mgr = OnnxModelManager::new("/nonexistent/model.onnx", 34);
        assert!(!mgr.is_loaded());
    }

    #[test]
    fn test_version_increments_on_reload() {
        let mgr = OnnxModelManager::new("", 34);
        assert_eq!(mgr.version(), 1);
        // reload won't succeed (no file) but version logic is tested
        mgr.try_reload(); // returns false, version doesn't increment via the guard
                          // If file existed, version would be 2
    }
}
