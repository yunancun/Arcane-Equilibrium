//! W7-S3 三向對賬引擎測試（P0 面窮舉）。注入時鐘（禁 wall-clock 日期腐化);Deletion-test 精神=
//! 幻影倉 P0 復現（cancel 後 late-fill / re-open remaining↑ → 拒 + 態/記帳不變 + chain 完整）。

use std::collections::BTreeMap;

use openclaw_types::{BrokerOperation, IbkrPaperOrderLifecycleState as St};

use super::*;
use crate::ibkr_cash_account_constraints::CashTranche;
use crate::ibkr_tws_account_data::SnapshotStaleness;
use crate::ibkr_tws_order_exec_data::IbkrOrderStatusV1;
use crate::ibkr_tws_order_lifecycle::{
    FillDelta, LifecycleEvent, OrderLifecycleConfig, OrderLifecycleDriver,
};

const NOW: u64 = 1_000_000;

fn new_driver() -> OrderLifecycleDriver {
    OrderLifecycleDriver::new(OrderLifecycleConfig::default())
}

fn create(d: &mut OrderLifecycleDriver, key: &str, order_id: i64) {
    d.apply_lifecycle_event(LifecycleEvent::Create {
        idempotency_key: key.to_string(),
        order_local_id: format!("loc-{key}"),
        operation: BrokerOperation::PaperOrderSubmit,
        order_id,
        now_ms: NOW,
    })
    .expect("create intent");
}

fn trans(
    d: &mut OrderLifecycleDriver,
    key: &str,
    to: St,
    op: BrokerOperation,
    fill: Option<FillDelta>,
) {
    d.apply_lifecycle_event(LifecycleEvent::Transition {
        idempotency_key: key.to_string(),
        next_state: to,
        operation: op,
        broker_order_id: None,
        fill,
        now_ms: NOW,
    })
    .expect("transition");
}

/// 驅至 BrokerAcknowledged（活躍受理態）。
fn drive_to_ack(d: &mut OrderLifecycleDriver, key: &str, order_id: i64) {
    use BrokerOperation::PaperOrderSubmit as Sub;
    create(d, key, order_id);
    trans(d, key, St::RustAuthorityAccepted, Sub, None);
    trans(d, key, St::BrokerSubmitRequested, Sub, None);
    trans(d, key, St::BrokerAcknowledged, Sub, None);
}

fn fd(cum: &str, rem: &str) -> FillDelta {
    FillDelta {
        cumulative_filled_decimal: cum.to_string(),
        remaining_decimal: rem.to_string(),
    }
}

fn order(
    order_id: i64,
    order_ref: &str,
    symbol: &str,
    status: IbkrOrderStatusV1,
) -> BrokerOrderTruth {
    BrokerOrderTruth {
        order_id,
        perm_id: order_id + 1_000_000,
        order_ref: order_ref.to_string(),
        symbol: symbol.to_string(),
        status: Some(status),
        filled_decimal: None,
        remaining_decimal: None,
    }
}

fn order_with_fill(
    order_id: i64,
    order_ref: &str,
    symbol: &str,
    status: IbkrOrderStatusV1,
    filled: &str,
    remaining: &str,
) -> BrokerOrderTruth {
    let mut o = order(order_id, order_ref, symbol, status);
    o.filled_decimal = Some(filled.to_string());
    o.remaining_decimal = Some(remaining.to_string());
    o
}

fn exec(exec_id: &str, order_id: i64, symbol: &str) -> BrokerExecutionTruth {
    BrokerExecutionTruth {
        exec_id: exec_id.to_string(),
        order_id,
        perm_id: order_id + 1_000_000,
        symbol: symbol.to_string(),
        shares_decimal: "10".to_string(),
        commission_decimal: "0.35".to_string(),
    }
}

