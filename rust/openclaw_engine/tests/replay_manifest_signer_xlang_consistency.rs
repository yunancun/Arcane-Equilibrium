//! REF-20 P2a-S2 cross-language consistency integration test.
//! REF-20 P2a-S2 跨語言一致性整合測試。
//!
//! MODULE_NOTE (EN):
//!   This integration test validates the V3 §12 acceptance #2 binding:
//!   `signature_verify` 4-fail-mode unit test PASS. It does so by loading
//!   a deterministic in-tree fixture (key + 3 manifest bodies + 3 golden
//!   signatures + 3 golden body hashes) and asserting:
//!     1. Rust `ManifestSigner::sign()` reproduces the golden signature
//!        byte-equal for all 3 fixture manifests.
//!     2. Rust `ManifestSigner::verify()` accepts the happy path.
//!     3. Each of the 4 fail-modes (`SignatureMismatch`,
//!        `ManifestHashMismatch`, `KeyMissing`, `KeyExpired`) fires under
//!        the spec'd condition.
//!
//!   The Python sibling test
//!   `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/
//!   replay/test_manifest_signer_xlang_consistency.py` consumes the same
//!   fixture and asserts the byte-equal invariant from the Python side.
//!   Together they enforce: same (canonical_bytes, key) → same signature
//!   tag across both implementations (HMAC-SHA256 byte-exact, 0 tolerance).
//!
//! MODULE_NOTE (中):
//!   本整合測試驗證 V3 §12 acceptance #2 binding：`signature_verify` 4
//!   fail-mode unit test PASS。透過載入 deterministic in-tree fixture
//!   （key + 3 manifest body + 3 golden signature + 3 golden body hash）
//!   並斷言：
//!     1. Rust `ManifestSigner::sign()` 對 3 個 fixture manifest 重現
//!        golden signature byte-equal。
//!     2. Rust `ManifestSigner::verify()` 接受 happy path。
//!     3. 4 種 fail-mode（`SignatureMismatch`、`ManifestHashMismatch`、
//!        `KeyMissing`、`KeyExpired`）各在規格條件下觸發。
//!
//!   Python sibling test 消費同一 fixture 並從 Python 側斷言 byte-equal
//!   不變量。兩者共同強制：對相同 (canonical_bytes, key)，兩 implementation
//!   產出相同 signature tag（HMAC-SHA256 byte-exact，0 容差）。
//!
//! Fixture 路徑 / Fixture path:
//!   `rust/openclaw_engine/tests/fixtures/replay_manifest_signer/`
//!
//! Run / 執行:
//!   `cargo test -p openclaw_engine --test replay_manifest_signer_xlang_consistency -- --nocapture`

use openclaw_engine::replay::manifest_signer::{
    compute_body_hash, compute_key_fingerprint, InMemoryKeyArchive, KeyStatus, ManifestSigner,
    SignatureFailMode,
};
use std::fs;
use std::path::PathBuf;

/// 取得 fixture 目錄絕對路徑。
/// Resolve absolute fixture directory path.
fn fixture_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixtures")
        .join("replay_manifest_signer")
}

/// 載入 fixture key + fingerprint，回 (signer, fingerprint)。
///
/// fingerprint 算法對齊 helper script `generate_replay_signing_key.sh` line
/// 91/93/111：對 **file content bytes**（含 trailing `\n`）做 sha256，取 first
/// 16 hex chars。HMAC key 仍用 decoded raw 32 bytes（key_hex.trim() 後 hex
/// decode）。
///
/// Load fixture key + fingerprint, return (signer, fingerprint).
///
/// fingerprint algorithm aligns with helper script
/// `generate_replay_signing_key.sh` line 91/93/111: sha256 over **file content
/// bytes** (including trailing `\n`), first 16 hex chars. HMAC key still uses
/// decoded raw 32 bytes (key_hex.trim() then hex decode).
fn load_fixture_signer() -> (ManifestSigner, String) {
    // 讀 file content as bytes — fingerprint 必對含 trailing newline 的整個檔案
    // 內容做 sha256（鏡像 `openssl dgst -sha256 -hex < key.hex`）。
    // Read file content as bytes — fingerprint must sha256 the entire file
    // content including trailing newline (mirrors `openssl dgst -sha256 -hex < key.hex`).
    let file_content = fs::read(fixture_dir().join("key.hex"))
        .expect("fixture key.hex missing");
    let key_hex = std::str::from_utf8(&file_content)
        .expect("fixture key.hex must be UTF-8")
        .trim()
        .to_string();
    let key_bytes = hex::decode(&key_hex).expect("fixture key not valid hex");

    // 不變量 / Invariant: V3 §5 demands 32-byte (256-bit) key.
    assert_eq!(
        key_bytes.len(),
        32,
        "fixture key must be 32 bytes (V3 §5 256-bit invariant)"
    );

    // fingerprint 對 file content bytes 算（含 trailing `\n`）。
    // fingerprint computed over file content bytes (including trailing `\n`).
    let fp = compute_key_fingerprint(&file_content);
    let expected_fp = fs::read_to_string(fixture_dir().join("fingerprint.txt"))
        .expect("fixture fingerprint.txt missing")
        .trim()
        .to_string();
    assert_eq!(fp, expected_fp, "fingerprint drift in fixture");

    let signer = ManifestSigner::new_from_bytes_for_test(key_bytes, fp.clone());
    (signer, fp)
}

