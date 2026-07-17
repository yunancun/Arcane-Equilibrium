//! W7-S3 三向對賬引擎測試（二）：StateUnknown resync / 斷線 resync / MED-1 終態量分歧 / staleness /
//! UNRESOLVED symbol / E2-LOW-2 結算台帳 disjoint / 凍結 symbol-scope。共用建構子見 `_test_helpers`;
//! 注入時鐘 + 注入日期（禁 wall-clock 腐化）。

use std::collections::BTreeMap;

use openclaw_types::{BrokerOperation, IbkrPaperOrderLifecycleState as St};

use super::test_helpers::*;
use super::*;
use crate::ibkr_cash_account_constraints::CashTranche;

// ===========================================================================
// StateUnknown / 斷線 resync（broker 真值覆本地未終態）
// ===========================================================================

#[test]
fn state_unknown_resync_to_filled_with_evidence() {
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
    // broker terminal-with-evidence:Filled。
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
        IntentReconOutcome::Resynced { to: St::Filled, .. }
    ));
    assert!(!rep.is_symbol_frozen("SPY"), "有佐證則不凍結");
    assert_eq!(state_of(&d, "k1"), St::Filled);
}

#[test]
fn reconnect_resync_broker_truth_over_local_inflight() {
    let mut d = new_driver();
    use BrokerOperation::PaperOrderSubmit as Sub;
    create(&mut d, "k1", 7);
    trans(&mut d, "k1", St::RustAuthorityAccepted, Sub, None);
    trans(&mut d, "k1", St::BrokerSubmitRequested, Sub, None); // in-flight
    let mut rec = OrderReconciler::new();
    // 重連後 broker 為真值:此單其實已成交。
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
    // 非單步可達（BrokerSubmitRequested→Filled）→ StateUnknown 漏斗 + terminal 佐證 → resync Filled。
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::Resynced { to: St::Filled, .. }
    ));
    assert_eq!(state_of(&d, "k1"), St::Filled, "broker 真值覆本地未終態");
    assert!(d.verify_chain(), "resync 經 mutator，chain 完整");
}

#[test]
fn partial_fill_resync_single_step() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    let view = fresh(
        vec![order_with_fill(
            7,
            "k1",
            "SPY",
            IbkrOrderStatusV1::Submitted,
            "30",
            "70",
        )],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::Resynced {
            to: St::PartiallyFilled,
            ..
        }
    ));
    assert_eq!(state_of(&d, "k1"), St::PartiallyFilled);
}

#[test]
fn consistent_when_broker_matches_local() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    let view = fresh(
        vec![order(7, "k1", "SPY", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::Consistent { .. }
    ));
    assert!(!rep.is_symbol_frozen("SPY"));
}

#[test]
fn matched_execution_on_live_order_not_orphan() {
    // P0-C tolerant:成交對到本地活躍意圖 → 非孤兒、不凍結（去重歸上游）。
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    let view = fresh(
        vec![order_with_fill(
            7,
            "k1",
            "SPY",
            IbkrOrderStatusV1::Submitted,
            "10",
            "90",
        )],
        vec![exec("e-1", 7, "SPY"), exec("e-1", 7, "SPY")],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.orphan_exec_ids.is_empty(), "matched exec 非孤兒");
    assert!(!rep.is_symbol_frozen("SPY"));
}

// ===========================================================================
// MED-1：終態成交量分歧幻影偵測
// ===========================================================================

#[test]
fn terminal_fill_quantity_divergence_frozen() {
    // E2 MED-1:本地 Filled(cum=100) × broker Filled(filled=150) → 量分歧 → 凍結 + ManualReview(=凍結+
    // Divergence alert;Filled 為型別終態無出邊,凍結為其 manual-review 執行手段)。
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    trans(
        &mut d,
        "k1",
        St::Filled,
        BrokerOperation::PaperOrderFillImport,
        Some(fd("100", "0")),
    );
    let mut rec = OrderReconciler::new();
    let view = fresh(
        vec![order_with_fill(
            7,
            "k1",
            "SPY",
            IbkrOrderStatusV1::Filled,
            "150",
            "0",
        )],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::DivergedFrozen {
            detail: "terminal fill quantity divergence vs broker",
            ..
        }
    ));
    assert!(rep.is_symbol_frozen("SPY"), "終態量分歧 → 凍結");
    assert!(rep
        .alerts
        .iter()
        .any(|a| a.kind == ReconciliationAlertKind::Divergence));
}

#[test]
fn terminal_fill_quantity_match_consistent() {
    // 對照:量相等(100==100.0,定點精確比)→ Consistent,不誤凍。
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    trans(
        &mut d,
        "k1",
        St::Filled,
        BrokerOperation::PaperOrderFillImport,
        Some(fd("100", "0")),
    );
    let mut rec = OrderReconciler::new();
    let view = fresh(
        vec![order_with_fill(
            7,
            "k1",
            "SPY",
            IbkrOrderStatusV1::Filled,
            "100.0",
            "0",
        )],
        vec![],
    );
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::Consistent { .. }
    ));
    assert!(!rep.is_symbol_frozen("SPY"));
}

// ===========================================================================
// staleness 閘 + UNRESOLVED symbol 保守凍結
// ===========================================================================

