//! Single-owner durable boundary around the existing OMS consumers. Local
//! mutations are provisional until the inbox/checkpoint/accounting transaction
//! commits. Failure latches all submission and requires restart/reconciliation.
use super::{
    loop_handlers::LoopState,
    recovery_store::{RecoveryStore, Result},
    types::{ExchangeEvent, PendingOrder, PendingOrderEvent},
};
use crate::{
    bybit_private_ws::ExecutionUpdate, database::TradingMsg, paper_state::PaperStateSnapshot,
    persistence::DualStateWriter, tick_pipeline::TickPipeline,
};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use tokio::sync::mpsc;

#[derive(Clone, Serialize, Deserialize)]
pub(super) struct Checkpoint {
    version: u32,
    pub(super) paper: PaperStateSnapshot,
    pub(super) pending: HashMap<String, PendingOrder>,
    #[serde(default)]
    pub(super) retired: HashMap<String, PendingOrder>,
    order_ids: HashMap<String, String>,
    fallbacks: HashSet<String>,
    total_fills: u64,
}
impl Checkpoint {
    pub(super) fn capture(pipeline: &TickPipeline, state: &LoopState) -> Self {
        Self {
            version: 1,
            paper: pipeline.paper_state.export_state(),
            pending: state.pending_orders.clone(),
            retired: state.retired_orders.clone(),
            order_ids: state.order_id_to_link.clone(),
            fallbacks: state.close_maker_fallback_dispatched.clone(),
            total_fills: pipeline.stats.total_fills,
        }
    }
    pub(super) fn validate(&self) -> Result<()> {
        if self.version != 1
            || self.pending.len() > 4096
            || self.retired.len() > 4096
            || self.order_ids.len() > 4096
            || serde_json::to_vec(self).map_err(|e| e.to_string())?.len() > 8 * 1024 * 1024
            || [
                self.paper.balance,
                self.paper.initial_balance,
                self.paper.peak_balance,
                self.paper.total_realized_pnl,
                self.paper.total_fees,
                self.paper.total_funding_pnl,
            ]
            .iter()
            .any(|x| !x.is_finite())
            || self
                .pending
                .iter()
                .chain(self.retired.iter())
                .any(|(id, p)| {
                    id.is_empty()
                        || id != &p.order_link_id
                        || p.symbol.is_empty()
                        || !p.qty.is_finite()
                        || p.qty < 0.0
                        || p.cum_filled_qty < 0.0
                        || !p.cum_filled_qty.is_finite()
                })
            || self.paper.positions.iter().any(|p| {
                !p.position.qty.is_finite()
                    || p.position.qty <= 0.0
                    || !p.position.entry_price.is_finite()
                    || p.position.entry_price <= 0.0
            })
        {
            return Err("invalid recovery checkpoint".into());
        }
        Ok(())
    }
    fn restore(self, pipeline: &mut TickPipeline, state: &mut LoopState) {
        pipeline
            .paper_state
            .restore_execution_projection(&self.paper);
        pipeline.stats.total_fills = self.total_fills;
        state.pending_orders = self.pending;
        state.retired_orders.clear();
        state.order_id_to_link = self.order_ids;
        state.close_maker_fallback_dispatched = self.fallbacks;
        state.seen_exec_set.clear();
        state.seen_exec_order.clear();
        for po in state.pending_orders.values_mut() {
            pipeline.exchange_submission_guard.track(&po.order_link_id);
            if po.is_close {
                pipeline.retain_pending_close(&po.symbol);
            }
            po.progress.reconciliation_retry_after_ms = Some(0);
            po.progress.maker_cancel_attempt_ts_ms = None;
        }
    }
}

