use super::config::AgentSpineMode;
use super::contracts::{
    ExecutionAuthoritySource, ExecutionMakerPreference, ExecutionOrderStyle, ExecutionPlan,
    ExecutionReport, ExecutionUrgency, GuardianP2Modification, GuardianVerdict, StrategistDecision,
    StrategySignalDirection, EXECUTION_PLAN_SCHEMA_VERSION, EXECUTION_REPORT_SCHEMA_VERSION,
    GUARDIAN_VERDICT_SCHEMA_VERSION, STRATEGIST_DECISION_SCHEMA_VERSION,
    STRATEGY_SIGNAL_SCHEMA_VERSION,
};
use super::events::{
    DecisionEdgeType, DecisionObjectType, ExecutionIdempotencyKey, SpineEdge, SpineObjectEnvelope,
    SpineStateTransition,
};
use super::runtime_shadow::{emit_entry_lineage, RuntimeShadowLineageInput};
use super::signal_adapter::{strategy_signal_from_open_intent, strategy_signal_to_trading_msg};
use super::store::{AgentSpineMsg, AgentSpineStore, ChannelAgentSpineStore};
use crate::database::TradingMsg;
use crate::intent_processor::{OrderIntent, VerdictInfo};
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
fn runtime_shadow_lineage_emits_complete_demo_chain() {
    let (tx, mut rx) = tokio::sync::mpsc::channel(16);
    let intent = sample_intent(true);
    let verdict = VerdictInfo {
        verdict: "Approved".to_string(),
        risk_score: 0.22,
        reasons: vec!["guardian_checks".to_string()],
        modified_qty: None,
    };

    let accepted = emit_entry_lineage(
        Some(&tx),
        AgentSpineMode::Shadow,
        RuntimeShadowLineageInput {
            signal_id: "sig-demo-grid_trading-BTCUSDT-900",
            context_id: "ctx-demo-BTCUSDT-900",
            intent_id: "intent-demo-BTCUSDT-900",
            verdict_id: "vrd-demo-BTCUSDT-900",
            ts_ms: 900,
            engine_mode: "demo",
            intent: &intent,
            approved_qty: 0.75,
            reference_price: 101.20,
            verdict_info: Some(&verdict),
            order_link_id: Some("oc_900_1"),
        },
    );

    assert_eq!(accepted, 10);
    let mut objects = Vec::new();
    let mut edges = Vec::new();
    let mut execution_keys = Vec::new();
    while let Ok(msg) = rx.try_recv() {
        match msg {
            AgentSpineMsg::Object(object) => objects.push(object),
            AgentSpineMsg::Edge(edge) => edges.push(edge),
            AgentSpineMsg::ExecutionIdempotencyKey(key) => execution_keys.push(key),
            AgentSpineMsg::StateTransition(_) => {
                panic!("runtime shadow emits no state transitions")
            }
        }
    }

    assert_eq!(objects.len(), 5);
    assert_eq!(edges.len(), 4);
    assert_eq!(execution_keys.len(), 1);
    assert!(objects
        .iter()
        .all(|object| object.authority_mode == AgentSpineMode::Shadow));
    assert!(objects
        .iter()
        .any(|object| object.object_type == DecisionObjectType::StrategySignal));
    assert!(objects
        .iter()
        .any(|object| object.object_type == DecisionObjectType::StrategistDecision));
    assert!(objects
        .iter()
        .any(|object| object.object_type == DecisionObjectType::GuardianVerdict));
    assert!(objects
        .iter()
        .any(|object| object.object_type == DecisionObjectType::ExecutionPlan));
    assert!(objects
        .iter()
        .any(|object| object.object_type == DecisionObjectType::ExecutionReport));
    assert!(edges
        .iter()
        .any(|edge| edge.edge_type == DecisionEdgeType::SignalFor));
    assert!(edges
        .iter()
        .any(|edge| edge.edge_type == DecisionEdgeType::ReviewedBy));
    assert!(edges
        .iter()
        .any(|edge| edge.edge_type == DecisionEdgeType::PlannedBy));
    assert!(edges
        .iter()
        .any(|edge| edge.edge_type == DecisionEdgeType::ExecutedBy));
    assert_eq!(execution_keys[0].engine_mode, "demo");
}

