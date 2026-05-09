//! Replay runner manifest verification tests.

use crate::manifest::{load_and_verify_manifest, ReplayManifest};
use openclaw_engine::config::RiskConfig;
use openclaw_engine::replay::manifest_signer::{
    canonical_body_for_signing, compute_body_hash, compute_key_fingerprint, ManifestSigner,
};
use openclaw_engine::strategies::StrategyParamsConfig;
use std::io::Write;
use std::path::Path;
use tempfile::TempDir;

/// 64 hex char (32 bytes) deterministic fixture key — checked into
/// tests directory; NEVER used in production.
/// 64 hex char (32 bytes) 確定性 fixture key — 僅 test 用。
const FIXTURE_KEY_HEX: &str = "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff";

/// 寫 sibling key.hex 檔案到 tmp dir，回 (key file path, fingerprint)。
/// helper script `printf '%s\n' "$KEY_HEX" > key.hex` 等價，含 trailing
/// newline，鏡像 production deploy 檔案格式。
///
/// Write a sibling key.hex file into tmp dir, return (path, fingerprint).
/// Equivalent to helper script `printf '%s\n' "$KEY_HEX" > key.hex`
/// (with trailing newline, mirrors production file format).
fn write_fixture_key(dir: &Path) -> (std::path::PathBuf, String) {
    let path = dir.join("key.hex");
    let content = format!("{}\n", FIXTURE_KEY_HEX);
    let mut f = std::fs::File::create(&path).expect("create key.hex");
    f.write_all(content.as_bytes()).expect("write key.hex");
    let fingerprint = compute_key_fingerprint(content.as_bytes());
    (path, fingerprint)
}

/// 用 fixture key 簽指定 body，產出對應 (sig_hex, hash_hex)。
/// Sign the given body with fixture key, return (sig_hex, hash_hex).
fn sign_body(body: &[u8], fingerprint: &str) -> (String, String) {
    let key_bytes = hex::decode(FIXTURE_KEY_HEX).unwrap();
    let signer = ManifestSigner::new_from_bytes_for_test(key_bytes, fingerprint.to_string());
    let sig = signer.sign(body);
    let hash = compute_body_hash(body);
    (sig, hash)
}

/// 寫一個含 sig + hash 的單檔 manifest 到 tmp dir，回 manifest 檔路徑。
/// 模擬 Track A `_write_manifest_fixture(...)` 寫法。
///
/// Write a single-file manifest containing sig + hash to tmp dir, return
/// the path. Mimics Track A `_write_manifest_fixture(...)`.
fn write_full_manifest(
    dir: &Path,
    body_fields: &[(&str, serde_json::Value)],
    fingerprint: &str,
    run_id: Option<&str>,
) -> std::path::PathBuf {
    // 1. 組 stripped body（無 sig/hash）。
    let mut body = serde_json::Map::new();
    for (k, v) in body_fields {
        body.insert((*k).to_string(), v.clone());
    }
    if let Some(rid) = run_id {
        body.insert(
            "run_id".to_string(),
            serde_json::Value::String(rid.to_string()),
        );
    }
    // 2. canonical body bytes for signing (sorted-keys + compact)。
    let canon = serde_json::to_vec(&serde_json::Value::Object(body.clone())).unwrap();
    // 3. 算 sig + hash。
    let (sig, hash) = sign_body(&canon, fingerprint);
    // 4. 把 sig + hash + signature_key_ref envelope 加進 body 寫成完整 manifest。
    body.insert("manifest_hash".to_string(), serde_json::Value::String(hash));
    body.insert("signature".to_string(), serde_json::Value::String(sig));
    body.insert(
        "signature_key_ref".to_string(),
        serde_json::Value::String(fingerprint.to_string()),
    );
    let full = serde_json::to_vec_pretty(&serde_json::Value::Object(body)).unwrap();
    let path = dir.join("manifest.json");
    std::fs::write(&path, full).expect("write manifest.json");
    path
}

