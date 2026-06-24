from __future__ import annotations

import datetime as dt
import json
import sys

from cost_gate_learning_lane.bounded_probe_order_construction_repair import (
    ORDER_CONSTRUCTION_REPAIR_SCHEMA_VERSION,
    build_bounded_demo_probe_order_construction_repair,
    main,
    render_markdown,
)


NOW = dt.datetime(2026, 6, 24, 17, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "ma_crossover|BTCUSDT|Sell"


def _placement_preview(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_probe_no_order_placement_construction_preview_v1",
        "generated_at_utc": "2026-06-24T16:47:19+00:00",
        "status": "SKIP_FAIL_CLOSED_NO_ORDER",
        "side_cell_key": SIDE_CELL,
        "symbol": "BTCUSDT",
        "side": "Sell",
        "blocking_reasons": [
            "stale_bbo_snapshot",
            "max_demo_notional_below_min_positive_qty_step",
            "rounded_notional_below_min_notional",
            "min_positive_qty_notional_exceeds_demo_cap",
        ],
        "placement_repair_limits": {
            "max_fresh_bbo_age_ms": 1000,
            "max_demo_notional_usdt_per_order": 10.0,
        },
        "runtime_bbo_snapshot": {
            "bbo_age_ms": 1652,
            "best_bid": 60040.1,
            "best_ask": 60040.2,
        },
        "instrument_filters": {
            "tick_size": 0.1,
            "qty_step": 0.001,
            "min_notional": 5.0,
        },
        "sell_near_touch_construction": {
            "reference_price": 60040.1,
            "post_round_limit_price": 60040.2,
            "post_round_passive_against_best_bid": True,
            "touch_gap_bps": 0.0166,
        },
        "qty_notional_construction": {
            "max_demo_notional_usdt_per_order": 10.0,
            "qty_step": 0.001,
            "min_notional": 5.0,
            "rounded_qty_down": 0.0,
            "min_positive_qty_notional_at_limit": 60.0402,
        },
        "answers": {
            "order_submission_performed": False,
            "bybit_call_performed": False,
            "pg_write_performed": False,
            "ledger_append_performed": False,
            "canonical_plan_mutation_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def test_btc_qty_step_cap_failure_emits_repair_required() -> None:
    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=_placement_preview(),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["schema_version"] == ORDER_CONSTRUCTION_REPAIR_SCHEMA_VERSION
    assert packet["status"] == "ORDER_CONSTRUCTION_REPAIR_REQUIRED"
    assert packet["answers"]["order_construction_repair_required"] is True
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["probe_authority_granted"] is False
    assert packet["answers"]["order_authority_granted"] is False
    assert packet["bbo_freshness"]["stale_bbo"] is True
    assert packet["sizing_feasibility"]["fits_current_cap"] is False
    assert (
        packet["sizing_feasibility"]["minimum_required_demo_notional_usdt_per_order"]
        == 60.0402
    )
    assert {
        option["option_id"] for option in packet["repair_options"]
    } >= {
        "repair_bbo_freshness_before_order_construction",
        "cap_repair_operator_qc_review_required",
        "lower_price_candidate_reroute_screen",
    }
    assert "ORDER_CONSTRUCTION_REPAIR_REQUIRED" in markdown


def test_construction_feasible_under_cap_still_grants_no_authority() -> None:
    preview = _placement_preview(
        status="WOULD_SUBMIT_IF_AUTHORIZED_NO_ORDER",
        blocking_reasons=[],
        runtime_bbo_snapshot={"bbo_age_ms": 100, "best_bid": 100.0, "best_ask": 100.1},
        instrument_filters={"tick_size": 0.1, "qty_step": 0.001, "min_notional": 5.0},
        sell_near_touch_construction={
            "reference_price": 100.0,
            "post_round_limit_price": 100.1,
            "post_round_passive_against_best_bid": True,
            "touch_gap_bps": 10.0,
        },
        qty_notional_construction={
            "max_demo_notional_usdt_per_order": 10.0,
            "qty_step": 0.001,
            "min_notional": 5.0,
            "rounded_qty_down": 0.099,
            "min_positive_qty_notional_at_limit": 0.1001,
        },
    )

    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=preview,
        now_utc=NOW,
    )

    assert packet["status"] == "ORDER_CONSTRUCTION_FEASIBLE_NO_AUTHORITY"
    assert packet["answers"]["order_construction_feasible_under_current_cap"] is True
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["order_authority_granted"] is False


def test_authority_or_mutation_contamination_fails_closed() -> None:
    preview = _placement_preview(
        answers={
            "order_submission_performed": True,
            "main_cost_gate_adjustment": "NONE",
        }
    )

    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=preview,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["source_placement_preview"]["authority_preserved"] is False
    assert "order_submission_performed_contaminating" in packet["source_placement_preview"][
        "authority_contamination_reasons"
    ]
    assert packet["answers"]["order_submission_performed"] is False


def test_non_boolean_authority_contamination_fails_closed() -> None:
    preview = _placement_preview(
        answers={
            "order_submission_performed": "true",
            "promotion_evidence": {"fill_id": "not_allowed"},
            "main_cost_gate_adjustment": "NONE",
        }
    )

    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=preview,
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    reasons = packet["source_placement_preview"]["authority_contamination_reasons"]
    assert "order_submission_performed_contaminating" in reasons
    assert "promotion_evidence_contaminating" in reasons


def test_blocking_reasons_dominate_feasible_preview_status() -> None:
    preview = _placement_preview(
        status="WOULD_SUBMIT_IF_AUTHORIZED_NO_ORDER",
        blocking_reasons=["instrument_not_trading"],
        runtime_bbo_snapshot={"bbo_age_ms": 100, "best_bid": 100.0, "best_ask": 100.1},
        sell_near_touch_construction={
            "reference_price": 100.0,
            "post_round_limit_price": 100.1,
        },
        qty_notional_construction={
            "max_demo_notional_usdt_per_order": 10.0,
            "qty_step": 0.001,
            "min_notional": 5.0,
        },
    )

    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=preview,
        now_utc=NOW,
    )

    assert packet["status"] == "ORDER_CONSTRUCTION_REPAIR_REQUIRED"
    assert packet["answers"]["order_construction_feasible_under_current_cap"] is False


def test_candidate_universe_screen_surfaces_lower_price_feasible_candidates() -> None:
    candidates = [
        {
            "side_cell_key": "ma_crossover|BTCUSDT|Sell",
            "symbol": "BTCUSDT",
            "limit_price": 60040.2,
            "qty_step": 0.001,
            "min_notional": 5.0,
        },
        {
            "side_cell_key": "grid_trading|SOLUSDT|Sell",
            "symbol": "SOLUSDT",
            "limit_price": 130.0,
            "qty_step": 0.01,
            "min_notional": 5.0,
        },
    ]

    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=_placement_preview(),
        candidate_universe=candidates,
        now_utc=NOW,
    )

    screen = packet["candidate_universe_screen"]
    assert screen["fits_current_cap_count"] == 1
    assert screen["rows"][0]["symbol"] == "SOLUSDT"
    assert screen["rows"][0]["fits_current_cap"] is True
    reroute = [
        option
        for option in packet["repair_options"]
        if option["option_id"] == "lower_price_candidate_reroute_screen"
    ][0]
    assert reroute["status"] == "AVAILABLE"
    assert reroute["feasible_candidate_count"] == 1


