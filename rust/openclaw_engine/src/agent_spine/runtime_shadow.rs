//! Runtime shadow lineage emission for approved open intents.
//!
//! W-C Caveat 1+2 fix（2026-05-11）：
//! - Caveat 1：emit_entry_lineage 末尾追加 5 條 SpineStateTransition（5 種 object
//!   生命週期 SM 的 build transition：strategy_signal/strategist_decision/
//!   guardian_verdict/execution_plan/execution_report，全部 from_state=None →
//!   to_state=<initial state>，trigger=runtime_<obj>_emit）。對應
//!   `agent.decision_state_changes` 從 0 row producer 升級為 active wiring。
//! - Caveat 2：新增 `emit_fill_completion_lineage` 函式，在交易所 fully_filled
//!   後寫一條新的 ExecutionReport row（filled_qty/liquidity_role/avg_fill_price
//!   全帶真值，狀態 `shadow_filled`），用 idempotency_key 區隔避免撞 stub row；
//!   同時 emit 2 條變更期 SpineStateTransition（execution_plan 與 execution_report
//!   皆 shadow_planned → shadow_executed/shadow_filled）。
//!   詳細設計參見 `docs/CCAgentWorkSpace/PA/2026-05-10--w_c_caveat_fix_plan.md`。

use super::config::AgentSpineMode;
use super::contracts::{
    ExecutionAuthoritySource, ExecutionMakerPreference, ExecutionOrderStyle, ExecutionPlan,
    ExecutionReport, ExecutionUrgency, GuardianVerdict, StrategistDecision,
    EXECUTION_PLAN_SCHEMA_VERSION, EXECUTION_REPORT_SCHEMA_VERSION,
    GUARDIAN_VERDICT_SCHEMA_VERSION, STRATEGIST_DECISION_SCHEMA_VERSION,
};
use super::events::{
    stable_id, DecisionEdgeType, DecisionObjectType, ExecutionIdempotencyKey, SpineEdge,
    SpineObjectEnvelope, SpineStateTransition,
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
    pub lease_id: Option<&'a str>,
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
        lease_id: input.lease_id.map(str::to_string),
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

    // ─────────────────────────────────────────────────────────────────────
    // W-C Caveat 1 修復：Stage A — 5 object 建立期 SpineStateTransition
    //
    // 5 種 Spine object 在本函式內由同一事件同步建立；建立完物件 + edges +
    // idempotency key 之後，追補 5 條 from_state=None → to_state=<initial> 的
    // state transition，讓 agent.decision_state_changes 從 0 row producer 升級
    // 為 active wiring（QA 2026-05-10 audit Caveat 1 修復點）。
    //
    // transition_id 由 SpineStateTransition::new 內部以
    // stable_id("transition", &[object_id, to_state, trigger, ts_ms]) 生成；
    // 即便 5 條 transition 共享同 ts_ms，仍因 object_id 與 trigger 不同而
    // 不會撞 PRIMARY KEY (transition_id, ts)。
    //
    // 注意：本批 transition 為「建立期」（from_state=None），對應 chk_object_type
    // CHECK 的 6 列舉，全部使用合法字串；engine_mode 沿用 input.engine_mode，
    // 已被本函式上方 matches!(input.engine_mode, "demo" | "live_demo") 過濾，
    // paper 模式不會走到此處（避免污染 spine 資料）。
    //
    // 由於上方 build_objects / edges / execution_key 已 consume decision_id /
    // order_plan_id / report 的 owned String，這裡用 plan/report.payload 內留下
    // 的 clone 重建 5 個 object_id 字串。
    // ─────────────────────────────────────────────────────────────────────
    let signal_id_for_transition = signal.signal_id.clone();
    let decision_id_for_transition = plan.decision_id.clone();
    let verdict_id_for_transition = plan.verdict_id.clone();
    let order_plan_id_for_transition = plan.order_plan_id.clone();
    let report_id_for_transition = report.execution_report_id.clone();

    let build_transitions: [(DecisionObjectType, String, &str, &str); 5] = [
        (
            DecisionObjectType::StrategySignal,
            signal_id_for_transition,
            "emitted",
            "runtime_signal_emit",
        ),
        (
            DecisionObjectType::StrategistDecision,
            decision_id_for_transition,
            "approved_open",
            "runtime_decision_emit",
        ),
        (
            DecisionObjectType::GuardianVerdict,
            verdict_id_for_transition,
            "approved",
            "runtime_verdict_emit",
        ),
        (
            DecisionObjectType::ExecutionPlan,
            order_plan_id_for_transition,
            "shadow_planned",
            "runtime_plan_emit",
        ),
        (
            DecisionObjectType::ExecutionReport,
            report_id_for_transition,
            "shadow_planned",
            "runtime_report_emit",
        ),
    ];
    for (object_type, object_id, to_state, trigger) in build_transitions {
        let transition = SpineStateTransition::new(
            input.ts_ms,
            object_id,
            object_type,
            None,
            to_state,
            input.engine_mode,
            trigger,
            json!({"shadow_lineage_only": true}),
        );
        accepted += usize::from(try_send(
            tx,
            AgentSpineMsg::StateTransition(transition),
            "state_transition",
        ));
    }

    accepted
}