/// Happy path: 寫合法 manifest + key.hex，verify 成功。
/// Happy path: write valid manifest + key.hex, verify succeeds.
#[test]
fn happy_path_full_manifest_verifies() {
    let tmp = TempDir::new().unwrap();
    let (_key_path, fingerprint) = write_fixture_key(tmp.path());
    let manifest_path = write_full_manifest(
        tmp.path(),
        &[
            ("experiment_id", serde_json::json!("exp_happy")),
            ("data_tier", serde_json::json!("S2_paper_full_truth")),
            ("fixture_uri", serde_json::json!("fixtures/happy/")),
            ("manifest_version", serde_json::json!(1)),
        ],
        &fingerprint,
        Some("run_happy_001"),
    );

    let result = load_and_verify_manifest(&manifest_path);
    assert!(
        result.is_ok(),
        "happy path must verify, got error: {:?}",
        result.err().map(|e| e.to_string())
    );
    let manifest = result.unwrap();
    assert_eq!(manifest.experiment_id, "exp_happy");
    assert_eq!(manifest.run_id.as_deref(), Some("run_happy_001"));
}

/// Fail mode (a) — tautology defense: post-sign body tampering must
/// surface as a verify error. Pre-Sprint-1 path (`let sig = signer.sign(
/// body); signer.verify(body, sig, ...)`) would silently pass because
/// the recomputed sig always matches itself.
///
/// Fail mode (a) — tautology defense：post-sign body tampering 必須
/// surface 為 verify 錯誤。Sprint-1 前的路徑（`let sig = signer.sign(
/// body); signer.verify(body, sig, ...)`）會 silently pass，因為重簽
/// 結果永遠等於自己。
#[test]
fn fail_mode_a_tautology_defense_body_drift() {
    let tmp = TempDir::new().unwrap();
    let (_key_path, fingerprint) = write_fixture_key(tmp.path());
    let manifest_path = write_full_manifest(
        tmp.path(),
        &[
            ("experiment_id", serde_json::json!("exp_taut_orig")),
            ("data_tier", serde_json::json!("S2")),
            ("fixture_uri", serde_json::json!("fixtures/x/")),
            ("manifest_version", serde_json::json!(1)),
        ],
        &fingerprint,
        None,
    );

    // 手動把 body 內 fixture_uri 改一字（不更 sig/hash），模擬 body
    // post-sign tampering 攻擊。
    // Mutate fixture_uri without updating sig/hash, simulating post-sign
    // body tampering.
    let raw = std::fs::read_to_string(&manifest_path).unwrap();
    let tampered = raw.replace("\"fixtures/x/\"", "\"fixtures/ATTACKER_PATH/\"");
    std::fs::write(&manifest_path, tampered).unwrap();

    let err = load_and_verify_manifest(&manifest_path)
        .err()
        .map(|e| e.to_string())
        .unwrap_or_default();
    assert!(
        err.contains("manifest_signer_verify_failed"),
        "expected verify_failed, got: {}",
        err
    );
    // hash gate fires first when body bytes change → label is
    // manifest_hash_mismatch (the redundant integrity anchor catches it
    // before signer.verify gets a chance to surface signature_mismatch).
    // body 改動 → canonical body hash drift → hash gate 先抓到（manifest_hash
    // 是冗餘完整性錨，比 signer.verify 更早 surface 錯誤）。
    assert!(
        err.contains("manifest_hash_mismatch"),
        "expected manifest_hash_mismatch (hash gate fires first), got: {}",
        err
    );
}

