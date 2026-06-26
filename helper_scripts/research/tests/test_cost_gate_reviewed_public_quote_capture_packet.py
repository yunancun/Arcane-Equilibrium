from __future__ import annotations

import datetime as dt
from pathlib import Path

from cost_gate_learning_lane.reviewed_public_quote_capture_packet import (
    AUTHORITY_BOUNDARY_VIOLATION_STATUS,
    READY_STATUS,
    SCHEMA_VERSION,
    build_reviewed_public_quote_capture_packet,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 26, 9, 20, tzinfo=dt.timezone.utc)


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
        "bybit_call_performed": False,
        "bybit_public_market_data_call_performed": False,
        "bybit_private_call_performed": False,
        "pg_query_performed": False,
        "pg_write_performed": False,
        "runtime_mutation_performed": False,
    }
    payload.update(overrides)
    return payload


def _maker_policy(**overrides) -> dict:
    payload = {
        "schema_version": "cost_gate_maker_first_micro_tier_placement_policy_v1",
        "status": "MAKER_FIRST_MICRO_TIER_POLICY_READY_NO_AUTHORITY",
        "candidate": _candidate(),
        "summary": {
            "mode": "post_only_maker_first_limit_or_skip",
            "primary_tier_index": 1,
            "primary_qty": 0.9,
            "primary_notional_usdt": 5.4576,
            "public_quote_capture_allowed_by_this_policy": False,
            "placement_call_allowed_by_this_policy": False,
            "order_admission_ready": False,
        },
        "contract": {
            "tier_priority_policy": {
                "tier_priorities": [
                    {
                        "priority": 1,
                        "tier_index": 1,
                        "qty": 0.9,
                        "notional_usdt": 5.4576,
                        "review_only": True,
                        "order_admission_ready": False,
                    }
                ]
            },
            "maker_first_placement_rules": {
                "mode": "post_only_maker_first_limit_or_skip",
                "time_in_force_required": "PostOnly",
                "taker_fallback_allowed": False,
            },
            "spread_cost_skip_policy": {
                "skip_formula": (
                    "skip unless reviewed_expected_net_edge_bps - spread_bps - "
                    "maker_fee_bps - slippage_buffer_bps > 0"
                ),
                "skip_if_missing_any_required_cost_or_spread_input": True,
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
            "public_quote_capture_readiness": {
                "source_helper": (
                    "helper_scripts/research/cost_gate_learning_lane/"
                    "bbo_freshness_public_quote_capture.py"
                ),
                "expected_schema_version": (
                    "bounded_probe_bbo_freshness_public_quote_capture_v1"
                ),
                "ready_status": "PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER",
                "network_call_permitted_by_this_contract": False,
            },
            "freshness_and_market_data_gates": {
                "max_fresh_bbo_age_ms": 1000,
                "ticker_must_have_exactly_one_row": True,
                "instrument_must_have_exactly_one_row": True,
                "bid_ask_required": True,
                "bid_must_be_less_than_ask": True,
                "bid_ask_size_positive": True,
                "spread_bps_must_be_recorded": True,
                "instrument_status_required": "Trading",
                "instrument_category_required": "linear",
                "instrument_filters_required": ["tick_size", "qty_step", "min_notional"],
                "raw_public_quote_is_not_construction_input": True,
            },
            "handoff_contract": {
                "public_quote_to_snapshot_adapter": {
                    "source_helper": (
                        "helper_scripts/research/cost_gate_learning_lane/"
                        "public_quote_market_snapshot_adapter.py"
                    ),
                    "output_schema_version": "bounded_probe_candidate_market_snapshot_v1",
                    "output_source": (
                        "bybit_public_quote_capture:"
                        "bbo_freshness_public_quote_capture_v1"
                    ),
                    "ready_status": "PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_NO_ORDER",
                    "requires_candidate_exact_match": True,
                    "requires_cap_match": True,
                    "requires_public_quote_path_sha": True,
                },
                "snapshot_to_construction_preview": {
                    "source_helper": (
                        "helper_scripts/research/cost_gate_learning_lane/"
                        "bounded_probe_candidate_construction_preview.py"
                    ),
                    "requires_fresh_bbo": True,
                    "requires_instrument_trading": True,
                    "order_admission_ready_from_this_contract": False,
                },
            },
        },
        "answers": _answers(),
    }
    payload.update(overrides)
    return payload


def test_reviewed_public_quote_capture_packet_ready_no_capture() -> None:
    packet = build_reviewed_public_quote_capture_packet(
        maker_first_policy=_maker_policy(),
        fresh_bbo_readiness=_fresh_bbo(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == SCHEMA_VERSION
    assert packet["status"] == READY_STATUS
    assert packet["candidate"]["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert packet["summary"]["runtime_capture_allowed_by_this_packet"] is False
    assert packet["summary"]["public_quote_capture_performed"] is False
    assert packet["summary"]["network_call_performed"] is False
    assert packet["summary"]["order_admission_ready"] is False
    assert packet["summary"]["request_count"] == 3
    assert packet["summary"]["max_fresh_bbo_age_ms"] == 1000

    review = packet["review_packet"]
    source = review["future_capture_source"]
    assert (
        source["expected_output_schema_version"]
        == "bounded_probe_bbo_freshness_public_quote_capture_v1"
    )
    assert source["runtime_capture_allowed_by_this_packet"] is False
    assert source["requires_separate_pm_e3_bb_review_before_runtime_capture"] is True

    envelope = review["request_envelope_review"]
    assert envelope["method"] == "GET"
    assert envelope["auth_or_cookie_headers_allowed"] is False
    assert envelope["private_or_order_paths_allowed"] is False
    assert envelope["redirects_allowed"] is False
    requests = {request["label"]: request for request in envelope["required_requests"]}
    assert requests["server_time"]["path"] == "/v5/market/time"
    assert requests["ticker"]["query"] == {"category": "linear", "symbol": "AVAXUSDT"}
    assert requests["instrument"]["path"] == "/v5/market/instruments-info"
    assert requests["instrument"]["capture_permitted_by_this_packet"] is False

    requirements = review["future_capture_artifact_requirements"]
    assert requirements["canonical_request_sha_required"] is True
    assert requirements["raw_response_sha_required"] is True
    assert requirements["ready_status_alone_is_not_order_admission"] is True

    maker = review["maker_policy_context"]
    assert maker["primary_tier"] == {
        "tier_index": 1,
        "qty": 0.9,
        "notional_usdt": 5.4576,
    }
    assert maker["time_in_force_required"] == "PostOnly"
    assert maker["taker_fallback_allowed"] is False

    handoff = review["handoff_contract"]
    assert handoff["raw_quote_can_feed_order_construction_directly"] is False
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert "Reviewed Public Quote Capture Packet No-Capture" in markdown


def test_authority_bearing_input_fails_closed() -> None:
    maker_policy = _maker_policy()
    maker_policy["answers"]["public_quote_capture_performed"] = True

    packet = build_reviewed_public_quote_capture_packet(
        maker_first_policy=maker_policy,
        fresh_bbo_readiness=_fresh_bbo(),
        now_utc=NOW,
    )

    assert packet["status"] == AUTHORITY_BOUNDARY_VIOLATION_STATUS
    assert packet["review_packet"] == {}
    assert packet["answers"]["public_quote_capture_performed"] is False
    assert packet["answers"]["bybit_call_performed"] is False


def test_candidate_mismatch_fails_closed() -> None:
    packet = build_reviewed_public_quote_capture_packet(
        maker_first_policy=_maker_policy(candidate=_candidate(symbol="SUIUSDT")),
        fresh_bbo_readiness=_fresh_bbo(),
        now_utc=NOW,
    )

    assert packet["status"] == "CANDIDATE_MISSING_OR_MISMATCH"
    assert packet["review_packet"] == {}
    assert packet["summary"]["reviewed_public_quote_capture_packet_ready"] is False


def test_not_ready_maker_policy_fails_closed() -> None:
    packet = build_reviewed_public_quote_capture_packet(
        maker_first_policy=_maker_policy(status="NOT_READY"),
        fresh_bbo_readiness=_fresh_bbo(),
        now_utc=NOW,
    )

    assert packet["status"] == "MAKER_FIRST_POLICY_INPUT_NOT_READY"
    assert packet["review_packet"] == {}


def test_not_ready_fresh_bbo_fails_closed() -> None:
    packet = build_reviewed_public_quote_capture_packet(
        maker_first_policy=_maker_policy(),
        fresh_bbo_readiness=_fresh_bbo(status="NOT_READY"),
        now_utc=NOW,
    )

    assert packet["status"] == "FRESH_BBO_READINESS_INPUT_NOT_READY"
    assert packet["review_packet"] == {}


def test_static_no_network_db_or_order_imports() -> None:
    source = Path(
        "helper_scripts/research/cost_gate_learning_lane/"
        "reviewed_public_quote_capture_packet.py"
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
