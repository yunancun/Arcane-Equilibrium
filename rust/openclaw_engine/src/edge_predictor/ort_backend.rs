//! ort (ONNX Runtime 1.24) backend — quantile trio predictor loader (Stage 2).
//! ort (ONNX Runtime 1.24) 後端 — 分位三重預測器載入器（Stage 2）。
//!
//! MODULE_NOTE (EN): Gated behind `edge_predictor_ort` feature. Loads a trio
//!   of LightGBM-exported ONNX files (q10/q50/q90) from disk via `ort::Session`,
//!   validates `metadata_props` against the compile-time `FEATURE_NAMES_V1`
//!   schema hash, and wraps the three sessions into a single `EdgePredictor`
//!   impl that runs inference + monotone rearrangement per call. Trio is
//!   loaded through the q50 path as anchor; q10/q90 sibling filenames are
//!   derived by substring-replace so one IPC-supplied path pins the entire
//!   training vintage.
//!
//!   Why ort and not tract: tract 0.21 implements TreeEnsembleClassifier but
//!   not TreeEnsembleRegressor (ai.onnx.ml opset), and LightGBM's onnxmltools
//!   converter emits TreeEnsembleRegressor for quantile regression. ort wraps
//!   the full Microsoft ONNX Runtime which supports the entire ai.onnx.ml
//!   op set. Cost is +~20MB libonnxruntime dylib bundled next to the binary
//!   (via ort's download-binaries + copy-dylibs default features).
//!
//!   Why three separate model files instead of one multi-output model:
//!   the Python training pipeline fits q10/q50/q90 as independent LightGBM
//!   quantile boosters and exports each via `onnxmltools.convert_lightgbm`
//!   (no multi-output regressor). Combining them into one ONNX graph would
//!   have required hand-rolling an `onnx` graph builder — not worth the
//!   complexity when three tiny inferences cost ~microseconds each.
//!
//!   ort's `Session::run` takes `&mut self`, so each quantile session lives
//!   behind a `Mutex<Session>` inside `OrtPredictor`. Three tiny tree-ensemble
//!   inferences serialize safely — contention is microsecond-scale.
//!
//! MODULE_NOTE (中): 經 `edge_predictor_ort` feature 門控。以 `ort::Session` 載入
//!   LightGBM 匯出的 q10/q50/q90 ONNX 三檔，以 metadata_props 對
//!   `FEATURE_NAMES_V1` 編譯期 hash 校驗；以 q50 路徑為錨，兄弟檔名由
//!   `_q50_` → `_q10_`/`_q90_` 推導，單一 IPC 路徑鎖定整個訓練批次。
//!   ort `Session::run` 需 `&mut self`，以 `Mutex<Session>` 包裝串行化；
//!   三個微型樹集成推理微秒級，鎖競爭可忽略。
//!
//! Spec: docs/references/2026-04-15--edge_predictor_spec.md v1.4 §7.1 / §7.3

use std::path::{Path, PathBuf};

use ort::session::{builder::GraphOptimizationLevel, Session};
use ort::value::Tensor;
use parking_lot::Mutex;

use super::features::{feature_schema_hash, FEATURE_SCHEMA_VERSION};
use super::rearrangement::enforce_monotone;
use super::{EdgePredictor, FeatureVectorV1, PredictError, Prediction};

// ── Owned metadata keys (MUST mirror program_code/ml_training/onnx_exporter.py).
// ── 擁有的 metadata key（必須鏡像 Python onnx_exporter.py）。
const META_SCHEMA_VERSION: &str = "edge_p3_schema_version";
const META_SCHEMA_HASH: &str = "edge_p3_feature_schema_hash";
const META_DEFINITION_HASH: &str = "edge_p3_feature_definition_hash";
const META_ENGINE_MODE: &str = "edge_p3_engine_mode";
const META_STRATEGY_NAME: &str = "edge_p3_strategy_name";
const META_QUANTILE: &str = "edge_p3_quantile";
const META_TRAIN_DATE: &str = "edge_p3_train_date";
const META_MODEL_ID: &str = "edge_p3_model_id";
const META_N_FEATURES: &str = "edge_p3_n_features";

