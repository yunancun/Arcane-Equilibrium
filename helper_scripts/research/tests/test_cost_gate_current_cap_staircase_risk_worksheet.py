from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.current_cap_staircase_risk_worksheet import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    CANDIDATE_MISMATCH_STATUS,
    CONSTRUCTION_INPUT_INCOMPLETE_STATUS,
    CONTROL_CONTRACT_NOT_READY_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_current_cap_staircase_risk_worksheet,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 8, 30, tzinfo=dt.timezone.utc)


def _control_contract(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_source_only_control_identity_contract_v1",
        "status": "SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY",
        "candidate": {
            "side_cell_key": "grid_trading|AVAXUSDT|Sell",
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "answers": {
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _construction_preview(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_candidate_construction_preview_v1",
        "status": "CANDIDATE_CONSTRUCTION_BBO_STALE",
        "candidate": {
            "side_cell_key": "grid_trading|AVAXUSDT|Sell",
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "blocking_gates": ["bbo_freshness"],
        "construction": {
            "cap_usdt": 10.0,
            "constructible": True,
            "limit_price": 6.064,
            "min_notional": 5.0,
            "qty_step": 0.1,
            "reference_price": 6.063,
            "tick_size": 0.001,
        },
        "market_inputs": {
            "effective_bbo_age_ms": 4935.735,
            "instrument_status": "Trading",
            "max_fresh_bbo_age_ms": 1000.0,
        },
        "readiness": {"bbo_fresh": False},
        "answers": {
            "bybit_call_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "order_submission_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
            "runtime_mutation_performed": False,
        },
    }
    payload.update(overrides)
    return payload


def test_avax_current_cap_staircase_ready_without_authority() -> None:
    packet = build_current_cap_staircase_risk_worksheet(
        control_identity_contract=_control_contract(),
        construction_preview=_construction_preview(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["summary"]["constructible_under_current_cap"] is True
    assert packet["summary"]["order_admission_ready"] is False
    assert packet["summary"]["bbo_refresh_required_before_order_admission"] is True
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    staircase = packet["cap_staircase"]
    assert staircase["summary"]["tier_count"] == 8
    assert staircase["summary"]["min_executable_qty"] == 0.9
    assert staircase["summary"]["min_executable_notional_usdt"] == 5.4576
    assert staircase["summary"]["max_qty_under_cap"] == 1.6
    assert staircase["summary"]["max_notional_under_cap_usdt"] == 9.7024
    assert staircase["tiers"][0]["qty"] == 0.9
    assert staircase["tiers"][-1]["qty"] == 1.6
    risk = packet["risk_worksheet"]
    assert risk["per_order_cap_usdt"] == 10.0
    assert risk["max_probe_orders_before_review"] == 3
    assert risk["worst_case_reserved_notional_usdt"] == 30.0
    assert risk["max_executable_tier_reserved_notional_usdt"] == 29.1072
    assert risk["fits_existing_total_review_cap"] is True
    assert "Current-Cap Staircase Risk Worksheet" in markdown


def test_authority_bearing_input_fails_closed() -> None:
    preview = _construction_preview(
        answers={
            "order_submission_performed": True,
            "main_cost_gate_adjustment": "NONE",
        }
    )

    packet = build_current_cap_staircase_risk_worksheet(
        control_identity_contract=_control_contract(),
        construction_preview=preview,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["source_inputs"]["authority_preserved"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_not_ready_control_contract_fails_closed() -> None:
    packet = build_current_cap_staircase_risk_worksheet(
        control_identity_contract=_control_contract(status="NOT_READY"),
        construction_preview=_construction_preview(),
        now_utc=NOW,
    )

    assert packet["status"] == CONTROL_CONTRACT_NOT_READY_STATUS
    assert packet["summary"]["constructible_under_current_cap"] is False
    assert packet["cap_staircase"]["tiers"] == []


def test_candidate_mismatch_fails_closed() -> None:
    preview = _construction_preview(
        candidate={
            "side_cell_key": "grid_trading|SUIUSDT|Sell",
            "strategy_name": "grid_trading",
            "symbol": "SUIUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        }
    )

    packet = build_current_cap_staircase_risk_worksheet(
        control_identity_contract=_control_contract(),
        construction_preview=preview,
        now_utc=NOW,
    )

    assert packet["status"] == CANDIDATE_MISMATCH_STATUS
    assert packet["source_inputs"]["candidate_match"] is False


def test_incomplete_construction_input_fails_closed() -> None:
    preview = _construction_preview(construction={"cap_usdt": 10.0})

    packet = build_current_cap_staircase_risk_worksheet(
        control_identity_contract=_control_contract(),
        construction_preview=preview,
        now_utc=NOW,
    )

    assert packet["status"] == CONSTRUCTION_INPUT_INCOMPLETE_STATUS
    assert packet["summary"]["worksheet_ready"] is False


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "current_cap_staircase_risk_worksheet.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "psycopg",
        "requests",
        "urllib",
        "ccxt",
        "pybit",
        "subprocess",
        "create_order",
        "cancel_order",
        "place_order",
    ]
    for needle in forbidden:
        assert needle not in source