fn fresh(orders: Vec<BrokerOrderTruth>, execs: Vec<BrokerExecutionTruth>) -> BrokerTruthView {
    BrokerTruthView {
        open_orders: orders,
        executions: execs,
        open_orders_staleness: SnapshotStaleness::Fresh { as_of_ms: NOW },
        executions_staleness: SnapshotStaleness::Fresh { as_of_ms: NOW },
    }
}

fn symbols(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
    pairs
        .iter()
        .map(|(k, s)| (k.to_string(), s.to_string()))
        .collect()
}

fn state_of(d: &OrderLifecycleDriver, key: &str) -> St {
    d.intent_by_idempotency_key(key).expect("intent").state
}

// ===========================================================================
// P0-C:孤兒禁丟棄
// ===========================================================================

#[test]
fn orphan_broker_order_frozen_not_dropped() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    // broker 有一張 order_id=999、無對應本地意圖的訂單（order_ref 空）。
    let view = fresh(
        vec![order(999, "", "AAPL", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.orphan_order_ids.contains(&999), "orphan 禁丟棄");
    assert!(rep.is_symbol_frozen("AAPL"), "孤兒 symbol 凍結");
    assert!(rep
        .alerts
        .iter()
        .any(|a| a.kind == ReconciliationAlertKind::OrphanBrokerOrder));
}

#[test]
fn orphan_broker_execution_frozen_not_dropped() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let view = fresh(vec![], vec![exec("e-1", 555, "TSLA")]);
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.orphan_exec_ids.iter().any(|e| e == "e-1"));
    assert!(rep.is_symbol_frozen("TSLA"));
    assert!(rep
        .alerts
        .iter()
        .any(|a| a.kind == ReconciliationAlertKind::OrphanBrokerExecution));
}

// ===========================================================================
// 三向 join：idempotency_key 優先 vs order-id fallback vs 歧義
// ===========================================================================

#[test]
fn idempotency_key_join_survives_order_id_drift() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7); // 本地 order_id=7
                                   // 重連後 broker order-id 漂移為 999,但 orderRef==idempotency_key → 權威 join。
    let view = fresh(
        vec![order(999, "k1", "SPY", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    // 命中即不孤兒、不凍結;broker Submitted 無 fill 對本地 Acknowledged → Consistent。
    assert!(rep.orphan_order_ids.is_empty(), "drift 不致孤兒");
    assert!(!rep.is_symbol_frozen("SPY"));
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::Consistent { .. }
    ));
}

#[test]
fn order_id_fallback_join_when_orderref_empty() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    // orderRef 空 → order-id fallback（7 唯一命中）。
    let view = fresh(
        vec![order(7, "", "SPY", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
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
    let view = fresh(
        vec![order(7, "", "SPY", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = reconcile(
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

// ===========================================================================
// P0-A：幻影倉防線（cancel 後 late-fill / re-open remaining↑）
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
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);

    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::DivergedFrozen { .. }
    ));
    assert!(rep.is_symbol_frozen("SPY"), "幻影 → 凍結 symbol");
    // 態/記帳不變:仍 Cancelled,journal 未增,chain 仍完整（幻影未污染狀態）。
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
    // 幻影僅以無序 execution 到達（order_id=7 對到 k1,非孤兒),但本地已 Cancelled → 衝突凍結。
    let view = fresh(vec![], vec![exec("e-late", 7, "SPY")]);
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::DivergedFrozen { .. }
    ));
    assert!(rep.is_symbol_frozen("SPY"));
    assert_eq!(state_of(&d, "k1"), St::Cancelled);
    assert_eq!(d.journal().len(), jl, "記帳不變");
}

#[test]
fn reduce_only_remaining_increase_blocked() {
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
    let jl = d.journal().len();
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
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::ReduceOnlyBlocked { .. }
    ));
    assert!(rep.is_symbol_frozen("SPY"));
    assert_eq!(
        state_of(&d, "k1"),
        St::PartiallyFilled,
        "reduce-only 拒後態不變"
    );
    assert_eq!(d.journal().len(), jl, "記帳不變");
}

