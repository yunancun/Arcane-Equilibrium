//! EDGE-P3-1 Realized Edge Predictor — Stage 0 module scaffold.
//! EDGE-P3-1 真實邊緣預測器 — Stage 0 模組骨架。
//!
//! MODULE_NOTE (EN): Per-strategy quantile LGBM edge predictor replacing the
//!   James-Stein `shrunk_bps`. This scaffold defines the `EdgePredictor` trait,
//!   `PredictError`, `Prediction`, `EdgePredictorStore` (per-strategy ArcSwap
//!   hot-reload per F9), and `PerEnginePredictors` (paper/demo/live isolation).
//!   Default build uses `null_backend` (always Err(NoModel) → falls back to
//!   shrinkage gate). Real backends (`tract_backend` / `ort_backend`) are
//!   feature-gated (`edge_predictor_tract` / `edge_predictor_ort`, mutually
//!   exclusive per F8) and ship empty stubs until Stage 2 (ML-MIT) lands the
//!   model artifact.
//! MODULE_NOTE (中): 逐策略 quantile LGBM 邊緣預測器，替代 James-Stein `shrunk_bps`。
//!   本骨架定義 `EdgePredictor` trait、錯誤型別、預測結果、`EdgePredictorStore`
//!   （per-strategy ArcSwap 熱重載，F9 guard discipline）、`PerEnginePredictors`
//!   （paper/demo/live 隔離）。預設 build 使用 `null_backend`（永遠 Err(NoModel)
//!   → fallback 至 shrinkage gate）。真實後端經 feature flag 門控，Stage 2 ML-MIT
//!   交付 ONNX 模型後啟用。
//!
//! Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4 §7

// F8 · Mutual-exclusion compile guard — guard against operator accidentally
// enabling both backends (60MB+ binary bloat + ambiguous runtime selection).
// F8 互斥編譯守則 — 防止 operator 同時啟用雙後端。
#[cfg(all(feature = "edge_predictor_tract", feature = "edge_predictor_ort"))]
compile_error!(
    "edge_predictor_tract and edge_predictor_ort are mutually exclusive; \
     pick exactly one backend to avoid +63MB binary bloat and ambiguous \
     runtime selection (spec §7.1 F8)"
);

pub mod feature_builder;
pub mod features;
pub mod gate;
pub mod null_backend;
pub mod rearrangement;

// Stage 2 backends — empty stubs today, real impl when ML-MIT ships artifact.
// Stage 2 後端 — 當前為空殼，ML-MIT 交付 artifact 時補實現。
#[cfg(feature = "edge_predictor_tract")]
pub mod tract_backend;
#[cfg(feature = "edge_predictor_ort")]
pub mod ort_backend;

use std::collections::HashMap;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};

use arc_swap::ArcSwap;
use parking_lot::RwLock;

pub use features::FeatureVectorV1;

/// Prediction output — three quantiles (q10, q50, q90) in bps.
/// 預測輸出 — 三個分位（q10/q50/q90），單位 bps。
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Prediction {
    pub q10: f32,
    pub q50: f32,
    pub q90: f32,
}

impl Prediction {
    /// Valid if all quantiles are finite and monotone non-decreasing.
    /// 所有分位有限且單調不降則 valid。
    pub fn is_valid(&self) -> bool {
        self.q10.is_finite()
            && self.q50.is_finite()
            && self.q90.is_finite()
            && self.q10 <= self.q50
            && self.q50 <= self.q90
    }
}

/// Errors from `EdgePredictor::predict`.
/// 預測器錯誤類型。
#[derive(Debug, Clone, thiserror::Error)]
pub enum PredictError {
    /// No model loaded for this strategy — fall back to shrinkage gate.
    /// 策略無 model 載入 — fallback 至 shrinkage。
    #[error("no model loaded for strategy")]
    NoModel,

    /// Feature schema hash mismatch — model expects a different feature set.
    /// Feature schema hash 不匹配 — 模型期望不同的 feature 集合。
    #[error("feature schema hash mismatch: expected={expected}, got={got}")]
    SchemaHashMismatch { expected: String, got: String },

    /// Feature definition hash mismatch — same features but changed formula/TF.
    /// Feature definition hash 不匹配 — 相同 feature 但公式/TF 變更。
    #[error("feature definition hash mismatch: expected={expected}, got={got}")]
    DefinitionHashMismatch { expected: String, got: String },