/// Parsed metadata_props snapshot — all keys required; missing → Err.
/// 解析後的 metadata_props 快照；缺 key 即 Err。
#[derive(Debug, Clone)]
struct OnnxMetadata {
    schema_version: String,
    schema_hash: String,
    definition_hash: String,
    engine_mode: String,
    strategy_name: String,
    quantile: String,
    train_date: String,
    model_id: String,
    n_features: usize,
}

fn extract_metadata(session: &Session, path: &Path) -> Result<OnnxMetadata, String> {
    let meta = session
        .metadata()
        .map_err(|e| format!("session.metadata() failed for {}: {}", path.display(), e))?;
    let get = |k: &str| -> Result<String, String> {
        meta.custom(k).ok_or_else(|| {
            format!(
                "ONNX artifact {} missing metadata key '{}' — re-export with \
                 current onnx_exporter.py (stamps EDGE-P3-1 frozen keys) \
                 / 缺少 metadata key '{}'，需用新版 onnx_exporter 重新匯出",
                path.display(),
                k,
                k
            )
        })
    };
    let n_features_str = get(META_N_FEATURES)?;
    let n_features: usize = n_features_str.parse().map_err(|e| {
        format!(
            "invalid {} value {:?}: {} / {} 無法解析",
            META_N_FEATURES, n_features_str, e, META_N_FEATURES
        )
    })?;
    Ok(OnnxMetadata {
        schema_version: get(META_SCHEMA_VERSION)?,
        schema_hash: get(META_SCHEMA_HASH)?,
        definition_hash: get(META_DEFINITION_HASH)?,
        engine_mode: get(META_ENGINE_MODE)?,
        strategy_name: get(META_STRATEGY_NAME)?,
        quantile: get(META_QUANTILE)?,
        train_date: get(META_TRAIN_DATE)?,
        model_id: get(META_MODEL_ID)?,
        n_features,
    })
}

/// Default input-tensor name used by onnxmltools.convert_lightgbm. Pull by
/// this first; if the session exposes a different name (exporter drift),
/// fall through to the first declared input.
/// onnxmltools.convert_lightgbm 的預設輸入 tensor 名；若匯出器命名漂移則退回
/// 首個輸入。
const ONNX_INPUT_NAME: &str = "input";

/// Single-quantile predictor — owns one `ort::Session` + its metadata.
/// Session lives behind `Mutex` because `Session::run` requires `&mut self`.
/// 單一分位預測器 — 持有一個 `ort::Session` 與其 metadata。因 ort
/// `Session::run` 需 `&mut self`，用 Mutex 包裝供 Arc<dyn EdgePredictor> 串行化。
pub(crate) struct OrtPredictor {
    meta: OnnxMetadata,
    input_name: String,
    session: Mutex<Session>,
}

