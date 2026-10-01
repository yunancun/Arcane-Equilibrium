//! PostgreSQL inbox + accounting projection, under one fenced engine owner.
//! A session advisory lock prevents concurrent consumers; the generation CAS
//! also rejects stale checkpoints. No retention job may delete execution IDs.
use super::execution_recovery::Checkpoint;
use super::types::PendingOrder;
use crate::{
    bybit_private_ws::ExecutionUpdate, database::TradingMsg, order_manager::CreateOrderRequest,
};
use serde_json::Value;
use sha2::{Digest, Sha256};
use sqlx::{Connection, PgConnection, PgPool};

pub(super) const TERMINAL_QUERY: &str = "SELECT progress FROM trading.bybit_order_intents WHERE engine_mode=$1 AND venue_order_id IS NOT NULL AND progress->'progress'->>'status' IN ('Cancelled','PartiallyFilledCanceled','Rejected','Deactivated') AND NOT COALESCE((progress->'progress'->>'terminal_reconciliation_complete')::boolean,FALSE) ORDER BY order_link_id LIMIT 4097";

pub(super) type Result<T> = std::result::Result<T, String>;
pub(super) struct RecoveryStore {
    conn: PgConnection,
    engine: String,
    generation: i64,
}

impl RecoveryStore {
    pub(super) async fn open(
        pool: &PgPool,
        engine: &str,
        account: &str,
        initial: &Checkpoint,
    ) -> Result<(Self, Checkpoint)> {
        // Detach: dropping the owner closes this connection and releases its
        // session lock. Never return a locked session to the pool.
        let mut conn = pool.acquire().await.map_err(err)?.detach();
        sqlx::query("SET statement_timeout = '5s'")
            .execute(&mut conn)
            .await
            .map_err(err)?;
        sqlx::query("SET lock_timeout = '1s'")
            .execute(&mut conn)
            .await
            .map_err(err)?;
        sqlx::query("SET synchronous_commit = on")
            .execute(&mut conn)
            .await
            .map_err(err)?;
        let locked: bool = sqlx::query_scalar(
            "SELECT pg_try_advisory_lock(hashtextextended('bybit-execution:' || $1, 0))",
        )
        .bind(engine)
        .fetch_one(&mut conn)
        .await
        .map_err(err)?;
        if !locked {
            return Err("another execution recovery owner holds this engine".into());
        }
        let existing: Option<(String, i64, Value)> = sqlx::query_as(
            "SELECT account_scope, generation, checkpoint FROM trading.bybit_recovery WHERE engine_mode=$1")
            .bind(engine).fetch_optional(&mut conn).await.map_err(err)?;
        let (generation, checkpoint) = if let Some((scope, generation, value)) = existing {
            if scope != account {
                return Err(
                    "account/environment scope changed; explicit reconciliation required".into(),
                );
            }
            let checkpoint: Checkpoint = serde_json::from_value(value).map_err(err)?;
            checkpoint.validate()?;
            (generation, checkpoint)
        } else {
            // Never seed a new ledger from a possibly ahead-of-execution venue
            // snapshot or legacy async aggregates. First adoption needs a clean
            // empty lane; brownfield recovery is explicitly fail-closed.
            let legacy: bool = sqlx::query_scalar(
                "SELECT EXISTS (SELECT 1 FROM trading.orders WHERE engine_mode=$1 UNION ALL SELECT 1 FROM trading.fills WHERE engine_mode=$1 UNION ALL SELECT 1 FROM trading.funding_settlements WHERE engine_mode=$1 UNION ALL SELECT 1 FROM trading.order_state_changes WHERE engine_mode=$1)",
            )
            .bind(engine)
            .fetch_one(&mut conn)
            .await
            .map_err(err)?;
            if legacy || !initial.paper.positions.is_empty() {
                return Err(
                    "legacy accounting/positions require an explicitly reconciled recovery baseline"
                        .into(),
                );
            }
            initial.validate()?;
            sqlx::query("INSERT INTO trading.bybit_recovery(engine_mode,account_scope,generation,checkpoint) VALUES($1,$2,0,$3)")
                .bind(engine).bind(account).bind(serde_json::to_value(initial).map_err(err)?)
                .execute(&mut conn).await.map_err(err)?;
            (0, initial.clone())
        };
        Ok((
            Self {
                conn,
                engine: engine.into(),
                generation,
            },
            checkpoint,
        ))
    }

