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


def test_current_repo_reports_active_order_submission_source_ready_without_authority() -> None:
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_placement_plan(),
        repo_root=Path.cwd(),
        now_utc=NOW,
    )

    assert packet["answers"]["rust_near_touch_authority_adapter_present"] is True
    assert packet["answers"]["rust_authority_path_wiring_present"] is True
    assert packet["answers"]["active_order_submission_ready"] is True
    assert packet["answers"]["active_order_submission_authority_granted"] is False
    blockers = packet["active_order_submission_readiness"]["blockers"]
    assert blockers == []
    assert (
        packet["active_order_submission_readiness"]["status"]
        == "ACTIVE_ORDER_SUBMISSION_WIRING_PRESENT"
    )
    assert (
        packet["active_order_submission_readiness"]["evidence"][
            "runtime_writer_default_adapter_disabled"
        ]
        is True
    )


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
