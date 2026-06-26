from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane.maker_cost_cushion_worksheet import (
    ASSUMPTION_INVALID_STATUS,
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    CANDIDATE_MISMATCH_STATUS,
    COST_INPUT_MISSING_STATUS,
    EDGE_NOT_READY_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_maker_cost_cushion_worksheet,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 11, 17, tzinfo=dt.timezone.utc)


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
        "bybit_call_performed": False,
        "bybit_private_call_performed": False,
        "auth_headers_present": False,
        "cookie_headers_present": False,
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
        "pg_query_performed": False,
        "pg_write_performed": False,
        "runtime_mutation_performed": False,
        "writer_enabled": False,
    }
    payload.update(overrides)
    return payload


def _preview(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_candidate_construction_preview_v1",
        "status": "CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER",
        "candidate": _candidate(),
        "construction": {
            "best_bid": 6.145,
            "best_ask": 6.146,
            "cap_usdt": 10.0,
            "constructible": True,
            "limit_price": 6.146,
            "rounded_qty": 1.6,
            "rounded_notional_usdt": 9.8336,
            "placement_mode": "sell_near_touch_post_only_at_or_above_best_ask",
            "passive_against_touch": True,
        },
        "market_inputs": {
            "best_bid": 6.145,
            "best_ask": 6.146,
            "effective_bbo_age_ms": 254.561,
            "max_fresh_bbo_age_ms": 1000.0,
            "spread_bps": 1.6272,
        },
        "answers": _answers(candidate_construction_preview_ready_no_order=True),
    }
    payload.update(overrides)
    return payload


def _summary(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_atomic_quote_adapter_preview_runner_v1",
        "status": "ATOMIC_QUOTE_ADAPTER_PREVIEW_READY_NO_ORDER",
        "candidate": {
            **_candidate(),
            "avg_net_bps": 73.5511,
            "current_cap_usdt": 10.0,
            "net_positive_pct": 100.0,
            "outcome_count": 48,
        },
        "answers": _answers(bybit_public_market_data_call_performed=True),
    }
    payload.update(overrides)
    return payload