/// W-C Caveat 2 修復：成交完成時補寫真實 ExecutionReport row 的輸入結構。
///
/// 由 event_consumer::loop_exchange 在 `fully_filled` 判定後構造，攜帶 fill
/// metadata（liquidity_role / filled_qty / avg_price / fees / slippage），用於
/// 新建一條獨立的 ExecutionReport（status=`shadow_filled`），與既有的 stub
/// `shadow_planned` row 並存（append-only event log 哲學）。
pub struct FillCompletionLineageInput<'a> {
    /// 對應原 stub plan 的 order_plan_id（必要，cross-ref 用）。
    pub order_plan_id: &'a str,
    /// 對應原 stub plan 的 decision_id（必要，spine envelope 必填）。
    pub decision_id: &'a str,
    /// 交易對。
    pub symbol: &'a str,
    /// engine_mode（必為 "demo" / "live_demo"，paper 一律 short-circuit 不寫）。
    pub engine_mode: &'a str,
    /// 策略名稱（emit 至 envelope metadata；當前 ExecutionReport struct 無
    /// strategy 欄，故藉 quality_metrics 帶出）。
    pub strategy: &'a str,
    /// 成交時刻（ms）— 用作 transition + envelope 的 ts_ms。
    pub ts_ms: u64,
    /// 已累積成交數量（po.cum_filled_qty，必 > 0；caller 已過 fully_filled 判定）。
    pub filled_qty: f64,
    /// 本次成交價格（exec_price）。
    pub avg_fill_price: f64,
    /// 已支付手續費（exec_fee）。
    pub fees_paid: f64,
    /// 手續費 bps（fee_rate × 10000，可選；棄缺時下游補算）。
    pub fee_bps: Option<f64>,
    /// 對抗 reference_price 的滑點 bps（taker 才有，maker 為 None）。
    pub slippage_bps: Option<f64>,
    /// 流動性角色（"maker" / "taker"，由 fill_helpers::fill_liquidity_role 給出）。
    pub liquidity_role: &'a str,
    /// 成交延遲（ms，exec_ts - sent_ts_ms）；可選。
    pub fill_latency_ms: Option<u64>,
    /// 交易所側 exec_id（與 trading.fills.exec_id 對齊用，下游 reviewer
    /// cross-join 證據鏈）。
    pub exchange_exec_id: &'a str,
    /// 對應原 stub `shadow_planned` row 的 execution_report_id（quality_metrics
    /// cross-ref，便於 reviewer 同 chain 回溯）。
    pub stub_report_id: &'a str,
    /// 對應原 dispatch order_link_id（可選，回填 exchange_order_id 欄）。
    pub order_link_id: Option<&'a str>,
}

