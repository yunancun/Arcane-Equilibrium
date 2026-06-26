from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.maker_first_micro_tier_policy import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_maker_first_micro_tier_policy,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 9, 5, tzinfo=dt.timezone.utc)


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
        "main_cost_gate_adjustment": "NONE",
        "cap_envelope_mutation_allowed": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "live_authority_granted": False,
        "order_admission_ready": False,
        "order_submission_performed": False,
        "promotion_evidence": False,
        "promotion_proof": False,
        "bybit_call_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "runtime_mutation_performed": False,
    }
    payload.update(overrides)
    return payload


def _worksheet(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_current_cap_staircase_risk_worksheet_v1",
        "status": "CURRENT_CAP_STAIRCASE_RISK_WORKSHEET_READY_NO_AUTHORITY",
        "candidate": _candidate(),
        "construction_inputs": {
            "tick_size": 0.001,
            "qty_step": 0.1,
            "min_notional": 5.0,
            "cap_usdt": 10.0,
        },
        "cap_staircase": {
            "tiers": [
                {
                    "tier_index": 1,
                    "qty": 0.9,
                    "notional_usdt": 5.4576,
                    "cap_utilization_pct": 54.576,
                },
                {
                    "tier_index": 2,
                    "qty": 1.0,
                    "notional_usdt": 6.064,
                    "cap_utilization_pct": 60.64,
                },
                {
                    "tier_index": 3,
                    "qty": 1.1,
                    "notional_usdt": 6.6704,
                    "cap_utilization_pct": 66.704,
                },
                {
                    "tier_index": 8,
                    "qty": 1.6,
                    "notional_usdt": 9.7024,
                    "cap_utilization_pct": 97.024,
                },
            ],
        },
        "risk_worksheet": {
            "per_order_cap_usdt": 10.0,
            "max_probe_orders_before_review": 3,
            "max_total_demo_notional_before_review": 30.0,
            "max_executable_tier_reserved_notional_usdt": 29.1072,
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _fee_schema(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_fee_slippage_maker_taker_schema_contract_v1",
        "status": "FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY",
        "candidate": _candidate(),
        "contract": {
            "maker_taker_policy": {
                "expected_liquidity_role_for_bounded_probe": "maker",
                "post_only_expected": True,
            },
            "fee_slippage_policy": {
                "actual_fee_required": True,
                "actual_slippage_required": True,
            },
            "risk_and_cap_context": {
                "per_order_cap_usdt": 10.0,
                "max_probe_orders_before_review": 3,
                "max_total_demo_notional_before_review": 30.0,
                "max_executable_tier_reserved_notional_usdt": 29.1072,
            },
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _fresh_bbo(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_fresh_bbo_readonly_readiness_path_v1",
        "status": "FRESH_BBO_READONLY_READINESS_PATH_READY_NO_AUTHORITY",
        "candidate": _candidate(),
        "contract": {
            "freshness_and_market_data_gates": {
                "max_fresh_bbo_age_ms": 1000,
                "bid_ask_required": True,
                "bid_must_be_less_than_ask": True,
                "spread_bps_must_be_recorded": True,
                "instrument_status_required": "Trading",
                "instrument_filters_required": ["tick_size", "qty_step", "min_notional"],
            },
            "risk_and_cap_context": {
                "per_order_cap_usdt": 10.0,
                "max_probe_orders_before_review": 3,
                "max_total_demo_notional_before_review": 30.0,
            },
        },
        "answers": _answers(
            public_quote_capture_performed=False,
            bybit_public_market_data_call_performed=False,
            bybit_private_call_performed=False,
        ),
    }
    payload.update(overrides)
    return payload


def test_maker_first_micro_tier_policy_ready_without_authority() -> None:
    packet = build_maker_first_micro_tier_policy(
        current_cap_worksheet=_worksheet(),
        fee_slippage_schema=_fee_schema(),
        fresh_bbo_readiness=_fresh_bbo(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["summary"]["primary_tier_index"] == 1
    assert packet["summary"]["primary_qty"] == 0.9
    assert packet["summary"]["placement_call_allowed_by_this_policy"] is False
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["order_admission_ready"] is False

    contract = packet["contract"]
    tiers = contract["tier_priority_policy"]["tier_priorities"]
    assert [tier["tier_index"] for tier in tiers[:3]] == [1, 2, 3]
    assert tiers[-1]["priority"] == "cap_ceiling_reference_only"
    assert tiers[-1]["tier_index"] == 8

    placement = contract["maker_first_placement_rules"]
    assert placement["mode"] == "post_only_maker_first_limit_or_skip"
    assert placement["time_in_force_required"] == "PostOnly"
    assert placement["market_order_allowed"] is False
    assert placement["taker_fallback_allowed"] is False
    assert placement["candidate_side_rules"]["passive_reference"] == "best_ask"
    assert (
        placement["candidate_side_rules"]["marketable_cross_rule"]
        == "skip if post-round sell limit_price <= best_bid"
    )

    skip_policy = contract["spread_cost_skip_policy"]
    assert skip_policy["skip_if_missing_any_required_cost_or_spread_input"] is True
    assert skip_policy["global_cost_gate_lowering_allowed"] is False
    assert skip_policy["freshness_gate_lowering_allowed"] is False

    taker = contract["taker_fallback_fail_closed"]
    assert taker["taker_conversion_is_not_maker_path_success"] is True
    assert taker["unattributed_or_cleanup_fills_count_for_profit_proof"] is False
    assert "Maker-First Micro-Tier Placement Policy" in markdown


def test_authority_bearing_input_fails_closed() -> None:
    worksheet = _worksheet()
    worksheet["answers"]["order_authority_granted"] = True

    packet = build_maker_first_micro_tier_policy(
        current_cap_worksheet=worksheet,
        fee_slippage_schema=_fee_schema(),
        fresh_bbo_readiness=_fresh_bbo(),
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["contract"] == {}
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["placement_call_performed"] is False


def test_candidate_mismatch_fails_closed() -> None:
    packet = build_maker_first_micro_tier_policy(
        current_cap_worksheet=_worksheet(),
        fee_slippage_schema=_fee_schema(candidate=_candidate(symbol="SUIUSDT")),
        fresh_bbo_readiness=_fresh_bbo(),
        now_utc=NOW,
    )

    assert packet["status"] == "CANDIDATE_MISSING_OR_MISMATCH"
    assert packet["contract"] == {}
    assert packet["summary"]["maker_first_micro_tier_policy_ready"] is False


def test_not_ready_input_fails_closed() -> None:
    packet = build_maker_first_micro_tier_policy(
        current_cap_worksheet=_worksheet(status="NOT_READY"),
        fee_slippage_schema=_fee_schema(),
        fresh_bbo_readiness=_fresh_bbo(),
        now_utc=NOW,
    )

    assert packet["status"] == "CURRENT_CAP_WORKSHEET_INPUT_NOT_READY"
    assert packet["contract"] == {}


def test_missing_tier_ladder_fails_closed() -> None:
    worksheet = _worksheet(cap_staircase={"tiers": []})

    packet = build_maker_first_micro_tier_policy(
        current_cap_worksheet=worksheet,
        fee_slippage_schema=_fee_schema(),
        fresh_bbo_readiness=_fresh_bbo(),
        now_utc=NOW,
    )

    assert packet["status"] == "CAP_TIER_LADDER_MISSING"
    assert packet["contract"] == {}


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "maker_first_micro_tier_policy.py"
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
