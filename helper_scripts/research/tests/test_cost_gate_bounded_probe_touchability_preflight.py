from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.bounded_probe_touchability_preflight import (
    TOUCHABILITY_PREFLIGHT_SCHEMA_VERSION,
    build_bounded_demo_probe_touchability_preflight,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 22, 13, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "ma_crossover|BTCUSDT|Sell"


def _preflight(**answer_overrides: object) -> dict:
    answers = {
        "sealed_horizon_evidence_ready": True,
        "decision_packet_aligned": True,
        "operator_review_recorded": True,
        "production_learning_lane_accumulating": True,
        "ready_for_operator_bounded_demo_probe_authorization": False,
        "bounded_demo_probe_design_ready_for_operator_review": True,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }
    answers.update(answer_overrides)
    return {
        "schema_version": "sealed_horizon_bounded_demo_probe_preflight_v1",
        "generated_at_utc": "2026-06-22T12:55:00+00:00",
        "status": "READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION",
        "side_cell_key": SIDE_CELL,
        "outcome_horizon_minutes": 240,
        "answers": answers,
        "bounded_demo_probe_design": {
            "schema_version": "bounded_demo_probe_design_v1",
            "status": "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN",
            "candidate": {
                "side_cell_key": SIDE_CELL,
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 240,
                "source_kind": "horizon_specific_sealed_replay",
            },
            "suggested_initial_probe_limits": {
                "active": False,
                "requires_separate_operator_authorization": True,
                "max_probe_intents_before_review": 3,
                "max_demo_notional_usdt_per_order": 10,
            },
            "authority_boundary": {
                "global_cost_gate_lowering_recommended": False,
                "main_cost_gate_adjustment": "NONE",
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        },
    }


def _order_touchability_audit(
    *,
    status: str = "PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH",
    fill_rows: int = 0,
    deep_no_touch: int = 6,
    touched_no_fill: int = 0,
    no_bbo: int = 0,
    answers: dict[str, object] | None = None,
    orders: list[dict[str, object]] | None = None,
) -> dict:
    merged_answers = {
        "orders_present": True,
        "fills_present": fill_rows > 0,
        "passive_limits_too_deep": deep_no_touch > 0,
        "bbo_touched_without_fill": touched_no_fill > 0,
        "global_cost_gate_lowering_recommended": False,
        "order_authority_granted": False,
        "probe_authority_granted": False,
        "promotion_evidence": False,
    }
    if answers:
        merged_answers.update(answers)
    return {
        "schema_version": "demo_order_to_fill_gap_audit_v1",
        "generated_at_utc": "2026-06-22T12:58:00+00:00",
        "summary": {
            "status": status,
            "reason": "synthetic_touchability_fixture",
            "next_action": "synthetic_next_action",
            "counts": {
                "reviewed_orders": 6,
                "fill_rows": fill_rows,
                "post_only_orders": 6,
                "orders_price_missing": 6,
                "effective_limit_prices_inferred": 6,
                "bbo_touched_no_fill_orders": touched_no_fill,
                "deep_passive_no_touch_orders": deep_no_touch,
                "no_bbo_coverage_orders": no_bbo,
            },
            "answers": merged_answers,
        },
        "orders": orders
        if orders is not None
        else [
            {
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "fill_count": 0,
                "classification": {
                    "status": "DAY_TIMEOUT_SELF_CANCEL_NO_TOUCH_DEEP_LIMIT",
                    "best_touch_gap_bps": 1530.6074,
                }
            },
            {
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "fill_count": 0,
                "classification": {
                    "status": "WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH",
                    "best_touch_gap_bps": 1156.4221,
                }
            },
        ],
    }


def test_deep_no_touch_audit_blocks_bounded_probe_until_placement_repair() -> None:
    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=_preflight(),
        order_to_fill_gap_audit=_order_touchability_audit(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == TOUCHABILITY_PREFLIGHT_SCHEMA_VERSION
    assert packet["status"] == "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE"
    assert packet["answers"]["touchability_repair_required"] is True
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["placement_requirements"]["active"] is False
    assert packet["placement_requirements"]["requires_separate_operator_authorization"] is True
    assert packet["placement_requirements"]["max_initial_passive_gap_bps"] == 75.0
    assert (
        packet["placement_requirements"]["if_gap_exceeds_limit"]
        == "skip_probe_order_and_record_touchability_block"
    )
    assert packet["placement_requirements"]["latest_runtime_max_best_touch_gap_bps"] == 1530.6074
    assert packet["order_touchability"]["deep_passive_no_touch_orders"] == 6
    assert packet["next_actions"] == [
        "revise_bounded_demo_probe_design_with_near_touch_or_skip_if_not_touchable_rules",
        "rerun_order_to_fill_touchability_audit_after_design_repair",
    ]
    assert "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE" in markdown


def test_touched_bbo_without_fill_requires_fill_path_reconcile_first() -> None:
    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=_preflight(),
        order_to_fill_gap_audit=_order_touchability_audit(
            status="BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED",
            deep_no_touch=0,
            touched_no_fill=1,
            answers={
                "passive_limits_too_deep": False,
                "bbo_touched_without_fill": True,
            },
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "FILL_PATH_RECONCILE_REQUIRED"
    assert packet["reason"] == "BBO_touched_one_or_more_orders_but_no_fill_was_recorded"
    assert packet["answers"]["touchability_repair_required"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_missing_order_touchability_audit_fails_closed() -> None:
    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=_preflight(),
        order_to_fill_gap_audit=None,
        now_utc=NOW,
    )

    assert packet["status"] == "ORDER_TOUCHABILITY_AUDIT_REQUIRED"
    assert packet["artifacts"]["demo_order_to_fill_gap_audit"]["status"] == "MISSING"
    assert packet["answers"]["order_touchability_audit_fresh"] is False


def test_authority_grant_in_input_is_rejected_before_reviewability_checks() -> None:
    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=_preflight(probe_authority_granted=True),
        order_to_fill_gap_audit=_order_touchability_audit(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["bounded_probe_design"]["authority_preserved"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_truthy_nested_authority_grant_in_input_is_rejected() -> None:
    preflight = _preflight()
    preflight["bounded_demo_probe_design"]["authority_boundary"][
        "probe_authority_granted"
    ] = "true"

    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=preflight,
        order_to_fill_gap_audit=_order_touchability_audit(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["bounded_probe_design"]["authority_preserved"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_broad_runtime_authority_grant_in_input_is_rejected() -> None:
    preflight = _preflight()
    preflight["bounded_demo_probe_design"]["authority_boundary"][
        "active_runtime_order_authority"
    ] = True

    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=preflight,
        order_to_fill_gap_audit=_order_touchability_audit(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["bounded_probe_design"]["authority_preserved"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_known_authority_and_mutation_aliases_are_rejected_recursively() -> None:
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
        preflight = _preflight()
        preflight["bounded_demo_probe_design"]["authority_boundary"][
            "nested_review_packet"
        ] = {key: "true"}

        packet = build_bounded_demo_probe_touchability_preflight(
            preflight=preflight,
            order_to_fill_gap_audit=_order_touchability_audit(),
            now_utc=NOW,
        )

        assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION", key
        assert packet["bounded_probe_design"]["authority_preserved"] is False


def test_authority_enum_and_object_payloads_are_rejected() -> None:
    contaminations = (
        ("runtime_order_authority_granted", "ORDER_AUTHORITY_GRANTED"),
        ("order_authority", "DEMO_LEARNING_PROBE_GRANTED"),
        ("execution_authority", "ORDER_AUTHORITY_GRANTED"),
        ("order_authority_granted", {"status": "granted"}),
        ("config_mutation_performed", {"status": "performed"}),
    )

    for key, value in contaminations:
        preflight = _preflight()
        preflight["bounded_demo_probe_design"]["authority_boundary"][
            "nested_review_packet"
        ] = {key: value}

        packet = build_bounded_demo_probe_touchability_preflight(
            preflight=preflight,
            order_to_fill_gap_audit=_order_touchability_audit(),
            now_utc=NOW,
        )

        assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION", key
        assert packet["bounded_probe_design"]["authority_preserved"] is False


def test_promotion_proof_in_input_is_rejected_before_touchability_ready() -> None:
    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=_preflight(promotion_proof=True),
        order_to_fill_gap_audit=_order_touchability_audit(
            status="FILL_FLOW_PRESENT",
            fill_rows=1,
            deep_no_touch=0,
            answers={
                "fills_present": True,
                "passive_limits_too_deep": False,
            },
            orders=[
                {
                    "strategy_name": "ma_crossover",
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "fill_count": 1,
                    "classification": {"status": "FILLED"},
                }
            ],
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["bounded_probe_design"]["authority_preserved"] is False
    assert packet["answers"]["ready_for_operator_touchability_review"] is False
    assert packet["answers"]["promotion_evidence"] is False


def test_fill_flow_present_is_ready_only_for_operator_touchability_review() -> None:
    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=_preflight(),
        order_to_fill_gap_audit=_order_touchability_audit(
            status="FILL_FLOW_PRESENT",
            fill_rows=2,
            deep_no_touch=0,
            answers={
                "fills_present": True,
                "passive_limits_too_deep": False,
            },
            orders=[
                {
                    "strategy_name": "ma_crossover",
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "fill_count": 2,
                    "classification": {"status": "FILLED"},
                }
            ],
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "TOUCHABILITY_GATE_READY_FOR_OPERATOR_REVIEW"
    assert packet["reason"] == "candidate_matched_fill_flow_exists_for_reviewed_Demo_orders"
    assert packet["answers"]["ready_for_operator_touchability_review"] is True
    assert packet["answers"]["candidate_matched_fill_flow_present"] is True
    assert packet["answers"]["promotion_evidence"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert packet["next_actions"] == [
        "review_candidate_matched_fill_quality_and_edge_capture_before_any_probe_authorization"
    ]


def test_candidate_strategy_name_is_required_for_fill_flow_readiness() -> None:
    preflight = _preflight()
    preflight["bounded_demo_probe_design"]["candidate"].pop("strategy_name")

    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=preflight,
        order_to_fill_gap_audit=_order_touchability_audit(
            status="FILL_FLOW_PRESENT",
            fill_rows=1,
            deep_no_touch=0,
            answers={
                "fills_present": True,
                "passive_limits_too_deep": False,
            },
            orders=[
                {
                    "strategy_name": "flash_dip_buy",
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "fill_count": 1,
                    "classification": {"status": "FILLED"},
                }
            ],
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "BOUNDED_PROBE_DESIGN_NOT_READY"
    assert packet["bounded_probe_design"]["candidate_identity_aligned"] is False
    assert packet["answers"]["bounded_probe_design_reviewable"] is False
    assert packet["answers"]["ready_for_operator_touchability_review"] is False
    assert packet["answers"]["candidate_matched_fill_flow_present"] is False
    assert packet["order_touchability"]["candidate_reviewed_orders"] == 0
    assert packet["order_touchability"]["candidate_fill_rows"] == 0


def test_same_symbol_side_wrong_strategy_fill_does_not_satisfy_candidate() -> None:
    preflight = _preflight()
    preflight["bounded_demo_probe_design"]["candidate"] = {
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
        "source_kind": "cost_gate_false_negative_after_cost",
    }

    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=preflight,
        order_to_fill_gap_audit=_order_touchability_audit(
            status="FILL_FLOW_PRESENT",
            fill_rows=1,
            deep_no_touch=0,
            answers={
                "fills_present": True,
                "passive_limits_too_deep": False,
            },
            orders=[
                {
                    "strategy_name": "flash_dip_buy",
                    "symbol": "AVAXUSDT",
                    "side": "Sell",
                    "fill_count": 1,
                    "classification": {"status": "FILLED"},
                }
            ],
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED"
    assert (
        packet["reason"]
        == "no_candidate_matched_orders_exist_for_first_touchability_attempt"
    )
    assert packet["answers"]["ready_for_operator_touchability_review"] is False
    assert packet["answers"]["first_attempt_touchability_bootstrap_required"] is True
    assert packet["answers"]["candidate_matched_fill_flow_present"] is False
    assert packet["placement_requirements"]["first_attempt_bootstrap"] is True
    assert packet["placement_requirements"]["first_attempt_bootstrap_is_proof"] is False
    assert packet["order_touchability"]["candidate_reviewed_orders"] == 0
    assert packet["order_touchability"]["candidate_fill_rows"] == 0
    assert packet["order_touchability"]["non_candidate_fill_rows"] == 1


def test_candidate_multi_fill_count_does_not_create_non_candidate_fill() -> None:
    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=_preflight(),
        order_to_fill_gap_audit=_order_touchability_audit(
            status="FILL_FLOW_PRESENT",
            fill_rows=2,
            deep_no_touch=0,
            answers={
                "fills_present": True,
                "passive_limits_too_deep": False,
            },
            orders=[
                {
                    "strategy_name": "ma_crossover",
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "fill_count": 2,
                    "classification": {"status": "FILLED"},
                }
            ],
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "TOUCHABILITY_GATE_READY_FOR_OPERATOR_REVIEW"
    assert packet["order_touchability"]["candidate_fill_rows"] == 2
    assert packet["order_touchability"]["non_candidate_fill_rows"] == 0


def test_non_candidate_fill_flow_does_not_satisfy_candidate_touchability() -> None:
    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=_preflight(),
        order_to_fill_gap_audit=_order_touchability_audit(
            status="FILL_FLOW_PRESENT",
            fill_rows=1,
            deep_no_touch=1,
            answers={
                "fills_present": True,
                "passive_limits_too_deep": True,
            },
            orders=[
                {
                    "strategy_name": "flash_dip_buy",
                    "symbol": "XRPUSDT",
                    "side": "Buy",
                    "fill_count": 1,
                    "classification": {"status": "FILLED"},
                },
                {
                    "strategy_name": "flash_dip_buy",
                    "symbol": "AVAXUSDT",
                    "side": "Buy",
                    "fill_count": 0,
                    "classification": {
                        "status": "WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH",
                        "best_touch_gap_bps": 1668.3432,
                    },
                },
            ],
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE"
    assert packet["reason"] == "non_candidate_fill_flow_cannot_satisfy_bounded_probe_touchability"
    assert packet["answers"]["ready_for_operator_touchability_review"] is False
    assert packet["answers"]["candidate_touchability_orders_present"] is False
    assert packet["answers"]["candidate_matched_fill_flow_present"] is False
    assert packet["order_touchability"]["candidate_fill_rows"] == 0
    assert packet["order_touchability"]["non_candidate_fill_rows"] == 1
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_non_reviewable_bounded_probe_design_fails_closed() -> None:
    preflight = _preflight()
    preflight["bounded_demo_probe_design"]["status"] = "OPERATOR_REVIEW_REQUIRED"

    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=preflight,
        order_to_fill_gap_audit=_order_touchability_audit(),
        now_utc=NOW,
    )

    assert packet["status"] == "BOUNDED_PROBE_DESIGN_NOT_READY"
    assert packet["answers"]["bounded_probe_design_reviewable"] is False


def test_false_negative_preflight_schema_is_reviewable_for_touchability() -> None:
    preflight = _preflight()
    preflight["schema_version"] = (
        "cost_gate_false_negative_bounded_demo_probe_preflight_v1"
    )
    preflight["bounded_demo_probe_design"]["candidate"] = {
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
        "source_kind": "cost_gate_false_negative_after_cost",
    }

    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=preflight,
        order_to_fill_gap_audit=_order_touchability_audit(
            status="FILL_FLOW_PRESENT",
            fill_rows=1,
            deep_no_touch=1,
            answers={
                "fills_present": True,
                "passive_limits_too_deep": True,
            },
            orders=[
                {
                    "strategy_name": "risk_close",
                    "symbol": "SOLUSDT",
                    "side": "Sell",
                    "fill_count": 1,
                    "classification": {"status": "FILLED"},
                },
                {
                    "strategy_name": "flash_dip_buy",
                    "symbol": "AVAXUSDT",
                    "side": "Buy",
                    "fill_count": 0,
                    "classification": {
                        "status": "WORKING_DEEP_PASSIVE_LIMIT_NO_TOUCH",
                        "best_touch_gap_bps": 1668.3432,
                    },
                },
            ],
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE"
    assert packet["reason"] == "non_candidate_fill_flow_cannot_satisfy_bounded_probe_touchability"
    assert packet["bounded_probe_design"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["order_touchability"]["candidate_reviewed_orders"] == 0
    assert packet["order_touchability"]["candidate_fill_rows"] == 0
    assert packet["answers"]["candidate_matched_fill_flow_present"] is False
    assert packet["answers"]["probe_authority_granted"] is False


def test_zero_candidate_orders_with_non_candidate_fill_enables_first_attempt_bootstrap_only() -> None:
    preflight = _preflight()
    preflight["bounded_demo_probe_design"]["candidate"] = {
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
        "source_kind": "cost_gate_false_negative_after_cost",
    }

    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=preflight,
        order_to_fill_gap_audit=_order_touchability_audit(
            status="FILL_FLOW_PRESENT",
            fill_rows=1,
            deep_no_touch=0,
            answers={
                "fills_present": True,
                "passive_limits_too_deep": False,
            },
            orders=[
                {
                    "strategy_name": "risk_close",
                    "symbol": "AVAXUSDT",
                    "side": "Sell",
                    "fill_count": 1,
                    "classification": {"status": "FILLED"},
                }
            ],
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "FIRST_ATTEMPT_TOUCHABILITY_BOOTSTRAP_REQUIRED"
    assert packet["answers"]["touchability_repair_required"] is True
    assert packet["answers"]["first_attempt_touchability_bootstrap_required"] is True
    assert packet["answers"]["ready_for_operator_touchability_review"] is False
    assert packet["answers"]["candidate_touchability_orders_present"] is False
    assert packet["answers"]["candidate_matched_fill_flow_present"] is False
    assert packet["placement_requirements"]["active"] is False
    assert packet["placement_requirements"]["requires_separate_operator_authorization"] is True
    assert packet["placement_requirements"]["first_attempt_bootstrap"] is True
    assert packet["placement_requirements"]["first_attempt_bootstrap_is_proof"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["promotion_evidence"] is False


def test_inconsistent_candidate_identity_fails_closed_before_first_attempt_bootstrap() -> None:
    preflight = _preflight()
    preflight["bounded_demo_probe_design"]["candidate"] = {
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "strategy_name": "ma_crossover",
        "symbol": "BTCUSDT",
        "side": "Buy",
        "outcome_horizon_minutes": 60,
        "source_kind": "cost_gate_false_negative_after_cost",
    }

    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=preflight,
        order_to_fill_gap_audit=_order_touchability_audit(
            status="FILL_FLOW_PRESENT",
            fill_rows=1,
            deep_no_touch=0,
            answers={
                "fills_present": True,
                "passive_limits_too_deep": False,
            },
            orders=[
                {
                    "strategy_name": "risk_close",
                    "symbol": "AVAXUSDT",
                    "side": "Sell",
                    "fill_count": 1,
                    "classification": {"status": "FILLED"},
                }
            ],
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "BOUNDED_PROBE_DESIGN_NOT_READY"
    assert packet["bounded_probe_design"]["candidate_identity_aligned"] is False
    assert packet["answers"]["bounded_probe_design_reviewable"] is False
    assert packet["answers"]["first_attempt_touchability_bootstrap_required"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_candidate_order_without_fill_does_not_bootstrap_as_zero_candidate_attempt() -> None:
    preflight = _preflight()

    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=preflight,
        order_to_fill_gap_audit=_order_touchability_audit(
            status="FILL_FLOW_PRESENT",
            fill_rows=1,
            deep_no_touch=0,
            answers={
                "fills_present": True,
                "passive_limits_too_deep": False,
            },
            orders=[
                {
                    "strategy_name": "flash_dip_buy",
                    "symbol": "XRPUSDT",
                    "side": "Buy",
                    "fill_count": 1,
                    "classification": {"status": "FILLED"},
                },
                {
                    "strategy_name": "ma_crossover",
                    "symbol": "BTCUSDT",
                    "side": "Sell",
                    "fill_count": 0,
                    "classification": {"status": "OPEN_UNCLASSIFIED"},
                },
            ],
        ),
        now_utc=NOW,
    )

    assert packet["status"] == "CANDIDATE_TOUCHABILITY_DATA_REQUIRED"
    assert packet["answers"]["first_attempt_touchability_bootstrap_required"] is False
    assert packet["answers"]["candidate_touchability_orders_present"] is True
    assert packet["order_touchability"]["candidate_reviewed_orders"] == 1
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
