from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import (
    current_candidate_standing_demo_loss_control_envelope_review as mod,
)


NOW = dt.datetime(2026, 6, 27, 3, 5, tzinfo=dt.timezone.utc)
GEN = dt.datetime(2026, 6, 27, 3, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "grid_trading|AVAXUSDT|Sell"


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    payload.update(overrides)
    return payload


def _answers(**overrides) -> dict:
    payload = {
        "review_contract_ready": True,
        "runtime_admission_ready": False,
        "order_admission_ready": False,
        "active_runtime_probe_authority": False,
        "active_runtime_order_authority": False,
        "bounded_demo_probe_authorized": False,
        "operator_authorization_object_emitted": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "live_authority_granted": False,
        "promotion_evidence": False,
        "promotion_proof": False,
        "order_submission_performed": False,
        "runtime_mutation_performed": False,
        "pg_write_performed": False,
    }
    payload.update(overrides)
    return payload


def _cap_resolution(**overrides) -> dict:
    payload = {
        "account_equity_artifact_accepted": True,
        "account_equity_usdt": 9552.43426257,
        "bounded_probe_local_cap_usdt_is_authority": False,
        "cap_resolved": True,
        "gui_risk_config_is_authority": True,
        "per_trade_budget_usdt": 955.24342626,
        "per_trade_risk_pct_display": 10.0,
        "per_trade_risk_pct_fraction": 0.1,
        "position_size_max_pct": 25.0,
        "resolved_cap_usdt": 955.24342626,
        "risk_source_of_truth": "GUI-backed Rust RiskConfig",
        "single_position_budget_usdt": 2388.10856564,
    }
    payload.update(overrides)
    return payload


def _current_envelope(**overrides) -> dict:
    payload = {
        "schema_version": mod.CURRENT_ENVELOPE_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.CURRENT_ENVELOPE_READY_STATUS,
        "candidate": _candidate(),
        "cap_resolution": _cap_resolution(),
        "summary": {
            "current_candidate_no_order_refresh_envelope_ready": True,
            "resolved_cap_usdt": 955.24342626,
            "gui_p1_risk_trade_pct": 10.0,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "order_admission_ready": False,
        },
        "answers": _answers(current_candidate_no_order_refresh_envelope_ready=True),
    }
    payload.update(overrides)
    return payload


def _admission_review(**overrides) -> dict:
    payload = {
        "schema_version": mod.ADMISSION_REVIEW_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.ADMISSION_BLOCKED_STATUS,
        "candidate": _candidate(),
        "risk_semantics": {
            "gui_risk_config_is_source_of_truth": True,
            "gui_p1_risk_trade_pct": 10.0,
            "per_trade_risk_pct_fraction": 0.1,
            "position_size_max_pct": 25.0,
            "account_equity_usdt": 9552.43426257,
            "resolved_cap_usdt": 955.24342626,
            "cap_source": mod.GUI_CAP_SOURCE,
            "rounded_notional_usdt": 954.6264,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "bounded_probe_local_cap_usdt_is_authority": False,
        },
        "runtime_admission_blockers": [
            "standing_demo_authorization_valid_if_supplied",
            "bounded_demo_authorization_object_valid",
            "decision_lease_valid",
            "guardian_risk_gate_valid",
            "rust_authority_path_valid",
            "fresh_bbo_refresh_at_actual_admission",
        ],
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _candidate_row(side_cell_key=SIDE_CELL, **overrides) -> dict:
    strategy, symbol, side = side_cell_key.split("|")
    payload = {
        "side_cell_key": side_cell_key,
        "candidate_class": "false_negative_after_cost",
        "status": "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE",
        "strategy_names": [strategy],
        "symbols": [symbol],
        "sides": [side],
        "horizon_minutes": [60],
        "dominant_horizon_minutes": 60,
        "operator_review_required": True,
        "global_cost_gate_lowering_recommended": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
        "avg_net_bps": 73.5511,
        "net_cost_cushion_bps": 73.5511,
        "outcome_count": 48,
        "false_negative_rank": 2,
    }
    payload.update(overrides)
    return payload


def _false_negative_packet(**overrides) -> dict:
    payload = {
        "schema_version": mod.FALSE_NEGATIVE_CANDIDATE_PACKET_SCHEMA_VERSION,
        "generated_at_utc": GEN.isoformat(),
        "status": mod.FALSE_NEGATIVE_PACKET_READY_STATUS,
        "ranked_false_negative_candidates": [
            _candidate_row("grid_trading|ETHUSDT|Buy", false_negative_rank=1),
            _candidate_row(),
        ],
        "summary": {
            "false_negative_candidate_count": 2,
            "top_false_negative_side_cell_key": "grid_trading|ETHUSDT|Buy",
        },
        "answers": {
            "operator_review_ready": True,
            "false_negative_candidates_present": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _review(**overrides) -> dict:
    kwargs = {
        "admission_review": _admission_review(),
        "current_envelope": _current_envelope(),
        "false_negative_candidate_packet": _false_negative_packet(),
        "now_utc": NOW,
    }
    kwargs.update(overrides)
    return mod.build_current_candidate_standing_demo_loss_control_envelope_review(
        **kwargs
    )


def test_ready_review_builds_current_candidate_envelope_preview_without_runtime_mutation() -> None:
    review = _review()

    assert review["schema_version"] == mod.SCHEMA_VERSION
    assert review["status"] == mod.READY_STATUS
    assert review["blocking_gate_count"] == 0
    assert review["candidate"]["side_cell_key"] == SIDE_CELL
    assert review["summary"]["resolved_cap_usdt"] == 955.24342626
    assert review["risk_cap_lineage"]["per_trade_risk_pct_fraction"] == 0.1
    assert review["risk_cap_lineage"]["per_trade_risk_pct_display"] == 10.0
    assert review["risk_cap_lineage"]["local_10_usdt_cap_is_global_risk_authority"] is False
    envelope = review["envelope_preview"]
    assert envelope["schema_version"] == mod.STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION
    assert envelope["candidate"]["side_cell_key"] == SIDE_CELL
    assert envelope["risk_cap_lineage"]["resolved_cap_usdt"] == 955.24342626
    assert envelope["max_authorized_probe_orders_per_candidate"] == 2
    assert review["standing_demo_authorization_validation"][
        "valid_for_candidate_scoped_authorization"
    ] is True
    assert review["answers"]["standing_envelope_materialized"] is False
    assert review["answers"]["bounded_demo_probe_authorized"] is False
    assert review["answers"]["runtime_admission_ready"] is False
    assert review["answers"]["order_admission_ready"] is False


def test_local_ten_usdt_cap_authority_blocks_review() -> None:
    envelope = _current_envelope(
        cap_resolution=_cap_resolution(bounded_probe_local_cap_usdt_is_authority=True)
    )

    review = _review(current_envelope=envelope)

    assert review["status"] == mod.NOT_READY_STATUS
    assert "current_envelope_bounded_local_cap_marked_authority" in review["source_blockers"]
    assert review["envelope_preview"] == {}
    assert review["answers"]["order_admission_ready"] is False


def test_candidate_must_exist_in_false_negative_packet() -> None:
    packet = _false_negative_packet(
        ranked_false_negative_candidates=[
            _candidate_row("grid_trading|ETHUSDT|Buy", false_negative_rank=1)
        ]
    )

    review = _review(false_negative_candidate_packet=packet)

    assert review["status"] == mod.NOT_READY_STATUS
    assert "current_candidate_not_found_in_packet" in review["source_blockers"]
    assert "candidate_alignment_failed" in review["source_blockers"]


def test_authority_contamination_blocks_review() -> None:
    admission = _admission_review(
        answers=_answers(order_submission_performed=True)
    )

    review = _review(admission_review=admission)

    assert review["status"] == mod.AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert any(
        reason.endswith("answers.order_submission_performed_true")
        for reason in review["authority_contamination_reasons"]
    )
    assert review["answers"]["standing_envelope_materialized"] is False


def test_probe_order_hard_cap_blocks_review() -> None:
    review = _review(max_authorized_probe_orders=10)

    assert review["status"] == mod.NOT_READY_STATUS
    assert "max_authorized_probe_orders_exceeds_hard_cap" in review["source_blockers"]
    assert review["materialization_plan"] == {}
