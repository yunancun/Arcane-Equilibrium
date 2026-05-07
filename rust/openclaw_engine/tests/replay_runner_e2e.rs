//! REF-20 Wave 4 R20-P2b-T1 — `replay_runner` end-to-end acceptance proofs.
//! REF-20 Wave 4 R20-P2b-T1 — `replay_runner` 端到端 acceptance 證明。
//!
//! MODULE_NOTE (EN):
//!   This integration test exercises the Wave 4 IMPL stack:
//!     CLI parser  ->  manifest_signer verify  ->  fixture_loader load
//!                ->  IsolatedPipeline execute  ->  report_writer JSON dump
//!
//!   We test the lib-level API directly (NOT `Command::new(target/release/replay_runner)`)
//!   for two reasons:
//!     1. cargo test runs WITHOUT the `replay_isolated` feature by default;
//!        spawning the binary would require pre-building it under that
//!        feature, which couples the e2e test to an external CI step.
//!     2. The lib-level path lets us mutate environment in a serialised
//!        manner (matching `replay_forbidden_guard_acceptance.rs` precedent)
//!        for the forbidden-trip test case.
//!
//!   Five acceptance proofs (per V3 §12 binding):
//!     1. happy_path_synthetic_fixture
//!         — valid manifest + S3 fixture -> result.status='completed' +
//!           replay_report.json written + execution_confidence='none'
//!     2. invalid_manifest_signature
//!         — manifest_signer verify path catches a tampered body and the
//!           runner aborts (4 fail-mode contract).
//!     3. fixture_missing_returns_typed_error
//!         — fixture file does not exist -> FixtureNotFound (no panic).
//!     4. forbidden_path_trip_via_env_aborts_run
//!         — setting OPENCLAW_REPLAY_FORBIDDEN_TRIPPED=AcquireLeaseDetected
//!           causes the pipeline to abort mid-execute with status =
//!           AbortedForbidden + abort_reason populated. Demonstrates the
//!           V3 §12 #10 acceptance binding from runner.rs's runtime guard.
//!     5. baseline_vs_candidate_two_runs
//!         — running two replays with different manifests but the same
//!           fixture produces two distinct ReplayResult JSON files; the
//!           skeleton "diff metrics" is captured in the test as the delta
//!           between the two `pnl_summary` objects (T2 will land the actual
//!           comparison route + diff renderer).
//!
//! MODULE_NOTE (中):
//!   本整合測試演練 Wave 4 IMPL stack：
//!     CLI 解析  ->  manifest_signer 驗證  ->  fixture_loader 載入
//!              ->  IsolatedPipeline 執行  ->  report_writer JSON 落盤
//!
//!   我們直接測 lib 層 API（**不**用 `Command::new(target/release/replay_runner)`）
//!   理由有二：
//!     1. cargo test 預設**不**帶 `replay_isolated` feature；要跑 binary
//!        需先以該 feature pre-build，把 e2e test 與 external CI step 耦合。
//!     2. lib 層路徑讓我們以 serialised 方式 mutate environment（對齊
//!        `replay_forbidden_guard_acceptance.rs` 先例），供 forbidden-trip
//!        test case 用。
//!
//!   五個 acceptance proof（V3 §12 binding）：
//!     1. happy_path_synthetic_fixture
//!         — 有效 manifest + S3 fixture -> result.status='completed' +
//!           replay_report.json 寫入 + execution_confidence='none'
//!     2. invalid_manifest_signature
//!         — manifest_signer 驗證路徑捕獲 tampered body，runner abort
//!           （4 fail-mode 契約）。
//!     3. fixture_missing_returns_typed_error
//!         — fixture file 不存在 -> FixtureNotFound（不 panic）。
//!     4. forbidden_path_trip_via_env_aborts_run
//!         — 設 OPENCLAW_REPLAY_FORBIDDEN_TRIPPED=AcquireLeaseDetected
//!           使 pipeline 在 execute 中途 abort，status = AbortedForbidden +
//!           abort_reason 填值。展示 V3 §12 #10 acceptance binding 自
//!           runner.rs 的 runtime guard。
//!     5. baseline_vs_candidate_two_runs
//!         — 以不同 manifest 但同 fixture 跑兩次 replay 產生兩份不同
//!           ReplayResult JSON；骨架「diff metrics」於 test 內以兩 `pnl_summary`
//!           的 delta 表達（T2 將落實際 comparison route + diff renderer）。
//!
//! Run / 執行:
//!   `cargo test -p openclaw_engine --features replay_isolated --test replay_runner_e2e -- --nocapture`

