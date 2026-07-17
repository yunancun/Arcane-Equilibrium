//! W8a activation envelope 驗證器測試（`ibkr_activation_envelope_check` 專屬;
//! `#[cfg(test)]` 經 path attribute 掛入）。
//!
//! 覆蓋:接受路徑 + nonce 消費/replay 拒 + 併發競態（恰一勝出）+ envelope 缺席 +
//! **seal 在位無 envelope → 拒**（seal≠活化機器證明）+ build SHA/兩 epoch 逐綁定拒 +
//! **readonly envelope + 任何 order verb → 結構性拒**（窮舉）+ deny path 不燒 nonce。
//! 全部時刻注入（fixture epoch ms 常量,無牆鐘,非 time-bomb）。

use std::sync::Arc;

use openclaw_types::{BrokerOperation, IbkrActivationEnvelopeBlocker, IbkrActivationEnvelopeV1};

use super::{
    check_readonly_contact, ActivationCheckPosture, ActivationNonceLedger,
    IbkrActivationCheckBlocker as B,
};

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