pub(super) struct ExecutionRecovery {
    pub(super) store: RecoveryStore,
    startup_pending: bool,
    next_position_check_ms: u64,
    account_check: Option<(i64, tokio::sync::oneshot::Receiver<Result<()>>)>,
    failed: bool,
    last_control: serde_json::Value,
}
impl ExecutionRecovery {
    pub(super) async fn open(
        pool: &sqlx::PgPool,
        engine: &str,
        account: &str,
        pipeline: &mut TickPipeline,
        state: &mut LoopState,
    ) -> Result<Self> {
        pipeline.exchange_submission_guard.block_storage(true);
        pipeline
            .exchange_submission_guard
            .block_reconciliation(true);
        let initial = Checkpoint::capture(pipeline, state);
        let (store, checkpoint) = RecoveryStore::open(pool, engine, account, &initial).await?;
        checkpoint.restore(pipeline, state);
        Ok(Self {
            store,
            startup_pending: true,
            next_position_check_ms: 0,
            account_check: None,
            failed: false,
            last_control: serde_json::Value::Null,
        })
    }
    fn fail(&mut self, pipeline: &TickPipeline, error: &str) {
        self.failed = true;
        pipeline.exchange_submission_guard.block_storage(true);
        tracing::error!(%error,"Execution recovery failed; submission remains fenced until verified restart");
    }
    pub(super) async fn recover(
        &mut self,
        pipeline: &mut TickPipeline,
        state: &mut LoopState,
        writer: &mut DualStateWriter,
        tx: Option<&mpsc::Sender<TradingMsg>>,
    ) -> Result<()> {
        let unapplied = match self.store.unapplied().await {
            Ok(v) => v,
            Err(e) => {
                self.fail(pipeline, &e);
                return Err(e);
            }
        };
        for execution in unapplied {
            self.exchange(
                Some(ExchangeEvent::Fill(execution)),
                pipeline,
                state,
                writer,
                tx,
            )
            .await;
            if self.failed {
                return Err("unapplied inbox recovery incomplete".into());
            }
        }
        // Pending intents retain the ordinary entry guard, including intents
        // committed just before a crash that may never have reached Bybit.
        pipeline.exchange_submission_guard.block_storage(false);
        super::loop_tick::schedule_pending_reconciliation(state, openclaw_core::now_ms());
        Ok(())
    }
    pub(super) async fn exchange(
        &mut self,
        mut event: Option<ExchangeEvent>,
        pipeline: &mut TickPipeline,
        state: &mut LoopState,
        writer: &mut DualStateWriter,
        order_tx: Option<&mpsc::Sender<TradingMsg>>,
    ) {
        if self.failed {
            return;
        }
        if matches!(
            event,
            Some(ExchangeEvent::Disconnected | ExchangeEvent::DcpTriggered)
        ) {
            self.startup_pending = true;
            self.next_position_check_ms = 0;
            pipeline
                .exchange_submission_guard
                .block_reconciliation(true);
        }
        if let Some(ExchangeEvent::OrderUpdate(ref order)) = event {
            if !order.order_id.is_empty() {
                if let Err(e) = self
                    .store
                    .bind_order_id(&order.order_link_id, &order.order_id)
                    .await
                {
                    self.fail(pipeline, &e);
                    return;
                }
            }
        }
        let exec_id = if let Some(ExchangeEvent::Fill(ref execution)) = event {
            if !valid_execution(execution) {
                // Invalid input must not poison the ID; a valid REST replay may repair it.
                tracing::error!(exec_id=%execution.exec_id,"Invalid execution; retaining unresolved order");
                return;
            }
            match self.store.receive(execution).await {
                Ok(false) => return,
                Ok(true) => {}
                Err(e) => {
                    self.fail(pipeline, &e);
                    return;
                }
            }
            if !super::funding_settlement::is_funding_execution(execution)
                && !attributable(execution, state)
            {
                match self.store.order_for_execution(execution).await {
                    Ok(Some(po))
                        if po.symbol == execution.symbol
                            && po.is_long == (execution.side == "Buy") =>
                    {
                        pipeline.exchange_submission_guard.track(&po.order_link_id);
                        state
                            .order_id_to_link
                            .insert(execution.order_id.clone(), po.order_link_id.clone());
                        state.pending_orders.insert(po.order_link_id.clone(), po);
                    }
                    _ => {
                        self.fail(pipeline,"execution has no unambiguous durable order; inbox retained for reconciliation");
                        return;
                    }
                }
            }
            Some(execution.exec_id.clone())
        } else {
            None
        };
        if let Some(ExchangeEvent::Fill(ref mut execution)) = event {
            if execution.order_link_id.is_empty() {
                if let Some(id) = state.order_id_to_link.get(&execution.order_id) {
                    execution.order_link_id = id.clone();
                }
            }
            if !execution.order_link_id.is_empty() {
                if let Err(e) = self
                    .store
                    .bind_order_id(&execution.order_link_id, &execution.order_id)
                    .await
                {
                    self.fail(pipeline, &e);
                    return;
                }
            }
        }
        // Position messages are comparison evidence only. A flat notification
        // may arrive before the close execution; removing the position would
        // lose its realized PnL. Never mutate the durable execution projection.
        if let Some(ExchangeEvent::PositionUpdate(ref position)) = event {
            let size = position.size.parse::<f64>().ok();
            let local = pipeline.paper_state.get_position(&position.symbol);
            let consistent = match (size, local) {
                (Some(size), Some(local)) => {
                    size.is_finite()
                        && (size - local.qty).abs() <= 1e-9
                        && (position.side == "Buy") == local.is_long
                }
                (Some(size), None) => size == 0.0,
                _ => false,
            };
            if !consistent {
                // Per-order reconciliation can repair known in-flight gaps.
                if state
                    .pending_orders
                    .values()
                    .any(|po| po.symbol == position.symbol)
                {
                    super::loop_tick::schedule_pending_reconciliation(
                        state,
                        openclaw_core::now_ms(),
                    );
                } else {
                    self.fail(pipeline,"position differs from execution projection without a recoverable pending order");
                }
            }
            return;
        }
        let before = Checkpoint::capture(pipeline, state);
        let observation = pipeline.begin_recovery_projection();
        let (buffer, mut rx) = mpsc::channel(256);
        let original = pipeline.replace_recovery_trading_channel(Some(buffer.clone()));
        super::loop_exchange::apply_exchange_event(
            event,
            pipeline,
            writer,
            state,
            Some(&buffer),
            false,
        )
        .await;
        pipeline.replace_recovery_trading_channel(original.clone());
        let messages = drain(&mut rx);
        let checkpoint = Checkpoint::capture(pipeline, state);
        if let Err(e) = self
            .store
            .commit(&checkpoint, &messages, exec_id.as_deref(), None)
            .await
        {
            before.restore(pipeline, state);
            pipeline.rollback_recovery_observation(observation);
            self.fail(pipeline, &e);
            return;
        }
        pipeline.finish_recovery_projection(&messages);
        state.retired_orders.clear();
        self.last_control = control(state);
        forward_non_accounting(messages, original.as_ref().or(order_tx));
        writer.force_write(&pipeline.snapshot());
    }
    pub(super) async fn registration(
        &mut self,
        event: Option<PendingOrderEvent>,
        pipeline: &mut TickPipeline,
        state: &mut LoopState,
        tx: Option<&mpsc::Sender<TradingMsg>>,
    ) {
        if self.failed {
            return;
        }
        let (event, intent, ready) = match event {
            Some(PendingOrderEvent::RegisterBeforeSubmit {
                order,
                request,
                ready,
            }) => (
                Some(PendingOrderEvent::Register(order.clone())),
                Some((order, request)),
                Some(ready),
            ),
            other => (other, None, None),
        };
        let (buffer, mut rx) = mpsc::channel(256);
        super::loop_pending_registration::handle_pending_registration(
            event,
            pipeline,
            state,
            Some(&buffer),
        );
        let messages = drain(&mut rx);
        let checkpoint = Checkpoint::capture(pipeline, state);
        if let Err(e) = self
            .store
            .commit(
                &checkpoint,
                &messages,
                None,
                intent.as_ref().map(|(o, r)| (o, r)),
            )
            .await
        {
            self.fail(pipeline, &e);
            return;
        }
        state.retired_orders.clear();
        self.last_control = control(state);
        forward_non_accounting(messages, tx);
        // This is the only authority for the dispatcher's first venue call.
        if let Some(ready) = ready {
            let _ = ready.send(());
        }
    }
    pub(super) async fn reconcile_startup(
        &mut self,
        pipeline: &TickPipeline,
        state: &LoopState,
        now_ms: u64,
    ) {
        if self.failed {
            return;
        }
        if let Some((generation, receiver)) = self.account_check.as_mut() {
            match receiver.try_recv() {
                Ok(Ok(()))
                    if *generation == self.store.generation()
                        && state.pending_orders.is_empty() =>
                {
                    self.startup_pending = false;
                    pipeline
                        .exchange_submission_guard
                        .block_reconciliation(false);
                }
                Err(tokio::sync::oneshot::error::TryRecvError::Empty) => return,
                result => tracing::warn!(
                    ?result,
                    "Account reconciliation incomplete or stale; new entries remain blocked"
                ),
            }
            self.account_check = None;
        }
        if !self.startup_pending
            || !state.pending_orders.is_empty()
            || now_ms < self.next_position_check_ms
        {
            return;
        }
        let Some(reconciler) = state.dcp_reconciler.as_ref() else {
            return;
        };
        self.next_position_check_ms = now_ms.saturating_add(30_000);
        self.account_check = Some((
            self.store.generation(),
            reconciler.schedule_account(pipeline.paper_state.export_state()),
        ));
    }
    pub(super) async fn checkpoint_control(
        &mut self,
        pipeline: &TickPipeline,
        state: &mut LoopState,
        force: bool,
    ) {
        if self.failed {
            return;
        }
        let next = control(state);
        if force || next != self.last_control {
            if let Err(e) = self
                .store
                .commit(&Checkpoint::capture(pipeline, state), &[], None, None)
                .await
            {
                self.fail(pipeline, &e);
                return;
            }
            state.retired_orders.clear();
            self.last_control = next;
        }
    }
}
fn control(state: &LoopState) -> serde_json::Value {
    serde_json::json!([
        state.pending_orders,
        state.order_id_to_link,
        state.close_maker_fallback_dispatched,
        state.retired_orders
    ])
}
fn drain(rx: &mut mpsc::Receiver<TradingMsg>) -> Vec<TradingMsg> {
    let mut result = Vec::new();
    while let Ok(msg) = rx.try_recv() {
        result.push(msg);
    }
    result
}
fn forward_non_accounting(messages: Vec<TradingMsg>, tx: Option<&mpsc::Sender<TradingMsg>>) {
    for msg in messages {
        if !matches!(
            msg,
            TradingMsg::Fill { .. }
                | TradingMsg::FundingSettlement { .. }
                | TradingMsg::Order { .. }
                | TradingMsg::OrderStateChange { .. }
        ) {
            if let Some(tx) = tx {
                let _ = crate::database::try_send_trading_msg(tx, msg, "recovery_postcommit");
            }
        }
    }
}
fn valid_execution(e: &ExecutionUpdate) -> bool {
    if e.exec_id.is_empty()
        || e.symbol.is_empty()
        || e.exec_time.parse::<u64>().ok().filter(|t| *t > 0).is_none()
    {
        return false;
    }
    if super::funding_settlement::is_funding_execution(e) {
        return e.exec_fee.parse::<f64>().is_ok_and(f64::is_finite);
    }
    !e.order_id.is_empty()
        && matches!(e.side.as_str(), "Buy" | "Sell")
        && [&e.exec_qty, &e.exec_price]
            .iter()
            .all(|s| s.parse::<f64>().is_ok_and(|n| n.is_finite() && n > 0.0))
        && (e.exec_fee.is_empty() || e.exec_fee.parse::<f64>().is_ok_and(f64::is_finite))
}
fn attributable(e: &ExecutionUpdate, state: &LoopState) -> bool {
    let matched = if !e.order_link_id.is_empty() {
        state.pending_orders.get(&e.order_link_id)
    } else if let Some(id) = state.order_id_to_link.get(&e.order_id) {
        state.pending_orders.get(id)
    } else {
        // A symbol/side match cannot prove venue ownership after a crash.
        // Only the durable link or an explicitly bound venue ID may attribute it.
        None
    };
    matched.is_some_and(|p| p.symbol == e.symbol && p.is_long == (e.side == "Buy"))
}
