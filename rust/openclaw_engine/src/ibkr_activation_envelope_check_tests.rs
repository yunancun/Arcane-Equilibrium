//! W8a activation envelope 驗證器測試（`ibkr_activation_envelope_check` 專屬;
//! `#[cfg(test)]` 經 path attribute 掛入）。
//!
//! 覆蓋:接受路徑 + nonce 消費/replay 拒 + 併發競態（恰一勝出）+ envelope 缺席 +
//! **seal 在位無 envelope → 拒**（seal≠活化機器證明）+ build SHA/兩 epoch 逐綁定拒 +
//! **readonly envelope + 任何 order verb → 結構性拒**（窮舉）+ deny path 不燒 nonce。
//! 全部時刻注入（fixture epoch ms 常量,無牆鐘,非 time-bomb）。

use std::sync::Arc;

use openclaw_types::{
    BrokerOperation, IbkrActivationEnvelopeBlocker, IbkrActivationEnvelopeV1,
    IbkrActivationOperationScopeV1,
};

use super::{
    check_effect_contact, check_readonly_contact, ActivationCheckPosture, ActivationNonceLedger,
    EffectCheckBlocker as EB, IbkrActivationCheckBlocker as B,
};
use crate::ibkr_effect_activation::{compute_effect_signature, EffectSignatureVerifier};

/// fixture 有效窗內的注入時刻（issued + 10min;同 types acceptance）。
const NOW_IN_WINDOW_MS: u64 = 1_772_232_600_000;

fn envelope() -> IbkrActivationEnvelopeV1 {
    IbkrActivationEnvelopeV1::readonly_fixture()
}

/// 與 fixture 全綁定相符的姿態（seal 缺席;各測試按需變異）。
fn matching_posture() -> ActivationCheckPosture {
    ActivationCheckPosture {
        now_ms: NOW_IN_WINDOW_MS,
        current_build_git_sha: "f".repeat(40),
        current_revocation_epoch: 1,
        current_kill_switch_epoch: 1,
        phase2_seal_present: false,
    }
}

// ---------------------------------------------------------------------------
// 接受路徑 + nonce 消費/replay
// ---------------------------------------------------------------------------

#[test]
fn accepted_readonly_contact_consumes_nonce_and_replay_is_denied() {
    let e = envelope();
    let posture = matching_posture();
    let ledger = ActivationNonceLedger::new();

    let first = check_readonly_contact(
        Some(&e),
        BrokerOperation::AccountSnapshotRead,
        &posture,
        &ledger,
    );
    assert!(first.activation_accepted, "blockers: {:?}", first.blockers);
    assert!(ledger.is_consumed(&e.activation_nonce));

    // 同 nonce 二次驗證 = replay → 必拒（reconnect/scope 變更需新 envelope 新 nonce）。
    let replay = check_readonly_contact(
        Some(&e),
        BrokerOperation::AccountSnapshotRead,
        &posture,
        &ledger,
    );
    assert!(!replay.activation_accepted);
    assert_eq!(replay.blockers, vec![B::NonceAlreadyConsumed]);
}

#[test]
fn nonce_consumption_is_atomic_under_concurrent_race() {
    // 併發競態:同一 envelope/nonce,16 執行緒同時裁決 → 恰一個放行,其餘全拒。
    let e = Arc::new(envelope());
    let posture = Arc::new(matching_posture());
    let ledger = Arc::new(ActivationNonceLedger::new());

    let mut handles = Vec::new();
    for _ in 0..16 {
        let e = Arc::clone(&e);
        let posture = Arc::clone(&posture);
        let ledger = Arc::clone(&ledger);
        handles.push(std::thread::spawn(move || {
            check_readonly_contact(Some(&e), BrokerOperation::MarketDataRead, &posture, &ledger)
                .activation_accepted
        }));
    }
    let accepted = handles
        .into_iter()
        .map(|h| h.join().expect("thread join"))
        .filter(|ok| *ok)
        .count();
    assert_eq!(accepted, 1, "同 nonce 併發下必須恰一勝出（原子消費）");
}

// ---------------------------------------------------------------------------
// envelope 缺席 + seal≠活化
// ---------------------------------------------------------------------------

