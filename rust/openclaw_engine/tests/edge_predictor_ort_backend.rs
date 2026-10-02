//! ort_backend integration tests — loads real ONNX fixtures and runs
//! end-to-end inference through the public `EdgePredictor` trait.
//!
//! The fixture trio under `tests/fixtures/edge_predictor/` is produced by
//! `gen_fixtures.py` (committed alongside the .onnx bytes so Rust tests
//! don't require a Python toolchain). Regenerate with:
//!   PYTHONPATH=program_code \
//!     program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/python \
//!     rust/openclaw_engine/tests/fixtures/edge_predictor/gen_fixtures.py
//!
//! ort_backend 整合測試 — 載入實際 ONNX fixture 並通過 `EdgePredictor` trait
//! 做端到端推理。fixture 由 `gen_fixtures.py` 產生並提交。
//!
//! Gated on `edge_predictor_ort` — default build skips this file entirely.
//! 經 `edge_predictor_ort` 門控；預設 build 整檔跳過。

#![cfg(feature = "edge_predictor_ort")]

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

use openclaw_engine::edge_predictor::{features::FeatureVectorV1, load_predictor_from_path};

/// `Arc<dyn EdgePredictor>` doesn't implement Debug, so the standard
/// `Result::unwrap_err()` won't compile on our loader return type. Map the
/// Ok side to () first, then the error is readable via standard unwrap.
/// `Arc<dyn EdgePredictor>` 無 Debug，用此 helper 把 Ok 側抹為 () 後再拿 Err。
fn expect_load_err<T>(r: Result<T, String>) -> String {
    match r {
        Ok(_) => panic!("expected loader Err, got Ok"),
        Err(e) => e,
    }
}

fn fixture_dir() -> PathBuf {
    std::env::var_os("AIML_D1_FIXTURE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/edge_predictor")
        })
}

fn q50_fixture_path() -> PathBuf {
    fixture_dir().join("edge_predictor_demo_fixture_strategy_q50_v1_2026-04-15.onnx")
}

/// Mid-range feature vector that clears Invariant #12 sanity.
/// 中間值特徵向量，通過 #12 合理範圍。
fn sample_features() -> FeatureVectorV1 {
    FeatureVectorV1 {
        adx_1h: 25.0,
        bb_width_pct: 1.5,
        atr_pct: 0.5,
        funding_rate: 0.0001,
        realized_vol_1h: 1.2,
        basis_bps: 5.0,
        orderbook_imbalance_top5: 0.1,
        spread_bps: 2.0,
        confluence_score: 30.0,
        persistence_elapsed_ms: 60_000.0,
        side: 1,
        notional_pct_of_bal: 5.0,
        concurrent_positions: 1,
        same_direction_cnt: 1,
        tod_sin: 0.5,
        tod_cos: 0.8,
        is_funding_settlement_window: 0,
    }
}

#[test]
fn test_load_trio_from_q50_fixture_succeeds() {
    let p = q50_fixture_path();
    assert!(
        p.exists(),
        "fixture missing at {} — run gen_fixtures.py",
        p.display()
    );
    let predictor = load_predictor_from_path(&p).expect("trio load should succeed");
    // schema_hash must equal the runtime FEATURE_NAMES_V1 hash (fixture is
    // stamped with that exact value by gen_fixtures.py via Rust-parity
    // _compute_feature_schema_hash). Any mismatch surfaces a contract drift.
    // schema_hash 必等於運行期 FEATURE_NAMES_V1 hash；不等即契約漂移。
    assert_eq!(
        predictor.schema_hash(),
        openclaw_engine::edge_predictor::features::feature_schema_hash()
    );
    assert_eq!(
        predictor.definition_hash(),
        openclaw_engine::edge_predictor::features::feature_definition_hash()
    );
    assert!(predictor.model_id().contains("fixture_strategy"));
    // Fixed historical fixture: this loose age check proves only mechanics.
    // age_seconds 應為正常範圍（<10 年）。
    assert!(predictor.age_seconds() < 10 * 365 * 24 * 3600);
}

// Literals fixed from independent tree/leaf traversal before Rust execution.
// This tolerance is absolute bps and is never fitted to actual outputs.
const EXPECTED_BPS: [f64; 3] = [-1.5273265838623047, 1.7042269483208656, 4.102983659686288];
const ABS_TOLERANCE_BPS: f64 = 0.00001;

