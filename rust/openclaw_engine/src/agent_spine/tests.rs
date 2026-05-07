use super::config::AgentSpineMode;
use super::contracts::{
    ExecutionPlan, GuardianVerdict, StrategistDecision, StrategySignalDirection,
    EXECUTION_PLAN_SCHEMA_VERSION, GUARDIAN_VERDICT_SCHEMA_VERSION,
    STRATEGIST_DECISION_SCHEMA_VERSION, STRATEGY_SIGNAL_SCHEMA_VERSION,
};
use super::events::{
    DecisionEdgeType, DecisionObjectType, ExecutionIdempotencyKey, SpineEdge, SpineObjectEnvelope,
    SpineStateTransition,
};
use super::signal_adapter::{strategy_signal_from_open_intent, strategy_signal_to_trading_msg};
use super::store::{AgentSpineMsg, AgentSpineStore, ChannelAgentSpineStore};
use crate::database::TradingMsg;
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use serde_json::json;
use std::str::FromStr;

fn sample_intent(is_long: bool) -> OrderIntent {
    OrderIntent {
        symbol: "BTCUSDT".to_string(),
        is_long,
        qty: 1.25,
        confidence: 0.72,
        strategy: "grid_trading".to_string(),
        order_type: "limit".to_string(),
        limit_price: Some(101.25),
        confluence_score: Some(33.0),
        persistence_elapsed_ms: Some(42_000),
        time_in_force: Some(TimeInForce::PostOnly),
        maker_timeout_ms: Some(90_000),
    }
}

#[test]
fn agent_spine_mode_defaults_disabled_and_shadow_is_non_enforcing() {
    assert_eq!(AgentSpineMode::default(), AgentSpineMode::Disabled);
    assert!(!AgentSpineMode::Disabled.writes_enabled());
    assert!(AgentSpineMode::Shadow.writes_enabled());
    assert!(!AgentSpineMode::Shadow.enforces_new_exposure());
    assert!(!AgentSpineMode::Shadow.store_error_blocks_new_exposure());
    assert!(AgentSpineMode::Primary.enforces_new_exposure());
    assert!(AgentSpineMode::Primary.store_error_blocks_new_exposure());
    assert_eq!(
        AgentSpineMode::from_str("canary").unwrap(),
        AgentSpineMode::Canary
    );
    assert!(AgentSpineMode::from_str("legacy_gate").is_err());
}

#[test]
fn open_intent_maps_to_typed_strategy_signal_without_execution_authority() {
    let signal = strategy_signal_from_open_intent(
        "sig-paper-grid_trading-BTCUSDT-123",
        "ctx-paper-BTCUSDT-123",
        123,
        "paper",
        &sample_intent(true),
    );

    assert_eq!(signal.schema_version, STRATEGY_SIGNAL_SCHEMA_VERSION);
    assert_eq!(signal.signal_id, "sig-paper-grid_trading-BTCUSDT-123");
    assert_eq!(signal.context_id.as_deref(), Some("ctx-paper-BTCUSDT-123"));
    assert_eq!(signal.engine_mode, "paper");
    assert_eq!(signal.symbol, "BTCUSDT");
    assert_eq!(signal.strategy, "grid_trading");
    assert_eq!(signal.direction, StrategySignalDirection::Long);
    assert_eq!(signal.raw_signal_strength, 0.72);
    assert_eq!(signal.confidence, 0.72);
    assert_eq!(signal.order_type.as_deref(), Some("limit"));
    assert_eq!(signal.limit_price, Some(101.25));
    assert_eq!(signal.time_in_force.as_deref(), Some("PostOnly"));
    assert_eq!(signal.maker_timeout_ms, Some(90_000));
    assert_eq!(signal.evidence_refs, vec!["ctx-paper-BTCUSDT-123"]);

    let json = serde_json::to_value(&signal).unwrap();
    assert!(json.get("decision_id").is_none());
    assert!(json.get("verdict_id").is_none());
    assert!(json.get("order_plan_id").is_none());
    assert!(json.get("lease_id").is_none());
}

