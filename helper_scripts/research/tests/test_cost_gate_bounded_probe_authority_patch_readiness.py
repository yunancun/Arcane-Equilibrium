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
    let _ = "demo_learning_lane_must_not_lower_main_cost_gate";
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
pub fn writer() { let _ = "probe_admission_decision"; }
""",
    )
    _write(
        repo / "rust/openclaw_engine/src/demo_learning_lane_ledger.rs",
        """pub fn ledger() { let _ = "probe_capture_error"; }""",
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
pub fn post_only_near_touch_or_skip() {
    let decision = BoundedProbePlacementDecision::Submit;
    let max_fresh_bbo_age_ms = 1000;
    let max_initial_passive_gap_bps = 75.0;
    let touch_gap_bps = max_initial_passive_gap_bps;
    let record_type = "bounded_probe_touchability_block";
    let lineage = ("bounded_probe_attempt", "side_cell_key");
    let _ = (decision, max_fresh_bbo_age_ms, touch_gap_bps, record_type, lineage);
}
""",
    )


def _write_authority_path_wiring(repo: Path) -> None:
    _write(
        repo / "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        """
fn execution_reference(best_bid: Option<f64>, best_ask: Option<f64>) {}
fn dispatch(intent: OrderIntent) {
    let req = BoundedProbeOptionalBboPlacementRequest {};
    let _ = post_only_near_touch_from_optional_bbo_or_skip(&req);
    let _ = "bounded_probe_attempt";
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
    assert packet["answers"]["order_authority_granted"] is False


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