impl OrtPredictor {
    fn load(path: &Path) -> Result<Self, String> {
        let session = Session::builder()
            .map_err(|e| format!("ort Session::builder(): {}", e))?
            .with_optimization_level(GraphOptimizationLevel::Level3)
            .map_err(|e| format!("with_optimization_level: {}", e))?
            .commit_from_file(path)
            .map_err(|e| {
                format!(
                    "ort commit_from_file({}) failed: {} / ort 載入失敗",
                    path.display(),
                    e
                )
            })?;
        let meta = extract_metadata(&session, path)?;

        // Rust compile-time FEATURE_NAMES_V1 hash is authoritative. Artifact
        // trained against a drifted feature set → reject loud rather than
        // serve silently wrong predictions.
        // Rust 編譯期 hash 為準；artifact 漂移即拒，不允許靜默錯配。
        let expected_schema = feature_schema_hash();
        if meta.schema_hash != expected_schema {
            return Err(format!(
                "schema_hash mismatch: artifact={} runtime={} (path={}) \
                 / schema_hash 不匹配，模型與 Rust 編譯期不一致",
                meta.schema_hash,
                expected_schema,
                path.display()
            ));
        }
        if meta.schema_version != FEATURE_SCHEMA_VERSION {
            return Err(format!(
                "schema_version mismatch: artifact={} runtime={}",
                meta.schema_version, FEATURE_SCHEMA_VERSION
            ));
        }
        if meta.n_features != FeatureVectorV1::DIM {
            return Err(format!(
                "n_features mismatch: artifact={} runtime={}",
                meta.n_features,
                FeatureVectorV1::DIM
            ));
        }

        // Resolve input name once at load (not per-tick) so we survive
        // exporter drift that renames "input" → "float_input" etc.
        // 載入時解析一次輸入名，躲過匯出器改名。
        let inputs = session.inputs();
        let input_name = inputs
            .iter()
            .find(|o| o.name() == ONNX_INPUT_NAME)
            .map(|o| o.name().to_string())
            .or_else(|| inputs.first().map(|o| o.name().to_string()))
            .ok_or_else(|| {
                format!(
                    "session has zero inputs — malformed ONNX graph at {} \
                     / session 無輸入 tensor",
                    path.display()
                )
            })?;

        Ok(Self {
            meta,
            input_name,
            session: Mutex::new(session),
        })
    }

    fn predict_scalar(&self, features: &[f32; FeatureVectorV1::DIM]) -> Result<f32, String> {
        // Build single-row [1, DIM] f32 tensor. Shape vec<i64> matches the
        // onnxmltools-exported LightGBM graph's declared input shape.
        // 建 [1, DIM] f32 tensor；shape 與 onnxmltools 匯出時宣告的一致。
        let shape = vec![1_i64, FeatureVectorV1::DIM as i64];
        let tensor = Tensor::from_array((shape, features.to_vec()))
            .map_err(|e| format!("Tensor::from_array: {}", e))?;

        // Session::run takes &mut self — hold the lock through output extraction
        // because SessionOutputs borrows from the session. LightGBM regressor
        // emits its main tensor under "variable" (onnxmltools default naming);
        // fall through to the first output for exporter-name drift — single-
        // output regressor has only one tensor anyway.
        // Session::run 需 &mut self；SessionOutputs 借用 session，故鎖需延續
        // 至 extract 完成。LightGBM regressor 主要輸出為 "variable"，命名漂移
        // 時退回首個輸出。
        let mut session = self.session.lock();
        let outputs = session
            .run(ort::inputs![self.input_name.as_str() => tensor])
            .map_err(|e| format!("ort run: {}", e))?;

        let scalar = if let Some(output) = outputs.get("variable") {
            let view = output
                .try_extract_array::<f32>()
                .map_err(|e| format!("output try_extract_array::<f32>: {}", e))?;
            view.iter().next().copied()
        } else if let Some(output) = outputs.values().next() {
            let view = output
                .try_extract_array::<f32>()
                .map_err(|e| format!("output try_extract_array::<f32>: {}", e))?;
            view.iter().next().copied()
        } else {
            return Err("ort outputs empty".to_string());
        };
        scalar.ok_or_else(|| "output tensor empty".to_string())
    }
}

/// Trio predictor — q10 + q50 + q90 loaded as a single logical unit.
/// Implements `EdgePredictor` by running all three inferences then
/// `enforce_monotone` per §7.3 Step 5 so the gate never sees crossing quantiles.
/// 三重預測器 — q10/q50/q90 作為邏輯單元載入；實作 `EdgePredictor` 時先跑三次
/// 推理再跑 `enforce_monotone`，gate 永遠不會看到 quantile crossing。
pub struct OnnxTrioPredictor {
    q10: OrtPredictor,
    q50: OrtPredictor,
    q90: OrtPredictor,
    // Trio-identity fields (all three agree by construction — verified in load).
    // 三重身分欄位（載入時驗證三者一致）。
    schema_hash: String,
    definition_hash: String,
    model_id: String,
    // Age anchor — seconds since train_date 00:00 UTC, computed on every call
    // so the gate sees real-time staleness rather than a frozen-at-load value.
    // Age 錨點 — train_date 00:00 UTC 至今秒數，每次調用實時計算。
    train_date_unix: u64,
}

