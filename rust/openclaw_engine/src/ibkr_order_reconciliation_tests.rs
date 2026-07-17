//! W7-S3 三向對賬引擎測試（一）：P0-C 孤兒 / 三向 join / 幻影 P0-A / F1·F2 持久凍結 / 裁決。
//! Deletion-test 精神=幻影倉 P0 復現（cancel 後 late-fill / re-open remaining↑ → 拒 + 持久凍結 +
//! 記帳無幻影污染 + chain 完整）。共用建構子見 `_test_helpers`。

use openclaw_types::{BrokerOperation, IbkrPaperOrderLifecycleState as St};

use super::test_helpers::*;
use super::*;

// ===========================================================================
// P0-C:孤兒禁丟棄
// ===========================================================================

#[test]
fn orphan_broker_order_frozen_not_dropped() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    // broker 有一張 order_id=999、無對應本地意圖的訂單（order_ref 空）。
    let view = fresh(
        vec![order(999, "", "AAPL", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.orphan_order_ids.contains(&999), "orphan 禁丟棄");
    assert!(rep.is_symbol_frozen("AAPL"), "孤兒 symbol 凍結");
    assert!(rec.is_symbol_frozen("AAPL"), "持久 store 亦凍");
    assert!(rep
        .alerts
        .iter()
        .any(|a| a.kind == ReconciliationAlertKind::OrphanBrokerOrder));
}

#[test]
fn orphan_broker_execution_frozen_not_dropped() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    let view = fresh(vec![], vec![exec("e-1", 555, "TSLA")]);
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.orphan_exec_ids.iter().any(|e| e == "e-1"));
    assert!(rep.is_symbol_frozen("TSLA"));
    assert!(rep
        .alerts
        .iter()
        .any(|a| a.kind == ReconciliationAlertKind::OrphanBrokerExecution));
}

// ===========================================================================
// 三向 join：idempotency_key 優先 vs order-id fallback vs 歧義 vs 純漂移孤兒
// ===========================================================================

#[test]
fn idempotency_key_join_survives_order_id_drift() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7); // 本地 order_id=7
    let mut rec = OrderReconciler::new();
    // 重連後 broker order-id 漂移為 999,但 orderRef==idempotency_key → 權威 join。
    let view = fresh(
        vec![order(999, "k1", "SPY", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.orphan_order_ids.is_empty(), "drift 不致孤兒");
    assert!(!rep.is_symbol_frozen("SPY"));
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::Consistent { .. }
    ));
}

