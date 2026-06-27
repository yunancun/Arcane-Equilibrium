from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.current_candidate_no_order_refresh_envelope import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    BOUNDED_AUTH_INPUT_NOT_NO_AUTHORITY_STATUS,
    CANDIDATE_MISMATCH_STATUS,
    GUI_RISK_CAP_INPUT_REQUIRED_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_current_candidate_no_order_refresh_envelope,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 27, 2, 0, tzinfo=dt.timezone.utc)


def _candidate(**overrides) -> dict:
    payload = {
        "side_cell_key": "grid_trading|AVAXUSDT|Sell",
        "strategy_name": "grid_trading",
        "symbol": "AVAXUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 60,
    }
    payload.update(overrides)
    return payload


def _answers(**overrides) -> dict:
    payload = {
        "bounded_demo_probe_authorized": False,
        "operator_authorization_object_emitted": False,
        "global_cost_gate_lowering_recommended": False,
        "freshness_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "cap_envelope_mutation_allowed": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "live_authority_granted": False,
        "order_admission_ready": False,
        "order_submission_performed": False,
        "promotion_evidence": False,
        "promotion_proof": False,
        "public_quote_capture_performed": False,
        "network_call_performed": False,
        "bybit_call_performed": False,
        "bybit_public_market_data_call_performed": False,
        "bybit_private_call_performed": False,
        "pg_write_performed": False,
        "runtime_mutation_performed": False,
    }
    payload.update(overrides)
    return payload


