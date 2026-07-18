//! W7-S3 三向對賬引擎測試**共用建構子**（注入時鐘;禁 wall-clock 日期腐化）。兩測試檔
//! （`_tests` / `_tests_more`）共用,避免重複;檔案行數治理拆分。

use std::collections::BTreeMap;

use openclaw_types::{BrokerOperation, IbkrPaperOrderLifecycleState as St};

use super::{BrokerExecutionTruth, BrokerOrderTruth, BrokerTruthView};
use crate::ibkr_tws_account_data::SnapshotStaleness;
use crate::ibkr_tws_order_exec_data::IbkrOrderStatusV1;
use crate::ibkr_tws_order_lifecycle::{
    FillDelta, LifecycleEvent, OrderLifecycleConfig, OrderLifecycleDriver,
};

pub(crate) const NOW: u64 = 1_000_000;

pub(crate) fn new_driver() -> OrderLifecycleDriver {
    OrderLifecycleDriver::new(OrderLifecycleConfig::default())
}

pub(crate) fn create(d: &mut OrderLifecycleDriver, key: &str, order_id: i64) {
    d.apply_lifecycle_event(LifecycleEvent::Create {
        idempotency_key: key.to_string(),
        order_local_id: format!("loc-{key}"),
        operation: BrokerOperation::PaperOrderSubmit,
        order_id,
        now_ms: NOW,
    })
    .expect("create intent");
}

pub(crate) fn trans(
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
pub(crate) fn drive_to_ack(d: &mut OrderLifecycleDriver, key: &str, order_id: i64) {
    use BrokerOperation::PaperOrderSubmit as Sub;
    create(d, key, order_id);
    trans(d, key, St::RustAuthorityAccepted, Sub, None);
    trans(d, key, St::BrokerSubmitRequested, Sub, None);
    trans(d, key, St::BrokerAcknowledged, Sub, None);
}

pub(crate) fn fd(cum: &str, rem: &str) -> FillDelta {
    FillDelta {
        cumulative_filled_decimal: cum.to_string(),
        remaining_decimal: rem.to_string(),
    }
}

pub(crate) fn order(
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

pub(crate) fn order_with_fill(
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

pub(crate) fn exec(exec_id: &str, order_id: i64, symbol: &str) -> BrokerExecutionTruth {
    BrokerExecutionTruth {
        exec_id: exec_id.to_string(),
        order_id,
        perm_id: order_id + 1_000_000,
        symbol: symbol.to_string(),
        shares_decimal: "10".to_string(),
        commission_decimal: "0.35".to_string(),
    }
}

pub(crate) fn fresh(
    orders: Vec<BrokerOrderTruth>,
    execs: Vec<BrokerExecutionTruth>,
) -> BrokerTruthView {
    BrokerTruthView {
        open_orders: orders,
        executions: execs,
        open_orders_staleness: SnapshotStaleness::Fresh { as_of_ms: NOW },
        executions_staleness: SnapshotStaleness::Fresh { as_of_ms: NOW },
    }
}

pub(crate) fn stale(orders: Vec<BrokerOrderTruth>) -> BrokerTruthView {
    let mut v = fresh(orders, vec![]);
    v.open_orders_staleness = SnapshotStaleness::DisconnectedStale;
    v
}

pub(crate) fn symbols(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
    pairs
        .iter()
        .map(|(k, s)| (k.to_string(), s.to_string()))
        .collect()
}

pub(crate) fn state_of(d: &OrderLifecycleDriver, key: &str) -> St {
    d.intent_by_idempotency_key(key).expect("intent").state
}

pub(crate) fn cum_of(d: &OrderLifecycleDriver, key: &str) -> Option<String> {
    d.intent_by_idempotency_key(key)
        .expect("intent")
        .cumulative_filled_decimal
        .clone()
}

pub(crate) fn rem_of(d: &OrderLifecycleDriver, key: &str) -> Option<String> {
    d.intent_by_idempotency_key(key)
        .expect("intent")
        .remaining_decimal
        .clone()
}
