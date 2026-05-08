//! W-AUDIT-3 F-15: Decision Lease router flag flip regression.
//!
//! Covers the path that was unblocked by W-AUDIT-2 F-03:
//! router gate flag ON -> IntentProcessor acquires a Production lease ->
//! GovernanceCore emits lease transition messages -> engine writer can persist
//! those rows into `learning.lease_transitions` when an explicit test PG is
//! provided.
//!
//! The DB case is opt-in via `OPENCLAW_TEST_PG`; it never uses runtime DB envs.

use openclaw_core::governance_core::{
    GovernanceCore, GovernanceProfile, LeaseId, LeaseOutcome, LeaseTransitionMsg,
};
use openclaw_engine::config::ConfigManager;
use openclaw_engine::database::lease_transition_writer::spawn_lease_transition_pipeline;
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::database::DatabaseConfig;
use openclaw_engine::intent_processor::{IntentProcessor, OrderIntent};
use openclaw_engine::paper_state::PaperState;
use sqlx::postgres::{PgPool, PgPoolOptions};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio_util::sync::CancellationToken;

const NOW_MS: u64 = 1_700_000_000_000;

fn make_intent(symbol: &str) -> OrderIntent {
    OrderIntent {
        symbol: symbol.to_string(),
        is_long: true,
        qty: 0.001,
        confidence: 0.7,
        strategy: "w_audit_3_f15".to_string(),
        order_type: "market".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    }
}

fn make_state(symbol: &str) -> PaperState {
    let mut state = PaperState::new(10_000.0);
    state.set_latest_price(symbol, 30_000.0);
    state.set_latest_turnover(symbol, 100_000_000.0);
    state
}

fn make_authorized_router_gov(
    tx: Option<std::sync::mpsc::Sender<LeaseTransitionMsg>>,
) -> GovernanceCore {
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();
    gov.set_router_gate_enabled_for_test(true);
    gov.set_engine_mode_tag("demo".to_string());
    if let Some(tx) = tx {
        gov.set_lease_transition_tx(tx);
    }
    gov
}

fn route_one_production_intent(gov: &GovernanceCore) -> String {
    let proc = IntentProcessor::new();
    let state = make_state("BTCUSDT");
    let result = proc.process_with_features(
        &make_intent("BTCUSDT"),
        gov,
        &state,
        2_000.0,
        GovernanceProfile::Production,
        None,
        None,
        NOW_MS,
    );
    assert!(result.submitted, "router-gated Production intent must pass");
    result
        .lease_id
        .expect("router gate ON + Production must return a lease id")
}

fn collect_msgs(
    rx: &std::sync::mpsc::Receiver<LeaseTransitionMsg>,
    expected: usize,
) -> Vec<LeaseTransitionMsg> {
    let mut msgs = Vec::with_capacity(expected);
    for _ in 0..expected {
        msgs.push(
            rx.recv_timeout(Duration::from_secs(1))
                .expect("lease transition msg not emitted within timeout"),
        );
    }
    msgs
}

#[test]
fn router_flag_flip_emits_writer_channel_transitions() {
    let (tx, rx) = std::sync::mpsc::channel::<LeaseTransitionMsg>();
    let gov = make_authorized_router_gov(Some(tx));
    assert!(
        gov.router_gate_enabled(),
        "test must flip the router gate ON"
    );
    assert!(
        gov.lease_transition_writer_configured(),
        "writer channel must be injected before routing"
    );

    let lease_id = route_one_production_intent(&gov);
    gov.release_lease(&LeaseId::Active(lease_id.clone()), LeaseOutcome::Consumed)
        .expect("fill-consumer style lease release must succeed");

    let msgs = collect_msgs(&rx, 5);
    let states: Vec<&str> = msgs.iter().map(|m| m.to_state.as_str()).collect();
    assert_eq!(
        states,
        ["DRAFT", "REGISTERED", "ACTIVE", "BRIDGED", "CONSUMED"]
    );
    assert!(msgs.iter().all(|m| m.lease_id == lease_id));
    assert!(msgs.iter().all(|m| m.profile == "Production"));
    assert!(msgs.iter().all(|m| m.engine_mode == "demo"));
    assert!(
        msgs.iter()
            .any(|m| m.context_id == format!("intent-router-BTCUSDT-{NOW_MS}")),
        "acquire rows must carry the router intent context"
    );
}