    pub(super) async fn unapplied(&mut self) -> Result<Vec<ExecutionUpdate>> {
        let rows: Vec<Value> = sqlx::query_scalar("SELECT payload FROM trading.bybit_execution_inbox WHERE engine_mode=$1 AND NOT applied ORDER BY receive_seq LIMIT 4097")
            .bind(&self.engine).fetch_all(&mut self.conn).await.map_err(err)?;
        if rows.len() > 4096 {
            return Err("recovery backlog exceeds bounded startup budget".into());
        }
        rows.into_iter()
            .map(|v| serde_json::from_value(v).map_err(err))
            .collect()
    }

    /// A terminal WS update can precede its execution. These durable intents
    /// must still receive REST confirmation even after later checkpoints have
    /// replaced the transient retired map.
    pub(super) async fn terminal_orders_to_reconcile(&mut self) -> Result<Vec<PendingOrder>> {
        let rows: Vec<Value> = sqlx::query_scalar(TERMINAL_QUERY)
            .bind(&self.engine)
            .fetch_all(&mut self.conn)
            .await
            .map_err(err)?;
        if rows.len() > 4096 {
            return Err("terminal reconciliation exceeds bounded startup budget".into());
        }
        rows.into_iter()
            .map(|v| serde_json::from_value(v).map_err(err))
            .collect()
    }