#[test]
fn test_d1_shared_input_exact_predictions_and_loaded_hashes() {
    let shared = shared_inputs();
    assert_eq!(validate_shared_contract(&shared), Ok(()));
    let row: Vec<f32> = shared["smoke"]["feature_values"]
        .as_array()
        .unwrap()
        .iter()
        .map(|v| v.as_f64().unwrap() as f32)
        .collect();
    assert_eq!(sample_features().to_array().as_slice(), row.as_slice());
    assert_eq!(
        shared["smoke"]["absolute_tolerance_bps"].as_f64(),
        Some(ABS_TOLERANCE_BPS)
    );
    for q in ["q10", "q50", "q90"] {
        let path = fixture_dir().join(shared["fixtures"][q]["path"].as_str().unwrap());
        let actual = format!("{:x}", Sha256::digest(std::fs::read(path).unwrap()));
        assert_eq!(actual, shared["fixtures"][q]["sha256"].as_str().unwrap());
        println!("D1_LOADED_HASH {q} {actual}");
    }
    let predictor = load_predictor_from_path(&q50_fixture_path()).unwrap();
    let prediction = predictor.predict(&sample_features()).unwrap();
    for (i, (q, actual)) in ["q10", "q50", "q90"]
        .into_iter()
        .zip([prediction.q10, prediction.q50, prediction.q90])
        .enumerate()
    {
        assert!(
            (shared["smoke"]["expected_bps"][q].as_f64().unwrap() - EXPECTED_BPS[i]).abs() < 1e-14
        );
        println!(
            "D1_PREDICTION {q} expected={:.15} actual={:.15} abs_tolerance={ABS_TOLERANCE_BPS}",
            EXPECTED_BPS[i], actual
        );
        assert!(
            (actual as f64 - EXPECTED_BPS[i]).abs() <= ABS_TOLERANCE_BPS,
            "{q} differs from independent oracle"
        );
    }
}

#[test]
fn test_predict_rejects_invariant12_violating_features() {
    let predictor = load_predictor_from_path(&q50_fixture_path()).unwrap();
    let mut bad = sample_features();
    bad.adx_1h = f32::NAN; // Invariant #12 trip
    let err = predictor.predict(&bad).unwrap_err();
    match err {
        openclaw_engine::edge_predictor::PredictError::InferenceFailed(msg) => {
            assert!(
                msg.contains("Invariant #12") || msg.contains("NaN/Inf"),
                "expected invariant #12 / NaN mention, got: {}",
                msg
            );
        }
        other => panic!("expected InferenceFailed, got {:?}", other),
    }
}

#[test]
fn test_load_rejects_tampered_metadata_schema_hash() {
    // Build a tampered copy: write a model_proto with the schema_hash swapped
    // for a bogus value and confirm the loader refuses. We do this by copying
    // the fixture bytes, mutating them in-place at the sha256 substring (the
    // full 16-hex value appears as a literal run of ASCII bytes inside the
    // protobuf metadata_props section), then loading from the copy.
    // 建立竄改副本：把 schema_hash ASCII 串替換為 bogus 值，確認載入器拒絕。
    let original = std::fs::read(q50_fixture_path()).unwrap();
    let expected = openclaw_engine::edge_predictor::features::feature_schema_hash();
    let hex_part = &expected["sha256:".len()..]; // 16 hex chars
    let expected_bytes = hex_part.as_bytes();
    let idx = find_subsequence(&original, expected_bytes).expect(
        "expected schema_hash ASCII in fixture bytes — did gen_fixtures.py write the \
         correct schema_hash?",
    );
    let mut tampered = original.clone();
    // Flip every hex char to '0' — still 16 valid hex chars, so proto parses
    // OK and extract_metadata() reads the tampered string, but the Rust hash
    // gate rejects it as !=.
    // 改為 16 個 '0'；proto 仍 parse 通過，但 hash 不匹配被拒。
    for b in &mut tampered[idx..idx + expected_bytes.len()] {
        *b = b'0';
    }
    let tmp = tempfile::tempdir().unwrap();
    let q50 = tmp
        .path()
        .join("edge_predictor_demo_fixture_strategy_q50_v1_2026-04-15.onnx");
    // Copy q10/q90 siblings unmodified so the loader only fails at the q50
    // schema_hash check rather than on derived-sibling-missing.
    // 複製 q10/q90 兄弟原檔以讓失敗點落在 q50 schema_hash 檢查。
    for quantile in ["q10", "q90"] {
        let src = fixture_dir().join(format!(
            "edge_predictor_demo_fixture_strategy_{}_v1_2026-04-15.onnx",
            quantile
        ));
        let dst = tmp.path().join(format!(
            "edge_predictor_demo_fixture_strategy_{}_v1_2026-04-15.onnx",
            quantile
        ));
        std::fs::copy(&src, &dst).unwrap();
    }
    std::fs::write(&q50, &tampered).unwrap();

    let err = expect_load_err(load_predictor_from_path(&q50));
    assert!(
        err.contains("schema_hash mismatch"),
        "expected schema_hash mismatch, got: {}",
        err
    );
}

