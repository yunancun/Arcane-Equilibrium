from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.source_only_control_identity_contract import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    INPUT_NOT_READY_STATUS,
    READY_STATUS,
    REQUIRED_GAP_NOT_PRESENT_STATUS,
    SCHEMA_VERSION,
    build_source_only_control_identity_contract,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 8, 30, tzinfo=dt.timezone.utc)


def _gap_closure(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_false_negative_evidence_floor_gap_closure_design_v1",
        "generated_at_utc": "2026-06-26T08:03:37+00:00",
        "status": "EVIDENCE_FLOOR_GAP_CLOSURE_DESIGN_READY_NO_AUTHORITY",
        "candidate": {
            "side_cell_key": "grid_trading|AVAXUSDT|Sell",
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 60,
        },
        "gap_closure_items": [
            {
                "gap_key": "candidate_matched_controls_present",
                "lane": "source_only_then_post_authorized_review",
            },
            {
                "gap_key": "candidate_matched_fee_slippage_and_maker_taker_labels",
                "lane": "authorization_required_after_probe",
            },
        ],
        "summary": {"gap_count": 9},
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


def test_control_identity_contract_ready_without_authority() -> None:
    packet = build_source_only_control_identity_contract(
        gap_closure=_gap_closure(),
        selected_side_cell_key="grid_trading|AVAXUSDT|Sell",
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["summary"]["same_side_cell_control_required"] is True
    assert packet["summary"]["cross_symbol_control_counts_as_candidate_proof"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    contract = packet["contract"]
    assert contract["candidate_identity"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert contract["admissible_matched_control_identity"]["record_type"] == (
        "blocked_signal_outcome"
    )
    assert contract["admissible_matched_control_identity"]["required_exact_fields"][
        "symbol"
    ] == "AVAXUSDT"
    assert "candidate_proof" in contract["research_control_identity"]["prohibited_use"]
    assert "Source-Only Control Identity Contract" in markdown


def test_authority_bearing_input_fails_closed() -> None:
    gap_closure = _gap_closure()
    gap_closure["answers"]["order_authority_granted"] = True

    packet = build_source_only_control_identity_contract(
        gap_closure=gap_closure,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["contract"] == {}
    assert packet["answers"]["order_authority_granted"] is False


def test_not_ready_gap_closure_fails_closed() -> None:
    packet = build_source_only_control_identity_contract(
        gap_closure=_gap_closure(status="GAP_CLOSURE_NOT_READY"),
        now_utc=NOW,
    )

    assert packet["status"] == INPUT_NOT_READY_STATUS
    assert packet["contract"] == {}
    assert packet["answers"]["promotion_evidence"] is False


def test_required_control_gap_must_be_present() -> None:
    gap_closure = _gap_closure()
    gap_closure["gap_closure_items"] = [
        {
            "gap_key": "repeat_or_oos_path_before_any_promotion_claim",
            "lane": "source_only_validation_design",
        }
    ]

    packet = build_source_only_control_identity_contract(
        gap_closure=gap_closure,
        now_utc=NOW,
    )

    assert packet["status"] == REQUIRED_GAP_NOT_PRESENT_STATUS
    assert packet["contract"] == {}


def test_selected_side_cell_mismatch_fails_closed() -> None:
    packet = build_source_only_control_identity_contract(
        gap_closure=_gap_closure(),
        selected_side_cell_key="grid_trading|SUIUSDT|Sell",
        now_utc=NOW,
    )

    assert packet["status"] == "CONTROL_IDENTITY_CANDIDATE_MISSING"
    assert packet["candidate"] == {}


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "source_only_control_identity_contract.py"
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