async fn maybe_pg_pool() -> Option<PgPool> {
    let url = std::env::var("OPENCLAW_TEST_PG").ok()?;
    match PgPoolOptions::new()
        .max_connections(2)
        .acquire_timeout(Duration::from_secs(5))
        .connect(&url)
        .await
    {
        Ok(pool) => Some(pool),
        Err(e) => {
            eprintln!("[lease_flag_flip_e2e] OPENCLAW_TEST_PG set but connect failed: {e}");
            None
        }
    }
}

async fn build_test_db_pool() -> Option<Arc<DbPool>> {
    let url = std::env::var("OPENCLAW_TEST_PG").ok()?;
    let mut cfg = DatabaseConfig::default();
    cfg.database_url = url;
    cfg.db_writes_enabled = true;
    cfg.pool_max_connections = 2;
    cfg.connect_timeout_ms = 5_000;
    let pool = DbPool::connect(&cfg).await;
    if !pool.is_available() {
        eprintln!("[lease_flag_flip_e2e] DbPool is unavailable; skipping DB e2e");
        return None;
    }
    Some(Arc::new(pool))
}

async fn ensure_lease_transition_table(pool: &PgPool) -> Result<(), sqlx::Error> {
    sqlx::query("CREATE SCHEMA IF NOT EXISTS learning")
        .execute(pool)
        .await?;
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS learning.lease_transitions (
            transition_id      TEXT        NOT NULL,
            lease_id           TEXT        NOT NULL,
            from_state         TEXT,
            to_state           TEXT        NOT NULL,
            event              TEXT        NOT NULL,
            initiator          TEXT        NOT NULL,
            reason_codes       TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
            requires_approval  BOOLEAN     NOT NULL DEFAULT FALSE,
            approved_by        TEXT,
            profile            TEXT        NOT NULL,
            engine_mode        TEXT        NOT NULL,
            context_id         TEXT,
            ts_ms              BIGINT      NOT NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (transition_id, created_at)
        )",
    )
    .execute(pool)
    .await?;
    Ok(())
}

async fn count_lease_rows(pool: &PgPool, lease_id: &str) -> Result<i64, sqlx::Error> {
    sqlx::query_scalar("SELECT COUNT(*) FROM learning.lease_transitions WHERE lease_id = $1")
        .bind(lease_id)
        .fetch_one(pool)
        .await
}

#[tokio::test]
async fn router_flag_flip_writes_lease_transition_rows_when_test_pg_present() {
    let Some(pg_pool) = maybe_pg_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };
    ensure_lease_transition_table(&pg_pool)
        .await
        .expect("ensure lease_transitions table");

    let Some(db_pool) = build_test_db_pool().await else {
        return;
    };
    let config = Arc::new(
        ConfigManager::load(Some("/tmp/nonexistent_openclaw_f15_e2e.toml"))
            .expect("default config load"),
    );
    let cancel = CancellationToken::new();
    let tx = spawn_lease_transition_pipeline(db_pool.clone(), config, cancel.clone());
    let gov = make_authorized_router_gov(Some(tx));

    let lease_id = route_one_production_intent(&gov);
    gov.release_lease(&LeaseId::Active(lease_id.clone()), LeaseOutcome::Consumed)
        .expect("fill-consumer style lease release must succeed");

    let deadline = Instant::now() + Duration::from_secs(7);
    let mut observed = 0_i64;
    while Instant::now() < deadline {
        observed = count_lease_rows(&pg_pool, &lease_id)
            .await
            .expect("count lease rows");
        if observed >= 5 {
            break;
        }
        tokio::time::sleep(Duration::from_millis(200)).await;
    }

    let states: Vec<String> = sqlx::query_scalar(
        "SELECT DISTINCT to_state FROM learning.lease_transitions
         WHERE lease_id = $1 ORDER BY to_state",
    )
    .bind(&lease_id)
    .fetch_all(&pg_pool)
    .await
    .expect("select lease transition states");

    let _ = sqlx::query("DELETE FROM learning.lease_transitions WHERE lease_id = $1")
        .bind(&lease_id)
        .execute(&pg_pool)
        .await;
    cancel.cancel();
    db_pool.close().await;
    pg_pool.close().await;

    assert!(
        observed >= 5,
        "expected at least 5 DB rows for {lease_id}, got {observed}"
    );
    for required in ["ACTIVE", "BRIDGED", "CONSUMED", "DRAFT", "REGISTERED"] {
        assert!(
            states.iter().any(|s| s == required),
            "missing persisted state {required}; states={states:?}"
        );
    }
    assert!(lease_id.starts_with("lease:"));
}