    /// Runtime inference failure (ONNX backend error, NaN output, etc).
    /// 推理運行時失敗（ONNX backend error / NaN 輸出等）。
    #[error("inference failed: {0}")]
    InferenceFailed(String),
}

/// `EdgePredictor` trait — per-strategy predictor with liveness + schema gates.
/// `EdgePredictor` trait — 逐策略預測器，帶存活期 + schema 門。
pub trait EdgePredictor: Send + Sync {
    /// Run inference on the feature vector.
    /// 在 feature 向量上運行推理。
    fn predict(&self, features: &FeatureVectorV1) -> Result<Prediction, PredictError>;

    /// Age since model artifact was created (not loaded time).
    /// 模型 artifact 創建至今的秒數（非載入時間）。
    fn age_seconds(&self) -> u64;

    /// Feature schema hash this model was trained against (§3.3).
    /// 本模型訓練時使用的 feature schema hash（§3.3）。
    fn schema_hash(&self) -> &str;

    /// Feature definition hash (canonical formula signature).
    /// Feature definition hash（公式簽名）。
    fn definition_hash(&self) -> &str;

    /// Model identifier for logging (e.g., "ma_crossover-v3-2026-04-20").
    /// 模型識別碼，供日誌使用。
    fn model_id(&self) -> &str;
}

/// Debug-safe newtype around `Arc<dyn EdgePredictor>` so it can be shipped
/// through `PipelineCommand` (which derives `Debug`). The wrapper's Debug
/// impl prints model_id + schema_hash instead of the opaque trait object.
/// Debug-safe 包裝 `Arc<dyn EdgePredictor>`，供 `PipelineCommand`（derive Debug）
/// 使用。Debug 輸出 model_id 與 schema_hash 而非 opaque trait object。
#[derive(Clone)]
pub struct BoxedEdgePredictor(pub Arc<dyn EdgePredictor + Send + Sync>);

impl BoxedEdgePredictor {
    pub fn new(p: Arc<dyn EdgePredictor + Send + Sync>) -> Self {
        Self(p)
    }
    pub fn into_arc(self) -> Arc<dyn EdgePredictor + Send + Sync> {
        self.0
    }
}

impl std::fmt::Debug for BoxedEdgePredictor {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("BoxedEdgePredictor")
            .field("model_id", &self.0.model_id())
            .field("schema_hash", &self.0.schema_hash())
            .field("definition_hash", &self.0.definition_hash())
            .field("age_seconds", &self.0.age_seconds())
            .finish()
    }
}

/// Per-strategy predictor store with ArcSwap hot-reload (F9 guard discipline).
/// 逐策略預測器容器，ArcSwap 熱重載（F9 guard discipline）。
///
/// F9 pattern: `load_for()` takes read lock, clones inner Arc<ArcSwap>, drops
/// read guard immediately, then lock-free ArcSwap read. Mid-predict swap is
/// safe — old Arc continues serving in-flight calls until they complete.
/// F9 模式：read lock → clone → drop → ArcSwap 無鎖讀。推理中熱換安全。
pub struct EdgePredictorStore {
    inner: RwLock<
        HashMap<String, Arc<ArcSwap<Option<Arc<dyn EdgePredictor + Send + Sync>>>>>,
    >,
}

impl EdgePredictorStore {
    pub fn new() -> Self {
        Self {
            inner: RwLock::new(HashMap::new()),
        }
    }

    /// Load the current predictor for `strategy` (lock-free once Arc cloned).
    /// F9 discipline: hold read guard only long enough to clone the inner Arc,
    /// then drop it before ArcSwap.load_full() to avoid blocking add-strategy
    /// writers during inference.
    ///
    /// 按 F9 discipline 讀取當前預測器，read guard 只拿到 clone Arc 即釋放。
    pub fn load_for(
        &self,
        strategy: &str,
    ) -> Option<Arc<dyn EdgePredictor + Send + Sync>> {
        let arc_swap = {
            let guard = self.inner.read();
            guard.get(strategy).cloned()?
            // guard dropped here
        };
        arc_swap.load_full().as_ref().clone()
    }

