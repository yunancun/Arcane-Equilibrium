from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.fresh_bbo_readonly_readiness_path import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_fresh_bbo_readonly_readiness_path,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 8, 50, tzinfo=dt.timezone.utc)


def _fee_schema(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_fee_slippage_maker_taker_schema_contract_v1",
        "status": "FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY",
        "candidate": {
            "side_cell_key": "grid_trading|AVAXUSDT|Sell",
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "contract": {
            "risk_and_cap_context": {
                "per_order_cap_usdt": 10.0,
                "max_probe_orders_before_review": 3,
                "max_total_demo_notional_before_review": 30.0,
                "bbo_refresh_required_before_order_admission": True,
            }
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
            "bybit_call_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
        },
    }
    payload.update(overrides)
    return payload


def test_fresh_bbo_readiness_contract_ready_without_authority() -> None:
    packet = build_fresh_bbo_readonly_readiness_path(
        fee_slippage_schema=_fee_schema(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["bybit_public_market_data_call_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["order_admission_ready"] is False
    assert packet["summary"]["public_quote_capture_permitted_by_this_packet"] is False
    assert packet["summary"]["max_fresh_bbo_age_ms"] == 1000

    contract = packet["contract"]
    capture = contract["public_quote_capture_readiness"]
    assert capture["network_call_permitted_by_this_contract"] is False
    assert capture["request_envelope"]["method"] == "GET"
    assert capture["request_envelope"]["auth_or_cookie_headers_allowed"] is False
    requests = {item["label"]: item for item in capture["required_requests"]}
    assert requests["server_time"]["path"] == "/v5/market/time"
    assert requests["ticker"]["query"] == {"category": "linear", "symbol": "AVAXUSDT"}
    assert requests["instrument"]["required"] is True

    gates = contract["freshness_and_market_data_gates"]
    assert gates["max_fresh_bbo_age_ms"] == 1000
    assert gates["bid_must_be_less_than_ask"] is True
    assert gates["instrument_status_required"] == "Trading"
    assert gates["raw_public_quote_is_not_construction_input"] is True

    handoff = contract["handoff_contract"]
    assert (
        handoff["public_quote_to_snapshot_adapter"]["output_source"]
        == "bybit_public_quote_capture:bbo_freshness_public_quote_capture_v1"
    )
    assert (
        handoff["snapshot_to_construction_preview"][
            "order_admission_ready_from_this_contract"
        ]
        is False
    )
    assert "Fresh BBO Read-Only Readiness Path" in markdown


def test_authority_bearing_fee_schema_fails_closed() -> None:
    fee_schema = _fee_schema()
    fee_schema["answers"]["order_authority_granted"] = True

    packet = build_fresh_bbo_readonly_readiness_path(
        fee_slippage_schema=fee_schema,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["contract"] == {}
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False


def test_not_ready_fee_schema_fails_closed() -> None:
    packet = build_fresh_bbo_readonly_readiness_path(
        fee_slippage_schema=_fee_schema(status="NOT_READY"),
        now_utc=NOW,
    )

    assert packet["status"] == "FEE_SCHEMA_INPUT_NOT_READY"
    assert packet["contract"] == {}
    assert packet["summary"]["fresh_bbo_readonly_readiness_path_ready"] is False


def test_missing_candidate_fails_closed() -> None:
    packet = build_fresh_bbo_readonly_readiness_path(
        fee_slippage_schema=_fee_schema(candidate={}),
        now_utc=NOW,
    )

    assert packet["status"] == "FRESH_BBO_CANDIDATE_MISSING"
    assert packet["contract"] == {}


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "fresh_bbo_readonly_readiness_path.py"
    ).read_text(encoding="utf-8")

    forbidden = [
        "psycopg",
        "import requests",
        "urllib",
        "ccxt",
        "pybit",
        "subprocess",
        "create_order",
        "cancel_order",
        "place_order",
        "urlopen",
    ]
    for needle in forbidden:
        assert needle not in source