use openclaw_engine::replay::fixture_loader::{self, FixtureSource};
use openclaw_engine::replay::forbidden_guard::{self, TRIP_ENV_VAR};
use openclaw_engine::replay::manifest_signer::{
    compute_body_hash, compute_key_fingerprint, InMemoryKeyArchive, KeyStatus, ManifestSigner,
    SignatureFailMode,
};
use openclaw_engine::replay::profile::ReplayProfile;
use openclaw_engine::replay::report_writer;
use openclaw_engine::replay::runner::{self, ReplayStatus};
use std::env;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use tempfile::tempdir;

// ─────────────────────────────────────────────────────────────────────────
// Serial-mutation guard for env-based proofs.
// 序列化 mutate 守衛供 env-based proof 使用。
//
// Rationale: cargo test runs tests inside the same file in parallel by
// default. Proof 4 mutates `OPENCLAW_REPLAY_FORBIDDEN_TRIPPED`, which
// `forbidden_guard::current_trip_value` reads. Without serialisation the
// mutation could leak into sibling proofs and cause spurious aborts.
// 同檔 test cargo 預設並行；Proof 4 mutate 的 env var 會被
// `forbidden_guard::current_trip_value` 讀，不序列化會洩漏到 sibling test
// 造成假 abort。
// ─────────────────────────────────────────────────────────────────────────

fn env_lock() -> &'static Mutex<()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
}

/// RAII helper that restores the env var to its prior value on Drop.
///
/// RAII 助手，於 Drop 時將 env var 還原為前值。
struct EnvVarRestore {
    name: String,
    prior: Option<String>,
}

impl EnvVarRestore {
    fn capture(name: &str) -> Self {
        Self {
            name: name.to_string(),
            prior: env::var(name).ok(),
        }
    }
}

impl Drop for EnvVarRestore {
    fn drop(&mut self) {
        match &self.prior {
            Some(v) => env::set_var(&self.name, v),
            None => env::remove_var(&self.name),
        }
    }
}

// ─────────────────────────────────────────────────────────────────────────
// Fixture helpers / Fixture 助手
// ─────────────────────────────────────────────────────────────────────────

fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("replay_runner_e2e")
}

fn fixture_synthetic_path() -> PathBuf {
    fixture_dir().join("synthetic_btcusdt.json")
}

fn fixture_key_path() -> PathBuf {
    fixture_dir().join("key.hex")
}

/// Load fixture key from disk + derive (signer, fingerprint, archive).
///
/// 從 disk 載入 fixture key + 衍生 (signer, fingerprint, archive)。
fn load_fixture_signer() -> (ManifestSigner, String, InMemoryKeyArchive) {
    let key_file_content = std::fs::read(fixture_key_path()).expect("fixture key.hex missing");
    let key_hex = std::str::from_utf8(&key_file_content)
        .unwrap()
        .trim()
        .to_string();
    let key_bytes = hex::decode(&key_hex).expect("key.hex must be hex");
    assert_eq!(key_bytes.len(), 32, "key must decode to 32 bytes");
    let fingerprint = compute_key_fingerprint(&key_file_content);
    let signer = ManifestSigner::new_from_bytes_for_test(key_bytes, fingerprint.clone());
    let mut archive = InMemoryKeyArchive::new();
    archive.insert(fingerprint.clone(), KeyStatus::Active);
    (signer, fingerprint, archive)
}