def test_candidate_universe_screen_keeps_false_negative_rank_priority() -> None:
    candidates = [
        {
            "side_cell_key": "grid_trading|APTUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "APTUSDT",
            "side": "Buy",
            "false_negative_rank": 8,
            "friction_rank": 8,
            "avg_net_bps": 13.6,
            "net_positive_pct": 70.0,
            "outcome_count": 44,
            "limit_price": 0.6,
            "qty_step": 0.01,
            "min_notional": 5.0,
        },
        {
            "side_cell_key": "grid_trading|AVAXUSDT|Sell",
            "strategy_name": "grid_trading",
            "symbol": "AVAXUSDT",
            "side": "Sell",
            "false_negative_rank": 1,
            "friction_rank": 1,
            "avg_net_bps": 73.5,
            "net_positive_pct": 100.0,
            "outcome_count": 48,
            "limit_price": 6.15,
            "qty_step": 0.1,
            "min_notional": 5.0,
        },
    ]

    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=_placement_preview(),
        candidate_universe=candidates,
        now_utc=NOW,
    )

    top = packet["candidate_universe_screen"]["rows"][0]
    assert top["side_cell_key"] == "grid_trading|AVAXUSDT|Sell"
    assert top["false_negative_rank"] == 1
    assert top["avg_net_bps"] == 73.5


