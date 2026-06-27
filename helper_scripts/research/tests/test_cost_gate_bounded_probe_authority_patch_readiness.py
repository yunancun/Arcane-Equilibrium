from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.bounded_probe_authority_patch_readiness import (
    PATCH_READINESS_SCHEMA_VERSION,
    build_bounded_demo_probe_authority_patch_readiness,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 22, 20, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "ma_crossover|BTCUSDT|Sell"


def _placement_plan(
    *,
    generated_at: str = "2026-06-22T19:55:00+00:00",
    authority_overrides: dict[str, object] | None = None,
    status: str = "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW",
) -> dict:
    boundary = {
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }
    if authority_overrides:
        boundary.update(authority_overrides)
    return {
        "schema_version": "bounded_demo_probe_placement_repair_plan_v1",
        "generated_at_utc": generated_at,
        "status": status,
        "reason": "synthetic_ready_plan",
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 240,
        },
        "placement_repair_plan": {
            "schema_version": "bounded_demo_probe_placement_repair_plan_v1",
            "status": "OPERATOR_REVIEW_READY_NOT_ACTIVE",
            "active": False,
            "requires_separate_operator_authorization": True,
            "order_mode": "post_only_near_touch_or_skip",
            "max_fresh_bbo_age_ms": 1000,
            "max_initial_passive_gap_bps": 75.0,
            "candidate": {
                "side_cell_key": SIDE_CELL,
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 240,
            },
            "probe_limits": {
                "max_probe_intents_before_review": 3,
                "max_demo_notional_usdt_per_order": 10.0,
            },
            "skip_record": {
                "record_type": "bounded_probe_touchability_block",
            },
            "post_order_evidence": [
                "demo_order_to_fill_gap_audit_after_probe",
                "fill_fee_slippage_rows_after_fill",
                "matched_blocked_signal_control_outcomes",
            ],
            "authority_boundary": boundary,
        },
        "answers": boundary,
        "boundary": "fixture",
    }


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


NO_RUNTIME_AUTHORITY_TRUE_KEYS = {
    "active_caller_enablement_authority_granted",
    "active_order_submission_authority_granted",
    "active_order_submission_ready_is_order_authority",
    "active_caller_source_ready_for_review_is_order_authority",
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "actual_runtime_admission_enablement_ready",
    "adapter_enablement_performed",
    "adapter_enabled_by_this_packet",
    "allowed_to_submit_order",
    "allowed_to_submit_order_in_current_review",
    "api_call_performed",
    "auth_mutation_performed",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "canonical_plan_mutation_performed",
    "crontab_edit_performed",
    "crontab_mutation_performed",
    "exchange_facing_order_authority_granted",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "live_execution_allowed",
    "order_authority_granted",
    "order_cancel_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_adapter_enablement_performed",
    "runtime_config_mutation_performed",
    "runtime_env_mutation_performed",
    "runtime_mutation_performed",
    "runtime_order_authority_found",
    "runtime_probe_authority_found",
    "rust_writer_enabled",
    "service_mutation_performed",
    "service_restart_performed",
    "writer_enablement_performed",
    "writer_enabled",
}


def _iter_key_values(payload: object, prefix: str = ""):
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, key, value
            yield from _iter_key_values(value, path)
    elif isinstance(payload, list):
        for idx, value in enumerate(payload):
            yield from _iter_key_values(value, f"{prefix}[{idx}]")


def _assert_no_runtime_authority_true(packet: dict) -> None:
    for path, key, value in _iter_key_values(packet):
        if key in NO_RUNTIME_AUTHORITY_TRUE_KEYS:
            assert value is False, f"{path} unexpectedly grants authority/action"
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert (
        packet["runtime_admission_propagation_review"]["answers"][
            "main_cost_gate_adjustment"
        ]
        == "NONE"
    )


def _write_existing_seams(repo: Path) -> None:
    _write(
        repo / "rust/openclaw_engine/src/demo_learning_lane.rs",
        """
pub const ORDER_AUTHORITY_GRANTED: &str = "DEMO_LEARNING_PROBE_GRANTED";
pub fn evaluate_probe_admission() {
    let main_cost_gate_adjustment = "NONE";
    let _ = main_cost_gate_adjustment;
}
""",
    )
    _write(
        repo / "rust/openclaw_engine/src/demo_learning_lane_hot_path.rs",
        """
pub fn exchange_gate_reject_event() {
    let _ = ELIGIBLE_REJECT_REASON_CODE;
}
""",
    )
    _write(
        repo / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
//! This writer does not submit orders.
pub fn writer() {
    let _ = build_admission_ledger_record_with_placement();
    let _ = build_capture_error_ledger_record();
}
""",
    )
    _write(
        repo / "rust/openclaw_engine/src/demo_learning_lane_ledger.rs",
        """
pub const ADMISSION_LEDGER_RECORD_TYPE: &str = "probe_admission_decision";
pub const CAPTURE_ERROR_LEDGER_RECORD_TYPE: &str = "probe_capture_error";
pub struct AdmissionLedgerRecord { pub allowed_to_submit_order: bool }
""",
    )
    _write(
        repo / "rust/openclaw_engine/src/intent_processor/mod.rs",
        """
pub struct OrderIntent { pub limit_price: Option<f64>, pub time_in_force: Option<TimeInForce> }
pub fn maker() { let _ = TimeInForce::PostOnly; }
""",
    )
    _write(
        repo / "rust/openclaw_engine/src/order_manager.rs",
        """pub enum TimeInForce { PostOnly }""",
    )
    _write(
        repo / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
fn dispatch(intent: OrderIntent) {
    let _ = OrderDispatchRequest {
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force,
    };
}
""",
    )