#[test]
fn runtime_shadow_lineage_is_disabled_for_unscoped_modes() {
    let (tx, mut rx) = tokio::sync::mpsc::channel(16);
    let intent = sample_intent(true);

    let disabled = emit_entry_lineage(
        Some(&tx),
        AgentSpineMode::Disabled,
        RuntimeShadowLineageInput {
            signal_id: "sig-demo-grid_trading-BTCUSDT-901",
            context_id: "ctx-demo-BTCUSDT-901",
            intent_id: "intent-demo-BTCUSDT-901",
            verdict_id: "vrd-demo-BTCUSDT-901",
            ts_ms: 901,
            engine_mode: "demo",
            intent: &intent,
            approved_qty: 0.75,
            reference_price: 101.20,
            verdict_info: None,
            order_link_id: None,
        },
    );
    let paper = emit_entry_lineage(
        Some(&tx),
        AgentSpineMode::Shadow,
        RuntimeShadowLineageInput {
            signal_id: "sig-paper-grid_trading-BTCUSDT-902",
            context_id: "ctx-paper-BTCUSDT-902",
            intent_id: "intent-paper-BTCUSDT-902",
            verdict_id: "vrd-paper-BTCUSDT-902",
            ts_ms: 902,
            engine_mode: "paper",
            intent: &intent,
            approved_qty: 0.75,
            reference_price: 101.20,
            verdict_info: None,
            order_link_id: None,
        },
    );

    assert_eq!(disabled, 0);
    assert_eq!(paper, 0);
    assert!(rx.try_recv().is_err());
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
        decision_action: "open".to_string(),
        selected_strategy: Some("grid_trading".to_string()),
        selected_candidate_id: Some(signal.signal_id.clone()),
        candidate_scores: json!([{"strategy": "grid_trading", "match_score": 0.71}]),
        expected_net_edge_bps: Some(12.5),
        portfolio_impact: json!({"new_notional_pct": 0.01}),
        thesis: Some("grid shadow proposal".to_string()),
        invalidation: Some("net edge turns negative".to_string()),
        fact_refs: vec![signal.signal_id.clone()],
        inference_refs: vec![],
        hypothesis_refs: vec![],
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
        p2_modifications: vec![GuardianP2Modification {
            field: "size".to_string(),
            action: "reduce".to_string(),
            original_value: Some(json!(1.25)),
            modified_value: json!(0.75),
            unit: Some("base_qty".to_string()),
            reason_code: "strategy_soft_risk".to_string(),
            reason: "soft risk size cap".to_string(),
            evidence_refs: vec![signal.signal_id.clone()],
            metadata: json!({}),
        }],
        metadata: json!({}),
    };
    let verdict_json = serde_json::to_value(&verdict).expect("guardian verdict json");
    assert_eq!(verdict_json["p2_modifications"][0]["field"], "size");
    let verdict_obj = SpineObjectEnvelope::from_guardian_verdict(&verdict, AgentSpineMode::Shadow)
        .expect("guardian verdict envelope");
    assert_eq!(verdict_obj.state, "modified");

    let plan = ExecutionPlan {
        schema_version: EXECUTION_PLAN_SCHEMA_VERSION.to_string(),
        order_plan_id: "plan-paper-BTCUSDT-789".to_string(),
        decision_id: decision.decision_id.clone(),
        verdict_id: verdict.verdict_id.clone(),
        verdict_version: verdict.verdict_version,
        ts_ms: 792,
        engine_mode: "paper".to_string(),
        symbol: "BTCUSDT".to_string(),
        strategy: "grid_trading".to_string(),
        direction: StrategySignalDirection::Long,
        symbol_source: ExecutionAuthoritySource::StrategistDecision,
        direction_source: ExecutionAuthoritySource::StrategistDecision,
        qty: 1.25,
        reduce_only: false,
        order_style: ExecutionOrderStyle::PostOnly,
        urgency: ExecutionUrgency::Normal,
        max_slippage_bps: Some(10.0),
        maker_preference: ExecutionMakerPreference::MakerOnly,
        order_type: "limit".to_string(),
        limit_price: Some(101.25),
        time_in_force: Some("PostOnly".to_string()),
        order_style_params: json!({}),
        local_stop_policy: json!({"mode": "guardian_required"}),
        anti_hunt_stop_policy: json!({"enabled": true}),
        lease_scope: Some("TRADE_ENTRY".to_string()),
        lease_ttl_ms: Some(30_000),
        lease_id: Some("lease-paper-BTCUSDT-789".to_string()),
        idempotency_key: "idem-paper-BTCUSDT-789".to_string(),
        metadata: json!({"writer": "mag032"}),
    };
    assert!(plan.symbol_direction_authority_is_delegated());
    assert!(plan.reduce_only_direction_is_consistent());
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
        verdict_version: 1,
        ts_ms: 903,
        engine_mode: "paper".to_string(),
        symbol: "ETHUSDT".to_string(),
        strategy: "grid_trading".to_string(),
        direction: StrategySignalDirection::Long,
        symbol_source: ExecutionAuthoritySource::StrategistDecision,
        direction_source: ExecutionAuthoritySource::StrategistDecision,
        qty: 0.5,
        reduce_only: false,
        order_style: ExecutionOrderStyle::PostOnly,
        urgency: ExecutionUrgency::Normal,
        max_slippage_bps: Some(12.5),
        maker_preference: ExecutionMakerPreference::MakerOnly,
        order_type: "limit".to_string(),
        limit_price: Some(2400.0),
        time_in_force: Some("PostOnly".to_string()),
        order_style_params: json!({}),
        local_stop_policy: json!({}),
        anti_hunt_stop_policy: json!({}),
        lease_scope: None,
        lease_ttl_ms: None,
        lease_id: None,
        idempotency_key: "idem-paper-ETHUSDT-900".to_string(),
        metadata: json!({}),
    };
    let key = ExecutionIdempotencyKey::reserved(&plan, 904);
    assert_eq!(key.idempotency_key, plan.idempotency_key);
    assert_eq!(key.order_plan_id, plan.order_plan_id);
    assert_eq!(key.decision_id, plan.decision_id);
    assert_eq!(key.engine_mode, plan.engine_mode);
    assert_eq!(key.first_seen_at_ms, 904);
    assert_eq!(key.status, "reserved");
    assert_eq!(key.details["verdict_id"], plan.verdict_id);
    assert_eq!(key.details["verdict_version"], plan.verdict_version);
    assert_eq!(key.details["symbol"], plan.symbol);
    assert_eq!(key.details["order_type"], plan.order_type);
    assert_eq!(key.details["order_style"], "post_only");

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