/// 載入 fixture manifest #N 的 (body_bytes, golden_sig_hex, golden_hash_hex)。
/// Load fixture manifest #N: (body_bytes, golden_sig_hex, golden_hash_hex).
fn load_fixture_manifest(n: u32) -> (Vec<u8>, String, String) {
    let body = fs::read(fixture_dir().join(format!("manifest_{}.json", n)))
        .unwrap_or_else(|e| panic!("fixture manifest_{}.json missing: {}", n, e));
    let sig = fs::read_to_string(fixture_dir().join(format!("manifest_{}.sig", n)))
        .unwrap_or_else(|e| panic!("fixture manifest_{}.sig missing: {}", n, e))
        .trim()
        .to_string();
    let hash = fs::read_to_string(fixture_dir().join(format!("manifest_{}.hash", n)))
        .unwrap_or_else(|e| panic!("fixture manifest_{}.hash missing: {}", n, e))
        .trim()
        .to_string();
    (body, sig, hash)
}

#[test]
fn xlang_signature_byte_equal_for_all_fixtures() {
    // 對 3 個 fixture manifest，Rust sign 結果必 == golden sig（即 Python 端
    // 預先算好的 sig）→ 雙端 HMAC-SHA256 byte-equal 不變量。
    //
    // For 3 fixture manifests, Rust sign() result MUST == golden sig
    // (pre-computed Python-side sig) → cross-language HMAC-SHA256 byte-equal
    // invariant.
    let (signer, _fp) = load_fixture_signer();
    for n in 1..=3 {
        let (body, golden_sig, golden_hash) = load_fixture_manifest(n);

        let computed_sig = signer.sign(&body);
        assert_eq!(
            computed_sig, golden_sig,
            "manifest_{} signature drift: Rust computed {} != golden {}",
            n, computed_sig, golden_sig
        );

        let computed_hash = compute_body_hash(&body);
        assert_eq!(
            computed_hash, golden_hash,
            "manifest_{} body hash drift: Rust computed {} != golden {}",
            n, computed_hash, golden_hash
        );
    }
}

#[test]
fn happy_path_verify_passes_with_fixture() {
    let (signer, fp) = load_fixture_signer();
    let mut archive = InMemoryKeyArchive::new();
    archive.insert(&fp, KeyStatus::Active);

    for n in 1..=3 {
        let (body, golden_sig, golden_hash) = load_fixture_manifest(n);
        let result = signer.verify(&body, &golden_hash, &golden_sig, &fp, &archive);
        assert!(
            result.is_ok(),
            "manifest_{} happy-path verify failed: {:?}",
            n,
            result
        );
    }
}

#[test]
fn fail_mode_signature_mismatch_with_fixture() {
    // V3 §12 acceptance #2 mode 1/4: tamper signature 1 byte → SignatureMismatch.
    let (signer, fp) = load_fixture_signer();
    let mut archive = InMemoryKeyArchive::new();
    archive.insert(&fp, KeyStatus::Active);

    let (body, golden_sig, golden_hash) = load_fixture_manifest(1);
    let mut tampered = golden_sig.into_bytes();
    tampered[0] = if tampered[0] == b'a' { b'b' } else { b'a' };
    let tampered_sig = String::from_utf8(tampered).unwrap();

    let err = signer
        .verify(&body, &golden_hash, &tampered_sig, &fp, &archive)
        .unwrap_err();
    assert_eq!(err, SignatureFailMode::SignatureMismatch);
    assert_eq!(err.audit_label(), "signature_mismatch");
}

