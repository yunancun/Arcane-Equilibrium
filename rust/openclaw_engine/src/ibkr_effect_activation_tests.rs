//! W7-S4a option B HMAC effect-activation 簽名層單元測試（`ibkr_effect_activation`）。
//!
//! 覆蓋:canonical payload 決定性 + 版本前綴/欄序;compute_signature 自洽;constant_time_eq
//! （定時,非 short-circuit);verifier 正簽驗過 / 篡改簽名拒 / 錯金鑰拒 / **金鑰缺席 fail-closed**;
//! operation-binding（submit 簽名 ≠ cancel 簽名 → 拒）。全片零 IO/零 socket;金鑰以測試域注入。

use super::*;
use openclaw_types::IbkrActivationEnvelopeV1;

const TEST_KEY: &str = "test-ibkr-effect-signing-key-do-not-use-in-prod";

fn paper_envelope() -> IbkrActivationEnvelopeV1 {
    IbkrActivationEnvelopeV1::paper_effect_fixture()
}

// ── canonical payload ────────────────────────────────────────────────────────

#[test]
fn canonical_payload_has_version_prefix_and_binds_operation() {
    let e = paper_envelope();
    let submit = canonical_effect_payload(&e, BrokerOperation::PaperOrderSubmit);
    // 版本前綴（drift guard）。
    assert!(
        submit.starts_with(&format!("{EFFECT_SIG_PAYLOAD_VERSION}|")),
        "payload 必以版本前綴起始: {submit}"
    );
    // operation verb 入 payload → submit 與 cancel 的 payload 必不同（簽名綁定精確操作面）。
    let cancel = canonical_effect_payload(&e, BrokerOperation::PaperOrderCancel);
    assert_ne!(submit, cancel, "operation verb 未綁定進 payload");
    // 綁定欄可見（lane/broker/scope/nonce/expiry）。
    assert!(submit.contains("stock_etf_cash"));
    assert!(submit.contains("ibkr"));
    assert!(submit.contains("paper"));
    assert!(submit.contains(&e.activation_nonce));
    assert!(submit.contains(&e.expires_at_ms.to_string()));
}

#[test]
fn compute_signature_is_deterministic_and_64_hex() {
    let e = paper_envelope();
    let sig = compute_effect_signature(&e, BrokerOperation::PaperOrderSubmit, TEST_KEY);
    // HMAC-SHA256 hex = 64 chars。
    assert_eq!(sig.len(), 64);
    // 同 input 重算必同。
    let sig2 = compute_effect_signature(&e, BrokerOperation::PaperOrderSubmit, TEST_KEY);
    assert_eq!(sig, sig2);
    // 不同金鑰 → 不同簽名。
    let sig_other = compute_effect_signature(&e, BrokerOperation::PaperOrderSubmit, "other-key");
    assert_ne!(sig, sig_other);
}

// ── constant_time_eq（定時,非 short-circuit）────────────────────────────────────

#[test]
fn constant_time_eq_matches_and_rejects() {
    assert!(constant_time_eq(b"abc123", b"abc123"));
    // 等長但首位元組即不同 → false（且實作 XOR 全長,非首差提前返回）。
    assert!(!constant_time_eq(b"Xbc123", b"abc123"));
    // 等長但末位元組不同 → false（證比對走完全長）。
    assert!(!constant_time_eq(b"abc12X", b"abc123"));
    // 長度不等 → false。
    assert!(!constant_time_eq(b"abc", b"abc123"));
}

// ── verifier:正簽 / 篡改 / 錯金鑰 / 金鑰缺席 fail-closed ──────────────────────────

#[test]
fn verifier_accepts_valid_signature() {
    let e = paper_envelope();
    let sig = compute_effect_signature(&e, BrokerOperation::PaperOrderSubmit, TEST_KEY);
    let verifier = EffectSignatureVerifier::with_key(Some(TEST_KEY.to_string()), sig);
    assert_eq!(
        verifier.verify(&e, BrokerOperation::PaperOrderSubmit),
        Ok(())
    );
}

#[test]
fn verifier_rejects_tampered_signature() {
    let e = paper_envelope();
    let mut sig = compute_effect_signature(&e, BrokerOperation::PaperOrderSubmit, TEST_KEY);
    // 翻末位 hex 字元（篡改;確保與原值不同）。
    let last = sig.pop().expect("64-hex non-empty");
    sig.push(if last == 'f' { '0' } else { 'f' });
    let verifier = EffectSignatureVerifier::with_key(Some(TEST_KEY.to_string()), sig);
    assert_eq!(
        verifier.verify(&e, BrokerOperation::PaperOrderSubmit),
        Err(EffectAuthError::BadSignature)
    );
}

#[test]
fn verifier_rejects_wrong_key() {
    let e = paper_envelope();
    // 用 TEST_KEY 簽,用不同金鑰驗 → BadSignature（防偽授權)。
    let sig = compute_effect_signature(&e, BrokerOperation::PaperOrderSubmit, TEST_KEY);
    let verifier = EffectSignatureVerifier::with_key(Some("leaked-different-key".to_string()), sig);
    assert_eq!(
        verifier.verify(&e, BrokerOperation::PaperOrderSubmit),
        Err(EffectAuthError::BadSignature)
    );
}

#[test]
fn verifier_fail_closed_when_key_absent() {
    // CC-B1 fail-closed:金鑰 slot 缺席（None）→ SigningKeyMissing,絕不放行（即便簽名 hex 正確)。
    let e = paper_envelope();
    let sig = compute_effect_signature(&e, BrokerOperation::PaperOrderSubmit, TEST_KEY);
    let verifier = EffectSignatureVerifier::with_key(None, sig);
    assert_eq!(
        verifier.verify(&e, BrokerOperation::PaperOrderSubmit),
        Err(EffectAuthError::SigningKeyMissing)
    );
}

#[test]
fn verifier_rejects_operation_mismatch() {
    // submit 的簽名拿去驗 cancel → BadSignature（operation 綁定進 payload）。
    let e = paper_envelope();
    let submit_sig = compute_effect_signature(&e, BrokerOperation::PaperOrderSubmit, TEST_KEY);
    let verifier = EffectSignatureVerifier::with_key(Some(TEST_KEY.to_string()), submit_sig);
    assert_eq!(
        verifier.verify(&e, BrokerOperation::PaperOrderCancel),
        Err(EffectAuthError::BadSignature)
    );
}