#[test]
fn shadow_spine_chain_is_complete_while_legacy_signal_msg_stays_unchanged() {
    let signal = strategy_signal_from_open_intent(
        "sig-live_demo-grid_trading-BTCUSDT-shadow",
        "ctx-live_demo-BTCUSDT-shadow",
        1_700_000_000_000,
        "live_demo",
        &sample_intent(true),
    );
    let legacy_before = serde_json::to_value(strategy_signal_to_trading_msg(&signal)).unwrap();

    let signal_obj = SpineObjectEnvelope::from_strategy_signal(&signal, AgentSpineMode::Shadow)
        .expect("strategy signal envelope");
    let decision = StrategistDecision {
        schema_version: STRATEGIST_DECISION_SCHEMA_VERSION.to_string(),
        decision_id: "decision-live_demo-BTCUSDT-shadow".to_string(),
        signal_id: signal.signal_id.clone(),
        ts_ms: signal.ts_ms + 1,
        engine_mode: signal.engine_mode.clone(),
        symbol: signal.symbol.clone(),
        strategy: signal.strategy.clone(),
        direction: signal.direction,
        confidence: signal.confidence,
        decision_action: "open".to_string(),
        selected_strategy: Some(signal.strategy.clone()),
        selected_candidate_id: Some(signal.signal_id.clone()),
        candidate_scores: json!([{"strategy": signal.strategy, "match_score": signal.confidence}]),
        expected_net_edge_bps: Some(8.0),
        portfolio_impact: json!({"mode": "shadow"}),
        thesis: Some("shadow integration regression".to_string()),
        invalidation: Some("Guardian rejection".to_string()),
        fact_refs: vec![signal.signal_id.clone()],
        inference_refs: vec![],
        hypothesis_refs: vec![],
        proposed_qty: Some(1.25),
        proposed_price: Some(101.25),
        rationale: Some("shadow integration regression".to_string()),
        evidence_refs: vec![signal.signal_id.clone()],
        metadata: json!({"mag": "035"}),
    };
    let decision_obj =
        SpineObjectEnvelope::from_strategist_decision(&decision, AgentSpineMode::Shadow)
            .expect("strategist decision envelope");
    let verdict = GuardianVerdict {
        schema_version: GUARDIAN_VERDICT_SCHEMA_VERSION.to_string(),
        verdict_id: "verdict-live_demo-BTCUSDT-shadow-v1".to_string(),
        decision_id: decision.decision_id.clone(),
        verdict_version: 1,
        ts_ms: signal.ts_ms + 2,
        engine_mode: signal.engine_mode.clone(),
        symbol: signal.symbol.clone(),
        strategy: signal.strategy.clone(),
        allow: true,
        risk_level: "low".to_string(),
        reasons: vec!["shadow_integration_only".to_string()],
        p2_modifications: vec![],
        metadata: json!({}),
    };
    let verdict_obj = SpineObjectEnvelope::from_guardian_verdict(&verdict, AgentSpineMode::Shadow)
        .expect("guardian verdict envelope");
    let plan = ExecutionPlan {
        schema_version: EXECUTION_PLAN_SCHEMA_VERSION.to_string(),
        order_plan_id: "plan-live_demo-BTCUSDT-shadow".to_string(),
        decision_id: decision.decision_id.clone(),
        verdict_id: verdict.verdict_id.clone(),
        verdict_version: verdict.verdict_version,
        ts_ms: signal.ts_ms + 3,
        engine_mode: signal.engine_mode.clone(),
        symbol: signal.symbol.clone(),
        strategy: signal.strategy.clone(),
        direction: signal.direction,
        symbol_source: ExecutionAuthoritySource::StrategistDecision,
        direction_source: ExecutionAuthoritySource::StrategistDecision,
        qty: 1.25,
        reduce_only: false,
        order_style: ExecutionOrderStyle::PostOnly,
        urgency: ExecutionUrgency::Normal,
        max_slippage_bps: Some(10.0),
        maker_preference: ExecutionMakerPreference::MakerOnly,
        order_type: "limit".to_string(),
        limit_price: Some(101.25),
        time_in_force: Some("PostOnly".to_string()),
        order_style_params: json!({}),
        local_stop_policy: json!({}),
        anti_hunt_stop_policy: json!({}),
        lease_scope: Some("TRADE_ENTRY".to_string()),
        lease_ttl_ms: Some(30_000),
        lease_id: Some("lease-live_demo-BTCUSDT-shadow".to_string()),
        idempotency_key: "idem-live_demo-BTCUSDT-shadow".to_string(),
        metadata: json!({"shadow_only": true}),
    };
    let plan_obj = SpineObjectEnvelope::from_execution_plan(&plan, AgentSpineMode::Shadow)
        .expect("execution plan envelope");
    let report = ExecutionReport {
        schema_version: EXECUTION_REPORT_SCHEMA_VERSION.to_string(),
        execution_report_id: "report-live_demo-BTCUSDT-shadow".to_string(),
        order_plan_id: plan.order_plan_id.clone(),
        decision_id: decision.decision_id.clone(),
        ts_ms: signal.ts_ms + 4,
        engine_mode: signal.engine_mode.clone(),
        symbol: signal.symbol.clone(),
        status: "shadow_planned".to_string(),
        exchange_order_id: None,
        fill_id: None,
        requested_qty: Some(1.25),
        filled_qty: Some(1.25),
        expected_price: Some(101.25),
        avg_fill_price: Some(101.35),
        slippage_bps: Some(9.876543),
        fees_paid: Some(0.031),
        fee_bps: Some(3.1),
        submit_latency_ms: Some(120.0),
        fill_latency_ms: Some(480.0),
        liquidity_role: "maker".to_string(),
        quality_metrics: json!({
            "metric_source": "executor_report_v2",
            "slippage_bps": 9.876543,
            "fees_paid": 0.031,
            "fill_latency_ms": 480.0
        }),
        metadata: json!({"no_order_submitted": true}),
    };
    let report_json = serde_json::to_value(&report).expect("execution report json");
    assert_eq!(report_json["slippage_bps"], 9.876543);
    assert_eq!(report_json["fees_paid"], 0.031);
    assert_eq!(report_json["fill_latency_ms"], 480.0);
    let report_obj = SpineObjectEnvelope::from_execution_report(&report, AgentSpineMode::Shadow)
        .expect("execution report envelope");

    let edges = [
        SpineEdge::new(
            signal.ts_ms + 5,
            signal_obj.object_id.clone(),
            decision_obj.object_id.clone(),
            DecisionEdgeType::SignalFor,
            signal.engine_mode.clone(),
            Some(decision.decision_id.clone()),
            json!({"contract": "signal_to_decision"}),
        ),
        SpineEdge::new(
            signal.ts_ms + 6,
            decision_obj.object_id.clone(),
            verdict_obj.object_id.clone(),
            DecisionEdgeType::ReviewedBy,
            signal.engine_mode.clone(),
            Some(decision.decision_id.clone()),
            json!({"contract": "decision_to_verdict"}),
        ),
        SpineEdge::new(
            signal.ts_ms + 7,
            verdict_obj.object_id.clone(),
            plan_obj.object_id.clone(),
            DecisionEdgeType::PlannedBy,
            signal.engine_mode.clone(),
            Some(decision.decision_id.clone()),
            json!({"contract": "verdict_to_plan"}),
        ),
        SpineEdge::new(
            signal.ts_ms + 8,
            plan_obj.object_id.clone(),
            report_obj.object_id.clone(),
            DecisionEdgeType::ExecutedBy,
            signal.engine_mode.clone(),
            Some(decision.decision_id.clone()),
            json!({"contract": "plan_to_report"}),
        ),
    ];
    let idempotency = ExecutionIdempotencyKey::reserved(&plan, signal.ts_ms + 9);
    let object_types = [
        signal_obj.object_type,
        decision_obj.object_type,
        verdict_obj.object_type,
        plan_obj.object_type,
        report_obj.object_type,
    ];

    assert_eq!(
        object_types,
        [
            DecisionObjectType::StrategySignal,
            DecisionObjectType::StrategistDecision,
            DecisionObjectType::GuardianVerdict,
            DecisionObjectType::ExecutionPlan,
            DecisionObjectType::ExecutionReport,
        ]
    );
    assert_eq!(
        edges.map(|edge| edge.edge_type.as_str()),
        ["signal_for", "reviewed_by", "planned_by", "executed_by"]
    );
    assert_eq!(signal_obj.state, "observed");
    assert_eq!(decision_obj.state, "proposed");
    assert_eq!(verdict_obj.state, "approved");
    assert_eq!(plan_obj.state, "planned");
    assert_eq!(report_obj.state, "shadow_planned");
    assert_eq!(
        plan_obj.lease_id.as_deref(),
        Some("lease-live_demo-BTCUSDT-shadow")
    );
    assert_eq!(idempotency.idempotency_key, plan.idempotency_key);
    assert_eq!(idempotency.order_plan_id, plan.order_plan_id);
    assert_eq!(idempotency.decision_id, decision.decision_id);

    let legacy_after = serde_json::to_value(strategy_signal_to_trading_msg(&signal)).unwrap();
    assert_eq!(legacy_after, legacy_before);
    assert_eq!(
        legacy_after["Signal"]["signal_id"],
        "sig-live_demo-grid_trading-BTCUSDT-shadow"
    );
    assert_eq!(legacy_after["Signal"]["signal_type"], "OpenLong");
    assert_eq!(legacy_after["Signal"]["strategy_name"], "grid_trading");
}