#[test]
fn fail_mode_manifest_hash_mismatch_with_fixture() {
    // V3 §12 acceptance #2 mode 2/4: tamper body 1 byte → ManifestHashMismatch.
    //
    // 設計：tamper body 後 caller 仍用 `golden_sig` 驗 — 但 sign() 用 tampered_body
    // 計算 → expected_sig == golden_sig（HMAC 對 tampered body 重算）才能進入
    // step 4，此時 declared hash（用 golden body 算的 hash）vs 實際 body
    // （tampered）vs caller 提供的 declared_hash 三者關係要設計清楚。
    //
    // 最直接的 case：caller 提供 `(tampered_body, declared_hash_of_tampered_body,
    // signature_of_original_body)` — signature 對 tampered_body 重算會 mismatch
    // → 不是純粹的 ManifestHashMismatch 路徑。
    //
    // 純粹的 ManifestHashMismatch 路徑：caller 提供 `(body_X, declared_hash_X,
    // signature_of_body_X)` 即「signature 對得上但 declared_hash 與重算 hash
    // 不符」。實作上：用 golden body + 原 sig + 改 1 byte 的 declared_hash。
    // 此時 sign(body) == golden_sig 通過 step 3，body hash != tampered_declared
    // → step 4 fail。
    //
    // Verify-step has two halves:
    //   step 3: recompute sig over body, check vs caller-supplied sig_hex.
    //   step 4: recompute hash over body, check vs caller-supplied declared_hash.
    //
    // To isolate ManifestHashMismatch: keep body unchanged + signature unchanged
    // (so step 3 passes) + tamper declared_hash 1 char.
    let (signer, fp) = load_fixture_signer();
    let mut archive = InMemoryKeyArchive::new();
    archive.insert(&fp, KeyStatus::Active);

    let (body, golden_sig, golden_hash) = load_fixture_manifest(1);
    let mut tampered = golden_hash.into_bytes();
    tampered[0] = if tampered[0] == b'a' { b'b' } else { b'a' };
    let tampered_hash = String::from_utf8(tampered).unwrap();

    let err = signer
        .verify(&body, &tampered_hash, &golden_sig, &fp, &archive)
        .unwrap_err();
    assert_eq!(err, SignatureFailMode::ManifestHashMismatch);
    assert_eq!(err.audit_label(), "manifest_hash_mismatch");
}

#[test]
fn fail_mode_key_missing_with_fixture() {
    // V3 §12 acceptance #2 mode 3/4: fingerprint not in archive → KeyMissing.
    let (signer, fp) = load_fixture_signer();
    let empty_archive = InMemoryKeyArchive::new();

    let (body, golden_sig, golden_hash) = load_fixture_manifest(1);
    let err = signer
        .verify(&body, &golden_hash, &golden_sig, &fp, &empty_archive)
        .unwrap_err();
    assert_eq!(err, SignatureFailMode::KeyMissing);
    assert_eq!(err.audit_label(), "key_missing");
}

#[test]
fn fail_mode_key_expired_with_fixture() {
    // V3 §12 acceptance #2 mode 4/4: fingerprint in archive with expired status
    // → KeyExpired.
    let (signer, fp) = load_fixture_signer();
    let mut archive = InMemoryKeyArchive::new();
    archive.insert(&fp, KeyStatus::Expired);

    let (body, golden_sig, golden_hash) = load_fixture_manifest(1);
    let err = signer
        .verify(&body, &golden_hash, &golden_sig, &fp, &archive)
        .unwrap_err();
    assert_eq!(err, SignatureFailMode::KeyExpired);
    assert_eq!(err.audit_label(), "key_expired");
}

#[test]
fn fingerprint_helper_matches_fixture() {
    // 驗證 fingerprint helper 與 fixture 中存的 expected fingerprint 一致。
    // Sanity-check fingerprint helper against fixture-stored expected fingerprint.
    let (_signer, fp) = load_fixture_signer();
    let expected_fp = fs::read_to_string(fixture_dir().join("fingerprint.txt"))
        .unwrap()
        .trim()
        .to_string();
    assert_eq!(fp, expected_fp);
    assert_eq!(fp.len(), 16);
}

#[test]
fn verify_order_invariant_signature_before_hash_with_fixture() {
    // V3 §5 verify-order invariant: 先 signature 後 manifest hash。
    // 同時 tamper signature 與 declared hash 時必先報 SignatureMismatch。
    //
    // V3 §5 verify-order invariant: signature first, then manifest hash.
    // When BOTH signature and declared hash are tampered, the error MUST be
    // SignatureMismatch (sig is checked first).
    let (signer, fp) = load_fixture_signer();
    let mut archive = InMemoryKeyArchive::new();
    archive.insert(&fp, KeyStatus::Active);

    let (body, golden_sig, golden_hash) = load_fixture_manifest(1);

    let mut tampered_sig = golden_sig.into_bytes();
    tampered_sig[0] = if tampered_sig[0] == b'a' { b'b' } else { b'a' };
    let mut tampered_hash = golden_hash.into_bytes();
    tampered_hash[0] = if tampered_hash[0] == b'a' { b'b' } else { b'a' };

    let err = signer
        .verify(
            &body,
            std::str::from_utf8(&tampered_hash).unwrap(),
            std::str::from_utf8(&tampered_sig).unwrap(),
            &fp,
            &archive,
        )
        .unwrap_err();
    assert_eq!(
        err,
        SignatureFailMode::SignatureMismatch,
        "V3 §5 verify-order: signature MUST be checked before declared hash"
    );
}