def _reroute(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_lower_price_reroute_review_v1",
        "status": "LOWER_PRICE_REROUTE_READY_FOR_DEMO_CONSTRUCTION_REVIEW",
        "selected_candidate": {
            **_candidate(),
            "avg_net_bps": 73.5511,
            "current_cap_usdt": 10.0,
            "net_positive_pct": 100.0,
            "outcome_count": 48,
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def test_maker_cost_cushion_worksheet_ready_without_authority() -> None:
    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(),
        atomic_summary=_summary(),
        reroute_review=_reroute(),
        maker_fee_bps_per_side=2.0,
        taker_fee_bps_per_side=5.5,
        slippage_buffer_bps=1.0,
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["preview_market_context"]["spread_bps"] == 1.6272
    assert packet["cost_cushion"]["modeled_avg_net_bps"] == 73.5511
    assert packet["cost_cushion"]["residual_after_spread_slippage_bps"] == 70.9239
    assert (
        packet["cost_cushion"]["maker_scenario"][
            "conservative_stress_margin_bps"
        ]
        == 66.9239
    )
    assert (
        packet["cost_cushion"]["taker_failure_analysis_scenario"][
            "conservative_stress_margin_bps"
        ]
        == 59.9239
    )
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["new_bybit_public_market_data_call_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["answers"]["order_admission_ready"] is False
    assert packet["answers"]["promotion_evidence"] is False
    assert packet["answers"]["main_cost_gate_adjustment"] == "NONE"
    assert "Maker Cost Cushion Worksheet" in markdown


def test_missing_positive_edge_fails_closed() -> None:
    summary = _summary(candidate={**_candidate(), "avg_net_bps": None})
    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(),
        atomic_summary=summary,
        now_utc=NOW,
    )

    assert packet["status"] == EDGE_NOT_READY_STATUS
    assert packet["candidate"] == {}
    assert packet["answers"]["order_submission_performed"] is False


def test_negative_fee_assumption_fails_closed() -> None:
    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(),
        atomic_summary=_summary(),
        maker_fee_bps_per_side=-0.1,
        now_utc=NOW,
    )

    assert packet["status"] == ASSUMPTION_INVALID_STATUS
    assert packet["cost_cushion"] == {}
    assert packet["answers"]["probe_authority_granted"] is False


def test_authority_bearing_input_fails_closed() -> None:
    summary = _summary()
    summary["answers"]["order_authority_granted"] = True

    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(),
        atomic_summary=summary,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["candidate"] == {}
    assert "order_authority_granted_true" in packet["source_inputs"][
        "authority_contamination_reasons"
    ]
    assert packet["answers"]["order_authority_granted"] is False


def test_broad_bybit_call_input_fails_closed() -> None:
    preview = _preview()
    preview["answers"]["bybit_call_performed"] = True

    packet = build_maker_cost_cushion_worksheet(
        construction_preview=preview,
        atomic_summary=_summary(),
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert "bybit_call_performed_true" in packet["source_inputs"][
        "authority_contamination_reasons"
    ]
    assert packet["answers"]["bybit_call_performed"] is False


def test_authority_and_proof_aliases_fail_closed() -> None:
    summary = _summary()
    summary["candidate"]["order_authority"] = "GRANTED"
    summary["candidate"]["probe_authority"] = "GRANTED"
    summary["candidate"]["execution_authority"] = "ENABLED"
    summary["candidate"]["cost_gate_proof"] = True
    summary["candidate"]["profit_proof"] = True

    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(),
        atomic_summary=summary,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    reasons = packet["source_inputs"]["authority_contamination_reasons"]
    assert "order_authority_true" in reasons
    assert "probe_authority_true" in reasons
    assert "execution_authority_true" in reasons
    assert "cost_gate_proof_true" in reasons
    assert "profit_proof_true" in reasons
    assert packet["cost_cushion"] == {}
    assert packet["readiness"]["maker_margin_positive"] is False


def test_authority_alias_positive_vocabulary_fails_closed() -> None:
    summary = _summary()
    summary["candidate"]["order_authority"] = "ALLOWED"
    summary["candidate"]["probe_authority"] = "PERMITTED"
    summary["candidate"]["execution_authority"] = "PRESENT"

    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(),
        atomic_summary=summary,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    reasons = packet["source_inputs"]["authority_contamination_reasons"]
    assert "order_authority_true" in reasons
    assert "probe_authority_true" in reasons
    assert "execution_authority_true" in reasons
    assert packet["cost_cushion"] == {}


def test_forbidden_status_strings_fail_closed_unless_false_safe() -> None:
    summary = _summary()
    summary["candidate"]["operator_authorization_object_emitted"] = "PRESENT_UNKNOWN_AGE"
    summary["candidate"]["order_authority"] = "APPROVED"
    summary["candidate"]["probe_authority"] = "AUTHORIZED_BY_OPERATOR"
    summary["candidate"]["execution_authority"] = "AUTHORITY_GRANTED"
    summary["candidate"]["promotion_proof"] = "PROOF_PRESENT"

    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(),
        atomic_summary=summary,
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    reasons = packet["source_inputs"]["authority_contamination_reasons"]
    assert "operator_authorization_object_emitted_true" in reasons
    assert "order_authority_true" in reasons
    assert "probe_authority_true" in reasons
    assert "execution_authority_true" in reasons
    assert "promotion_proof_true" in reasons
    assert packet["readiness"]["authority_preserved"] is False


def test_false_safe_forbidden_status_strings_are_allowed() -> None:
    summary = _summary()
    summary["candidate"]["order_authority"] = "NOT_GRANTED"
    summary["candidate"]["probe_authority"] = "absent"
    summary["candidate"]["execution_authority"] = "not present"

    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(),
        atomic_summary=summary,
        now_utc=NOW,
    )

    assert packet["status"] == READY_STATUS
    assert packet["source_inputs"]["authority_contamination_reasons"] == []
    assert packet["readiness"]["authority_preserved"] is True


def test_incomplete_candidate_identity_fails_closed() -> None:
    incomplete = _candidate(outcome_horizon_minutes=None)
    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(candidate=incomplete),
        atomic_summary=_summary(candidate={**incomplete, "avg_net_bps": 73.5511}),
        now_utc=NOW,
    )

    assert packet["status"] == CANDIDATE_MISMATCH_STATUS
    assert "candidate_0_outcome_horizon_minutes_missing" in packet["source_inputs"][
        "candidate_identity_reasons"
    ]
    assert packet["candidate"] == {}
    assert packet["cost_cushion"] == {}


def test_internally_inconsistent_side_cell_fails_closed() -> None:
    inconsistent = _candidate(symbol="SUIUSDT")
    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(candidate=inconsistent),
        atomic_summary=_summary(candidate={**inconsistent, "avg_net_bps": 73.5511}),
        now_utc=NOW,
    )

    assert packet["status"] == CANDIDATE_MISMATCH_STATUS
    assert "candidate_0_side_cell_key_inconsistent" in packet["source_inputs"][
        "candidate_identity_reasons"
    ]
    assert packet["readiness"]["candidate_match"] is False
    assert packet["answers"]["order_admission_ready"] is False


def test_invalid_notional_fails_closed_without_positive_readiness() -> None:
    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(construction={**_preview()["construction"], "rounded_notional_usdt": -9.8336}),
        atomic_summary=_summary(),
        now_utc=NOW,
    )

    assert packet["status"] == COST_INPUT_MISSING_STATUS
    assert packet["cost_cushion"] == {}
    assert packet["readiness"]["maker_margin_positive"] is False
    assert packet["readiness"]["taker_margin_positive_for_failure_analysis"] is False
    assert packet["candidate"] == {}


def test_candidate_mismatch_fails_closed() -> None:
    packet = build_maker_cost_cushion_worksheet(
        construction_preview=_preview(),
        atomic_summary=_summary(candidate={**_candidate(symbol="SUIUSDT"), "avg_net_bps": 73.0}),
        now_utc=NOW,
    )

    assert packet["status"] == CANDIDATE_MISMATCH_STATUS
    assert packet["candidate"] == {}
    assert packet["answers"]["order_admission_ready"] is False