#[test]
fn test_load_rejects_missing_sibling_file() {
    // Copy only q50 to a temp dir — q10/q90 siblings absent. Loader must
    // surface the missing sibling rather than panic or silently succeed.
    // 只複製 q50 至 tmp；loader 應明確報缺兄弟檔而非 panic 或靜默成功。
    let tmp = tempfile::tempdir().unwrap();
    let q50 = tmp
        .path()
        .join("edge_predictor_demo_fixture_strategy_q50_v1_2026-04-15.onnx");
    std::fs::copy(q50_fixture_path(), &q50).unwrap();
    let err = expect_load_err(load_predictor_from_path(&q50));
    // The ort loader surfaces the filesystem error (ENOENT) when reading
    // the q10/q90 sibling — assert on either "q10" or "q90" so the test is
    // robust to either sibling being tried first.
    // ort 讀不到兄弟檔會顯露 ENOENT；斷言提到 q10 或 q90。
    assert!(
        err.contains("q10") || err.contains("q90"),
        "expected missing-sibling error, got: {}",
        err
    );
}

/// Helper: find first index of `needle` in `haystack`. Small linear scan; used
/// only in tests on <10KB blobs so O(n·m) is fine.
/// 輔助：於 `haystack` 找 `needle` 起始索引；測試用，線性掃描即可。
fn find_subsequence(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

fn shared_inputs() -> Value {
    let bytes = include_bytes!("fixtures/edge_predictor/aiml_d1_shared_inputs.json");
    assert_eq!(
        format!("{:x}", Sha256::digest(bytes)),
        "08353f098f8aa6e022aa241f982b729bf55a0c906b442aad2f9404da1cb873d7"
    );
    serde_json::from_slice(bytes).unwrap()
}

fn validate_shared_contract(shared: &Value) -> Result<(), &'static str> {
    use openclaw_engine::edge_predictor::features::{FEATURE_DEFINITIONS_V1, FEATURE_NAMES_V1};
    let names: Vec<_> = shared["feature_names"]
        .as_array()
        .ok_or("missing names")?
        .iter()
        .map(Value::as_str)
        .collect();
    if names
        != FEATURE_NAMES_V1
            .iter()
            .map(|s| Some(*s))
            .collect::<Vec<_>>()
    {
        return Err("feature order/schema mismatch");
    }
    let definitions: Vec<_> = shared["feature_definitions"]
        .as_array()
        .ok_or("missing definitions")?
        .iter()
        .map(Value::as_str)
        .collect();
    if definitions
        != FEATURE_DEFINITIONS_V1
            .iter()
            .map(|s| Some(*s))
            .collect::<Vec<_>>()
    {
        return Err("feature definition mismatch");
    }
    if shared["smoke"]["feature_values"].as_array().map(Vec::len) != Some(17) {
        return Err("missing feature value");
    }
    Ok(())
}

#[test]
fn test_d1_shared_input_rejects_order_definition_and_missing_values() {
    let mut v = shared_inputs();
    v["feature_names"].as_array_mut().unwrap().swap(0, 1);
    assert_eq!(
        validate_shared_contract(&v),
        Err("feature order/schema mismatch")
    );
    let mut v = shared_inputs();
    v["feature_definitions"][0] = Value::String("adx_1h=wrong-window".into());
    assert_eq!(
        validate_shared_contract(&v),
        Err("feature definition mismatch")
    );
    let mut v = shared_inputs();
    v["smoke"]["feature_values"].as_array_mut().unwrap().pop();
    assert_eq!(validate_shared_contract(&v), Err("missing feature value"));
}

fn copy_trio() -> tempfile::TempDir {
    let tmp = tempfile::tempdir().unwrap();
    for q in ["q10", "q50", "q90"] {
        let name = format!("edge_predictor_demo_fixture_strategy_{q}_v1_2026-04-15.onnx");
        std::fs::copy(fixture_dir().join(&name), tmp.path().join(name)).unwrap();
    }
    tmp
}