#[test]
fn stale_snapshot_skips_reconciliation() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    let view = stale(vec![order(999, "", "AAPL", IbkrOrderStatusV1::Submitted)]);
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.skipped_stale, "非 Fresh → 延後");
    assert!(rep.frozen_symbols.is_empty(), "首 pass 無前凍 → 延後不誤凍");
    assert!(rep.outcomes.is_empty());
    assert_eq!(state_of(&d, "k1"), St::BrokerAcknowledged, "態未動");
}

#[test]
fn unresolved_symbol_still_freezes_conservatively() {
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
    // 無 broker 匹配、local_symbols 亦無 k1 → UNRESOLVED 令牌凍結。
    let view = fresh(vec![], vec![]);
    let rep = rec.reconcile(&mut d, &view, &BTreeMap::new(), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::UnknownTerminalFrozen { .. }
    ));
    assert!(rep
        .frozen_symbols
        .iter()
        .any(|s| s.starts_with("UNRESOLVED:")));
}

// ===========================================================================
// E2-LOW-2：結算台帳 disjoint 不變量（純函數,注入日期）
// ===========================================================================

#[test]
fn settlement_ledger_matured_tranche_folded_and_removed() {
    // settled=100，一筆已成熟 tranche(50, 結算日=今日) → settled=150、unsettled 空。
    let tr = vec![CashTranche {
        amount_decimal: "50".to_string(),
        settlement_date: "20260718".to_string(),
    }];
    let led: SettlementLedger =
        reconcile_settlement_ledger("100", &tr, "20260718").expect("ledger");
    assert_eq!(led.settled_cash_decimal, "150");
    assert!(led.unsettled_tranches.is_empty(), "成熟 tranche 移出");
    assert_eq!(led.matured_folded_count, 1);
}

#[test]
fn settlement_ledger_future_tranche_kept_disjoint() {
    let tr = vec![
        CashTranche {
            amount_decimal: "50".to_string(),
            settlement_date: "20260717".to_string(),
        },
        CashTranche {
            amount_decimal: "40".to_string(),
            settlement_date: "20260720".to_string(),
        },
    ];
    let led = reconcile_settlement_ledger("100", &tr, "20260718").expect("ledger");
    assert_eq!(led.settled_cash_decimal, "150", "只滾入成熟 50");
    assert_eq!(led.unsettled_tranches.len(), 1);
    assert_eq!(led.unsettled_tranches[0].settlement_date, "20260720");
    assert!(led
        .unsettled_tranches
        .iter()
        .all(|t| t.settlement_date.as_str() > "20260718"));
}

#[test]
fn settlement_ledger_fractional_precise_fold() {
    let tr = vec![CashTranche {
        amount_decimal: "0.35".to_string(),
        settlement_date: "20260718".to_string(),
    }];
    let led = reconcile_settlement_ledger("100.10", &tr, "20260718").expect("ledger");
    assert_eq!(led.settled_cash_decimal, "100.45");
}

#[test]
fn settlement_ledger_malformed_fails_closed() {
    let bad_amount = vec![CashTranche {
        amount_decimal: "abc".to_string(),
        settlement_date: "20260718".to_string(),
    }];
    assert!(matches!(
        reconcile_settlement_ledger("100", &bad_amount, "20260718"),
        Err(LedgerReconcileError::MalformedTrancheAmount(_))
    ));
    let bad_date = vec![CashTranche {
        amount_decimal: "10".to_string(),
        settlement_date: "2026-07-18".to_string(),
    }];
    assert!(matches!(
        reconcile_settlement_ledger("100", &bad_date, "20260718"),
        Err(LedgerReconcileError::MalformedTrancheDate(_))
    ));
    assert!(matches!(
        reconcile_settlement_ledger("xx", &[], "20260718"),
        Err(LedgerReconcileError::MalformedSettledCash)
    ));
    assert!(matches!(
        reconcile_settlement_ledger("100", &[], "bad"),
        Err(LedgerReconcileError::MalformedTrancheDate(_))
    ));
}

// ===========================================================================
// 多意圖確定序 + 部分凍結不外溢
// ===========================================================================

#[test]
fn freeze_is_symbol_scoped_not_global() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7); // SPY，一致
    drive_to_ack(&mut d, "k2", 8); // AAPL，幻影孤兒
    let mut rec = OrderReconciler::new();
    let view = fresh(
        vec![
            order(7, "k1", "SPY", IbkrOrderStatusV1::Submitted),
            order(999, "", "AAPL", IbkrOrderStatusV1::Submitted),
        ],
        vec![],
    );
    let rep = rec.reconcile(
        &mut d,
        &view,
        &symbols(&[("k1", "SPY"), ("k2", "AAPL")]),
        NOW,
    );
    assert!(rep.is_symbol_frozen("AAPL"), "孤兒 symbol 凍結");
    assert!(!rep.is_symbol_frozen("SPY"), "一致 symbol 不外溢凍結");
}

#[test]
fn empty_view_all_intents_untouched() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut rec = OrderReconciler::new();
    let view = fresh(vec![], vec![]);
    let rep = rec.reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    // BrokerAcknowledged 活躍、broker 無此單、無成交佐證 → 保守 StateUnknown 漏斗 → ManualReview 凍結。
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::UnknownTerminalFrozen { .. }
    ));
    assert_eq!(state_of(&d, "k1"), St::ManualReviewRequired);
}
