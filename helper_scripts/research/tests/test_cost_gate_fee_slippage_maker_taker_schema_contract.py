from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.fee_slippage_maker_taker_schema_contract import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    WORKSHEET_NOT_READY_STATUS,
    build_fee_slippage_maker_taker_schema_contract,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 8, 40, tzinfo=dt.timezone.utc)


def _worksheet(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_current_cap_staircase_risk_worksheet_v1",
        "status": "CURRENT_CAP_STAIRCASE_RISK_WORKSHEET_READY_NO_AUTHORITY",
        "candidate": {
            "side_cell_key": "grid_trading|AVAXUSDT|Sell",
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "summary": {
            "constructible_under_current_cap": True,
            "order_admission_ready": False,
        },
        "construction_inputs": {
            "bbo_refresh_required_before_order_admission": True,
        },
        "risk_worksheet": {
            "per_order_cap_usdt": 10.0,
            "max_probe_orders_before_review": 3,
            "max_total_demo_notional_before_review": 30.0,
            "max_executable_tier_reserved_notional_usdt": 29.1072,
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


def test_fee_slippage_schema_ready_without_authority() -> None:
    packet = build_fee_slippage_maker_taker_schema_contract(
        current_cap_worksheet=_worksheet(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["summary"]["actual_fee_required"] is True
    assert packet["summary"]["actual_slippage_required"] is True
    assert packet["summary"]["maker_taker_label_required"] is True
    assert packet["summary"]["modeled_cost_only_allowed_for_proof"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    contract = packet["contract"]
    proof_row = contract["row_types"]["candidate_probe_outcome"]
    assert proof_row["required_exact_fields"]["symbol"] == "AVAXUSDT"
    assert proof_row["net_pnl_formula"] == (
        "realized_net_bps = gross_bps - fee_bps - slippage_bps"
    )
    group_ids = {group["group_id"] for group in proof_row["required_field_groups"]}
    assert {
        "actual_fee",
        "actual_slippage",
        "maker_taker_label",
        "net_pnl_reconstruction",
        "lineage",
    } <= group_ids
    assert contract["maker_taker_policy"]["expected_liquidity_role_for_bounded_probe"] == "maker"
    assert contract["fee_slippage_policy"]["modeled_cost_only_allowed_for_proof"] is False
    assert "Fee/Slippage/Maker-Taker Schema Contract" in markdown


def test_authority_bearing_worksheet_fails_closed() -> None:
    worksheet = _worksheet()
    worksheet["answers"]["probe_authority_granted"] = True

    packet = build_fee_slippage_maker_taker_schema_contract(
        current_cap_worksheet=worksheet,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["contract"] == {}
    assert packet["answers"]["probe_authority_granted"] is False


def test_not_ready_worksheet_fails_closed() -> None:
    packet = build_fee_slippage_maker_taker_schema_contract(
        current_cap_worksheet=_worksheet(status="NOT_READY"),
        now_utc=NOW,
    )

    assert packet["status"] == WORKSHEET_NOT_READY_STATUS
    assert packet["contract"] == {}
    assert packet["summary"]["schema_contract_ready"] is False


def test_missing_candidate_fails_closed() -> None:
    packet = build_fee_slippage_maker_taker_schema_contract(
        current_cap_worksheet=_worksheet(candidate={}),
        now_utc=NOW,
    )

    assert packet["status"] == "FEE_SCHEMA_CANDIDATE_MISSING"
    assert packet["contract"] == {}


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "fee_slippage_maker_taker_schema_contract.py"
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