fn replace_metadata(path: &Path, key: &str, old: &str, new: &str) {
    assert_eq!(old.len(), new.len());
    let mut bytes = std::fs::read(path).unwrap();
    let mut needle = key.as_bytes().to_vec();
    needle.extend([0x12, old.len() as u8]);
    needle.extend(old.as_bytes());
    let at = find_subsequence(&bytes, &needle).unwrap() + needle.len() - old.len();
    bytes[at..at + old.len()].copy_from_slice(new.as_bytes());
    std::fs::write(path, bytes).unwrap();
}

#[test]
fn test_d1_loader_rejects_definition_scope_and_quantile_drift() {
    for (q, key, old, new, reason) in [
        (
            "q50",
            "edge_p3_feature_definition_hash",
            "sha256:d701f7d30e3c29f8",
            "sha256:0000000000000000",
            "definition_hash mismatch",
        ),
        (
            "q10",
            "edge_p3_strategy_name",
            "fixture_strategy",
            "foreign_strategy",
            "trio mismatch on strategy_name",
        ),
        (
            "q90",
            "edge_p3_engine_mode",
            "demo",
            "live",
            "trio mismatch on engine_mode",
        ),
        (
            "q10",
            "edge_p3_quantile",
            "q10",
            "q90",
            "wrong quantile artifact",
        ),
    ] {
        let tmp = copy_trio();
        let path = tmp.path().join(format!(
            "edge_predictor_demo_fixture_strategy_{q}_v1_2026-04-15.onnx"
        ));
        replace_metadata(&path, key, old, new);
        let err = expect_load_err(load_predictor_from_path(
            &tmp.path()
                .join("edge_predictor_demo_fixture_strategy_q50_v1_2026-04-15.onnx"),
        ));
        assert!(err.contains(reason), "{key}: {err}");
        println!("D1_LOADER_DENY {key} {err}");
    }
}

#[test]
fn test_d1_fixture_identity_detects_model_metadata_tamper_and_corrupt_graph() {
    let tmp = copy_trio();
    let path = tmp
        .path()
        .join("edge_predictor_demo_fixture_strategy_q50_v1_2026-04-15.onnx");
    replace_metadata(
        &path,
        "edge_p3_model_id",
        "edge_predictor_demo_fixture_strategy_q50_v1_2026-04-15",
        "edge_predictor_demo_foreign_strategy_q50_v1_2026-04-15",
    );
    let actual = format!("{:x}", Sha256::digest(std::fs::read(&path).unwrap()));
    assert_ne!(
        actual,
        shared_inputs()["fixtures"]["q50"]["sha256"]
            .as_str()
            .unwrap()
    );
    // Hash binding belongs to this fixture harness; the legacy loader has no
    // expected qualified model-id/hash parameter. It cannot certify serving.
    std::fs::write(&path, b"invalid onnx graph").unwrap();
    assert!(!expect_load_err(load_predictor_from_path(&path)).is_empty());
}

#[test]
fn test_d1_actual_ort_inference_shape_failure_is_reported() {
    let tmp = copy_trio();
    let path = tmp
        .path()
        .join("edge_predictor_demo_fixture_strategy_q50_v1_2026-04-15.onnx");
    let mut bytes = std::fs::read(&path).unwrap();
    // Fixed fixture GraphProto input: "features", float, shape [dynamic,17].
    // Alter only a TEMP copy's declared input dimension to 18. Metadata stays
    // valid so public load succeeds, then actual Session::run must fail on 17.
    let input = b"\x0a\x08features\x12\x0c\x0a\x0a\x08\x01\x12\x06\x0a\x00\x0a\x02\x08\x11";
    assert_eq!(
        bytes.windows(input.len()).filter(|w| *w == input).count(),
        1
    );
    let at = find_subsequence(&bytes, input).unwrap() + input.len() - 1;
    bytes[at] = 18;
    std::fs::write(&path, bytes).unwrap();
    let predictor = load_predictor_from_path(&path).unwrap();
    match predictor.predict(&sample_features()) {
        Err(openclaw_engine::edge_predictor::PredictError::InferenceFailed(reason)) => {
            assert!(reason.contains("q50: ort run:"), "{reason}");
            assert!(reason.contains("17") && reason.contains("18"), "{reason}");
            println!("D1_ACTUAL_INFERENCE_FAILURE {reason}");
        }
        other => panic!("expected actual ORT shape failure, got {other:?}"),
    }
}

