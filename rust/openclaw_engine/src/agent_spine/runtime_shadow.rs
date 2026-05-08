//! Runtime shadow lineage emission for approved open intents.

use super::config::AgentSpineMode;
use super::contracts::{
    ExecutionAuthoritySource, ExecutionMakerPreference, ExecutionOrderStyle, ExecutionPlan,
    ExecutionReport, ExecutionUrgency, GuardianVerdict, StrategistDecision,
    EXECUTION_PLAN_SCHEMA_VERSION, EXECUTION_REPORT_SCHEMA_VERSION,
    GUARDIAN_VERDICT_SCHEMA_VERSION, STRATEGIST_DECISION_SCHEMA_VERSION,
};
use super::events::{
    stable_id, DecisionEdgeType, ExecutionIdempotencyKey, SpineEdge, SpineObjectEnvelope,
};
use super::signal_adapter::strategy_signal_from_open_intent;
use super::store::AgentSpineMsg;
use crate::intent_processor::{OrderIntent, VerdictInfo};
use crate::order_manager::TimeInForce;
use serde_json::json;
use tokio::sync::mpsc;
use tracing::warn;

pub struct RuntimeShadowLineageInput<'a> {
    pub signal_id: &'a str,
    pub context_id: &'a str,
    pub intent_id: &'a str,
    pub verdict_id: &'a str,
    pub ts_ms: u64,
    pub engine_mode: &'a str,
    pub intent: &'a OrderIntent,
    pub approved_qty: f64,
    pub reference_price: f64,
    pub verdict_info: Option<&'a VerdictInfo>,
    pub order_link_id: Option<&'a str>,
}