#[test]
fn orderref_empty_pure_drift_orphan_frozen() {
    // E2 LOW-1:當下 wire orderRef="" → 無 drift-immune 主 join;order-id 純漂移(999≠7)→ order-id
    // fallback 亦失配 → Orphan → 凍結(fail-closed,不猜)。
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    let view = fresh(
        vec![order(999, "", "SPY", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.orphan_order_ids.contains(&999), "純漂移→孤兒禁丟棄");
    assert!(rep.is_symbol_frozen("SPY"), "fail-closed 凍結");
}

#[test]
fn order_id_fallback_join_when_orderref_empty() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    // orderRef 空 → order-id fallback（7 唯一命中）。
    let view = fresh(
        vec![order(7, "", "SPY", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.orphan_order_ids.is_empty());
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::Consistent { .. }
    ));
}

#[test]
fn ambiguous_order_id_frozen_not_guessed() {
    let mut d = new_driver();
    // 兩筆本地意圖共用 order_id=7（重連撞號情形）。
    drive_to_ack(&mut d, "k1", 7);
    drive_to_ack(&mut d, "k2", 7);
    let mut rec = OrderReconciler::new();
    let view = fresh(
        vec![order(7, "", "SPY", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = rec.reconcile(
        &mut d,
        &view,
        &symbols(&[("k1", "SPY"), ("k2", "SPY")]),
        NOW,
    );
    assert!(rep.is_symbol_frozen("SPY"), "歧義 fail-closed 凍結");
    assert!(rep
        .alerts
        .iter()
        .any(|a| a.kind == ReconciliationAlertKind::Divergence));
}

#[test]
fn forced_diverge_duplicate_broker_order_manual_review() {
    // E4 GAP-1:兩張 broker 訂單以 order_ref 解到同一意圖 → forced_diverge → DivergedFrozen + 凍結 +
    // Divergence alert + 意圖升 ManualReviewRequired。
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    let view = fresh(
        vec![
            order(7, "k1", "SPY", IbkrOrderStatusV1::Submitted),
            order(8, "k1", "SPY", IbkrOrderStatusV1::Submitted),
        ],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep
        .outcomes
        .iter()
        .any(|o| matches!(o, IntentReconOutcome::DivergedFrozen { .. })));
    assert!(rep.is_symbol_frozen("SPY"));
    assert!(rep
        .alerts
        .iter()
        .any(|a| a.kind == ReconciliationAlertKind::Divergence));
    assert_eq!(
        state_of(&d, "k1"),
        St::ManualReviewRequired,
        "升 ManualReview"
    );
}

// ===========================================================================
// P0-A：幻影倉防線（cancel 後 late-fill / re-open remaining↑）+ F2 持久化
// ===========================================================================

#[test]
fn phantom_late_fill_after_cancel_blocked_state_unchanged() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    trans(
        &mut d,
        "k1",
        St::CancelRequested,
        BrokerOperation::PaperOrderCancel,
        None,
    );
    trans(
        &mut d,
        "k1",
        St::Cancelled,
        BrokerOperation::PaperOrderCancel,
        None,
    );
    assert_eq!(state_of(&d, "k1"), St::Cancelled);
    let chain_before = d.verify_chain();
    let journal_len_before = d.journal().len();
    let mut rec = OrderReconciler::new();

    // broker 幻影:同單 late-fill 顯示 Filled。
    let view = fresh(
        vec![order_with_fill(
            7,
            "k1",
            "SPY",
            IbkrOrderStatusV1::Filled,
            "100",
            "0",
        )],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);

    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::DivergedFrozen { .. }
    ));
    assert!(rep.is_symbol_frozen("SPY"), "幻影 → 凍結 symbol");
    // 態/記帳不變:仍 Cancelled,journal 未增,chain 仍完整（幻影未污染狀態;終態不可再遷）。
    assert_eq!(state_of(&d, "k1"), St::Cancelled, "終態不因幻影再遷");
    assert_eq!(d.journal().len(), journal_len_before, "記帳不變");
    assert!(chain_before && d.verify_chain(), "chain 完整");
}

#[test]
fn phantom_late_fill_as_execution_after_cancel_frozen() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    trans(
        &mut d,
        "k1",
        St::CancelRequested,
        BrokerOperation::PaperOrderCancel,
        None,
    );
    trans(
        &mut d,
        "k1",
        St::Cancelled,
        BrokerOperation::PaperOrderCancel,
        None,
    );
    let jl = d.journal().len();
    let mut rec = OrderReconciler::new();
    // 幻影僅以無序 execution 到達（order_id=7 對到 k1,非孤兒),但本地已 Cancelled → 衝突凍結。
    let view = fresh(vec![], vec![exec("e-late", 7, "SPY")]);
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::DivergedFrozen { .. }
    ));
    assert!(rep.is_symbol_frozen("SPY"));
    assert_eq!(state_of(&d, "k1"), St::Cancelled);
    assert_eq!(d.journal().len(), jl, "記帳不變");
}

#[test]
fn reduce_only_remaining_increase_blocked_and_manual_review() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    // 本地 PartiallyFilled:cumulative=50 remaining=50。
    trans(
        &mut d,
        "k1",
        St::PartiallyFilled,
        BrokerOperation::PaperOrderFillImport,
        Some(fd("50", "50")),
    );
    let mut rec = OrderReconciler::new();
    // broker 幻影再開倉:remaining 升至 60（cumulative 同 50 非遞減，僅隔離 remaining↑）。
    let view = fresh(
        vec![order_with_fill(
            7,
            "k1",
            "SPY",
            IbkrOrderStatusV1::Submitted,
            "50",
            "60",
        )],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::ReduceOnlyBlocked { .. }
    ));
    assert!(rep.is_symbol_frozen("SPY"));
    // F2:升 ManualReviewRequired(持久凍結);但幻影量**永不入帳**——cum/rem 仍為 50/50。
    assert_eq!(
        state_of(&d, "k1"),
        St::ManualReviewRequired,
        "reduce-only 幻影 → 升 MRR"
    );
    assert_eq!(cum_of(&d, "k1").as_deref(), Some("50"), "幻影量不入帳");
    assert_eq!(rem_of(&d, "k1").as_deref(), Some("50"), "幻影量不入帳");
}

#[test]
fn reduce_only_freeze_persists_across_pass() {
    // F2:reduce-only 幻影凍結後,下一 pass broker 幻影消失 → 仍凍結(sticky-until-adjudication)。
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    trans(
        &mut d,
        "k1",
        St::PartiallyFilled,
        BrokerOperation::PaperOrderFillImport,
        Some(fd("50", "50")),
    );
    let mut rec = OrderReconciler::new();
    let view1 = fresh(
        vec![order_with_fill(
            7,
            "k1",
            "SPY",
            IbkrOrderStatusV1::Submitted,
            "50",
            "60",
        )],
        vec![],
    );
    let _ = rec.reconcile(&mut d, &view1, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rec.is_symbol_frozen("SPY"));
    // pass2:broker 幻影消失（空 view）→ 仍凍結。
    let view2 = fresh(vec![], vec![]);
    let rep2 = rec.reconcile(&mut d, &view2, &symbols(&[("k1", "SPY")]), NOW);
    assert!(
        rep2.is_symbol_frozen("SPY"),
        "reduce-only 凍結跨 pass 不自動解凍"
    );
    assert!(rec.is_symbol_frozen("SPY"));
    assert!(matches!(
        rep2.outcomes[0],
        IntentReconOutcome::FrozenPendingAdjudication { .. }
    ));
}