/// W-C Caveat 2 修復：成交完成後寫一條真實 ExecutionReport row + 2 條變更期
/// SpineStateTransition + 1 條 ExecutedBy edge with `fill_completion=true`。
///
/// 與 [`emit_entry_lineage`] 共享 fail-soft 哲學：
/// - mode 未啟用 / tx None / engine_mode 非 demo/live_demo → 0 emit
/// - filled_qty <= 0 或非 finite → 0 emit
/// - serde 序列化失敗 → warn 但不 panic
/// - mpsc try_send 失敗 → warn drop，不阻塞 hot path
///
/// 新 row 的 idempotency_key 使用 `shadow_execution_report_filled:` 前綴
/// （區隔 stub 的 `shadow_execution_plan:` 前綴），避免 ON CONFLICT
/// DO NOTHING 撞舊 row。execution_report_id 由 stable_id seed
/// "shadow_filled" 後綴生成，與 stub 報告 id 互不相撞。
///
/// 回傳實際 accepted 訊息數（report object 1 + edge 1 + 2 transition = 期望 4，
/// 因為 channel 可能 full 時較少）。
pub fn emit_fill_completion_lineage(
    tx: Option<&mpsc::Sender<AgentSpineMsg>>,
    mode: AgentSpineMode,
    input: FillCompletionLineageInput<'_>,
) -> usize {
    if !mode.writes_enabled()
        || tx.is_none()
        || !matches!(input.engine_mode, "demo" | "live_demo")
        || !input.filled_qty.is_finite()
        || input.filled_qty <= 0.0
    {
        return 0;
    }
    let tx = tx.expect("checked Some above");

    // 注意：新 report_id 必須與 stub `shadow_planned` row 的 id 不同，避免被
    // V064 schema 的 `idx_agent_decision_objects_object_type_idempotency_key`
    // 唯一索引判定為重複；suffix `shadow_filled` 與 stub 的 `shadow_planned`
    // 對應，stable_id 自然產生不同 hash。
    let filled_report_id = stable_id(
        "report",
        &[
            input.engine_mode,
            input.order_plan_id,
            "shadow_filled",
        ],
    );

    let report = ExecutionReport {
        schema_version: EXECUTION_REPORT_SCHEMA_VERSION.to_string(),
        execution_report_id: filled_report_id.clone(),
        order_plan_id: input.order_plan_id.to_string(),
        decision_id: input.decision_id.to_string(),
        ts_ms: input.ts_ms,
        engine_mode: input.engine_mode.to_string(),
        symbol: input.symbol.to_string(),
        status: "shadow_filled".to_string(),
        exchange_order_id: input.order_link_id.map(str::to_string),
        fill_id: Some(input.exchange_exec_id.to_string()),
        requested_qty: None,
        filled_qty: Some(input.filled_qty),
        expected_price: None,
        avg_fill_price: Some(input.avg_fill_price),
        slippage_bps: input.slippage_bps,
        fees_paid: Some(input.fees_paid),
        fee_bps: input.fee_bps,
        submit_latency_ms: None,
        // ExecutionReport.fill_latency_ms 為 Option<f64>，u64 ms 轉 f64 安全。
        fill_latency_ms: input.fill_latency_ms.map(|ms| ms as f64),
        liquidity_role: input.liquidity_role.to_string(),
        quality_metrics: json!({
            "shadow_lineage_only": true,
            "fill_completion": true,
            "strategy": input.strategy,
            "stub_report_id": input.stub_report_id,
            "exchange_exec_id": input.exchange_exec_id,
        }),
        metadata: json!({
            "shadow_lineage_only": true,
            "no_order_authority": true,
            "fill_completion": true,
        }),
    };

    // 用 from_execution_report 包成 envelope；序列化失敗時 warn 但不 panic
    // （fail-soft，與既有 emit_entry_lineage 對齊）。
    let envelope = match SpineObjectEnvelope::from_execution_report(&report, mode) {
        Ok(env) => env,
        Err(err) => {
            warn!(
                error = %err,
                engine_mode = input.engine_mode,
                symbol = %input.symbol,
                "agent spine fill completion lineage serialization failed"
            );
            return 0;
        }
    };

    // 同 ts_ms 寫一條 ExecutedBy edge，details.fill_completion=true 區隔
    // stub plan→report edge。透過 details JSON 標記避免新增 DecisionEdgeType
    // enum（PA §2.2 Option α-A，0 migration cost）。
    let edge = SpineEdge::new(
        input.ts_ms,
        input.order_plan_id.to_string(),
        filled_report_id.clone(),
        DecisionEdgeType::ExecutedBy,
        input.engine_mode,
        Some(input.decision_id.to_string()),
        json!({
            "contract": "runtime_plan_to_filled_report",
            "shadow_lineage_only": true,
            "fill_completion": true,
        }),
    );

    let mut accepted = 0;
    accepted += usize::from(try_send(tx, AgentSpineMsg::Object(envelope), "object"));
    accepted += usize::from(try_send(tx, AgentSpineMsg::Edge(edge), "edge"));

    // Stage B（PA §1.3）— 變更期 transitions：execution_plan + execution_report
    // 從 shadow_planned 升至 shadow_executed / shadow_filled，trigger 統一
    // `runtime_fill_confirmed`。注意 partial fill 不在此寫（caller 必先過
    // `fully_filled` 判定）。
    let plan_transition = SpineStateTransition::new(
        input.ts_ms,
        input.order_plan_id.to_string(),
        DecisionObjectType::ExecutionPlan,
        Some("shadow_planned".to_string()),
        "shadow_executed",
        input.engine_mode,
        "runtime_fill_confirmed",
        json!({
            "shadow_lineage_only": true,
            "fill_completion": true,
            "exchange_exec_id": input.exchange_exec_id,
        }),
    );
    accepted += usize::from(try_send(
        tx,
        AgentSpineMsg::StateTransition(plan_transition),
        "state_transition",
    ));

    // execution_report 的 transition 對 stub_report_id 寫（既有 stub row 真的從
    // shadow_planned 轉到 shadow_filled），不是新建的 filled_report_id；新 filled
    // ExecutionReport row 由 ExecutedBy edge（line 519-528）連回 stub 與 plan，
    // 符合 append-only event log 哲學：transition 描述「既有 object 狀態變化」，
    // 不在「新建 object 自身」上掛 from_state（新建 row 沒有 prior state）。
    // (Round 2 E2 C-A.2 修復：原 object_id=filled_report_id 語意不對齊。)
    let report_transition = SpineStateTransition::new(
        input.ts_ms,
        input.stub_report_id.to_string(),
        DecisionObjectType::ExecutionReport,
        Some("shadow_planned".to_string()),
        "shadow_filled",
        input.engine_mode,
        "runtime_fill_confirmed",
        json!({
            "shadow_lineage_only": true,
            "fill_completion": true,
            "filled_report_id": filled_report_id,
        }),
    );
    accepted += usize::from(try_send(
        tx,
        AgentSpineMsg::StateTransition(report_transition),
        "state_transition",
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
