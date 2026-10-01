//! Bounded, read-only unresolved-order reconciliation. Replays verified
//! executions before the terminal state through the existing consumer; no create retry.
use super::types::{ExchangeEvent, PendingOrder};
use crate::bybit_private_ws::{ExecutionUpdate, OrderUpdate};
use crate::bybit_rest_client::BybitRestClient;
use serde_json::Value;
use std::{collections::HashSet, future::Future, pin::Pin, sync::Arc, time::Duration};
use tokio::sync::{mpsc, Semaphore};

const MAX_CONCURRENT_ORDERS: usize = 4;

type Params = Vec<(String, String)>;
type Fetch = Arc<
    dyn Fn(&'static str, Params) -> Pin<Box<dyn Future<Output = Result<Value, String>> + Send>>
        + Send
        + Sync,
>;

pub(super) struct DcpReconciler {
    fetch: Fetch,
    tx: mpsc::UnboundedSender<ExchangeEvent>,
    in_flight: Arc<parking_lot::Mutex<HashSet<String>>>,
    slots: Arc<Semaphore>,
}

impl DcpReconciler {
    pub(super) fn new(
        client: Arc<BybitRestClient>,
        tx: mpsc::UnboundedSender<ExchangeEvent>,
    ) -> Self {
        let fetch: Fetch = Arc::new(move |path, params| {
            let client = client.clone();
            Box::pin(async move {
                let refs: Vec<_> = params
                    .iter()
                    .map(|(k, v)| (k.as_str(), v.as_str()))
                    .collect();
                client
                    .get_checked(path, &refs)
                    .await
                    .map(|r| r.result)
                    .map_err(|e| e.to_string())
            })
        });
        Self {
            fetch,
            tx,
            in_flight: Default::default(),
            slots: Arc::new(Semaphore::new(MAX_CONCURRENT_ORDERS)),
        }
    }

    /// Startup barrier: all open orders must be accounted for and every
    /// paginated one-way USDT position must match the execution projection.
    #[cfg(test)]
    pub(super) async fn account_matches(
        &self,
        paper: &crate::paper_state::PaperStateSnapshot,
    ) -> Result<(), String> {
        account_matches(&self.fetch, paper).await
    }

    pub(super) fn schedule_account(
        &self,
        paper: crate::paper_state::PaperStateSnapshot,
    ) -> tokio::sync::oneshot::Receiver<Result<(), String>> {
        let fetch = self.fetch.clone();
        let (tx, rx) = tokio::sync::oneshot::channel();
        tokio::spawn(async move {
            let result =
                tokio::time::timeout(Duration::from_secs(15), account_matches(&fetch, &paper))
                    .await
                    .unwrap_or_else(|_| Err("account reconciliation timed out".into()));
            let _ = tx.send(result);
        });
        rx
    }

    pub(super) fn schedule(&self, pending: &[PendingOrder]) {
        let work: Vec<_> = pending
            .iter()
            .filter(|po| self.in_flight.lock().insert(po.order_link_id.clone()))
            .cloned()
            .collect();
        if work.is_empty() {
            return;
        }
        // A stalled REST read consumes one slot, not the whole pending batch.
        // The shared semaphore caps work across disconnect/timer schedule calls.
        for po in work {
            let fetch = self.fetch.clone();
            let tx = self.tx.clone();
            let in_flight = self.in_flight.clone();
            let slots = self.slots.clone();
            tokio::spawn(async move {
                let Ok(_permit) = slots.acquire_owned().await else {
                    in_flight.lock().remove(&po.order_link_id);
                    return;
                };
                let mut resolved = false;
                for delay in [0, 250, 1000] {
                    if tx.is_closed() {
                        break;
                    }
                    tokio::time::sleep(Duration::from_millis(delay)).await;
                    match tokio::time::timeout(Duration::from_secs(15), reconcile(&po, &fetch))
                        .await
                    {
                        Ok(Ok(events)) => {
                            for event in events {
                                if tx.send(event).is_err() {
                                    break;
                                }
                            }
                            resolved = true;
                            break;
                        }
                        Ok(Err(error)) => {
                            tracing::warn!(order_link_id=%po.order_link_id, %error, "Order reconciliation awaiting complete per-order evidence")
                        }
                        Err(_) => {
                            tracing::warn!(order_link_id=%po.order_link_id, "Order reconciliation attempt timed out")
                        }
                    }
                }
                if !resolved {
                    tracing::error!(order_link_id=%po.order_link_id, "Order reconciliation exhausted; keeping order unresolved");
                }
                in_flight.lock().remove(&po.order_link_id);
            });
        }
    }

    #[cfg(test)]
    pub(super) async fn reconcile_fixture(
        &self,
        po: &PendingOrder,
    ) -> Result<Vec<ExchangeEvent>, String> {
        reconcile(po, &self.fetch).await
    }

    #[cfg(test)]
    pub(super) fn is_idle(&self) -> bool {
        self.in_flight.lock().is_empty()
    }

    #[cfg(test)]
    pub(super) fn fixture(responses: Vec<Value>) -> (Self, mpsc::UnboundedReceiver<ExchangeEvent>) {
        let responses = Arc::new(parking_lot::Mutex::new(std::collections::VecDeque::from(
            responses,
        )));
        let fetch: Fetch = Arc::new(move |_, _| {
            let response = responses
                .lock()
                .pop_front()
                .ok_or_else(|| "fixture exhausted".into());
            Box::pin(std::future::ready(response))
        });
        Self::fixture_with_fetch(fetch)
    }

    #[cfg(test)]
    pub(super) fn fixture_with_fetch(
        fetch: Fetch,
    ) -> (Self, mpsc::UnboundedReceiver<ExchangeEvent>) {
        let (tx, rx) = mpsc::unbounded_channel();
        (
            Self {
                fetch,
                tx,
                in_flight: Default::default(),
                slots: Arc::new(Semaphore::new(MAX_CONCURRENT_ORDERS)),
            },
            rx,
        )
    }
}

async fn account_matches(
    fetch: &Fetch,
    paper: &crate::paper_state::PaperStateSnapshot,
) -> Result<(), String> {
    let params = vec![
        ("category".into(), "linear".into()),
        ("settleCoin".into(), "USDT".into()),
        ("limit".into(), "200".into()),
    ];
    let orders = (fetch)("/v5/order/realtime", params.clone()).await?;
    if !rows(&orders)?.is_empty()
        || orders.get("nextPageCursor").and_then(Value::as_str) != Some("")
    {
        return Err("unaccounted open orders or incomplete order page".into());
    }
    let mut positions = std::collections::HashMap::new();
    let mut cursor = String::new();
    let mut cursors = HashSet::new();
    for _ in 0..20 {
        let mut params = params.clone();
        if !cursor.is_empty() {
            params.push(("cursor".into(), cursor.clone()));
        }
        let value = (fetch)("/v5/position/list", params).await?;
        for item in rows(&value)? {
            if item.get("positionIdx").and_then(Value::as_u64) != Some(0) {
                return Err("unknown or hedge position mode".into());
            }
            let symbol = item
                .get("symbol")
                .and_then(Value::as_str)
                .filter(|s| !s.is_empty())
                .ok_or("missing position symbol")?;
            let size = nonnegative(
                item.get("size")
                    .and_then(Value::as_str)
                    .ok_or("missing position size")?,
            )?;
            if size == 0.0 {
                continue;
            }
            let side = item
                .get("side")
                .and_then(Value::as_str)
                .filter(|s| matches!(*s, "Buy" | "Sell"))
                .ok_or("invalid position side")?;
            let price = nonnegative(
                item.get("avgPrice")
                    .and_then(Value::as_str)
                    .ok_or("missing position price")?,
            )?;
            if price == 0.0
                || positions
                    .insert(symbol.to_owned(), (side == "Buy", size, price))
                    .is_some()
            {
                return Err("invalid/duplicate position".into());
            }
        }
        cursor = value
            .get("nextPageCursor")
            .and_then(Value::as_str)
            .ok_or("missing position cursor")?
            .to_owned();
        if cursor.is_empty() {
            if positions.len() != paper.positions.len() {
                return Err("position universe differs".into());
            }
            for pos in &paper.positions {
                let p = &pos.position;
                let Some((side, qty, price)) = positions.get(&p.symbol) else {
                    return Err("position missing".into());
                };
                if *side != p.is_long
                    || (*qty - p.qty).abs() > 1e-10 * p.qty.abs().max(1.0)
                    || (*price - p.entry_price).abs() > 1e-10 * p.entry_price.abs().max(1.0)
                {
                    return Err("position accounting differs".into());
                }
            }
            return Ok(());
        }
        if !cursors.insert(cursor.clone()) {
            return Err("repeated position cursor".into());
        }
    }
    Err("position page budget exhausted".into())
}

fn nonnegative(value: &str) -> Result<f64, String> {
    value
        .parse::<f64>()
        .ok()
        .filter(|x| x.is_finite() && *x >= 0.0)
        .ok_or_else(|| "invalid quantity".into())
}
fn rows(value: &Value) -> Result<&Vec<Value>, String> {
    value
        .get("list")
        .and_then(Value::as_array)
        .ok_or_else(|| "missing list".into())
}

async fn reconcile(po: &PendingOrder, fetch: &Fetch) -> Result<Vec<ExchangeEvent>, String> {
    let params = vec![
        ("category".into(), "linear".into()),
        ("symbol".into(), po.symbol.clone()),
        ("orderLinkId".into(), po.order_link_id.clone()),
    ];
    let mut result = fetch("/v5/order/realtime", params.clone()).await?;
    if rows(&result)?.is_empty() {
        result = fetch("/v5/order/history", params).await?;
    }
    if rows(&result)?.len() != 1 {
        return Err("missing or ambiguous order identity".into());
    }
    let order: OrderUpdate =
        serde_json::from_value(rows(&result)?[0].clone()).map_err(|e| e.to_string())?;
    if order.order_link_id != po.order_link_id
        || order.symbol != po.symbol
        || order.order_id.is_empty()
        || order.side != if po.is_long { "Buy" } else { "Sell" }
    {
        return Err("order identity mismatch".into());
    }
    if !matches!(
        order.order_status.as_str(),
        "Filled" | "Cancelled" | "Rejected" | "Deactivated" | "PartiallyFilledCanceled"
    ) {
        return Err("Order confirmation not yet terminal".into());
    }
    let expected = nonnegative(&order.cum_exec_qty)?;
    if order.order_status == "Filled" && expected == 0.0 {
        return Err("filled order has no execution quantity".into());
    }
    if expected + 1e-10 < po.cum_filled_qty {
        return Err("stale cumulative execution quantity".into());
    }
    let mut executions = Vec::new();
    let mut ids = HashSet::new();
    let mut cursor = String::new();
    let mut cursors = HashSet::new();
    if expected > 0.0 {
        for page in 0..20 {
            let mut params = vec![
                ("category".into(), "linear".into()),
                ("symbol".into(), po.symbol.clone()),
                ("orderId".into(), order.order_id.clone()),
                ("limit".into(), "100".into()),
            ];
            if !cursor.is_empty() {
                params.push(("cursor".into(), cursor));
            }
            let result = fetch("/v5/execution/list", params).await?;
            for row in rows(&result)? {
                let mut exec: ExecutionUpdate =
                    serde_json::from_value(row.clone()).map_err(|e| e.to_string())?;
                if exec.order_id != order.order_id
                    || exec.symbol != po.symbol
                    || exec.side != order.side
                    || (!exec.order_link_id.is_empty() && exec.order_link_id != po.order_link_id)
                    || exec.exec_id.is_empty()
                    || exec.exec_type != "Trade"
                {
                    return Err("execution identity/type mismatch".into());
                }
                if nonnegative(&exec.exec_qty)? == 0.0
                    || nonnegative(&exec.exec_price)? == 0.0
                    || exec.exec_time.parse::<u64>().map_or(true, |t| t == 0)
                {
                    return Err("invalid execution values".into());
                }
                exec.order_link_id = po.order_link_id.clone();
                if ids.insert(exec.exec_id.clone()) {
                    executions.push(exec);
                }
            }
            cursor = result
                .get("nextPageCursor")
                .and_then(Value::as_str)
                .ok_or_else(|| "missing or malformed execution pagination cursor".to_owned())?
                .to_owned();
            if cursor.is_empty() {
                break;
            }
            if page == 19 || !cursors.insert(cursor.clone()) {
                return Err("execution pagination incomplete".into());
            }
        }
    }
    let actual: f64 = executions
        .iter()
        .map(|e| e.exec_qty.parse::<f64>().unwrap())
        .sum();
    if (actual - expected).abs() > 1e-8 * expected.max(1.0) {
        return Err("execution set does not match terminal quantity".into());
    }
    executions.sort_by_key(|e| e.exec_time.parse::<u64>().unwrap());
    let mut events: Vec<_> = executions
        .into_iter()
        .filter(|e| !po.progress.applied_execution_ids.contains(&e.exec_id))
        .map(ExchangeEvent::Fill)
        .collect();
    events.push(ExchangeEvent::OrderUpdate(order));
    Ok(events)
}