    /// Register a new strategy slot (initialised with no model loaded).
    /// 註冊新策略槽（初始無 model）。
    pub fn register(&self, strategy: &str) {
        let mut guard = self.inner.write();
        guard
            .entry(strategy.to_string())
            .or_insert_with(|| Arc::new(ArcSwap::from_pointee(None)));
    }

    /// Swap in a new predictor for `strategy` — lock-free for concurrent readers.
    /// 為策略熱換新預測器 — 對讀者無鎖。
    pub fn swap(
        &self,
        strategy: &str,
        predictor: Arc<dyn EdgePredictor + Send + Sync>,
    ) {
        self.register(strategy);
        let guard = self.inner.read();
        if let Some(slot) = guard.get(strategy) {
            slot.store(Arc::new(Some(predictor)));
        }
    }

    /// Clear the predictor for `strategy` (subsequent load_for returns None).
    /// 清除策略的預測器（後續 load_for 返回 None）。
    pub fn clear(&self, strategy: &str) {
        let guard = self.inner.read();
        if let Some(slot) = guard.get(strategy) {
            slot.store(Arc::new(None));
        }
    }

    /// Kill-switch: clear every registered strategy's predictor. Slots remain
    /// registered (so `load_for` still returns None predictably); operator
    /// intent is "stop using any model", not "forget which strategies exist".
    /// Returns the number of slots cleared, useful for IPC response.
    /// Kill-switch：清空每個已註冊策略的 predictor。槽位保留，僅清除 arc-swapped
    /// 模型。返回清除數量供 IPC 回報。
    pub fn clear_all(&self) -> usize {
        let guard = self.inner.read();
        let n = guard.len();
        for slot in guard.values() {
            slot.store(Arc::new(None));
        }
        n
    }

    /// Count of registered strategy slots (loaded or not).
    /// 已註冊的策略槽數量。
    pub fn registered_count(&self) -> usize {
        self.inner.read().len()
    }

    /// Count of slots currently holding a loaded predictor.
    /// 當前實際載入預測器的槽數量。
    pub fn loaded_count(&self) -> usize {
        let guard = self.inner.read();
        guard
            .values()
            .filter(|slot| slot.load().is_some())
            .count()
    }
}

impl Default for EdgePredictorStore {
    fn default() -> Self {
        Self::new()
    }
}

/// Per-engine predictor stores — paper / demo / live isolation parallels
/// `PerEngineRiskStores`. Each engine gets its own ArcSwap map so Paper
/// can promote a new model while Demo/Live stay on the old artifact.
/// 逐引擎預測器容器，平行於 `PerEngineRiskStores`。各引擎獨立 ArcSwap map，
/// Paper 熱換新 model 時不影響 Demo/Live。
pub struct PerEnginePredictors {
    pub paper: Arc<EdgePredictorStore>,
    pub demo: Arc<EdgePredictorStore>,
    pub live: Arc<EdgePredictorStore>,
}

impl PerEnginePredictors {
    pub fn new() -> Self {
        Self {
            paper: Arc::new(EdgePredictorStore::new()),
            demo: Arc::new(EdgePredictorStore::new()),
            live: Arc::new(EdgePredictorStore::new()),
        }
    }
}

impl Default for PerEnginePredictors {
    fn default() -> Self {
        Self::new()
    }
}

/// EDGE-P3-1 Step 7b: Load a predictor from an on-disk ONNX artifact. Today
/// this is a stub — no backend is compiled in (both `edge_predictor_tract`
/// and `edge_predictor_ort` feature flags are empty pending ML-MIT #26). The
/// stub unconditionally returns `Err("onnx_loader_not_wired")` so the
/// `ReloadEdgePredictor` IPC handler can exercise its happy and error paths
/// without a real model file, and so `engine_capabilities.ipc_methods.
/// reload_edge_predictor` can stay `False` honestly. When #26 lands, swap
/// this body for the feature-flag-gated tract/ort loader and the flag flips
/// `True` at the same time.
/// EDGE-P3-1 Step 7b：從磁碟 ONNX artifact 載入 predictor 的存根。當前無後端
/// 編入（tract/ort feature flag 皆空，待 ML-MIT #26）；存根回 Err，IPC handler
/// 仍可跑通 happy/error 路徑，capability flag 誠實保持 False。#26 交付後換為
/// feature-flag gated 的實作並同步翻 flag。
pub fn load_predictor_from_path(
    path: &std::path::Path,
) -> Result<Arc<dyn EdgePredictor + Send + Sync>, String> {
    if !path.exists() {
        return Err(format!(
            "onnx_loader_not_wired: path does not exist ({}) — awaiting ML-MIT #26 \
             / 載入器未接線：路徑不存在，待 ML-MIT #26",
            path.display()
        ));
    }
    Err(format!(
        "onnx_loader_not_wired: awaiting ML-MIT #26 first ONNX artifact \
         (path={}) / 載入器未接線，待 ML-MIT #26 首個 ONNX artifact",
        path.display()
    ))
}