#[test]
fn absent_envelope_is_denied_without_touching_ledger() {
    let ledger = ActivationNonceLedger::new();
    let verdict = check_readonly_contact(
        None,
        BrokerOperation::HealthRead,
        &matching_posture(),
        &ledger,
    );
    assert!(!verdict.activation_accepted);
    assert_eq!(verdict.blockers, vec![B::EnvelopeAbsent]);
}

#[test]
fn seal_in_place_without_envelope_is_denied_seal_is_not_activation_authority() {
    // seal≠活化機器證明:sealed Phase-2 PASS artifact 在位 + 無 envelope → 接觸拒絕。
    let mut posture = matching_posture();
    posture.phase2_seal_present = true;
    let ledger = ActivationNonceLedger::new();

    let verdict = check_readonly_contact(None, BrokerOperation::HealthRead, &posture, &ledger);
    assert!(!verdict.activation_accepted);
    assert!(verdict.blockers.contains(&B::EnvelopeAbsent));
    assert!(verdict.blockers.contains(&B::SealIsNotActivationAuthority));
}

#[test]
fn seal_in_place_with_valid_envelope_does_not_block() {
    // seal 是 Phase-2 pre-contact gate 事實,與 envelope 正交:在位不加分也不擋有效活化。
    let mut posture = matching_posture();
    posture.phase2_seal_present = true;
    let e = envelope();
    let ledger = ActivationNonceLedger::new();

    let verdict = check_readonly_contact(Some(&e), BrokerOperation::HealthRead, &posture, &ledger);
    assert!(
        verdict.activation_accepted,
        "blockers: {:?}",
        verdict.blockers
    );
}

// ---------------------------------------------------------------------------
// readonly + order verb → 結構性拒（窮舉;deny 不燒 nonce）
// ---------------------------------------------------------------------------

#[test]
fn every_order_verb_is_structurally_denied_and_never_consumes_nonce() {
    use BrokerOperation as Op;
    let e = envelope();
    let posture = matching_posture();
    let ledger = ActivationNonceLedger::new();

    for op in [
        Op::PaperOrderSubmit,
        Op::PaperOrderCancel,
        Op::PaperOrderReplace,
        Op::LiveOrderSubmit,
        Op::MarginOrShort,
        Op::OptionsOrCfd,
        Op::TransferOrAccountWrite,
    ] {
        let verdict = check_readonly_contact(Some(&e), op, &posture, &ledger);
        assert!(
            !verdict.activation_accepted,
            "order verb {op:?} 必須結構性拒"
        );
        assert_eq!(
            verdict.blockers,
            vec![B::OrderVerbStructurallyDenied],
            "order verb {op:?}"
        );
        // deny path 不燒 nonce。
        assert!(!ledger.is_consumed(&e.activation_nonce));
    }

    // 同一 envelope 的合法唯讀操作仍可放行（order verb 拒絕未汙染 nonce）。
    let ok = check_readonly_contact(Some(&e), Op::MarketDataRead, &posture, &ledger);
    assert!(ok.activation_accepted);
}

#[test]
fn non_order_operations_outside_readonly_scope_are_denied() {
    use BrokerOperation as Op;
    let e = envelope();
    let posture = matching_posture();
    let ledger = ActivationNonceLedger::new();

    for op in [
        Op::PaperOrderFillImport,
        Op::ShadowSignalEmit,
        Op::ShadowFillReconstruct,
        Op::ScorecardDerive,
    ] {
        let verdict = check_readonly_contact(Some(&e), op, &posture, &ledger);
        assert!(!verdict.activation_accepted, "{op:?} 不屬唯讀接觸面");
        assert_eq!(verdict.blockers, vec![B::OperationOutsideReadonlyScope]);
        assert!(!ledger.is_consumed(&e.activation_nonce));
    }
}

// ---------------------------------------------------------------------------
// 姿態綁定逐一拒:build SHA / revocation epoch / kill-switch epoch
// ---------------------------------------------------------------------------