impl OnnxTrioPredictor {
    /// Load a trio from the q50 artifact path. q10/q90 sibling filenames are
    /// derived by substring replace (`_q50_` → `_q10_`/`_q90_`). All three
    /// artifacts must agree on schema_hash / definition_hash / strategy_name /
    /// engine_mode / train_date or load fails — never serve a mixed-vintage
    /// trio to the gate.
    /// 以 q50 artifact 路徑載入三重。兄弟檔名由 `_q50_` 替換推導。三個 artifact
    /// 必須在 schema / strategy / engine_mode / train_date 一致，否則拒載入。
    pub fn load_from_q50_path(q50_path: &Path) -> Result<Self, String> {
        let q10_path = derive_sibling_path(q50_path, "_q50_", "_q10_")?;
        let q90_path = derive_sibling_path(q50_path, "_q50_", "_q90_")?;

        let q50 = OrtPredictor::load(q50_path)
            .map_err(|e| format!("load q50 ({}): {}", q50_path.display(), e))?;
        let q10 = OrtPredictor::load(&q10_path)
            .map_err(|e| format!("load q10 ({}): {}", q10_path.display(), e))?;
        let q90 = OrtPredictor::load(&q90_path)
            .map_err(|e| format!("load q90 ({}): {}", q90_path.display(), e))?;

        verify_trio_aligned(&q10.meta, &q50.meta, &q90.meta)?;
        verify_quantile_tags(&q10.meta, &q50.meta, &q90.meta)?;

        let schema_hash = q50.meta.schema_hash.clone();
        let definition_hash = q50.meta.definition_hash.clone();
        let model_id = q50.meta.model_id.clone();
        let train_date_unix = parse_train_date_unix(&q50.meta.train_date);

        Ok(Self {
            q10,
            q50,
            q90,
            schema_hash,
            definition_hash,
            model_id,
            train_date_unix,
        })
    }
}

fn derive_sibling_path(base: &Path, from: &str, to: &str) -> Result<PathBuf, String> {
    let name = base.file_name().and_then(|s| s.to_str()).ok_or_else(|| {
        format!(
            "path {} has no utf-8 file_name / 路徑無 utf-8 檔名",
            base.display()
        )
    })?;
    if !name.contains(from) {
        return Err(format!(
            "filename '{}' missing marker '{}' — can't derive sibling trio paths \
             (expected convention `..._q50_...onnx`) \
             / 檔名缺 '{}' 標記無法推導兄弟路徑",
            name, from, from
        ));
    }
    let new_name = name.replace(from, to);
    let parent = base.parent().unwrap_or_else(|| Path::new(""));
    Ok(parent.join(new_name))
}

fn verify_trio_aligned(
    q10: &OnnxMetadata,
    q50: &OnnxMetadata,
    q90: &OnnxMetadata,
) -> Result<(), String> {
    macro_rules! trio_same {
        ($field:ident) => {
            if q10.$field != q50.$field || q50.$field != q90.$field {
                return Err(format!(
                    "trio mismatch on {}: q10={:?} q50={:?} q90={:?} \
                     / 三重 {} 不一致",
                    stringify!($field),
                    q10.$field,
                    q50.$field,
                    q90.$field,
                    stringify!($field),
                ));
            }
        };
    }
    trio_same!(schema_version);
    trio_same!(schema_hash);
    trio_same!(definition_hash);
    trio_same!(engine_mode);
    trio_same!(strategy_name);
    trio_same!(train_date);
    trio_same!(n_features);
    Ok(())
}