/// Helper — current unix epoch seconds (used by backends to compute age).
/// 工具函數 — 當前 unix epoch 秒數（後端計算 age 用）。
pub(crate) fn now_unix_seconds() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

// ============================================================
// Tests
// ============================================================
#[cfg(test)]
mod tests {
    use super::*;
    use crate::edge_predictor::null_backend::NullPredictor;

    #[test]
    fn test_prediction_is_valid_monotone() {
        let p = Prediction { q10: -10.0, q50: 5.0, q90: 20.0 };
        assert!(p.is_valid());
    }

    #[test]
    fn test_prediction_invalid_crossing_quantiles() {
        let p = Prediction { q10: 20.0, q50: 5.0, q90: 30.0 };
        assert!(!p.is_valid());
    }

    #[test]
    fn test_prediction_invalid_nan() {
        let p = Prediction { q10: 0.0, q50: f32::NAN, q90: 10.0 };
        assert!(!p.is_valid());
    }

    #[test]
    fn test_store_new_is_empty() {
        let store = EdgePredictorStore::new();
        assert_eq!(store.registered_count(), 0);
        assert_eq!(store.loaded_count(), 0);
        assert!(store.load_for("ma_crossover").is_none());
    }

    #[test]
    fn test_store_register_increments_registered_not_loaded() {
        let store = EdgePredictorStore::new();
        store.register("ma_crossover");
        store.register("bb_breakout");
        assert_eq!(store.registered_count(), 2);
        assert_eq!(store.loaded_count(), 0);
        assert!(store.load_for("ma_crossover").is_none());
    }

    #[test]
    fn test_store_swap_makes_load_for_return_some() {
        let store = EdgePredictorStore::new();
        let p = Arc::new(NullPredictor::new());
        store.swap("ma_crossover", p);
        assert_eq!(store.loaded_count(), 1);
        assert!(store.load_for("ma_crossover").is_some());
    }

    #[test]
    fn test_store_clear_removes_loaded_but_keeps_registered() {
        let store = EdgePredictorStore::new();
        let p = Arc::new(NullPredictor::new());
        store.swap("ma_crossover", p);
        store.clear("ma_crossover");
        assert_eq!(store.registered_count(), 1);
        assert_eq!(store.loaded_count(), 0);
        assert!(store.load_for("ma_crossover").is_none());
    }

    #[test]
    fn test_store_swap_is_idempotent_for_register() {
        let store = EdgePredictorStore::new();
        store.register("funding_arb");
        store.register("funding_arb");
        store.swap("funding_arb", Arc::new(NullPredictor::new()));
        assert_eq!(store.registered_count(), 1);
    }

    #[test]
    fn test_per_engine_predictors_three_independent_stores() {
        let pep = PerEnginePredictors::new();
        pep.paper.register("ma_crossover");
        assert_eq!(pep.paper.registered_count(), 1);
        assert_eq!(pep.demo.registered_count(), 0);
        assert_eq!(pep.live.registered_count(), 0);
    }

    #[test]
    fn test_per_engine_swap_isolation() {
        let pep = PerEnginePredictors::new();
        pep.paper.swap("ma_crossover", Arc::new(NullPredictor::new()));
        assert_eq!(pep.paper.loaded_count(), 1);
        assert_eq!(pep.demo.loaded_count(), 0);
        assert_eq!(pep.live.loaded_count(), 0);
    }

    #[test]
    fn test_predict_error_messages_contain_context() {
        let e = PredictError::SchemaHashMismatch {
            expected: "abc123".into(),
            got: "def456".into(),
        };
        let msg = format!("{}", e);
        assert!(msg.contains("abc123"));
        assert!(msg.contains("def456"));
    }
}