pub fn emit_entry_lineage(
    tx: Option<&mpsc::Sender<AgentSpineMsg>>,
    mode: AgentSpineMode,
    input: RuntimeShadowLineageInput<'_>,
) -> usize {
    if !mode.writes_enabled()
        || tx.is_none()
        || !matches!(input.engine_mode, "demo" | "live_demo")
        || !input.approved_qty.is_finite()
        || input.approved_qty <= 0.0
    {
        return 0;
    }
    let tx = tx.expect("checked Some above");

    let signal = strategy_signal_from_open_intent(
        input.signal_id,
        input.context_id,
        input.ts_ms,
        input.engine_mode,
        input.intent,
    );
    let decision_id = stable_id("decision", &[input.engine_mode, input.signal_id]);
    let order_plan_id = stable_id(
        "plan",
        &[input.engine_mode, decision_id.as_str(), input.verdict_id],
    );
    let report_id = stable_id(
        "report",
        &[input.engine_mode, order_plan_id.as_str(), "shadow_planned"],
    );
    let proposed_price = finite_positive(input.intent.limit_price)
        .or_else(|| finite_positive(Some(input.reference_price)));
    let risk_level = input
        .verdict_info
        .and_then(|vi| risk_score_level(vi.risk_score))
        .unwrap_or("unknown")
        .to_string();
    let reasons = input
        .verdict_info
        .map(|vi| vi.reasons.clone())
        .unwrap_or_else(|| vec!["approved_without_verdict_info".to_string()]);
    let risk_score = input.verdict_info.map(|vi| vi.risk_score);
    let modified_qty = input.verdict_info.and_then(|vi| vi.modified_qty);

    let decision = StrategistDecision {
        schema_version: STRATEGIST_DECISION_SCHEMA_VERSION.to_string(),
        decision_id: decision_id.clone(),
        signal_id: signal.signal_id.clone(),
        ts_ms: input.ts_ms,
        engine_mode: input.engine_mode.to_string(),
        symbol: input.intent.symbol.clone(),
        strategy: input.intent.strategy.clone(),
        direction: signal.direction,
        confidence: input.intent.confidence,
        decision_action: "open".to_string(),
        selected_strategy: Some(input.intent.strategy.clone()),
        selected_candidate_id: Some(signal.signal_id.clone()),
        candidate_scores: json!({
            "strategy": input.intent.strategy,
            "confidence": input.intent.confidence,
        }),
        expected_net_edge_bps: None,
        portfolio_impact: json!({}),
        thesis: Some("runtime shadow lineage for approved legacy intent".to_string()),
        invalidation: None,
        fact_refs: vec![input.context_id.to_string()],
        inference_refs: vec![],
        hypothesis_refs: vec![],
        proposed_qty: Some(input.approved_qty),
        proposed_price,
        rationale: Some(
            "mirrors existing approved runtime intent; no trading authority".to_string(),
        ),
        evidence_refs: vec![signal.signal_id.clone(), input.context_id.to_string()],
        metadata: json!({
            "shadow_lineage_only": true,
            "no_order_authority": true,
            "legacy_intent_id": input.intent_id,
            "legacy_context_id": input.context_id,
        }),
    };

    let verdict = GuardianVerdict {
        schema_version: GUARDIAN_VERDICT_SCHEMA_VERSION.to_string(),
        verdict_id: input.verdict_id.to_string(),
        decision_id: decision_id.clone(),
        verdict_version: 1,
        ts_ms: input.ts_ms,
        engine_mode: input.engine_mode.to_string(),
        symbol: input.intent.symbol.clone(),
        strategy: input.intent.strategy.clone(),
        allow: true,
        risk_level,
        reasons,
        p2_modifications: vec![],
        metadata: json!({
            "shadow_lineage_only": true,
            "legacy_intent_id": input.intent_id,
            "risk_score": risk_score,
            "modified_qty": modified_qty,
        }),
    };

    let plan = ExecutionPlan {
        schema_version: EXECUTION_PLAN_SCHEMA_VERSION.to_string(),
        order_plan_id: order_plan_id.clone(),
        decision_id: decision_id.clone(),
        verdict_id: verdict.verdict_id.clone(),
        verdict_version: verdict.verdict_version,
        ts_ms: input.ts_ms,
        engine_mode: input.engine_mode.to_string(),
        symbol: input.intent.symbol.clone(),
        strategy: input.intent.strategy.clone(),
        direction: signal.direction,
        symbol_source: ExecutionAuthoritySource::StrategistDecision,
        direction_source: ExecutionAuthoritySource::StrategistDecision,
        qty: input.approved_qty,
        reduce_only: false,
        order_style: order_style(input.intent),
        urgency: ExecutionUrgency::Normal,
        max_slippage_bps: None,
        maker_preference: maker_preference(input.intent),
        order_type: input.intent.order_type.clone(),
        limit_price: input.intent.limit_price,
        time_in_force: input
            .intent
            .time_in_force
            .map(|tif| tif.as_str().to_string()),
        order_style_params: json!({}),
        local_stop_policy: json!({}),
        anti_hunt_stop_policy: json!({}),
        lease_scope: Some("TRADE_ENTRY".to_string()),
        lease_ttl_ms: Some(30_000),
        lease_id: None,
        idempotency_key: format!(
            "shadow_execution_plan:{}:{}",
            input.engine_mode, order_plan_id
        ),
        metadata: json!({
            "shadow_lineage_only": true,
            "no_order_authority": true,
            "legacy_intent_id": input.intent_id,
            "dispatch_order_link_id": input.order_link_id,
        }),
    };

    let report = ExecutionReport {
        schema_version: EXECUTION_REPORT_SCHEMA_VERSION.to_string(),
        execution_report_id: report_id,
        order_plan_id: order_plan_id.clone(),
        decision_id: decision_id.clone(),
        ts_ms: input.ts_ms,
        engine_mode: input.engine_mode.to_string(),
        symbol: input.intent.symbol.clone(),
        status: "shadow_planned".to_string(),
        exchange_order_id: input.order_link_id.map(str::to_string),
        fill_id: None,
        requested_qty: Some(input.approved_qty),
        filled_qty: Some(0.0),
        expected_price: proposed_price,
        avg_fill_price: None,
        slippage_bps: None,
        fees_paid: None,
        fee_bps: None,
        submit_latency_ms: None,
        fill_latency_ms: None,
        liquidity_role: "unknown".to_string(),
        quality_metrics: json!({
            "shadow_lineage_only": true,
            "planned_not_executed_by_spine": true,
        }),
        metadata: json!({
            "shadow_lineage_only": true,
            "no_order_authority": true,
            "legacy_intent_id": input.intent_id,
        }),
    };

    let objects = match build_objects(&signal, &decision, &verdict, &plan, &report, mode) {
        Ok(objects) => objects,
        Err(err) => {
            warn!(
                error = %err,
                engine_mode = input.engine_mode,
                symbol = %input.intent.symbol,
                "agent spine runtime shadow lineage serialization failed"
            );
            return 0;
        }
    };
    let edges = vec![
        SpineEdge::new(
            input.ts_ms,
            signal.signal_id.clone(),
            decision_id.clone(),
            DecisionEdgeType::SignalFor,
            input.engine_mode,
            Some(decision_id.clone()),
            json!({"contract": "runtime_signal_to_decision", "shadow_lineage_only": true}),
        ),
        SpineEdge::new(
            input.ts_ms,
            decision_id.clone(),
            verdict.verdict_id.clone(),
            DecisionEdgeType::ReviewedBy,
            input.engine_mode,
            Some(decision_id.clone()),
            json!({"contract": "runtime_decision_to_verdict", "shadow_lineage_only": true}),
        ),
        SpineEdge::new(
            input.ts_ms,
            verdict.verdict_id.clone(),
            order_plan_id.clone(),
            DecisionEdgeType::PlannedBy,
            input.engine_mode,
            Some(decision_id.clone()),
            json!({"contract": "runtime_verdict_to_plan", "shadow_lineage_only": true}),
        ),
        SpineEdge::new(
            input.ts_ms,
            order_plan_id,
            report.execution_report_id.clone(),
            DecisionEdgeType::ExecutedBy,
            input.engine_mode,
            Some(decision_id),
            json!({"contract": "runtime_plan_to_shadow_report", "shadow_lineage_only": true}),
        ),
    ];
    let execution_key = ExecutionIdempotencyKey::reserved(&plan, input.ts_ms);

    let mut accepted = 0;
    for object in objects {
        accepted += usize::from(try_send(tx, AgentSpineMsg::Object(object), "object"));
    }
    for edge in edges {
        accepted += usize::from(try_send(tx, AgentSpineMsg::Edge(edge), "edge"));
    }
    accepted += usize::from(try_send(
        tx,
        AgentSpineMsg::ExecutionIdempotencyKey(execution_key),
        "execution_idempotency_key",
    ));
    accepted
}