#[test]
fn build_sha_mismatch_is_denied_and_does_not_burn_nonce() {
    let e = envelope();
    let ledger = ActivationNonceLedger::new();

    let mut wrong = matching_posture();
    wrong.current_build_git_sha = "0".repeat(40);
    let verdict = check_readonly_contact(Some(&e), BrokerOperation::HealthRead, &wrong, &ledger);
    assert!(!verdict.activation_accepted);
    assert_eq!(verdict.blockers, vec![B::BuildGitShaMismatch]);

    // deny 未燒 nonce:改回相符姿態即可放行（證明拒絕路徑零副作用）。
    let ok = check_readonly_contact(
        Some(&e),
        BrokerOperation::HealthRead,
        &matching_posture(),
        &ledger,
    );
    assert!(ok.activation_accepted);
}

#[test]
fn revocation_epoch_mismatch_is_denied_in_both_directions() {
    let e = envelope(); // 綁定 epoch = 1
    let ledger = ActivationNonceLedger::new();

    // envelope 落後於當前(已被撤銷)。
    let mut revoked = matching_posture();
    revoked.current_revocation_epoch = 2;
    let verdict = check_readonly_contact(Some(&e), BrokerOperation::HealthRead, &revoked, &ledger);
    assert_eq!(verdict.blockers, vec![B::RevocationEpochMismatch]);

    // envelope 超前於當前(偽造/時序錯亂)——同樣拒。
    let mut ahead = matching_posture();
    ahead.current_revocation_epoch = 0;
    let verdict = check_readonly_contact(Some(&e), BrokerOperation::HealthRead, &ahead, &ledger);
    assert_eq!(verdict.blockers, vec![B::RevocationEpochMismatch]);
}

#[test]
fn kill_switch_epoch_mismatch_is_denied() {
    let e = envelope();
    let ledger = ActivationNonceLedger::new();

    let mut killed = matching_posture();
    killed.current_kill_switch_epoch = 2;
    let verdict = check_readonly_contact(Some(&e), BrokerOperation::HealthRead, &killed, &ledger);
    assert!(!verdict.activation_accepted);
    assert_eq!(verdict.blockers, vec![B::KillSwitchEpochMismatch]);
    assert!(!ledger.is_consumed(&e.activation_nonce));
}

// ---------------------------------------------------------------------------
// 契約 shape/時窗 blocker 嵌套投影
// ---------------------------------------------------------------------------

#[test]
fn expired_envelope_is_denied_via_nested_contract_blocker() {
    let e = envelope();
    let mut posture = matching_posture();
    posture.now_ms = e.expires_at_ms; // now == expires 即過期(含界拒)
    let ledger = ActivationNonceLedger::new();

    let verdict = check_readonly_contact(Some(&e), BrokerOperation::HealthRead, &posture, &ledger);
    assert!(!verdict.activation_accepted);
    assert!(verdict.blockers.contains(&B::EnvelopeContract(
        IbkrActivationEnvelopeBlocker::EnvelopeExpired
    )));
    assert!(!ledger.is_consumed(&e.activation_nonce));
}

#[test]
fn default_envelope_projects_every_shape_blocker_and_is_denied() {
    let e = IbkrActivationEnvelopeV1::default();
    let ledger = ActivationNonceLedger::new();

    let verdict = check_readonly_contact(
        Some(&e),
        BrokerOperation::HealthRead,
        &matching_posture(),
        &ledger,
    );
    assert!(!verdict.activation_accepted);
    // shape 面逐欄拒因保真嵌套(單一校驗真源在 types validate)。
    for expected in [
        B::EnvelopeContract(IbkrActivationEnvelopeBlocker::ContractIdMismatch),
        B::EnvelopeContract(IbkrActivationEnvelopeBlocker::OperationScopeDenied),
        B::EnvelopeContract(IbkrActivationEnvelopeBlocker::ActivationNonceInvalid),
        B::EnvelopeContract(IbkrActivationEnvelopeBlocker::MissingIssuedAt),
    ] {
        assert!(verdict.blockers.contains(&expected), "缺 {expected:?}");
    }
    // default 的 build sha 為空 ≠ 現 binary sha → 姿態面也拒。
    assert!(verdict.blockers.contains(&B::BuildGitShaMismatch));
}

