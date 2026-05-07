//! Agent Spine DB writer.
//!
//! MAG-032 provides the durable writer surface but does not wire it into
//! runtime startup. That keeps the current legacy trading behavior unchanged
//! until the later shadow integration task explicitly enables it.

use super::batch_insert::{batch_insert_chunked, BatchInsertOutcome};
use super::pool::DbPool;
use crate::agent_spine::events::{
    ExecutionIdempotencyKey, SpineEdge, SpineObjectEnvelope, SpineStateTransition,
};
use crate::agent_spine::store::AgentSpineMsg;
use sqlx::{types::Json, Postgres, QueryBuilder};
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{info, warn};

pub async fn run_agent_spine_writer(
    mut rx: mpsc::Receiver<AgentSpineMsg>,
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) {
    let mut object_buf: Vec<SpineObjectEnvelope> = Vec::with_capacity(32);
    let mut edge_buf: Vec<SpineEdge> = Vec::with_capacity(32);
    let mut transition_buf: Vec<SpineStateTransition> = Vec::with_capacity(16);
    let mut execution_key_buf: Vec<ExecutionIdempotencyKey> = Vec::with_capacity(16);

    let flush_interval = {
        let cfg = config.get();
        std::time::Duration::from_millis(cfg.database.batch_flush_interval_ms)
    };
    let mut flush_timer = tokio::time::interval(flush_interval);
    flush_timer.tick().await;

    info!("agent_spine_writer started / Agent Spine writer 已啟動");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = flush_timer.tick() => {
                if pool.is_available() {
                    flush_all(&pool, &mut object_buf, &mut edge_buf, &mut transition_buf, &mut execution_key_buf).await;
                }
            }
            msg = rx.recv() => {
                match msg {
                    Some(AgentSpineMsg::Object(object)) => object_buf.push(object),
                    Some(AgentSpineMsg::Edge(edge)) => edge_buf.push(edge),
                    Some(AgentSpineMsg::StateTransition(transition)) => transition_buf.push(transition),
                    Some(AgentSpineMsg::ExecutionIdempotencyKey(key)) => execution_key_buf.push(key),
                    None => break,
                }
            }
        }
    }

    if pool.is_available() {
        flush_all(
            &pool,
            &mut object_buf,
            &mut edge_buf,
            &mut transition_buf,
            &mut execution_key_buf,
        )
        .await;
    }

    info!("agent_spine_writer stopped / Agent Spine writer 已停止");
}

async fn flush_all(
    pool: &DbPool,
    objects: &mut Vec<SpineObjectEnvelope>,
    edges: &mut Vec<SpineEdge>,
    transitions: &mut Vec<SpineStateTransition>,
    execution_keys: &mut Vec<ExecutionIdempotencyKey>,
) {
    if !objects.is_empty() {
        flush_objects(pool, objects).await;
    }
    if !edges.is_empty() {
        flush_edges(pool, edges).await;
    }
    if !transitions.is_empty() {
        flush_state_transitions(pool, transitions).await;
    }
    if !execution_keys.is_empty() {
        flush_execution_idempotency_keys(pool, execution_keys).await;
    }
}

const OBJECT_COLS: usize = 20;
const EDGE_COLS: usize = 9;
const TRANSITION_COLS: usize = 9;
const EXECUTION_KEY_COLS: usize = 7;

fn ts_from_ms(ts_ms: u64) -> chrono::DateTime<chrono::Utc> {
    chrono::DateTime::from_timestamp_millis(ts_ms as i64).unwrap_or_default()
}

fn should_clear_buffer(table: &str, outcome: BatchInsertOutcome, pending_rows: usize) -> bool {
    if outcome.all_ok() {
        true
    } else {
        warn!(
            table = table,
            pending_rows = pending_rows,
            rows_affected = outcome.rows_affected,
            failed_chunks = outcome.failed_chunks,
            "agent_spine_writer flush incomplete — retaining buffer for retry"
        );
        false
    }
}

