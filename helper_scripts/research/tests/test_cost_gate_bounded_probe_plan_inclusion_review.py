from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.bounded_probe_plan_inclusion_review import (
    READY_STATUS,
    build_plan_inclusion_review,
)
from cost_gate_learning_lane.contract import (
    ADMIT_DECISION,
    BOUNDED_PROBE_AUTHORIZED_STATUS,
    BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    ORDER_AUTHORITY_GRANTED,
)


NOW = dt.datetime(2026, 6, 24, 21, 10, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


def _contains_true_key(value, key: str) -> bool:
    if isinstance(value, dict):
        return any(
            (k == key and v is True) or _contains_true_key(v, key)
            for k, v in value.items()
        )
    if isinstance(value, list):
        return any(_contains_true_key(item, key) for item in value)
    return False


def _candidate(**overrides) -> dict:
    candidate = {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
        "source_kind": "cost_gate_false_negative_after_cost",
    }
    candidate.update(overrides)
    return candidate


def _preflight(**overrides) -> dict:
    candidate = _candidate()
    payload = {
        "schema_version": "cost_gate_false_negative_bounded_demo_probe_preflight_v1",
        "generated_at_utc": "2026-06-24T21:00:00+00:00",
        "status": "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
        "candidate": candidate,
        "bounded_demo_probe_design": {
            "schema_version": "bounded_demo_probe_design_v1",
            "status": "READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION",
            "candidate": candidate,
            "suggested_initial_probe_limits": {
                "active": False,
                "requires_separate_operator_authorization": True,
                "max_probe_intents_before_review": 3,
                "max_demo_notional_usdt_per_order": 10,
                "max_total_demo_notional_usdt_before_review": 30,
            },
            "stop_conditions": ["operator_review_missing_or_expired"],
        },
        "answers": {
            "ready_for_operator_bounded_demo_probe_authorization": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "order_submission_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _construction_preview(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_candidate_construction_preview_v1",
        "generated_at_utc": "2026-06-24T21:01:00+00:00",
        "status": "CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER",
        "candidate": _candidate(),
        "blocking_gates": [],
        "construction": {
            "constructible": True,
            "limit_price": 6.359,
            "rounded_qty": 1.5,
            "rounded_notional_usdt": 9.5385,
            "cap_usdt": 10.0,
            "placement_mode": "sell_near_touch_post_only_at_or_above_best_ask",
        },
        "answers": {
            "candidate_construction_preview_ready_no_order": True,
            "canonical_plan_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "ledger_append_performed": False,
            "live_authority_granted": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "order_submission_performed": False,
            "pg_write_performed": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
            "runtime_mutation_performed": False,
            "writer_enabled": False,
        },
    }
    payload.update(overrides)
    return payload


def _authorization_packet(**overrides) -> dict:
    candidate = _candidate(source_kind=None)
    auth = {
        "schema_version": BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
        "status": BOUNDED_PROBE_AUTHORIZED_STATUS,
        "authorization_id": "standing-demo-avax-sell-test",
        "operator_id": "codex-standing-demo-operator",
        "side_cell_key": SIDE_CELL,
        "expires_at_utc": "2026-06-24T23:00:00+00:00",
        "authority_path_readiness_status": "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
        "main_cost_gate_adjustment": "NONE",
        "order_authority": ORDER_AUTHORITY_GRANTED,
        "max_authorized_probe_orders": 1,
        "probe_authority_granted": True,
        "order_authority_granted": True,
        "promotion_evidence": False,
    }
    payload = {
        "schema_version": "bounded_demo_probe_operator_authorization_packet_v1",
        "generated_at_utc": "2026-06-24T21:02:00+00:00",
        "status": BOUNDED_PROBE_AUTHORIZED_STATUS,
        "decision": "authorize",
        "candidate": candidate,
        "operator_authorization": auth,
        "answers": {
            "operator_authorization_object_emitted": True,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "plan_mutation_performed": False,
            "writer_enabled": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
            "probe_authority_granted_in_authorization_object": True,
            "order_authority_granted_in_authorization_object": True,
        },
    }
    payload.update(overrides)
    return payload


def test_builds_inactive_plan_preview_and_blocks_on_adapter_disabled() -> None:
    review = build_plan_inclusion_review(
        preflight=_preflight(),
        construction_preview=_construction_preview(),
        authorization_packet=_authorization_packet(),
        now_utc=NOW,
    )

    assert review["status"] == READY_STATUS
    assert review["answers"]["active_runtime_order_authority"] is False
    assert review["answers"]["plan_mutation_performed"] is False
    assert review["plan_preview"]["order_authority"] == ORDER_AUTHORITY_GRANTED
    assert review["plan_preview"]["operator_authorization"]["side_cell_key"] == SIDE_CELL
    assert review["plan_preview"]["probe_candidates"][0]["probe_proposal"]["max_probe_orders"] == 1
    assert review["inactive_adapter_decision"]["decision"] == "ADAPTER_DISABLED"
    assert review["inactive_adapter_decision"]["allowed_to_submit_order"] is False
    assert review["hypothetical_adapter_enabled_decision"]["decision"] == ADMIT_DECISION
    assert (
        review["hypothetical_adapter_enabled_decision"][
            "would_admit_if_adapter_enabled"
        ]
        is True
    )
    assert (
        review["hypothetical_adapter_enabled_decision"][
            "allowed_to_submit_order_in_current_review"
        ]
        is False
    )
    assert review["hypothetical_only"] is True
    assert not _contains_true_key(review, "allowed_to_submit_order")


def test_candidate_mismatch_fails_closed() -> None:
    preview = _construction_preview(
        candidate=_candidate(side_cell_key="grid_trading|ETHUSDT|Buy", symbol="ETHUSDT", side="Buy")
    )
    review = build_plan_inclusion_review(
        preflight=_preflight(),
        construction_preview=preview,
        authorization_packet=_authorization_packet(),
        now_utc=NOW,
    )

    assert review["status"] == "CANDIDATE_ALIGNMENT_MISMATCH"
    assert review["plan_preview"] is None
    assert review["answers"]["active_runtime_order_authority"] is False


def test_expired_authorization_fails_before_plan_preview() -> None:
    packet = _authorization_packet()
    packet["operator_authorization"]["expires_at_utc"] = "2026-06-24T20:00:00+00:00"
    review = build_plan_inclusion_review(
        preflight=_preflight(),
        construction_preview=_construction_preview(),
        authorization_packet=packet,
        now_utc=NOW,
    )

    assert review["status"] == "AUTHORIZATION_PACKET_NOT_READY"
    assert review["authorization_packet_validation_reason"] == "operator_authorization_expired"
    assert review["plan_preview"] is None


def test_mutating_preflight_fails_closed() -> None:
    preflight = _preflight()
    preflight["answers"]["order_submission_performed"] = True
    review = build_plan_inclusion_review(
        preflight=preflight,
        construction_preview=_construction_preview(),
        authorization_packet=_authorization_packet(),
        now_utc=NOW,
    )

    assert review["status"] == "PREFLIGHT_NOT_READY"
    assert review["answers"]["order_submission_performed"] is False


def test_hidden_allowed_to_submit_order_in_input_fails_closed() -> None:
    preflight = _preflight()
    preflight["nested"] = {"allowed_to_submit_order": True}
    review = build_plan_inclusion_review(
        preflight=preflight,
        construction_preview=_construction_preview(),
        authorization_packet=_authorization_packet(),
        now_utc=NOW,
    )

    assert review["status"] == "PREFLIGHT_NOT_READY"
    assert review["plan_preview"] is None


def test_hidden_authority_in_auth_packet_fails_closed_outside_auth_object() -> None:
    packet = _authorization_packet()
    packet["nested"] = {"active_runtime_order_authority": True}
    review = build_plan_inclusion_review(
        preflight=_preflight(),
        construction_preview=_construction_preview(),
        authorization_packet=packet,
        now_utc=NOW,
    )

    assert review["status"] == "AUTHORIZATION_PACKET_NOT_READY"
    assert review["authorization_packet_validation_reason"].startswith(
        "authorization_packet_hidden_authority_violation"
    )
    assert review["plan_preview"] is None