// ===========================================================================
// P0-B：unknown-terminal 凍結 symbol
// ===========================================================================

#[test]
fn unknown_terminal_no_evidence_frozen_and_manual_review() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    // 先落 StateUnknown（重啟 recovery 語境;經合法遷移）。
    trans(
        &mut d,
        "k1",
        St::StateUnknown,
        BrokerOperation::PaperOrderFillImport,
        None,
    );
    // broker 無此單、無成交 → 無 terminal 佐證。
    let view = fresh(vec![], vec![]);
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "MSFT")]), NOW);
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
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::Resynced { to: St::Filled, .. }
    ));
    assert!(!rep.is_symbol_frozen("SPY"), "有佐證則不凍結");
    assert_eq!(state_of(&d, "k1"), St::Filled);
}

// ===========================================================================
// in-flight 斷線 → resync（broker 真值覆本地未終態）
// ===========================================================================

#[test]
fn reconnect_resync_broker_truth_over_local_inflight() {
    let mut d = new_driver();
    use BrokerOperation::PaperOrderSubmit as Sub;
    create(&mut d, "k1", 7);
    trans(&mut d, "k1", St::RustAuthorityAccepted, Sub, None);
    trans(&mut d, "k1", St::BrokerSubmitRequested, Sub, None); // in-flight
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
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
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
    // broker 顯示部分成交。
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
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
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
    let view = fresh(
        vec![order(7, "k1", "SPY", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
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
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.orphan_exec_ids.is_empty(), "matched exec 非孤兒");
    assert!(!rep.is_symbol_frozen("SPY"));
}

// ===========================================================================
// staleness 閘：非 Fresh → 對賬延後（不動態、不誤凍）
// ===========================================================================

#[test]
fn stale_snapshot_skips_reconciliation() {
    let mut d = new_driver();
    drive_to_ack(&mut d, "k1", 7);
    let mut view = fresh(
        vec![order(999, "", "AAPL", IbkrOrderStatusV1::Submitted)],
        vec![],
    );
    view.open_orders_staleness = SnapshotStaleness::DisconnectedStale;
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    assert!(rep.skipped_stale, "非 Fresh → 延後");
    assert!(rep.frozen_symbols.is_empty(), "延後不誤凍");
    assert!(rep.outcomes.is_empty());
    assert_eq!(state_of(&d, "k1"), St::BrokerAcknowledged, "態未動");
}

// ===========================================================================
// symbol 缺席保守凍結（本地 + broker 皆無 symbol → UNRESOLVED 令牌 + 告警，不靜默放行）
// ===========================================================================

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
    // 無 broker 匹配、local_symbols 亦無 k1 → UNRESOLVED 令牌凍結。
    let view = fresh(vec![], vec![]);
    let rep = reconcile(&mut d, &view, &BTreeMap::new(), NOW);
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
// E2-LOW-2：結算台帳 disjoint 不變量
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
    // 混合:一成熟 + 一未來 → settled 只滾成熟，unsettled 只留未來（disjoint）。
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
    // disjoint:輸出 unsettled 內無任何已成熟（≤ today）tranche。
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
    let view = fresh(
        vec![
            order(7, "k1", "SPY", IbkrOrderStatusV1::Submitted),
            order(999, "", "AAPL", IbkrOrderStatusV1::Submitted),
        ],
        vec![],
    );
    let rep = reconcile(
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
    let view = fresh(vec![], vec![]);
    let rep = reconcile(&mut d, &view, &symbols(&[("k1", "SPY")]), NOW);
    // BrokerAcknowledged 活躍、broker 無此單、無成交佐證 → 保守 StateUnknown 漏斗 → ManualReview 凍結。
    assert!(matches!(
        rep.outcomes[0],
        IntentReconOutcome::UnknownTerminalFrozen { .. }
    ));
    assert_eq!(state_of(&d, "k1"), St::ManualReviewRequired);
}
