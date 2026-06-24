from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.bounded_probe_shadow_placement_impact import (
    SHADOW_PLACEMENT_IMPACT_SCHEMA_VERSION,
    build_bounded_demo_probe_shadow_placement_impact,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 22, 15, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "ma_crossover|BTCUSDT|Sell"


def _placement_plan(
    *,
    status: str = "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW",
    authority_overrides: dict[str, object] | None = None,
) -> dict:
    answers = {
        "placement_repair_plan_ready_for_operator_review": (
            status == "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
        ),
        "near_touch_or_skip_required": True,
        "runtime_mutation_performed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }
    if authority_overrides:
        answers.update(authority_overrides)
    return {
        "schema_version": "bounded_demo_probe_placement_repair_plan_v1",
        "generated_at_utc": "2026-06-22T14:55:00+00:00",
        "status": status,
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 240,
        },
        "placement_repair_plan": {
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
            "authority_boundary": {
                "global_cost_gate_lowering_recommended": False,
                "main_cost_gate_adjustment": "NONE",
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        },
        "answers": answers,
    }


def _authority_readiness(
    *,
    status: str = "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
    answers_overrides: dict[str, object] | None = None,
) -> dict:
    answers = {
        "placement_repair_plan_ready": True,
        "source_scan_complete": True,
        "existing_authority_seams_present": True,
        "rust_near_touch_authority_adapter_present": True,
        "rust_authority_path_wiring_present": True,
        "rust_patch_required": False,
        "runtime_mutation_performed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }
    if answers_overrides:
        answers.update(answers_overrides)
    return {
        "schema_version": "bounded_demo_probe_authority_patch_readiness_v1",
        "generated_at_utc": "2026-06-22T14:57:00+00:00",
        "status": status,
        "reason": "source_contains_required_near_touch_authority_adapter_and_evidence_hooks",
        "next_actions": [
            "operator_review_static_patch_readiness_before_demo_authorization",
            "run_bounded_demo_probe_only_after_separate_authorization",
        ],
        "answers": answers,
    }


def _order(
    *,
    order_id: str = "oc_1",
    strategy_name: str = "flash_dip_buy",
    symbol: str = "BNBUSDT",
    side: str = "Buy",
    effective_limit_price: float = 499.545,
    placement_best_bid: float = 580.7,
    placement_best_ask: float = 584.1,
    future_min_best_ask: float = 583.7,
    future_max_best_bid: float = 584.7,
    original_gap: float = 1441.7507,
) -> dict:
    return {
        "order_id": order_id,
        "intent_id": f"intent-{order_id}",
        "order_ts": "2026-06-22T14:00:00+00:00",
        "strategy_name": strategy_name,
        "symbol": symbol,
        "side": side,
        "time_in_force": "PostOnly",
        "effective_limit_price": effective_limit_price,
        "placement_bbo_ts": "2026-06-22T14:00:00+00:00",
        "placement_best_bid": placement_best_bid,
        "placement_best_ask": placement_best_ask,
        "min_best_ask": future_min_best_ask,
        "max_best_bid": future_max_best_bid,
        "classification": {
            "status": "WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH",
            "best_touch_gap_bps": original_gap,
        },
    }


def _order_audit(*orders: dict) -> dict:
    return {
        "schema_version": "demo_order_to_fill_gap_audit_v1",
        "generated_at_utc": "2026-06-22T14:56:00+00:00",
        "summary": {
            "status": "PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH",
            "counts": {
                "reviewed_orders": len(orders),
                "fill_rows": 0,
                "deep_passive_no_touch_orders": len(orders),
            },
        },
        "orders": list(orders),
    }


def test_shadow_near_touch_improves_current_sample_but_marks_mismatch() -> None:
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_order_audit(_order(), _order(order_id="oc_2")),
        placement_repair_plan=_placement_plan(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)
    summary = packet["shadow_summary"]

    assert packet["schema_version"] == SHADOW_PLACEMENT_IMPACT_SCHEMA_VERSION
    assert packet["status"] == "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH"
    assert summary["reviewed_order_count"] == 2
    assert summary["shadow_submit_count"] == 2
    assert summary["candidate_matched_order_count"] == 0
    assert summary["max_shadow_initial_touch_gap_bps"] <= 75.0
    assert summary["max_gap_reduction_bps"] > 1300.0
    assert packet["answers"]["shadow_placement_improves_touchability"] is True
    assert packet["answers"]["candidate_specific_alpha_proof"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH" in markdown


def test_ready_authority_path_moves_mismatch_to_candidate_matched_evidence() -> None:
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_order_audit(_order(), _order(order_id="oc_2")),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_authority_readiness(),
        now_utc=NOW,
    )

    assert packet["status"] == "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH"
    assert packet["source_status"]["authority_path_ready_for_operator_review"] is True
    assert (
        "operator_review_mechanical_touchability_before_rust_patch"
        not in packet["next_actions"]
    )
    assert packet["next_actions"] == [
        "collect_candidate_matched_bounded_demo_probe_evidence_after_exact_authorization",
        "rerun_shadow_placement_after_candidate_matched_flow",
    ]
    assert packet["answers"]["order_authority_granted"] is False


def test_candidate_matched_sell_sample_can_be_effective() -> None:
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_order_audit(
            _order(
                strategy_name="ma_crossover",
                symbol="BTCUSDT",
                side="Sell",
                effective_limit_price=120.0,
                placement_best_bid=100.0,
                placement_best_ask=100.5,
                future_min_best_ask=99.5,
                future_max_best_bid=101.0,
                original_gap=1900.0,
            )
        ),
        placement_repair_plan=_placement_plan(),
        now_utc=NOW,
    )
    order = packet["shadow_orders"][0]

    assert packet["status"] == "SHADOW_PLACEMENT_TOUCHABILITY_REPAIR_EFFECTIVE_FOR_MATCHED_SAMPLE"
    assert packet["shadow_summary"]["candidate_matched_order_count"] == 1
    assert packet["shadow_summary"]["candidate_matched_submit_count"] == 1
    assert order["shadow_limit_price"] == 100.5
    assert order["shadow_initial_touch_gap_bps"] == 50.0
    assert order["future_bbo_would_cross_shadow_limit"] is True


def test_ready_authority_path_moves_matched_sample_to_exact_authorization() -> None:
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_order_audit(
            _order(
                strategy_name="ma_crossover",
                symbol="BTCUSDT",
                side="Sell",
                effective_limit_price=120.0,
                placement_best_bid=100.0,
                placement_best_ask=100.5,
                future_min_best_ask=99.5,
                future_max_best_bid=101.0,
                original_gap=1900.0,
            )
        ),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_authority_readiness(),
        now_utc=NOW,
    )

    assert packet["status"] == "SHADOW_PLACEMENT_TOUCHABILITY_REPAIR_EFFECTIVE_FOR_MATCHED_SAMPLE"
    assert (
        "operator_review_existing_rust_authority_path_patch"
        not in packet["next_actions"]
    )
    assert packet["next_actions"] == [
        "obtain_exact_bounded_demo_authorization_before_probe",
        "refresh_order_to_fill_and_execution_realism_artifacts_after_probe",
    ]
    assert packet["answers"]["probe_authority_granted"] is False


def test_readiness_answer_contradiction_is_not_treated_as_ready() -> None:
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_order_audit(_order(), _order(order_id="oc_2")),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_authority_readiness(
            answers_overrides={"source_scan_complete": False}
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH"
    assert packet["source_status"]["authority_path_ready_for_operator_review"] is False
    assert packet["next_actions"] == [
        "operator_review_mechanical_touchability_before_rust_patch",
        "collect_candidate_matched_bounded_demo_probe_evidence_after_authorization",
    ]
    assert packet["answers"]["order_authority_granted"] is False


def test_missing_placement_plan_fails_closed() -> None:
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_order_audit(_order()),
        placement_repair_plan=None,
        now_utc=NOW,
    )

    assert packet["status"] == "PLACEMENT_REPAIR_PLAN_REQUIRED"
    assert packet["artifacts"]["placement_repair_plan"]["status"] == "MISSING"
    assert packet["answers"]["shadow_placement_improves_touchability"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_missing_order_audit_fails_closed() -> None:
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=None,
        placement_repair_plan=_placement_plan(),
        now_utc=NOW,
    )

    assert packet["status"] == "ORDER_TOUCHABILITY_AUDIT_REQUIRED"
    assert packet["artifacts"]["demo_order_to_fill_gap_audit"]["status"] == "MISSING"
    assert packet["shadow_summary"]["reviewed_order_count"] == 0


def test_wide_spread_would_skip_all_orders() -> None:
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_order_audit(
            _order(placement_best_bid=100.0, placement_best_ask=103.0)
        ),
        placement_repair_plan=_placement_plan(),
        now_utc=NOW,
    )

    assert packet["status"] == "SHADOW_PLACEMENT_REPAIR_WOULD_SKIP_ALL_ORDERS"
    assert packet["shadow_summary"]["shadow_submit_count"] == 0
    assert packet["shadow_orders"][0]["status"] == "WOULD_SKIP_GAP_TOO_WIDE"


def test_authority_grant_in_placement_plan_is_rejected() -> None:
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_order_audit(_order()),
        placement_repair_plan=_placement_plan(
            authority_overrides={"order_authority_granted": True}
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["source_status"]["authority_preserved"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_authority_grant_in_patch_readiness_is_rejected() -> None:
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_order_audit(_order()),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_authority_readiness(
            answers_overrides={"probe_authority_granted": True}
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["source_status"]["authority_patch_preserved"] is False
    assert packet["answers"]["probe_authority_granted"] is False


def test_nested_authority_grant_in_patch_readiness_is_rejected() -> None:
    readiness = _authority_readiness()
    readiness["source_readiness"] = {
        "checks": [
            {
                "check_id": "contaminated",
                "active_runtime_order_authority": True,
            }
        ]
    }
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_order_audit(_order()),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=readiness,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["source_status"]["authority_patch_preserved"] is False
    assert packet["source_status"]["authority_path_ready_for_operator_review"] is False
    assert packet["answers"]["order_authority_granted"] is False