def test_stale_candidate_universe_artifact_is_not_used_for_reroute() -> None:
    candidate_artifact = {
        "schema_version": "bounded_probe_candidate_universe_instrument_screen_input_v1",
        "generated_at_utc": "2026-06-20T17:00:00+00:00",
        "rows": [
            {
                "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                "symbol": "AVAXUSDT",
                "limit_price": 6.15,
                "qty_step": 0.1,
                "min_notional": 5.0,
            }
        ],
    }

    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=_placement_preview(),
        candidate_universe=candidate_artifact["rows"],
        candidate_universe_artifact=candidate_artifact,
        now_utc=NOW,
    )

    assert packet["source_candidate_universe"]["valid_for_reroute_screen"] is False
    assert packet["candidate_universe_screen"]["fits_current_cap_count"] == 0


def test_non_trading_candidate_is_not_feasible_for_reroute() -> None:
    candidates = [
        {
            "side_cell_key": "grid_trading|AVAXUSDT|Sell",
            "symbol": "AVAXUSDT",
            "limit_price": 6.15,
            "qty_step": 0.1,
            "min_notional": 5.0,
            "instrument_status": "PreLaunch",
        }
    ]

    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=_placement_preview(),
        candidate_universe=candidates,
        now_utc=NOW,
    )

    row = packet["candidate_universe_screen"]["rows"][0]
    assert row["fits_current_cap"] is False
    assert row["instrument_reject_reason"] == "instrument_status_not_trading"


def test_cli_bare_array_candidate_universe_is_not_valid_for_reroute(
    tmp_path, monkeypatch
) -> None:
    preview_path = tmp_path / "preview.json"
    universe_path = tmp_path / "universe.json"
    output_path = tmp_path / "out.json"
    preview_path.write_text(json.dumps(_placement_preview()), encoding="utf-8")
    universe_path.write_text(
        json.dumps(
            [
                {
                    "side_cell_key": "grid_trading|AVAXUSDT|Sell",
                    "symbol": "AVAXUSDT",
                    "limit_price": 6.15,
                    "qty_step": 0.1,
                    "min_notional": 5.0,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bounded_probe_order_construction_repair",
            "--placement-preview-json",
            str(preview_path),
            "--candidate-universe-json",
            str(universe_path),
            "--json-output",
            str(output_path),
        ],
    )

    assert main() == 0
    packet = json.loads(output_path.read_text(encoding="utf-8"))

    assert packet["source_candidate_universe"]["valid_for_reroute_screen"] is False
    assert packet["candidate_universe_screen"]["fits_current_cap_count"] == 0
    assert packet["input_artifacts"]["candidate_universe_json"]["sha256"]


def test_missing_or_stale_preview_fails_closed() -> None:
    packet = build_bounded_demo_probe_order_construction_repair(
        placement_preview=None,
        now_utc=NOW,
    )

    assert packet["status"] == "PLACEMENT_CONSTRUCTION_PREVIEW_REQUIRED"
    assert packet["source_placement_preview"]["artifact"]["status"] == "MISSING"
