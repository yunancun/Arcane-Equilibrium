from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.fee_tier_maker_ratio_evidence_design import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    AUTH_PACKET_NOT_READY_STATUS,
    AUTH_PACKET_UNSAFE_STATUS,
    CANDIDATE_MISMATCH_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_fee_tier_maker_ratio_evidence_design,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 12, 40, tzinfo=dt.timezone.utc)


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
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "live_authority_granted": False,
        "order_admission_ready": False,
        "order_submission_performed": False,
        "promotion_evidence": False,
        "promotion_proof": False,
        "bybit_call_performed": False,
        "bybit_private_call_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "runtime_mutation_performed": False,
    }
    payload.update(overrides)
    return payload


def _auth_packet(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_operator_authorization_v1",
        "status": "FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED",
        "decision": "defer",
        "candidate": _candidate(),
        "authorization_id": None,
        "typed_confirm_expected": None,
        "typed_confirm_template": (
            "authorize_bounded_demo_probe:grid_trading|AVAXUSDT|Sell:"
            "<max_authorized_probe_orders<=3>:<authorization_id>"
        ),
        "typed_confirm_readiness": "PREFLIGHT_NOT_READY",
        "typed_confirm_matches": False,
        "probe_authority_granted": None,
        "order_authority_granted": None,
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
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def _maker_policy(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_maker_first_micro_tier_placement_policy_v1",
        "status": "MAKER_FIRST_MICRO_TIER_POLICY_READY_NO_AUTHORITY",
        "candidate": _candidate(),
        "contract": {
            "maker_first_placement_rules": {
                "mode": "post_only_maker_first_limit_or_skip",
                "time_in_force_required": "PostOnly",
            },
            "spread_cost_skip_policy": {
                "skip_if_missing_any_required_cost_or_spread_input": True,
                "global_cost_gate_lowering_allowed": False,
                "freshness_gate_lowering_allowed": False,
            },
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def test_fee_tier_maker_ratio_design_ready_without_authority() -> None:
    packet = build_fee_tier_maker_ratio_evidence_design(
        auth_packet=_auth_packet(),
        fee_slippage_schema=_fee_schema(),
        maker_first_policy=_maker_policy(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["summary"]["fee_tier_private_read_performed"] is False
    assert packet["summary"]["maker_ratio_proof_available_now"] is False
    assert packet["answers"]["private_fee_read_performed"] is False
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["order_submission_performed"] is False

    contract = packet["contract"]
    provenance = contract["fee_tier_provenance"]
    assert provenance["private_fee_read_status"] == "not_performed_by_this_packet"
    assert "maker_fee_bps" in provenance["required_fields"]
    assert "e3_bb_review_id" in provenance["required_fields"]

    ratio = contract["maker_ratio_measurement"]
    assert ratio["formula"] == (
        "maker_ratio = maker_filled_notional_usdt / filled_notional_usdt"
    )
    assert "exec_id" in ratio["required_fields"]
    assert "decision_lease_id" in ratio["minimum_lineage"]

    pnl = contract["after_fee_pnl_reconstruction"]
    assert pnl["formula"] == (
        "net_bps_after_actual_cost = gross_bps - actual_fee_bps - actual_slippage_bps"
    )
    assert pnl["expected_liquidity_role"] == "maker"
    assert "modeled_fee_tier_without_provenance" in contract["proof_exclusions"]
    assert "Fee-Tier Maker-Ratio Evidence Design" in markdown


def test_authority_bearing_input_fails_closed() -> None:
    maker_policy = _maker_policy()
    maker_policy["answers"]["order_authority_granted"] = True

    packet = build_fee_tier_maker_ratio_evidence_design(
        auth_packet=_auth_packet(),
        fee_slippage_schema=_fee_schema(),
        maker_first_policy=maker_policy,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["contract"] == {}
    assert "order_authority_granted_true" in packet["source_inputs"][
        "authority_contamination_reasons"
    ]
    assert packet["answers"]["order_authority_granted"] is False


def test_stale_exact_typed_confirm_fails_closed() -> None:
    packet = build_fee_tier_maker_ratio_evidence_design(
        auth_packet=_auth_packet(
            typed_confirm_expected=(
                "authorize_bounded_demo_probe:grid_trading|AVAXUSDT|Sell:0:"
            )
        ),
        fee_slippage_schema=_fee_schema(),
        maker_first_policy=_maker_policy(),
        now_utc=NOW,
    )

    assert packet["status"] == AUTH_PACKET_UNSAFE_STATUS
    assert packet["contract"] == {}
    assert packet["summary"]["fee_tier_maker_ratio_evidence_design_ready"] is False


def test_truthy_typed_confirm_match_marker_fails_closed() -> None:
    for marker in ("true", 1):
        packet = build_fee_tier_maker_ratio_evidence_design(
            auth_packet=_auth_packet(typed_confirm_matches=marker),
            fee_slippage_schema=_fee_schema(),
            maker_first_policy=_maker_policy(),
            now_utc=NOW,
        )

        assert packet["status"] == AUTH_PACKET_UNSAFE_STATUS
        assert packet["contract"] == {}


def test_candidate_mismatch_fails_closed() -> None:
    packet = build_fee_tier_maker_ratio_evidence_design(
        auth_packet=_auth_packet(),
        fee_slippage_schema=_fee_schema(candidate=_candidate(symbol="SUIUSDT")),
        maker_first_policy=_maker_policy(),
        now_utc=NOW,
    )

    assert packet["status"] == CANDIDATE_MISMATCH_STATUS
    assert packet["contract"] == {}


def test_incomplete_candidate_identity_fails_closed() -> None:
    incomplete = {"side_cell_key": "grid_trading|AVAXUSDT|Sell"}
    packet = build_fee_tier_maker_ratio_evidence_design(
        auth_packet=_auth_packet(candidate=incomplete),
        fee_slippage_schema=_fee_schema(candidate=incomplete),
        maker_first_policy=_maker_policy(candidate=incomplete),
        now_utc=NOW,
    )

    assert packet["status"] == AUTH_PACKET_NOT_READY_STATUS
    assert packet["contract"] == {}


def test_incomplete_non_auth_candidate_identity_fails_closed() -> None:
    incomplete = {"side_cell_key": "grid_trading|AVAXUSDT|Sell"}
    packet = build_fee_tier_maker_ratio_evidence_design(
        auth_packet=_auth_packet(),
        fee_slippage_schema=_fee_schema(candidate=incomplete),
        maker_first_policy=_maker_policy(candidate=incomplete),
        now_utc=NOW,
    )

    assert packet["status"] == CANDIDATE_MISMATCH_STATUS
    assert packet["contract"] == {}


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "fee_tier_maker_ratio_evidence_design.py"
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