/// Construct a tiny ReplayManifest body and sign it. Used by happy/baseline
/// proofs. Returns the body bytes (caller writes to a tempfile in
/// the test).
///
/// 構造一個小的 ReplayManifest body 並簽名。供 happy/baseline proof 使用。
/// 回傳 body bytes（caller 在 test 中寫入 tempfile）。
fn build_signed_manifest_body(
    experiment_id: &str,
    data_tier: &str,
    fixture_uri: &str,
) -> (Vec<u8>, String, String, String) {
    let (signer, fingerprint, _archive) = load_fixture_signer();
    let body = serde_json::json!({
        "experiment_id": experiment_id,
        "data_tier": data_tier,
        "fixture_uri": fixture_uri,
        "manifest_hash": "to_be_filled",
        "signature": "to_be_filled",
        "signature_key_ref": fingerprint,
    });
    // For T1 self-consistency we sign the JSON body AS-WRITTEN (the same
    // path replay_runner::main verifies against). Sorted-keys
    // canonicalisation is Wave 4 T2's job.
    // T1 自洽：對 AS-WRITTEN 的 JSON body 簽（與 replay_runner::main 驗的
    // 同一路徑）。Sorted-keys canonicalisation 屬 Wave 4 T2。
    let mut to_persist = body.clone();
    let raw_body = serde_json::to_vec_pretty(&to_persist).unwrap();
    let body_hash = compute_body_hash(&raw_body);
    let sig = signer.sign(&raw_body);
    to_persist["manifest_hash"] = serde_json::Value::String(body_hash.clone());
    to_persist["signature"] = serde_json::Value::String(sig.clone());
    let final_body = serde_json::to_vec_pretty(&to_persist).unwrap();
    (final_body, fingerprint, body_hash, sig)
}

/// Write manifest body to `<dir>/manifest.json`; copy `key.hex` next to it
/// so the runner finds the sibling key for verification.
///
/// 寫 manifest body 至 `<dir>/manifest.json`；把 `key.hex` 複製到旁邊使
/// runner 找到 sibling key 做驗證。
fn write_test_manifest(dir: &Path, body: &[u8]) -> PathBuf {
    let manifest_path = dir.join("manifest.json");
    std::fs::write(&manifest_path, body).unwrap();
    std::fs::copy(fixture_key_path(), dir.join("key.hex")).unwrap();
    manifest_path
}

// ─────────────────────────────────────────────────────────────────────────
// Proof 1: happy path — valid manifest + S3 fixture → completed run
// ─────────────────────────────────────────────────────────────────────────

#[test]
fn proof_1_happy_path_synthetic_fixture() {
    // Use the lib-level path (CLI parse skipped — we directly drive the
    // pipeline because the binary entry's `main()` is gated under
    // `#[cfg(feature = "replay_isolated")]` and only callable from a
    // feature-enabled cargo test invocation).
    // 走 lib 層路徑（CLI 解析略過 — 因 binary entry 的 `main()` 在
    // `#[cfg(feature = "replay_isolated")]` 後，僅 feature-enabled cargo test
    // 可呼）。
    let _guard = env_lock().lock().unwrap();
    let _trip = EnvVarRestore::capture(TRIP_ENV_VAR);
    env::remove_var(TRIP_ENV_VAR);

    // Fixture pipeline.
    // Fixture pipeline。
    let src = FixtureSource::S3Synthetic {
        path: fixture_synthetic_path(),
    };
    let events = fixture_loader::load_fixtures(&src).unwrap();
    assert!(events.len() >= 10, "fixture must have ≥10 events");

    let mut pipeline = runner::build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_e2e_happy".into(),
        src.tier_label(),
        events,
    )
    .unwrap();
    pipeline.execute().unwrap();
    let result = pipeline.into_result();

    assert_eq!(result.status, ReplayStatus::Completed);
    assert_eq!(result.execution_confidence, "none"); // V3 §12 #11 invariant
    assert_eq!(result.fills.len(), 1, "1 distinct symbol → 1 entry fill");
    assert!(result.diagnostics.guard_enforce_runtime_calls >= 10);

    // Write report and confirm JSON.
    // 寫 report 並確認 JSON。
    let tmp = tempdir().unwrap();
    let json_path = report_writer::write_replay_report(tmp.path(), &result).unwrap();
    assert!(json_path.exists());

    let raw = std::fs::read_to_string(&json_path).unwrap();
    let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
    assert_eq!(v["execution_confidence"], "none");
    assert_eq!(v["manifest_id"], "exp_e2e_happy");
    assert_eq!(v["result"]["status"]["kind"], "completed");
}

// ─────────────────────────────────────────────────────────────────────────
// Proof 2: tampered manifest signature → manifest_signer fails (audit_label
// = signature_mismatch). We exercise the manifest_signer path directly
// because the binary's `load_and_verify_manifest` is private; the lib-level
// API is the same one the binary calls.
// ─────────────────────────────────────────────────────────────────────────

