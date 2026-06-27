from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.current_cap_staircase_risk_worksheet import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    CANDIDATE_MISMATCH_STATUS,
    CONSTRUCTION_INPUT_INCOMPLETE_STATUS,
    CONTROL_CONTRACT_NOT_READY_STATUS,
    DEMO_ACCOUNT_EQUITY_ARTIFACT_READY_STATUS,
    GUI_RISK_CAP_INPUT_REQUIRED_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_current_cap_staircase_risk_worksheet,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 8, 30, tzinfo=dt.timezone.utc)
CURRENT_DEMO_EQUITY_USDT = 9552.43426257
CURRENT_GUI_PER_TRADE_CAP_USDT = 955.24342626
CURRENT_GUI_PER_TRADE_CAP_USDT_4DP = 955.2434
CURRENT_GUI_MAX_SINGLE_POSITION_BUDGET_USDT = 2388.10856564


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


def _gui_risk_config(**limits_overrides) -> dict:
    limits = {
        "per_trade_risk_pct": 0.1,
        "position_size_max_pct": 25.0,
        "total_exposure_max_pct": 150.0,
        "correlated_exposure_max_pct": 65.0,
        "max_order_notional_usdt": 0.0,
    }
    limits.update(limits_overrides)
    return {"limits": limits}