fn build_objects(
    signal: &super::contracts::StrategySignal,
    decision: &StrategistDecision,
    verdict: &GuardianVerdict,
    plan: &ExecutionPlan,
    report: &ExecutionReport,
    mode: AgentSpineMode,
) -> serde_json::Result<Vec<SpineObjectEnvelope>> {
    Ok(vec![
        SpineObjectEnvelope::from_strategy_signal(signal, mode)?,
        SpineObjectEnvelope::from_strategist_decision(decision, mode)?,
        SpineObjectEnvelope::from_guardian_verdict(verdict, mode)?,
        SpineObjectEnvelope::from_execution_plan(plan, mode)?,
        SpineObjectEnvelope::from_execution_report(report, mode)?,
    ])
}

fn try_send(tx: &mpsc::Sender<AgentSpineMsg>, msg: AgentSpineMsg, msg_type: &str) -> bool {
    match tx.try_send(msg) {
        Ok(()) => true,
        Err(mpsc::error::TrySendError::Full(_)) => {
            warn!(
                msg_type = msg_type,
                "agent spine runtime shadow channel full; dropping lineage msg"
            );
            false
        }
        Err(mpsc::error::TrySendError::Closed(_)) => {
            warn!(
                msg_type = msg_type,
                "agent spine runtime shadow channel closed; dropping lineage msg"
            );
            false
        }
    }
}

fn finite_positive(value: Option<f64>) -> Option<f64> {
    value.filter(|v| v.is_finite() && *v > 0.0)
}

fn order_style(intent: &OrderIntent) -> ExecutionOrderStyle {
    if matches!(intent.time_in_force, Some(TimeInForce::PostOnly)) {
        ExecutionOrderStyle::PostOnly
    } else if intent.order_type.eq_ignore_ascii_case("limit") {
        ExecutionOrderStyle::Limit
    } else {
        ExecutionOrderStyle::Market
    }
}

fn maker_preference(intent: &OrderIntent) -> ExecutionMakerPreference {
    if matches!(intent.time_in_force, Some(TimeInForce::PostOnly)) {
        ExecutionMakerPreference::MakerOnly
    } else if intent.order_type.eq_ignore_ascii_case("limit") {
        ExecutionMakerPreference::PreferMaker
    } else {
        ExecutionMakerPreference::AllowTaker
    }
}

fn risk_score_level(score: f64) -> Option<&'static str> {
    if !score.is_finite() {
        None
    } else if score >= 0.80 {
        Some("risk_score_high")
    } else if score >= 0.50 {
        Some("risk_score_medium")
    } else {
        Some("risk_score_low")
    }
}