    pub(super) async fn registered_outbox_intents(
        &mut self,
        ids: &[String],
    ) -> Result<Vec<String>> {
        if ids.is_empty() {
            return Ok(Vec::new());
        }
        sqlx::query_scalar("SELECT order_link_id FROM trading.bybit_order_intents WHERE engine_mode=$1 AND order_link_id=ANY($2)")
            .bind(&self.engine).bind(ids).fetch_all(&mut self.conn).await.map_err(err)
    }
    pub(super) async fn has_venue_binding(&mut self, link: &str) -> Result<bool> {
        sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM trading.bybit_order_intents WHERE engine_mode=$1 AND order_link_id=$2 AND venue_order_id IS NOT NULL)")
            .bind(&self.engine).bind(link).fetch_one(&mut self.conn).await.map_err(err)
    }

    pub(super) async fn terminal_progress(
        &mut self,
        link: &str,
        venue: &str,
    ) -> Result<PendingOrder> {
        let row: Option<(Value,Option<String>)> = sqlx::query_as("SELECT progress,venue_order_id FROM trading.bybit_order_intents WHERE engine_mode=$1 AND order_link_id=$2")
            .bind(&self.engine).bind(link).fetch_optional(&mut self.conn).await.map_err(err)?;
        let (value, bound) = row.ok_or("completion has no durable intent")?;
        if bound.as_deref() != Some(venue) {
            return Err("completion venue identity differs".into());
        }
        serde_json::from_value(value).map_err(err)
    }

    /// false = already atomically projected, true = durable and needs replay.
    pub(super) async fn receive(&mut self, execution: &ExecutionUpdate) -> Result<bool> {
        let value = serde_json::to_value(execution).map_err(err)?;
        sqlx::query("INSERT INTO trading.bybit_execution_inbox(engine_mode,exec_id,payload,applied) VALUES($1,$2,$3,FALSE) ON CONFLICT(engine_mode,exec_id) DO NOTHING")
            .bind(&self.engine).bind(&execution.exec_id).bind(&value).execute(&mut self.conn).await.map_err(err)?;
        let (old, applied): (Value,bool) = sqlx::query_as("SELECT payload,applied FROM trading.bybit_execution_inbox WHERE engine_mode=$1 AND exec_id=$2")
            .bind(&self.engine).bind(&execution.exec_id).fetch_one(&mut self.conn).await.map_err(err)?;
        let mut old: ExecutionUpdate = serde_json::from_value(old).map_err(err)?;
        // Fast/REST representations may enrich optional fee/maker fields or
        // orderLinkId. They cannot change the execution's economic identity.
        if old.order_id != execution.order_id
            || old.symbol != execution.symbol
            || old.side != execution.side
            || old.exec_qty != execution.exec_qty
            || old.exec_price != execution.exec_price
            || old.exec_time != execution.exec_time
            || (!old.exec_type.is_empty()
                && !execution.exec_type.is_empty()
                && old.exec_type != execution.exec_type)
            || (!old.order_link_id.is_empty()
                && !execution.order_link_id.is_empty()
                && old.order_link_id != execution.order_link_id)
        {
            return Err("conflicting execution identity".into());
        }
        if old.exec_type.is_empty() && !execution.exec_type.is_empty() {
            old.exec_type = execution.exec_type.clone();
            sqlx::query("UPDATE trading.bybit_execution_inbox SET payload=$3 WHERE engine_mode=$1 AND exec_id=$2")
                .bind(&self.engine).bind(&execution.exec_id).bind(serde_json::to_value(old).map_err(err)?)
                .execute(&mut self.conn).await.map_err(err)?;
        }
        Ok(!applied)
    }

    pub(super) async fn bind_order_id(&mut self, link: &str, venue: &str) -> Result<()> {
        if link.is_empty() || venue.is_empty() {
            return Err("order binding requires durable link and venue identity".into());
        }
        let old: Option<Option<String>> = sqlx::query_scalar("SELECT venue_order_id FROM trading.bybit_order_intents WHERE engine_mode=$1 AND order_link_id=$2")
            .bind(&self.engine).bind(link).fetch_optional(&mut self.conn).await.map_err(err)?;
        if old.is_none() {
            return Err("order binding has no durable intent".into());
        }
        if old
            .as_ref()
            .and_then(|x| x.as_ref())
            .is_some_and(|x| x != venue)
        {
            return Err("venue order ID changed for immutable intent".into());
        }
        let updated = sqlx::query("UPDATE trading.bybit_order_intents SET venue_order_id=$3 WHERE engine_mode=$1 AND order_link_id=$2")
            .bind(&self.engine).bind(link).bind(venue).execute(&mut self.conn).await.map_err(err)?;
        if updated.rows_affected() != 1 {
            return Err("order binding did not update exactly one durable intent".into());
        }
        Ok(())
    }
    pub(super) async fn order_for_execution(
        &mut self,
        exec: &ExecutionUpdate,
    ) -> Result<Option<PendingOrder>> {
        let value: Option<Value> = if !exec.order_link_id.is_empty() {
            sqlx::query_scalar("SELECT progress FROM trading.bybit_order_intents WHERE engine_mode=$1 AND order_link_id=$2")
                .bind(&self.engine).bind(&exec.order_link_id).fetch_optional(&mut self.conn).await.map_err(err)?
        } else {
            sqlx::query_scalar("SELECT progress FROM trading.bybit_order_intents WHERE engine_mode=$1 AND venue_order_id=$2")
                .bind(&self.engine).bind(&exec.order_id).fetch_optional(&mut self.conn).await.map_err(err)?
        };
        value
            .map(|v| serde_json::from_value(v).map_err(err))
            .transpose()
    }

    /// Checkpoint, consumption progress, and canonical accounting rows are one
    /// transaction. The original request is immutable and never resubmitted.
    pub(super) fn generation(&self) -> i64 {
        self.generation
    }

    pub(super) async fn commit(
        &mut self,
        checkpoint: &Checkpoint,
        messages: &[TradingMsg],
        execution: Option<&str>,
        intent: Option<(&PendingOrder, &CreateOrderRequest)>,
    ) -> Result<()> {
        // Bound the entire transaction, including all pending progress updates.
        // An uncertain COMMIT is fenced and resolved from PG on restart.
        tokio::time::timeout(
            std::time::Duration::from_secs(5),
            self.commit_inner(checkpoint, messages, execution, intent),
        )
        .await
        .map_err(|_| "recovery transaction deadline exceeded".to_string())?
    }

    async fn commit_inner(
        &mut self,
        checkpoint: &Checkpoint,
        messages: &[TradingMsg],
        execution: Option<&str>,
        intent: Option<(&PendingOrder, &CreateOrderRequest)>,
    ) -> Result<()> {
        checkpoint.validate()?;
        if let Some(id) = execution {
            let accounting = messages
                .iter()
                .filter(|message| match message {
                    TradingMsg::Fill {
                        fill_id,
                        engine_mode,
                        ..
                    } => fill_id == &format!("bybit-{id}") && engine_mode == &self.engine,
                    TradingMsg::FundingSettlement {
                        exec_id,
                        engine_mode,
                        ..
                    } => exec_id == id && engine_mode == &self.engine,
                    _ => false,
                })
                .count();
            if accounting != 1 {
                return Err(
                    "execution was not represented exactly once in canonical accounting".into(),
                );
            }
        }
        let mut tx = self.conn.begin().await.map_err(err)?;
        if let Some((order, request)) = intent {
            if request.category.as_str() != "linear"
                || request.symbol != order.symbol
                || request.order_link_id.as_deref() != Some(order.order_link_id.as_str())
                || (request.side.as_str() == "Buy") != order.is_long
                || request.order_type.as_str().to_ascii_lowercase() != order.order_type
                || !request.qty.is_finite()
                || request.qty < 0.0
                || request.qty != order.qty
                || request.price != order.limit_price
                || request.time_in_force != order.time_in_force
                || request.reduce_only.unwrap_or(false) != order.is_close
                || (request.qty == 0.0
                    && (!order.is_close || request.close_on_trigger != Some(true)))
            {
                return Err("pending identity does not match immutable venue request".into());
            }
            let request = serde_json::to_value(request).map_err(err)?;
            let hash = format!(
                "{:x}",
                Sha256::digest(serde_json::to_vec(&request).map_err(err)?)
            );
            // No ON CONFLICT: even identical attempts cannot acquire permission
            // to send a second request after restart or terminal cleanup.
            sqlx::query("INSERT INTO trading.bybit_order_intents(engine_mode,order_link_id,request_hash,request,pending,progress) VALUES($1,$2,$3,$4,$5,$5)")
                .bind(&self.engine).bind(&order.order_link_id).bind(hash).bind(request)
                .bind(serde_json::to_value(order).map_err(err)?).execute(&mut *tx).await.map_err(err)?;
        }
        for po in checkpoint
            .pending
            .values()
            .chain(checkpoint.retired.values())
        {
            sqlx::query("UPDATE trading.bybit_order_intents SET progress=$3 WHERE engine_mode=$1 AND order_link_id=$2")
                .bind(&self.engine).bind(&po.order_link_id).bind(serde_json::to_value(po).map_err(err)?)
                .execute(&mut *tx).await.map_err(err)?;
        }
        crate::database::recovery_sql::persist(&mut tx, messages)
            .await
            .map_err(err)?;
        if let Some(id) = execution {
            let updated = sqlx::query("UPDATE trading.bybit_execution_inbox SET applied=true WHERE engine_mode=$1 AND exec_id=$2 AND NOT applied")
                .bind(&self.engine).bind(id).execute(&mut *tx).await.map_err(err)?.rows_affected();
            if updated != 1 {
                return Err("execution consumption generation changed".into());
            }
        }
        let updated = sqlx::query("UPDATE trading.bybit_recovery SET checkpoint=$1,generation=generation+1 WHERE engine_mode=$2 AND generation=$3")
            .bind(serde_json::to_value(checkpoint).map_err(err)?).bind(&self.engine).bind(self.generation)
            .execute(&mut *tx).await.map_err(err)?.rows_affected();
        if updated != 1 {
            return Err("stale recovery generation".into());
        }
        tx.commit().await.map_err(err)?;
        self.generation += 1;
        Ok(())
    }
}
fn err(e: impl std::fmt::Display) -> String {
    e.to_string()
}