#[test]
fn typed_strategy_signal_preserves_legacy_trading_signal_persistence_shape() {
    let signal = strategy_signal_from_open_intent(
        "sig-live_demo-grid_trading-BTCUSDT-456",
        "ctx-live_demo-BTCUSDT-456",
        456,
        "live_demo",
        &sample_intent(false),
    );

    let msg = strategy_signal_to_trading_msg(&signal);

    match msg {
        TradingMsg::Signal {
            signal_id,
            ts_ms,
            symbol,
            strategy_name,
            timeframe,
            signal_type,
            strength,
            context_id,
        } => {
            assert_eq!(signal_id, "sig-live_demo-grid_trading-BTCUSDT-456");
            assert_eq!(ts_ms, 456);
            assert_eq!(symbol, "BTCUSDT");
            assert_eq!(strategy_name, "grid_trading");
            assert_eq!(timeframe, "1m");
            assert_eq!(signal_type, "OpenShort");
            assert_eq!(strength, 0.72);
            assert_eq!(context_id, "ctx-live_demo-BTCUSDT-456");
        }
        other => panic!("expected TradingMsg::Signal, got {other:?}"),
    }
}

#[test]
fn durable_spine_objects_model_signal_decision_verdict_plan_chain() {
    let signal = strategy_signal_from_open_intent(
        "sig-paper-grid_trading-BTCUSDT-789",
        "ctx-paper-BTCUSDT-789",
        789,
        "paper",
        &sample_intent(true),
    );
    let signal_obj = SpineObjectEnvelope::from_strategy_signal(&signal, AgentSpineMode::Shadow)
        .expect("strategy signal envelope");

    let decision = StrategistDecision {
        schema_version: STRATEGIST_DECISION_SCHEMA_VERSION.to_string(),
        decision_id: "decision-paper-BTCUSDT-789".to_string(),
        signal_id: signal.signal_id.clone(),
        ts_ms: 790,
        engine_mode: "paper".to_string(),
        symbol: "BTCUSDT".to_string(),
        strategy: "grid_trading".to_string(),
        direction: StrategySignalDirection::Long,
        confidence: 0.71,
        proposed_qty: Some(1.25),
        proposed_price: Some(101.25),
        rationale: Some("shadow proposal".to_string()),
        evidence_refs: vec![signal.signal_id.clone()],
        metadata: json!({"mode": "shadow"}),
    };
    let decision_obj =
        SpineObjectEnvelope::from_strategist_decision(&decision, AgentSpineMode::Shadow)
            .expect("strategist decision envelope");

    let verdict = GuardianVerdict {
        schema_version: GUARDIAN_VERDICT_SCHEMA_VERSION.to_string(),
        verdict_id: "verdict-paper-BTCUSDT-789-v1".to_string(),
        decision_id: decision.decision_id.clone(),
        verdict_version: 1,
        ts_ms: 791,
        engine_mode: "paper".to_string(),
        symbol: "BTCUSDT".to_string(),
        strategy: "grid_trading".to_string(),
        allow: true,
        risk_level: "low".to_string(),
        reasons: vec!["shadow_only".to_string()],
        metadata: json!({}),
    };
    let verdict_obj = SpineObjectEnvelope::from_guardian_verdict(&verdict, AgentSpineMode::Shadow)
        .expect("guardian verdict envelope");

    let plan = ExecutionPlan {
        schema_version: EXECUTION_PLAN_SCHEMA_VERSION.to_string(),
        order_plan_id: "plan-paper-BTCUSDT-789".to_string(),
        decision_id: decision.decision_id.clone(),
        verdict_id: verdict.verdict_id.clone(),
        ts_ms: 792,
        engine_mode: "paper".to_string(),
        symbol: "BTCUSDT".to_string(),
        strategy: "grid_trading".to_string(),
        direction: StrategySignalDirection::Long,
        qty: 1.25,
        order_type: "limit".to_string(),
        limit_price: Some(101.25),
        time_in_force: Some("PostOnly".to_string()),
        lease_id: Some("lease-paper-BTCUSDT-789".to_string()),
        idempotency_key: "idem-paper-BTCUSDT-789".to_string(),
        metadata: json!({"writer": "mag032"}),
    };
    let plan_obj = SpineObjectEnvelope::from_execution_plan(&plan, AgentSpineMode::Shadow)
        .expect("execution plan envelope");

    assert_eq!(signal_obj.object_type, DecisionObjectType::StrategySignal);
    assert_eq!(
        decision_obj.decision_id.as_deref(),
        Some(decision.decision_id.as_str())
    );
    assert_eq!(verdict_obj.verdict_version, Some(1));
    assert_eq!(
        plan_obj.order_plan_id.as_deref(),
        Some(plan.order_plan_id.as_str())
    );
    assert!(plan_obj.payload_hash.starts_with("sha256:"));
    assert_eq!(plan_obj.payload_hash.len(), "sha256:".len() + 64);

    let signal_edge = SpineEdge::new(
        793,
        signal_obj.object_id.clone(),
        decision_obj.object_id.clone(),
        DecisionEdgeType::SignalFor,
        "paper",
        Some(decision.decision_id.clone()),
        json!({"contract": "signal_to_decision"}),
    );
    let verdict_edge = SpineEdge::new(
        794,
        decision_obj.object_id.clone(),
        verdict_obj.object_id.clone(),
        DecisionEdgeType::ReviewedBy,
        "paper",
        Some(decision.decision_id.clone()),
        json!({"contract": "decision_to_verdict"}),
    );
    let plan_edge = SpineEdge::new(
        795,
        verdict_obj.object_id.clone(),
        plan_obj.object_id.clone(),
        DecisionEdgeType::PlannedBy,
        "paper",
        Some(decision.decision_id.clone()),
        json!({"contract": "verdict_to_plan"}),
    );

    assert_eq!(signal_edge.edge_type.as_str(), "signal_for");
    assert_eq!(verdict_edge.edge_type.as_str(), "reviewed_by");
    assert_eq!(plan_edge.edge_type.as_str(), "planned_by");
    assert_ne!(signal_edge.edge_id, verdict_edge.edge_id);
    assert_eq!(
        signal_edge.decision_id.as_deref(),
        Some(decision.decision_id.as_str())
    );
}