// ═══════════════════════════════════════════════════════════════════════════
// W7-S4a effect 面裁決（check_effect_contact;§4 option B HMAC）
// ═══════════════════════════════════════════════════════════════════════════

const EFFECT_TEST_KEY: &str = "test-ibkr-effect-signing-key-do-not-use-in-prod";

fn paper_envelope() -> IbkrActivationEnvelopeV1 {
    IbkrActivationEnvelopeV1::paper_effect_fixture()
}

/// paper fixture 全綁定相符的姿態（seal 缺席）。
fn paper_posture() -> ActivationCheckPosture {
    ActivationCheckPosture {
        now_ms: NOW_IN_WINDOW_MS,
        current_build_git_sha: "f".repeat(40),
        current_revocation_epoch: 1,
        current_kill_switch_epoch: 1,
        phase2_seal_present: false,
    }
}

/// 對指定 envelope/operation 以測試金鑰算正確簽名並包成 verifier（正簽路徑）。
fn valid_verifier(e: &IbkrActivationEnvelopeV1, op: BrokerOperation) -> EffectSignatureVerifier {
    let sig = compute_effect_signature(e, op, EFFECT_TEST_KEY);
    EffectSignatureVerifier::with_key(Some(EFFECT_TEST_KEY.to_string()), sig)
}

// ── 全過放行 + nonce 消費 + replay 拒 ────────────────────────────────────────

#[test]
fn accepted_paper_effect_mints_permit_consumes_nonce_and_replay_denied() {
    let e = paper_envelope();
    let posture = paper_posture();
    let ledger = ActivationNonceLedger::new();
    let op = BrokerOperation::PaperOrderSubmit;

    let first = check_effect_contact(Some(&e), op, &posture, &ledger, &valid_verifier(&e, op));
    assert!(first.is_accepted(), "blockers: {:?}", first.blockers());
    assert!(ledger.is_consumed(&e.activation_nonce));

    // 同 nonce 二次（正簽）= replay → 必拒（reconnect/scope 變更需新 envelope 新 nonce）。
    let replay = check_effect_contact(Some(&e), op, &posture, &ledger, &valid_verifier(&e, op));
    assert!(!replay.is_accepted());
    assert_eq!(replay.blockers(), vec![EB::NonceAlreadyConsumed]);
}

// ── envelope 缺席 + seal≠活化（CC-B4）─────────────────────────────────────────

#[test]
fn absent_effect_envelope_denied_and_seal_is_not_activation_authority() {
    let ledger = ActivationNonceLedger::new();
    let op = BrokerOperation::PaperOrderSubmit;
    let e = paper_envelope();
    let verifier = valid_verifier(&e, op);

    // 無 envelope + 無 seal。
    let v = check_effect_contact(None, op, &paper_posture(), &ledger, &verifier);
    assert!(!v.is_accepted());
    assert_eq!(v.blockers(), vec![EB::EffectEnvelopeAbsent]);

    // CC-B4:sealed Phase-2 PASS 在位 + 無 effect envelope → order 拒（seal≠活化）。
    let mut sealed = paper_posture();
    sealed.phase2_seal_present = true;
    let v = check_effect_contact(None, op, &sealed, &ledger, &verifier);
    assert!(!v.is_accepted());
    assert!(v.blockers().contains(&EB::EffectEnvelopeAbsent));
    assert!(v.blockers().contains(&EB::SealIsNotActivationAuthority));
}

// ── readonly envelope + order verb → OrderVerbStructurallyDenied（§1.4 item 4）───

#[test]
fn readonly_scope_envelope_plus_order_verb_is_structurally_denied() {
    let e = IbkrActivationEnvelopeV1::readonly_fixture(); // scope=Readonly
    let ledger = ActivationNonceLedger::new();
    for op in [
        BrokerOperation::PaperOrderSubmit,
        BrokerOperation::PaperOrderCancel,
        BrokerOperation::PaperOrderReplace,
    ] {
        let v = check_effect_contact(
            Some(&e),
            op,
            &matching_posture(),
            &ledger,
            &valid_verifier(&e, op),
        );
        assert!(!v.is_accepted(), "readonly+{op:?} 必拒");
        assert_eq!(
            v.blockers(),
            vec![EB::OrderVerbStructurallyDenied],
            "readonly+{op:?}"
        );
        // 結構性拒不燒 nonce。
        assert!(!ledger.is_consumed(&e.activation_nonce));
    }
}

