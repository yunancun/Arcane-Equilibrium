from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.bounded_probe_active_order_wiring_contract import (
    ACTIVE_ORDER_WIRING_CONTRACT_SCHEMA_VERSION,
    PATCH_REQUIRED_STATUS,
    READY_STATUS,
    build_bounded_probe_active_order_wiring_contract,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 24, 22, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _candidate() -> dict[str, object]:
    return {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 240,
    }


def _write_ready_active_order_repo(repo: Path, *, writer_no_order: bool = False) -> None:
    _write(
        repo / "rust/openclaw_engine/src/bounded_probe_active_order.rs",
        """
pub struct ActiveBoundedProbeOrderRequest {
    pub side_cell_key: String,
    pub context_id: String,
    pub signal_id: String,
    pub max_demo_notional_usdt_per_order: f64,
    pub max_probe_intents_before_review: u64,
    pub order_link_id: String,
    pub order_id: Option<String>,
    pub fill_id: Option<String>,
    pub fee: f64,
    pub slippage_bps: Option<f64>,
    pub matched_blocked_control: Option<String>,
}

pub enum ActiveBoundedProbeOrderDecision { Submit, Skip }

pub fn candidate_matched_bounded_probe_order(
    req: ActiveBoundedProbeOrderRequest,
) -> ActiveBoundedProbeOrderDecision {
    let bounded_probe_attempt = req.side_cell_key.clone();
    let demo_only = true;
    let live_demo = demo_only;
    let one_order_per_admitted_attempt = req.max_probe_intents_before_review == 1;
    let _placement = post_only_near_touch_or_skip();
    let _ = TimeInForce::PostOnly;
    let _ = OrderType::Limit;
    let limit_price = 1.0;
    let max_fresh_bbo_age_ms = DEFAULT_MAX_FRESH_BBO_AGE_MS;
    let max_initial_passive_gap_bps = DEFAULT_MAX_INITIAL_PASSIVE_GAP_BPS;
    let admission = evaluate_probe_admission();
    let allowed_to_submit_order = admission.allowed_to_submit_order;
    let order_authority = ORDER_AUTHORITY_GRANTED;
    let risk_state = current_risk_state();
    validate_operator_authorization();
    let decision_lease = DecisionLease {};
    let main_cost_gate_adjustment = "NONE";
    let order_id = req.order_id.clone();
    let fill_id = req.fill_id.clone();
    let fee = req.fee;
    let slippage_bps = req.slippage_bps;
    let matched_blocked_control = req.matched_blocked_control.clone();
    let _ = (
        bounded_probe_attempt,
        live_demo,
        one_order_per_admitted_attempt,
        limit_price,
        max_fresh_bbo_age_ms,
        max_initial_passive_gap_bps,
        allowed_to_submit_order,
        order_authority,
        risk_state,
        decision_lease,
        main_cost_gate_adjustment,
        order_id,
        fill_id,
        fee,
        slippage_bps,
        matched_blocked_control,
    );
    ActiveBoundedProbeOrderDecision::Submit
}
""",
    )
    _write(
        repo / "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        """
pub const DEFAULT_MAX_FRESH_BBO_AGE_MS: u64 = 1000;
pub const DEFAULT_MAX_INITIAL_PASSIVE_GAP_BPS: f64 = 75.0;
pub fn post_only_near_touch_or_skip() {}
""",
    )
    _write(
        repo / "rust/openclaw_engine/src/demo_learning_lane.rs",
        """
pub const ORDER_AUTHORITY_GRANTED: &str = "DEMO_LEARNING_PROBE_GRANTED";
pub fn evaluate_probe_admission() {
    let allowed_to_submit_order = false;
    let risk_state = RiskStateNotNormal;
    validate_operator_authorization();
    let main_cost_gate_adjustment = "NONE";
    let learning_probe_admission_is_demo_only = true;
    let live_demo = learning_probe_admission_is_demo_only;
    let max_probe_orders = 1;
    let _ = (
        allowed_to_submit_order,
        risk_state,
        main_cost_gate_adjustment,
        live_demo,
        max_probe_orders,
    );
}
""",
    )
    writer_contract = "This writer does not submit orders." if writer_no_order else ""
    _write(
        repo / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        f"""
//! {writer_contract}
const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str = "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn active_bounded_probe_order_submission() {{
    let bounded_probe_adapter_enabled = true;
    submit_candidate_matched_bounded_probe_order();
    evaluate_probe_admission(
        &plan,
        event,
        &ledger_rows,
        now_ms,
        &AdmissionConfig::default(),
        bounded_probe_adapter_enabled,
        risk_state,
    );
}}
""",
    )
    _write(
        repo / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
pub fn dispatch_admitted_bounded_probe_order() {
    active_bounded_probe_order_submission();
    let _order = candidate_matched_bounded_probe_order();
    let _ = tx.send(OrderDispatchRequest {
        order_link_id,
        context_id,
        signal_id,
    });
    let _ = LeaseOutcome::Consumed;
    let order_id = order_link_id.clone();
    let fill_id = make_fill_id();
    let fee = exec_fee;
    let slippage_bps = Some(0.0);
    let matched_blocked_control = load_matched_blocked_control();
    let _ = (order_id, fill_id, fee, slippage_bps, matched_blocked_control);
}
""",
    )
    _write(
        repo / "rust/openclaw_engine/src/order_manager.rs",
        """
pub enum TimeInForce { PostOnly }
pub enum OrderType { Limit }
pub struct OrderInfo { pub order_id: String, pub order_link_id: String }
pub struct ExecutionInfo { pub fill_id: String, pub exec_fee: f64, pub fee: f64, pub slippage_bps: Option<f64> }
""",
    )