async fn flush_objects(pool: &DbPool, buf: &mut Vec<SpineObjectEnvelope>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "agent.decision_objects flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };

    let outcome = batch_insert_chunked(
        pg,
        pool,
        "agent.decision_objects",
        buf.as_slice(),
        OBJECT_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO agent.decision_objects (created_at, object_id, object_type, object_version, engine_mode, symbol, strategy, signal_id, decision_id, verdict_id, verdict_version, order_plan_id, execution_report_id, lease_id, state, source_agent, authority_mode, idempotency_key, payload_hash, payload) "
            );
            qb.push_values(chunk.iter(), |mut b, row| {
                b.push_bind(ts_from_ms(row.created_at_ms));
                b.push_bind(row.object_id.as_str());
                b.push_bind(row.object_type.as_str());
                b.push_bind(row.object_version.as_str());
                b.push_bind(row.engine_mode.as_str());
                b.push_bind(row.symbol.as_str());
                b.push_bind(row.strategy.as_deref());
                b.push_bind(row.signal_id.as_deref());
                b.push_bind(row.decision_id.as_deref());
                b.push_bind(row.verdict_id.as_deref());
                b.push_bind(row.verdict_version);
                b.push_bind(row.order_plan_id.as_deref());
                b.push_bind(row.execution_report_id.as_deref());
                b.push_bind(row.lease_id.as_deref());
                b.push_bind(row.state.as_str());
                b.push_bind(row.source_agent.as_str());
                b.push_bind(row.authority_mode.as_str());
                b.push_bind(row.idempotency_key.as_str());
                b.push_bind(row.payload_hash.as_str());
                b.push_bind(Json(row.payload.clone()));
            });
            qb.push(" ON CONFLICT (object_type, idempotency_key) DO NOTHING");
            qb
        },
    )
    .await;

    if should_clear_buffer("agent.decision_objects", outcome, buf.len()) {
        buf.clear();
    }
}

async fn flush_edges(pool: &DbPool, buf: &mut Vec<SpineEdge>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "agent.decision_edges flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };

    let outcome = batch_insert_chunked(
        pg,
        pool,
        "agent.decision_edges",
        buf.as_slice(),
        EDGE_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO agent.decision_edges (edge_id, created_at, from_object_id, to_object_id, edge_type, engine_mode, decision_id, payload_hash, details) "
            );
            qb.push_values(chunk.iter(), |mut b, row| {
                b.push_bind(row.edge_id.as_str());
                b.push_bind(ts_from_ms(row.created_at_ms));
                b.push_bind(row.from_object_id.as_str());
                b.push_bind(row.to_object_id.as_str());
                b.push_bind(row.edge_type.as_str());
                b.push_bind(row.engine_mode.as_str());
                b.push_bind(row.decision_id.as_deref());
                b.push_bind(row.payload_hash.as_deref());
                b.push_bind(Json(row.details.clone()));
            });
            qb.push(" ON CONFLICT (from_object_id, to_object_id, edge_type) DO NOTHING");
            qb
        },
    )
    .await;

    if should_clear_buffer("agent.decision_edges", outcome, buf.len()) {
        buf.clear();
    }
}

async fn flush_state_transitions(pool: &DbPool, buf: &mut Vec<SpineStateTransition>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "agent.decision_state_changes flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };

    let outcome = batch_insert_chunked(
        pg,
        pool,
        "agent.decision_state_changes",
        buf.as_slice(),
        TRANSITION_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO agent.decision_state_changes (ts, transition_id, object_id, object_type, from_state, to_state, engine_mode, trigger, details) "
            );
            qb.push_values(chunk.iter(), |mut b, row| {
                b.push_bind(ts_from_ms(row.ts_ms));
                b.push_bind(row.transition_id.as_str());
                b.push_bind(row.object_id.as_str());
                b.push_bind(row.object_type.as_str());
                b.push_bind(row.from_state.as_deref());
                b.push_bind(row.to_state.as_str());
                b.push_bind(row.engine_mode.as_str());
                b.push_bind(row.trigger.as_str());
                b.push_bind(Json(row.details.clone()));
            });
            qb.push(" ON CONFLICT (transition_id, ts) DO NOTHING");
            qb
        },
    )
    .await;

    if should_clear_buffer("agent.decision_state_changes", outcome, buf.len()) {
        buf.clear();
    }
}

async fn flush_execution_idempotency_keys(pool: &DbPool, buf: &mut Vec<ExecutionIdempotencyKey>) {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            warn!(
                pending_rows = buf.len(),
                "agent.execution_idempotency_keys flush skipped: DB pool unavailable — retaining buffer"
            );
            return;
        }
    };

    let outcome = batch_insert_chunked(
        pg,
        pool,
        "agent.execution_idempotency_keys",
        buf.as_slice(),
        EXECUTION_KEY_COLS,
        |chunk| {
            let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO agent.execution_idempotency_keys (idempotency_key, order_plan_id, decision_id, engine_mode, first_seen_at, status, details) "
            );
            qb.push_values(chunk.iter(), |mut b, row| {
                b.push_bind(row.idempotency_key.as_str());
                b.push_bind(row.order_plan_id.as_str());
                b.push_bind(row.decision_id.as_str());
                b.push_bind(row.engine_mode.as_str());
                b.push_bind(ts_from_ms(row.first_seen_at_ms));
                b.push_bind(row.status.as_str());
                b.push_bind(Json(row.details.clone()));
            });
            qb.push(" ON CONFLICT (idempotency_key) DO NOTHING");
            qb
        },
    )
    .await;

    if should_clear_buffer("agent.execution_idempotency_keys", outcome, buf.len()) {
        buf.clear();
    }
}