def _account_equity_artifact(
    *,
    equity: float = 100.0,
    generated_at: dt.datetime = NOW,
    payload_overrides: dict | None = None,
    **overrides,
) -> dict:
    payload_data = {
        "source": "rust_engine",
        "read_model": "rust_snapshot_fast",
        "pipeline_status": "connected",
        "totalEquity": equity,
        "total_equity": equity,
        "equity": equity,
        "balance": equity,
    }
    if payload_overrides:
        payload_data.update(payload_overrides)
    payload = {
        "schema_version": "demo_account_equity_artifact_v1",
        "status": DEMO_ACCOUNT_EQUITY_ARTIFACT_READY_STATUS,
        "generated_at_utc": generated_at.isoformat(),
        "environment": "demo",
        "source_endpoint": "/api/v1/strategy/demo/balance?fast=1",
        "payload": {
            "action_result": "success",
            "data": payload_data,
            "is_simulated": True,
            "data_category": "paper_simulated",
        },
        "answers": {
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }
    payload.update(overrides)
    return payload


def _worksheet(**kwargs) -> dict:
    kwargs.setdefault("control_identity_contract", _control_contract())
    kwargs.setdefault("construction_preview", _construction_preview())
    kwargs.setdefault("gui_risk_config", _gui_risk_config())
    kwargs.setdefault("account_equity_artifact", _account_equity_artifact())
    kwargs.setdefault("now_utc", NOW)
    return build_current_cap_staircase_risk_worksheet(**kwargs)


def test_avax_current_cap_staircase_ready_without_authority() -> None:
    packet = _worksheet()
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["summary"]["constructible_under_current_cap"] is True
    assert packet["summary"]["constructible_under_gui_risk_cap"] is True
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
    cap = packet["cap_resolution"]
    assert cap["source"] == "GUI Risk tab -> Rust RiskConfig limits"
    assert cap["risk_source_of_truth"] == "GUI-backed Rust RiskConfig"
    assert cap["per_trade_risk_pct_display"] == 10.0
    assert cap["position_size_max_pct"] == 25.0
    assert cap["account_equity_usdt"] == 100.0
    assert cap["account_equity_artifact_accepted"] is True
    assert cap["per_trade_budget_usdt"] == 10.0
    assert cap["single_position_budget_usdt"] == 25.0
    assert cap["source_construction_cap_usdt"] == 10.0
    assert cap["resolved_cap_usdt"] == 10.0
    assert cap["construction_cap_is_authority"] is False
    assert cap["bounded_probe_local_cap_usdt_is_authority"] is False
    assert cap["local_10_usdt_cap_is_global_risk_authority"] is False
    assert cap["gui_risk_config_is_authority"] is True
    assert packet["construction_inputs"]["source_construction_cap_usdt"] == 10.0
    assert packet["construction_inputs"]["resolved_cap_usdt"] == 10.0
    assert "GUI-Risk-Cap Staircase Risk Worksheet" in markdown


def test_current_demo_gui_ten_percent_cap_is_not_source_ten_usdt() -> None:
    packet = _worksheet(
        account_equity_artifact=_account_equity_artifact(
            equity=CURRENT_DEMO_EQUITY_USDT
        )
    )

    assert packet["status"] == READY_STATUS
    cap = packet["cap_resolution"]
    assert cap["risk_source_of_truth"] == "GUI-backed Rust RiskConfig"
    assert cap["per_trade_risk_pct_fraction"] == 0.1
    assert cap["per_trade_risk_pct_display"] == 10.0
    assert cap["position_size_max_pct"] == 25.0
    assert cap["account_equity_usdt"] == CURRENT_DEMO_EQUITY_USDT
    assert cap["per_trade_budget_usdt"] == CURRENT_GUI_PER_TRADE_CAP_USDT
    assert (
        cap["single_position_budget_usdt"]
        == CURRENT_GUI_MAX_SINGLE_POSITION_BUDGET_USDT
    )
    assert cap["source_construction_cap_usdt"] == 10.0
    assert cap["construction_cap_is_authority"] is False
    assert cap["bounded_probe_local_cap_usdt_is_authority"] is False
    assert cap["local_10_usdt_cap_is_global_risk_authority"] is False
    assert cap["resolved_cap_usdt"] == CURRENT_GUI_PER_TRADE_CAP_USDT
    assert cap["resolved_cap_usdt"] != cap["source_construction_cap_usdt"]

    risk = packet["risk_worksheet"]
    assert risk["per_order_cap_usdt"] == CURRENT_GUI_PER_TRADE_CAP_USDT_4DP
    assert risk["worst_case_reserved_notional_usdt"] == 2865.7303
    assert packet["construction_inputs"]["resolved_cap_usdt"] == (
        CURRENT_GUI_PER_TRADE_CAP_USDT
    )
    assert packet["cap_staircase"]["summary"]["max_qty_under_cap"] == 157.5
    assert packet["cap_staircase"]["summary"]["max_notional_under_cap_usdt"] == 955.08


def test_authority_bearing_input_fails_closed() -> None:
    preview = _construction_preview(
        answers={
            "order_submission_performed": True,
            "main_cost_gate_adjustment": "NONE",
        }
    )

    packet = _worksheet(construction_preview=preview)

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["source_inputs"]["authority_preserved"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_not_ready_control_contract_fails_closed() -> None:
    packet = _worksheet(control_identity_contract=_control_contract(status="NOT_READY"))

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

    packet = _worksheet(construction_preview=preview)

    assert packet["status"] == CANDIDATE_MISMATCH_STATUS
    assert packet["source_inputs"]["candidate_match"] is False


def test_incomplete_construction_input_fails_closed() -> None:
    preview = _construction_preview(construction={"cap_usdt": 10.0})

    packet = _worksheet(construction_preview=preview)

    assert packet["status"] == CONSTRUCTION_INPUT_INCOMPLETE_STATUS
    assert packet["summary"]["worksheet_ready"] is False


def test_gui_risk_config_and_equity_required_for_cap_resolution() -> None:
    packet = build_current_cap_staircase_risk_worksheet(
        control_identity_contract=_control_contract(),
        construction_preview=_construction_preview(),
        gui_risk_config=None,
        account_equity_artifact=None,
        now_utc=NOW,
    )

    assert packet["status"] == GUI_RISK_CAP_INPUT_REQUIRED_STATUS
    assert packet["summary"]["worksheet_ready"] is False
    assert packet["cap_resolution"]["cap_resolved"] is False
    assert "gui_risk_config_limits_missing" in packet["cap_resolution"][
        "blocking_reasons"
    ]
    assert "account_equity_artifact_required" in packet["cap_resolution"][
        "blocking_reasons"
    ]
    assert "account_equity_usdt_missing_or_non_positive" in packet[
        "cap_resolution"
    ]["blocking_reasons"]


def test_gui_risk_cap_can_exceed_stale_source_construction_cap_without_using_it() -> None:
    packet = _worksheet(account_equity_artifact=_account_equity_artifact(equity=200.0))

    assert packet["status"] == READY_STATUS
    assert packet["cap_resolution"]["source_construction_cap_usdt"] == 10.0
    assert packet["cap_resolution"]["resolved_cap_usdt"] == 20.0
    assert packet["risk_worksheet"]["per_order_cap_usdt"] == 20.0
    assert packet["cap_staircase"]["summary"]["max_qty_under_cap"] == 3.2
    assert packet["cap_staircase"]["summary"]["max_notional_under_cap_usdt"] == 19.4048


def test_manual_equity_without_artifact_does_not_resolve_cap() -> None:
    packet = build_current_cap_staircase_risk_worksheet(
        control_identity_contract=_control_contract(),
        construction_preview=_construction_preview(),
        gui_risk_config=_gui_risk_config(),
        account_equity_artifact=None,
        account_equity_usdt=100.0,
        now_utc=NOW,
    )

    assert packet["status"] == GUI_RISK_CAP_INPUT_REQUIRED_STATUS
    assert packet["account_equity_resolution"]["accepted"] is False
    assert "account_equity_artifact_required" in packet["cap_resolution"][
        "blocking_reasons"
    ]
    assert packet["cap_resolution"]["resolved_cap_usdt"] is None


def test_stale_equity_artifact_fails_closed() -> None:
    stale = NOW - dt.timedelta(seconds=901)

    packet = _worksheet(
        account_equity_artifact=_account_equity_artifact(generated_at=stale)
    )

    assert packet["status"] == GUI_RISK_CAP_INPUT_REQUIRED_STATUS
    assert packet["account_equity_resolution"]["accepted"] is False
    assert "account_equity_artifact_stale" in packet["cap_resolution"][
        "blocking_reasons"
    ]


def test_slow_or_private_equity_artifact_fails_closed() -> None:
    artifact = _account_equity_artifact(
        source_endpoint="/api/v1/strategy/demo/balance",
        payload_overrides={"read_model": "bybit_rest"},
    )

    packet = _worksheet(account_equity_artifact=artifact)

    assert packet["status"] == GUI_RISK_CAP_INPUT_REQUIRED_STATUS
    assert "account_equity_source_endpoint_not_demo_fast_balance" in packet[
        "cap_resolution"
    ]["blocking_reasons"]
    assert "account_equity_read_model_not_rust_snapshot_fast" in packet[
        "cap_resolution"
    ]["blocking_reasons"]


def test_equity_artifact_status_must_be_ready() -> None:
    artifact = _account_equity_artifact(status="DEMO_FAST_BALANCE_SOURCE_FAILURE")

    packet = _worksheet(account_equity_artifact=artifact)

    assert packet["status"] == GUI_RISK_CAP_INPUT_REQUIRED_STATUS
    assert packet["account_equity_resolution"]["accepted"] is False
    assert "account_equity_artifact_status_not_ready" in packet["cap_resolution"][
        "blocking_reasons"
    ]


def test_manual_equity_must_match_artifact_when_both_supplied() -> None:
    packet = _worksheet(
        account_equity_artifact=_account_equity_artifact(equity=100.0),
        account_equity_usdt=99.0,
    )

    assert packet["status"] == GUI_RISK_CAP_INPUT_REQUIRED_STATUS
    assert "account_equity_usdt_mismatch_artifact" in packet["cap_resolution"][
        "blocking_reasons"
    ]


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
