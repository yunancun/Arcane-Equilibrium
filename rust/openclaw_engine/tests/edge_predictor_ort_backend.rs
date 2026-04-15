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
    Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/edge_predictor")
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
    // age_seconds should be small but non-zero (fixture stamped today or
    // a few days ago in wall-clock terms — anything below 10 years is fine).
    // age_seconds 應為正常範圍（<10 年）。
    assert!(predictor.age_seconds() < 10 * 365 * 24 * 3600);
}

#[test]
fn test_predict_returns_monotone_finite_trio() {
    let predictor = load_predictor_from_path(&q50_fixture_path()).unwrap();
    let features = sample_features();
    let p = predictor.predict(&features).expect("inference should succeed");
    assert!(p.q10.is_finite() && p.q50.is_finite() && p.q90.is_finite());
    assert!(p.q10 <= p.q50, "q10={} > q50={}", p.q10, p.q50);
    assert!(p.q50 <= p.q90, "q50={} > q90={}", p.q50, p.q90);
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