def _write_patch_adapter(repo: Path) -> None:
    _write(
        repo / "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        """
pub enum BoundedProbePlacementDecision {
    Submit(BoundedProbeAttemptPlacement),
    Skip(BoundedProbeTouchabilityBlock),
}

pub struct BoundedProbeAttemptPlacement {
    pub record_type: &'static str,
    pub side_cell_key: String,
    pub touch_gap_bps: f64,
}

pub struct BoundedProbeTouchabilityBlock {
    pub record_type: &'static str,
    pub side_cell_key: String,
}

pub fn post_only_near_touch_or_skip() -> BoundedProbePlacementDecision {
    let max_fresh_bbo_age_ms = 1000;
    let max_initial_passive_gap_bps = 75.0;
    let touch_gap_bps = max_initial_passive_gap_bps;
    let skip = BoundedProbeTouchabilityBlock {
        record_type: "bounded_probe_touchability_block",
        side_cell_key: String::new(),
    };
    let attempt = BoundedProbeAttemptPlacement {
        record_type: "bounded_probe_attempt",
        side_cell_key: skip.side_cell_key.clone(),
        touch_gap_bps,
    };
    let _ = (max_fresh_bbo_age_ms, touch_gap_bps, skip);
    BoundedProbePlacementDecision::Submit(attempt)
}
""",
    )


def _write_authority_path_wiring(repo: Path) -> None:
    _write(
        repo / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
const BOUNDED_PROBE_ATTEMPT_RECORD_TYPE: &str = "bounded_probe_attempt";
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
fn dispatch(intent: OrderIntent) {
    let req = BoundedProbeOptionalBboPlacementRequest {};
    let _ = post_only_near_touch_from_optional_bbo_or_skip(&req);
    let _ = BOUNDED_PROBE_ATTEMPT_RECORD_TYPE;
    let _ = OrderDispatchRequest {
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force,
    };
}
""",
    )