#[test]
fn proof_2_invalid_manifest_signature() {
    let (signer, fingerprint, archive) = load_fixture_signer();
    let body =
        br#"{"experiment_id":"exp_e2e_sig","data_tier":"S3","fixture_uri":"unused"}"#.to_vec();
    let body_hash = compute_body_hash(&body);
    let sig = signer.sign(&body);

    // Tamper signature: flip 1 byte / 改 signature 第 1 byte。
    let mut tampered = sig.into_bytes();
    tampered[0] = if tampered[0] == b'a' { b'b' } else { b'a' };
    let tampered_sig = String::from_utf8(tampered).unwrap();

    let err = signer
        .verify(&body, &body_hash, &tampered_sig, &fingerprint, &archive)
        .unwrap_err();
    assert_eq!(err, SignatureFailMode::SignatureMismatch);
    assert_eq!(err.audit_label(), "signature_mismatch");
}

// ─────────────────────────────────────────────────────────────────────────
// Proof 3: fixture file missing → typed FixtureNotFound (no panic).
// ─────────────────────────────────────────────────────────────────────────

#[test]
fn proof_3_fixture_missing_returns_typed_error() {
    let src = FixtureSource::S3Synthetic {
        path: PathBuf::from("/nonexistent/replay_fixtures/missing_xyz.json"),
    };
    let err = fixture_loader::load_fixtures(&src).unwrap_err();
    assert!(matches!(
        err,
        fixture_loader::FixtureError::FixtureNotFound { .. }
    ));
}

// ─────────────────────────────────────────────────────────────────────────
// Proof 4: forbidden trip via env var → IsolatedPipeline aborts during
// execute(); status = AbortedForbidden; report writer can still serialise
// the partial result for audit.
// ─────────────────────────────────────────────────────────────────────────

#[test]
fn proof_4_forbidden_path_trip_via_env_aborts_run() {
    let _guard = env_lock().lock().unwrap();
    let _trip = EnvVarRestore::capture(TRIP_ENV_VAR);

    // Set the trip BEFORE building pipeline — the pipeline's first
    // enforce_at_runtime call will abort.
    // 在建 pipeline **前** 設 trip — pipeline 的首個 enforce_at_runtime 呼叫即 abort。
    env::set_var(TRIP_ENV_VAR, "AcquireLeaseDetected");

    // Sanity: enforce_at_startup confirms trip detected at the env layer.
    // sanity：enforce_at_startup 確認 env 層偵測到 trip。
    assert!(forbidden_guard::enforce_at_startup().is_err());

    let src = FixtureSource::S3Synthetic {
        path: fixture_synthetic_path(),
    };
    let events = fixture_loader::load_fixtures(&src).unwrap();
    let mut pipeline = runner::build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_e2e_forbidden".into(),
        src.tier_label(),
        events,
    )
    .unwrap();
    let exec_result = pipeline.execute();
    assert!(
        exec_result.is_err(),
        "pipeline must abort on forbidden trip"
    );

    let result = pipeline.into_result();
    assert!(matches!(
        result.status,
        ReplayStatus::AbortedForbidden { .. }
    ));
    let reason = result
        .diagnostics
        .abort_reason
        .as_deref()
        .expect("aborted run must populate abort_reason");
    assert!(
        reason.contains("forbidden_guard::enforce_at_runtime"),
        "abort_reason must reference enforce_at_runtime, got: {}",
        reason
    );

    // Even on abort, report writer must still produce the artifact (audit).
    // 即使 abort，report writer 仍須產出 artifact（audit）。
    let tmp = tempdir().unwrap();
    let json_path = report_writer::write_replay_report(tmp.path(), &result).unwrap();
    assert!(json_path.exists());
    let raw = std::fs::read_to_string(&json_path).unwrap();
    let v: serde_json::Value = serde_json::from_str(&raw).unwrap();
    assert_eq!(v["result"]["status"]["kind"], "aborted_forbidden");
}

// ─────────────────────────────────────────────────────────────────────────
// Proof 5: baseline vs candidate — two replay runs produce two distinct
// JSON artefacts; the "comparison" payload is the delta of pnl_summary
// objects (T2 will land the formal comparison route + DSR/PBO metrics).
// ─────────────────────────────────────────────────────────────────────────