fn verify_quantile_tags(
    q10: &OnnxMetadata,
    q50: &OnnxMetadata,
    q90: &OnnxMetadata,
) -> Result<(), String> {
    for (want, got, role) in [
        ("q10", q10.quantile.as_str(), "q10 slot"),
        ("q50", q50.quantile.as_str(), "q50 slot"),
        ("q90", q90.quantile.as_str(), "q90 slot"),
    ] {
        if want != got {
            return Err(format!(
                "{} holds wrong quantile artifact (tag={}) / {} 分位標記錯配",
                role, got, role
            ));
        }
    }
    Ok(())
}

fn parse_train_date_unix(s: &str) -> u64 {
    // "YYYY-MM-DD" → unix epoch of 00:00 UTC that day. Parse failure returns
    // 0 so age_seconds() yields a huge value and Invariant #11 (staleness)
    // gates out the predictor loud rather than silently looking fresh.
    // 解析失敗回 0 → age_seconds() 超大 → 觸發 #11 staleness 門；絕不靜默看起來新。
    chrono::NaiveDate::parse_from_str(s, "%Y-%m-%d")
        .ok()
        .and_then(|d| d.and_hms_opt(0, 0, 0))
        .map(|dt| dt.and_utc().timestamp().max(0) as u64)
        .unwrap_or(0)
}

impl EdgePredictor for OnnxTrioPredictor {
    fn predict(&self, features: &FeatureVectorV1) -> Result<Prediction, PredictError> {
        // Invariant #12 — NaN/Inf/out-of-range → fail-closed before inference.
        // Invariant #12 — NaN/Inf/超界 → 推理前 fail-closed。
        if !features.all_in_range() {
            return Err(PredictError::InferenceFailed(
                "feature vector failed Invariant #12 sanity check \
                 (NaN/Inf/out-of-range) / 特徵違反 #12 合理範圍"
                    .into(),
            ));
        }
        let arr = features.to_array();
        let q10 = self
            .q10
            .predict_scalar(&arr)
            .map_err(|e| PredictError::InferenceFailed(format!("q10: {}", e)))?;
        let q50 = self
            .q50
            .predict_scalar(&arr)
            .map_err(|e| PredictError::InferenceFailed(format!("q50: {}", e)))?;
        let q90 = self
            .q90
            .predict_scalar(&arr)
            .map_err(|e| PredictError::InferenceFailed(format!("q90: {}", e)))?;
        if !q10.is_finite() || !q50.is_finite() || !q90.is_finite() {
            return Err(PredictError::InferenceFailed(format!(
                "non-finite ort output q10={} q50={} q90={}",
                q10, q50, q90
            )));
        }
        // Monotone rearrangement per §7.3 Step 5 — always runs, idempotent.
        // 單調重排（§7.3 Step 5）— 冪等，恆執行。
        let p = enforce_monotone(Prediction { q10, q50, q90 });
        if !p.is_valid() {
            return Err(PredictError::InferenceFailed(format!(
                "rearrangement produced invalid prediction: q10={} q50={} q90={}",
                p.q10, p.q50, p.q90
            )));
        }
        Ok(p)
    }

    fn age_seconds(&self) -> u64 {
        let now = super::now_unix_seconds();
        now.saturating_sub(self.train_date_unix)
    }

    fn schema_hash(&self) -> &str {
        &self.schema_hash
    }

    fn definition_hash(&self) -> &str {
        &self.definition_hash
    }

    fn model_id(&self) -> &str {
        &self.model_id
    }
}