def test_current_repo_blocks_active_order_wiring_contract() -> None:
    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=Path.cwd(),
        candidate=_candidate(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == ACTIVE_ORDER_WIRING_CONTRACT_SCHEMA_VERSION
    assert packet["status"] == PATCH_REQUIRED_STATUS
    assert packet["answers"]["source_contract_ready_for_e3_bb_review"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert (
        "bounded_probe_active_order_module_missing"
        in packet["source_contract"]["missing_requirements"]
    )
    assert "source_only_rust_patch_for_active_order_wiring" in markdown


def test_missing_repo_fails_closed(tmp_path: Path) -> None:
    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path / "missing",
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == PATCH_REQUIRED_STATUS
    assert packet["source_contract"]["all_requirements_present"] is False
    assert packet["answers"]["active_runtime_order_authority"] is False
    assert any(
        row["missing_paths"] for row in packet["source_contract"]["requirements"]
    )


def test_future_complete_source_contract_only_reaches_e3_bb_review_ready(
    tmp_path: Path,
) -> None:
    _write_ready_active_order_repo(tmp_path)

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == READY_STATUS
    assert packet["answers"]["source_contract_ready_for_e3_bb_review"] is True
    assert packet["answers"]["active_order_submission_ready"] is True
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["active_runtime_order_authority"] is False
    assert packet["max_safe_next_action"] == "e3_bb_exchange_facing_review_packet_only_no_order"


def test_marker_strings_do_not_satisfy_active_order_contract(tmp_path: Path) -> None:
    for rel_path in (
        "rust/openclaw_engine/src/bounded_probe_active_order.rs",
        "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        "rust/openclaw_engine/src/demo_learning_lane.rs",
        "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        "rust/openclaw_engine/src/order_manager.rs",
    ):
        _write(
            tmp_path / rel_path,
            """
// ActiveBoundedProbeOrderRequest ActiveBoundedProbeOrderDecision
pub fn marker_only() {
    let _ = "candidate_matched_bounded_probe_order";
    let _ = "bounded_probe_attempt";
    let _ = "side_cell_key";
    let _ = "demo_only live_demo one_order_per_admitted_attempt";
    let _ = "post_only_near_touch_or_skip TimeInForce::PostOnly OrderType::Limit";
    let _ = "limit_price max_fresh_bbo_age_ms max_initial_passive_gap_bps";
    let _ = "evaluate_probe_admission allowed_to_submit_order ORDER_AUTHORITY_GRANTED";
    let _ = "risk_state validate_operator_authorization Decision Lease main_cost_gate_adjustment";
    let _ = "dispatch_admitted_bounded_probe_order active_bounded_probe_order_submission";
    let _ = "OrderDispatchRequest tx.send order_link_id context_id signal_id";
    let _ = "order_id fill_id fee slippage_bps matched_blocked_control";
}
""",
        )

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == PATCH_REQUIRED_STATUS
    assert packet["source_contract"]["all_requirements_present"] is False
    assert packet["answers"]["source_contract_ready_for_e3_bb_review"] is False


def test_marker_strings_with_comment_tokens_do_not_satisfy_contract(
    tmp_path: Path,
) -> None:
    for rel_path in (
        "rust/openclaw_engine/src/bounded_probe_active_order.rs",
        "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        "rust/openclaw_engine/src/demo_learning_lane.rs",
        "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        "rust/openclaw_engine/src/order_manager.rs",
    ):
        _write(
            tmp_path / rel_path,
            """
pub fn marker_only() {
    let _ = "ActiveBoundedProbeOrderRequest //";
    let _ = "ActiveBoundedProbeOrderDecision //";
    let _ = "candidate_matched_bounded_probe_order //";
    let _ = "bounded_probe_attempt //";
    let _ = "side_cell_key //";
    let _ = "demo_only live_demo one_order_per_admitted_attempt //";
    let _ = "post_only_near_touch_or_skip TimeInForce::PostOnly OrderType::Limit //";
    let _ = "limit_price max_fresh_bbo_age_ms max_initial_passive_gap_bps //";
    let _ = "evaluate_probe_admission allowed_to_submit_order ORDER_AUTHORITY_GRANTED //";
    let _ = "risk_state validate_operator_authorization Decision Lease main_cost_gate_adjustment //";
    let _ = "dispatch_admitted_bounded_probe_order active_bounded_probe_order_submission //";
    let _ = "OrderDispatchRequest tx.send order_link_id context_id signal_id //";
    let _ = "order_id fill_id fee slippage_bps matched_blocked_control //";
    let _ = "submit_candidate_matched_bounded_probe_order bounded_probe_adapter_enabled //";
}
""",
        )

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == PATCH_REQUIRED_STATUS
    assert packet["source_contract"]["all_requirements_present"] is False
    assert packet["answers"]["active_order_submission_ready"] is False


def test_raw_marker_strings_do_not_satisfy_active_order_contract(
    tmp_path: Path,
) -> None:
    for rel_path in (
        "rust/openclaw_engine/src/bounded_probe_active_order.rs",
        "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        "rust/openclaw_engine/src/demo_learning_lane.rs",
        "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        "rust/openclaw_engine/src/order_manager.rs",
    ):
        _write(
            tmp_path / rel_path,
            """
pub fn marker_only() {
    let _ = r#"ActiveBoundedProbeOrderRequest " candidate_matched_bounded_probe_order //"#;
    let _ = r##"ActiveBoundedProbeOrderDecision bounded_probe_attempt side_cell_key //"##;
    let _ = r#"demo_only live_demo one_order_per_admitted_attempt //"#;
    let _ = r#"post_only_near_touch_or_skip TimeInForce::PostOnly OrderType::Limit //"#;
    let _ = r#"limit_price max_fresh_bbo_age_ms max_initial_passive_gap_bps //"#;
    let _ = r#"evaluate_probe_admission allowed_to_submit_order ORDER_AUTHORITY_GRANTED //"#;
    let _ = r#"risk_state validate_operator_authorization Decision Lease main_cost_gate_adjustment //"#;
    let _ = r#"dispatch_admitted_bounded_probe_order active_bounded_probe_order_submission //"#;
    let _ = r#"OrderDispatchRequest tx.send order_link_id context_id signal_id //"#;
    let _ = r#"order_id fill_id fee slippage_bps matched_blocked_control //"#;
    let _ = r#"submit_candidate_matched_bounded_probe_order bounded_probe_adapter_enabled //"#;
}
""",
        )

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == PATCH_REQUIRED_STATUS
    assert packet["source_contract"]["all_requirements_present"] is False
    assert packet["answers"]["active_order_submission_ready"] is False


def test_multiline_marker_strings_do_not_satisfy_active_order_contract(
    tmp_path: Path,
) -> None:
    for rel_path in (
        "rust/openclaw_engine/src/bounded_probe_active_order.rs",
        "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        "rust/openclaw_engine/src/demo_learning_lane.rs",
        "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        "rust/openclaw_engine/src/order_manager.rs",
    ):
        _write(
            tmp_path / rel_path,
            """
pub fn marker_only() {
    let _ = "
ActiveBoundedProbeOrderRequest
ActiveBoundedProbeOrderDecision
candidate_matched_bounded_probe_order
bounded_probe_attempt
side_cell_key
demo_only
live_demo
one_order_per_admitted_attempt
post_only_near_touch_or_skip
TimeInForce::PostOnly
OrderType::Limit
limit_price
max_fresh_bbo_age_ms
max_initial_passive_gap_bps
evaluate_probe_admission
allowed_to_submit_order
ORDER_AUTHORITY_GRANTED
risk_state
validate_operator_authorization
Decision Lease
main_cost_gate_adjustment
dispatch_admitted_bounded_probe_order
active_bounded_probe_order_submission
OrderDispatchRequest
tx.send
order_link_id
context_id
signal_id
order_id
fill_id
fee
slippage_bps
matched_blocked_control
submit_candidate_matched_bounded_probe_order
bounded_probe_adapter_enabled
";
}
""",
        )

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == PATCH_REQUIRED_STATUS
    assert packet["source_contract"]["all_requirements_present"] is False
    assert packet["answers"]["active_order_submission_ready"] is False


def test_macro_marker_tokens_do_not_satisfy_active_order_contract(
    tmp_path: Path,
) -> None:
    for rel_path in (
        "rust/openclaw_engine/src/bounded_probe_active_order.rs",
        "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        "rust/openclaw_engine/src/demo_learning_lane.rs",
        "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        "rust/openclaw_engine/src/order_manager.rs",
    ):
        _write(
            tmp_path / rel_path,
            """
pub fn marker_only() {
    stringify!(
        ActiveBoundedProbeOrderRequest
        ActiveBoundedProbeOrderDecision
        candidate_matched_bounded_probe_order
        bounded_probe_attempt
        side_cell_key
        demo_only
        live_demo
        one_order_per_admitted_attempt
        post_only_near_touch_or_skip
        TimeInForce::PostOnly
        OrderType::Limit
        limit_price
        max_fresh_bbo_age_ms
        max_initial_passive_gap_bps
        evaluate_probe_admission
        allowed_to_submit_order
        ORDER_AUTHORITY_GRANTED
        risk_state
        validate_operator_authorization
        Decision Lease
        main_cost_gate_adjustment
        dispatch_admitted_bounded_probe_order
        active_bounded_probe_order_submission
        OrderDispatchRequest
        tx.send
        order_link_id
        context_id
        signal_id
        order_id
        fill_id
        fee
        slippage_bps
        matched_blocked_control
        submit_candidate_matched_bounded_probe_order
        bounded_probe_adapter_enabled
    );
}
""",
        )

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == PATCH_REQUIRED_STATUS
    assert packet["source_contract"]["all_requirements_present"] is False
    assert packet["answers"]["active_order_submission_ready"] is False


def test_legacy_no_order_contract_still_blocks_active_order_readiness(
    tmp_path: Path,
) -> None:
    _write_ready_active_order_repo(tmp_path, writer_no_order=True)

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == PATCH_REQUIRED_STATUS
    assert packet["source_contract"]["all_requirements_present"] is True
    assert packet["answers"]["active_order_submission_ready"] is False
    assert "demo_learning_lane_writer_contract_no_order_submission" in packet[
        "active_order_submission_readiness"
    ]["blockers"]
    assert packet["answers"]["order_authority_granted"] is False


def test_authority_bearing_input_is_rejected(tmp_path: Path) -> None:
    _write_ready_active_order_repo(tmp_path)

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        authority_readiness_packet={
            "schema_version": "fixture",
            "answers": {"order_authority_granted": True},
        },
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["authority_readiness_packet"]["authority_violation"] == (
        "order_authority_granted"
    )
    assert packet["max_safe_next_action"] == (
        "remove_authority_bearing_input_before_any_next_review"
    )
    assert packet["answers"]["source_contract_ready_for_e3_bb_review"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_string_authority_grant_input_is_rejected(tmp_path: Path) -> None:
    _write_ready_active_order_repo(tmp_path)

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        authority_readiness_packet={
            "schema_version": "fixture",
            "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
        },
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["authority_readiness_packet"]["authority_violation"] == "order_authority"
    assert packet["max_safe_next_action"] == (
        "remove_authority_bearing_input_before_any_next_review"
    )
    assert packet["answers"]["order_authority_granted"] is False


def test_grant_like_string_authority_grant_input_is_rejected(tmp_path: Path) -> None:
    _write_ready_active_order_repo(tmp_path)

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        authority_readiness_packet={
            "schema_version": "fixture",
            "answers": {"order_authority_granted": "DEMO_LEARNING_PROBE_GRANTED"},
        },
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["authority_readiness_packet"]["authority_violation"] == (
        "order_authority_granted"
    )
    assert packet["answers"]["order_authority_granted"] is False


def test_truthy_authority_alias_input_is_rejected(tmp_path: Path) -> None:
    _write_ready_active_order_repo(tmp_path)

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        authority_readiness_packet={
            "schema_version": "fixture",
            "runtime_env_mutation_performed": "true",
        },
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["authority_readiness_packet"]["authority_violation"] == (
        "runtime_env_mutation_performed"
    )
    assert packet["answers"]["source_contract_ready_for_e3_bb_review"] is False


def test_adjacent_authority_alias_input_is_rejected(tmp_path: Path) -> None:
    _write_ready_active_order_repo(tmp_path)

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        authority_readiness_packet={
            "schema_version": "fixture",
            "answers": {
                "pg_query_performed": True,
                "private_endpoint_called": "yes",
            },
        },
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["authority_readiness_packet"]["authority_violation"] in {
        "pg_query_performed",
        "private_endpoint_called",
    }
    assert packet["answers"]["source_contract_ready_for_e3_bb_review"] is False


def test_cost_gate_adjustment_alias_input_is_rejected(tmp_path: Path) -> None:
    _write_ready_active_order_repo(tmp_path)

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        authority_readiness_packet={
            "schema_version": "fixture",
            "answers": {"cost_gate_adjustment": "LOWER"},
        },
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["authority_readiness_packet"]["authority_violation"] == (
        "cost_gate_adjustment"
    )
    assert packet["answers"]["source_contract_ready_for_e3_bb_review"] is False


def test_lineage_requirement_is_mandatory(tmp_path: Path) -> None:
    _write_ready_active_order_repo(tmp_path)
    active_module = tmp_path / "rust/openclaw_engine/src/bounded_probe_active_order.rs"
    active_module.write_text(
        active_module.read_text(encoding="utf-8").replace(
            "matched_blocked_control",
            "removed_matched_control",
        ),
        encoding="utf-8",
    )
    dispatch = tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs"
    dispatch.write_text(
        dispatch.read_text(encoding="utf-8").replace(
            "matched_blocked_control",
            "removed_matched_control",
        ),
        encoding="utf-8",
    )

    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=tmp_path,
        candidate=_candidate(),
        now_utc=NOW,
    )

    assert packet["status"] == PATCH_REQUIRED_STATUS
    assert "candidate_matched_order_fill_fee_slippage_lineage_missing" in packet[
        "source_contract"
    ]["missing_requirements"]
    assert packet["answers"]["order_authority_granted"] is False