// ── 永久 denied verb（margin/short/options/cfd/transfer/live）→ 結構拒 ──────────

#[test]
fn permanently_denied_verbs_are_structurally_denied_under_any_scope() {
    let ledger = ActivationNonceLedger::new();
    for scope_env in [
        IbkrActivationEnvelopeV1::paper_effect_fixture(),
        IbkrActivationEnvelopeV1::readonly_fixture(),
    ] {
        for op in [
            BrokerOperation::LiveOrderSubmit,
            BrokerOperation::MarginOrShort,
            BrokerOperation::OptionsOrCfd,
            BrokerOperation::TransferOrAccountWrite,
        ] {
            let v = check_effect_contact(
                Some(&scope_env),
                op,
                &paper_posture(),
                &ledger,
                &valid_verifier(&scope_env, op),
            );
            assert!(!v.is_accepted(), "{op:?} 必拒");
            assert_eq!(v.blockers(), vec![EB::PermanentlyDeniedVerb], "{op:?}");
        }
    }
}

#[test]
fn paper_scope_non_order_operation_is_outside_effect_scope() {
    let e = paper_envelope();
    let ledger = ActivationNonceLedger::new();
    let op = BrokerOperation::MarketDataRead;
    let v = check_effect_contact(
        Some(&e),
        op,
        &paper_posture(),
        &ledger,
        &valid_verifier(&e, op),
    );
    assert!(!v.is_accepted());
    assert_eq!(v.blockers(), vec![EB::OperationOutsideEffectScope]);
}

#[test]
fn unknown_scope_envelope_is_effect_scope_denied() {
    let mut e = paper_envelope();
    e.operation_scope = IbkrActivationOperationScopeV1::UnknownDenied;
    let ledger = ActivationNonceLedger::new();
    let op = BrokerOperation::PaperOrderSubmit;
    let v = check_effect_contact(
        Some(&e),
        op,
        &paper_posture(),
        &ledger,
        &valid_verifier(&e, op),
    );
    assert!(!v.is_accepted());
    assert_eq!(v.blockers(), vec![EB::EffectScopeDenied]);
}

// ── option B HMAC 簽名:篡改拒 / 金鑰缺席 fail-closed（deny 不燒 nonce）──────────

#[test]
fn tampered_signature_is_denied_without_burning_nonce() {
    let e = paper_envelope();
    let ledger = ActivationNonceLedger::new();
    let op = BrokerOperation::PaperOrderSubmit;
    // 用錯金鑰簽 → 驗證端（正確金鑰）算出的期望值不符 → SignatureInvalid。
    let bad_sig = compute_effect_signature(&e, op, "attacker-key");
    let verifier = EffectSignatureVerifier::with_key(Some(EFFECT_TEST_KEY.to_string()), bad_sig);
    let v = check_effect_contact(Some(&e), op, &paper_posture(), &ledger, &verifier);
    assert!(!v.is_accepted());
    assert_eq!(v.blockers(), vec![EB::SignatureInvalid]);
    // 簽名失敗 deny path 不燒 nonce。
    assert!(!ledger.is_consumed(&e.activation_nonce));
}

#[test]
fn missing_signing_key_is_fail_closed_and_does_not_burn_nonce() {
    // CC-B1:金鑰 slot 缺席（None）→ SigningKeyMissing,絕不放行（即便簽名 hex 正確）。
    let e = paper_envelope();
    let ledger = ActivationNonceLedger::new();
    let op = BrokerOperation::PaperOrderSubmit;
    let sig = compute_effect_signature(&e, op, EFFECT_TEST_KEY);
    let verifier = EffectSignatureVerifier::with_key(None, sig);
    let v = check_effect_contact(Some(&e), op, &paper_posture(), &ledger, &verifier);
    assert!(!v.is_accepted());
    assert_eq!(v.blockers(), vec![EB::SigningKeyMissing]);
    assert!(!ledger.is_consumed(&e.activation_nonce));
}