// ============================================================
// Tests (unit) — fixture-free, pure-logic only. Model-loading +
// end-to-end inference tests live in `tests/edge_predictor_ort_backend.rs`
// where the fixture ONNX files are generated/committed.
// 單元測試 — 純邏輯，無 fixture；E2E 測試在 `tests/` 整合套件。
// ============================================================
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_derive_sibling_path_replaces_only_marker_substring() {
        let base = Path::new("/tmp/edge_predictor_demo_ma_crossover_q50_v1_2026-04-15.onnx");
        let q10 = derive_sibling_path(base, "_q50_", "_q10_").unwrap();
        let q90 = derive_sibling_path(base, "_q50_", "_q90_").unwrap();
        assert_eq!(
            q10.file_name().unwrap(),
            "edge_predictor_demo_ma_crossover_q10_v1_2026-04-15.onnx"
        );
        assert_eq!(
            q90.file_name().unwrap(),
            "edge_predictor_demo_ma_crossover_q90_v1_2026-04-15.onnx"
        );
    }

    #[test]
    fn test_derive_sibling_path_rejects_missing_marker() {
        let base = Path::new("/tmp/some_unrelated_model.onnx");
        assert!(derive_sibling_path(base, "_q50_", "_q10_").is_err());
    }

    #[test]
    fn test_verify_trio_aligned_rejects_schema_drift() {
        let mut q50 = make_meta(
            "v1",
            "hashA",
            "hashA",
            "demo",
            "ma",
            "q50",
            "2026-04-15",
            "mid",
        );
        let q10 = make_meta(
            "v1",
            "hashA",
            "hashA",
            "demo",
            "ma",
            "q10",
            "2026-04-15",
            "low",
        );
        let q90 = make_meta(
            "v1",
            "hashA",
            "hashA",
            "demo",
            "ma",
            "q90",
            "2026-04-15",
            "hi",
        );
        q50.schema_hash = "hashB".into();
        let err = verify_trio_aligned(&q10, &q50, &q90).unwrap_err();
        assert!(err.contains("schema_hash"), "actual err: {}", err);
    }

    #[test]
    fn test_verify_trio_aligned_rejects_mixed_train_date() {
        let q10 = make_meta("v1", "h", "h", "demo", "ma", "q10", "2026-04-15", "low");
        let q50 = make_meta("v1", "h", "h", "demo", "ma", "q50", "2026-04-16", "mid");
        let q90 = make_meta("v1", "h", "h", "demo", "ma", "q90", "2026-04-15", "hi");
        let err = verify_trio_aligned(&q10, &q50, &q90).unwrap_err();
        assert!(err.contains("train_date"), "actual err: {}", err);
    }

    #[test]
    fn test_verify_quantile_tags_rejects_swapped_quantiles() {
        let q10 = make_meta("v1", "h", "h", "demo", "ma", "q50", "2026-04-15", "x");
        let q50 = make_meta("v1", "h", "h", "demo", "ma", "q10", "2026-04-15", "x");
        let q90 = make_meta("v1", "h", "h", "demo", "ma", "q90", "2026-04-15", "x");
        assert!(verify_quantile_tags(&q10, &q50, &q90).is_err());
    }

    #[test]
    fn test_parse_train_date_unix_roundtrip() {
        let ts = parse_train_date_unix("2026-04-15");
        // 2026-04-15 00:00 UTC ~= 1776470400.
        assert!(
            ts > 1_700_000_000,
            "expected sensible unix seconds, got {}",
            ts
        );
    }

    #[test]
    fn test_parse_train_date_unix_bad_input_returns_zero() {
        assert_eq!(parse_train_date_unix("not-a-date"), 0);
        assert_eq!(parse_train_date_unix(""), 0);
    }

    fn make_meta(
        schema_version: &str,
        schema_hash: &str,
        definition_hash: &str,
        engine_mode: &str,
        strategy_name: &str,
        quantile: &str,
        train_date: &str,
        model_id: &str,
    ) -> OnnxMetadata {
        OnnxMetadata {
            schema_version: schema_version.into(),
            schema_hash: schema_hash.into(),
            definition_hash: definition_hash.into(),
            engine_mode: engine_mode.into(),
            strategy_name: strategy_name.into(),
            quantile: quantile.into(),
            train_date: train_date.into(),
            model_id: model_id.into(),
            n_features: FeatureVectorV1::DIM,
        }
    }
}
