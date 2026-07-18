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
    // 必修-1:版本前綴 = v2（簽名覆蓋擴欄後 bump;drift guard）。
    assert_eq!(EFFECT_SIG_PAYLOAD_VERSION, 2);
    assert!(
        submit.starts_with("2|"),
        "payload 必以 v2 版本前綴起始: {submit}"
    );
    // operation verb 入 payload → submit 與 cancel 的 payload 必不同（簽名綁定精確操作面）。
    let cancel = canonical_effect_payload(&e, BrokerOperation::PaperOrderCancel);
    assert_ne!(submit, cancel, "operation verb 未綁定進 payload");
    // 24 欄（23 pipe 分隔）。
    assert_eq!(
        submit.split('|').count(),
        24,
        "canonical payload v2 應為 24 欄"
    );
    // 綁定欄可見（core + 必修-1 擴欄:session/risk/額度/三 lineage/operator）。
    for needle in [
        "stock_etf_cash",
        "ibkr",
        "paper",
        e.activation_nonce.as_str(),
        e.session_attestation_fingerprint.as_str(),
        e.risk_config_hash.as_str(),
        e.max_order_notional_usd_decimal.as_str(),
        e.max_position_notional_usd_decimal.as_str(),
        e.cost_gate_lineage.as_str(),
        e.guardian_lineage.as_str(),
        e.decision_lease_lineage.as_str(),
        e.operator_identity.as_str(),
    ] {
        assert!(
            submit.contains(needle),
            "payload 缺綁定欄 {needle:?}: {submit}"
        );
    }
    assert!(submit.contains(&e.expires_at_ms.to_string()));
}

#[test]
fn verifier_rejects_tamper_of_each_newly_signed_binding_field() {
    // 必修-1:對每一新簽綁定欄做「簽後竄改為另一有效格式值」→ shape 仍過但重算 payload 變 →
    // 簽名失效（BadSignature）。證持 (envelope,sig) 者無法竄改任一綁定欄再驗過（tamper-proof）。
    let e = paper_envelope();
    let op = BrokerOperation::PaperOrderSubmit;
    let sig = compute_effect_signature(&e, op, TEST_KEY);

    let mutations: Vec<(&str, fn(&mut IbkrActivationEnvelopeV1))> = vec![
        ("session_attestation_fingerprint", |e| {
            e.session_attestation_fingerprint = "9".repeat(64)
        }),
        ("risk_config_hash", |e| e.risk_config_hash = "9".repeat(64)),
        ("max_order_notional", |e| {
            e.max_order_notional_usd_decimal = "2000".into()
        }),
        ("max_position_notional", |e| {
            e.max_position_notional_usd_decimal = "9999".into()
        }),
        ("max_orders_per_day", |e| e.max_orders_per_day = 99),
        ("cost_gate_lineage", |e| {
            e.cost_gate_lineage = "9".repeat(64)
        }),
        ("guardian_lineage", |e| e.guardian_lineage = "9".repeat(64)),
        ("decision_lease_lineage", |e| {
            e.decision_lease_lineage = "9".repeat(64)
        }),
        ("operator_identity", |e| {
            e.operator_identity = "operator:evil".into()
        }),
    ];
    for (name, mutate) in mutations {
        let mut tampered = paper_envelope();
        mutate(&mut tampered);
        let verifier = EffectSignatureVerifier::with_key(Some(TEST_KEY.to_string()), sig.clone());
        assert_eq!(
            verifier.verify(&tampered, op),
            Err(EffectAuthError::BadSignature),
            "竄改 {name} 後簽名必失效（BadSignature）"
        );
    }
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
