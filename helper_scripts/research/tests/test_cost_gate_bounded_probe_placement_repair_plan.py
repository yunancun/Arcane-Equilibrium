from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.bounded_probe_placement_repair_plan import (
    PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION,
    build_bounded_demo_probe_placement_repair_plan,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 22, 14, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "ma_crossover|BTCUSDT|Sell"


def _touchability_preflight(
    *,
    status: str = "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE",
    order_status: str = "PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH",
    authority_overrides: dict[str, object] | None = None,
    fill_rows: int = 0,
    deep_no_touch: int = 6,
) -> dict:
    answers = {
        "bounded_probe_design_reviewable": True,
        "order_touchability_audit_fresh": True,
        "current_order_flow_deep_no_touch": deep_no_touch > 0,
        "touchability_repair_required": (
            status
            in {
                "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE",
                "FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED",
            }
        ),
        "first_attempt_touchability_bootstrap_required": (
            status == "FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED"
        ),
        "ready_for_operator_touchability_review": (
            status == "TOUCHABILITY_GATE_READY_FOR_OPERATOR_REVIEW"
        ),
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }
    if authority_overrides:
        answers.update(authority_overrides)
    return {
        "schema_version": "bounded_demo_probe_touchability_preflight_v1",
        "generated_at_utc": "2026-06-22T13:58:00+00:00",
        "status": status,
        "reason": "synthetic_touchability_fixture",
        "next_actions": ["synthetic_touchability_next_action"],
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 240,
        },
        "bounded_probe_design": {
            "authority_preserved": True,
            "design_schema_version": "bounded_demo_probe_design_v1",
            "design_status": "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN",
            "max_demo_notional_usdt_per_order": 10.0,
            "max_probe_intents_before_review": 3,
            "outcome_horizon_minutes": 240,
            "reviewable": True,
            "side": "Sell",
            "side_cell_key": SIDE_CELL,
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
        },
        "order_touchability": {
            "status": order_status,
            "reviewed_orders": 6,
            "fill_rows": fill_rows,
            "deep_passive_no_touch_orders": deep_no_touch,
            "bbo_touched_no_fill_orders": 0,
            "max_best_touch_gap_bps": 1530.6074,
            "min_best_touch_gap_bps": 1156.7403,
        },
        "placement_requirements": {
            "active": False,
            "requires_separate_operator_authorization": True,
            "environment": "demo_or_live_demo_only",
            "execution_path": "existing_rust_authority_path_only",
            "max_initial_passive_gap_bps": 75.0,
            "max_deep_no_touch_gap_bps": 500.0,
            "require_fresh_bbo_before_order": True,
            "post_only_allowed_only_if_gap_lte_max_initial_passive_gap_bps": True,
            "if_gap_exceeds_limit": "skip_probe_order_and_record_touchability_block",
            "require_order_to_fill_gap_audit_after_probe": True,
            "require_fill_fee_slippage_lineage_after_fill": True,
            "first_attempt_bootstrap": (
                status == "FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED"
            ),
            "first_attempt_bootstrap_is_proof": False,
            "max_probe_intents_before_review": 3,
            "max_demo_notional_usdt_per_order": 10.0,
        },
        "answers": answers,
        "boundary": "fixture",
    }