fn frozen_binding() -> openclaw_engine::edge_predictor::PredictorArtifactBinding {
    let shared = shared_inputs();
    openclaw_engine::edge_predictor::PredictorArtifactBinding {
        engine_mode: "demo".into(),
        strategy_name: "fixture_strategy".into(),
        model_ids: ["q10", "q50", "q90"].map(|q| {
            shared["fixtures"][q]["metadata"]["edge_p3_model_id"]
                .as_str()
                .unwrap()
                .into()
        }),
        artifact_sha256: ["q10", "q50", "q90"]
            .map(|q| shared["fixtures"][q]["sha256"].as_str().unwrap().into()),
    }
}

fn bound_gate(
    path: &Path,
    engine: openclaw_engine::tick_pipeline::PipelineKind,
    strategy: &str,
    expected: Option<openclaw_engine::edge_predictor::PredictorArtifactBinding>,
) -> openclaw_engine::edge_predictor::gate::PredictorGateOutcome {
    bound_gate_with_age(path, engine, strategy, expected, u64::MAX)
}

fn bound_gate_with_age(
    path: &Path,
    engine: openclaw_engine::tick_pipeline::PipelineKind,
    strategy: &str,
    expected: Option<openclaw_engine::edge_predictor::PredictorArtifactBinding>,
    max_age: u64,
) -> openclaw_engine::edge_predictor::gate::PredictorGateOutcome {
    use openclaw_engine::edge_predictor::{
        gate::{edge_predictor_gate, GateInputs},
        EdgePredictorStore,
    };
    use rand::{rngs::SmallRng, SeedableRng};
    let predictor = load_predictor_from_path(path).unwrap();
    let actual = predictor.artifact_binding().unwrap();
    eprintln!("D1_BINDING actual={actual:?} expected={expected:?}");
    let store = EdgePredictorStore::new();
    store.swap(strategy, predictor);
    let inputs = GateInputs {
        expected_binding: expected,
        engine_kind: engine,
        strategy,
        symbol: "BTCUSDT",
        context_id: "fixture:d1.1:scope-counterexample",
        cost_bps: 20.0,
        is_add_to_existing: false,
        now_ms: 0,
    };
    let cfg = openclaw_engine::config::risk_config::EdgePredictor {
        model_max_age_seconds: max_age,
        exploration_rate: 0.0,
        ..Default::default()
    };
    let out = edge_predictor_gate(
        &inputs,
        &sample_features(),
        &store,
        &mut SmallRng::seed_from_u64(51),
        &cfg,
        || "{}".into(),
    );
    eprintln!("D1_IDENTITY_GATE {out:?}");
    out
}

#[test]
fn matching_demo_strategy_control_is_veto() {
    use openclaw_engine::{
        edge_predictor::gate::PredictorGateOutcome, tick_pipeline::PipelineKind,
    };
    assert!(matches!(
        bound_gate(
            &q50_fixture_path(),
            PipelineKind::Demo,
            "fixture_strategy",
            Some(frozen_binding())
        ),
        PredictorGateOutcome::Reject(_)
    ));
}

#[test]
fn demo_artifact_in_live_gate_must_disable_model_contribution() {
    use openclaw_engine::{
        edge_predictor::gate::{FallbackReason, PredictorGateOutcome},
        tick_pipeline::PipelineKind,
    };
    assert!(matches!(
        bound_gate(
            &q50_fixture_path(),
            PipelineKind::Live,
            "fixture_strategy",
            Some(frozen_binding())
        ),
        PredictorGateOutcome::Fallback(FallbackReason::ModelIdentityMismatch)
    ));
}

#[test]
fn fixture_strategy_artifact_in_other_strategy_slot_must_disable_model() {
    use openclaw_engine::{
        edge_predictor::gate::{FallbackReason, PredictorGateOutcome},
        tick_pipeline::PipelineKind,
    };
    assert!(matches!(
        bound_gate(
            &q50_fixture_path(),
            PipelineKind::Demo,
            "other_strategy",
            Some(frozen_binding())
        ),
        PredictorGateOutcome::Fallback(FallbackReason::ModelIdentityMismatch)
    ));
}