// ===========================================================================
// P0-B：unknown-terminal 凍結 symbol + F1 持久性 + 顯式裁決
// ===========================================================================

#[test]
fn unknown_terminal_no_evidence_frozen_and_manual_review() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    trans(
        &mut d,
        "k1",
        St::StateUnknown,
        BrokerOperation::PaperOrderFillImport,
        None,
    );
    let mut rec = OrderReconciler::new();
    // broker 無此單、無成交 → 無 terminal 佐證。
    let view = fresh(vec![], vec![]);
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "MSFT")]), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::UnknownTerminalFrozen { .. }
    ));
    assert!(rep.is_symbol_frozen("MSFT"), "P0-B 凍結 symbol");
    assert_eq!(
        state_of(&d, "k1"),
        St::ManualReviewRequired,
        "升 ManualReview"
    );
    assert!(rep
        .alerts
        .iter()
        .any(|a| a.kind == ReconciliationAlertKind::UnknownTerminalFreeze));
}

#[test]
fn cross_pass_freeze_sticky_until_adjudication() {
    // CC F1:pass1 凍結 → pass2 broker 空 view → 仍凍結;stale pass 亦不解凍;唯顯式裁決可解。
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    trans(
        &mut d,
        "k1",
        St::StateUnknown,
        BrokerOperation::PaperOrderFillImport,
        None,
    );
    let mut rec = OrderReconciler::new();
    let rep1 = rec.reconcile(
        &mut d,
        &fresh(vec![], vec![]),
        &symbols(&[("k1", "MSFT")]),
        NOW,
    );
    assert!(rep1.is_symbol_frozen("MSFT"));
    assert_eq!(state_of(&d, "k1"), St::ManualReviewRequired);

    // pass2:broker 仍空;意圖已 MRR → 無條件重推凍結。
    let rep2 = rec.reconcile(
        &mut d,
        &fresh(vec![], vec![]),
        &symbols(&[("k1", "MSFT")]),
        NOW,
    );
    assert!(rep2.is_symbol_frozen("MSFT"), "F1:跨 pass 不自動解凍");
    assert!(matches!(
        rep2.outcomes[0],
        IntentReconOutcome::FrozenPendingAdjudication { .. }
    ));

    // stale pass:fail-closed 仍回帶 sticky 凍結集(不因 stale 漏凍)。
    let rep3 = rec.reconcile(&mut d, &stale(vec![]), &symbols(&[("k1", "MSFT")]), NOW);
    assert!(rep3.skipped_stale);
    assert!(rep3.is_symbol_frozen("MSFT"), "stale 不漏凍");
    assert!(rec.is_symbol_frozen("MSFT"));

    // 顯式裁決:此凍結錨定 MRR 意圖 → adjudicate 從 store 移除,但下一 pass 由持久態重推(保守)。
    assert!(rec.adjudicate_unfreeze("MSFT"));
    assert!(!rec.is_symbol_frozen("MSFT"), "顯式解凍即時從 store 移除");
    let rep4 = rec.reconcile(
        &mut d,
        &fresh(vec![], vec![]),
        &symbols(&[("k1", "MSFT")]),
        NOW,
    );
    assert!(rep4.is_symbol_frozen("MSFT"), "MRR 意圖未解決 → 保守重凍");
}

#[test]
fn adjudicate_unfreeze_clears_orphan_freeze() {
    // 孤兒凍結非錨定意圖 → 顯式裁決可真正解除(孤兒消失後不重凍)。
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    let _ = rec.reconcile(
        &mut d,
        &fresh(
            vec![order(999, "", "AAPL", IbkrOrderStatusV1::Submitted)],
            vec![],
        ),
        &symbols(&[("k1", "SPY")]),
        NOW,
    );
    assert!(rec.is_symbol_frozen("AAPL"));
    assert!(rec.adjudicate_unfreeze("AAPL"));
    // 孤兒已消失(空 view)→ 不再凍結。
    let rep2 = rec.reconcile(
        &mut d,
        &fresh(vec![], vec![]),
        &symbols(&[("k1", "SPY")]),
        NOW,
    );
    assert!(!rep2.is_symbol_frozen("AAPL"), "孤兒凍結經裁決後真正解除");
    assert!(!rec.is_symbol_frozen("AAPL"));
}