def test_missing_placement_plan_fails_closed(tmp_path: Path) -> None:
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=None,
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["schema_version"] == PATCH_READINESS_SCHEMA_VERSION
    assert packet["status"] == "PLACEMENT_REPAIR_PLAN_REQUIRED"
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_existing_seams_without_near_touch_adapter_requires_rust_patch(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["status"] == "RUST_PATCH_REQUIRED_NEAR_TOUCH_PLACEMENT_ADAPTER_MISSING"
    assert packet["answers"]["existing_authority_seams_present"] is True
    assert packet["answers"]["rust_near_touch_authority_adapter_present"] is False
    assert packet["answers"]["rust_patch_required"] is True
    assert "near_touch_or_skip_adapter_missing_from_rust_authority_path" in packet[
        "source_readiness"
    ]["missing_required_patch_seams"]
    assert "execution_realism_first" in markdown
    assert "edge_amplification_by_side_cell_horizon" in markdown


def test_full_source_patch_readiness_can_pass_after_adapter_exists(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
    assert packet["answers"]["rust_near_touch_authority_adapter_present"] is True
    assert packet["answers"]["rust_authority_path_wiring_present"] is True
    assert packet["answers"]["active_order_submission_ready"] is False
    assert packet["answers"]["active_order_submission_authority_granted"] is False
    assert (
        packet["active_order_submission_readiness"]["status"]
        == "ACTIVE_ORDER_SUBMISSION_WIRING_MISSING"
    )
    assert "demo_learning_lane_writer_contract_no_order_submission" in packet[
        "active_order_submission_readiness"
    ]["blockers"]
    assert packet["answers"]["rust_patch_required"] is False
    assert packet["source_readiness"]["missing_required_patch_seams"] == []


def test_order_intent_tif_surface_requires_postonly_on_time_in_force_enum(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write_authority_path_wiring(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/intent_processor/mod.rs",
        """
pub struct OrderIntent {
    pub limit_price: Option<f64>,
    pub time_in_force: Option<TimeInForce>,
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/order_manager.rs",
        """
pub enum TimeInForce { GTC }
pub enum UnrelatedPlacementMode { PostOnly }
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "SOURCE_SCAN_INCOMPLETE"
    assert packet["answers"]["existing_authority_seams_present"] is False
    assert "order_intent_limit_tif_surface_missing" in packet["source_readiness"][
        "missing_existing_seams"
    ]
    check = next(
        row
        for row in packet["source_readiness"]["existing_authority_seams"]
        if row["check_id"] == "order_intent_limit_tif_surface"
    )
    assert check["scan_mode"] == "code_without_comments_or_strings_structural"
    assert check["missing_patterns"] == ["TimeInForce.PostOnly"]
    _assert_no_runtime_authority_true(packet)


def test_adapter_without_authority_path_wiring_still_requires_patch(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "RUST_PATCH_REQUIRED_AUTHORITY_PATH_WIRING_MISSING"
    assert packet["answers"]["rust_near_touch_authority_adapter_present"] is True
    assert packet["answers"]["rust_authority_path_wiring_present"] is False
    assert packet["answers"]["rust_patch_required"] is True
    assert "authority_path_wiring_missing_from_tick_dispatch" in packet[
        "source_readiness"
    ]["missing_required_patch_seams"]


def test_adapter_and_wiring_without_required_guard_seams_still_requires_patch(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        """
pub enum BoundedProbePlacementDecision { Submit }
pub fn post_only_near_touch_or_skip() -> BoundedProbePlacementDecision {
    BoundedProbePlacementDecision::Submit
}
""",
    )
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "RUST_PATCH_REQUIRED_REQUIRED_SEAMS_MISSING"
    assert packet["answers"]["rust_patch_required"] is True
    assert "fresh_bbo_age_guard_missing_from_rust_authority_path" in packet[
        "source_readiness"
    ]["missing_required_patch_seams"]
    assert "candidate_matched_attempt_lineage_missing_from_rust_authority_path" in packet[
        "source_readiness"
    ]["missing_required_patch_seams"]


def test_required_patch_marker_strings_do_not_make_readiness_ready(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        """
pub fn marker_only() {
    let _ = "post_only_near_touch_or_skip BoundedProbePlacementDecision";
    let _ = "max_fresh_bbo_age_ms max_initial_passive_gap_bps touch_gap_bps";
    let _ = "BoundedProbeTouchabilityBlock record_type";
    let _ = "BoundedProbeAttemptPlacement side_cell_key";
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
fn dispatch(intent: OrderIntent) {
    let _ = "post_only_near_touch_from_optional_bbo_or_skip";
    let _ = "BoundedProbeOptionalBboPlacementRequest";
    let _ = "BOUNDED_PROBE_ATTEMPT_RECORD_TYPE";
    let _ = OrderDispatchRequest {
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force,
    };
}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] != "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
    assert packet["answers"]["rust_patch_required"] is True
    assert packet["source_readiness"]["required_patch_seams_present"] is False


def test_required_patch_marker_strings_with_comment_tokens_do_not_make_ready(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        """
pub fn marker_only() {
    let _ = "post_only_near_touch_or_skip //";
    let _ = "BoundedProbePlacementDecision //";
    let _ = "max_fresh_bbo_age_ms max_initial_passive_gap_bps touch_gap_bps //";
    let _ = "BoundedProbeTouchabilityBlock record_type //";
    let _ = "BoundedProbeAttemptPlacement side_cell_key //";
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
fn dispatch(intent: OrderIntent) {
    let _ = "post_only_near_touch_from_optional_bbo_or_skip //";
    let _ = "BoundedProbeOptionalBboPlacementRequest //";
    let _ = "BOUNDED_PROBE_ATTEMPT_RECORD_TYPE //";
    let _ = OrderDispatchRequest {
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force,
    };
}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] != "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
    assert packet["answers"]["rust_patch_required"] is True
    assert packet["source_readiness"]["required_patch_seams_present"] is False


def test_required_patch_raw_marker_strings_do_not_make_readiness_ready(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        """
pub fn marker_only() {
    let _ = r#"post_only_near_touch_or_skip " BoundedProbePlacementDecision //"#;
    let _ = r##"max_fresh_bbo_age_ms max_initial_passive_gap_bps touch_gap_bps //"##;
    let _ = r#"BoundedProbeTouchabilityBlock record_type //"#;
    let _ = r#"BoundedProbeAttemptPlacement side_cell_key //"#;
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
fn dispatch(intent: OrderIntent) {
    let _ = r#"post_only_near_touch_from_optional_bbo_or_skip //"#;
    let _ = r##"BoundedProbeOptionalBboPlacementRequest //"##;
    let _ = r#"BOUNDED_PROBE_ATTEMPT_RECORD_TYPE //"#;
    let _ = OrderDispatchRequest {
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force,
    };
}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] != "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
    assert packet["answers"]["rust_patch_required"] is True
    assert packet["source_readiness"]["required_patch_seams_present"] is False


def test_required_patch_multiline_marker_strings_do_not_make_readiness_ready(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        """
pub fn marker_only() {
    let _ = "
post_only_near_touch_or_skip
BoundedProbePlacementDecision
max_fresh_bbo_age_ms
max_initial_passive_gap_bps
touch_gap_bps
BoundedProbeTouchabilityBlock
record_type
BoundedProbeAttemptPlacement
side_cell_key
";
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
fn dispatch(intent: OrderIntent) {
    let _ = "
post_only_near_touch_from_optional_bbo_or_skip
BoundedProbeOptionalBboPlacementRequest
BOUNDED_PROBE_ATTEMPT_RECORD_TYPE
";
    let _ = OrderDispatchRequest {
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force,
    };
}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] != "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
    assert packet["answers"]["rust_patch_required"] is True
    assert packet["source_readiness"]["required_patch_seams_present"] is False


def test_required_patch_macro_marker_tokens_do_not_make_readiness_ready(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        """
pub fn marker_only() {
    stringify!(
        post_only_near_touch_or_skip
        BoundedProbePlacementDecision
        max_fresh_bbo_age_ms
        max_initial_passive_gap_bps
        touch_gap_bps
        BoundedProbeTouchabilityBlock
        record_type
        BoundedProbeAttemptPlacement
        side_cell_key
    );
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
fn dispatch(intent: OrderIntent) {
    stringify!(
        post_only_near_touch_from_optional_bbo_or_skip
        BoundedProbeOptionalBboPlacementRequest
        BOUNDED_PROBE_ATTEMPT_RECORD_TYPE
    );
    let _ = OrderDispatchRequest {
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force,
    };
}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] != "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
    assert packet["answers"]["rust_patch_required"] is True
    assert packet["source_readiness"]["required_patch_seams_present"] is False


def test_existing_seam_marker_strings_do_not_make_readiness_ready(
    tmp_path: Path,
) -> None:
    for rel_path in (
        "rust/openclaw_engine/src/demo_learning_lane.rs",
        "rust/openclaw_engine/src/demo_learning_lane_hot_path.rs",
        "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        "rust/openclaw_engine/src/demo_learning_lane_ledger.rs",
        "rust/openclaw_engine/src/intent_processor/mod.rs",
        "rust/openclaw_engine/src/order_manager.rs",
        "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
    ):
        _write(
            tmp_path / rel_path,
            """
// evaluate_probe_admission ORDER_AUTHORITY_GRANTED main_cost_gate_adjustment
pub fn marker_only() {
    let _ = "exchange_gate_reject_event ELIGIBLE_REJECT_REASON_CODE";
    let _ = "ADMISSION_LEDGER_RECORD_TYPE CAPTURE_ERROR_LEDGER_RECORD_TYPE";
    let _ = "build_admission_ledger_record_with_placement build_capture_error_ledger_record";
    let _ = "allowed_to_submit_order limit_price time_in_force TimeInForce::PostOnly";
    let _ = "best_bid best_ask execution_reference";
    let _ = "OrderDispatchRequest limit_price: intent.limit_price time_in_force: intent.time_in_force";
}
""",
        )
    _write_patch_adapter(tmp_path)
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] != "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
    assert packet["answers"]["existing_authority_seams_present"] is False
    assert packet["source_readiness"]["missing_existing_seams"]


def test_authority_grant_in_placement_plan_is_rejected(tmp_path: Path) -> None:
    _write_existing_seams(tmp_path)
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(
            authority_overrides={"order_authority_granted": True}
        ),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["placement_repair_plan"]["authority_preserved"] is False


def test_truthy_string_authority_grant_in_placement_plan_is_rejected(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(
            authority_overrides={"order_authority_granted": "true"}
        ),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["placement_repair_plan"]["authority_preserved"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_grant_like_string_authority_grant_in_placement_plan_is_rejected(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(
            authority_overrides={"order_authority_granted": "DEMO_LEARNING_PROBE_GRANTED"}
        ),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["placement_repair_plan"]["authority_preserved"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_adjacent_authority_alias_in_placement_plan_is_rejected(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(
            authority_overrides={
                "private_endpoint_called": "yes",
                "bounded_demo_probe_authorized": True,
            }
        ),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["placement_repair_plan"]["authority_preserved"] is False


def test_cost_gate_adjustment_alias_in_placement_plan_is_rejected(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(
            authority_overrides={"cost_gate_adjustment": "LOWER"}
        ),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["placement_repair_plan"]["authority_preserved"] is False


def test_authority_alias_in_placement_plan_is_rejected(tmp_path: Path) -> None:
    _write_existing_seams(tmp_path)
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(
            authority_overrides={"runtime_env_mutation_performed": "enabled"}
        ),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["placement_repair_plan"]["authority_preserved"] is False


def test_current_repo_reports_gui_cap_supplier_source_ready_without_runtime_authority() -> None:
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=Path.cwd(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW"
    assert packet["answers"]["existing_authority_seams_present"] is True
    assert packet["source_readiness"]["missing_existing_seams"] == []
    assert packet["answers"]["rust_near_touch_authority_adapter_present"] is True
    assert packet["answers"]["rust_authority_path_wiring_present"] is True
    assert packet["answers"]["active_order_submission_ready"] is True
    assert packet["answers"]["active_order_submission_authority_granted"] is False
    blockers = packet["active_order_submission_readiness"]["blockers"]
    assert blockers == []
    assert "separate_source_patch_to_enable_active_bounded_demo_order_submission" not in packet[
        "active_order_submission_readiness"
    ]["required_before_order"]
    assert "runtime_source_sync_and_clean_head_verification" in packet[
        "active_order_submission_readiness"
    ]["required_before_order"]
    assert (
        packet["active_order_submission_readiness"]["status"]
        == "ACTIVE_ORDER_SUBMISSION_WIRING_PRESENT"
    )
    assert (
        packet["active_order_submission_readiness"]["evidence"][
            "runtime_writer_default_adapter_disabled"
        ]
        is False
    )
    caller = packet["active_caller_enablement_review"]
    assert caller["status"] == "ACTIVE_CALLER_SOURCE_READY_FOR_E3_BB_REVIEW"
    assert caller["active_caller_source_ready_for_review"] is True
    assert packet["answers"]["active_caller_source_ready_for_review"] is True
    assert packet["answers"]["active_caller_enablement_ready"] is False
    assert packet["answers"]["active_caller_enablement_authority_granted"] is False
    assert caller["evidence"]["runtime_active_order_request_supplier_present"] is True
    assert (
        caller["evidence"]["runtime_active_order_request_supplier_argument_present"]
        is True
    )
    assert caller["evidence"]["runtime_active_order_request_supplier_contract_missing"] == []
    assert "runtime_writer_default_adapter_disabled" not in caller["blockers"]
    assert "production_active_bounded_probe_caller_missing" not in caller["blockers"]
    assert "reviewed_runtime_adapter_enablement_gate_missing" not in caller["blockers"]
    assert "runtime_active_order_request_supplier_missing" not in caller["blockers"]
    assert "runtime_source_sync_not_verified" in caller["blockers"]
    assert "post_restart_pending_order_reconciliation_not_proven" in caller["blockers"]
    propagation = packet["runtime_admission_propagation_review"]
    assert (
        propagation["status"]
        == "RUNTIME_ADMISSION_PROPAGATION_SOURCE_READY_FOR_E3_BB_REVIEW_NO_RUNTIME_AUTHORITY"
    )
    assert (
        packet["answers"]["runtime_admission_propagation_ready_for_e3_bb_review"]
        is True
    )
    assert (
        packet["answers"]["source_ready_sufficient_for_e3_bb_enablement_review"]
        is True
    )
    assert (
        packet["answers"]["active_order_submission_ready_is_order_authority"]
        is False
    )
    assert (
        packet["answers"][
            "active_caller_source_ready_for_review_is_order_authority"
        ]
        is False
    )
    assert packet["answers"]["actual_runtime_admission_enablement_ready"] is False
    assert packet["answers"]["runtime_source_sync_verified"] is False
    assert (
        packet["answers"]["post_restart_pending_order_reconciliation_proven"]
        is False
    )
    assert packet["answers"]["runtime_adapter_enablement_performed"] is False
    assert "active_caller_source_review_not_ready" not in propagation["blockers"]
    assert "runtime_source_sync_not_verified" in propagation["blockers"]
    assert "post_restart_pending_order_reconciliation_not_proven" in propagation[
        "blockers"
    ]
    assert (
        "runtime_adapter_enablement_not_performed_source_only_packet"
        in propagation["blockers"]
    )
    _assert_no_runtime_authority_true(packet)


def test_active_order_readiness_fails_closed_when_source_files_missing(
    tmp_path: Path,
) -> None:
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path / "missing-repo",
        now_utc=NOW,
    )

    active = packet["active_order_submission_readiness"]
    assert active["status"] == "ACTIVE_ORDER_SUBMISSION_WIRING_MISSING"
    assert packet["answers"]["active_order_submission_ready"] is False
    assert any(
        blocker.startswith("source_file_missing:")
        for blocker in active["blockers"]
    )
    assert "positive_active_order_submission_evidence_missing" in active["blockers"]


def test_active_order_readiness_requires_positive_submission_evidence(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub fn writer() {
    let _ = "probe_admission_decision";
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
fn dispatch() {
    let _ = "bounded_probe_attempt";
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        """
pub fn post_only_near_touch_or_skip() {}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    active = packet["active_order_submission_readiness"]
    assert active["status"] == "ACTIVE_ORDER_SUBMISSION_WIRING_MISSING"
    assert packet["answers"]["active_order_submission_ready"] is False
    assert active["evidence"]["missing_positive_active_evidence"] == [
        "writer_submits_candidate_matched_probe_order",
        "dispatch_forwards_admitted_bounded_probe_to_exchange",
        "adapter_enabled_by_runtime_bounded_probe_gate",
    ]
    assert "positive_active_order_submission_evidence_missing" in active["blockers"]
    assert packet["answers"]["order_authority_granted"] is False


def test_active_order_marker_strings_do_not_count_as_positive_evidence(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub fn writer() {
    let _ = "submit_candidate_matched_bounded_probe_order";
    let _ = "active_bounded_probe_order_submission";
    let _ = "bounded_probe_adapter_enabled";
    let _ = "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
fn dispatch() {
    let _ = "dispatch_admitted_bounded_probe_order";
    let _ = "active_bounded_probe_order_submission";
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
        """
pub fn post_only_near_touch_or_skip() {}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    active = packet["active_order_submission_readiness"]
    assert active["status"] == "ACTIVE_ORDER_SUBMISSION_WIRING_MISSING"
    assert active["evidence"]["positive_active_evidence"] == {
        "writer_submits_candidate_matched_probe_order": False,
        "dispatch_forwards_admitted_bounded_probe_to_exchange": False,
        "adapter_enabled_by_runtime_bounded_probe_gate": False,
    }
    assert "positive_active_order_submission_evidence_missing" in active["blockers"]
    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["production_active_caller_present"] is False
    assert caller["actual_active_caller_enablement_ready"] is False
    assert packet["answers"]["active_caller_enablement_authority_granted"] is False


def test_cfg_test_active_caller_does_not_count_as_production_enablement(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write_authority_path_wiring(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() {}
pub fn active_bounded_probe_order_submission() {}
#[cfg(test)]
mod tests {
    fn test_only_call() {
        let decision = submit_candidate_matched_bounded_probe_order();
        active_bounded_probe_order_submission(decision);
    }
}
fn writer() {
    let bounded_probe_adapter_enabled =
        std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED).ok();
    let _ = bounded_probe_adapter_enabled;
    let allowed_to_submit_order = false;
    let _ = allowed_to_submit_order;
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
const BOUNDED_PROBE_ATTEMPT_RECORD_TYPE: &str = "bounded_probe_attempt";
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
pub fn active_bounded_probe_order_submission() {}
pub fn dispatch_admitted_bounded_probe_order() {}
fn dispatch(intent: OrderIntent) {
    let req = BoundedProbeOptionalBboPlacementRequest {};
    let _ = post_only_near_touch_from_optional_bbo_or_skip(&req);
    let _ = BOUNDED_PROBE_ATTEMPT_RECORD_TYPE;
    let _ = OrderDispatchRequest {
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force,
    };
}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert packet["answers"]["active_order_submission_ready"] is True
    assert caller["evidence"]["production_active_caller_present"] is False
    assert "production_active_bounded_probe_caller_missing" in caller["blockers"]
    assert caller["actual_active_caller_enablement_ready"] is False


def test_active_caller_enablement_source_ready_remains_no_authority(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
struct RiskConfig { limits: GuiRiskLimits }
struct GuiRiskLimits {
    per_trade_risk_pct: f64,
    position_size_max_pct: f64,
    max_order_notional_usdt: f64,
}
struct AcceptedDemoEquity { equity_usdt: f64 }
struct OrderDispatchRequest;
struct UnboundedSender<T>(T);
struct ActiveBoundedProbeOrderRequest {
    order_link_id: String,
    decision_lease_id: Option<String>,
    limits: ActiveBoundedProbeRiskLimits,
}
struct ActiveBoundedProbeRiskLimits { max_demo_notional_usdt_per_order: f64 }
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) -> Option<u8> { Some(1) }
fn dispatch_active_bounded_probe_order_draft(
    _tx: UnboundedSender<OrderDispatchRequest>,
    _active_order_draft: u8,
) {}
fn bounded_probe_order_link_id_for_candidate() -> String { String::new() }
fn bounded_probe_adapter_enabled_from_value(value: &str) -> bool {
    value.trim() == "1" || value.trim().eq_ignore_ascii_case("true")
}
fn evaluate_probe_admission(_enabled: bool) {}
fn gui_derived_active_order_request_supplier(
    risk_config: RiskConfig,
    accepted_demo_equity: AcceptedDemoEquity,
    decision_lease_id: String,
) -> ActiveBoundedProbeOrderRequest {
    let per_trade_budget_usdt =
        accepted_demo_equity.equity_usdt * risk_config.limits.per_trade_risk_pct;
    let single_position_budget_usdt =
        accepted_demo_equity.equity_usdt * risk_config.limits.position_size_max_pct / 100.0;
    let max_order_notional_usdt = risk_config.limits.max_order_notional_usdt;
    let effective_single_order_cap_usdt = per_trade_budget_usdt
        .min(single_position_budget_usdt)
        .min(max_order_notional_usdt);
    let order_link_id = bounded_probe_order_link_id_for_candidate();
    let limits = ActiveBoundedProbeRiskLimits {
        max_demo_notional_usdt_per_order: effective_single_order_cap_usdt,
    };
    ActiveBoundedProbeOrderRequest {
        order_link_id,
        decision_lease_id: Some(decision_lease_id),
        limits,
    }
}
fn build_runtime_admission_result(
    active_order_request: Option<ActiveBoundedProbeOrderRequest>,
    active_order_dispatch_channel_available: bool,
) {
    let bounded_probe_adapter_env_enabled =
        std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED)
            .map(|value| bounded_probe_adapter_enabled_from_value(&value))
            .unwrap_or(false);
    let bounded_probe_adapter_enabled = bounded_probe_adapter_env_enabled
        && active_order_request.is_some()
        && active_order_dispatch_channel_available;
    let decision = submit_candidate_matched_bounded_probe_order();
    let active_order_draft = active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(bounded_probe_adapter_enabled);
    if let Some(draft) = active_order_draft {
        dispatch_active_bounded_probe_order_draft(UnboundedSender(OrderDispatchRequest), draft);
    }
}
fn runtime_caller(risk_config: RiskConfig, accepted_demo_equity: AcceptedDemoEquity, decision_lease_id: String) {
    let active_order_request = Some(gui_derived_active_order_request_supplier(
        risk_config,
        accepted_demo_equity,
        decision_lease_id,
    ));
    build_runtime_admission_result(active_order_request, true);
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
const BOUNDED_PROBE_ATTEMPT_RECORD_TYPE: &str = "bounded_probe_attempt";
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
pub fn active_bounded_probe_order_submission() {}
pub fn dispatch_admitted_bounded_probe_order() {}
fn dispatch(intent: OrderIntent, active_order_request: Option<ActiveBoundedProbeOrderRequest>) {
    let req = BoundedProbeOptionalBboPlacementRequest {};
    let _ = post_only_near_touch_from_optional_bbo_or_skip(&req);
    let _ = BOUNDED_PROBE_ATTEMPT_RECORD_TYPE;
    let _ = OrderDispatchRequest {
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force,
    };
    writer.record_reject_event_with_placement_active_request_and_order_dispatch(
        reject_event,
        risk_state,
        event_ts_ms,
        Some(placement_decision),
        active_order_request,
        self.order_dispatch_tx.clone(),
    );
}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    supplier_checks = caller["evidence"][
        "runtime_active_order_request_supplier_contract_checks"
    ]
    assert caller["status"] == "ACTIVE_CALLER_SOURCE_READY_FOR_E3_BB_REVIEW"
    assert caller["active_caller_source_ready_for_review"] is True
    assert caller["evidence"]["runtime_active_order_request_supplier_present"] is True
    assert caller["evidence"]["runtime_active_order_request_supplier_argument_present"] is True
    assert caller["evidence"]["runtime_active_order_request_supplier_contract_missing"] == []
    assert all(supplier_checks.values())
    assert packet["answers"]["active_caller_source_ready_for_review"] is True
    assert caller["actual_active_caller_enablement_ready"] is False
    assert packet["answers"]["active_caller_enablement_ready"] is False
    assert packet["answers"]["active_caller_enablement_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["runtime_mutation_performed"] is False
    assert "runtime_source_sync_not_verified" in caller["blockers"]
    assert "post_restart_pending_order_reconciliation_not_proven" in caller["blockers"]
    propagation = packet["runtime_admission_propagation_review"]
    assert (
        propagation["status"]
        == "RUNTIME_ADMISSION_PROPAGATION_SOURCE_READY_FOR_E3_BB_REVIEW_NO_RUNTIME_AUTHORITY"
    )
    assert (
        propagation["runtime_admission_propagation_ready_for_e3_bb_review"]
        is True
    )
    assert (
        packet["answers"]["runtime_admission_propagation_ready_for_e3_bb_review"]
        is True
    )
    assert (
        packet["answers"]["source_ready_sufficient_for_e3_bb_enablement_review"]
        is True
    )
    assert (
        packet["answers"]["active_order_submission_ready_is_order_authority"]
        is False
    )
    assert (
        packet["answers"][
            "active_caller_source_ready_for_review_is_order_authority"
        ]
        is False
    )
    assert packet["answers"]["actual_runtime_admission_enablement_ready"] is False
    assert packet["answers"]["runtime_source_sync_verified"] is False
    assert (
        packet["answers"]["post_restart_pending_order_reconciliation_proven"]
        is False
    )
    assert packet["answers"]["runtime_adapter_enablement_performed"] is False
    assert packet["answers"]["adapter_enabled_by_this_packet"] is False
    assert packet["answers"]["allowed_to_submit_order_in_current_review"] is False
    assert packet["answers"]["exchange_facing_order_authority_granted"] is False
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert "runtime_source_sync_not_verified" in propagation["blockers"]
    assert "post_restart_pending_order_reconciliation_not_proven" in propagation[
        "blockers"
    ]
    assert (
        "runtime_adapter_enablement_not_performed_source_only_packet"
        in propagation["blockers"]
    )
    assert "active_caller_source_review_not_ready" not in propagation["blockers"]
    _assert_no_runtime_authority_true(packet)


def test_active_caller_supplier_rejects_hardcoded_local_10_usdt_cap(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
struct RiskConfig { limits: GuiRiskLimits }
struct GuiRiskLimits {
    per_trade_risk_pct: f64,
    position_size_max_pct: f64,
    max_order_notional_usdt: f64,
}
struct AcceptedDemoEquity { equity_usdt: f64 }
struct ActiveBoundedProbeOrderRequest {
    order_link_id: String,
    decision_lease_id: Option<String>,
    limits: ActiveBoundedProbeRiskLimits,
}
struct ActiveBoundedProbeRiskLimits { max_demo_notional_usdt_per_order: f64 }
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn bounded_probe_order_link_id_for_candidate() -> String { String::new() }
fn bounded_probe_adapter_enabled_from_value(value: &str) -> bool {
    value.trim() == "1" || value.trim().eq_ignore_ascii_case("true")
}
fn evaluate_probe_admission(_enabled: bool) {}
fn build_runtime_admission_record(active_order_request: Option<ActiveBoundedProbeOrderRequest>) {
    let bounded_probe_adapter_enabled =
        std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED)
            .map(|value| bounded_probe_adapter_enabled_from_value(&value))
            .unwrap_or(false)
            && active_order_request.is_some();
    let decision = submit_candidate_matched_bounded_probe_order();
    active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(bounded_probe_adapter_enabled);
}
fn runtime_caller(risk_config: RiskConfig, accepted_demo_equity: AcceptedDemoEquity, decision_lease_id: String) {
    let per_trade_budget_usdt =
        accepted_demo_equity.equity_usdt * risk_config.limits.per_trade_risk_pct;
    let single_position_budget_usdt =
        accepted_demo_equity.equity_usdt * risk_config.limits.position_size_max_pct / 100.0;
    let max_order_notional_usdt = risk_config.limits.max_order_notional_usdt;
    let effective_single_order_cap_usdt = per_trade_budget_usdt
        .min(single_position_budget_usdt)
        .min(max_order_notional_usdt);
    let _ = effective_single_order_cap_usdt;
    let order_link_id = bounded_probe_order_link_id_for_candidate();
    let active_order_request = Some(ActiveBoundedProbeOrderRequest {
        order_link_id,
        decision_lease_id: Some(decision_lease_id),
        limits: ActiveBoundedProbeRiskLimits {
            max_demo_notional_usdt_per_order: 10.0,
        },
    });
    build_runtime_admission_record(active_order_request);
}
""",
    )
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    missing = caller["evidence"][
        "runtime_active_order_request_supplier_contract_missing"
    ]
    assert caller["evidence"]["runtime_active_order_request_supplier_argument_present"] is True
    assert caller["evidence"]["runtime_active_order_request_supplier_present"] is False
    assert "hardcoded_local_10_usdt_cap_absent" in missing
    assert caller["evidence"]["suspicious_hardcoded_local_10_usdt_cap_matches"]
    assert caller["active_caller_source_ready_for_review"] is False
    assert (
        "runtime_active_order_request_supplier_contract_missing:hardcoded_local_10_usdt_cap_absent"
        in caller["blockers"]
    )
    _assert_no_runtime_authority_true(packet)


def test_env_gate_without_active_request_guard_does_not_count(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn bounded_probe_adapter_enabled_from_value(value: &str) -> bool {
    value.trim() == "1" || value.trim().eq_ignore_ascii_case("true")
}
fn evaluate_probe_admission(_enabled: bool) {}
fn build_runtime_admission_record() {
    let bounded_probe_adapter_enabled =
        std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED)
            .map(|value| bounded_probe_adapter_enabled_from_value(&value))
            .unwrap_or(false);
    let decision = submit_candidate_matched_bounded_probe_order();
    active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(bounded_probe_adapter_enabled);
}
""",
    )
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["production_active_caller_present"] is True
    assert caller["evidence"]["runtime_adapter_enablement_gate_present"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "reviewed_runtime_adapter_enablement_gate_missing" in caller["blockers"]


def test_env_presence_gate_does_not_count_even_with_active_request_guard(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn evaluate_probe_admission(_enabled: bool) {}
fn build_runtime_admission_record(active_order_request: Option<u8>) {
    let bounded_probe_adapter_enabled =
        std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED).ok().is_some()
            && active_order_request.is_some();
    let decision = submit_candidate_matched_bounded_probe_order();
    active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(bounded_probe_adapter_enabled);
}
""",
    )
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["production_active_caller_present"] is True
    assert caller["evidence"]["runtime_adapter_enablement_gate_present"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "reviewed_runtime_adapter_enablement_gate_missing" in caller["blockers"]


def test_env_and_active_request_gate_without_dispatch_channel_guard_does_not_count(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) -> Option<u8> { Some(1) }
fn dispatch_active_bounded_probe_order_draft(_draft: u8) {}
fn bounded_probe_adapter_enabled_from_value(value: &str) -> bool {
    value.trim() == "1" || value.trim().eq_ignore_ascii_case("true")
}
fn evaluate_probe_admission(_enabled: bool) {}
fn build_runtime_admission_result(
    active_order_request: Option<u8>,
    active_order_dispatch_channel_available: bool,
) {
    let bounded_probe_adapter_env_enabled =
        std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED)
            .map(|value| bounded_probe_adapter_enabled_from_value(&value))
            .unwrap_or(false);
    let bounded_probe_adapter_enabled = bounded_probe_adapter_env_enabled
        && active_order_request.is_some();
    let decision = submit_candidate_matched_bounded_probe_order();
    let active_order_draft = active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(bounded_probe_adapter_enabled);
    let _ = (active_order_dispatch_channel_available, active_order_draft);
}
""",
    )
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["production_active_caller_present"] is True
    assert caller["evidence"]["runtime_adapter_enablement_gate_present"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "reviewed_runtime_adapter_enablement_gate_missing" in caller["blockers"]


def test_unused_active_caller_helper_does_not_count_as_reviewed_runtime_path(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write_authority_path_wiring(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn evaluate_probe_admission(_enabled: bool) {}
fn unused_debug_active_caller() {
    let decision = submit_candidate_matched_bounded_probe_order();
    active_bounded_probe_order_submission(decision);
}
fn build_runtime_admission_record() {
    let bounded_probe_adapter_enabled =
        std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED).ok();
    evaluate_probe_admission(bounded_probe_adapter_enabled.is_some());
}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["production_active_caller_present"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "production_active_bounded_probe_caller_missing" in caller["blockers"]


def test_unused_dispatch_active_caller_does_not_count_as_reviewed_runtime_path(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn evaluate_probe_admission(_enabled: bool) {}
fn build_runtime_admission_record() {
    let bounded_probe_adapter_enabled =
        std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED).ok();
    evaluate_probe_admission(bounded_probe_adapter_enabled);
}
""",
    )
    _write(
        tmp_path / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
const BOUNDED_PROBE_ATTEMPT_RECORD_TYPE: &str = "bounded_probe_attempt";
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
pub fn active_bounded_probe_order_submission() {}
pub fn dispatch_admitted_bounded_probe_order() {}
fn unused_dispatch_helper() {
    active_bounded_probe_order_submission();
}
fn dispatch(intent: OrderIntent) {
    let req = BoundedProbeOptionalBboPlacementRequest {};
    let _ = post_only_near_touch_from_optional_bbo_or_skip(&req);
    let _ = BOUNDED_PROBE_ATTEMPT_RECORD_TYPE;
    let _ = OrderDispatchRequest {
        limit_price: intent.limit_price,
        time_in_force: intent.time_in_force,
    };
}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["tick_dispatch_call_sites"]
    assert caller["evidence"]["production_active_caller_present"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "production_active_bounded_probe_caller_missing" in caller["blockers"]


def test_env_gate_constant_without_runtime_admission_use_does_not_count(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write_authority_path_wiring(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn evaluate_probe_admission(_enabled: bool) {}
fn build_runtime_admission_record() {
    let decision = submit_candidate_matched_bounded_probe_order();
    active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(true);
}
""",
    )

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["runtime_adapter_enablement_gate_present"] is False
    assert caller["evidence"]["runtime_gate_feeds_admission_scan"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "reviewed_runtime_adapter_enablement_gate_missing" in caller["blockers"]


def test_env_read_inside_hardcoded_block_does_not_count(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn evaluate_probe_admission(_enabled: bool) {}
fn build_runtime_admission_record() {
    let bounded_probe_adapter_enabled = {
        let _unused = std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED).ok();
        true
    };
    let decision = submit_candidate_matched_bounded_probe_order();
    active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(bounded_probe_adapter_enabled);
}
""",
    )
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["production_active_caller_present"] is True
    assert caller["evidence"]["runtime_adapter_enablement_gate_present"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "reviewed_runtime_adapter_enablement_gate_missing" in caller["blockers"]


def test_wrapped_env_read_does_not_count_as_adapter_gate_flow(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn evaluate_probe_admission(_enabled: bool) {}
fn some_other_runtime_flag(_ignored: Result<String, std::env::VarError>) -> bool { true }
fn build_runtime_admission_record() {
    let bounded_probe_adapter_enabled =
        some_other_runtime_flag(std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED));
    let decision = submit_candidate_matched_bounded_probe_order();
    active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(bounded_probe_adapter_enabled);
}
""",
    )
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["production_active_caller_present"] is True
    assert caller["evidence"]["runtime_adapter_enablement_gate_present"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "reviewed_runtime_adapter_enablement_gate_missing" in caller["blockers"]


def test_hardcoded_true_adapter_gate_does_not_count(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn evaluate_probe_admission(_enabled: bool) {}
fn build_runtime_admission_record() {
    let _gate_name = OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED;
    let bounded_probe_adapter_enabled = true;
    let decision = submit_candidate_matched_bounded_probe_order();
    active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(bounded_probe_adapter_enabled);
}
""",
    )
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["production_active_caller_present"] is True
    assert caller["evidence"]["runtime_adapter_enablement_gate_present"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "reviewed_runtime_adapter_enablement_gate_missing" in caller["blockers"]


def test_typed_hardcoded_true_adapter_gate_does_not_count(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn evaluate_probe_admission(_enabled: bool) {}
fn build_runtime_admission_record() {
    let _gate_name = OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED;
    let bounded_probe_adapter_enabled: bool = true;
    let decision = submit_candidate_matched_bounded_probe_order();
    active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(bounded_probe_adapter_enabled);
}
""",
    )
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["production_active_caller_present"] is True
    assert caller["evidence"]["runtime_adapter_enablement_gate_present"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "reviewed_runtime_adapter_enablement_gate_missing" in caller["blockers"]


def test_unrelated_env_read_does_not_count_as_adapter_gate_flow(
    tmp_path: Path,
) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    _write(
        tmp_path / "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
        """
pub const OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED: &str =
    "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED";
pub fn build_admission_ledger_record_with_placement() {}
pub fn build_capture_error_ledger_record() {}
pub fn submit_candidate_matched_bounded_probe_order() -> u8 { 1 }
pub fn active_bounded_probe_order_submission(_decision: u8) {}
fn evaluate_probe_admission(_enabled: bool) {}
fn some_other_runtime_flag() -> bool { true }
fn build_runtime_admission_record() {
    let _unused_env = std::env::var(OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED).ok();
    let bounded_probe_adapter_enabled = some_other_runtime_flag();
    let decision = submit_candidate_matched_bounded_probe_order();
    active_bounded_probe_order_submission(decision);
    evaluate_probe_admission(bounded_probe_adapter_enabled);
}
""",
    )
    _write_authority_path_wiring(tmp_path)

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    caller = packet["active_caller_enablement_review"]
    assert caller["evidence"]["production_active_caller_present"] is True
    assert caller["evidence"]["runtime_adapter_enablement_gate_present"] is False
    assert caller["active_caller_source_ready_for_review"] is False
    assert "reviewed_runtime_adapter_enablement_gate_missing" in caller["blockers"]


def test_missing_existing_authority_seam_blocks_patch_review(tmp_path: Path) -> None:
    _write_existing_seams(tmp_path)
    _write_patch_adapter(tmp_path)
    (tmp_path / "rust/openclaw_engine/src/demo_learning_lane.rs").unlink()

    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=tmp_path,
        now_utc=NOW,
    )

    assert packet["status"] == "SOURCE_SCAN_INCOMPLETE"
    assert packet["answers"]["source_scan_complete"] is False
    assert "demo_learning_lane_admission_policy_missing" in packet[
        "source_readiness"
    ]["missing_existing_seams"]


def test_stale_placement_plan_requires_refresh(tmp_path: Path) -> None:
    _write_existing_seams(tmp_path)
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(generated_at="2026-06-20T19:55:00+00:00"),
        repo_root=tmp_path,
        now_utc=NOW,
        max_artifact_age_hours=24,
    )

    assert packet["status"] == "PLACEMENT_REPAIR_PLAN_REQUIRED"
    assert packet["placement_repair_plan"]["artifact"]["status"] == "STALE"