#[tokio::test]
async fn channel_spine_store_queues_object_edge_transition_and_idempotency_key() {
    let signal = strategy_signal_from_open_intent(
        "sig-paper-grid_trading-ETHUSDT-900",
        "ctx-paper-ETHUSDT-900",
        900,
        "paper",
        &sample_intent(true),
    );
    let object = SpineObjectEnvelope::from_strategy_signal(&signal, AgentSpineMode::Shadow)
        .expect("strategy signal envelope");
    let edge = SpineEdge::new(
        901,
        object.object_id.clone(),
        "decision-paper-ETHUSDT-900",
        DecisionEdgeType::SignalFor,
        "paper",
        Some("decision-paper-ETHUSDT-900".to_string()),
        json!({}),
    );
    let transition = SpineStateTransition::new(
        902,
        object.object_id.clone(),
        DecisionObjectType::StrategySignal,
        None,
        "observed",
        "paper",
        "strategy_emit",
        json!({}),
    );
    let plan = ExecutionPlan {
        schema_version: EXECUTION_PLAN_SCHEMA_VERSION.to_string(),
        order_plan_id: "plan-paper-ETHUSDT-900".to_string(),
        decision_id: "decision-paper-ETHUSDT-900".to_string(),
        verdict_id: "verdict-paper-ETHUSDT-900-v1".to_string(),
        ts_ms: 903,
        engine_mode: "paper".to_string(),
        symbol: "ETHUSDT".to_string(),
        strategy: "grid_trading".to_string(),
        direction: StrategySignalDirection::Long,
        qty: 0.5,
        order_type: "limit".to_string(),
        limit_price: Some(2400.0),
        time_in_force: Some("PostOnly".to_string()),
        lease_id: None,
        idempotency_key: "idem-paper-ETHUSDT-900".to_string(),
        metadata: json!({}),
    };
    let key = ExecutionIdempotencyKey::reserved(&plan, 904);

    let (tx, mut rx) = tokio::sync::mpsc::channel(4);
    let store = ChannelAgentSpineStore::new(tx);

    assert!(store.put_object(object.clone()).accepted);
    assert!(store.put_edge(edge.clone()).accepted);
    assert!(store.put_state_transition(transition.clone()).accepted);
    assert!(store.reserve_execution_key(key.clone()).accepted);

    assert!(matches!(rx.recv().await.unwrap(), AgentSpineMsg::Object(row) if row == object));
    assert!(matches!(rx.recv().await.unwrap(), AgentSpineMsg::Edge(row) if row == edge));
    assert!(
        matches!(rx.recv().await.unwrap(), AgentSpineMsg::StateTransition(row) if row == transition)
    );
    assert!(
        matches!(rx.recv().await.unwrap(), AgentSpineMsg::ExecutionIdempotencyKey(row) if row == key)
    );
}