def _false_negative_review(candidate: dict | None = None, **overrides) -> dict:
    source = candidate or _candidate()
    payload = {
        "schema_version": "cost_gate_false_negative_operator_review_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": "STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT_REVIEW",
        "reason": "standing_demo_authorization_valid_for_preflight_review",
        "decision": "defer",
        "selected_side_cell_key": source["side_cell_key"],
        "candidate": {
            "side_cell_key": source["side_cell_key"],
            "strategy_names": [source["strategy_name"]],
            "symbols": [source["symbol"]],
            "sides": [source["side"]],
            "dominant_horizon_minutes": source["outcome_horizon_minutes"],
            "false_negative_rank": 1,
            "candidate_class": "false_negative_after_cost",
            "operator_review_required": True,
            "global_cost_gate_lowering_recommended": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "answers": _answers(
            operator_review_approved_for_preflight=False,
            bounded_demo_probe_preflight_approved=False,
            review_grants_runtime_authority=False,
            standing_demo_authorization_valid=False,
            standing_demo_authorization_consumed=False,
        ),
    }
    payload.update(overrides)
    return payload


def _false_negative_preflight(candidate: dict | None = None, **overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_false_negative_bounded_demo_probe_preflight_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": "STANDING_DEMO_AUTHORIZATION_INVALID_FOR_PREFLIGHT",
        "reason": "standing_demo_authorization_valid_for_preflight",
        "candidate": candidate or _candidate(),
        "answers": _answers(
            ready_for_operator_bounded_demo_probe_authorization=False,
        ),
    }
    payload.update(overrides)
    return payload


def _bounded_auth(candidate: dict | None = None, **overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_operator_authorization_packet_v1",
        "generated_at_utc": NOW.isoformat(),
        "status": "STANDING_DEMO_AUTHORIZATION_INVALID",
        "reason": "standing_demo_authorization_invalid",
        "decision": "defer",
        "candidate": candidate or _candidate(),
        "operator_authorization": None,
        "answers": _answers(
            active_runtime_probe_authority=False,
            active_runtime_order_authority=False,
        ),
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
    equity: float = 9552.43426257,
    generated_at: dt.datetime = NOW,
    **overrides,
) -> dict:
    payload = {
        "schema_version": "demo_account_equity_artifact_v1",
        "status": "DEMO_FAST_BALANCE_EQUITY_ARTIFACT_READY_NO_AUTHORITY",
        "generated_at_utc": generated_at.isoformat(),
        "environment": "demo",
        "source_endpoint": "/api/v1/strategy/demo/balance?fast=1",
        "payload": {
            "action_result": "success",
            "data": {
                "source": "rust_engine",
                "read_model": "rust_snapshot_fast",
                "pipeline_status": "connected",
                "totalEquity": equity,
                "total_equity": equity,
                "equity": equity,
                "balance": equity,
            },
            "is_simulated": True,
            "data_category": "paper_simulated",
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _packet(**kwargs) -> dict:
    kwargs.setdefault("false_negative_review", _false_negative_review())
    kwargs.setdefault("false_negative_preflight", _false_negative_preflight())
    kwargs.setdefault("bounded_auth", _bounded_auth())
    kwargs.setdefault("gui_risk_config", _gui_risk_config())
    kwargs.setdefault("account_equity_artifact", _account_equity_artifact())
    kwargs.setdefault("now_utc", NOW)
    return build_current_candidate_no_order_refresh_envelope(**kwargs)


def test_current_candidate_refresh_envelope_uses_gui_percent_cap() -> None:
    packet = _packet()
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["source_inputs"]["candidate_match"] is True
    assert packet["source_inputs"]["bounded_auth_no_authority"] is True
    assert packet["answers"]["public_quote_capture_performed"] is False
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False

    cap = packet["cap_resolution"]
    assert cap["risk_source_of_truth"] == "GUI-backed Rust RiskConfig"
    assert cap["per_trade_risk_pct_fraction"] == 0.1
    assert cap["per_trade_risk_pct_display"] == 10.0
    assert cap["account_equity_usdt"] == 9552.43426257
    assert cap["per_trade_budget_usdt"] == 955.24342626
    assert cap["single_position_budget_usdt"] == 2388.10856564
    assert cap["max_order_notional_usdt"] == 0.0
    assert cap["resolved_cap_usdt"] == 955.24342626
    assert cap["bounded_probe_local_cap_usdt_is_authority"] is False
    assert packet["summary"]["local_10_usdt_cap_is_global_risk_authority"] is False

    envelope = packet["refresh_envelope"]
    assert envelope["future_public_quote_refresh_review"][
        "runtime_capture_allowed_by_this_packet"
    ] is False
    requests = {
        request["label"]: request
        for request in envelope["request_envelope_review"]["required_requests"]
    }
    assert requests["server_time"]["path"] == "/v5/market/time"
    assert requests["ticker"]["query"] == {
        "category": "linear",
        "symbol": "AVAXUSDT",
    }
    assert requests["instrument"]["path"] == "/v5/market/instruments-info"
    assert (
        envelope["handoff_contract"]["public_quote_to_snapshot_adapter"][
            "cap_must_match_resolved_gui_risk_cap_usdt"
        ]
        is True
    )
    assert "Current Candidate No-Order Refresh Envelope" in markdown


def test_gui_percent_can_resolve_above_legacy_ten_usdt_local_probe_cap() -> None:
    packet = _packet(account_equity_artifact=_account_equity_artifact(equity=200.0))

    assert packet["status"] == READY_STATUS
    assert packet["cap_resolution"]["per_trade_budget_usdt"] == 20.0
    assert packet["cap_resolution"]["resolved_cap_usdt"] == 20.0
    assert packet["cap_resolution"]["resolved_cap_usdt"] != 10.0
    assert packet["refresh_envelope"]["resolved_gui_risk_cap"][
        "bounded_probe_local_cap_usdt_is_authority"
    ] is False
    assert packet["refresh_envelope"]["resolved_gui_risk_cap"][
        "single_position_budget_usdt"
    ] == 50.0


def test_candidate_mismatch_fails_closed_before_refresh_review() -> None:
    mismatch = _candidate(
        side_cell_key="grid_trading|SUIUSDT|Sell",
        symbol="SUIUSDT",
    )

    packet = _packet(false_negative_preflight=_false_negative_preflight(mismatch))

    assert packet["status"] == CANDIDATE_MISMATCH_STATUS
    assert packet["candidate"] == {}
    assert packet["refresh_envelope"] == {}
    assert packet["summary"]["runtime_capture_allowed_by_this_packet"] is False


def test_bounded_auth_object_or_runtime_authority_fails_closed() -> None:
    auth = _bounded_auth(
        operator_authorization={"authorization_id": "auth-should-not-exist"},
        answers=_answers(operator_authorization_object_emitted=True),
    )

    packet = _packet(bounded_auth=auth)

    assert packet["status"] in {
        AUTHORITY_BOUNDARY_VIOLATION_STATUS,
        BOUNDED_AUTH_INPUT_NOT_NO_AUTHORITY_STATUS,
    }
    assert packet["refresh_envelope"] == {}
    assert packet["answers"]["operator_authorization_object_emitted"] is False


def test_stale_equity_artifact_fails_closed() -> None:
    stale = NOW - dt.timedelta(seconds=901)

    packet = _packet(account_equity_artifact=_account_equity_artifact(generated_at=stale))

    assert packet["status"] == GUI_RISK_CAP_INPUT_REQUIRED_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["refresh_envelope"] == {}
    assert packet["cap_resolution"]["cap_resolved"] is False
    assert "account_equity_artifact_stale" in packet["cap_resolution"][
        "blocking_reasons"
    ]


def test_toml_percent_value_in_fraction_field_fails_closed() -> None:
    packet = _packet(gui_risk_config=_gui_risk_config(per_trade_risk_pct=10.0))

    assert packet["status"] == GUI_RISK_CAP_INPUT_REQUIRED_STATUS
    assert "per_trade_risk_pct_not_fraction" in packet["cap_resolution"][
        "blocking_reasons"
    ]
    assert packet["cap_resolution"]["resolved_cap_usdt"] is None


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "current_candidate_no_order_refresh_envelope.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "psycopg",
        "import requests",
        "urllib",
        "ccxt",
        "pybit",
        "subprocess",
        "urlopen",
        "create_order",
        "cancel_order",
        "place_order",
    ]
    for needle in forbidden:
        assert needle not in source