#[test]
fn changed_model_identity_and_bytes_must_not_reuse_frozen_model_binding() {
    use openclaw_engine::{
        edge_predictor::gate::{FallbackReason, PredictorGateOutcome},
        tick_pipeline::PipelineKind,
    };
    let tmp = copy_trio();
    let path = tmp.path().join(q50_fixture_path().file_name().unwrap());
    replace_metadata(
        &path,
        "edge_p3_model_id",
        "edge_predictor_demo_fixture_strategy_q50_v1_2026-04-15",
        "wrongpredictor_demo_fixture_strategy_q50_v1_2026-04-15",
    );
    assert_eq!(
        format!("{:x}", Sha256::digest(std::fs::read(&path).unwrap())),
        "f92b8f81c08b4d7e097918c4794e2639a6f18fc1a3173854b2e55111684a11c3"
    );
    assert!(matches!(
        bound_gate(
            &path,
            PipelineKind::Demo,
            "fixture_strategy",
            Some(frozen_binding())
        ),
        PredictorGateOutcome::Fallback(FallbackReason::ModelIdentityMismatch)
    ));
}

#[test]
fn test_d1_each_expected_model_id_and_hash_is_enforced() {
    use openclaw_engine::{
        edge_predictor::gate::{FallbackReason, PredictorGateOutcome},
        tick_pipeline::PipelineKind,
    };
    for i in 0..3 {
        for field in ["model_id", "artifact_sha256"] {
            let mut expected = frozen_binding();
            if field == "model_id" {
                expected.model_ids[i] = "wrong-model-id".into();
            } else {
                expected.artifact_sha256[i] = "0".repeat(64);
            }
            eprintln!("D1_NEGATIVE expected_field={field} quantile_index={i}");
            assert!(matches!(
                bound_gate(
                    &q50_fixture_path(),
                    PipelineKind::Demo,
                    "fixture_strategy",
                    Some(expected)
                ),
                PredictorGateOutcome::Fallback(FallbackReason::ModelIdentityMismatch)
            ));
        }
    }
}

#[test]
fn test_d1_missing_or_incomplete_expected_binding_disables_model() {
    use openclaw_engine::{
        edge_predictor::gate::{FallbackReason, PredictorGateOutcome},
        tick_pipeline::PipelineKind,
    };
    let mut incomplete = frozen_binding();
    incomplete.artifact_sha256[0].clear();
    for expected in [None, Some(incomplete)] {
        assert!(matches!(
            bound_gate(
                &q50_fixture_path(),
                PipelineKind::Demo,
                "fixture_strategy",
                expected
            ),
            PredictorGateOutcome::Fallback(FallbackReason::UnboundModel)
        ));
    }
}

#[test]
fn test_d1_loaded_binding_and_prediction_survive_path_mutation() {
    let tmp = copy_trio();
    let path = tmp.path().join(q50_fixture_path().file_name().unwrap());
    let expected = frozen_binding(); // accepted fixture mechanics literals, before load
    let predictor = load_predictor_from_path(&path).unwrap();
    assert_eq!(predictor.artifact_binding(), Some(expected.clone()));
    for q in ["q10", "q50", "q90"] {
        std::fs::write(
            tmp.path().join(
                q50_fixture_path()
                    .file_name()
                    .unwrap()
                    .to_str()
                    .unwrap()
                    .replace("_q50_", &format!("_{q}_")),
            ),
            b"changed after session load",
        )
        .unwrap();
    }
    assert_eq!(predictor.artifact_binding(), Some(expected));
    let actual = predictor.predict(&sample_features()).unwrap();
    for (value, expected) in [actual.q10, actual.q50, actual.q90]
        .into_iter()
        .zip(EXPECTED_BPS)
    {
        assert!((value as f64 - expected).abs() <= ABS_TOLERANCE_BPS);
    }
    assert!(load_predictor_from_path(&path).is_err());
}

#[test]
fn test_d1_wrong_identity_is_no_op_even_when_artifact_is_stale() {
    use openclaw_engine::{
        edge_predictor::gate::{FallbackReason, PredictorGateOutcome},
        tick_pipeline::PipelineKind,
    };
    assert!(matches!(
        bound_gate_with_age(
            &q50_fixture_path(),
            PipelineKind::Live,
            "fixture_strategy",
            Some(frozen_binding()),
            0
        ),
        PredictorGateOutcome::Fallback(FallbackReason::ModelIdentityMismatch)
    ));
    assert!(matches!(
        bound_gate_with_age(
            &q50_fixture_path(),
            PipelineKind::Demo,
            "fixture_strategy",
            None,
            0
        ),
        PredictorGateOutcome::Fallback(FallbackReason::UnboundModel)
    ));
    assert!(matches!(
        bound_gate_with_age(
            &q50_fixture_path(),
            PipelineKind::Demo,
            "fixture_strategy",
            Some(frozen_binding()),
            0
        ),
        PredictorGateOutcome::Fallback(FallbackReason::ModelStale)
    ));
}