/// Fail mode (b) — sibling key.hex absent → hard error.
/// Pre-Sprint-1 path returned `Ok(manifest)` with stderr warning (E3-P0-1
/// fail-open). Sprint 1 changes this to fail-closed.
///
/// Fail mode (b) — sibling key.hex 缺 → hard error。
/// Pre-Sprint-1 路徑回 `Ok(manifest)` 並印 stderr warning（E3-P0-1
/// fail-open）。Sprint 1 改為 fail-closed。
#[test]
fn fail_mode_b_key_hex_missing_hard_errors() {
    let tmp = TempDir::new().unwrap();
    // 故意不寫 key.hex / Deliberately do not write key.hex.
    // 用一個假 fingerprint，因為 key.hex 不存在 verify path 不會走到 archive。
    // Use a dummy fingerprint; key.hex absent path returns Err before archive.
    let fingerprint = "deadbeefdeadbeef".to_string();
    let manifest_path = write_full_manifest(
        tmp.path(),
        &[
            ("experiment_id", serde_json::json!("exp_no_key")),
            ("data_tier", serde_json::json!("S2")),
            ("fixture_uri", serde_json::json!("fixtures/")),
            ("manifest_version", serde_json::json!(1)),
        ],
        &fingerprint,
        None,
    );

    let err = load_and_verify_manifest(&manifest_path)
        .err()
        .map(|e| e.to_string())
        .unwrap_or_default();
    assert!(
        err.contains("manifest_signer_key_missing"),
        "expected manifest_signer_key_missing fail-closed, got: {}",
        err
    );
}

/// Fail mode (c) — signature tampered (1 byte) → SignatureMismatch.
/// 簽名第 1 byte 改寫，body + hash 仍對 → 必走 signature_mismatch 而非
/// hash gate（hash gate 對 disk 內容算 ok）。
///
/// Fail mode (c) — signature tampered (1 byte) → SignatureMismatch.
/// Mutate sig first byte; body + declared_hash still consistent → must
/// fall through to signature_mismatch (not hash gate).
#[test]
fn fail_mode_c_signature_tampered_signature_mismatch() {
    let tmp = TempDir::new().unwrap();
    let (_key_path, fingerprint) = write_fixture_key(tmp.path());
    let manifest_path = write_full_manifest(
        tmp.path(),
        &[
            ("experiment_id", serde_json::json!("exp_sig_tamper")),
            ("data_tier", serde_json::json!("S2")),
            ("fixture_uri", serde_json::json!("fixtures/")),
            ("manifest_version", serde_json::json!(1)),
        ],
        &fingerprint,
        None,
    );

    // Parse manifest, tamper signature 1 byte, write back.
    // 讀回 manifest，改 signature 第 1 byte，寫回。
    let raw = std::fs::read_to_string(&manifest_path).unwrap();
    let mut value: serde_json::Value = serde_json::from_str(&raw).unwrap();
    let sig = value["signature"].as_str().unwrap().to_string();
    let mut tampered = sig.into_bytes();
    tampered[0] = if tampered[0] == b'a' { b'b' } else { b'a' };
    let tampered_sig = String::from_utf8(tampered).unwrap();
    value["signature"] = serde_json::Value::String(tampered_sig);
    let new_raw = serde_json::to_vec_pretty(&value).unwrap();
    std::fs::write(&manifest_path, new_raw).unwrap();

    let err = load_and_verify_manifest(&manifest_path)
        .err()
        .map(|e| e.to_string())
        .unwrap_or_default();
    assert!(
        err.contains("manifest_signer_verify_failed"),
        "expected verify_failed, got: {}",
        err
    );
    assert!(
        err.contains("signature_mismatch"),
        "expected signature_mismatch (hash gate must NOT fire when only \
         sig is tampered), got: {}",
        err
    );
}