def test_deep_no_touch_emits_near_touch_or_skip_repair_plan() -> None:
    packet = build_bounded_demo_probe_placement_repair_plan(
        touchability_preflight=_touchability_preflight(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)
    plan = packet["placement_repair_plan"]

    assert packet["schema_version"] == PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION
    assert packet["status"] == "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
    assert packet["answers"]["placement_repair_plan_ready_for_operator_review"] is True
    assert packet["answers"]["near_touch_or_skip_required"] is True
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert plan["active"] is False
    assert plan["requires_separate_operator_authorization"] is True
    assert plan["order_mode"] == "post_only_near_touch_or_skip"
    assert plan["max_fresh_bbo_age_ms"] == 1000
    assert plan["max_initial_passive_gap_bps"] == 75.0
    assert plan["runtime_touchability_baseline"]["max_best_touch_gap_bps"] == 1530.6074
    assert "computed_best_touch_gap_bps_lte_max_initial_passive_gap_bps" in plan[
        "pre_order_checks"
    ]
    assert plan["side_aware_limit_rule"]["Sell"]["skip_if"] == (
        "touch_gap_bps > max_initial_passive_gap_bps"
    )
    assert plan["skip_record"]["record_type"] == "bounded_probe_touchability_block"
    assert "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW" in markdown


def test_missing_touchability_preflight_fails_closed() -> None:
    packet = build_bounded_demo_probe_placement_repair_plan(
        touchability_preflight=None,
        now_utc=NOW,
    )

    assert packet["status"] == "TOUCHABILITY_PREFLIGHT_REQUIRED"
    assert packet["source_touchability_preflight"]["artifact"]["status"] == "MISSING"
    assert packet["placement_repair_plan"]["status"] == "NOT_ACTIVE_BLOCKED"
    assert packet["answers"]["placement_repair_plan_ready_for_operator_review"] is False


def test_fill_path_reconcile_status_blocks_placement_repair_plan() -> None:
    packet = build_bounded_demo_probe_placement_repair_plan(
        touchability_preflight=_touchability_preflight(
            status="FILL_PATH_RECONCILE_REQUIRED",
            order_status="BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED",
            deep_no_touch=0,
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "FILL_PATH_RECONCILE_REQUIRED"
    assert packet["placement_repair_plan"]["status"] == "NOT_ACTIVE_BLOCKED"
    assert packet["answers"]["near_touch_or_skip_required"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_candidate_touchability_data_required_passes_through_without_repair_plan() -> None:
    packet = build_bounded_demo_probe_placement_repair_plan(
        touchability_preflight=_touchability_preflight(
            status="CANDIDATE_TOUCHABILITY_DATA_REQUIRED",
            order_status="FILL_FLOW_PRESENT",
            fill_rows=1,
            deep_no_touch=0,
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "CANDIDATE_TOUCHABILITY_DATA_REQUIRED"
    assert packet["placement_repair_plan"]["status"] == "NOT_ACTIVE_BLOCKED"
    assert packet["answers"]["placement_repair_plan_ready_for_operator_review"] is False
    assert packet["answers"]["near_touch_or_skip_required"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_first_attempt_bootstrap_emits_review_only_near_touch_plan() -> None:
    packet = build_bounded_demo_probe_placement_repair_plan(
        touchability_preflight=_touchability_preflight(
            status="FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED",
            order_status="FILL_FLOW_PRESENT",
            fill_rows=1,
            deep_no_touch=0,
        ),
        now_utc=NOW,
    )
    plan = packet["placement_repair_plan"]

    assert packet["status"] == "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
    assert (
        packet["reason"]
        == "first_candidate_attempt_requires_review_only_near_touch_or_skip_probe_placement"
    )
    assert packet["next_actions"] == [
        "operator_review_first_attempt_near_touch_or_skip_placement_plan",
        "only_after_separate_authorization_patch_existing_rust_authority_path",
        "rerun_order_to_fill_touchability_audit_after_first_candidate_attempt",
    ]
    assert packet["answers"]["placement_repair_plan_ready_for_operator_review"] is True
    assert packet["answers"]["near_touch_or_skip_required"] is True
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False
    assert plan["status"] == "OPERATOR_REVIEW_READY_NOT_ACTIVE"
    assert plan["active"] is False
    assert plan["requires_separate_operator_authorization"] is True
    assert plan["runtime_touchability_baseline"]["first_attempt_bootstrap"] is True
    assert plan["runtime_touchability_baseline"]["first_attempt_bootstrap_is_proof"] is False


def test_authority_grant_in_touchability_preflight_is_rejected() -> None:
    packet = build_bounded_demo_probe_placement_repair_plan(
        touchability_preflight=_touchability_preflight(
            authority_overrides={"probe_authority_granted": True}
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["source_touchability_preflight"]["authority_preserved"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_truthy_nested_authority_grant_in_touchability_preflight_is_rejected() -> None:
    touchability = _touchability_preflight()
    touchability["placement_requirements"]["nested_authority"] = {
        "order_authority_granted": "1"
    }

    packet = build_bounded_demo_probe_placement_repair_plan(
        touchability_preflight=touchability,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["source_touchability_preflight"]["authority_preserved"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_broad_runtime_authority_grant_in_touchability_preflight_is_rejected() -> None:
    touchability = _touchability_preflight()
    touchability["bounded_probe_design"]["active_runtime_order_authority"] = True

    packet = build_bounded_demo_probe_placement_repair_plan(
        touchability_preflight=touchability,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["source_touchability_preflight"]["authority_preserved"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_known_authority_and_mutation_aliases_in_touchability_are_rejected() -> None:
    forbidden_keys = (
        "runtime_order_authority_granted",
        "runtime_order_authority_found",
        "allowed_to_submit_order_in_current_review",
        "actual_runtime_admission_enablement_ready",
        "order_authority_granted_in_authorization_object",
        "config_mutation_performed",
        "env_mutation_performed",
        "environment_mutation_performed",
        "order_modify_performed",
        "review_grants_runtime_authority",
        "cost_gate_mutation_found",
    )

    for key in forbidden_keys:
        touchability = _touchability_preflight(
            status="FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED",
            order_status="FILL_FLOW_PRESENT",
            deep_no_touch=0,
        )
        touchability["placement_requirements"]["nested_review_packet"] = {key: "true"}

        packet = build_bounded_demo_probe_placement_repair_plan(
            touchability_preflight=touchability,
            now_utc=NOW,
        )

        assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION", key
        assert packet["source_touchability_preflight"]["authority_preserved"] is False


def test_authority_enum_and_object_payloads_in_touchability_are_rejected() -> None:
    contaminations = (
        ("runtime_order_authority_granted", "ORDER_AUTHORITY_GRANTED"),
        ("order_authority", "DEMO_LEARNING_PROBE_GRANTED"),
        ("execution_authority", "ORDER_AUTHORITY_GRANTED"),
        ("order_authority_granted", {"status": "granted"}),
        ("config_mutation_performed", {"status": "performed"}),
    )

    for key, value in contaminations:
        touchability = _touchability_preflight(
            status="FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED",
            order_status="FILL_FLOW_PRESENT",
            deep_no_touch=0,
        )
        touchability["placement_requirements"]["nested_review_packet"] = {key: value}

        packet = build_bounded_demo_probe_placement_repair_plan(
            touchability_preflight=touchability,
            now_utc=NOW,
        )

        assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION", key
        assert packet["source_touchability_preflight"]["authority_preserved"] is False


def test_fill_flow_present_routes_to_touchability_review_without_repair_plan() -> None:
    packet = build_bounded_demo_probe_placement_repair_plan(
        touchability_preflight=_touchability_preflight(
            status="TOUCHABILITY_GATE_READY_FOR_OPERATOR_REVIEW",
            order_status="FILL_FLOW_PRESENT",
            fill_rows=2,
            deep_no_touch=0,
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "PLACEMENT_REPAIR_NOT_REQUIRED_TOUCHABILITY_REVIEW_READY"
    assert packet["answers"]["placement_repair_plan_ready_for_operator_review"] is False
    assert packet["answers"]["promotion_evidence"] is False
    assert packet["next_actions"] == [
        "review_fill_quality_and_edge_capture_before_placement_repair"
    ]