#[test]
fn proof_5_baseline_vs_candidate_two_runs() {
    let _guard = env_lock().lock().unwrap();
    let _trip = EnvVarRestore::capture(TRIP_ENV_VAR);
    env::remove_var(TRIP_ENV_VAR);

    let src = FixtureSource::S3Synthetic {
        path: fixture_synthetic_path(),
    };
    let events_a = fixture_loader::load_fixtures(&src).unwrap();
    let events_b = events_a.clone(); // same fixture for skeletal proof

    // baseline run / baseline 跑。
    let mut pa = runner::build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_baseline_001".into(),
        src.tier_label(),
        events_a,
    )
    .unwrap();
    pa.execute().unwrap();
    let baseline = pa.into_result();

    // candidate run / candidate 跑。
    let mut pc = runner::build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_candidate_001".into(),
        src.tier_label(),
        events_b,
    )
    .unwrap();
    pc.execute().unwrap();
    let candidate = pc.into_result();

    // Both must complete deterministically against same fixture, so the
    // pnl_summary fields are EQUAL (T2 will introduce strategy-config
    // perturbation to make them diverge; T1 only proves the "two
    // independent results emitted to disk" pipeline).
    // 同 fixture 上兩者皆確定性完成，故 pnl_summary 欄位相等（T2 將引入
    // strategy-config perturbation 使其分歧；T1 僅證「兩獨立結果落盤」管線）。
    assert_eq!(
        baseline.pnl_summary.events_processed,
        candidate.pnl_summary.events_processed
    );
    assert_eq!(
        baseline.pnl_summary.fills_emitted,
        candidate.pnl_summary.fills_emitted
    );
    assert_eq!(baseline.manifest_id, "exp_baseline_001");
    assert_eq!(candidate.manifest_id, "exp_candidate_001");
    assert_ne!(baseline.manifest_id, candidate.manifest_id);

    // Two distinct JSON artefacts on disk / 兩份不同 JSON artefact 落盤。
    let tmp = tempdir().unwrap();
    let dir_a = tmp.path().join("baseline");
    let dir_b = tmp.path().join("candidate");
    let path_a = report_writer::write_replay_report(&dir_a, &baseline).unwrap();
    let path_b = report_writer::write_replay_report(&dir_b, &candidate).unwrap();
    assert_ne!(path_a, path_b);

    // Skeletal "diff metrics" — T2 will replace with structured diff /
    // 骨架「diff metrics」— T2 將以結構化 diff 取代。
    let pnl_diff = candidate.pnl_summary.net_pnl - baseline.pnl_summary.net_pnl;
    assert!(
        pnl_diff.abs() < 1e-9,
        "T1 deterministic fixture: baseline ≡ candidate net_pnl"
    );
}

// ─────────────────────────────────────────────────────────────────────────
// Helper-coverage proof: build_signed_manifest_body / write_test_manifest
// glue is exercised end-to-end so they don't bit-rot before T2 lands the
// CLI-driven binary spawn (Command::new) path.
// 助手覆蓋 proof：build_signed_manifest_body / write_test_manifest glue 端到端
// 演練，避免 T2 落 CLI-driven binary spawn (Command::new) 路徑前 bit-rot。
// ─────────────────────────────────────────────────────────────────────────

#[test]
fn proof_helper_signed_manifest_round_trip() {
    let tmp = tempdir().unwrap();
    let fixture_uri_str = fixture_synthetic_path().to_string_lossy().into_owned();
    let (body, _fp, _hash, _sig) =
        build_signed_manifest_body("exp_helper_round_trip", "S3", &fixture_uri_str);
    let manifest_path = write_test_manifest(tmp.path(), &body);
    assert!(manifest_path.exists());
    assert!(
        tmp.path().join("key.hex").exists(),
        "sibling key.hex must be present so runner finds it"
    );

    // Sanity: the manifest can be parsed as JSON with the required fields.
    // sanity：manifest 可解析為 JSON 且必填欄位俱在。
    let parsed: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&manifest_path).unwrap()).unwrap();
    assert_eq!(parsed["experiment_id"], "exp_helper_round_trip");
    assert_eq!(parsed["data_tier"], "S3");
    assert!(!parsed["signature"].as_str().unwrap().is_empty());
    assert!(!parsed["manifest_hash"].as_str().unwrap().is_empty());
}