/// Fail mode (d) — declared manifest_hash tampered (1 byte) → returns
/// manifest_hash_mismatch error label (sanity gate fires before
/// signer.verify).
///
/// Fail mode (d) — declared manifest_hash 改 1 byte → manifest_hash_mismatch
/// label 直接由 sanity gate（在 signer.verify 之前）回。
#[test]
fn fail_mode_d_declared_hash_tampered_manifest_hash_mismatch() {
    let tmp = TempDir::new().unwrap();
    let (_key_path, fingerprint) = write_fixture_key(tmp.path());
    let manifest_path = write_full_manifest(
        tmp.path(),
        &[
            ("experiment_id", serde_json::json!("exp_hash_tamper")),
            ("data_tier", serde_json::json!("S2")),
            ("fixture_uri", serde_json::json!("fixtures/")),
            ("manifest_version", serde_json::json!(1)),
        ],
        &fingerprint,
        None,
    );

    // Parse manifest, tamper manifest_hash 1 byte, write back.
    // 讀回 manifest，改 manifest_hash 第 1 byte，寫回。
    let raw = std::fs::read_to_string(&manifest_path).unwrap();
    let mut value: serde_json::Value = serde_json::from_str(&raw).unwrap();
    let hash = value["manifest_hash"].as_str().unwrap().to_string();
    let mut tampered = hash.into_bytes();
    tampered[0] = if tampered[0] == b'a' { b'b' } else { b'a' };
    let tampered_hash = String::from_utf8(tampered).unwrap();
    value["manifest_hash"] = serde_json::Value::String(tampered_hash);
    let new_raw = serde_json::to_vec_pretty(&value).unwrap();
    std::fs::write(&manifest_path, new_raw).unwrap();

    let err = load_and_verify_manifest(&manifest_path)
        .err()
        .map(|e| e.to_string())
        .unwrap_or_default();
    assert!(
        err.contains("manifest_hash_mismatch"),
        "expected manifest_hash_mismatch (sanity gate fires before \
         signer.verify), got: {}",
        err
    );
}

/// Cross-language byte-equal sanity:
/// canonical_body_for_signing(disk single-file manifest) reproduces
/// the exact bytes that Python sibling signer signed (sorted-keys +
/// compact + envelope stripped). This is THE invariant Track A's Python
/// `_write_manifest_fixture` MUST honor for verify to succeed.
///
/// 跨語言 byte-equal 健全性：對 disk 單檔 manifest 跑
/// canonical_body_for_signing，重現 Python sibling signer 簽時的精確
/// bytes（sorted-keys + compact + envelope stripped）。這是 Track A
/// `_write_manifest_fixture` 必對齊以使 verify 成功的核心不變量。
#[test]
fn canonical_body_byte_equal_to_python_sibling() {
    // 這個 byte sequence 必對應 Python:
    //   json.dumps(stripped, sort_keys=True, separators=(',', ':'),
    //              ensure_ascii=False).encode('utf-8')
    // 對 stripped = {"data_tier":"S2","experiment_id":"x","manifest_version":1}.
    let disk_full = br#"{
        "experiment_id": "x",
        "data_tier": "S2",
        "manifest_version": 1,
        "signature": "deadbeef",
        "manifest_hash": "cafebabe",
        "signature_key_ref": "fp_x"
    }"#;
    let canon = canonical_body_for_signing(disk_full).unwrap();
    let expected = br#"{"data_tier":"S2","experiment_id":"x","manifest_version":1}"#;
    assert_eq!(
        canon,
        expected,
        "canonical body drift: got {} expected {}",
        std::str::from_utf8(&canon).unwrap(),
        std::str::from_utf8(expected).unwrap()
    );
}

// ─── REF-20 Sprint B2 R5-T4 round 2 — manifest config blob tests ──

/// R5-T4 round 2 test 1: ReplayManifest happily parses manifests that
/// declare `strategy_params` as a JSON object. The blob is preserved
/// verbatim (no premature deserialise into StrategyParamsConfig); the
/// CLI flow does the typed deserialise + factory wire downstream.
/// 此 test 確保 manifest schema 接收 blob，CLI flow 在下游做型別反序列化。
///
/// R5-T4 round 2 test 1：ReplayManifest 接受帶 `strategy_params` JSON
/// object 的 manifest；blob 保留原樣（不提前反序列化），CLI flow 在
/// 下游做型別反序列化 + factory 接線。
#[test]
fn manifest_strategy_params_parses_into_typed_config() {
    // Arrange: minimal-valid manifest JSON with strategy_params blob
    // mimicking V049 register handler's `_replay_strategy_params`
    // injection (strategy_params has the same shape as
    // StrategyParamsConfig serde wire format).
    // 安排：含 strategy_params blob 的最小可解析 manifest JSON，模擬
    // V049 register handler `_replay_strategy_params` 注入。
    let raw = serde_json::json!({
        "experiment_id": "xp_round2_strat",
        "data_tier": "S2",
        "fixture_uri": "fixtures/x/",
        "signature": "deadbeef",
        "manifest_hash": "cafebabe",
        "signature_key_ref": "fp_x",
        "strategy": "grid_trading",
        "strategy_params": {
            "grid_trading": {
                "grid_levels": 17
            }
        }
    });

    // Act: parse via serde (mimics load_and_verify_manifest's
    // serde_json::from_str on disk bytes).
    // 動作：以 serde 解析（mimics load_and_verify_manifest）。
    let parsed: ReplayManifest = serde_json::from_str(&raw.to_string()).expect("manifest parses");
    let blob = parsed
        .strategy_params
        .as_ref()
        .expect("strategy_params present");

    // Now do the typed deserialise that CLI flow does. This proves
    // the wire format aligns with StrategyParamsConfig.
    // 驗 wire format 對齊 StrategyParamsConfig。
    let typed: StrategyParamsConfig = serde_json::from_value(blob.clone()).expect("blob → typed");
    assert_eq!(
        typed.grid_trading.grid_levels, 17,
        "grid_levels round-trip failed: got {} expected 17",
        typed.grid_trading.grid_levels,
    );
}