// ── shape/posture 綁定逐一拒（expired / build sha / epoch）不燒 nonce ─────────────

#[test]
fn expired_paper_envelope_is_denied_via_nested_contract_blocker() {
    let e = paper_envelope();
    let mut posture = paper_posture();
    posture.now_ms = e.expires_at_ms; // now==expires 即過期(含界拒)
    let ledger = ActivationNonceLedger::new();
    let op = BrokerOperation::PaperOrderSubmit;
    let v = check_effect_contact(Some(&e), op, &posture, &ledger, &valid_verifier(&e, op));
    assert!(!v.is_accepted());
    assert!(v.blockers().contains(&EB::EnvelopeContract(
        IbkrActivationEnvelopeBlocker::EnvelopeExpired
    )));
    assert!(!ledger.is_consumed(&e.activation_nonce));
}

#[test]
fn effect_posture_mismatches_are_denied_and_do_not_burn_nonce() {
    let e = paper_envelope();
    let op = BrokerOperation::PaperOrderSubmit;

    // build sha 不符。
    let mut wrong = paper_posture();
    wrong.current_build_git_sha = "0".repeat(40);
    let ledger = ActivationNonceLedger::new();
    let v = check_effect_contact(Some(&e), op, &wrong, &ledger, &valid_verifier(&e, op));
    assert!(!v.is_accepted());
    assert!(v.blockers().contains(&EB::BuildGitShaMismatch));
    assert!(!ledger.is_consumed(&e.activation_nonce));

    // revocation epoch 不符（超前/落後皆拒——此處超前）。
    let mut revoked = paper_posture();
    revoked.current_revocation_epoch = 2;
    let v = check_effect_contact(Some(&e), op, &revoked, &ledger, &valid_verifier(&e, op));
    assert!(v.blockers().contains(&EB::RevocationEpochMismatch));

    // kill-switch epoch 不符。
    let mut killed = paper_posture();
    killed.current_kill_switch_epoch = 2;
    let v = check_effect_contact(Some(&e), op, &killed, &ledger, &valid_verifier(&e, op));
    assert!(v.blockers().contains(&EB::KillSwitchEpochMismatch));
}

// ── 併發:同 nonce 全過裁決,恰一勝出（原子消費）───────────────────────────────

#[test]
fn effect_nonce_consumption_is_atomic_under_concurrent_race() {
    use std::sync::Arc;
    let e = Arc::new(paper_envelope());
    let posture = Arc::new(paper_posture());
    let ledger = Arc::new(ActivationNonceLedger::new());
    let op = BrokerOperation::PaperOrderSubmit;

    let mut handles = Vec::new();
    for _ in 0..16 {
        let e = Arc::clone(&e);
        let posture = Arc::clone(&posture);
        let ledger = Arc::clone(&ledger);
        handles.push(std::thread::spawn(move || {
            let verifier = valid_verifier(&e, op);
            check_effect_contact(Some(&e), op, &posture, &ledger, &verifier).is_accepted()
        }));
    }
    let accepted = handles
        .into_iter()
        .map(|h| h.join().expect("thread join"))
        .filter(|ok| *ok)
        .count();
    assert_eq!(accepted, 1, "同 nonce 併發下必須恰一勝出（原子消費）");
}

// ── CC-B4 擴 effect 面:sealed-P2 在位 + 有效 paper envelope 不擋（seal 正交）───────

#[test]
fn seal_in_place_with_valid_paper_envelope_still_activates() {
    let e = paper_envelope();
    let mut posture = paper_posture();
    posture.phase2_seal_present = true; // seal 在位（Phase-2 pre-contact gate 事實）
    let ledger = ActivationNonceLedger::new();
    let op = BrokerOperation::PaperOrderSubmit;
    let v = check_effect_contact(Some(&e), op, &posture, &ledger, &valid_verifier(&e, op));
    assert!(
        v.is_accepted(),
        "seal 在位不應擋有效 effect 活化: {:?}",
        v.blockers()
    );
}