/// R5-T4 round 2 test 2: ReplayManifest accepts `risk_overrides` blob;
/// the typed deserialise into RiskConfig succeeds and downstream gates
/// see the override (e.g. `limits.position_size_max_pct`).
/// 同 test 1 但驗 risk_overrides → RiskConfig 的 wire format 對齊。
///
/// R5-T4 round 2 test 2：ReplayManifest 接受 `risk_overrides` blob；
/// 反序列化為 RiskConfig 後下游 gate（如 `limits.position_size_max_pct`）
/// 看到 override 值。
#[test]
fn manifest_risk_overrides_apply_to_risk_config() {
    let raw = serde_json::json!({
        "experiment_id": "xp_round2_risk",
        "data_tier": "S2",
        "fixture_uri": "fixtures/x/",
        "signature": "deadbeef",
        "manifest_hash": "cafebabe",
        "signature_key_ref": "fp_x",
        "strategy": "grid_trading",
        "risk_overrides": {
            "limits": {
                "position_size_max_pct": 7.5
            }
        }
    });
    let parsed: ReplayManifest = serde_json::from_str(&raw.to_string()).expect("manifest parses");
    let blob = parsed
        .risk_overrides
        .as_ref()
        .expect("risk_overrides present");
    let typed: RiskConfig = serde_json::from_value(blob.clone()).expect("blob → typed");
    let pct = typed.limits.position_size_max_pct;
    assert!(
        (pct - 7.5).abs() < 1e-9,
        "position_size_max_pct round-trip failed: got {} expected 7.5",
        pct,
    );
}

/// R5-T4 round 2 test 3: backward-compat — manifests WITHOUT the new
/// fields parse correctly (`#[serde(default)]` works) and yield None
/// for both blob options. This is the xlang 13/13 invariant: existing
/// fixtures don't grow the field, canonical_bytes unchanged.
/// R5-T4 round 2 test 3：向後相容 — 舊 manifest 無此欄位 parse 仍成功，
/// 兩 blob 為 None。確保 xlang 13/13 invariant：既有 fixture 不長出新
/// 欄位 → canonical_bytes 不變。
#[test]
fn manifest_legacy_fixture_without_blob_fields_still_parses() {
    let raw = serde_json::json!({
        "experiment_id": "xp_legacy",
        "data_tier": "S2",
        "fixture_uri": "fixtures/x/",
        "signature": "deadbeef",
        "manifest_hash": "cafebabe",
        "signature_key_ref": "fp_x"
    });
    let parsed: ReplayManifest = serde_json::from_str(&raw.to_string()).expect("legacy parses");
    assert!(
        parsed.strategy_params.is_none(),
        "expected None for absent strategy_params"
    );
    assert!(
        parsed.risk_overrides.is_none(),
        "expected None for absent risk_overrides"
    );
    // strategy is also absent → synthetic walker path engages.
    // strategy 亦缺 → synthetic walker 路徑啟用。
    assert!(parsed.strategy.is_none());
}
